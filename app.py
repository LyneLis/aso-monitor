import streamlit as st
import json
import os
from google_play_scraper import app
from datetime import datetime

# Настройка страницы
st.set_page_config(page_title="ASO Monitor Pro", layout="wide")

DB_FILE = 'apps_history.json'

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def fetch_meta(package_id, lang, country):
    try:
        result = app(package_id, lang=lang, country=country)
        return {
            "title": result['title'],
            "summary": result['summary'],
            "description": result['description']
        }
    except Exception as e:
        st.error(f"Ошибка парсинга: {e}")
        return None

st.title("🚀 ASO Monitor: Title, SD & FD")

# Боковая панель
with st.sidebar:
    st.header("Добавить конкурента")
    new_id = st.text_input("Package ID", placeholder="com.android.chrome")
    new_geo = st.text_input("ГЕО", value="us")
    if st.button("Добавить"):
        db = load_data()
        meta = fetch_meta(new_id, 'en', new_geo)
        if meta:
            db[new_id] = {"geo": new_geo, "current": meta, "history": []}
            save_data(db)
            st.rerun()

# Основной блок
db = load_data()
for pkg_id, info in db.items():
    with st.expander(f"📦 {info['current']['title']} ({pkg_id})", expanded=True):
        if st.button(f"Проверить обновления", key=pkg_id):
            new_meta = fetch_meta(pkg_id, 'en', info['geo'])
            if new_meta and new_meta != info['current']:
                info['history'].append(info['current'])
                info['current'] = new_meta
                save_data(db)
                st.success("Есть изменения!")
                st.rerun()
            else:
                st.info("Изменений нет")

        if info['history']:
            last = info['history'][-1]
            st.subheader("Что изменилось:")
            if last['title'] != info['current']['title']:
                st.warning(f"Title: {last['title']} -> {info['current']['title']}")
            if last['summary'] != info['current']['summary']:
                st.warning(f"SD: {last['summary']} -> {info['current']['summary']}")
            
            report = f"БЫЛО:\n{last}\n\nСТАЛО:\n{info['current']}"
            st.download_button("📥 Скачать для ИИ", report, file_name="report.txt")