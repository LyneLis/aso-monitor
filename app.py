import streamlit as st
import json
import pandas as pd
from google_play_scraper import app
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# Настройка страницы
st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# Подключение к Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    DB_AVAILABLE = True
except Exception as e:
    st.error(f"Ошибка инициализации подключения: {e}")
    DB_AVAILABLE = False

# --- ФУНКЦИИ ДАННЫХ ---

def load_data():
    if not DB_AVAILABLE:
        return {}
    try:
        df = conn.read(ttl=0)
        if df is None or df.empty:
            return {}
        
        data = {}
        for _, row in df.iterrows():
            if pd.isna(row['package_id']):
                continue
            pkg_id = str(row['package_id'])
            data[pkg_id] = {
                "geo": str(row['geo']),
                "current": {
                    "title": str(row['title']),
                    "summary": str(row['summary']),
                    "description": str(row['description'])
                },
                "history": json.loads(row['history']) if isinstance(row['history'], str) and row['history'] != "" else []
            }
        return data
    except Exception as e:
        return {}

def save_data(data):
    if not DB_AVAILABLE:
        st.error("Ошибка: Подключение к базе данных не установлено.")
        st.stop() # Замораживаем экран
        
    try:
        rows = []
        for pkg_id, info in data.items():
            rows.append({
                "package_id": pkg_id,
                "geo": info['geo'],
                "title": info['current']['title'],
                "summary": info['current']['summary'],
                "description": info['current']['description'],
                "history": json.dumps(info['history'], ensure_ascii=False)
            })
        
        df_to_save = pd.DataFrame(rows)
        conn.update(data=df_to_save)
        st.success("✅ Данные успешно сохранены в Google Sheets!")
        return True
    except Exception as e:
        # ВЫВОДИМ ОШИБКУ И ОСТАНАВЛИВАЕМ САЙТ
        st.error(f"❌ ОШИБКА ЗАПИСИ В ТАБЛИЦУ: {e}")
        st.info("Сайт заморожен. Пожалуйста, скопируй текст ошибки выше и отправь его.")
        st.stop() # Замораживаем экран

# --- ИНТЕРФЕЙС ---

st.title("🚀 ASO Monitor 24/7")

db = load_data()

with st.sidebar:
    st.header("➕ Добавить приложение")
    new_id = st.text_input("Package ID", placeholder="com.openmygame.games...")
    new_geo = st.text_input("ГЕО (страна)", value="us")
    
    if st.button("Добавить в мониторинг"):
        if new_id:
            with st.spinner("Запрос к Google Play..."):
                try:
                    res = app(new_id, lang='en', country=new_geo)
                    meta = {
                        "title": res['title'],
                        "summary": res['summary'],
                        "description": res['description']
                    }
                    current_db = db.copy()
                    current_db[new_id] = {"geo": new_geo, "current": meta, "history": []}
                    
                    if save_data(current_db):
                        st.balloons()
                        st.rerun()
                except Exception as e:
                    # ВЫВОДИМ ОШИБКУ И ОСТАНАВЛИВАЕМ САЙТ
                    st.error(f"❌ ОШИБКА ПАРСИНГА GOOGLE PLAY: {e}")
                    st.info("Сайт заморожен. Скопируй ошибку и пришли мне.")
                    st.stop() # Замораживаем экран
        else:
            st.warning("Введите Package ID!")

if not db:
    st.info("База данных пуста. Добавьте первое приложение слева.")
else:
    st.write(f"В мониторинге приложений: {len(db)}")
    for pkg_id, info in db.items():
        with st.expander(f"📦 {info['current']['title']} ({pkg_id})"):
            if st.button("Проверить обновления", key=f"check_{pkg_id}"):
                st.info("Кнопка проверки пока в режиме ожидания")