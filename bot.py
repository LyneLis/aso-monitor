import json
import time

from core import (
    GeminiClient,
    Settings,
    TelegramClient,
    detect_changes_with_table_error,
    fetch_app_data,
    format_changes_report,
    get_minsk_time,
    history_entry_from_snapshot,
    snapshot_from_fetch,
    snapshot_from_row,
)
from core.telegram import BOT_CHUNK_LIMIT
from sheets import GspreadAppsRepository

settings = Settings.from_env()
telegram = TelegramClient(settings, message_limit=BOT_CHUNK_LIMIT)
gemini = GeminiClient(settings, verbose=True)


def check_apps():
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
            res = fetch_app_data(p_id, full_geo)
            old_scr, history, current_log = GspreadAppsRepository.parse_row_lists(row)

            old_snap, is_table_error = snapshot_from_row(
                row.get("title"),
                row.get("summary"),
                row.get("description"),
                row.get("icon"),
                row.get("header_image"),
                old_scr,
            )
            new_snap = snapshot_from_fetch(res)
            is_ios = str(p_id).isdigit()

            result = detect_changes_with_table_error(
                old_snap,
                new_snap,
                history,
                is_table_error,
                label_style="bot",
                is_ios=is_ios,
                history_limit=3,
            )

            if result.has_changes:
                changes = result.changed
                print(f"    ⚠️ Изменение в {p_id} ({full_geo})")
                current_log.append({
                    "time": get_minsk_time(),
                    "status": f"🔴 Авто: Изменение ({', '.join(changes)})",
                })

                if has_owner:
                    user_stats[c_id]["updated"] += 1
                    b_key = (p_id, c_id, is_ios)
                    if b_key not in batched_alerts:
                        batched_alerts[b_key] = {"changes": {}, "texts": {}, "visuals": [], "is_rollback": False}

                    batched_alerts[b_key]["changes"][full_geo] = changes
                    if result.is_rollback:
                        batched_alerts[b_key]["is_rollback"] = True

                    if "Иконка" in changes:
                        batched_alerts[b_key]["visuals"].append({
                            "type": "diff",
                            "name": "Иконка",
                            "old": old_snap.icon,
                            "new": new_snap.icon,
                            "geo": full_geo,
                        })
                    if "Feature Graphic" in changes:
                        batched_alerts[b_key]["visuals"].append({
                            "type": "diff",
                            "name": "Feature Graphic",
                            "old": old_snap.header_image,
                            "new": new_snap.header_image,
                            "geo": full_geo,
                        })
                    if "Скриншоты" in changes and new_snap.screenshots:
                        batched_alerts[b_key]["visuals"].append({
                            "type": "screens",
                            "screens": new_snap.screenshots,
                            "geo": full_geo,
                        })

                    if result.text_payload:
                        batched_alerts[b_key]["texts"][full_geo] = result.text_payload

                row["title"] = new_snap.title
                row["summary"] = new_snap.summary
                row["description"] = new_snap.description
                row["icon"] = new_snap.icon
                row["header_image"] = new_snap.header_image
                row["screenshots"] = json.dumps(new_snap.screenshots, ensure_ascii=False)
                history.append(history_entry_from_snapshot(old_snap, get_minsk_time()))
                row["history"] = json.dumps(history[-5:], ensure_ascii=False)
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
