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
    if s_val.lower() in ['nan', 'none', '#n/a', '']:
        return ""
    if '#error' in s_val.lower():
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
        res = requests.get(url, timeout=10).json()
        
        if res['resultCount'] == 0:
            url_fallback = f"https://itunes.apple.com/lookup?id={pkg_id}&country={c_code}"
            res = requests.get(url_fallback).json()
            if res['resultCount'] == 0:
                raise Exception(f"Приложение {pkg_id} не найдено в App Store ({c_code})")
        
        data = res['results'][0]
        subtitle = data.get('subtitle', '')
        screens = data.get('screenshotUrls', [])
        
        if not subtitle or not screens:
            try:
                app_url = f"https://apps.apple.com/{c_code.lower()}/app/id{pkg_id}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
                    "Accept-Language": f"{locale},en-US;q=0.9,en;q=0.8"
                }
                html = requests.get(app_url, headers=headers, timeout=10).text
                
                if not subtitle:
                    match = re.search(r'<h2[^>]*class="[^"]*subtitle[^"]*"[^>]*>(.*?)</h2>', html, re.IGNORECASE | re.DOTALL)
                    if match:
                        subtitle = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                
                if not screens:
                    # Ищем ТОЛЬКО jpeg/png для Телеграма
                    scr_matches = re.findall(r'<source[^>]*srcset="([^"\s]+)[^"]*"[^>]*type="image/jpeg"', html)
                    if not scr_matches:
                        scr_matches = re.findall(r'<img[^>]*class="[^"]*we-artwork__image[^"]*"[^>]*src="([^"]+)"', html)
                    
                    clean_screens = []
                    for s in scr_matches:
                        if s not in clean_screens:
                            clean_screens.append(s)
                    if clean_screens:
                        screens = clean_screens
                        
            except Exception as e:
                print(f"⚠️ Ошибка HTML-парсера для {pkg_id}: {e}")

        icon_url = data.get('artworkUrl512', data.get('artworkUrl100', ''))

        return {
            'title': data.get('trackName', ''),
            'summary': subtitle or '', 
            'description': data.get('description', ''),
            'icon': icon_url or '', 
            'headerImage': '',
            'screenshots': screens or []
        }
    else:
        return gp_app(pkg_id, lang=l_code, country=c_code)

def check_apps():
    print(f"--- СТАРТ ПРОВЕРКИ v3.13 ({get_minsk_time()}) ---")
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
            is_ios = str