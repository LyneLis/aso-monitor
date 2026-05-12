import gspread
from google_play_scraper import app
import os
import json
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

# Настройки окружения
TOKEN = os.environ.get("TELEGRAM_TOKEN")
service_account_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1jHKbRYt0hJg29RWLIXZ2fL3et_hgzvkhCSxVtTjKV9g/edit"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Настраиваем ИИ с использованием REST-транспорта (фикс для GitHub Actions)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY, transport='rest')

# СИСТЕМНЫЙ ПРОМПТ ДЛЯ ASO АНАЛИЗА
ASO_PROMPT = """
Ты — ведущий ASO-стратег и эксперт по мобильному маркетингу с глубокой экспертизой в анализе данных. Твоя специализация — реверс-инжиниринг стратегий конкурентов через деконструкцию их метаданных и обновлений.

Тебе будут предоставлены данные о метаданных (Title, Subtitle, Description) конкурента "До" и "После" последних релизов. Твоя задача — провести глубокий анализ изменений и выявить скрытую стратегию роста.

Analysis Algorithm:
1. Semantic Delta: Выяви, какие конкретно ключевые слова были добавлены, какие удалены, а какие перемещены в зоны с большим весом.
2. Intent Analysis: Определи изменение фокуса (Generic vs Long-tail, функции vs выгоды).
3. Weight Redistribution: Проанализируй плотность ключевых слов.
4. Hypothesis Generation: Сформулируй 3 гипотезы о целях изменений.
5. Impact Prediction: Прогноз влияния на видимость и CR.

Output Format:
- Summary: Краткий вывод (1 предложение о векторе стратегии).
- Keywords Migration:
  Удалено: список через запятую
  Добавлено: список через запятую
  Приоритезировано: список через запятую
- Strategic Shift: Описание изменений.
- Threat Level: High/Medium/Low.
- Action Plan: 3 конкретных шага.

Tone: Профессиональный, аналитический, лаконичный.
"""

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

def analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d):
    if not GEMINI_API_KEY:
        return "❌ Ключ Gemini API не найден."
    
    # Собираем промпт
    full_prompt = (
        f"{ASO_PROMPT}\n\n"
        f"--- БЫЛО ---\nTitle: {old_t}\nShort Description: {old_s}\nFull Description: {old_d}\n\n"
        f"--- СТАЛО ---\nTitle: {new_t}\nShort Description: {new_s}\nFull Description: {new_d}"
    )

    # Динамический поиск работающей модели (Актуально для 2026 года)
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
    except Exception as e:
        print(f"⚠️ Не удалось получить список моделей: {e}")

    # Приоритетный список моделей (от новых к старым)
    priority_list = [
        'models/gemini-3-flash', 
        'models/gemini-1.5-flash', 
        'models/gemini-1.5-pro'
    ]
    
    # Формируем финальную очередь проверки
    models_to_try = [m for m in priority_list if m in available_models]
    if not models_to_try: # Если список пуст, берем первую доступную из системы
        models_to_try = available_models[:2] if available_models else priority_list

    last_error = ""
    for model_name in models_to_try:
        try:
            print(f"🤖 Пробую модель: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(full_prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Ошибка на {model_name}: {last_error}")
            continue 
            
    return f"❌ Ошибка ИИ-анализа: {last_error}. Проверьте доступность моделей в Google AI Studio."

def check_apps():
    print(f"--- СТАРТ ПРОВЕРКИ С АВТОЗАПИСЬЮ И ИИ-АНАЛИЗОМ ({get_minsk_time()}) ---")
    
    try:
        gc = gspread.service_account_from_dict(service_account_info)
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.get_worksheet(0) 
        
        headers = worksheet.row_values(1)
        col_map = {name: i+1 for i, name in enumerate(headers)}
        
        data = worksheet.get_all_records()
        print(f"✅ Таблица загружена. Строк: {len(data)}")
    except Exception as e:
        print(f"❌ Ошибка API Таблиц: {e}")
        return

    user_stats = {}

    for i, row in enumerate(data):
        row_number = i + 2
        p_id = str(row.get('package_id', '')).strip()
        if not p_id or p_id == 'nan': continue
        
        full_geo = str(row.get('geo', 'us')).strip()
        c_id = str(row.get('chat_id', '')).strip()
        
        if c_id not in user_stats:
            user_stats[c_id] = {'checked': 0, 'updated': 0}
        user_stats[c_id]['checked'] += 1

        # Логика локалей (Мексика для es-419 и полные коды для остальных)
        if full_geo == "es-419":
            l_code, c_code = "es-419", "MX"
        elif "-" in full_geo:
            l_code = full_geo
            c_code = full_geo.split("-")[1].upper()
        else:
            l_code, c_code = full_geo.lower(), full_geo.upper()

        # Загрузка логов
        log_str = str(row.get('check_log', '[]')).strip()
        if not log_str or log_str == 'nan': log_str = '[]'
        try: current_log = json.loads(log_str)
        except: current_log = []

        try:
            res = app(p_id, lang=l_code, country=c_code)
            
            old_t = str(row.get('title', '')).strip()
            old_s = str(row.get('summary', '')).strip()
            old_d = str(row.get('description', '')).strip()
            
            new_t = str(res['title']).strip()
            new_s = str(res['summary']).strip()
            new_d = str(res['description']).strip()

            changes = []
            if new_t != old_t: changes.append("Название")
            if new_s != old_s: changes.append("SD")
            if new_d != old_d: changes.append("FD")

            if changes:
                print(f"    ⚠️ Изменение в {p_id}. Запуск ИИ...")
                user_stats[c_id]['updated'] += 1
                current_log.append({"time": get_minsk_time(), "status": f"🔴 Авто: Изменение ({', '.join(changes)})"})
                
                # 1. Telegram: Уведомление
                msg = f"🔔 АВТО-ИЗМЕНЕНИЕ! [{full_geo.upper()}]\n📦 {p_id}\n\nПоля: {', '.join(changes)}\nНазвание: {new_t}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": msg})
                
                # 2. Telegram: Файл отчета
                report_content = (
                    f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ\nДата: {get_minsk_time()}\nПриложение: {p_id}\nЛокаль: {full_geo}\n"
                    f"{'='*30}\n\n--- СТАРОЕ НАЗВАНИЕ ---\n{old_t}\n\n--- НОВОЕ НАЗВАНИЕ ---\n{new_t}\n\n"
                    f"{'-'*30}\n--- СТАРЫЙ SD ---\n{old_s}\n\n--- НОВЫЙ SD ---\n{new_s}\n\n"
                    f"{'-'*30}\n--- СТАРЫЙ FD ---\n{old_d}\n\n--- НОВЫЙ FD ---\n{new_d}\n"
                )
                file_path = f"report_{p_id}.txt"
                with open(file_path, "w", encoding="utf-8") as f: f.write(report_content)
                with open(file_path, "rb") as f:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", 
                                 data={"chat_id": c_id, "caption": f"📄 Детальный отчет: {p_id}"}, files={"document": f})
                os.remove(file_path)

                # 3. Telegram: Анализ ИИ
                ai_analysis = analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d)
                ai_msg = f"🤖 **Анализ стратегии от ИИ:**\n\n{ai_analysis}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                              data={"chat_id": c_id, "text": ai_msg, "parse_mode": "Markdown"})

                # 4. Обновление таблицы
                if "title" in col_map: worksheet.update_cell(row_number, col_map["title"], new_t)
                if "summary" in col_map: worksheet.update_cell(row_number, col_map["summary"], new_s)
                if "description" in col_map: worksheet.update_cell(row_number, col_map["description"], new_d)
                
            else:
                print(f"    ✅ {p_id}: Без изменений.")
                current_log.append({"time": get_minsk_time(), "status": "🟢 Авто: Без изменений"})

            if "check_log" in col_map:
                current_log = current_log[-5:]
                worksheet.update_cell(row_number, col_map["check_log"], json.dumps(current_log, ensure_ascii=False))

        except Exception as e:
            print(f"    ❌ Ошибка {p_id}: {e}")
            current_log.append({"time": get_minsk_time(), "status": f"❌ Авто: Ошибка стора"})
            if "check_log" in col_map:
                current_log = current_log[-5:]
                worksheet.update_cell(row_number, col_map["check_log"], json.dumps(current_log, ensure_ascii=False))

    # Финальное резюме
    for c_id, stats in user_stats.items():
        if stats['checked'] > 0 and stats['updated'] > 0:
            report = (f"⚙️ Системный авто-отчет\n⏰ {get_minsk_time()}\n"
                      f"📦 Проверено: {stats['checked']}\n⚠️ Обновлено: {stats['updated']}")
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()