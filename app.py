import st
import os
import subprocess
import sys
import importlib

# 1. Функция для принудительного обновления окружения
def force_install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    importlib.invalidate_caches() # Очистка кэша импортов

# 2. Пытаемся импортировать библиотеку
try:
    from st_gsheets_connection import GSheetsConnection
except ImportError:
    force_install("st-gsheets-connection")
    # Пробуем импортировать снова после установки
    from st_gsheets_connection import GSheetsConnection

import streamlit as st
import json
import pandas as pd
from google_play_scraper import app
from datetime import datetime

# --- НАСТРОЙКА СТРАНИЦЫ ---
st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# Подключение к Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    DB_AVAILABLE = True
except Exception as e:
    st.error(f"Ошибка подключения к базе: {e}")
    DB_AVAILABLE = False

# --- ФУНКЦИИ ДАННЫХ ---

def load_data():
    if not DB_AVAILABLE: return {}
    try:
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
    except: return {}

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
        conn.update(data=pd.DataFrame(rows))
        st.toast("✅ Данные сохранены!")
    except Exception as e:
        st.error(f"Ошибка сохранения: {e}")

# --- ИНТЕРФЕЙС ---
st.title("🚀 ASO Monitor 24/7")

db = load_data()

with st.sidebar:
    st.header("Добавить приложение")
    new_id = st.text_input("Package ID")
    new_geo = st.text_input("ГЕО", value="us")
    if st.button("Добавить"):
        if new_id:
            try:
                res = app(new_id, lang='en', country=new_geo)
                meta = {"title": res['title'], "summary": res['summary'], "description": res['description']}
                db[new_id] = {"geo": new_geo, "current": meta, "history": []}
                save_data(db)
                st.success(f"Приложение {res['title']} добавлено!")
                st.rerun()
            except: st.error("Не найдено")

if not db:
    st.info("Добавьте первое приложение для мониторинга.")
else:
    for pkg_id, info in db.items():
        with st.expander(f"📦 {info['current']['title']} ({pkg_id})"):
            if st.button("Проверить обновления", key=pkg_id):
                new_m = app(pkg_id, lang='en', country=info['geo'])
                if new_m['title'] != info['current']['title'] or new_m['summary'] != info['current']['summary']:
                    info['history'].append(info['current'])
                    info['current'] = {"title": new_m['title'], "summary": new_m['summary'], "description": new_m['description']}
                    save_data(db)
                    st.balloons()
                    st.rerun()
                else: st.info("Изменений нет")