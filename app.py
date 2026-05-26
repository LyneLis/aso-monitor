import streamlit as st
import time
from datetime import UTC, datetime, timedelta

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
STALE_CHECK_HOURS = 24
ADD_APP_PREVIEW_KEY = "add_app_preview"
DEFAULT_PREVIEW_LOCALE = "en-US"


def owner_name_for(chat_id):
    return next((name for name, cid in users_dict.items() if str(cid) == str(chat_id)), "Неизвестно")


def group_matches_search(pkg_id, chat_id, keys, query):
    if not query:
        return True
    owner_name = owner_name_for(chat_id)
    values = [str(pkg_id), str(chat_id), owner_name]
    for key in keys:
        info = db[key]
        current = info.get("current", {})
        values.extend([
            info.get("geo", ""),
            current.get("title", ""),
            current.get("summary", ""),
        ])
    haystack = " ".join(str(value).lower() for value in values)
    return query.lower() in haystack


def filter_app_groups(app_groups, query):
    return {
        group_key: keys
        for group_key, keys in app_groups.items()
        if group_matches_search(group_key[0], group_key[1], keys, query)
    }


def locale_key_by_name(locale_name):
    return next((key for key, value in GP_LOCALES_RAW.items() if value == locale_name), DEFAULT_PREVIEW_LOCALE)


def platform_label_for_app_id(app_id):
    return "App Store" if str(app_id).isdigit() else "Google Play"


def preview_matches(preview, app_id, locale):
    return bool(preview and preview.get("app_id") == app_id and preview.get("locale") == locale and preview.get("data"))


def current_dict_from_fetch_result(result):
    return {
        "title": result["title"],
        "summary": result["summary"],
        "description": result["description"],
        "icon": result.get("icon", ""),
        "header_image": result.get("headerImage", ""),
        "screenshots": result.get("screenshots", []),
    }


def latest_log_label(info):
    logs = info.get("check_log") or []
    if not logs:
        return "Проверок еще не было"
    last = logs[-1]
    return f"{last.get('time', '—')} · {last.get('status', '—')}"


def latest_log_status(info):
    logs = info.get("check_log") or []
    if not logs:
        return ""
    return logs[-1].get("status", "")


def latest_log_time(info):
    logs = info.get("check_log") or []
    if not logs:
        return None
    try:
        return datetime.strptime(logs[-1].get("time", ""), "%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError):
        return None


def log_time(log):
    try:
        return datetime.strptime(log.get("time", ""), "%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError):
        return datetime.min


def current_minsk_datetime():
    return (datetime.now(UTC) + timedelta(hours=3)).replace(tzinfo=None)


def is_error_status(status):
    return str(status or "").startswith("❌")


def is_change_status(status):
    return "Изменение" in str(status or "")


def is_stale_info(info, now=None):
    checked_at = latest_log_time(info)
    if not checked_at:
        return True
    current_time = now or current_minsk_datetime()
    return current_time - checked_at > timedelta(hours=STALE_CHECK_HOURS)


def is_problem_info(info):
    status = latest_log_status(info)
    return is_error_status(status) or is_stale_info(info)


def status_priority_for_info(info, now=None):
    status = latest_log_status(info)
    if is_error_status(status):
        return 0
    if is_stale_info(info, now):
        return 1
    if is_change_status(status):
        return 2
    return 3


def locale_status_label(info, now=None):
    status = latest_log_status(info)
    if is_error_status(status):
        return "🔴 Ошибка"
    if not info.get("check_log"):
        return "🟠 Без проверки"
    if is_stale_info(info, now):
        return "🟠 Давно"
    if is_change_status(status):
        return "🔵 Изменение"
    return "🟢 Ок"


def group_status_summary(keys, now=None):
    current_time = now or current_minsk_datetime()
    infos = [db[key] for key in keys]
    errors = sum(1 for info in infos if is_error_status(latest_log_status(info)))
    stale = sum(1 for info in infos if is_stale_info(info, current_time))
    changes = sum(1 for info in infos if is_change_status(latest_log_status(info)))

    if errors:
        return f"🔴 Ошибка: {errors}"
    if stale:
        return f"🟠 Проверить: {stale}"
    if changes:
        return f"🔵 Изменение: {changes}"
    return "🟢 Ок"


def group_status_priority(keys, now=None):
    current_time = now or current_minsk_datetime()
    return min(status_priority_for_info(db[key], current_time) for key in keys)


def latest_group_check_label(keys):
    latest = None
    latest_info = None
    for key in keys:
        checked_at = latest_log_time(db[key])
        if checked_at and (latest is None or checked_at > latest):
            latest = checked_at
            latest_info = db[key]
    if not latest or not latest_info:
        return "Проверок еще не было"
    return f"Последняя проверка: {latest.strftime('%d.%m.%Y %H:%M:%S')} · {latest_info['geo'].upper()}"


def attention_locales_label(keys, now=None):
    current_time = now or current_minsk_datetime()
    problem_geos = [
        db[key]["geo"].upper()
        for key in keys
        if status_priority_for_info(db[key], current_time) < 2
    ]
    if not problem_geos:
        return ""
    shown = ", ".join(problem_geos[:4])
    hidden = len(problem_geos) - 4
    if hidden > 0:
        shown += f" +{hidden}"
    return f"Требуют внимания: {shown}"


def flatten_log_entries(data, predicate):
    rows = []
    for info in data.values():
        current = info.get("current", {})
        title = current.get("title") or info.get("package_id", "")
        for log in info.get("check_log") or []:
            status = log.get("status", "")
            if not predicate(status):
                continue
            rows.append({
                "time": log.get("time", ""),
                "owner": owner_name_for(info.get("chat_id")),
                "app": title,
                "geo": str(info.get("geo", "")).upper(),
                "status": status,
            })
    return sorted(rows, key=lambda row: log_time({"time": row["time"]}), reverse=True)


def row_for_info(info, status=None):
    current = info.get("current", {})
    return {
        "Время": latest_log_label(info).split(" · ")[0],
        "Владелец": owner_name_for(info.get("chat_id")),
        "Приложение": current.get("title") or info.get("package_id", ""),
        "Локаль": str(info.get("geo", "")).upper(),
        "Статус": status or latest_log_status(info) or "Проверок еще не было",
    }


def render_health_panel(data):
    now = current_minsk_datetime()
    infos = list(data.values())
    error_infos = [info for info in infos if is_error_status(latest_log_status(info))]
    change_infos = [info for info in infos if is_change_status(latest_log_status(info))]
    unchecked_infos = [info for info in infos if not info.get("check_log")]
    stale_infos = [info for info in infos if is_stale_info(info, now)]

    st.subheader("Состояние сервиса")
    col_err, col_change, col_empty, col_stale = st.columns(4)
    col_err.metric("Ошибки", len(error_infos))
    col_change.metric("Последние изменения", len(change_infos))
    col_empty.metric("Без проверок", len(unchecked_infos))
    col_stale.metric(f"Старше {STALE_CHECK_HOURS} ч", len(stale_infos))

    if not infos:
        st.info("Пока нет локалей для мониторинга.")
        return

    if error_infos:
        st.warning("Есть локали с ошибками проверки.")
    elif stale_infos:
        st.warning("Есть локали, которые давно не проверялись.")
    else:
        st.success("Критичных проблем по последним логам не видно.")

    recent_errors = flatten_log_entries(data, is_error_status)[:5]
    recent_changes = flatten_log_entries(data, is_change_status)[:5]
    stale_rows = [
        row_for_info(info, "Давно не проверялась" if info.get("check_log") else "Проверок еще не было")
        for info in sorted(stale_infos, key=lambda item: latest_log_time(item) or datetime.min)[:10]
    ]

    tab_errors, tab_changes, tab_stale = st.tabs(["Ошибки", "Изменения", "Давно не проверялись"])
    with tab_errors:
        if recent_errors:
            st.dataframe(
                [{
                    "Время": row["time"],
                    "Владелец": row["owner"],
                    "Приложение": row["app"],
                    "Локаль": row["geo"],
                    "Статус": row["status"],
                } for row in recent_errors],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("Ошибок в последних логах нет.")
    with tab_changes:
        if recent_changes:
            st.dataframe(
                [{
                    "Время": row["time"],
                    "Владелец": row["owner"],
                    "Приложение": row["app"],
                    "Локаль": row["geo"],
                    "Статус": row["status"],
                } for row in recent_changes],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("Недавних изменений в последних логах нет.")
    with tab_stale:
        if stale_rows:
            st.dataframe(stale_rows, hide_index=True, use_container_width=True)
        else:
            st.caption("Все локали проверялись недавно.")


def set_flash(kind, message):
    st.session_state["flash_message"] = {"kind": kind, "message": message}


def render_flash():
    flash = st.session_state.pop("flash_message", None)
    if not flash:
        return
    render = {
        "success": st.success,
        "info": st.info,
        "warning": st.warning,
        "error": st.error,
    }.get(flash.get("kind"), st.info)
    render(flash.get("message", ""))


def render_overview(android_groups, ios_groups):
    app_count = len(android_groups) + len(ios_groups)
    locale_count = sum(len(keys) for keys in android_groups.values()) + sum(len(keys) for keys in ios_groups.values())
    owner_count = len({db[key].get("chat_id") for keys in list(android_groups.values()) + list(ios_groups.values()) for key in keys})

    col_apps, col_locales, col_android, col_ios, col_users = st.columns(5)
    col_apps.metric("Приложений", app_count)
    col_locales.metric("Локалей", locale_count)
    col_android.metric("Android", len(android_groups))
    col_ios.metric("iOS", len(ios_groups))
    col_users.metric("Владельцев", owner_count)


def save_apps_or_show_error(data, *, updated_keys=None, deleted_keys=None):
    if repo.save_apps(data, updated_keys=updated_keys, deleted_keys=deleted_keys):
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
render_flash()
db = repo.load_apps()
if repo.load_errors:
    st.error(f"Не удалось загрузить данные из Google Sheets: {repo.load_error_message()}")
    if "apps" in repo.load_errors:
        st.stop()

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
    st.header("🔎 Навигация")
    search_query = st.text_input(
        "Поиск",
        placeholder="Название, Package ID, локаль или владелец",
    ).strip()
    show_problem_only = st.checkbox("Показать только проблемные", value=False)

    st.divider()
    st.header("➕ Добавить приложение")
    st.info("Чтобы получать уведомления, сначала напишите боту.")
    st.link_button("➕ Добавить бота", "https://t.me/aso_omg_bot", use_container_width=True)
    
    locale_names = list(GP_LOCALES_RAW.values())
    default_preview_name = GP_LOCALES_RAW[DEFAULT_PREVIEW_LOCALE]
    with st.form("add_app_preview_form"):
        new_id = st.text_input("Package ID / App ID", placeholder="com.app.name ИЛИ 835599320").strip()
        preview_locale_name = st.selectbox(
            "Локаль для поиска",
            options=locale_names,
            index=locale_names.index(default_preview_name),
        )
        find_app_submitted = st.form_submit_button("Найти приложение", use_container_width=True)
    preview_geo = locale_key_by_name(preview_locale_name)

    if find_app_submitted:
        if not new_id:
            st.warning("Введите Package ID / App ID.")
        else:
            with st.spinner("Ищу приложение..."):
                try:
                    preview_data = fetch_app_data(new_id, preview_geo)
                    st.session_state[ADD_APP_PREVIEW_KEY] = {
                        "app_id": new_id,
                        "locale": preview_geo,
                        "data": preview_data,
                    }
                    st.success("Приложение найдено.")
                except Exception as e:
                    st.session_state.pop(ADD_APP_PREVIEW_KEY, None)
                    st.error(f"Не удалось найти приложение ({e})")

    preview = st.session_state.get(ADD_APP_PREVIEW_KEY)
    has_preview = preview_matches(preview, new_id, preview_geo)
    selected_names = []
    new_geos = []
    add_for_user = "Выбрать..."

    if has_preview:
        preview_data = preview["data"]
        preview_title = preview_data.get("title") or preview["app_id"]
        preview_icon = preview_data.get("icon")
        col_preview_icon, col_preview_text = st.columns([1, 3])
        with col_preview_icon:
            if preview_icon:
                st.image(preview_icon, width=56)
        with col_preview_text:
            st.write(f"**{preview_title}**")
            st.caption(f"{platform_label_for_app_id(preview['app_id'])} · {preview['app_id']}")
            st.caption(f"Проверено в {GP_LOCALES_RAW.get(preview['locale'], preview['locale'])}")

        default_locale_names = [GP_LOCALES_RAW.get(preview_geo, default_preview_name)]
        selected_names = st.multiselect("Выберите локали", options=locale_names, default=default_locale_names)
        new_geos = [k for k, v in GP_LOCALES_RAW.items() if v in selected_names]

        if users_dict:
            add_for_user = st.selectbox("Добавить для пользователя", options=["Выбрать..."] + list(users_dict.keys()))
        else:
            st.warning("Пользователи не найдены.")

    can_add_app = bool(has_preview and new_geos and add_for_user != "Выбрать...")
    if st.button(
        "Добавить в мониторинг",
        type="primary",
        use_container_width=True,
        disabled=not can_add_app,
        help="Сначала найдите приложение, затем выберите локали и пользователя.",
    ):
        if can_add_app:
            app_id = preview["app_id"]
            preview_data = preview["data"]
            preview_locale = preview["locale"]
            selected_chat_id = str(users_dict[add_for_user]).strip()
            
            success_added = 0
            added_keys = set()
            with st.spinner(f"Загрузка локалей..."):
                for geo in new_geos:
                    u_key = f"{app_id}_{geo}_{selected_chat_id}"
                    if u_key in db: 
                        st.warning(f"[{geo}] Уже отслеживается!")
                    else:
                        try:
                            res = preview_data if geo == preview_locale else fetch_app_data(app_id, geo)
                            db[u_key] = {
                                "package_id": app_id,
                                "geo": geo,
                                "chat_id": selected_chat_id,
                                "current": current_dict_from_fetch_result(res),
                                "history": [],
                                "check_log": [{"time": get_minsk_time(), "status": "🆕 Добавлено"}],
                            }
                            success_added += 1
                            added_keys.add(u_key)
                        except Exception as e:
                            st.error(f"Ошибка: {geo} не найдено ({e})")

            if success_added > 0:
                if save_apps_or_show_error(db, updated_keys=added_keys):
                    st.session_state.pop(ADD_APP_PREVIEW_KEY, None)
                    st.success(f"Успешно добавлено локалей: {success_added}")
                    st.rerun()

# --- ОСНОВНАЯ ЧАСТЬ ---
if st.button(
    "🔍 Проверить все локали",
    type="primary",
    help="Проверяет все записи в таблице, независимо от выбранного пользователя и поиска.",
    disabled=not db,
):
    with st.spinner("Тотальная проверка обновлений... (Может занять время из-за лимитов ИИ)"):
        updates_count = 0
        errors_count = 0
        batched_alerts = {}
        keys_to_check = list(db.keys())
        total_checks = len(keys_to_check)
        progress = st.progress(0, text="Подготовка проверки")
        status_box = st.empty()

        for idx, key in enumerate(keys_to_check, start=1):
            info = db[key]
            title = info.get("current", {}).get("title") or info["package_id"]
            status_box.info(f"Проверка {idx}/{total_checks}: {title} · {info['geo'].upper()}")
            u, changed_list, txt_payload, outcome = run_check_for_item(key, info, {}, single_mode=False, skip_ai=True)
            updates_count += u
            if latest_log_status(info).startswith("❌"):
                errors_count += 1
            progress.progress(idx / total_checks, text=f"Проверено локалей: {idx}/{total_checks}")
            
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

        progress.empty()
        status_box.empty()

        total_alerts = len(batched_alerts)
        if total_alerts:
            alert_progress = st.progress(0, text="Подготовка уведомлений")
            alert_status = st.empty()
            for alert_index, ((pkg_id, c_id, is_ios), data) in enumerate(batched_alerts.items(), start=1):
                alert_status.info(f"Отправка уведомлений {alert_index}/{total_alerts}: {pkg_id}")
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
                alert_progress.progress(alert_index / total_alerts, text=f"Уведомления: {alert_index}/{total_alerts}")

            alert_progress.empty()
            alert_status.empty()
        
        if not save_apps_or_show_error(db, updated_keys=db.keys()):
            st.stop()
        if updates_count > 0 or errors_count > 0:
            flash_kind = "warning" if errors_count else "success"
            set_flash(flash_kind, f"Проверка завершена. Изменений: {updates_count}. Ошибок: {errors_count}.")
        else:
            set_flash("info", "Проверка завершена. Изменений не обнаружено.")
        st.rerun()

# --- ФИЛЬТРАЦИЯ И ГРУППИРОВКА ---
android_apps = {}
ios_apps = {}
visible_db = {}

for key, info in db.items():
    if view_chat_id and str(info.get('chat_id')).strip() != view_chat_id:
        continue
    visible_db[key] = info
    if show_problem_only and not is_problem_info(info):
        continue

    grp = (info['package_id'], info['chat_id'])
    if str(info['package_id']).isdigit():
        if grp not in ios_apps: ios_apps[grp] = []
        ios_apps[grp].append(key)
    else:
        if grp not in android_apps: android_apps[grp] = []
        android_apps[grp].append(key)

android_apps = filter_app_groups(android_apps, search_query)
ios_apps = filter_app_groups(ios_apps, search_query)

tab_apps, tab_service = st.tabs(["📱 Приложения", "⚙️ Состояние"])

def render_app_groups(app_groups, os_icon):
    if not app_groups:
        st.info("Нет приложений для отображения.")
        return
        
    sorted_groups = sorted(
        app_groups.items(),
        key=lambda item: (
            group_status_priority(item[1]),
            (db[item[1][0]]["current"].get("title") or item[0][0]).lower(),
        ),
    )
    for (pkg_id, chat_id), keys in sorted_groups:
        owner_name = owner_name_for(chat_id)
        first_info = db[keys[0]]
        main_title = first_info['current'].get('title') or pkg_id
        main_icon = first_info['current'].get('icon')
        status_summary = group_status_summary(keys)
        attention_label = attention_locales_label(keys)

        with st.expander(f"{status_summary} · {os_icon} {main_title} · {pkg_id} · {owner_name} · {len(keys)} лок."):
            col_img, col_space, col_btn = st.columns([1, 2, 4])
            with col_img:
                if main_icon and main_icon != 'nan': st.image(main_icon, width=80)
                st.caption(f"{len(keys)} локалей")
            with col_space:
                st.write(f"**{status_summary}**")
                st.caption(latest_group_check_label(keys))
                if attention_label:
                    st.caption(attention_label)
            
            with col_btn:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(
                        f"Проверить локали ({len(keys)})",
                        key=f"ch_grp_{pkg_id}_{chat_id}",
                        use_container_width=True,
                    ):
                        with st.spinner("Сверка..."):
                            upd = 0
                            errors = 0
                            batched_ai = {}
                            progress = st.progress(0, text="Подготовка проверки")
                            status_box = st.empty()
                            for idx, k in enumerate(keys, start=1):
                                locale_info = db[k]
                                title = locale_info.get("current", {}).get("title") or locale_info["package_id"]
                                status_box.info(f"Проверка {idx}/{len(keys)}: {title} · {locale_info['geo'].upper()}")
                                u, _, txt_payload, _ = run_check_for_item(k, db[k], {}, single_mode=False, skip_ai=True)
                                upd += u
                                if latest_log_status(db[k]).startswith("❌"):
                                    errors += 1
                                if txt_payload:
                                    batched_ai[db[k]['geo']] = txt_payload
                                progress.progress(idx / len(keys), text=f"Проверено локалей: {idx}/{len(keys)}")
                            progress.empty()
                            status_box.empty()
                            if upd > 0 and batched_ai:
                                st.info("Готовлю пакетный AI-разбор")
                                ai_msg = gemini.analyze_batched_changes(batched_ai)
                                telegram.send_message(
                                    f"🤖 Пакетный анализ ({pkg_id}):\n\n{clean_ai_for_telegram(ai_msg)}",
                                    chat_id,
                                )
                        if save_apps_or_show_error(db, updated_keys=keys):
                            if errors:
                                set_flash("warning", f"Проверка завершена. Изменений: {upd}. Ошибок: {errors}.")
                            elif upd:
                                set_flash("success", f"Проверка завершена. Изменений: {upd}.")
                            else:
                                set_flash("info", "Проверка завершена. Изменений не обнаружено.")
                            st.rerun()
                
                with col2:
                    saved_audit = first_info.get('ai_audit', '')
                    btn_label = "Обновить ASO-разбор" if saved_audit else "Текущий ASO разбор"
                    
                    if st.button(btn_label, key=f"ai_force_{pkg_id}_{chat_id}", use_container_width=True):
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
                                    if save_apps_or_show_error(db, updated_keys={keys[0]}):
                                        set_flash("success", "ASO-разбор обновлен.")
                                        st.rerun()
                                else:
                                    st.error(f"Ошибка ИИ: {ai_msg}")
                            else:
                                st.error("Нет данных для анализа.")
            
            if first_info.get('ai_audit'):
                with st.expander("📊 Сохраненный ИИ-Аудит (Текущая стратегия)"):
                    st.markdown(first_info['ai_audit'])

            tabs_loc = st.tabs([
                f"{GP_LOCALES_RAW.get(db[k]['geo'], db[k]['geo'])} · {locale_status_label(db[k])}"
                for k in keys
            ])
            for i, k in enumerate(keys):
                with tabs_loc[i]:
                    info = db[k]
                    c1, c2, c3 = st.columns([1.5, 4, 1])
                    with c1:
                        if info['current'].get('icon'): st.image(info['current']['icon'], width=70)
                    with c2:
                        st.write(f"**Локаль:** `{info['geo']}` · {locale_status_label(info)}")
                        st.caption(f"Последняя проверка: {latest_log_label(info)}")
                        title = info['current'].get('title')
                        summary = info['current'].get('summary')
                        if title:
                            st.write(f"**Название:** {title}")
                        if summary:
                            st.caption(summary)
                        if st.button("Проверить локаль", key=f"btn_sng_{k}", use_container_width=True):
                            u, changed, _, _ = run_check_for_item(k, info, {}, single_mode=True)
                            if save_apps_or_show_error(db, updated_keys={k}):
                                if latest_log_status(info).startswith("❌"):
                                    set_flash("warning", f"{info['geo'].upper()}: проверка завершилась с ошибкой.")
                                elif u:
                                    set_flash("success", f"{info['geo'].upper()}: найдено изменение ({', '.join(changed)}).")
                                else:
                                    set_flash("info", f"{info['geo'].upper()}: изменений не обнаружено.")
                                st.rerun()
                    with c3:
                        confirm_key = f"confirm_del_{k}"
                        if st.session_state.get(confirm_key):
                            st.warning("Удалить?")
                            if st.button("Да", key=f"del_yes_{k}", use_container_width=True):
                                del db[k]
                                st.session_state[confirm_key] = False
                                if save_apps_or_show_error(db, deleted_keys={k}):
                                    st.rerun()
                            if st.button("Нет", key=f"del_no_{k}", use_container_width=True):
                                st.session_state[confirm_key] = False
                                st.rerun()
                        elif st.button("🗑️", key=f"del_{k}", help="Удалить локаль из мониторинга"):
                            st.session_state[confirm_key] = True
                            st.rerun()

with tab_apps:
    render_overview(android_apps, ios_apps)
    st.divider()
    tab_android, tab_ios = st.tabs(["🤖 Android (Google Play)", "🍎 iOS (App Store)"])

    with tab_android:
        render_app_groups(android_apps, "🤖")

    with tab_ios:
        render_app_groups(ios_apps, "🍎")

with tab_service:
    render_health_panel(visible_db)
