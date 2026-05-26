import streamlit as st
import time

from core import (
    GP_LOCALES_RAW,
    GeminiClient,
    Settings,
    TelegramClient,
    add_changed_locale_to_batch,
    check_item_snapshots,
    clean_ai_for_telegram,
    current_dict_from_snapshot,
    fetch_app_data,
    fill_missing_assets,
    format_changes_report,
    format_single_locale_report,
    get_minsk_time,
    snapshot_from_current,
)
from sheets import StreamlitAppsRepository

st.set_page_config(page_title="ASO Monitor PRO", layout="wide")

settings = Settings.from_streamlit_secrets(st.secrets)
gemini = GeminiClient(settings)
telegram = TelegramClient(settings)
repo = StreamlitAppsRepository.connect()
users_dict = repo.load_users()


def save_apps_or_show_error(data):
    if repo.save_apps(data):
        return True
    details = f" ({repo.last_error})" if repo.last_error else ""
    st.error(f"Не удалось сохранить изменения в Google Sheets{details}")
    return False


def run_check_for_item(key, info, user_reports_dict, single_mode=False, skip_ai=False):
    updates = 0
    changed = []
    text_changes_payload = None
    outcome = None

    try:
        log_entry = {"time": get_minsk_time(), "status": "🟢 Ок"}
        old_snap, is_table_error = snapshot_from_current(info["current"])

        outcome = check_item_snapshots(
            info["package_id"],
            info["geo"],
            old_snap,
            info.get("history", []),
            is_table_error,
            label_style="web",
        )
        new_snap = outcome.new_snapshot
        result = outcome.result

        if result.has_changes:
            updates = 1
            changed = result.changed
            text_changes_payload = result.text_payload
            c_id = info["chat_id"]

            if single_mode:
                os_icon = "🍎" if str(info["package_id"]).isdigit() else "🤖"
                msg_prefix = "🔄 ОТКАТ (A/B ТЕСТ)" if result.is_rollback else "⚠️ ИЗМЕНЕНИЕ"
                alert_msg = (
                    f"{msg_prefix} {os_icon} [{info['geo'].upper()}]\n📦 {new_snap.title}\n"
                    f"Изменено: {', '.join(changed)}"
                )
                if result.is_rollback:
                    alert_msg += "\n\n⚠️ Тексты вернулись к одной из прошлых версий."
                telegram.send_message(alert_msg, c_id)

                if result.text_payload:
                    report_content = format_single_locale_report(
                        info["package_id"],
                        info["geo"],
                        old_snap,
                        new_snap,
                        get_minsk_time(),
                    )
                    telegram.send_document(
                        report_content,
                        f"report_{info['package_id']}.txt",
                        f"📄 Детальный отчет: {info['package_id']}",
                        c_id,
                    )

                    if not skip_ai:
                        tp = result.text_payload
                        raw_ai_analysis = gemini.analyze_changes(
                            tp["old_t"], tp["new_t"], tp["old_s"], tp["new_s"], tp["old_d"], tp["new_d"]
                        )
                        telegram.send_message(
                            f"🤖 Анализ ИИ (Сайт):\n\n{clean_ai_for_telegram(raw_ai_analysis)}",
                            c_id,
                        )

            info["history"].append(info["current"])
            info["current"] = current_dict_from_snapshot(new_snap)
            log_entry["status"] = f"🔴 Изменение ({', '.join(changed)})"

        elif result.is_table_error:
            info["current"] = current_dict_from_snapshot(new_snap)
            log_entry["status"] = "🟢 Исправление ошибки"
        else:
            fill_missing_assets(info["current"], new_snap)

        info.setdefault("check_log", []).append(log_entry)
        info["check_log"] = info["check_log"][-5:]
    except Exception as e:
        print(f"Ошибка проверки {key}: {e}")
        log_entry = {"time": get_minsk_time(), "status": "❌ Ошибка"}
        info.setdefault("check_log", []).append(log_entry)
        info["check_log"] = info["check_log"][-5:]

    return updates, changed, text_changes_payload, outcome


# --- ИНТЕРФЕЙС ---
st.title("🚀 ASO Monitor PRO")
st.caption("Поддерживает Google Play (ID: com.app.name) и App Store (ID: 123456789)")
db = repo.load_apps()

# --- САЙДБАР ---
with st.sidebar:
    st.header("👤 Профиль пользователя")
    if users_dict:
        view_user = st.selectbox("Режим просмотра", options=["Все приложения"] + list(users_dict.keys()))
        view_chat_id = str(users_dict[view_user]).strip() if view_user != "Все приложения" else None
    else:
        st.warning("Пользователи не найдены.")
        view_user = "Все приложения"
        view_chat_id = None

    st.divider()
    st.header("➕ Добавить приложение")
    st.info("Чтобы получать уведомления, сначала напишите боту.")
    st.link_button("➕ Добавить бота", "https://t.me/aso_omg_bot", use_container_width=True)
    
    new_id = st.text_input("Package ID / App ID", placeholder="com.app.name ИЛИ 835599320").strip()
    selected_names = st.multiselect("Выберите локали", options=list(GP_LOCALES_RAW.values()), default=["English (United States)"])
    new_geos = [k for k, v in GP_LOCALES_RAW.items() if v in selected_names]
    
    if users_dict:
        add_for_user = st.selectbox("Добавить для пользователя", options=["Выбрать..."] + list(users_dict.keys()))
    else:
        add_for_user = "Выбрать..."

    if st.button("Добавить в мониторинг", type="primary", use_container_width=True):
        if new_id and new_geos and add_for_user != "Выбрать...":
            selected_chat_id = str(users_dict[add_for_user]).strip()
            
            success_added = 0
            with st.spinner(f"Загрузка локалей..."):
                for geo in new_geos:
                    u_key = f"{new_id}_{geo}_{selected_chat_id}"
                    if u_key in db: 
                        st.warning(f"[{geo}] Уже отслеживается!")
                    else:
                        try:
                            res = fetch_app_data(new_id, geo)
                            db[u_key] = {
                                "package_id": new_id, "geo": geo, "chat_id": selected_chat_id,
                                "current": {
                                    "title": res['title'], "summary": res['summary'], "description": res['description'],
                                    "icon": res.get('icon', ''), "header_image": res.get('headerImage', ''), "screenshots": res.get('screenshots', [])
                                },
                                "history": [], "check_log": [{"time": get_minsk_time(), "status": "🆕 Добавлено"}]
                            }
                            success_added += 1
                        except Exception as e:
                            st.error(f"Ошибка: {geo} не найдено ({e})")
                
            if success_added > 0:
                if save_apps_or_show_error(db):
                    st.success(f"Успешно добавлено локалей: {success_added}")
                    st.rerun()
        else:
            st.warning("Заполните ID, локали и пользователя!")

# --- ОСНОВНАЯ ЧАСТЬ ---
if st.button("🔍 Проверить вообще всё", type="primary"):
    with st.spinner("Тотальная проверка обновлений... (Может занять время из-за лимитов ИИ)"):
        updates_count = 0
        batched_alerts = {}
        
        for key, info in db.items():
            u, changed_list, txt_payload, outcome = run_check_for_item(key, info, {}, single_mode=False, skip_ai=True)
            updates_count += u
            
            if u > 0 and outcome:
                add_changed_locale_to_batch(
                    batched_alerts,
                    info['package_id'],
                    info['chat_id'],
                    info['geo'],
                    outcome.old_snapshot,
                    outcome.new_snapshot,
                    changed_list,
                    txt_payload,
                    is_rollback=outcome.result.is_rollback,
                )

        for (pkg_id, c_id, is_ios), data in batched_alerts.items():
            os_icon = "🍎" if is_ios else "🤖"
            summary_msg = f"🔔 ИЗМЕНЕНИЯ (Массовая проверка сайта) {os_icon}\n📦 {pkg_id}\n\n"
            for geo, clist in data['changes'].items():
                summary_msg += f"🌍 [{geo.upper()}]: {', '.join(clist)}\n"
            telegram.send_message(summary_msg, c_id, chunk_sleep=1)

            if data['texts']:
                full_report = format_changes_report(pkg_id, data['texts'])
                telegram.send_document(full_report, f"report_{pkg_id}.txt", f"📄 Отчет: {pkg_id}", c_id)
                time.sleep(1)

            for vis in data['visuals']:
                geo = vis['geo'].upper()
                if vis['type'] == 'diff':
                    telegram.send_visual_diff(c_id, vis['old'], vis['new'], vis['name'], pkg_id, geo)
                    time.sleep(1.5)
                elif vis['type'] == 'screens' and vis['screens']:
                    telegram.send_screenshots(c_id, vis['screens'], pkg_id, geo)
                    time.sleep(2)

            if data['texts']:
                ai_msg = gemini.analyze_batched_changes(data['texts'])
                if not gemini.is_error_response(ai_msg):
                    telegram.send_message(
                        f"🤖 Пакетный анализ ({pkg_id}):\n\n{clean_ai_for_telegram(ai_msg)}",
                        c_id,
                    )
                    st.toast(f"⏳ Ожидание 40 секунд для сброса лимитов ИИ ({pkg_id})...")
                    time.sleep(40)
                else:
                    telegram.send_message(f"⚠️ ИИ вернул ошибку: {ai_msg}", c_id)
        
        if not save_apps_or_show_error(db):
            st.stop()
        if updates_count > 0:
            st.success(f"Готово. Изменений: {updates_count}")
        else:
            st.info("Изменений не обнаружено.")
        st.rerun()

# --- ФИЛЬТРАЦИЯ И ГРУППИРОВКА ---
android_apps = {}
ios_apps = {}

for key, info in db.items():
    if view_chat_id and str(info.get('chat_id')).strip() != view_chat_id:
        continue

    grp = (info['package_id'], info['chat_id'])
    if str(info['package_id']).isdigit():
        if grp not in ios_apps: ios_apps[grp] = []
        ios_apps[grp].append(key)
    else:
        if grp not in android_apps: android_apps[grp] = []
        android_apps[grp].append(key)

tab_android, tab_ios = st.tabs(["🤖 Android (Google Play)", "🍎 iOS (App Store)"])

def render_app_groups(app_groups, os_icon):
    if not app_groups:
        st.info("Нет приложений для отображения.")
        return
        
    for (pkg_id, chat_id), keys in app_groups.items():
        owner_name = next((name for name, cid in users_dict.items() if str(cid) == str(chat_id)), "Неизвестно")
        first_info = db[keys[0]]
        main_title = first_info['current']['title']
        main_icon = first_info['current'].get('icon')

        with st.expander(f"{os_icon} | {main_title} ({pkg_id}) | 👤 {owner_name}"):
            col_img, col_space, col_btn = st.columns([1, 2, 4])
            with col_img:
                if main_icon and main_icon != 'nan': st.image(main_icon, width=80)
            
            with col_btn:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"🔍 Проверить локали ({len(keys)})", key=f"ch_grp_{pkg_id}_{chat_id}"):
                        with st.spinner("Сверка..."):
                            upd = 0
                            batched_ai = {}
                            for k in keys:
                                u, _, txt_payload, _ = run_check_for_item(k, db[k], {}, single_mode=False, skip_ai=True)
                                upd += u
                                if txt_payload: batched_ai[db[k]['geo']] = txt_payload
                            if upd > 0 and batched_ai:
                                ai_msg = gemini.analyze_batched_changes(batched_ai)
                                telegram.send_message(
                                    f"🤖 Пакетный анализ ({pkg_id}):\n\n{clean_ai_for_telegram(ai_msg)}",
                                    chat_id,
                                )
                        if save_apps_or_show_error(db):
                            st.rerun()
                
                with col2:
                    saved_audit = first_info.get('ai_audit', '')
                    btn_label = "🔄 Обновить ASO-аудит" if saved_audit else "🧠 Текущий ASO обзор"
                    
                    if st.button(btn_label, key=f"ai_force_{pkg_id}_{chat_id}"):
                        with st.spinner("ИИ анализирует тексты... (может занять около минуты из-за лимитов)"):
                            batched_current = {}
                            for k in keys:
                                inf = db[k]
                                batched_current[inf['geo']] = {
                                    'title': inf['current']['title'],
                                    'summary': inf['current']['summary'],
                                    'description': inf['current']['description']
                                }
                            
                            if batched_current:
                                ai_msg = gemini.analyze_current_aso(batched_current)
                                if not gemini.is_error_response(ai_msg):
                                    db[keys[0]]['ai_audit'] = ai_msg
                                    if save_apps_or_show_error(db):
                                        st.rerun()
                                else:
                                    st.error(f"Ошибка ИИ: {ai_msg}")
                            else:
                                st.error("Нет данных для анализа.")
            
            if first_info.get('ai_audit'):
                with st.expander("📊 Сохраненный ИИ-Аудит (Текущая стратегия)"):
                    st.markdown(first_info['ai_audit'])

            st.markdown("---")
            tabs_loc = st.tabs([GP_LOCALES_RAW.get(db[k]['geo'], db[k]['geo']) for k in keys])
            for i, k in enumerate(keys):
                with tabs_loc[i]:
                    info = db[k]
                    c1, c2, c3 = st.columns([1.5, 4, 1])
                    with c1:
                        if info['current'].get('icon'): st.image(info['current']['icon'], width=70)
                    with c2:
                        st.write(f"**Локаль:** `{info['geo']}`")
                        if st.button("Проверить", key=f"btn_sng_{k}"):
                            run_check_for_item(k, info, {}, single_mode=True)
                            if save_apps_or_show_error(db):
                                st.rerun()
                    with c3:
                        if st.button("🗑️", key=f"del_{k}"):
                            del db[k]
                            if save_apps_or_show_error(db):
                                st.rerun()

with tab_android:
    render_app_groups(android_apps, "🤖")

with tab_ios:
    render_app_groups(ios_apps, "🍎")
