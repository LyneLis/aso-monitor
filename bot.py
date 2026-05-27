import json
import time

from core import (
    GeminiClient,
    Settings,
    TelegramClient,
    add_changed_locale_to_batch,
    check_item_snapshots,
    format_changes_report,
    get_minsk_time,
    history_entry_from_snapshot,
    snapshot_from_row,
)
from core.parsing import fetch_app_data
from core.telegram import BOT_CHUNK_LIMIT
from core.display import publisher_from_fetch, resolve_english_app_label
from sheets import GspreadAppsRepository
from sheets.serialization import parse_json_list

settings = Settings.from_env()
telegram = TelegramClient(settings, message_limit=BOT_CHUNK_LIMIT)
gemini = GeminiClient(settings, verbose=True)


def write_metadata_to_row(row, metadata):
    publisher = publisher_from_fetch(metadata or {})
    if publisher:
        row["publisher"] = publisher


def write_snapshot_to_row(row, snap, metadata=None):
    row["title"] = snap.title
    row["summary"] = snap.summary
    row["description"] = snap.description
    row["icon"] = snap.icon
    row["header_image"] = snap.header_image
    row["screenshots"] = json.dumps(snap.screenshots, ensure_ascii=False)
    write_metadata_to_row(row, metadata)


def append_check_log(row, status, **extra):
    current_log = parse_json_list(row.get("check_log", "[]"))
    entry = {"time": get_minsk_time(), "status": status}
    entry.update({key: value for key, value in extra.items() if value})
    current_log.append(entry)
    row["check_log"] = json.dumps(current_log[-5:], ensure_ascii=False)


def save_row_error(repo, row_index, row, error):
    error_text = str(error)[:300]
    append_check_log(row, "❌ Авто: Ошибка", error=error_text)
    try:
        repo.update_row(row_index, row)
    except Exception as save_error:
        print(f"    ❌ Не удалось записать ошибку в таблицу: {save_error}")


def check_apps(fetcher=None):
    print(f"--- СТАРТ ПРОВЕРКИ v3.23 (Интервал 12ч) ({get_minsk_time()}) ---")
    repo = GspreadAppsRepository(settings)
    try:
        repo.open()
    except Exception as e:
        print(f"❌ Ошибка API Таблиц: {e}")
        return

    user_stats = {}
    batched_alerts = {}
    rows = list(repo.iter_rows())
    group_records = {}
    display_name_cache = {}
    label_fetcher = fetcher or fetch_app_data

    for _, row in rows:
        p_id = str(row.get("package_id", "")).strip()
        c_id = str(row.get("chat_id", "")).strip()
        if p_id and p_id != "nan":
            group_records.setdefault((p_id, c_id), []).append(row)

    def app_display_name_for(p_id, c_id):
        cache_key = (p_id, c_id)
        if cache_key not in display_name_cache:
            display_name_cache[cache_key] = resolve_english_app_label(
                p_id,
                group_records.get(cache_key, []),
                fetcher=label_fetcher,
            )
        return display_name_cache[cache_key]

    for row_index, row in rows:
        p_id = str(row.get("package_id", "")).strip()
        if not p_id or p_id == "nan":
            continue

        c_id = str(row.get("chat_id", "")).strip()
        has_owner = bool(c_id and c_id.lower() != "nan")

        if has_owner:
            user_stats.setdefault(c_id, {"checked": 0, "updated": 0})
            user_stats[c_id]["checked"] += 1

        full_geo = str(row.get("geo", "us")).strip()

        try:
            old_scr, history, current_log = GspreadAppsRepository.parse_row_lists(row)

            old_snap, is_table_error = snapshot_from_row(
                row.get("title"),
                row.get("summary"),
                row.get("description"),
                row.get("icon"),
                row.get("header_image"),
                old_scr,
            )
            is_ios = str(p_id).isdigit()

            outcome = check_item_snapshots(
                p_id,
                full_geo,
                old_snap,
                history,
                is_table_error,
                label_style="bot",
                is_ios=is_ios,
                history_limit=3,
                fetcher=fetcher,
            )
            new_snap = outcome.new_snapshot
            result = outcome.result
            write_metadata_to_row(row, outcome.metadata)

            pending_alert = None
            if result.has_changes:
                changes = result.changed
                print(f"    ⚠️ Изменение в {p_id} ({full_geo})")
                current_log.append({
                    "time": get_minsk_time(),
                    "status": f"🔴 Авто: Изменение ({', '.join(changes)})",
                })

                write_snapshot_to_row(row, new_snap, outcome.metadata)
                history.append(history_entry_from_snapshot(old_snap, get_minsk_time()))
                row["history"] = json.dumps(history[-5:], ensure_ascii=False)

                if has_owner:
                    pending_alert = (
                        p_id,
                        c_id,
                        full_geo,
                        old_snap,
                        new_snap,
                        changes,
                        result.text_payload,
                        result.is_rollback,
                    )
            elif result.is_table_error:
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Исправление ошибки"})
                write_snapshot_to_row(row, new_snap, outcome.metadata)
            else:
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Без изменений"})

            row["check_log"] = json.dumps(current_log[-5:], ensure_ascii=False)
            repo.update_row(row_index, row)
            if pending_alert:
                (
                    alert_p_id,
                    alert_c_id,
                    alert_geo,
                    alert_old,
                    alert_new,
                    alert_changes,
                    text_payload,
                    is_rollback,
                ) = pending_alert
                user_stats[alert_c_id]["updated"] += 1
                app_display_name = app_display_name_for(alert_p_id, alert_c_id)
                add_changed_locale_to_batch(
                    batched_alerts,
                    alert_p_id,
                    alert_c_id,
                    alert_geo,
                    alert_old,
                    alert_new,
                    alert_changes,
                    text_payload,
                    is_rollback=is_rollback,
                    app_display_name=app_display_name,
                )
            time.sleep(0.6)
        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")
            save_row_error(repo, row_index, row, e)

    for (pkg_id, c_id, is_ios), data in batched_alerts.items():
        os_icon = "🍎" if is_ios else "🤖"
        msg_prefix = "🔄 АВТО-ОТКАТ" if data["is_rollback"] else "🔔 ИЗМЕНЕНИЯ"
        app_display_name = data.get("app_display_name") or pkg_id
        summary_msg = f"{msg_prefix} {os_icon}\n📦 {app_display_name}\n\n"
        for geo, changes_list in data["changes"].items():
            summary_msg += f"🌍 [{geo.upper()}]: {', '.join(changes_list)}\n"
        telegram.send_message(summary_msg, c_id)

        if data["texts"]:
            full_report = format_changes_report(app_display_name, data["texts"])
            telegram.send_document(full_report, f"report_{pkg_id}.txt", f"📄 Отчет: {app_display_name}", c_id)

        for vis in data["visuals"]:
            geo = vis["geo"].upper()
            if vis["type"] == "diff":
                telegram.send_visual_diff(c_id, vis["old"], vis["new"], vis["name"], app_display_name, geo)
            elif vis["type"] == "screens":
                telegram.send_screenshots(c_id, vis["screens"], app_display_name, geo)

        if data["texts"]:
            print(f"🧠 Запуск ИИ для {app_display_name}...")
            try:
                ai_msg = gemini.analyze_batched_changes(data["texts"])
                if not gemini.is_error_response(ai_msg):
                    print("✅ Анализ получен, отправляю в TG (с разбивкой)...")
                    telegram.send_ai_analysis(c_id, ai_msg)
                else:
                    print(f"⚠️ ИИ вернул ошибку или пустой ответ: {ai_msg}")
            except Exception as ai_err:
                print(f"❌ Критическая ошибка при работе с ИИ: {ai_err}")

            print("⏳ Ожидание 45 секунд для сброса лимитов ИИ...")
            time.sleep(45)


if __name__ == "__main__":
    check_apps()
