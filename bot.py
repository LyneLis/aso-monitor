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

def send_telegram_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def send_telegram_file(file_path, caption):
    url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    with open(file_path, "rb") as file:
        requests.post(url, data={"chat_id": CHAT_ID, "caption": caption}, files={"document": file})

def run_check():
    try:
        csv_url = GSHEET_URL.replace("/edit?gid=", "/export?format=csv&gid=")
        df = pd.read_csv(csv_url)
        
        updates_found = 0
        errors_found = []
        full_report = "--- ASO COMPARISON REPORT ---\n\n"
        
        for _, row in df.iterrows():
            if pd.isna(row['package_id']) or pd.isna(row['geo']): continue
            
            pkg_id, geo = str(row['package_id']).strip(), str(row['geo']).strip()
            old_title, old_summary, old_desc = str(row['title']), str(row['summary']), str(row['description'])
            
            try:
                res = fetch_gp_data(pkg_id, geo)
                changed = []
                if res['title'] != old_title: changed.append("Title")
                if res['summary'] != old_summary: changed.append("SD")
                if res['description'] != old_desc: changed.append("FD")
                
                if changed:
                    updates_found += 1
                    report_entry = (
                        f"📦 [{geo.upper()}] {pkg_id}\n"
                        f"ИЗМЕНЕНО: {', '.join(changed)}\n\n"
                        f"--- OLD TITLE ---\n{old_title}\n"
                        f"--- NEW TITLE ---\n{res['title']}\n\n"
                        f"--- OLD SD ---\n{old_summary}\n"
                        f"--- NEW SD ---\n{res['summary']}\n\n"
                        f"--- OLD FD ---\n{old_desc}\n"
                        f"--- NEW FD ---\n{res['description']}\n"
                        f"{'='*30}\n\n"
                    )
                    full_report += report_entry
                    send_telegram_msg(f"🔔 Изменение в {pkg_id} ({geo})")
            except Exception as e:
                # Собираем ошибки, чтобы не молчать
                errors_found.append(f"❌ Ошибка {pkg_id} ({geo}): {e}")
                
        # Отправляем файл, если есть изменения
        if updates_found > 0:
            file_name = "aso_report.txt"
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(full_report)
            send_telegram_file(file_name, f"📊 Найдено изменений: {updates_found}. Файл для нейросети готов.")
        
        # Если изменений нет, но ошибок тоже нет
        elif not errors_found:
            send_telegram_msg("✅ Автопроверка: Изменений в сторах не найдено.")

        # Если были ошибки по конкретным приложениям — присылаем их списком
        if errors_found:
            send_telegram_msg("⚠️ Проблемы при проверке некоторых приложений:\n\n" + "\n".join(errors_found))
            
    except Exception as e: 
        send_telegram_msg(f"🚨 Критическая ошибка скрипта: {e}")

if __name__ == "__main__":
    run_check()