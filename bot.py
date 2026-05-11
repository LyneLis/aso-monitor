import pandas as pd
import requests
from google_play_scraper import app
import os
import time
import random
from datetime import datetime, timedelta

TOKEN = os.environ.get("TELEGRAM_TOKEN")
GS_URL = os.environ.get("GSHEET_URL")

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%H:%M:%S")

def check_apps():
    # Генерируем абсолютно случайный параметр для каждой попытки обхода кэша
    rand_id = random.randint(1000, 9999)
    csv_url = GS_URL.split('/edit')[0] + f"/export?format=csv&gid=0&cache_bust={rand_id}"
    
    print(f"--- ЗАПУСК АВТОПРОВЕРКИ ({get_minsk_time()}) ---")
    print(f"Использую URL: {csv_url}")
    
    try:
        df = pd.read_csv(csv_url)
        print(f"✅ Таблица успешно загружена. Строк: {len(df)}")
    except Exception as e:
        print(f"❌ ОШИБКА ЗАГРУЗКИ CSV: {e}")
        return

    user_stats = {}
    
    for i, row in df.iterrows():
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        geo = str(row.get('geo', 'us')).strip()
        c_id = str(row.get('chat_id', '')).strip()
        
        if c_id not in user_stats:
            user_stats[c_id] = {'checked': 0, 'updated': 0}
        
        user_stats[c_id]['checked'] += 1
        
        try:
            print(f"[{i+1}] Проверяю {p_id} ({geo})...")
            res = app(p_id, lang=geo, country=geo)
            
            # ВНИМАНИЕ: Смотрим логи здесь!
            old_title = str(row.get('title', '')).strip()
            new_title = str(res['title']).strip()
            
            print(f"    В таблице: '{old_title}'")
            print(f"    В сторе:   '{new_title}'")
            
            if new_title != old_title:
                print(f"    ⚠️ ЕСТЬ ИЗМЕНЕНИЕ!")
                user_stats[c_id]['updated'] += 1
                msg = f"🔔 ИЗМЕНЕНИЕ! [{geo.upper()}]\n📦 {p_id}\n\nБыло: {old_title}\nСтало: {new_title}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": msg})
            else:
                print(f"    ✅ Совпадает.")
                
        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")

    # Финальный сигнал, что скрипт дошел до конца
    for c_id, stats in user_stats.items():
        report = (f"🤖 Автопроверка GitHub завершена\n"
                  f"⏰ {get_minsk_time()}\n"
                  f"📦 Проверено: {stats['checked']}\n"
                  f"⚠️ Обновлений: {stats['updated']}")
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()