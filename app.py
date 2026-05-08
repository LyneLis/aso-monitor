import streamlit as st
import os
import subprocess
import sys
import json
import pandas as pd
from google_play_scraper import app
from datetime import datetime

# 1. Хак для принудительной установки (если облако проигнорировало requirements.txt)
try:
    from st_gsheets_connection import GSheetsConnection
except ImportError:
    # Если библиотеки нет, пробуем установить её прямо сейчас
    subprocess.check_call([sys.executable, "-m", "pip", "install", "st-gsheets-connection"])
    from st_gsheets_connection import GSheetsConnection

# 2. Настройка страницы
st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# 3. Подключение к Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    DB_AVAILABLE = True
except Exception as e:
    st.error(f"Ошибка подключения к Google Sheets: {e}")
    st.info("Проверьте настройки Secrets в панели Streamlit Cloud.")
    DB_AVAILABLE = False

# --- ЛОГИКА ДАННЫХ ---

def load_data():
    if not DB_AVAILABLE: return {}
    try:
        # Читаем таблицу (ttl=0 чтобы данные всегда были актуальны)
        df = conn.read(ttl=0)
        if df is None or df.empty: return {}
        
        data = {}
        for _, row in df.iterrows():
            if pd.isna(row['package_id']): continue
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
    if not DB_AVAILABLE: return
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
        st.toast("✅ Данные сохранены в облако!")
    except Exception as e:
        st.error(f"Ошибка при сохранении: {e}")

# --- ИНТЕРФЕЙС ---

st.title("🚀 ASO Monitor 24/7")

db = load_data()

with st.sidebar:
    st.header("Добавить приложение")
    new_id = st.text_input("Package ID (напр. com.whatsapp)")
    new_geo = st.text_input("ГЕО (us, ru, de)", value="us")
    if st.button("Добавить в мониторинг"):
        if new_id:
            try:
                res = app(new_id, lang='en', country=new_geo)
                meta = {"title": res['title'], "summary": res['summary'], "description": res['description']}
                db[new_id] = {"geo": new_geo, "current": meta, "history": []}
                save_data(db)
                st.success(f"Приложение {res['title']} добавлено!")
                st.rerun()
            except:
                st.error("Приложение не найдено в Google Play.")

# Вывод списка приложений
if not db:
    st.info("Список пуст. Добавьте приложение в боковой панели 👈")
else:
    for pkg_id, info in db.items():
        with st.expander(f"📦 {info['current']['title']} ({pkg_id})"):
            if st.button("Проверить обновления", key=pkg_id):
                with st.spinner("Сверка со стором..."):
                    try:
                        new_m = app(pkg_id, lang='en', country=info['geo'])
                        if (new_m['title'] != info['current']['title'] or 
                            new_m['summary'] != info['current']['summary']):
                            
                            info['history'].append(info['current'])
                            info['current'] = {
                                "title": new_m['title'], 
                                "summary": new_m['summary'], 
                                "description": new_m['description']
                            }
                            save_data(db)
                            st.balloons()
                            st.rerun()
                        else:
                            st.info("Изменений не найдено.")
                    except:
                        st.error("Ошибка связи с Google Play.")
            
            if info['history']:
                st.warning("Внимание! Обнаружены изменения метаданных.")
                st.download_button(
                    label="📥 Скачать отчет для ИИ",
                    data=f"ОТЧЕТ ДЛЯ {pkg_id}\n\nБЫЛО:\n{info['history'][-1]}\n\nСТАЛО:\n{info['current']}",
                    file_name=f"report_{pkg_id}.txt"
                )