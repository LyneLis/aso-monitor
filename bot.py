import json
import pandas as pd
import requests
from google_play_scraper import app
import os

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GSHEET_URL = os.environ.get("GSHEET_URL")

def fetch_gp_data(pkg_id, locale):
    if "-" in locale:
        l_parts = locale.split("-")
        l_code, c_code = l_parts[0].lower(), l_parts[1].lower()
    else:
        l_code, c_code = locale.lower(), locale.lower()
    if l_code == "iw": l_code = "iw"
    return app(pkg_id, lang=l_code, country=c_code)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def run_check():
    try:
        csv_url = GSHEET_URL.replace("/edit?gid=", "/export?format=csv&gid=")
        df = pd.read_csv(csv_url)
        updates_found = False
        
        for _, row in df.iterrows():
            if pd.isna(row['package_id']) or pd.isna(row['geo']): continue
            
            pkg_id = str(row['package_id']).strip()
            geo = str(row['geo']).strip()
            
            old_title = str(row['title'])
            old_summary = str(row['summary'])
            old_desc = str(row['description'])
            
            try:
                # Теперь робот использует правильную функцию для парсинга локали
                res = fetch_gp_data(pkg_id, geo)
                
                changed = []
                if res['title'] != old_title: changed.append("Title")
                if res['summary'] != old_summary: changed.append("SD")
                if res['description'] != old_desc: changed.append("FD")
                
                if changed:
                    msg = f"🔔 АВТО-ПРОВЕРКА [{geo.upper()}]:\nНайдено изменение у {res['title']}!\nID: {pkg_id}\n\nИзменено: {', '.join(changed)}"
                    send_telegram(msg)
                    updates_found = True
            except Exception as e:
                print(f"Не удалось проверить {pkg_id} в локали {geo}. Ошибка: {e}")
                
        if not updates_found: 
            print("Изменений не найдено")
            
    except Exception as e: 
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    run_check()