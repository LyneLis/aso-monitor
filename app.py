import streamlit as st
import json
import pandas as pd
import requests
from google_play_scraper import app
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# Словарь локалей
GP_LOCALES = {
    "": "Начните вводить локаль (напр. Russian или ru-RU)...",
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

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

def fetch_gp_data(pkg_id, locale):
    if "-" in locale:
        l_parts = locale.split("-")
        l_code, c_code = l_parts[0].lower(), l_parts[1].lower()
    else:
        l_code, c_code = locale.lower(), locale.lower()
    if l_code == "iw": l_code = "iw"
    return app(pkg_id, lang=l_code, country=c_code)

def send_telegram_msg(text):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.post(url, data={"chat_id": chat_id, "text": text})
        except: pass

def load_data():
    if not DB_AVAILABLE: return {}
    try:
        df = conn.read(ttl=0)
        if df is None or df.empty: return {}
        data = {}
        for _, row in df.iterrows():
            if pd.isna(row['package_id']) or pd.isna(row['geo']): continue
            p_id, geo = str(row['package_id']).strip(), str(row['geo']).strip()
            u_key = f"{p_id}_{geo}"
            c_log = []
            if 'check_log' in df.columns and not pd.isna(row['check_log']):
                try: c_log = json.loads(str(row['check_log']))
                except: pass
            data[u_key] = {
                "package_id": p_id, "geo": geo,
                "current": {"title": str(row['title']), "summary": str(row['summary']), "description": str(row['description'])},
                "history": json.loads(row['history']) if 'history' in df.columns and isinstance(row['history'], str) else [],
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
                "package_id": info['package_id'], "geo": info['geo'],
                "title": info['current']['title'], "summary": info['current']['summary'], "description": info['current']['description'],
                "history": json.dumps(info['history'], ensure_ascii=False),
                "check_log": json.dumps(info.get('check_log', []), ensure_ascii=False)
            })
        conn.update(data=pd.DataFrame(rows))
        return True
    except: return False

st.title("🚀 ASO Monitor PRO")
db = load_data()

# 🔍 ГЛАВНАЯ КНОПКА ПРОВЕРКИ
if st.button("🔍 Проверить все приложения сейчас"):
    with st.spinner("Сверка со стором..."):
        updates_count = 0
        for key, info in db.items():
            try:
                new_m = fetch_gp_data(info['package_id'], info['geo'])
                log_entry = {"time": get_minsk_time(), "status": "🟢 Без изменений"}
                changed = []
                if new_m['title'] != info['current']['title']: changed.append("Title")
                if new_m['summary'] != info['current']['summary']: changed.append("SD")
                if new_m['description'] != info['current']['description']: changed.append("FD")

                if changed:
                    send_telegram_msg(f"⚠️ ИЗМЕНЕНИЕ [{info['geo'].upper()}]\n{new_m['title']}\nИзменено: {', '.join(changed)}")
                    info['history'].append(info['current'])
                    info['current'] = {"title": new_m['title'], "summary": new_m['summary'], "description": new_m['description']}
                    log_entry["status"] = f"🔴 Изменение: {', '.join(changed)}"
                    updates_count += 1
                info.setdefault('check_log', []).append(log_entry)
                info['check_log'] = info['check_log'][-15:]
            except: pass
        save_data(db)
        st.rerun()

# ➕ БОКОВАЯ ПАНЕЛЬ
with st.sidebar:
    st.header("➕ Добавить приложение")
    new_id = st.text_input("Package ID").strip()
    selected_name = st.selectbox("Локаль Google Play", options=list(GP_LOCALES.values()), index=0)
    new_geo = [k for k, v in GP_LOCALES.items() if v == selected_name][0]

    if st.button("Добавить в мониторинг"):
        if new_id and new_geo != "":
            u_key = f"{new_id}_{new_geo}"
            if u_key in db: st.warning("Уже отслеживается!")
            else:
                with st.spinner(f"Загрузка {new_geo}..."):
                    try:
                        res = fetch_gp_data(new_id, new_geo)
                        db[u_key] = {
                            "package_id": new_id, "geo": new_geo,
                            "current": {"title": res['title'], "summary": res['summary'], "description": res['description']},
                            "history": [], "check_log": [{"time": get_minsk_time(), "status": "🆕 Добавлено"}]
                        }
                        save_data(db)
                        st.rerun()
                    except: st.error("Ошибка: Приложение не найдено.")

# 📦 СПИСОК ПРИЛОЖЕНИЙ
for key, info in db.items():
    col_exp, col_del = st.columns([11, 1])
    with col_exp:
        with st.expander(f"📦 [{info['geo']}] {info['current']['title']}"):
            # ИНДИВИДУАЛЬНАЯ ПРОВЕРКА
            if st.button("Проверить", key=f"ch_{key}"):
                with st.spinner("Проверка..."):
                    try:
                        new_m = fetch_gp_data(info['package_id'], info['geo'])
                        log_entry = {"time": get_minsk_time(), "status": "🟢 Ок"}
                        changed = []
                        if new_m['title'] != info['current']['title']: changed.append("Title")
                        if new_m['summary'] != info['current']['summary']: changed.append("SD")
                        if new_m['description'] != info['current']['description']: changed.append("FD")
                        
                        if changed:
                            send_telegram_msg(f"⚠️ ИЗМЕНЕНИЕ [{info['geo'].upper()}]\n{new_m['title']}\nИзменено: {', '.join(changed)}")
                            info['history'].append(info['current'])
                            info['current'] = {"title": new_m['title'], "summary": new_m['summary'], "description": new_m['description']}
                            log_entry["status"] = f"🔴 Изменение: {', '.join(changed)}"
                            st.success(f"Обновлено: {', '.join(changed)}")
                        else:
                            st.info("Без изменений.")
                        
                        info.setdefault('check_log', []).append(log_entry)
                        info['check_log'] = info['check_log'][-15:]
                        save_data(db)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка связи со стором")

            st.write(f"**ID:** {info['package_id']}")
            st.write(f"**Локаль:** {GP_LOCALES.get(info['geo'], info['geo'])}")
            
            if info['history']:
                st.warning("⚠️ Есть старые версии!")
                rep = f"БЫЛО:\n{info['history'][-1]}\n\nСТАЛО:\n{info['current']}"
                st.download_button(label="📥 Скачать отчет", data=rep, file_name=f"aso_{key}.txt", key=f"dl_{key}")
            
            st.markdown("---")
            st.markdown("🕒 **История проверок (Минск):**")
            if info.get('check_log'):
                for log in reversed(info['check_log']):
                    st.text(f"[{log['time']}] {log['status']}")
            
    with col_del:
        if st.button("🗑️", key=f"del_{key}"):
            del db[key]
            save_data(db)
            st.rerun()