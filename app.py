import streamlit as st
import json
import pandas as pd
from google_play_scraper import app
from datetime import datetime
from st_gsheets_connection import GSheetsConnection

# 1. Настройка страницы
st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

# 2. Инициализация подключения к Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---

def load_data():
    """Загружает данные из Google Таблицы и превращает в словарь."""
    try:
        # Читаем данные (ttl=0 чтобы не кэшировало старое)
        df = conn.read(ttl=0)
        
        if df is None or df.empty:
            return {}
        
        data = {}
        for _, row in df.iterrows():
            # Проверка на наличие пустых строк
            if pd.isna(row['package_id']):
                continue
                
            data[str(row['package_id'])] = {
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
        # Если таблицы еще нет или она пустая, возвращаем пустой словарь
        return {}

def save_data(data):
    """Превращает словарь в таблицу и записывает в Google Sheets."""
    try:
        if not data:
            return
            
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
        
        df = pd.DataFrame(rows)
        # Запись в таблицу (перезаписывает всё содержимое текущим состоянием)
        conn.update(data=df)
        st.toast("✅ База данных в облаке обновлена!")
    except Exception as e:
        st.error(f"Ошибка сохранения: {e}")
        st.info("Проверьте, что доступ к таблице открыт для 'Anyone with the link' в режиме 'Editor'")

def fetch_meta(package_id, lang, country):
    """Парсит данные приложения из Google Play."""
    try:
        result = app(package_id, lang=lang, country=country)
        return {
            "title": result['title'],
            "summary": result['summary'],
            "description": result['description']
        }
    except Exception as e:
        st.error(f"Не удалось найти приложение {package_id}: {e}")
        return None

# --- ИНТЕРФЕЙС ПРИЛОЖЕНИЯ ---

st.title("🚀 ASO Monitor: Cloud Edition")
st.markdown("Данные хранятся в Google Таблицах и не пропадают при перезагрузке.")

# Загружаем базу
db = load_data()

# --- БОКОВАЯ ПАНЕЛЬ (ДОБАВЛЕНИЕ) ---
with st.sidebar:
    st.header("➕ Добавить приложение")
    new_id = st.text_input("Package ID (например, com.whatsapp)", key="add_id")
    new_geo = st.text_input("ГЕО (us, ru, de)", value="us", key="add_geo")
    
    if st.button("Добавить в мониторинг"):
        if new_id:
            with st.spinner("Загружаю данные из Google Play..."):
                meta = fetch_meta(new_id, 'en', new_geo)
                if meta:
                    db[new_id] = {"geo": new_geo, "current": meta, "history": []}
                    save_data(db)
                    st.success("Приложение добавлено!")
                    st.rerun()

# --- ОСНОВНАЯ ЧАСТЬ (СПИСОК) ---
if not db:
    st.warning("Ваш список мониторинга пуст. Добавьте первое приложение в боковой панели 👈")
else:
    for pkg_id, info in db.items():
        with st.expander(f"📦 {info['current']['title']} ({pkg_id})"):
            col1, col2 = st.columns([1, 3])
            
            # Кнопка проверки обновлений
            if col1.button("Проверить обновления", key=f"btn_{pkg_id}"):
                with st.spinner("Сверяю данные..."):
                    new_meta = fetch_meta(pkg_id, 'en', info['geo'])
                    
                    if new_meta:
                        # Сравниваем старое и новое
                        if (new_meta['title'] != info['current']['title'] or 
                            new_meta['summary'] != info['current']['summary'] or 
                            new_meta['description'] != info['current']['description']):
                            
                            # Добавляем старое в историю и обновляем текущее
                            info['history'].append(info['current'])
                            info['current'] = new_meta
                            save_data(db)
                            st.balloons()
                            st.rerun()
                        else:
                            st.info("Изменений не обнаружено.")

            # Отображение изменений, если они есть в истории
            if info['history']:
                st.subheader("⚠️ Найдено изменение метаданных!")
                last = info['history'][-1]
                
                if last['title'] != info['current']['title']:
                    st.warning(f"**Изменен Title:**")
                    st.write(f"Было: {last['title']}")
                    st.write(f"Стало: {info['current']['title']}")
                
                if last['summary'] != info['current']['summary']:
                    st.warning(f"**Изменен Short Description:**")
                    st.write(f"Было: {last['summary']}")
                    st.write(f"Стало: {info['current']['summary']}")
                
                # Кнопка для ИИ
                full_report = (
                    f"ОТЧЕТ ОБ ИЗМЕНЕНИИ МЕТАДАННЫХ\n"
                    f"Приложение: {pkg_id}\n"
                    f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"БЫЛО:\n{json.dumps(last, ensure_ascii=False, indent=2)}\n\n"
                    f"СТАЛО:\n{json.dumps(info['current'], ensure_ascii=False, indent=2)}"
                )
                st.download_button(
                    label="📥 Скачать отчет для ИИ",
                    data=full_report,
                    file_name=f"aso_report_{pkg_id}.txt",
                    mime="text/plain"
                )
            else:
                st.write("Версия в Google Play совпадает с версией в вашей базе.")