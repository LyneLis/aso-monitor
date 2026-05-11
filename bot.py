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
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%H:%M:%S")

def check_apps():
    print(f"--- СТАРТ ПРОВЕРКИ ({get_minsk_time()}) ---")
    
    try:
        gc = gspread.service_account_from_dict(service_account_info)
        sh = gc.open_by_url(SPREADSHEET_URL)
        # ВАЖНО: убедись, что лист apps первый, или укажи его имя:
        worksheet = sh.get_worksheet(0) 
        data = worksheet.get_all_records()
        print(f"✅ Данные получены. Строк: {len(data)}")
    except Exception as e:
        print(f"❌ Ошибка Google API: {e}")
        return

    user_stats = {}

    for i, row in enumerate(data):
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        # Получаем локаль (например "ru-RU")
        full_geo = str(row.get('geo', 'us')).strip()
        c_id = str(row.get('chat_id', '')).strip()
        
        # Разрезаем "ru-RU" на "ru" и "RU"
        if "-" in full_geo:
            parts = full_geo.split("-")
            l_code = parts[0].lower()
            c_code = parts[1].upper()
        else:
            l_code = full_geo.lower()
            c_code = full_geo.upper()

        if c_id not in user_stats:
            user_stats[c_id] = {'checked': 0, 'updated': 0}
        user_stats[c_id]['checked'] += 1
        
        try:
            # Запрашиваем данные с правильными кодами
            res = app(p_id, lang=l_code, country=c_code)
            
            old_title = str(row.get('title', '')).strip()
            new_title = str(res['title']).strip()
            
            print(f"[{i+1}] {p_id} ({l_code}-{c_code}) | Таблица: '{old_title[:15]}' | Стор: '{new_title[:15]}'")

            if new_title != old_title:
                print(f"    ⚠️ ИЗМЕНЕНИЕ!")
                user_stats[c_id]['updated'] += 1
                msg = f"🔔 ИЗМЕНЕНИЕ! [{full_geo.upper()}]\n📦 {p_id}\n\nБыло: {old_title}\nСтало: {new_title}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": msg})
            else:
                print(f"    ✅ Ок")

        except Exception as e:
            # Если всё равно ошибка - выводим детали
            print(f"    ❌ Ошибка {p_id} (locale: {l_code}-{c_code}): {e}")

    # Финальные отчеты
    for c_id, stats in user_stats.items():
        if stats['checked'] > 0:
            report = (f"🤖 Автопроверка GitHub (API Mode)\n"
                      f"⏰ {get_minsk_time()}\n"
                      f"📦 Проверено: {stats['checked']}\n"
                      f"⚠️ Обновлений: {stats['updated']}")
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()