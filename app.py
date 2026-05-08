import streamlit as st
import json
import pandas as pd
from google_play_scraper import app
from datetime import datetime

# ВОТ ОНО! Правильное имя модуля для импорта:
from streamlit_gsheets import GSheetsConnection

# 1. Настройка страницы
st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# 2. Подключение к Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    DB_AVAILABLE = True
except Exception as e:
    st.error(f"Ошибка подключения к базе данных: {e}")
    st.info("Проверьте, что в настройках (Secrets) добавлена ссылка на таблицу.")
    DB_AVAILABLE = False

# --- ФУНКЦИИ ДАННЫХ ---

def load_data():
    if not DB_AVAILABLE:
        return {}
    try:
        # Читаем таблицу (ttl=0 отключает кэширование, чтобы видеть изменения сразу)
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
        return
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
        # Обновляем таблицу полностью
        conn.update(data=df_to_save)
        st.toast("✅ Данные в Google Таблице обновлены!")
    except Exception as e:
        st.error(f"Не удалось сохранить данные: {e}")

# --- ИНТЕРФЕЙС ---

st.title("🚀 ASO Monitor 24/7")
st.write("Мониторинг обновлений в Google Play с хранением истории в облаке.")

db = load_data()

# Добавление новых приложений
with st.sidebar:
    st.header("➕ Добавить приложение")
    new_id = st.text_input("Package ID", placeholder="com.whatsapp")
    new_geo = st.text_input("ГЕО (страна)", value="us")
    
    if st.button("Добавить в базу"):
        if new_id:
            with st.spinner("Загружаю данные из Google Play..."):
                try:
                    res = app(new_id, lang='en', country=new_geo)
                    meta = {
                        "title": res['title'],
                        "summary": res['summary'],
                        "description": res['description']
                    }
                    db[new_id] = {"geo": new_geo, "current": meta, "history": []}
                    save_data(db)
                    st.success(f"Добавлено: {res['title']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Приложение не найдено: {e}")

# Отображение списка
if not db:
    st.info("Ваш список мониторинга пока пуст. Добавьте конкурентов в боковом меню.")
else:
    for pkg_id, info in db.items():
        with st.expander(f"📦 {info['current']['title']} ({pkg_id})"):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                if st.button("Проверить обновления", key=f"btn_{pkg_id}"):
                    with st.spinner("Проверяю Google Play..."):
                        try:
                            new_m = app(pkg_id, lang='en', country=info['geo'])
                            
                            # Сравниваем основные поля
                            if (new_m['title'] != info['current']['title'] or 
                                new_m['summary'] != info['current']['summary']):
                                
                                # Сохраняем старую версию в историю
                                info['history'].append(info['current'])
                                # Обновляем текущую
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
                            st.error("Не удалось связаться с Google Play.")

            with col2:
                st.write(f"**ГЕО мониторинга:** {info['geo']}")

            if info['history']:
                st.warning("⚠️ Зафиксированы изменения!")
                last_ver = info['history'][-1]
                
                # Показываем разницу, если она есть
                if last_ver['title'] != info['current']['title']:
                    st.write(f"**Старый Title:** {last_ver['title']}")
                if last_ver['summary'] != info['current']['summary']:
                    st.write(f"**Старый Short Description:** {last_ver['summary']}")
                
                report_text = f"ASO REPORT for {pkg_id}\n\nOLD:\n{last_ver}\n\nNEW:\n{info['current']}"
                st.download_button(
                    label="📥 Скачать отчет для ИИ",
                    data=report_text,
                    file_name=f"aso_report_{pkg_id}.txt",
                    key=f"dl_{pkg_id}"
                )