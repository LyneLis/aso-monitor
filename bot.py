import pandas as pd
import requests
from google_play_scraper import app
import os

# Берем данные из секретов GitHub
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GSHEET_URL = os.environ.get("GSHEET_URL")

def fetch_gp_data(pkg_id, locale):
    """Парсинг данных из Google Play"""
    try:
        if "-" in locale:
            l_parts = locale.split("-")
            l_code, c_code = l_parts[0].lower(), l_parts[1].lower()
        else:
            l_code, c_code = locale.lower(), locale.lower()
        if l_code == "iw": l_code = "iw"
        return app(pkg_id, lang=l_code, country=c_code)
    except Exception as e:
        print(f"Ошибка при парсинге {pkg_id} ({locale}): {e}")
        return None

def send_telegram_msg(text):
    """Отправка текстового сообщения"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def send_telegram_file(file_path, caption):
    """Отправка файла отчета"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as file:
            response = requests.post(url, data={"chat_id": CHAT_ID, "caption": caption}, files={"document": file})
            print(f"Статус отправки файла: {response.status_code}")
    except Exception as e:
        print(f"Ошибка при отправке файла: {e}")

def run_check():
    try:
        # УМНАЯ ССЫЛКА: превращаем любую ссылку на таблицу в прямую ссылку на CSV
        if "/edit" in GSHEET_URL:
            base_url = GSHEET_URL.split('/edit')[0]
            csv_url = f"{base_url}/export?format=csv&gid=0"
        else:
            csv_url = GSHEET_URL

        df = pd.read_csv(csv_url)
        
        updates_found = 0
        errors_found = []
        full_report = "--- ПОЛНЫЙ ОТЧЕТ ОБ ИЗМЕНЕНИЯХ ASO ---\n\n"
        
        for _, row in df.iterrows():
            if pd.isna(row['package_id']) or pd.isna(row['geo']): continue
            
            pkg_id, geo = str(row['package_id']).strip(), str(row['geo']).strip()
            # Поля из таблицы
            old_title = str(row['title']) if not pd.isna(row['title']) else ""
            old_summary = str(row['summary']) if not pd.isna(row['summary']) else ""
            old_desc = str(row['description']) if not pd.isna(row['description']) else ""
            
            res = fetch_gp_data(pkg_id, geo)
            if res:
                changed = []
                if res['title'] != old_title: changed.append("TITLE (Заголовок)")
                if res['summary'] != old_summary: changed.append("SD (Краткое описание)")
                if res['description'] != old_desc: changed.append("FD (Полное описание)")
                
                if changed:
                    updates_found += 1
                    report_entry = (
                        f"📦 ПРИЛОЖЕНИЕ: {pkg_id}\n"
                        f"🌍 ГЕО: {geo.upper()}\n"
                        f"⚠️ ОБНАРУЖЕНЫ ИЗМЕНЕНИЯ: {', '.join(changed)}\n\n"
                        f"--- СТАРОЕ НАЗВАНИЕ ---\n{old_title}\n"
                        f"+++ НОВОЕ НАЗВАНИЕ +++\n{res['title']}\n\n"
                        f"--- СТАРОЕ КР. ОПИСАНИЕ ---\n{old_summary}\n"
                        f"+++ НОВОЕ КР. ОПИСАНИЕ +++\n{res['summary']}\n\n"
                        f"--- СТАРОЕ ПОЛН. ОПИСАНИЕ ---\n{old_desc[:200]}...\n" # Обрезаем в логе для красоты
                        f"+++ НОВОЕ ПОЛН. ОПИСАНИЕ +++\n{res['description'][:200]}...\n"
                        f"{'='*40}\n\n"
                    )
                    full_report += report_entry
                    send_telegram_msg(f"🔔 Изменение найдено! [{geo.upper()}] {pkg_id}")
            else:
                errors_found.append(f"❌ Не удалось получить данные для {pkg_id} ({geo})")
                
        if updates_found > 0:
            file_name = "aso_report.txt"
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(full_report)
            send_telegram_file(file_name, f"📊 Проверка завершена. Изменений: {updates_found}")
        elif not errors_found:
            send_telegram_msg("✅ Проверка: Изменений в сторах не найдено.")

        if errors_found:
            send_telegram_msg("⚠️ Ошибки при проверке некоторых приложений:\n\n" + "\n".join(errors_found))
            
    except Exception as e: 
        send_telegram_msg(f"🚨 Критическая ошибка: {e}")

if __name__ == "__main__":
    run_check()