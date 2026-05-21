import gspread
from google_play_scraper import app as gp_app
import os
import json
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import time
import re

# Настройки окружения
TOKEN = os.environ.get("TELEGRAM_TOKEN")
service_account_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1jHKbRYt0hJg29RWLIXZ2fL3et_hgzvkhCSxVtTjKV9g/edit"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY, transport='rest')

ASO_PROMPT = """
Ты — ведущий ASO-стратег и эксперт по mobile-маркетингу с глубокой экспертизой в анализе данных. Твоя специализация — реверс-инжиниринг стратегий конкурентов.
Тебе будут предоставлены данные "До" и "После". Проведи анализ изменений и выяви стратегию роста.

ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ 

Output Format:
- Summary: краткий вывод.
- Keywords Migration: что удалено/добавлено.
- Strategic Shift: описание.
- Threat Level: High/Medium/Low.
- Action Plan: 3 шага.
"""

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

def run_gemini(prompt):
    if not GEMINI_API_KEY: return "❌ Ключ Gemini API не найден."
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name.replace('models/', ''))
    except:
        pass

    priority_list = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-2.5-pro', 'gemini-1.5-pro', 'gemini-pro']
    models_to_try = [m for m in priority_list if m in available_models]
    if not models_to_try:
        models_to_try = available_models[:2] if available_models else priority_list

    last_error = ""
    for model_name in models_to_try:
        try:
            print(f"🤖 Пробую модель: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = str(e)
            continue
    return f"❌ Ошибка ИИ-анализа: {last_error}"

def analyze_batched_changes_with_ai(batched_data):
    prompt = ASO_PROMPT + "\n\nВНИМАНИЕ: Конкурент обновил сразу несколько локалей. Проанализируй общую ASO-стратегию этих изменений (какие рынки в фокусе, какие ключевики тестируют):\n"
    for loc, data in batched_data.items():
        prompt += f"\n🌍 --- ЛОКАЛЬ: {loc.upper()} ---\n"
        prompt += f"БЫЛО:\nTitle: {data['old_t']}\nShort/Subtitle: {data['old_s']}\nFull Desc: {data['old_d']}\n"
        prompt += f"СТАЛО:\nTitle: {data['new_t']}\nShort/Subtitle: {data['new_s']}\nFull Desc: {data['new_d']}\n"
    return run_gemini(prompt)

def clean_val(val):
    s_val = str(val).strip()
    if s_val.lower() in ['nan', 'none', '#n/a', '']:
        return ""
    if '#error' in s_val.lower():
        return None
    return s_val

def send_visual_diff(chat_id, token, old_url, new_url, name, p_id, geo):
    if not old_url or not new_url or old_url.lower() == 'nan' or new_url.lower() == 'nan': 
        return
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    media = [
        {"type": "photo", "media": old_url, "parse_mode": "HTML", "caption": f"🔴 <b>БЫЛО</b> | {name}\n📦 {p_id} [{geo}]"},
        {"type": "photo", "media": new_url, "parse_mode": "HTML", "caption": f"🟢 <b>СТАЛО</b> | {name}\n📦 {p_id} [{geo}]"}
    ]
    try:
        requests.post(url, json={"chat_id": chat_id, "media": media})
    except Exception as e:
        print(f"⚠️ Ошибка отправки медиа-группы: {e}")

def fetch_app_data(pkg_id, locale):
    if locale == "es-419":
        l_code, c_code = "es-419", "MX" 
    elif "-" in locale:
        l_code = locale 
        c_code = locale.split("-")[1].upper() 
    else:
        l_code, c_code = locale.lower(), locale.upper()
        
    if l_code == "iw": l_code = "iw"

    if str(pkg_id).isdigit():
        apple_lang = locale.replace('-', '_').lower()
        url = f"https://itunes.apple.com/lookup?id={pkg_id}&country={c_code}&lang={apple_lang}"
        res = requests.get(url, timeout=10).json()
        
        if res.get('resultCount', 0) == 0:
            url_fallback = f"https://itunes.apple.com/lookup?id={pkg_id}&country={c_code}"
            res = requests.get(url_fallback, timeout=10).json()
            if res.get('resultCount', 0) == 0:
                raise Exception(f"Приложение {pkg_id} не найдено в App Store ({c_code})")
        
        data = res['results'][0]
        
        # Берем API-скрины
        screens = data.get('screenshotUrls', [])
        if not screens:
            screens = data.get('ipadScreenshotUrls', [])

        # Получаем иконку заранее, чтобы потом исключить ее из скриншотов
        icon_url = data.get('artworkUrl512', data.get('artworkUrl100', ''))
        if icon_url: 
            icon_url = icon_url.replace('.webp', '.jpg')

        subtitle = data.get('subtitle', '')
        if not subtitle or not screens:
            try:
                app_url = f"https://apps.apple.com/{c_code.lower()}/app/id{pkg_id}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
                    "Accept-Language": f"{locale},en-US;q=0.9"
                }
                html = requests.get(app_url, headers=headers, timeout=10).text
                
                # Парсинг сабтайтла
                if not subtitle:
                    match = re.search(r'<h2[^>]*class="[^"]*subtitle[^"]*"[^>]*>(.*?)</h2>', html, re.IGNORECASE | re.DOTALL)
                    if match:
                        subtitle = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                
                # ХИРУРГИЧЕСКИЙ ПАРСИНГ СКРИНШОТОВ (Отрезаем низ страницы)
                if not screens:
                    target_html = html
                    # Находим начало карусели со скриншотами
                    if 'we-screenshot-viewer' in target_html:
                        target_html = target_html.split('we-screenshot-viewer')[1]
                        # Отрезаем всё, что идет после этой секции (чтобы убить похожие приложения)
                        if '</section>' in target_html:
                            target_html = target_html.split('</section>')[0]
                    else:
                        # Запасной вариант: просто отсекаем отзывы и нижние полки
                        if 'shelf-title' in target_html:
                            target_html = target_html.split('shelf-title')[0]
                    
                    # Теперь собираем картинки только из безопасной, отрезанной зоны
                    scr_matches = re.findall(r'<source[^>]*srcset="([^"\s]+)[^"]*"[^>]*type="image/jpeg"', target_html)
                    if not scr_matches:
                        scr_matches = re.findall(r'<source[^>]*srcset="([^"\s]+)[^"]*"[^>]*type="image/webp"', target_html)
                    if not scr_matches:
                        scr_matches = re.findall(r'<img[^>]*class="[^"]*we-artwork__image[^"]*"[^>]*src="([^"]+)"', target_html)
                    
                    clean_screens = []
                    for s in scr_matches:
                        s_lower = s.lower()
                        # ФИЛЬТР 1: Отстреливаем иконки по словам в URL
                        if 'icon' in s_lower or 'appicon' in s_lower:
                            continue
                            
                        # ФИЛЬТР 2: Математический фильтр пикселей (Apple пишет их в URL)
                        res_match = re.search(r'/(\d+)x(\d+)[a-zA-Z]*\.', s)
                        if res_match:
                            w, h = int(res_match.group(1)), int(res_match.group(2))
                            if w == h and w != 0: continue  # Квадрат = иконка
                            if h == 0 and w < 300: continue # Мелкие элементы
                                
                        s_jpg = s.replace('.webp', '.jpg').replace('w.webp', 'bb.jpg').replace('w.png', 'bb.png')
                        
                        # ФИЛЬТР 3: Убеждаемся, что мы не скачали иконку самого приложения
                        if icon_url and s_jpg.split('/')[-1] == icon_url.split('/')[-1]:
                            continue
                            
                        if s_jpg not in clean_screens:
                            clean_screens.append(s_jpg)
                    
                    if clean_screens: 
                        screens = clean_screens
                        
            except Exception as e:
                print(f"⚠️ Ошибка HTML-парсера: {e}")

        # Гарантируем, что в базу лягут только JPG, которые любит Telegram
        screens = [s.replace('.webp', '.jpg') for s in screens]

        return {
            'title': data.get('trackName', ''),
            'summary': subtitle or '', 
            'description': data.get('description', ''),
            'icon': icon_url or '', 
            'headerImage': '',
            'screenshots': screens or []
        }
    else:
        return gp_app(pkg_id, lang=l_code, country=c_code)

def check_apps():
    print(f"--- СТАРТ ПРОВЕРКИ v3.22 (Анти-спам) ({get_minsk_time()}) ---")
    try:
        gc = gspread.service_account_from_dict(service_account_info)
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.get_worksheet(0) 
        headers = worksheet.row_values(1)
        all_rows = worksheet.get_all_values() 
        col_map = {name: i for i, name in enumerate(headers)}
    except Exception as e:
        print(f"❌ Ошибка API Таблиц: {e}"); return

    user_stats = {}
    batched_alerts = {} # 🧺 КОРЗИНКА: Сюда мы будем складывать все изменения, чтобы отправить их разом

    for i, row_values in enumerate(all_rows[1:], start=2):
        row = {headers[j]: (row_values[j] if j < len(row_values) else "") for j in range(len(headers))}
        
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        c_id = str(row.get('chat_id', '')).strip()
        has_owner = bool(c_id and c_id.lower() != 'nan')

        if has_owner:
            user_stats.setdefault(c_id, {'checked': 0, 'updated': 0})
            user_stats[c_id]['checked'] += 1

        full_geo = str(row.get('geo', 'us')).strip()

        try:
            res = fetch_app_data(p_id, full_geo)
            
            old_t = clean_val(row.get('title'))
            old_s = clean_val(row.get('summary'))
            old_d = clean_val(row.get('description'))
            old_icon = clean_val(row.get('icon'))
            old_header = clean_val(row.get('header_image'))

            try: old_scr = json.loads(str(row.get('screenshots', '[]')))
            except: old_scr = []
            try: history = json.loads(str(row.get('history', '[]')))
            except: history = []
            try: current_log = json.loads(str(row.get('check_log', '[]')))
            except: current_log = []

            new_t, new_s, new_d = str(res['title']).strip(), str(res['summary']).strip(), str(res['description']).strip()
            new_icon, new_header, new_scr = str(res['icon']).strip(), str(res.get('headerImage', '')).strip(), res['screenshots']

            is_table_error = (old_t is None or old_s is None or old_d is None)
            is_ios = str(p_id).isdigit()

            changes = []
            if not is_table_error:
                if new_t != old_t: changes.append("Название")
                if new_s != old_s: changes.append("Subtitle" if is_ios else "SD")
                if new_d != old_d: changes.append("Описание" if is_ios else "FD")
                
                if old_icon and new_icon != old_icon: changes.append("Иконка")
                if old_header and new_header != old_header: changes.append("Feature Graphic")
                if new_scr != old_scr: changes.append("Скриншоты")

            if changes:
                print(f"    ⚠️ Изменение в {p_id} ({full_geo})")
                current_log.append({"time": get_minsk_time(), "status": f"🔴 Авто: Изменение ({', '.join(changes)})"})
                
                if has_owner:
                    user_stats[c_id]['updated'] += 1
                    is_rollback = any(new_t == past.get('title') and new_s == past.get('summary') for past in history[-3:])
                    
                    b_key = (p_id, c_id, is_ios)
                    if b_key not in batched_alerts:
                        batched_alerts[b_key] = {'changes': {}, 'texts': {}, 'visuals': [], 'is_rollback': False}
                    
                    batched_alerts[b_key]['changes'][full_geo] = changes
                    if is_rollback: batched_alerts[b_key]['is_rollback'] = True
                    
                    if "Иконка" in changes:
                        batched_alerts[b_key]['visuals'].append({'type': 'diff', 'name': 'Иконка', 'old': old_icon, 'new': new_icon, 'geo': full_geo})
                    if "Feature Graphic" in changes:
                        batched_alerts[b_key]['visuals'].append({'type': 'diff', 'name': 'Feature Graphic', 'old': old_header, 'new': new_header, 'geo': full_geo})
                    if "Скриншоты" in changes and new_scr:
                        batched_alerts[b_key]['visuals'].append({'type': 'screens', 'screens': new_scr, 'geo': full_geo})
                        
                    if any(k in ["Название", "SD", "Subtitle", "FD", "Описание"] for k in changes):
                        batched_alerts[b_key]['texts'][full_geo] = {
                            'old_t': old_t, 'new_t': new_t,
                            'old_s': old_s, 'new_s': new_s,
                            'old_d': old_d, 'new_d': new_d
                        }

                row['title'], row['summary'], row['description'] = new_t, new_s, new_d
                row['icon'], row['header_image'] = new_icon, new_header
                row['screenshots'] = json.dumps(new_scr, ensure_ascii=False)
                history.append({"title": old_t, "summary": old_s, "description": old_d, "time": get_minsk_time()})
                row['history'] = json.dumps(history[-5:], ensure_ascii=False)
                
            elif is_table_error:
                print(f"    🛠 Восстановление данных из-за ошибки в таблице для {p_id}")
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Исправление ошибки"})
                row['title'], row['summary'], row['description'] = new_t, new_s, new_d
                row['icon'], row['header_image'], row['screenshots'] = new_icon, new_header, json.dumps(new_scr, ensure_ascii=False)

            else:
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Без изменений"})
                if not old_icon and new_icon:
                    row['icon'], row['header_image'], row['screenshots'] = new_icon, new_header, json.dumps(new_scr, ensure_ascii=False)

            row['check_log'] = json.dumps(current_log[-5:], ensure_ascii=False)

            new_row_list = [row.get(h, "") for h in headers]
            range_name = f"A{i}:{gspread.utils.rowcol_to_a1(i, len(headers))}"
            worksheet.update(range_name, [new_row_list])
            time.sleep(0.6)

        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")

    # 🚀 ЭТАП 2: РАССЫЛКА ИЗ КОРЗИНКИ (По 1 сообщению на приложение)
    for (pkg_id, c_id, is_ios), data in batched_alerts.items():
        os_icon = "🍎" if is_ios else "🤖"
        msg_prefix = "🔄 АВТО-ОТКАТ" if data['is_rollback'] else "🔔 ИЗМЕНЕНИЯ"
        
        # 1. Единое сводное сообщение
        summary_msg = f"{msg_prefix} {os_icon}\n📦 {pkg_id}\n\n"
        for geo, changes_list in data['changes'].items():
            summary_msg += f"🌍 [{geo.upper()}]: {', '.join(changes_list)}\n"
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": summary_msg})
        
        # 2. Единый текстовый файл со всеми локалями
        if data['texts']:
            full_report = f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ\nПриложение: {pkg_id}\nДата: {get_minsk_time()}\n\n"
            for geo, txt in data['texts'].items():
                full_report += f"Локаль: {geo.upper()}\n{'='*40}\n"
                full_report += f"--- БЫЛО ---\nНазвание: {txt['old_t']}\nSD/Subtitle: {txt['old_s']}\nFD:\n{txt['old_d']}\n\n"
                full_report += f"--- СТАЛО ---\nНазвание: {txt['new_t']}\nSD/Subtitle: {txt['new_s']}\nFD:\n{txt['new_d']}\n\n"
            
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", 
                         data={"chat_id": c_id, "caption": f"📄 Полный отчет: {pkg_id}"}, 
                         files={"document": (f"report_{pkg_id}.txt", full_report.encode('utf-8'))})
                         
        # 3. Рассылка визуалов (Скриншоты, иконки)
        for vis in data['visuals']:
            geo = vis['geo'].upper()
            if vis['type'] == 'diff':
                send_visual_diff(c_id, TOKEN, vis['old'], vis['new'], vis['name'], pkg_id, geo)
            elif vis['type'] == 'screens':
                media = []
                for idx, scr_url in enumerate(vis['screens'][:10]):
                    caption = f"📱 <b>ОБНОВЛЕННЫЕ СКРИНШОТЫ</b> {os_icon}\n📦 {pkg_id} [{geo}]" if idx == 0 else ""
                    media.append({"type": "photo", "media": scr_url, "parse_mode": "HTML", "caption": caption})
                if media:
                    resp = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMediaGroup", json={"chat_id": c_id, "media": media})
                    if resp.status_code != 200:
                        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={
                            "chat_id": c_id, "text": f"⚠️ Скриншоты [{geo}] изменились, но Telegram не смог их отобразить."
                        })
                        
        # 4. Один пакетный ИИ-анализ
        if data['texts']:
            print(f"🧠 Запуск ИИ для {pkg_id} ({len(data['texts'])} локалей)")
            ai_msg = analyze_batched_changes_with_ai(data['texts'])
            clean_ai = ai_msg.replace('*', '').replace('_', '').replace('#', '').replace('`', '')
            full_text = f"🤖 Глобальный ASO-Анализ ({pkg_id}):\n\n{clean_ai}"
            
            limit = 4000
            for chunk_idx in range(0, len(full_text), limit):
                chunk = full_text[chunk_idx:chunk_idx+limit]
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": chunk})
            time.sleep(3)

    for c_id, stats in user_stats.items():
        if stats['updated'] > 0:
            report = (f"⚙️ Системный авто-отчет\n⏰ {get_minsk_time()}\n"
                      f"📦 Проверено: {stats['checked']}\n⚠️ Обновлено: {stats['updated']}")
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()