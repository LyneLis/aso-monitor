import gspread
from google_play_scraper import app as gp_app
import os
import json
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import time
import re

# Настройки окружения
TOKEN = os.environ.get("TELEGRAM_TOKEN")
service_account_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1jHKbRYt0hJg29RWLIXZ2fL3et_hgzvkhCSxVtTjKV9g/edit"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY, transport='rest')

ASO_PROMPT = """
Ты — ведущий ASO-стратег и эксперт по мобильному маркетингу с глубокой экспертизой в анализе данных. Твоя специализация — реверс-инжиниринг стратегий конкурентов.
Тебе будут предоставлены данные "До" и "После". Проведи анализ изменений и выяви стратегию роста.
Output Format:
- Summary: краткий вывод.
- Keywords Migration: что удалено/добавлено.
- Strategic Shift: описание.
- Threat Level: High/Medium/Low.
- Action Plan: 3 шага.
"""

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

def analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d):
    if not GEMINI_API_KEY: return "❌ Ключ Gemini API не найден."
    
    full_prompt = (
        f"{ASO_PROMPT}\n\n"
        f"--- БЫЛО ---\nTitle: {old_t}\nShort/Subtitle: {old_s}\nFull Description: {old_d}\n\n"
        f"--- СТАЛО ---\nTitle: {new_t}\nShort/Subtitle: {new_s}\nFull Description: {new_d}"
    )

    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name.replace('models/', ''))
    except Exception as e:
        print(f"⚠️ Не удалось получить список моделей: {e}")

    priority_list = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']

    models_to_try = [m for m in priority_list if m in available_models]
    if not models_to_try:
        models_to_try = available_models[:2] if available_models else priority_list

    last_error = ""
    for model_name in models_to_try:
        try:
            print(f"🤖 Пробую модель: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(full_prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = str(e)
            continue
            
    return f"❌ Ошибка ИИ-анализа: {last_error}"

def clean_val(val):
    s_val = str(val).strip()
    if s_val.lower() in ['nan', '', 'none', '#n/a'] or '#error' in s_val.lower():
        return None
    return s_val

def send_visual_diff(chat_id, token, old_url, new_url, name, p_id, geo):
    if not old_url or not new_url or old_url.lower() == 'nan' or new_url.lower() == 'nan': 
        return
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    media = [
        {"type": "photo", "media": old_url, "parse_mode": "HTML", "caption": f"🔴 <b>БЫЛО</b> | {name}\n📦 {p_id} [{geo}]"},
        {"type": "photo", "media": new_url, "parse_mode": "HTML", "caption": f"🟢 <b>СТАЛО</b> | {name}\n📦 {p_id} [{geo}]"}
    ]
    try:
        requests.post(url, json={"chat_id": chat_id, "media": media})
    except Exception as e:
        print(f"⚠️ Ошибка отправки медиа-группы: {e}")

def fetch_app_data(pkg_id, locale):
    if locale == "es-419":
        l_code, c_code = "es-419", "MX" 
    elif "-" in locale:
        l_code = locale 
        c_code = locale.split("-")[1].upper() 
    else:
        l_code, c_code = locale.lower(), locale.upper()
        
    if l_code == "iw": l_code = "iw"

    if str(pkg_id).isdigit():
        apple_lang = locale.replace('-', '_').lower()
        url = f"https://itunes.apple.com/lookup?id={pkg_id}&country={c_code}&lang={apple_lang}"
        
        res = requests.get(url).json()
        
        if res['resultCount'] == 0:
            url_fallback = f"https://itunes.apple.com/lookup?id={pkg_id}&country={c_code}"
            res = requests.get(url_fallback).json()
            if res['resultCount'] == 0:
                raise Exception(f"Приложение {pkg_id} не найдено в App Store ({c_code})")
        
        data = res['results'][0]
        
        subtitle = data.get('subtitle', '')
        if not subtitle:
            try:
                app_url = data.get('trackViewUrl', f"https://apps.apple.com/{c_code.lower()}/app/id{pkg_id}")
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                    "Accept-Language": f"{locale},en-US;q=0.9,en;q=0.8"
                }
                html = requests.get(app_url, headers=headers, timeout=5).text
                match = re.search(r'app-header__subtitle[^>]*>([^<]+)<', html)
                if match:
                    subtitle = match.group(1).strip()
            except Exception as e:
                print(f"⚠️ Не удалось стянуть Subtitle для {pkg_id}: {e}")

        # СТРОГО IPHONE СКРИНШОТЫ
        screens = data.get('screenshotUrls', [])
        icon_url = data.get('artworkUrl512', data.get('artworkUrl100', ''))

        return {
            'title': data.get('trackName', ''),
            'summary': subtitle, 
            'description': data.get('description', ''),
            'icon': icon_url, 
            'headerImage': '',
            'screenshots': screens
        }
    else:
        return gp_app(pkg_id, lang=l_code, country=c_code)

def check_apps():
    print(f"--- СТАРТ ПРОВЕРКИ v3.12 ({get_minsk_time()}) ---")
    try:
        gc = gspread.service_account_from_dict(service_account_info)
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.get_worksheet(0) 
        headers = worksheet.row_values(1)
        all_rows = worksheet.get_all_values() 
        col_map = {name: i for i, name in enumerate(headers)}
    except Exception as e:
        print(f"❌ Ошибка API Таблиц: {e}"); return

    user_stats = {}

    for i, row_values in enumerate(all_rows[1:], start=2):
        row = {headers[j]: (row_values[j] if j < len(row_values) else "") for j in range(len(headers))}
        
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        c_id = str(row.get('chat_id', '')).strip()
        has_owner = bool(c_id and c_id.lower() != 'nan')

        if has_owner:
            user_stats.setdefault(c_id, {'checked': 0, 'updated': 0})
            user_stats[c_id]['checked'] += 1

        full_geo = str(row.get('geo', 'us')).strip()

        try:
            res = fetch_app_data(p_id, full_geo)
            
            old_t = clean_val(row.get('title'))
            old_s = clean_val(row.get('summary'))
            old_d = clean_val(row.get('description'))
            old_icon = clean_val(row.get('icon'))
            old_header = clean_val(row.get('header_image'))

            try: old_scr = json.loads(str(row.get('screenshots', '[]')))
            except: old_scr = []
            try: history = json.loads(str(row.get('history', '[]')))
            except: history = []
            try: current_log = json.loads(str(row.get('check_log', '[]')))
            except: current_log = []

            new_t, new_s, new_d = str(res['title']).strip(), str(res['summary']).strip(), str(res['description']).strip()
            new_icon, new_header, new_scr = str(res['icon']).strip(), str(res.get('headerImage', '')).strip(), res['screenshots']

            is_table_error = (old_t is None or old_s is None or old_d is None)
            is_ios = str(p_id).isdigit()

            changes = []
            if not is_table_error:
                if new_t != old_t: changes.append("Название")
                if new_s != old_s: changes.append("Subtitle" if is_ios else "SD")
                if new_d != old_d: changes.append("Описание" if is_ios else "FD")
                
                if old_icon and new_icon != old_icon: changes.append("Иконка")
                if old_header and new_header != old_header: changes.append("Feature Graphic")
                if old_scr and new_scr != old_scr: changes.append("Скриншоты")

            if changes:
                print(f"    ⚠️ Изменение в {p_id} ({full_geo})")
                current_log.append({"time": get_minsk_time(), "status": f"🔴 Авто: Изменение ({', '.join(changes)})"})
                
                if has_owner:
                    user_stats[c_id]['updated'] += 1
                    is_rollback = any(new_t == past.get('title') and new_s == past.get('summary') for past in history[-3:])
                    
                    os_icon = "🍎" if is_ios else "🤖"
                    msg_prefix = "🔄 АВТО-ОТКАТ" if is_rollback else "🔔 АВТО-ИЗМЕНЕНИЕ!"
                    alert_msg = f"{msg_prefix} {os_icon} [{full_geo.upper()}]\n📦 {p_id}\n\nПоля: {', '.join(changes)}"
                    
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": alert_msg})
                    
                    if "Иконка" in changes:
                        send_visual_diff(c_id, TOKEN, old_icon, new_icon, "Иконка", p_id, full_geo.upper())

                    if "Feature Graphic" in changes:
                        send_visual_diff(c_id, TOKEN, old_header, new_header, "Feature Graphic", p_id, full_geo.upper())
                    
                    if "Скриншоты" in changes and new_scr:
                        media = []
                        for idx, scr_url in enumerate(new_scr[:10]):
                            caption = f"📱 <b>ОБНОВЛЕННЫЕ СКРИНШОТЫ</b> {os_icon}\n📦 {p_id} [{full_geo.upper()}]" if idx == 0 else ""
                            media.append({"type": "photo", "media": scr_url, "parse_mode": "HTML", "caption": caption})
                        if media:
                            try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMediaGroup", json={"chat_id": c_id, "media": media})
                            except: pass
                    
                    if any(k in ["Название", "SD", "Subtitle", "FD", "Описание"] for k in changes):
                        report = (
                            f"ОТЧЕТ: {p_id}\n\n"
                            f"--- БЫЛО ---\n{old_t}\n{old_s}\n\n"
                            f"--- СТАЛО ---\n{new_t}\n{new_s}"
                        )
                        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", 
                                     data={"chat_id": c_id, "caption": f"📄 Отчет: {p_id}"}, 
                                     files={"document": (f"report_{p_id}.txt", report.encode('utf-8'))})

                        raw_ai_analysis = analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d)
                        clean_ai_analysis = raw_ai_analysis.replace('*', '').replace('_', '').replace('#', '').replace('`', '')
                        ai_msg = f"🤖 Анализ ИИ:\n\n{clean_ai_analysis}"
                        
                        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                      data={"chat_id": c_id, "text": ai_msg})

                row['title'], row['summary'], row['description'] = new_t, new_s, new_d
                row['icon'], row['header_image'] = new_icon, new_header
                row['screenshots'] = json.dumps(new_scr, ensure_ascii=False)
                history.append({"title": old_t, "summary": old_s, "description": old_d, "time": get_minsk_time()})
                row['history'] = json.dumps(history[-5:], ensure_ascii=False)
                
            elif is_table_error:
                print(f"    🛠 Восстановление данных из-за ошибки в таблице для {p_id}")
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Исправление ошибки"})
                row['title'], row['summary'], row['description'] = new_t, new_s, new_d
                row['icon'], row['header_image'], row['screenshots'] = new_icon, new_header, json.dumps(new_scr, ensure_ascii=False)

            else:
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Без изменений"})
                if not old_icon and new_icon:
                    row['icon'], row['header_image'], row['screenshots'] = new_icon, new_header, json.dumps(new_scr, ensure_ascii=False)

            row['check_log'] = json.dumps(current_log[-5:], ensure_ascii=False)

            new_row_list = [row.get(h, "") for h in headers]
            range_name = f"A{i}:{gspread.utils.rowcol_to_a1(i, len(headers))}"
            worksheet.update(range_name, [new_row_list])
            time.sleep(0.6)

        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")

    for c_id, stats in user_stats.items():
        if stats['updated'] > 0:
            report = (f"⚙️ Системный авто-отчет\n⏰ {get_minsk_time()}\n"
                      f"📦 Проверено: {stats['checked']}\n⚠️ Обновлено: {stats['updated']}")
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()