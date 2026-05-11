import gspread
from google_play_scraper import app
import os
import json
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

TOKEN = os.environ.get("TELEGRAM_TOKEN")
service_account_info = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1jHKbRYt0hJg29RWLIXZ2fL3et_hgzvkhCSxVtTjKV9g/edit"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Настраиваем ИИ, если ключ передан
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# СИСТЕМНЫЙ ПРОМПТ
ASO_PROMPT = """
Ты — ведущий ASO-стратег и эксперт по мобильному маркетингу с глубокой экспертизой в анализе данных. Твоя специализация — реверс-инжиниринг стратегий конкурентов через деконструкцию их метаданных и обновлений.

Тебе будут предоставлены данные о метаданных (Title, Subtitle, Description) конкурента "До" и "После" последних релизов. Твоя задача — провести глубокий анализ изменений и выявить скрытую стратегию роста.

Analysis Algorithm:
1. Semantic Delta: Выяви, какие конкретно ключевые слова были добавлены, какие удалены, а какие перемещены в зоны с большим весом (например, из Description в Title).
2. Intent Analysis: Определи изменение фокуса. Они ушли в "широкие охватные запросы" (Generic) или в "узкие высококонверсионные" (Long-tail)? Сменили ли они акцент с функций на выгоды?
3. Weight Redistribution: Проанализируй, как изменилась плотность ключевых слов. Пытаются ли они ранжироваться по новым категорийным запросам?
4. Hypothesis Generation: На основе изменений сформулируй 3 гипотезы: почему они это сделали и на какой сегмент аудитории теперь нацелены.
5. Impact Prediction: Как это изменение повлияет на их видимость в поиске и конверсию (CR).

Output Format (Presentation Ready):
- Summary: Краткий вывод (1 предложение о векторе стратегии).
- Keyword Migration Table: Таблица [Удалено] | [Добавлено] | [Приоритезировано].
- Strategic Shift: Описание качественного изменения стратегии.
- Threat Level: Насколько это изменение опасно для нашего проекта (High/Medium/Low).
- Action Plan: 3 конкретных шага, которые мы должны предпринять в ответ.

Tone: Профессиональный, аналитический, лаконичный. Избегай общих фраз, используй терминологию ASO.
"""

def get_minsk_time():
    return (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")

def analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d):
    if not GEMINI_API_KEY:
        return "❌ Ключ Gemini API не найден. Анализ не выполнен."
    
    full_prompt = f"{ASO_PROMPT}\n\n--- БЫЛО ---\nTitle: {old_t}\nShort Description: {old_s}\nFull Description: {old_d}\n\n--- СТАЛО ---\nTitle: {new_t}\nShort Description: {new_s}\nFull Description: {new_d}"
    
    # Список моделей (используем базовые имена для лучшей совместимости с API v1)
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
    last_error = ""

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            # Добавляем стандартный конфиг, это часто помогает избежать ошибок версий
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                )
            )
            return response.text
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Модель {model_name} выдала ошибку: {last_error}")
            continue # Пробуем следующую модель
            
    return f"❌ Ошибка ИИ-анализа (модели недоступны). Убедитесь, что в Google AI Studio приняты условия использования. Последняя ошибка: {last_error}"

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
        print(f"❌ Ошибка API: {e}")
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

        if full_geo == "es-419":
            l_code, c_code = "es-419", "MX"
        elif "-" in full_geo:
            l_code = full_geo
            c_code = full_geo.split("-")[1].upper()
        else:
            l_code, c_code = full_geo.lower(), full_geo.upper()

        log_str = str(row.get('check_log', '[]')).strip()
        if not log_str or log_str == 'nan': log_str = '[]'
        try:
            current_log = json.loads(log_str)
        except:
            current_log = []

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
                print(f"    ⚠️ Изменение в {p_id}. Отправляю отчет и генерирую ИИ-анализ...")
                user_stats[c_id]['updated'] += 1
                
                current_log.append({"time": get_minsk_time(), "status": f"🔴 Авто: Изменение ({', '.join(changes)})"})
                
                msg = f"🔔 АВТО-ИЗМЕНЕНИЕ! [{full_geo.upper()}]\n📦 {p_id}\n\nПоля: {', '.join(changes)}\nНазвание: {new_t}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": msg})
                
                report_content = (
                    f"ОТЧЕТ ОБ ИЗМЕНЕНИЯХ (АВТО)\nДата: {get_minsk_time()}\nПриложение: {p_id}\nЛокаль: {full_geo}\n"
                    f"{'='*30}\n\n"
                    f"--- СТАРОЕ НАЗВАНИЕ ---\n{old_t}\n\n--- НОВОЕ НАЗВАНИЕ ---\n{new_t}\n\n"
                    f"{'-'*30}\n"
                    f"--- СТАРЫЙ SD ---\n{old_s}\n\n--- НОВЫЙ SD ---\n{new_s}\n\n"
                    f"{'-'*30}\n"
                    f"--- СТАРЫЙ FD ---\n{old_d}\n\n--- НОВЫЙ FD ---\n{new_d}\n"
                )
                file_path = f"report_{p_id}.txt"
                with open(file_path, "w", encoding="utf-8") as f: f.write(report_content)
                
                with open(file_path, "rb") as f:
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", 
                                 data={"chat_id": c_id, "caption": f"📄 Детальный авто-отчет: {p_id}"}, 
                                 files={"document": f})
                os.remove(file_path)

                ai_analysis = analyze_changes_with_ai(old_t, new_t, old_s, new_s, old_d, new_d)
                ai_msg = f"🤖 **Анализ стратегии от ИИ:**\n\n{ai_analysis}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": ai_msg, "parse_mode": "Markdown"})

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

    for c_id, stats in user_stats.items():
        if stats['checked'] > 0 and stats['updated'] > 0:
            report = (f"⚙️ Системный авто-отчет GitHub\n⏰ {get_minsk_time()}\n"
                      f"📦 Проверено: {stats['checked']}\n⚠️ Найдено и обновлено: {stats['updated']}")
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": c_id, "text": report})

if __name__ == "__main__":
    check_apps()