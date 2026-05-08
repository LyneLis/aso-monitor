import streamlit as st
import json
import pandas as pd
import requests
from google_play_scraper import app
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    DB_AVAILABLE = True
except Exception as e:
    st.error(f"Ошибка инициализации подключения: {e}")
    DB_AVAILABLE = False

def get_minsk_time():
    # Минск находится в UTC+3
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

def get_lang(geo_code):
    mapping = {'us': 'en', 'uk': 'en', 'gb': 'en', 'au': 'en', 'ca': 'en'}
    return mapping.get(geo_code, geo_code)

def send_telegram_msg(text):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            requests.post(url, data={"chat_id": chat_id, "text": text})
        except Exception as e:
            st.sidebar.error(f"Сбой отправки в TG: {e}")

def load_data():
    if not DB_AVAILABLE: return {}
    try:
        df = conn.read(ttl=0)
        if df is None or df.empty: return {}
        data = {}
        for _, row in df.iterrows():
            if pd.isna(row['package_id']): continue
            
            pkg_id = str(row['package_id']).strip()
            geo = str(row['geo']).strip().lower()
            unique_key = f"{pkg_id}_{geo}"
            
            # Безопасно загружаем логи проверок, если колонка уже существует
            check_log = []
            if 'check_log' in df.columns:
                log_val = row['check_log']
                if isinstance(log_val, str) and log_val.strip() != "":
                    try:
                        check_log = json.loads(log_val)
                    except:
                        pass
            
            data[unique_key] = {
                "package_id": pkg_id,
                "geo": geo,
                "current": {
                    "title": str(row['title']),
                    "summary": str(row['summary']),
                    "description": str(row['description'])
                },
                "history": json.loads(row['history']) if isinstance(row['history'], str) and row['history'] != "" else [],
                "check_log": check_log
            }
        return data
    except Exception as e:
        return {}

def save_data(data):
    if not DB_AVAILABLE: return False
    try:
        rows = []
        for key, info in data.items():
            rows.append({
                "package_id": info['package_id'],
                "geo": info['geo'],
                "title": info['current']['title'],
                "summary": info['current']['summary'],
                "description": info['current']['description'],
                "history": json.dumps(info['history'], ensure_ascii=False),
                "check_log": json.dumps(info.get('check_log', []), ensure_ascii=False)
            })
        conn.update(data=pd.DataFrame(rows))
        st.toast("✅ Данные успешно сохранены в Google Sheets!")
        return True
    except Exception as e:
        st.error(f"❌ ОШИБКА ЗАПИСИ В ТАБЛИЦУ: {e}")
        return False

st.title("🚀 ASO Monitor PRO")
db = load_data()

# Кнопка "Проверить всё сразу"
if st.button("🔍 Проверить все приложения сейчас"):
    with st.spinner("Идет массовая проверка в Google Play..."):
        updates_count = 0
        for key, info in db.items():
            try:
                pkg_id = info['package_id']
                geo = info['geo']
                target_lang = get_lang(geo)
                new_m = app(pkg_id, lang=target_lang, country=geo)
                
                log_entry = {"time": get_minsk_time(), "status": "🟢 Без изменений"}

                if new_m['title'] != info['current']['title'] or new_m['summary'] != info['current']['summary']:
                    msg = f"⚠️ ИЗМЕНЕНИЕ ASO!\nГЕО: {geo.upper()}\nПриложение: {new_m['title']}\nID: {pkg_id}\n\nБыло: {info['current']['title']}\nСтало: {new_m['title']}"
                    send_telegram_msg(msg)
                    
                    info['history'].append(info['current'])
                    info['current'] = {
                        "title": new_m['title'], 
                        "summary": new_m['summary'], 
                        "description": new_m['description']
                    }
                    log_entry["status"] = "🔴 Найдено изменение!"
                    updates_count += 1
                
                # Добавляем в лог и храним только последние 15 записей
                info.setdefault('check_log', []).append(log_entry)
                info['check_log'] = info['check_log'][-15:]
                
            except:
                info.setdefault('check_log', []).append({"time": get_minsk_time(), "status": "⚪ Ошибка связи со стором"})
                info['check_log'] = info['check_log'][-15:]
        
        save_data(db)
        if updates_count > 0:
            st.success(f"Проверка завершена! Найдено и отправлено в TG изменений: {updates_count}")
        else:
            st.info("Проверка завершена. Изменений у конкурентов не обнаружено.")
        st.rerun()

# Боковое меню
with st.sidebar:
    st.header("➕ Добавить приложение")
    new_id = st.text_input("Package ID", placeholder="com.whatsapp").strip()
    new_geo = st.text_input("ГЕО (страна)", value="us").strip().lower()
    
    if st.button("Добавить в мониторинг"):
        if new_id and len(new_geo) == 2:
            unique_key = f"{new_id}_{new_geo}"
            if unique_key in db:
                st.warning(f"Приложение {new_id} для ГЕО {new_geo.upper()} уже есть в списке!")
            else:
                with st.spinner("Запрос к Google Play..."):
                    try:
                        target_lang = get_lang(new_geo)
                        res = app(new_id, lang=target_lang, country=new_geo)

                        meta = {
                            "title": res['title'],
                            "summary": res['summary'],
                            "description": res['description']
                        }
                        current_db = db.copy()
                        # При добавлении сразу пишем первый лог
                        first_log = [{"time": get_minsk_time(), "status": "🆕 Добавлено в трекер"}]
                        current_db[unique_key] = {"package_id": new_id, "geo": new_geo, "current": meta, "history": [], "check_log": first_log}
                        
                        if save_data(current_db):
                            st.balloons()
                            st.rerun()
                    except Exception as e:
                        st.error(f"Приложение не найдено в ГЕО '{new_geo}'. Убедитесь, что ID и код страны верны.")
        else:
            st.warning("Введите Package ID и корректный 2-буквенный код страны (например: us, ru, de)!")

# Список приложений
if not db:
    st.info("База данных пуста. Добавьте первое приложение слева.")
else:
    st.write(f"В мониторинге приложений: {len(db)}")
    for key, info in db.items():
        pkg_id = info['package_id']
        geo = info['geo']
        
        col_expander, col_delete = st.columns([11, 1])
        
        with col_expander:
            with st.expander(f"📦 [{geo.upper()}] {info['current']['title']} ({pkg_id})"):
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    if st.button("Проверить обновления", key=f"check_{key}"):
                        with st.spinner("Сверяю с Google Play..."):
                            try:
                                target_lang = get_lang(geo)
                                new_m = app(pkg_id, lang=target_lang, country=geo)
                                
                                log_entry = {"time": get_minsk_time(), "status": "🟢 Без изменений"}
                                
                                if (new_m['title'] != info['current']['title'] or 
                                    new_m['summary'] != info['current']['summary']):
                                    
                                    msg = f"⚠️ ИЗМЕНЕНИЕ ASO!\nГЕО: {geo.upper()}\nПриложение: {new_m['title']}\nID: {pkg_id}\n\nБыло: {info['current']['title']}\nСтало: {new_m['title']}"
                                    send_telegram_msg(msg)

                                    info['history'].append(info['current'])
                                    info['current'] = {
                                        "title": new_m['title'],
                                        "summary": new_m['summary'],
                                        "description": new_m['description']
                                    }
                                    log_entry["status"] = "🔴 Найдено изменение!"
                                    st.balloons()
                                else:
                                    st.info("Изменений не найдено.")
                                
                                info.setdefault('check_log', []).append(log_entry)
                                info['check_log'] = info['check_log'][-15:]
                                save_data(db)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Не удалось связаться с Google Play: {e}")
                
                with col2:
                    st.write(f"**ГЕО мониторинга:** {geo.upper()}")
                    st.write(f"**Short Description:** {info['current']['summary']}")

                if info['history']:
                    st.warning("⚠️ Зафиксированы старые изменения!")
                    last_ver = info['history'][-1]
                    
                    if last_ver['title'] != info['current']['title']:
                        st.write(f"**Старый Title:** ~~{last_ver['title']}~~ ➡️ {info['current']['title']}")
                    if last_ver['summary'] != info['current']['summary']:
                        st.write(f"**Старый SD:** ~~{last_ver['summary']}~~ ➡️ {info['current']['summary']}")
                    
                    report_text = f"ОТЧЕТ ОБ ИЗМЕНЕНИИ ASO ДЛЯ {pkg_id} (ГЕО: {geo.upper()})\n\nБЫЛО:\n{last_ver}\n\nСТАЛО:\n{info['current']}"
                    st.download_button(
                        label="📥 Скачать отчет для ИИ",
                        data=report_text,
                        file_name=f"aso_report_{pkg_id}_{geo}.txt",
                        key=f"dl_{key}"
                    )
                
                # --- БЛОК ИСТОРИИ ПРОВЕРОК ---
                st.markdown("---")
                st.markdown("🕒 **История проверок (Время Минское):**")
                if info.get('check_log'):
                    # Показываем новые сверху
                    for log in reversed(info['check_log']):
                        st.text(f"[{log['time']}] {log['status']}")
                else:
                    st.text("Проверок еще не было.")
                    
        with col_delete:
            if st.button("🗑️", key=f"del_{key}", help="Удалить приложение"):
                del db[key]
                save_data(db)
                st.rerun()