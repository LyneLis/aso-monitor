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
    print(f"--- СТАРТ ПРОВЕРКИ С АВТОЗАПИСЬЮ ({get_minsk_time()}) ---")
    
    try:
        gc = gspread.service_account_from_dict(service_account_info)
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.get_worksheet(0) # Лист apps должен быть первым
        
        # Получаем заголовки, чтобы знать номера колонок
        headers = worksheet.row_values(1)
        col_map = {name: i+1 for i, name in enumerate(headers)}
        
        data = worksheet.get_all_records()
        print(f"✅ Таблица загружена. Строк: {len(data)}")
    except Exception as e:
        print(f"❌ Ошибка API: {e}")
        return

    user_stats = {}

    for i, row in enumerate(data):
        # Номер строки в самой таблице (i=0 это 2-я строка таблицы)
        row_number = i + 2
        
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
            
            old_t = str(row.get('title', '')).strip()
            old_s = str(row.get('summary', '')).strip()
            old_d = str(row.get('description', '')).strip()
            
            new_t = str(res['title']).strip()
            new_s = str(res['summary']).strip()
            new_d = str(res['description']).strip()

            changes = []
            if new_t != old_t: changes.append("Название")
            if new_s != old_s: changes.append("SD")
            if new_d != old_d: changes.append("FD")

            if changes:
                print(f"    ⚠️ Изменение в {p_id}. Отправляю отчет и обновляю таблицу...")
                user_stats[c_id]['updated'] += 1
                
                # 1. Отправляем сообщение
                msg = f"🔔 ИЗМЕНЕНИЕ! [{full_geo.upper()}]\n📦 {p_id}\n\nПоля: {', '.join(changes)}\n\nНазвание: {new_t}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": msg})
                
                # 2. Формируем и отправляем файл
                report_content = (
                    f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ\nДата: {get_minsk_time()}\nПриложение: {p_id}\nЛокаль: {full_geo}\n"
                    f"{'='*30}\n\n--- НОВОЕ НАЗВАНИЕ ---\n{new_t}\n\n--- НОВЫЙ SD ---\n{new_s}\n\n--- НОВЫЙ FD ---\n{new_d}\n"
                )
                file_path = f"report_{p_id}.txt"
                with open(file_path, "w", encoding="utf-8") as f: f.write(report_content)
                
                with open(file_path, "rb") as f:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", 
                                 data={"chat_id": c_id, "caption": f"📄 Детальный отчет: {p_id}"}, 
                                 files={"document": f})
                os.remove(file_path)

                # 3. ЗАПИСЫВАЕМ НОВЫЕ ДАННЫЕ В ТАБЛИЦУ (чтобы не спамить в след. раз)
                updates = []
                if "title" in col_map:
                    worksheet.update_cell(row_number, col_map["title"], new_t)
                if "summary" in col_map:
                    worksheet.update_cell(row_number, col_map["summary"], new_s)
                if "description" in col_map:
                    worksheet.update_cell(row_number, col_map["description"], new_d)
                
                print(f"    ✅ Данные в таблице для {p_id} обновлены.")
            else:
                print(f"    ✅ {p_id}: Без изменений.")

        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")

    # Финальный отчет
    for c_id, stats in user_stats.items():
        if stats['checked'] > 0:
            report = (f"⚙️ Статус GitHub\n⏰ {get_minsk_time()}\n"
                      f"📦 Проверено: {stats['checked']}\n⚠️ Обновлено: {stats['updated']}")
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()