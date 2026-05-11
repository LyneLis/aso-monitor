import gspread
from google_play_scraper import app
import os
import json
import requests
from datetime import datetime, timedelta

# Настройки
TOKEN = os.environ.get("TELEGRAM_TOKEN")
# Берем JSON из секретов GitHub
service_account_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1jHKbRYt0hJg29RWLIXZ2fL3et_hgzvkhCSxVtTjKV9g/edit"

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%H:%M:%S")

def check_apps():
    print(f"--- СТАРТ ПРОВЕРКИ ({get_minsk_time()}) ---")
    
    # Авторизация через Service Account
    gc = gspread.service_account_from_dict(service_account_info)
    sh = gc.open_by_url(SPREADSHEET_URL)
    worksheet = sh.get_worksheet(0) # Берем первый лист (apps)
    
    # Получаем все данные
    data = worksheet.get_all_records()
    print(f"✅ Данные получены напрямую из API. Строк: {len(data)}")

    user_stats = {}

    for i, row in enumerate(data):
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        geo = str(row.get('geo', 'us')).strip()
        c_id = str(row.get('chat_id', '')).strip()
        
        if c_id not in user_stats:
            user_stats[c_id] = {'checked': 0, 'updated': 0}
        
        user_stats[c_id]['checked'] += 1
        
        try:
            res = app(p_id, lang=geo, country=geo)
            old_title = str(row.get('title', '')).strip()
            new_title = str(res['title']).strip()
            
            # Для отладки в логах
            print(f"[{i+1}] {p_id} ({geo}) | Таблица: '{old_title[:15]}...' | Стор: '{new_title[:15]}...'")

            if new_title != old_title:
                print(f"    ⚠️ ИЗМЕНЕНИЕ НАЙДЕНО!")
                user_stats[c_id]['updated'] += 1
                msg = f"🔔 ИЗМЕНЕНИЕ! [{geo.upper()}]\n📦 {p_id}\n\nБыло: {old_title}\nСтало: {new_title}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": msg})
        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")

    # Финальный отчет
    for c_id, stats in user_stats.items():
        report = (f"🤖 Автопроверка GitHub (API Mode)\n"
                  f"⏰ {get_minsk_time()}\n"
                  f"📦 Проверено: {stats['checked']}\n"
                  f"⚠️ Обновлений: {stats['updated']}")
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()