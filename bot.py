import pandas as pd
import requests
from google_play_scraper import app
import os
from datetime import datetime, timedelta

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GS_URL = os.environ.get("GSHEET_URL")

def get_minsk_time():
    """Получаем текущее время по Минску для красивого лога"""
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%H:%M:%S")

def check_apps():
    csv_url = GS_URL.split('/edit')[0] + "/export?format=csv&gid=0"
    df = pd.read_csv(csv_url)
    
    # Словарь для сбора статистики по каждому пользователю (chat_id)
    user_stats = {}
    
    for _, row in df.iterrows():
        try:
            p_id, geo, c_id = str(row['package_id']).strip(), str(row['geo']).strip(), str(row['chat_id']).strip()
            
            if p_id == 'nan' or c_id == 'nan': continue
            
            # Создаем счетчики для пользователя, если их еще нет
            if c_id not in user_stats:
                user_stats[c_id] = {'checked': 0, 'updated': 0}
            
            user_stats[c_id]['checked'] += 1
            
            res = app(p_id, lang=geo, country=geo)
            
            changes = []
            if res['title'] != str(row['title']): changes.append("Название")
            if res['summary'] != str(row['summary']): changes.append("Краткое описание")
            if res['description'] != str(row['description']): changes.append("Полное описание")
            
            if changes:
                user_stats[c_id]['updated'] += 1
                msg = f"🔔 ИЗМЕНЕНИЕ! [{geo.upper()}]\n📦 {p_id}\n\nПоля: {', '.join(changes)}\n\nНовый заголовок: {res['title']}"
                
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                             data={"chat_id": c_id, "text": msg})
                
                with open("update.txt", "w", encoding="utf-8") as f:
                    f.write(f"Новое полное описание:\n\n{res['description']}")
                
                with open("update.txt", "rb") as f:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", 
                                 data={"chat_id": c_id}, files={"document": f})
        except Exception as e: 
            print(f"Ошибка при проверке {p_id}: {e}")
            continue

    # ФИНАЛЬНЫЙ СТАТУС-ОТЧЕТ ВСЕМ ПОЛЬЗОВАТЕЛЯМ
    current_time = get_minsk_time()
    for c_id, stats in user_stats.items():
        status_msg = (
            f"⚙️ Системный статус (Минск: {current_time})\n"
            f"Автопроверка успешно завершена!\n"
            f"──────────────\n"
            f"Проверено ваших приложений: {stats['checked']}\n"
            f"Найдено обновлений: {stats['updated']}"
        )
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                     data={"chat_id": c_id, "text": status_msg})

if __name__ == "__main__":
    check_apps()