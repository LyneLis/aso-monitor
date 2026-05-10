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
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в ТГ: {e}")

def run_check():
    try:
        csv_url = GSHEET_URL.replace("/edit?gid=", "/export?format=csv&gid=")
        df = pd.read_csv(csv_url)
        
        updates_count = 0
        errors = []
        apps_checked = 0
        
        for _, row in df.iterrows():
            if pd.isna(row['package_id']) or pd.isna(row['geo']): continue
            
            pkg_id = str(row['package_id']).strip()
            geo = str(row['geo']).strip()
            apps_checked += 1
            
            old_title = str(row['title'])
            old_summary = str(row['summary'])
            old_desc = str(row['description'])
            
            try:
                res = fetch_gp_data(pkg_id, geo)
                
                changed = []
                if res['title'] != old_title: changed.append("Title")
                if res['summary'] != old_summary: changed.append("SD")
                if res['description'] != old_desc: changed.append("FD")
                
                if changed:
                    msg = f"🔔 ИЗМЕНЕНИЕ [{geo.upper()}]:\nПриложение: {res['title']}\nID: {pkg_id}\n\nИзменено: {', '.join(changed)}"
                    send_telegram(msg)
                    updates_count += 1
            except Exception as e:
                # Фиксируем, что именно пошло не так
                errors.append(f"❌ {pkg_id} ({geo}): {str(e)}")
                
        # --- ФИНАЛЬНЫЕ УВЕДОМЛЕНИЯ ---
        
        # 1. Если вообще не нашли изменений
        if updates_count == 0 and not errors:
            send_telegram(f"✅ Ежедневная проверка завершена.\nПроверено приложений: {apps_checked}\nИзменений не обнаружено. Все спокойно!")
        
        # 2. Если были ошибки
        if errors:
            error_report = "\n".join(errors)
            send_telegram(f"⚠️ ОТЧЕТ ОБ ОШИБКАХ ПРОВЕРКИ:\n\n{error_report}")

        # 3. Если были изменения (дополнительное резюме)
        if updates_count > 0:
            send_telegram(f"📊 Итог проверки: найдено изменений в {updates_count} приложениях.")
            
    except Exception as e: 
        send_telegram(f"🚨 КРИТИЧЕСКАЯ ОШИБКА СКРИПТА:\n{str(e)}")

if __name__ == "__main__":
    run_check()