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
from core.telegram import BOT_CHUNK_LIMIT
from sheets import GspreadAppsRepository

settings = Settings.from_env()
telegram = TelegramClient(settings, message_limit=BOT_CHUNK_LIMIT)
gemini = GeminiClient(settings, verbose=True)


def write_snapshot_to_row(row, snap):
    row["title"] = snap.title
    row["summary"] = snap.summary
    row["description"] = snap.description
    row["icon"] = snap.icon
    row["header_image"] = snap.header_image
    row["screenshots"] = json.dumps(snap.screenshots, ensure_ascii=False)


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

    for row_index, row in repo.iter_rows():
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

            if result.has_changes:
                changes = result.changed
                print(f"    ⚠️ Изменение в {p_id} ({full_geo})")
                current_log.append({
                    "time": get_minsk_time(),
                    "status": f"🔴 Авто: Изменение ({', '.join(changes)})",
                })

                if has_owner:
                    user_stats[c_id]["updated"] += 1
                    add_changed_locale_to_batch(
                        batched_alerts,
                        p_id,
                        c_id,
                        full_geo,
                        old_snap,
                        new_snap,
                        changes,
                        result.text_payload,
                        is_rollback=result.is_rollback,
                    )

                write_snapshot_to_row(row, new_snap)
                history.append(history_entry_from_snapshot(old_snap, get_minsk_time()))
                row["history"] = json.dumps(history[-5:], ensure_ascii=False)
            elif result.is_table_error:
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Исправление ошибки"})
                write_snapshot_to_row(row, new_snap)
            else:
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Без изменений"})

            row["check_log"] = json.dumps(current_log[-5:], ensure_ascii=False)
            repo.update_row(row_index, row)
            time.sleep(0.6)
        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")

    for (pkg_id, c_id, is_ios), data in batched_alerts.items():
        os_icon = "🍎" if is_ios else "🤖"
        msg_prefix = "🔄 АВТО-ОТКАТ" if data["is_rollback"] else "🔔 ИЗМЕНЕНИЯ"
        summary_msg = f"{msg_prefix} {os_icon}\n📦 {pkg_id}\n\n"
        for geo, changes_list in data["changes"].items():
            summary_msg += f"🌍 [{geo.upper()}]: {', '.join(changes_list)}\n"
        telegram.send_message(summary_msg, c_id)

        if data["texts"]:
            full_report = format_changes_report(pkg_id, data["texts"])
            telegram.send_document(full_report, f"report_{pkg_id}.txt", f"📄 Отчет: {pkg_id}", c_id)

        for vis in data["visuals"]:
            geo = vis["geo"].upper()
            if vis["type"] == "diff":
                telegram.send_visual_diff(c_id, vis["old"], vis["new"], vis["name"], pkg_id, geo)
            elif vis["type"] == "screens":
                telegram.send_screenshots(c_id, vis["screens"], pkg_id, geo)

        if data["texts"]:
            print(f"🧠 Запуск ИИ для {pkg_id}...")
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
