import streamlit as st
import json
import pandas as pd
import requests
import google.generativeai as genai
from google_play_scraper import app as gp_app
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import re

st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# --- НАСТРОЙКА ИИ ---
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
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

def analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d):
    if not GEMINI_API_KEY:
        return "❌ Ключ Gemini API не найден в секретах Streamlit."
    
    full_prompt = (
        f"{ASO_PROMPT}\n\n"
        f"--- БЫЛО ---\nTitle: {old_t}\nShort Description: {old_s}\nFull Description: {old_d}\n\n"
        f"--- СТАЛО ---\nTitle: {new_t}\nShort Description: {new_s}\nFull Description: {new_d}"
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
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(full_prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = str(e)
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

def send_telegram_msg(text, chat_id, use_markdown=False):
    token = st.secrets.get("TELEGRAM_TOKEN")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": text}
        if use_markdown:
            data["parse_mode"] = "Markdown"
        try: 
            res = requests.post(url, data=data)
            if use_markdown and res.status_code != 200:
                requests.post(url, data={"chat_id": chat_id, "text": text})
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
                "check_log": c_log
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
                "check_log": json.dumps(info.get('check_log', []), ensure_ascii=False)
            })
        conn.update(worksheet="apps", data=pd.DataFrame(rows))
        return True
    except: return False

def clean_val(val):
    s_val = str(val).strip()
    if s_val.lower() in ['nan', 'none', '#n/a', '']:
        return ""
    if '#error' in s_val.lower():
        return None
    return s_val

def run_check_for_item(key, info, user_reports_dict, single_mode=False):
    updates = 0
    changed = []
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
            
            # ИСПРАВЛЕНИЕ: Всегда фиксируем изменение скринов, если списки не совпадают
            if new_scr != old_scr_list: changed.append("Скриншоты")

        if changed:
            updates = 1
            c_id = info['chat_id']

            is_rollback = False
            for past in info['history']:
                if new_m['title'] == past.get('title') and new_m['summary'] == past.get('summary') and new_m['description'] == past.get('description'):
                    is_rollback = True
                    break

            os_icon = "🍎" if str(info['package_id']).isdigit() else "🤖"
            msg_prefix = "🔄 ОТКАТ (A/B ТЕСТ)" if is_rollback else "⚠️ ИЗМЕНЕНИЕ"
            alert_msg = f"{msg_prefix} {os_icon} [{info['geo'].upper()}]\n📦 {new_m['title']}\nИзменено: {', '.join(changed)}"

            if is_rollback: alert_msg += "\n\n⚠️ Тексты вернулись к одной из прошлых версий."
            
            send_telegram_msg(alert_msg, c_id)

            text_changed = any(k in changed for k in ["Title", "SD", "FD"])
            if text_changed:
                report_content = (
                    f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ (Ручная проверка)\nДата: {get_minsk_time()}\nПриложение: {info['package_id']}\nЛокаль: {info['geo']}\n"
                    f"{'='*30}\n\n--- СТАРОЕ НАЗВАНИЕ ---\n{old_t}\n\n--- НОВОЕ НАЗВАНИЕ ---\n{new_m['title']}\n\n"
                    f"{'-'*30}\n--- СТАРЫЙ SD ---\n{old_s}\n\n--- НОВЫЙ SD ---\n{new_m['summary']}\n\n"
                    f"{'-'*30}\n--- СТАРЫЙ FD ---\n{old_d}\n\n--- НОВЫЙ FD ---\n{new_m['description']}\n"
                )
                
                if single_mode:
                    send_telegram_file(report_content, f"report_{info['package_id']}.txt", f"📄 Детальный отчет: {info['package_id']}", c_id)
                else:
                    user_reports_dict.setdefault(c_id, "--- ASO MANUAL REPORT (FROM SITE) ---\n\n")
                    user_reports_dict[c_id] += report_content

                raw_ai_analysis = analyze_changes_with_ai(old_t, new_m['title'], old_s, new_m['summary'], old_d, new_m['description'])
                clean_ai_analysis = raw_ai_analysis.replace('*', '').replace('_', '').replace('#', '').replace('`', '')
                ai_msg = f"🤖 Анализ ИИ (Сайт):\n\n{clean_ai_analysis}"
                send_telegram_msg(ai_msg, c_id)

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

    return updates, changed

# --- ИНТЕРФЕЙС ---
st.title("🚀 ASO Monitor PRO")
st.caption("Поддерживает Google Play (ID: com.app.name) и App Store (ID: 123456789)")
db = load_data()

if st.button("🔍 Проверить вообще всё", type="primary"):
    with st.spinner("Тотальная проверка стора и анализ ИИ..."):
        updates_count = 0
        user_reports = {} 
        
        for key, info in db.items():
            u, _ = run_check_for_item(key, info, user_reports, single_mode=False)
            updates_count += u
        
        if updates_count > 0:
            for c_id, rep_text in user_reports.items():
                send_telegram_file(rep_text, "global_aso_report.txt", f"📊 Массовая проверка: найдено {updates_count} изменений.", c_id)
            st.success(f"Проверка окончена. Найдено изменений: {updates_count}. Отчеты отправлены!")
        else:
            st.info("Изменений не обнаружено. (Новые визуалы инициализированы, если их не было)")
            
        save_data(db)
        st.rerun()

with st.sidebar:
    st.header("➕ Добавить приложение")
    st.info("Чтобы получать уведомления, сначала напишите боту.")
    st.link_button("➕ Добавить бота", "https://t.me/aso_omg_bot", use_container_width=True)
    st.divider()
    
    new_id = st.text_input("Package ID / App ID", placeholder="com.app.name ИЛИ 835599320").strip()
    
    selected_names = st.multiselect("Выберите локали (можно несколько)", options=list(GP_LOCALES_RAW.values()), default=["English (United States)"])
    new_geos = [k for k, v in GP_LOCALES_RAW.items() if v in selected_names]
    
    if users_dict:
        user_name = st.selectbox("Пользователь", options=["Выбрать..."] + list(users_dict.keys()))
    else:
        st.warning("Пользователи не найдены.")
        user_name = "Выбрать..."

    if st.button("Добавить в мониторинг", type="primary", use_container_width=True):
        if new_id and new_geos and user_name != "Выбрать...":
            selected_chat_id = users_dict[user_name]
            success_added = 0
            
            with st.spinner(f"Загрузка локалей ({len(new_geos)} шт.)..."):
                for geo in new_geos:
                    u_key = f"{new_id}_{geo}_{selected_chat_id}"
                    if u_key in db: 
                        st.warning(f"[{geo}] Уже отслеживается!")
                    else:
                        try:
                            res = fetch_app_data(new_id, geo)
                            db[u_key] = {
                                "package_id": new_id, "geo": geo, "chat_id": str(selected_chat_id),
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
            st.warning("Заполните ID, выберите локали и пользователя!")

android_apps = {}
ios_apps = {}

for key, info in db.items():
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
        st.info("В этой категории пока нет отслеживаемых приложений.")
        return
        
    for (pkg_id, chat_id), keys in app_groups.items():
        owner_name = next((name for name, cid in users_dict.items() if str(cid) == str(chat_id)), "Неизвестно")
        first_info = db[keys[0]]
        main_title = first_info['current']['title']
        main_icon = first_info['current'].get('icon')

        with st.expander(f"{os_icon} | {main_title} ({pkg_id}) | 👤 {owner_name} | 🌍 Локалей: {len(keys)}"):
            col_img, col_space, col_btn = st.columns([1, 2, 4])
            
            with col_img:
                if main_icon and main_icon != 'nan': st.image(main_icon, width=80)
                
            with col_btn:
                if st.button(f"🔍 Проверить все локали ({len(keys)} шт.)", key=f"ch_grp_{pkg_id}_{chat_id}"):
                    with st.spinner("Сверка всей группы со стором..."):
                        user_reports = {}
                        upd = 0
                        for k in keys:
                            u, _ = run_check_for_item(k, db[k], user_reports, single_mode=False)
                            upd += u
                        if upd > 0:
                            for c_id, rep_text in user_reports.items():
                                send_telegram_file(rep_text, f"group_report_{pkg_id}.txt", f"📊 Проверка {pkg_id}: найдено {upd} изм.", c_id)
                            st.success(f"Обновлено локалей: {upd}. Отчеты отправлены.")
                        else:
                            st.info("Группа проверена. Без изменений.")
                        save_data(db)
                        st.rerun()

            st.markdown("---")
            
            locale_labels = [GP_LOCALES_RAW.get(db[k]['geo'], db[k]['geo']) for k in keys]
            tabs_loc = st.tabs(locale_labels)
            
            for i, k in enumerate(keys):
                info = db[k]
                with tabs_loc[i]:
                    loc_icon = info['current'].get('icon')
                    loc_header = info['current'].get('header_image')
                    loc_scr_count = len(info['current'].get('screenshots', []))

                    col_loc_img, col_info, col_del = st.columns([1.5, 4, 1])
                    
                    with col_loc_img:
                        if loc_icon and loc_icon != 'nan': 
                            st.image(loc_icon, width=80, caption="Локальная Иконка")
                        if loc_header and loc_header != 'nan': 
                            st.image(loc_header, width=150, caption="Локальный Баннер (FG)")
                        if loc_scr_count > 0:
                            st.caption(f"📸 Скриншотов: {loc_scr_count}")

                    with col_info:
                        st.write(f"**Локаль (Код):** `{info['geo']}`")
                        
                        if st.button("Проверить локаль", key=f"ch_sng_{k}"):
                            with st.spinner("Проверка одной локали..."):
                                user_reports = {} 
                                u, c = run_check_for_item(k, info, user_reports, single_mode=True)
                                if u > 0: st.success(f"Обновлено: {', '.join(c)}. Отчет отправлен.")
                                else: st.info("Без изменений.")
                                save_data(db)
                                st.rerun()

                        if info['history']:
                            st.warning("⚠️ Есть старые версии!")
                            rep = f"БЫЛО:\n{info['history'][-1]}\n\nСТАЛО:\n{info['current']}"
                            st.download_button(label="📥 Скачать историю", data=rep, file_name=f"aso_{k}.txt", key=f"dl_{k}")
                        
                        st.markdown("🕒 **История проверок:**")
                        if info.get('check_log'):
                            for log in reversed(info['check_log']):
                                st.text(f"[{log['time']}] {log['status']}")
                    
                    with col_del:
                        if st.button("🗑️ Удалить", key=f"del_{k}"):
                            del db[k]
                            save_data(db)
                            st.rerun()

with tab_android:
    render_app_groups(android_apps, "🤖")

with tab_ios:
    render_app_groups(ios_apps, "🍎")