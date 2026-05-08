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
        return False
        
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
        st.toast("✅ Данные успешно сохранены в Google Sheets!")
        return True
    except Exception as e:
        st.error(f"❌ ОШИБКА ЗАПИСИ В ТАБЛИЦУ: {e}")
        return False

# --- ИНТЕРФЕЙС ---

st.title("🚀 ASO Monitor 24/7")

db = load_data()

with st.sidebar:
    st.header("➕ Добавить приложение")
    new_id = st.text_input("Package ID", placeholder="com.whatsapp")
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
                    st.error(f"Ошибка при добавлении: {e}")
        else:
            st.warning("Введите Package ID!")

if not db:
    st.info("База данных пуста. Добавьте первое приложение слева.")
else:
    st.write(f"В мониторинге приложений: {len(db)}")
    for pkg_id, info in db.items():
        with st.expander(f"📦 {info['current']['title']} ({pkg_id})"):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # ВОТ ОНА — РАБОЧАЯ КНОПКА ПРОВЕРКИ
                if st.button("Проверить обновления", key=f"check_{pkg_id}"):
                    with st.spinner("Сверяю с Google Play..."):
                        try:
                            new_m = app(pkg_id, lang='en', country=info['geo'])
                            
                            # Сравниваем Тайтл и Краткое описание
                            if (new_m['title'] != info['current']['title'] or 
                                new_m['summary'] != info['current']['summary']):
                                
                                # Если есть изменения — переносим текущее в историю
                                info['history'].append(info['current'])
                                # Обновляем текущее на новое
                                info['current'] = {
                                    "title": new_m['title'],
                                    "summary": new_m['summary'],
                                    "description": new_m['description']
                                }
                                
                                if save_data(db):
                                    st.balloons()
                                    st.rerun()
                            else:
                                st.info("Изменений не найдено.")
                        except Exception as e:
                            st.error(f"Не удалось связаться с Google Play: {e}")
            
            with col2:
                st.write(f"**ГЕО мониторинга:** {info['geo']}")
                st.write(f"**Short Description:** {info['current']['summary']}")

            # Если в истории что-то есть, показываем предупреждение и кнопку отчета
            if info['history']:
                st.warning("⚠️ Зафиксированы изменения!")
                last_ver = info['history'][-1]
                
                if last_ver['title'] != info['current']['title']:
                    st.write(f"**Старый Title:** ~~{last_ver['title']}~~ ➡️ {info['current']['title']}")
                if last_ver['summary'] != info['current']['summary']:
                    st.write(f"**Старый SD:** ~~{last_ver['summary']}~~ ➡️ {info['current']['summary']}")
                
                report_text = f"ОТЧЕТ ОБ ИЗМЕНЕНИИ ASO ДЛЯ {pkg_id}\n\nБЫЛО:\n{last_ver}\n\nСТАЛО:\n{info['current']}"
                st.download_button(
                    label="📥 Скачать отчет для ИИ",
                    data=report_text,
                    file_name=f"aso_report_{pkg_id}.txt",
                    key=f"dl_{pkg_id}"
                )