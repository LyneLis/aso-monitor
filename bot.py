import gspread
from google_play_scraper import app
import os
import json
import requests
from datetime import datetime, timedelta

# Настройки
TOKEN = os.environ.get("TELEGRAM_TOKEN")
service_account_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1jHKbRYt0hJg29RWLIXZ2fL3et_hgzvkhCSxVtTjKV9g/edit"

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

def check_apps():
    print(f"--- СТАРТ ПРОВЕРКИ С ФАЙЛАМИ ({get_minsk_time()}) ---")
    
    try:
        gc = gspread.service_account_from_dict(service_account_info)
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.get_worksheet(0) 
        data = worksheet.get_all_records()
        print(f"✅ Таблица загружена напрямую. Строк: {len(data)}")
    except Exception as e:
        print(f"❌ Ошибка API: {e}")
        return

    user_stats = {}

    for i, row in enumerate(data):
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        full_geo = str(row.get('geo', 'us')).strip()
        c_id = str(row.get('chat_id', '')).strip()
        
        if c_id not in user_stats:
            user_stats[c_id] = {'checked': 0, 'updated': 0}
        user_stats[c_id]['checked'] += 1

        # Парсинг локали
        if "-" in full_geo:
            parts = full_geo.split("-")
            l_code, c_code = parts[0].lower(), parts[1].upper()
        else:
            l_code, c_code = full_geo.lower(), full_geo.upper()

        try:
            res = app(p_id, lang=l_code, country=c_code)
            
            # Данные из таблицы
            old_t = str(row.get('title', '')).strip()
            old_s = str(row.get('summary', '')).strip()
            old_d = str(row.get('description', '')).strip()
            
            # Данные из стора
            new_t = str(res['title']).strip()
            new_s = str(res['summary']).strip()
            new_d = str(res['description']).strip()

            changes = []
            if new_t != old_t: changes.append("Название")
            if new_s != old_s: changes.append("Краткое описание (SD)")
            if new_d != old_d: changes.append("Полное описание (FD)")

            if changes:
                print(f"    ⚠️ Найдено: {', '.join(changes)} для {p_id}")
                user_stats[c_id]['updated'] += 1
                
                # Текстовое сообщение
                msg = f"🔔 ИЗМЕНЕНИЕ! [{full_geo.upper()}]\n📦 {p_id}\n\nПоля: {', '.join(changes)}\n\nНазвание: {new_t}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": msg})
                
                # Формируем файл отчета
                report_content = (
                    f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ (Автопроверка GitHub)\n"
                    f"Дата: {get_minsk_time()}\n"
                    f"Приложение: {p_id}\n"
                    f"Локаль: {full_geo}\n"
                    f"{'='*30}\n\n"
                    f"--- СТАРОЕ НАЗВАНИЕ ---\n{old_t}\n\n"
                    f"--- НОВОЕ НАЗВАНИЕ ---\n{new_t}\n\n"
                    f"--- СТАРОЕ КРАТКОЕ (SD) ---\n{old_s}\n\n"
                    f"--- НОВОЕ КРАТКОЕ (SD) ---\n{new_s}\n\n"
                    f"--- СТАРОЕ ПОЛНОЕ (FD) ---\n{old_d}\n\n"
                    f"--- НОВОЕ ПОЛНОЕ (FD) ---\n{new_d}\n"
                )
                
                file_path = f"report_{p_id}.txt"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(report_content)
                
                # Отправляем файл
                with open(file_path, "rb") as f:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", 
                                 data={"chat_id": c_id, "caption": f"📄 Детальный отчет: {p_id}"}, 
                                 files={"document": f})
                
                # Удаляем временный файл
                os.remove(file_path)
            else:
                print(f"    ✅ {p_id} без изменений.")

        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")

    # Финальный отчет
    for c_id, stats in user_stats.items():
        if stats['checked'] > 0:
            report = (f"⚙️ Системный отчет GitHub\n"
                      f"⏰ Проверка: {get_minsk_time()}\n"
                      f"📦 Приложений: {stats['checked']}\n"
                      f"⚠️ Найдено изменений: {stats['updated']}")
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()