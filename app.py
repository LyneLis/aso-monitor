import streamlit as st
import json
import pandas as pd
from google_play_scraper import app
from datetime import datetime

# Настройка страницы
st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# Пробуем подключиться к Google Sheets встроенным методом Streamlit
try:
    from st_gsheets_connection import GSheetsConnection
    conn = st.connection("gsheets", type=GSheetsConnection)
    DB_TYPE = "cloud"
except Exception as e:
    st.error(f"Ошибка подключения к облачной базе: {e}")
    st.info("Работаю в локальном режиме. Данные не будут сохраняться после перезагрузки.")
    DB_TYPE = "local"

# --- ЛОГИКА ДАННЫХ ---

def load_data():
    if DB_TYPE == "cloud":
        try:
            df = conn.read(ttl=0)
            if df is None or df.empty: return {}
            data = {}
            for _, row in df.iterrows():
                if pd.isna(row['package_id']): continue
                data[str(row['package_id'])] = {
                    "geo": str(row['geo']),
                    "current": {"title": str(row['title']), "summary": str(row['summary']), "description": str(row['description'])},
                    "history": json.loads(row['history']) if isinstance(row['history'], str) else []
                }
            return data
        except: return {}
    return st.session_state.get('local_db', {})

def save_data(data):
    if DB_TYPE == "cloud":
        try:
            rows = []
            for pkg_id, info in data.items():
                rows.append({
                    "package_id": pkg_id, "geo": info['geo'], "title": info['current']['title'],
                    "summary": info['current']['summary'], "description": info['current']['description'],
                    "history": json.dumps(info['history'], ensure_ascii=False)
                })
            conn.update(data=pd.DataFrame(rows))
            st.toast("✅ Сохранено в Google Sheets")
        except Exception as e:
            st.error(f"Ошибка записи в таблицу: {e}")
    else:
        st.session_state['local_db'] = data

# --- ИНТЕРФЕЙС ---

st.title("🚀 ASO Monitor")

db = load_data()

with st.sidebar:
    st.header("Добавить приложение")
    new_id = st.text_input("Package ID")
    new_geo = st.text_input("ГЕО", value="us")
    if st.button("Добавить"):
        try:
            res = app(new_id, lang='en', country=new_geo)
            meta = {"title": res['title'], "summary": res['summary'], "description": res['description']}
            db[new_id] = {"geo": new_geo, "current": meta, "history": []}
            save_data(db)
            st.rerun()
        except: st.error("Приложение не найдено")

for pkg_id, info in db.items():
    with st.expander(f"📦 {info['current']['title']}"):
        if st.button("Проверить обновления", key=pkg_id):
            try:
                new_m = app(pkg_id, lang='en', country=info['geo'])
                if new_m['title'] != info['current']['title'] or new_m['summary'] != info['current']['summary']:
                    info['history'].append(info['current'])
                    info['current'] = {"title": new_m['title'], "summary": new_m['summary'], "description": new_m['description']}
                    save_data(db)
                    st.balloons()
                    st.rerun()
                else: st.info("Изменений нет")
            except: st.error("Ошибка связи со стором")
        
        if info['history']:
            st.warning("Метаданные изменились!")
            st.download_button("Скачать отчет для ИИ", str(info), file_name="report.txt")