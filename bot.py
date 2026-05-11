import pandas as pd
import requests
from google_play_scraper import app
import os
import time
from datetime import datetime, timedelta

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GS_URL = os.environ.get("GSHEET_URL")

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%H:%M:%S")

def check_apps():
    # Обход кэша Google через случайное число в ссылке
    cache_buster = int(time.time())
    csv_url = GS_URL.split('/edit')[0] + f"/export?format=csv&gid=0&cb={cache_buster}"
    
    print(f"--- Старт автопроверки ({get_minsk_time()}) ---")
    
    try:
        df = pd.read_csv(csv_url)
        total_apps = len(df)
    except Exception as e:
        print(f"Ошибка загрузки CSV: {e}")
        return

    updated_count = 0
    checked_count = 0
    results_found = []

    for _, row in df.iterrows():
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        geo = str(row.get('geo', 'us')).strip()
        c_id = str(row.get('chat_id', '')).strip()
        checked_count += 1
        
        try:
            res = app(p_id, lang=geo, country=geo)
            old_title = str(row.get('title', '')).strip()
            new_title = str(res['title']).strip()
            
            if new_title != old_title:
                updated_count += 1
                msg = f"🔔 ИЗМЕНЕНИЕ! [{geo.upper()}]\n📦 {p_id}\n\nБыло: {old_title}\nСтало: {new_title}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": msg})
                results_found.append(f"✅ {p_id}: ИЗМЕНЕНО")
            else:
                results_found.append(f"🔹 {p_id}: ок")
        except:
            results_found.append(f"❌ {p_id}: ошибка")

    # ОТПРАВЛЯЕМ СТАТУС В ЛЮБОМ СЛУЧАЕ (чтобы ты видел, что бот работает)
    # Берем первый chat_id из таблицы, чтобы хоть кому-то пришел отчет
    if total_apps > 0:
        first_chat_id = str(df.iloc[0].get('chat_id', '')).strip()
        status_report = (
            f"🤖 Автопроверка GitHub завершена\n"
            f"⏰ Время: {get_minsk_time()}\n"
            f"📦 Проверено: {checked_count}\n"
            f"⚠️ Найдено изменений: {updated_count}\n"
            f"────────────────\n" + "\n".join(results_found[:10]) # первые 10 для лога
        )
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": first_chat_id, "text": status_report})

if __name__ == "__main__":
    check_apps()