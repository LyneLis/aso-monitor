import streamlit as st
import json
import pandas as pd
import requests
import google.generativeai as genai
from google_play_scraper import app as gp_app
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
from bs4 import BeautifulSoup
import re
import time
import codecs

st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# --- НАСТРОЙКА ИИ ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY, transport='rest')

ASO_PROMPT = """
Ты — ведущий ASO-стратег и эксперт по mobile-маркетингу с глубокой экспертизой в анализе данных. Твоя специализация — реверс-инжиниринг стратегий конкурентов.
Тебе будут предоставлены данные "До" и "После". Проведи анализ изменений и выяви стратегию роста.

ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ 

Output Format:
- Summary: краткий вывод.
- Keywords Migration: что удалено/добавлено.
- Strategic Shift: описание.
- Threat Level: High/Medium/Low.
- Action Plan: 3 шага.
"""

CURRENT_ASO_PROMPT = """
Ты — ведущий ASO-стратег и эксперт по mobile-маркетингу.
Тебе будут предоставлены ТЕКУЩИЕ текстовые метаданные приложения (Title, Subtitle/Short Description, Full Description) в одной или нескольких локалях. Никаких прошлых данных нет, это аудит состояния на сегодняшний день.
Твоя задача — провести глубокий реверс-инжиниринг текущей ASO-стратегии конкурента.

ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ.

Output Format:
- 🎯 Summary: краткий вывод о текущем позиционировании.
- 🔑 Core Keywords: на какие ключевые запросы сделан основной упор (по каждой локали).
- 💡 Value Proposition: какие главные фичи или боли пользователя они подсвечивают.
- ⚠️ Weaknesses: возможные слабые места или упущенные возможности в их текстах.
- 🚀 Action Plan: 3 конкретные идеи, как нам адаптировать нашу стратегию, чтобы обойти их в поиске.
"""

def analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d):
    if not GEMINI_API_KEY:
        return "❌ Ключ Gemini API не найден в секретах Streamlit."
    
    full_prompt = (
        f"{ASO_PROMPT}\n\n"
        f"--- БЫЛО ---\nTitle: {old_t}\nShort Description: {old_s}\nFull Description: {old_d}\n\n"
        f"--- СТАЛО ---\nTitle: {new_t}\nShort Description: {new_s}\nFull Description: {new_d}"
    )
    return run_gemini(full_prompt)

def analyze_batched_changes_with_ai(batched_data):
    if not GEMINI_API_KEY: return "❌ Ключ Gemini API не найден."
    
    prompt = ASO_PROMPT + "\n\nВНИМАНИЕ: Конкурент обновил сразу несколько локалей. Проанализируй общую ASO-стратегию этих изменений (какие рынки в фокусе, какие ключевики тестируют):\n"
    
    for loc, data in batched_data.items():
        prompt += f"\n🌍 --- ЛОКАЛЬ: {loc.upper()} ---\n"
        prompt += f"БЫЛО:\nTitle: {data['old_t']}\nShort/Subtitle: {data['old_s']}\nFull Desc: {data['old_d']}\n"
        prompt += f"СТАЛО:\nTitle: {data['new_t']}\nShort/Subtitle: {data['new_s']}\nFull Desc: {data['new_d']}\n"

    return run_gemini(prompt)

def analyze_current_aso_with_ai(batched_data):
    if not GEMINI_API_KEY: return "❌ Ключ Gemini API не найден."
    
    prompt = CURRENT_ASO_PROMPT + "\n\nПроанализируй текущую ASO-стратегию конкурента на основе следующих данных:\n"
    
    for loc, data in batched_data.items():
        prompt += f"\n🌍 --- ЛОКАЛЬ: {loc.upper()} ---\n"
        prompt += f"Title: {data['title']}\nSubtitle/Short Desc: {data['summary']}\nFull Desc: {data['description']}\n"

    return run_gemini(prompt)

def run_gemini(prompt):
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name.replace('models/', ''))
    except:
        pass

    priority_list = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-2.5-pro', 'gemini-1.5-pro', 'gemini-pro']
    models_to_try = [m for m in priority_list if m in available_models]
    if not models_to_try:
        models_to_try = available_models[:2] if available_models else priority_list

    last_error = ""
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            error_str = str(e)
            last_error = error_str
            
            # 🛑 УМНЫЙ ОБХОД ЛИМИТОВ: Если поймали ошибку 429, ждем 35 сек и повторяем
            if "429" in error_str or "Quota" in error_str:
                time.sleep(35) 
                try:
                    response = model.generate_content(prompt)
                    if response and response.text:
                        return response.text
                except Exception as retry_e:
                    last_error = str(retry_e)
                    continue
            else:
                continue 
            
    return f"❌ Ошибка ИИ-анализа: {last_error}"

GP_LOCALES_RAW = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "az-AZ": "Azerbaijani (Azerbaijan)",
    "be": "Belarusian", "bg": "Bulgarian", "bn-BD": "Bengali (Bangladesh)", "ca": "Catalan",
    "cs-CZ": "Czech (Czech Republic)", "da-DK": "Danish (Denmark)", "de-DE": "German (Germany)",
    "el-GR": "Greek (Greece)", "en-AU": "English (Australia)", "en-CA": "English (Canada)",
    "en-GB": "English (United Kingdom)", "en-IN": "English (India)", "en-SG": "English (Singapore)",
    "en-US": "English (United States)", "en-ZA": "English (South Africa)", "es-419": "Spanish (Latin America)",
    "es-ES": "Spanish (Spain)", "es-US": "Spanish (United States)", "et": "Estonian", "fa": "Persian",
    "fi-FI": "Finnish (Finland)", "fil": "Filipino", "fr-CA": "French (Canada)", "fr-FR": "French (France)",
    "gu-IN": "Gujarati (India)", "hi-IN": "Hindi (India)", "hr": "Croatian", "hu-HU": "Hungarian (Hungary)",
    "hy-AM": "Armenian (Armenia)", "id": "Indonesian", "is-IS": "Icelandic (Iceland)", "it-IT": "Italian (Italy)",
    "iw-IL": "Hebrew (Israel)", "ja-JP": "Japanese (Japan)", "ka-GE": "Georgian (Georgia)",
    "kk": "Kazakh", "km-KH": "Khmer (Cambodia)", "kn-IN": "Kannada (India)", "ko-KR": "Korean (South Korea)",
    "ky-KG": "Kyrgyz", "lo-LA": "Lao (Laos)", "lt": "Lithuanian", "lv": "Latvian", "mk-MK": "Macedonian (North Macedonia)",
    "ml-IN": "Malayalam (India)", "mn-MN": "Mongolian (Mongolia)", "mr-IN": "Marathi (India)",
    "ms": "Malay", "ms-MY": "Malay (Malaysia)", "my-MM": "Burmese (Myanmar)", "ne-NP": "Nepali (Nepal)",
    "nl-NL": "Dutch (Netherlands)", "no-NO": "Norwegian (Norway)", "pa-IN": "Punjabi (India)",
    "pl-PL": "Polish (Poland)", "pt-BR": "Portuguese (Brazil)", "pt-PT": "Portuguese (Portugal)",
    "ro": "Romanian", "ru-RU": "Russian (Russia)", "si-LK": "Sinhala (Sri Lanka)", "sk": "Slovak",
    "sl": "Slovenian", "sq": "Albanian", "sr": "Serbian", "sv-SE": "Swedish (Sweden)", "sw": "Swahili",
    "ta-IN": "Tamil (India)", "te-IN": "Telugu (India)", "th-TH": "Thai (Thailand)", "tr-TR": "Turkish (Turkey)",
    "uk": "Ukrainian", "ur-PK": "Urdu (Pakistan)", "uz-UZ": "Uzbek (Uzbekistan)", "vi-VN": "Vietnamese (Vietnam)",
    "zh-CN": "Chinese (Simplified)", "zh-HK": "Chinese (Hong Kong)", "zh-TW": "Chinese (Traditional)", "zu": "Zulu"
}

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    DB_AVAILABLE = True
except Exception as e:
    st.error(f"Ошибка подключения: {e}")
    DB_AVAILABLE = False

def get_users():
    if not DB_AVAILABLE: return {}
    try:
        df = conn.read(worksheet="users", ttl=0)
        return dict(zip(df['name'], df['chat_id']))
    except: return {}

users_dict = get_users()

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

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
        
        if res.get('resultCount', 0) == 0:
            url_fallback = f"https://itunes.apple.com/lookup?id={pkg_id}&country={c_code}"
            res = requests.get(url_fallback, timeout=10).json()
            if res.get('resultCount', 0) == 0:
                raise Exception(f"Приложение {pkg_id} не найдено в App Store ({c_code})")
        
        data = res['results'][0]
        screens = data.get('screenshotUrls', []) or data.get('ipadScreenshotUrls', [])
        icon_url = data.get('artworkUrl512', data.get('artworkUrl100', '')).replace('.webp', '.jpg')
        subtitle = data.get('subtitle', '')
        
        try:
            app_url = f"https://apps.apple.com/{c_code.lower()}/app/id{pkg_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": f"{locale},en-US;q=0.9"
            }
            response = requests.get(app_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                response.encoding = 'utf-8' 
                html_content = response.text
                soup = BeautifulSoup(html_content, 'html.parser')
                
                if not subtitle:
                    p_tag = soup.find('p', class_=re.compile(r'^subtitle'))
                    if p_tag:
                        subtitle = p_tag.get_text(strip=True)
                
                if not subtitle:
                    sub_match = re.search(r'"subtitle"\s*:\s*"((?:[^"\\]|\\.)*)"', html_content)
                    if sub_match:
                        raw_subtitle = sub_match.group(1)
                        try:
                            subtitle = codecs.decode(raw_subtitle, 'unicode_escape')
                        except:
                            subtitle = raw_subtitle

                if subtitle:
                    try:
                        subtitle = subtitle.encode('latin-1').decode('utf-8')
                    except UnicodeEncodeError:
                        pass
                
                if subtitle:
                    subtitle = subtitle.strip('"')
                
                clean_screens = []
                all_imgs = soup.find_all('picture')
                
                for pic in all_imgs:
                    source = pic.find('source', type='image/jpeg') or pic.find('source', type='image/webp')
                    if source and source.has_attr('srcset'):
                        img_url = source['srcset'].split()[0]
                        s_lower = img_url.lower()
                        if any(x in s_lower for x in ['icon', 'logo', 'artwork', 'brand']): continue
                        res_match = re.search(r'/(\d+)x(\d+)', s_lower)
                        if res_match:
                            w, h = int(res_match.group(1)), int(res_match.group(2))
                            if (w == 300 or h == 300) and w != h:
                                s_jpg = img_url.replace('.webp', '.jpg').replace('w.webp', 'bb.jpg').replace('w.png', 'bb.png')
                                if s_jpg not in clean_screens: clean_screens.append(s_jpg)

                if not clean_screens:
                    for pic in all_imgs:
                        source = pic.find('source', type='image/jpeg') or pic.find('source', type='image/webp')
                        if source and source.has_attr('srcset'):
                            img_url = source['srcset'].split()[0]
                            s_lower = img_url.lower()
                            if any(x in s_lower for x in ['icon', 'logo', 'artwork']): continue
                            res_match = re.search(r'/(\d+)x(\d+)', s_lower)
                            if res_match:
                                w, h = int(res_match.group(1)), int(res_match.group(2))
                                if w != h and (w >= 300 or h >= 300):
                                    s_jpg = img_url.replace('.webp', '.jpg').replace('w.webp', 'bb.jpg')
                                    if s_jpg not in clean_screens: clean_screens.append(s_jpg)
                
                if clean_screens:
                    screens = clean_screens

        except Exception as e:
            print(f"⚠️ Ошибка BS4 на сайте: {e}")

        return {
            'title': data.get('trackName', ''),
            'summary': subtitle or '', 
            'description': data.get('description', ''),
            'icon': icon_url or '', 
            'headerImage': '',
            'screenshots': [s.replace('.webp', '.jpg') for s in screens]
        }
    else:
        return gp_app(pkg_id, lang=l_code, country=c_code)

def send_telegram_msg(text, chat_id, use_markdown=False):
    token = st.secrets.get("TELEGRAM_TOKEN")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        limit = 4000
        for i in range(0, len(text), limit):
            chunk = text[i:i+limit]
            data = {"chat_id": chat_id, "text": chunk}
            if use_markdown:
                data["parse_mode"] = "Markdown"
            try: 
                res = requests.post(url, data=data)
                if use_markdown and res.status_code != 200:
                    requests.post(url, data={"chat_id": chat_id, "text": chunk})
            except: pass

def send_telegram_file(file_content, filename, caption, chat_id):
    token = st.secrets.get("TELEGRAM_TOKEN")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        files = {"document": (filename, file_content.encode('utf-8'))}
        try: requests.post(url, data={"chat_id": chat_id, "caption": caption}, files=files)
        except: pass

def load_data():
    if not DB_AVAILABLE: return {}
    try:
        df = conn.read(worksheet="apps", ttl=0)
        if df is None or df.empty: return {}
        data = {}
        for _, row in df.iterrows():
            if pd.isna(row['package_id']) or pd.isna(row['geo']): continue
            p_id, geo = str(row['package_id']).strip(), str(row['geo']).strip()
            c_id = "" if pd.isna(row.get('chat_id')) else str(row['chat_id']).strip()
            
            u_key = f"{p_id}_{geo}_{c_id}" 
            c_log = []
            if 'check_log' in df.columns and not pd.isna(row['check_log']):
                try: c_log = json.loads(str(row['check_log']))
                except: pass
                
            ai_audit = str(row['ai_audit']) if 'ai_audit' in df.columns and not pd.isna(row.get('ai_audit')) else ""
            
            data[u_key] = {
                "package_id": p_id, "geo": geo, "chat_id": c_id,
                "current": {
                    "title": "" if pd.isna(row.get('title')) else str(row.get('title')).strip(), 
                    "summary": "" if pd.isna(row.get('summary')) else str(row.get('summary')).strip(), 
                    "description": "" if pd.isna(row.get('description')) else str(row.get('description')).strip(),
                    "icon": "" if pd.isna(row.get('icon')) else str(row.get('icon')).strip(),
                    "header_image": "" if pd.isna(row.get('header_image')) else str(row.get('header_image')).strip(),
                    "screenshots": json.loads(row['screenshots']) if 'screenshots' in df.columns and not pd.isna(row.get('screenshots')) else []
                },
                "history": json.loads(row['history']) if 'history' in df.columns and not pd.isna(row.get('history')) else [],
                "check_log": c_log,
                "ai_audit": ai_audit
            }
        return data
    except: return {}

def save_data(data):
    if not DB_AVAILABLE: return False
    try:
        rows = []
        for key, info in data.items():
            rows.append({
                "package_id": info['package_id'], "geo": info['geo'], "chat_id": info.get('chat_id', ''),
                "title": info['current']['title'], "summary": info['current']['summary'], "description": info['current']['description'],
                "icon": info['current'].get('icon', ''),
                "header_image": info['current'].get('header_image', ''),
                "screenshots": json.dumps(info['current'].get('screenshots', []), ensure_ascii=False),
                "history": json.dumps(info['history'], ensure_ascii=False),
                "check_log": json.dumps(info.get('check_log', []), ensure_ascii=False),
                "ai_audit": info.get('ai_audit', '')
            })
        conn.update(worksheet="apps", data=pd.DataFrame(rows))
        return True
    except: return False

def clean_val(val):
    s_val = str(val).strip()
    if s_val.lower() in ['nan', 'none', '#n/a', '']: return ""
    if '#error' in s_val.lower(): return None
    return s_val

def run_check_for_item(key, info, user_reports_dict, single_mode=False, skip_ai=False):
    updates = 0
    changed = []
    text_changes_payload = None
    
    try:
        new_m = fetch_app_data(info['package_id'], info['geo'])
        log_entry = {"time": get_minsk_time(), "status": "🟢 Ок"}
        old = info['current']

        new_icon = new_m.get('icon', '')
        new_header = new_m.get('headerImage', '') 
        new_scr = new_m.get('screenshots', [])

        old_t = clean_val(old['title'])
        old_s = clean_val(old['summary'])
        old_d = clean_val(old['description'])
        old_scr_list = old.get('screenshots', [])
        
        is_table_error = (old_t is None or old_s is None or old_d is None)

        if not is_table_error:
            if new_m['title'] != old_t: changed.append("Title")
            if new_m['summary'] != old_s: changed.append("SD")
            if new_m['description'] != old_d: changed.append("FD")

            if old.get('icon') and old.get('icon') != 'nan' and new_icon != old['icon']: changed.append("Иконка")
            if old.get('header_image') and old.get('header_image') != 'nan' and new_header != old.get('header_image'): changed.append("Feature Graphic")
            if new_scr != old_scr_list: changed.append("Скриншоты")

        if changed:
            updates = 1
            c_id = info['chat_id']
            is_rollback = any(new_m['title'] == p.get('title') and new_m['summary'] == p.get('summary') and new_m['description'] == p.get('description') for p in info['history'])

            text_changed = any(k in changed for k in ["Title", "SD", "FD"])
            if text_changed:
                text_changes_payload = {
                    'old_t': old_t, 'new_t': new_m['title'],
                    'old_s': old_s, 'new_s': new_m['summary'],
                    'old_d': old_d, 'new_d': new_m['description']
                }

            if single_mode:
                os_icon = "🍎" if str(info['package_id']).isdigit() else "🤖"
                msg_prefix = "🔄 ОТКАТ (A/B ТЕСТ)" if is_rollback else "⚠️ ИЗМЕНЕНИЕ"
                alert_msg = f"{msg_prefix} {os_icon} [{info['geo'].upper()}]\n📦 {new_m['title']}\nИзменено: {', '.join(changed)}"
                if is_rollback: alert_msg += "\n\n⚠️ Тексты вернулись к одной из прошлых версий."
                send_telegram_msg(alert_msg, c_id)
                
                if text_changed:
                    report_content = (
                        f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ\nПриложение: {info['package_id']}\nЛокаль: {info['geo'].upper()}\nДата: {get_minsk_time()}\n"
                        f"{'='*40}\n\n--- БЫЛО ---\nНазвание: {old_t}\nSD / Subtitle: {old_s}\nFD / Описание:\n{old_d}\n\n"
                        f"{'-'*40}\n\n--- СТАЛО ---\nНазвание: {new_m['title']}\nSD / Subtitle: {new_m['summary']}\nFD / Описание:\n{new_m['description']}\n"
                    )
                    send_telegram_file(report_content, f"report_{info['package_id']}.txt", f"📄 Детальный отчет: {info['package_id']}", c_id)
                    
                    if not skip_ai:
                        raw_ai_analysis = analyze_changes_with_ai(old_t, new_m['title'], old_s, new_m['summary'], old_d, new_m['description'])
                        clean_ai_analysis = raw_ai_analysis.replace('*', '').replace('_', '').replace('#', '').replace('`', '')
                        send_telegram_msg(f"🤖 Анализ ИИ (Сайт):\n\n{clean_ai_analysis}", c_id)

            info['history'].append(info['current'])
            info['current'] = {
                "title": new_m['title'], "summary": new_m['summary'], "description": new_m['description'],
                "icon": new_icon, "header_image": new_header, "screenshots": new_scr
            }
            log_entry["status"] = f"🔴 Изменение ({', '.join(changed)})"
        
        elif is_table_error:
            info['current'] = {
                "title": new_m['title'], "summary": new_m['summary'], "description": new_m['description'],
                "icon": new_icon, "header_image": new_header, "screenshots": new_scr
            }
            log_entry["status"] = "🟢 Исправление ошибки"
        else:
            if (not old.get('icon') or old.get('icon') == 'nan') and new_icon:
                info['current']['icon'] = new_icon
            if (not old.get('header_image') or old.get('header_image') == 'nan') and new_header:
                info['current']['header_image'] = new_header
            if (not old.get('screenshots') or len(old.get('screenshots', [])) == 0) and new_scr:
                info['current']['screenshots'] = new_scr

        info.setdefault('check_log', []).append(log_entry)
        info['check_log'] = info['check_log'][-5:]
    except Exception as e:
        print(f"Ошибка проверки {key}: {e}")
        log_entry = {"time": get_minsk_time(), "status": f"❌ Ошибка"}
        info.setdefault('check_log', []).append(log_entry)
        info['check_log'] = info['check_log'][-5:]

    return updates, changed, text_changes_payload


# --- ИНТЕРФЕЙС ---
st.title("🚀 ASO Monitor PRO")
st.caption("Поддерживает Google Play (ID: com.app.name) и App Store (ID: 123456789)")
db = load_data()

# --- САЙДБАР ---
with st.sidebar:
    st.header("👤 Профиль пользователя")
    if users_dict:
        view_user = st.selectbox("Режим просмотра", options=["Все приложения"] + list(users_dict.keys()))
        view_chat_id = str(users_dict[view_user]).strip() if view_user != "Все приложения" else None
    else:
        st.warning("Пользователи не найдены.")
        view_user = "Все приложения"
        view_chat_id = None

    st.divider()
    st.header("➕ Добавить приложение")
    st.info("Чтобы получать уведомления, сначала напишите боту.")
    st.link_button("➕ Добавить бота", "https://t.me/aso_omg_bot", use_container_width=True)
    
    new_id = st.text_input("Package ID / App ID", placeholder="com.app.name ИЛИ 835599320").strip()
    selected_names = st.multiselect("Выберите локали", options=list(GP_LOCALES_RAW.values()), default=["English (United States)"])
    new_geos = [k for k, v in GP_LOCALES_RAW.items() if v in selected_names]
    
    if users_dict:
        add_for_user = st.selectbox("Добавить для пользователя", options=["Выбрать..."] + list(users_dict.keys()))
    else:
        add_for_user = "Выбрать..."

    if st.button("Добавить в мониторинг", type="primary", use_container_width=True):
        if new_id and new_geos and add_for_user != "Выбрать...":
            selected_chat_id = str(users_dict[add_for_user]).strip()
            
            success_added = 0
            with st.spinner(f"Загрузка локалей..."):
                for geo in new_geos:
                    u_key = f"{new_id}_{geo}_{selected_chat_id}"
                    if u_key in db: 
                        st.warning(f"[{geo}] Уже отслеживается!")
                    else:
                        try:
                            res = fetch_app_data(new_id, geo)
                            db[u_key] = {
                                "package_id": new_id, "geo": geo, "chat_id": selected_chat_id,
                                "current": {
                                    "title": res['title'], "summary": res['summary'], "description": res['description'],
                                    "icon": res.get('icon', ''), "header_image": res.get('headerImage', ''), "screenshots": res.get('screenshots', [])
                                },
                                "history": [], "check_log": [{"time": get_minsk_time(), "status": "🆕 Добавлено"}]
                            }
                            success_added += 1
                        except Exception as e:
                            st.error(f"Ошибка: {geo} не найдено ({e})")
                
            if success_added > 0:
                save_data(db)
                st.success(f"Успешно добавлено локалей: {success_added}")
                st.rerun()
        else:
            st.warning("Заполните ID, локали и пользователя!")

# --- ОСНОВНАЯ ЧАСТЬ ---
if st.button("🔍 Проверить вообще всё", type="primary"):
    with st.spinner("Тотальная проверка обновлений... (Может занять время из-за лимитов ИИ)"):
        updates_count = 0
        batched_alerts = {}
        
        for key, info in db.items():
            old_icon = info['current'].get('icon', '')
            old_header = info['current'].get('header_image', '')
            
            u, changed_list, txt_payload = run_check_for_item(key, info, {}, single_mode=False, skip_ai=True)
            updates_count += u
            
            if u > 0:
                p_id = info['package_id']
                c_id = info['chat_id']
                geo = info['geo']
                is_ios = str(p_id).isdigit()
                b_key = (p_id, c_id, is_ios)
                
                if b_key not in batched_alerts:
                    batched_alerts[b_key] = {'changes': {}, 'texts': {}, 'visuals': []}
                
                batched_alerts[b_key]['changes'][geo] = changed_list
                
                if "Иконка" in changed_list:
                    batched_alerts[b_key]['visuals'].append({'type': 'diff', 'name': 'Иконка', 'old': old_icon, 'new': info['current'].get('icon', ''), 'geo': geo})
                if "Feature Graphic" in changed_list:
                    batched_alerts[b_key]['visuals'].append({'type': 'diff', 'name': 'Feature Graphic', 'old': old_header, 'new': info['current'].get('header_image', ''), 'geo': geo})
                if "Скриншоты" in changed_list:
                    batched_alerts[b_key]['visuals'].append({'type': 'screens', 'screens': info['current'].get('screenshots', []), 'geo': geo})
                
                if txt_payload:
                    batched_alerts[b_key]['texts'][geo] = txt_payload

        # Отправка результатов
        token = st.secrets.get("TELEGRAM_TOKEN")
        for (pkg_id, c_id, is_ios), data in batched_alerts.items():
            os_icon = "🍎" if is_ios else "🤖"
            summary_msg = f"🔔 ИЗМЕНЕНИЯ (Массовая проверка сайта) {os_icon}\n📦 {pkg_id}\n\n"
            for geo, clist in data['changes'].items():
                summary_msg += f"🌍 [{geo.upper()}]: {', '.join(clist)}\n"
            send_telegram_msg(summary_msg, c_id)
            time.sleep(1) 
            
            # Отправка TXT отчетов
            if data['texts']:
                full_report = f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ\nПриложение: {pkg_id}\n\n"
                for geo, txt in data['texts'].items():
                    full_report += f"Локаль: {geo.upper()}\n{'='*40}\n"
                    full_report += f"--- БЫЛО ---\nНазвание: {txt['old_t']}\nSD/Subtitle: {txt['old_s']}\nFD:\n{txt['old_d']}\n\n"
                    full_report += f"--- СТАЛО ---\nНазвание: {txt['new_t']}\nSD/Subtitle: {txt['new_s']}\nFD:\n{txt['new_d']}\n\n"
                send_telegram_file(full_report, f"report_{pkg_id}.txt", f"📄 Отчет: {pkg_id}", c_id)
                time.sleep(1)
            
            # Отправка графики
            for vis in data['visuals']:
                geo = vis['geo'].upper()
                if vis['type'] == 'diff':
                    send_visual_diff(c_id, token, vis['old'], vis['new'], vis['name'], pkg_id, geo)
                    time.sleep(1.5)
                elif vis['type'] == 'screens' and vis['screens']:
                    media = [{"type": "photo", "media": s, "parse_mode": "HTML", "caption": f"📱 Скриншот {pkg_id} [{geo}]" if idx == 0 else ""} for idx, s in enumerate(vis['screens'][:10])]
                    requests.post(f"https://api.telegram.org/bot{token}/sendMediaGroup", json={"chat_id": c_id, "media": media})
                    time.sleep(2)
            
            # ИИ-анализ
            if data['texts']:
                ai_msg = analyze_batched_changes_with_ai(data['texts'])
                if ai_msg and "❌" not in ai_msg:
                    clean_ai = ai_msg.replace('*', '').replace('_', '').replace('#', '').replace('`', '')
                    send_telegram_msg(f"🤖 Пакетный анализ ({pkg_id}):\n\n{clean_ai}", c_id)
                    
                    st.toast(f"⏳ Ожидание 40 секунд для сброса лимитов ИИ ({pkg_id})...")
                    time.sleep(40)
                else:
                    send_telegram_msg(f"⚠️ ИИ вернул ошибку: {ai_msg}", c_id)
        
        save_data(db)
        if updates_count > 0:
            st.success(f"Готово. Изменений: {updates_count}")
        else:
            st.info("Изменений не обнаружено.")
        st.rerun()

# --- ФИЛЬТРАЦИЯ И ГРУППИРОВКА ---
android_apps = {}
ios_apps = {}

for key, info in db.items():
    if view_chat_id and str(info.get('chat_id')).strip() != view_chat_id:
        continue

    grp = (info['package_id'], info['chat_id'])
    if str(info['package_id']).isdigit():
        if grp not in ios_apps: ios_apps[grp] = []
        ios_apps[grp].append(key)
    else:
        if grp not in android_apps: android_apps[grp] = []
        android_apps[grp].append(key)

tab_android, tab_ios = st.tabs(["🤖 Android (Google Play)", "🍎 iOS (App Store)"])

def render_app_groups(app_groups, os_icon):
    if not app_groups:
        st.info("Нет приложений для отображения.")
        return
        
    for (pkg_id, chat_id), keys in app_groups.items():
        owner_name = next((name for name, cid in users_dict.items() if str(cid) == str(chat_id)), "Неизвестно")
        first_info = db[keys[0]]
        main_title = first_info['current']['title']
        main_icon = first_info['current'].get('icon')

        with st.expander(f"{os_icon} | {main_title} ({pkg_id}) | 👤 {owner_name}"):
            col_img, col_space, col_btn = st.columns([1, 2, 4])
            with col_img:
                if main_icon and main_icon != 'nan': st.image(main_icon, width=80)
            
            with col_btn:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"🔍 Проверить локали ({len(keys)})", key=f"ch_grp_{pkg_id}_{chat_id}"):
                        with st.spinner("Сверка..."):
                            upd = 0
                            batched_ai = {}
                            for k in keys:
                                u, _, txt_payload = run_check_for_item(k, db[k], {}, single_mode=False, skip_ai=True)
                                upd += u
                                if txt_payload: batched_ai[db[k]['geo']] = txt_payload
                            if upd > 0 and batched_ai:
                                ai_msg = analyze_batched_changes_with_ai(batched_ai)
                                clean_ai = ai_msg.replace('*', '').replace('_', '').replace('#', '').replace('`', '')
                                send_telegram_msg(f"🤖 Пакетный анализ ({pkg_id}):\n\n{clean_ai}", chat_id)
                        save_data(db)
                        st.rerun()
                
                with col2:
                    saved_audit = first_info.get('ai_audit', '')
                    btn_label = "🔄 Обновить ASO-аудит" if saved_audit else "🧠 Текущий ASO обзор"
                    
                    if st.button(btn_label, key=f"ai_force_{pkg_id}_{chat_id}"):
                        with st.spinner("ИИ анализирует тексты... (может занять около минуты из-за лимитов)"):
                            batched_current = {}
                            for k in keys:
                                inf = db[k]
                                batched_current[inf['geo']] = {
                                    'title': inf['current']['title'],
                                    'summary': inf['current']['summary'],
                                    'description': inf['current']['description']
                                }
                            
                            if batched_current:
                                ai_msg = analyze_current_aso_with_ai(batched_current)
                                if ai_msg and "❌" not in ai_msg:
                                    db[keys[0]]['ai_audit'] = ai_msg
                                    save_data(db)
                                    st.rerun()
                                else:
                                    st.error(f"Ошибка ИИ: {ai_msg}")
                            else:
                                st.error("Нет данных для анализа.")
            
            if first_info.get('ai_audit'):
                with st.expander("📊 Сохраненный ИИ-Аудит (Текущая стратегия)"):
                    st.markdown(first_info['ai_audit'])

            st.markdown("---")
            tabs_loc = st.tabs([GP_LOCALES_RAW.get(db[k]['geo'], db[k]['geo']) for k in keys])
            for i, k in enumerate(keys):
                with tabs_loc[i]:
                    info = db[k]
                    c1, c2, c3 = st.columns([1.5, 4, 1])
                    with c1:
                        if info['current'].get('icon'): st.image(info['current']['icon'], width=70)
                    with c2:
                        st.write(f"**Локаль:** `{info['geo']}`")
                        if st.button("Проверить", key=f"btn_sng_{k}"):
                            run_check_for_item(k, info, {}, single_mode=True)
                            save_data(db)
                            st.rerun()
                    with c3:
                        if st.button("🗑️", key=f"del_{k}"):
                            del db[k]
                            save_data(db)
                            st.rerun()

with tab_android:
    render_app_groups(android_apps, "🤖")

with tab_ios:
    render_app_groups(ios_apps, "🍎")