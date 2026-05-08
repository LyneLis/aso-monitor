import json
import pandas as pd
import requests
from google_play_scraper import app
import os

# Загружаем настройки из секретов GitHub
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GSHEET_URL = os.environ.get("GSHEET_URL")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def run_check():
    try:
        # Читаем таблицу напрямую через pandas (CSV экспорт)
        csv_url = GSHEET_URL.replace("/edit?gid=", "/export?format=csv&gid=")
        df = pd.read_csv(csv_url)
        
        updates_found = False
        
        for index, row in df.iterrows():
            pkg_id = row['package_id']
            geo = row['geo']
            old_title = row['title']
            
            # Тянем свежие данные
            res = app(pkg_id, lang='en', country=geo)
            
            if res['title'] != old_title:
                msg = f"🔔 АВТО-ПРОВЕРКА: Изменение у {pkg_id}!\nБыло: {old_title}\nСтало: {res['title']}"
                send_telegram(msg)
                updates_found = True
        
        if not updates_found:
            print("Изменений не найдено")
            
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    run_check()