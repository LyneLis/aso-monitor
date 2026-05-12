import gspread
from google_play_scraper import app
import os
import json
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import time # Добавили для пауз

# Настройки окружения
TOKEN = os.environ.get("TELEGRAM_TOKEN")
service_account_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1jHKbRYt0hJg29RWLIXZ2fL3et_hgzvkhCSxVtTjKV9g/edit"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY, transport='rest')

ASO_PROMPT = """
Ты — ведущий ASO-стратег и эксперт по мобильному маркетингу.
Проведи глубокий анализ изменений Title, SD, FD. Выяви стратегию и дай план из 3 шагов.
"""

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

def analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d):
    if not GEMINI_API_KEY: return "❌ Ключ Gemini API не найден."
    full_prompt = (
        f"{ASO_PROMPT}\n\n"
        f"--- БЫЛО ---\nTitle: {old_t}\nShort Description: {old_s}\nFull Description: {old_d}\n\n"
        f"--- СТАЛО ---\nTitle: {new_t}\nShort Description: {new_s}\nFull Description: {new_d}"
    )
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(full_prompt)
        return response.text if response else "Ошибка ИИ"
    except Exception as e:
        return f"❌ Ошибка ИИ: {e}"

def check_apps():
    print(f"--- СТАРТ ПРОВЕРКИ v3.2 ({get_minsk_time()}) ---")
    
    try:
        gc = gspread.service_account_from_dict(service_account_info)
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.get_worksheet(0) 
        headers = worksheet.row_values(1)
        # Получаем все данные одним запросом (Read 1/1)
        all_rows = worksheet.get_all_values() 
        col_map = {name: i for i, name in enumerate(headers)}
    except Exception as e:
        print(f"❌ Ошибка API Таблиц: {e}"); return

    user_stats = {}

    # Начинаем со 2-й строки (индекс 1 в all_rows)
    for i, row_values in enumerate(all_rows[1:], start=2):
        # Создаем словарь текущей строки для удобной работы
        row = {headers[j]: (row_values[j] if j < len(row_values) else "") for j in range(len(headers))}
        
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        c_id = str(row.get('chat_id', '')).strip()
        has_owner = bool(c_id and c_id.lower() != 'nan')

        if has_owner:
            user_stats.setdefault(c_id, {'checked': 0, 'updated': 0})
            user_stats[c_id]['checked'] += 1

        full_geo = str(row.get('geo', 'us')).strip()
        l_code, c_code = (full_geo, full_geo.split("-")[1].upper()) if "-" in full_geo else (full_geo.lower(), full_geo.upper())
        if full_geo == "es-419": l_code, c_code = "es-419", "MX"

        try:
            res = app(p_id, lang=l_code, country=c_code)
            
            # Читаем старые данные
            old_t, old_s, old_d = str(row.get('title', '')), str(row.get('summary', '')), str(row.get('description', ''))
            old_icon, old_header = str(row.get('icon', '')), str(row.get('header_image', ''))
            
            try: old_scr = json.loads(str(row.get('screenshots', '[]')))
            except: old_scr = []
            try: history = json.loads(str(row.get('history', '[]')))
            except: history = []
            try: current_log = json.loads(str(row.get('check_log', '[]')))
            except: current_log = []

            # Новые данные
            new_t, new_s, new_d = str(res['title']).strip(), str(res['summary']).strip(), str(res['description']).strip()
            new_icon, new_header, new_scr = str(res['icon']).strip(), str(res.get('headerImage', '')).strip(), res['screenshots']

            changes = []
            if new_t != old_t: changes.append("Название")
            if new_s != old_s: changes.append("SD")
            if new_d != old_d: changes.append("FD")
            if old_icon and old_icon != 'nan' and new_icon != old_icon: changes.append("Иконка")
            if old_header and old_header != 'nan' and new_header != old_header: changes.append("Feature Graphic")
            if old_scr and new_scr != old_scr: changes.append("Скриншоты")

            if changes:
                print(f"    ⚠️ Изменение в {p_id} ({full_geo})")
                current_log.append({"time": get_minsk_time(), "status": f"🔴 Авто: Изменение ({', '.join(changes)})"})
                
                if has_owner:
                    user_stats[c_id]['updated'] += 1
                    
                    is_rollback = any(new_t == past.get('title') and new_s == past.get('summary') for past in history[-3:])
                    msg_prefix = "🔄 АВТО-ОТКАТ" if is_rollback else "🔔 АВТО-ИЗМЕНЕНИЕ!"
                    alert_msg = f"{msg_prefix} [{full_geo.upper()}]\n📦 {p_id}\n\nПоля: {', '.join(changes)}"
                    if is_rollback: alert_msg += "\n\n⚠️ Тексты вернулись к старой версии."
                    
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": alert_msg})
                    
                    if any(k in ["Название", "SD", "FD"] for k in changes):
                        report = f"ОТЧЕТ: {p_id}\n\n--- БЫЛО ---\n{old_t}\n{old_s}\n\n--- СТАЛО ---\n{new_t}\n{new_s}"
                        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", 
                                     data={"chat_id": c_id, "caption": f"📄 Отчет: {p_id}"}, 
                                     files={"document": (f"report_{p_id}.txt", report.encode('utf-8'))})

                        ai_analysis = analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d)
                        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                      data={"chat_id": c_id, "text": f"🤖 *Анализ ИИ:*\n\n{ai_analysis}", "parse_mode": "Markdown"})

                # Обновляем локальный словарь строки (подготовка к записи)
                row['title'], row['summary'], row['description'] = new_t, new_s, new_d
                row['icon'], row['header_image'] = new_icon, new_header
                row['screenshots'] = json.dumps(new_scr, ensure_ascii=False)
                history.append({"title": old_t, "summary": old_s, "description": old_d, "time": get_minsk_time()})
                row['history'] = json.dumps(history[-5:], ensure_ascii=False)
                
            else:
                print(f"    ✅ {p_id}: Ок")
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Без изменений"})
                # Тихое обновление если не было графики
                if (not old_icon or old_icon == 'nan') and new_icon:
                    row['icon'], row['header_image'], row['screenshots'] = new_icon, new_header, json.dumps(new_scr, ensure_ascii=False)

            row['check_log'] = json.dumps(current_log[-5:], ensure_ascii=False)

            # --- ФИНАЛЬНЫЙ ПАКЕТНЫЙ ПУШ СТРОКИ (Write 1/1) ---
            new_row_list = [row.get(h, "") for h in headers]
            # Формируем диапазон A{номер}:Z{номер}
            range_name = f"A{i}:{gspread.utils.rowcol_to_a1(i, len(headers))}"
            worksheet.update(range_name, [new_row_list])
            
            time.sleep(0.6) # Пауза, чтобы Google не ругался на скорость

        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")

    # Резюме пользователям
    for c_id, stats in user_stats.items():
        if stats['updated'] > 0:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                          data={"chat_id": c_id, "text": f"⚙️ Авто-проверка: {stats['checked']} прил., {stats['updated']} изм."})

if __name__ == "__main__":
    check_apps()