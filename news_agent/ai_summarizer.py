import os, requests, json, time

GPTUNNEL_API = "https://gptunnel.ru/v1/chat/completions"
MODEL = "deepseek-v3.2"
MAX_RETRIES = 3
SYS_PROMPT = (
    "Ты — опытный аналитик, освещающий политику, технологии и науку. Беспристрастен."
)

# Load custom prompt override if exists
PROMPT_OVERRIDE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompt_custom.txt")
if os.path.exists(PROMPT_OVERRIDE_FILE):
    with open(PROMPT_OVERRIDE_FILE, encoding="utf-8") as f:
        custom = f.read().strip()
        if custom:
            print(f"  Using custom prompt: {custom[:60]}...")
            SYS_PROMPT = custom

USER_PROMPT_TEMPLATE = (
    "Вот подборка новостей из RSS-лент, сгруппированная по событиям.\n"
    "Каждое событие помечено меткой источника (в квадратных скобках), категорией (politics/tech/ai) и ареалом.\n"
    "{news_block}\n"
    "Инструкция:\n"
    "{task_scope}"
    "2. Если нет новостей нужной категории — пропусти эту категорию. Не придумывай и не дозаполняй её другими категориями.\n"
    "3. Для каждого события используй ТОЛЬКО факты из предоставленных новостей. Каждый блок «=== Событие N ===» во входном списке — это ОДНА отдельная новость (в конце блока могут быть ссылки на несколько источников об одном и том же). Строго запрещено:\n"
    "   - выдумывать события или факты, которых нет в списке: запрещено использовать свои знания вне списка, додумывать детали, даты, места, цифры;\n"
    "   - объединять несколько разных новостей в одно событие. Если у новостей разные суть, места или объекты — это РАЗНЫЕ события, включай их отдельно. Не смешивай выдержки из разных блоков «=== Событие N ===» в одном поле summary;\n"
    "   - приписывать новости факты, регион или ссылки из другой новости (например, нельзя к новости о России добавить факт про Ливан и ссылку на ливанский источник);\n"
    "   - переносить в summary то, чего нет в самой новости (даже если это соседняя новость в списке).\n"
    "   Если внутри одного блока «=== Событие N ===» оказалось несколько независимых новостей — РАЗДЕЛИ его на несколько отдельных событий, каждое со своими ссылками. Объединять соседние блоки «=== Событие N ===» в одно событие — запрещено.\n"
    "4. Сверься со списком ранее опубликованных событий (если есть). Если событие уже было в прошлом выпуске и нет новых важных подробностей — пропусти его. Если есть существенное развитие — включи, укажи это.\n"
    "5. Категорически НЕ включай маркетингово-рекламные новости о потребительских гаджетах, особенно смартфонах. Это НЕ новости, а реклама. Всегда пропускай (даже если тема связана с tech/ai):\n"
    "   - анонсы и презентации новых моделей смартфонов/планшетов/ноутбуков («представлен iPhone 17», «Samsung представила Galaxy S26»);\n"
    "   - новости о прохождении тестов, бенчмарков, скорости, производительности гаджетов («смартфон набрал X баллов в AnTuTu», «результаты Geekbench», «новый чип быстрее»);\n"
    "   - новости о новом дизайне, внешнем виде, характеристиках, комплектации конкретной модели;\n"
    "   - даты начала продаж, предзаказы, бронирования, «поступил в продажу», «цена в России»;\n"
    "   - слухи/утечки о ещё не вышедших устройствах;\n"
    "   - новости-«ожидания», прогнозы и обсуждения будущих анонсов гаджетов («ожидания от запуска Apple/iPhone», «что представит Apple в сентябре», «все утечки о флагмане»).\n"
    "   Исключения: (1) в категории 'ai' допустима ОДНА такая новость, только если это единственная значимая новость об ИИ за день; (2) в категории 'photo' маркетинговые новости допустимы без ограничений; (3) если речь о массовом индустриальном событии (например закрытие завода, массовые увольнения, санкции, банкротство производителя) — это можно включить в 'tech'.\n"
    "6. В поле area укажи ареал события.\n"
    "7. Для каждого события напиши краткую суть (2-3 предложения) только на русском (поле summary).\n"
    "8. Для каждого события обязательно укажи ссылки на источники (только из списка выше).\n"
    "9. В поле category укажи категорию, которая ТОЧНО соответствует содержанию новости. По умолчанию бери категорию, указанную в скобках рядом с новостью во входном списке, и меняй её только если она явно ошибочна:\n"
    "   - 'politics' — политика, решения властей, конфликты, общество;\n"
    "   - 'energy' — ТОЛЬКО энергетика: нефть, газ, уголь, электроэнергия, АЭС, возобновляемые источники, энергосети, цены на энергоносители. Наука о космосе/физике/климате — это НЕ energy;\n"
    "   - 'tech' — технологии и наука: космос, физика, биология, медицина, экология, климат, промышленность, техника;\n"
    "   - 'ai' — ТОЛЬКО об искусственном интеллекте: нейросети, ИИ-модели, ИИ-продукты, применение ИИ. Обычное научное исследование — это НЕ ai;\n"
    "   - 'finance' — финансы и экономика: банки, рынки, валюта, экономические показатели;\n"
    "   - 'photo' — фотография: фотоиндустрия, фотографы, камеры, выставки, фотоконкурсы.\n"
    "10. Для политических событий (category='politics') в поле perspective напиши на русском, как событие может оцениваться разными политическими силами; для остальных категорий оставь пустым.\n"
    "11. Поле perspective_type: 'from_source', 'assumed', 'unclear' или пустая строка.\n"
    "{history_block}"
)


def get_system_prompt():
    prompt = USER_PROMPT_TEMPLATE.replace("{news_block}", "<новости из RSS>").replace("{history_block}", "<история предыдущих выпусков>")
    return "Системная роль: " + SYS_PROMPT + "\n\nПромт пользователя:\n" + prompt


def _build_news_block(clusters, max_per=5):
    news_block = ""
    for idx, cluster in enumerate(clusters, 1):
        area = ""
        for a in cluster:
            if a.get("area"):
                area = a["area"]
                break
        news_block += f"\n=== Событие {idx} ===\n"
        for a in cluster[:max_per]:
            kw = a.get("keywords", [])
            kw_str = f" [ключевые слова: {', '.join(kw[:4])}]" if kw else ""
            cat = a.get("category", "politics")
            news_block += (
                f"[{a['region_label']}] ({cat}) {a['title']}{kw_str}\n"
                f"  Ареал: {area} | Источник: {a['source_name']} — {a['link']}\n"
                f"  Дата: {a.get('published', 'неизвестно')}\n"
            )
    return news_block


def _build_payload(news_block, history_block, task_scope):
    prompt = USER_PROMPT_TEMPLATE.format(news_block=news_block, history_block=history_block, task_scope=task_scope)
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "tools": [{
            "type": "function",
            "function": {
                "name": "report_news",
                "description": "Сообщить важнейшие события (политика, ИИ, технологии, финансы)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title_ru": {
                                        "type": "string",
                                        "description": "Заголовок на русском"
                                    },
                                    "title_en": {
                                        "type": "string",
                                        "description": "Заголовок на английском"
                                    },
                                    "date": {
                                        "type": "string",
                                        "description": "Дата события"
                                    },
                                    "summary": {
                                        "type": "string",
                                        "description": "Суть на русском, 2-3 предложения"
                                    },
                                    "category": {
                                        "type": "string",
                                        "enum": ["politics", "ai", "tech", "energy", "finance", "photo"],
                                        "description": "Категория: politics, energy, ai, tech, finance, photo"
                                    },
                                    "area": {
                                        "type": "string",
                                        "enum": ["Россия", "Северная и Центральная Америка", "Южная Америка", "Европа", "Ближний Восток", "Дальний Восток", "Южная и Юго-Восточная Азия", "Океания и Австралия", "Африка", "Мир"],
                                        "description": "Ареал, откуда событие"
                                    },
                                    "perspective": {
                                        "type": "string",
                                        "description": "Для politics: как оценивается разными политическими силами. Для ai/tech/finance: оставь пустым."
                                    },
                                    "perspective_type": {
                                        "type": "string",
                                        "enum": ["from_source", "assumed", "unclear", ""]
                                    },
                                    "sources": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Названия источников"
                                    },
                                    "links": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Ссылки на источники"
                                    },
                                    "is_development": {
                                        "type": "boolean",
                                        "description": "True если это развитие ранее освещённого события"
                                    }
                                },
                                "required": ["title_ru", "title_en", "date", "summary",
                                             "category", "area", "sources", "links"]
                            }
                        }
                    },
                    "required": ["events"]
                }
            }
        }],
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": 16384
    }


def _history_block(history):
    history_block = ""
    if history:
        history_block = "\n\n=== Ранее опубликованные события ===\n"
        for ev in history[-10:]:
            history_block += (
                f"- {ev.get('title_ru', '')} ({ev.get('date', '')})\n"
                f"  Первый раз: {ev.get('first_reported', '')}\n"
            )
    return history_block


def _call_ai(payload, api_key):
    resp = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(GPTUNNEL_API, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }, json=payload, timeout=300)
            if resp.status_code == 200:
                break
            print(f"  [AI ERROR] attempt {attempt+1}: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            print(f"  [AI ERROR] attempt {attempt+1}: {e}")
        if attempt < MAX_RETRIES - 1:
            wait = 10 * (attempt + 1)
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)
    else:
        return None, None

    resp.encoding = "utf-8"
    data = resp.json()
    usage = data.get("usage", {})
    total_cost = usage.get("total_cost", 0)
    total_tokens = usage.get("total_tokens", 0)
    print(f"  AI: {usage.get('total_tokens', 0)} tokens, cost {total_cost}")

    msg = data["choices"][0]["message"]
    if msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            if tc["function"]["name"] == "report_news":
                try:
                    events = json.loads(tc["function"]["arguments"]).get("events", [])
                except json.JSONDecodeError:
                    args_raw = tc["function"]["arguments"]
                    fixed = args_raw.rsplit("}", 1)[0] + "}]}"
                    try:
                        events = json.loads(fixed).get("events", [])
                    except Exception:
                        print(f"  AI: обрезанный JSON ({len(args_raw)} символов), fallback")
                        events = []
                print(f"  AI: {len(events)} событий")
                return events, {"tokens": total_tokens, "cost": total_cost}

    text = msg.get("content", "")
    if text:
        import re
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                arr = json.loads(match.group())
                if arr and isinstance(arr, list):
                    events = [e for e in arr if isinstance(e, dict) and e.get("title_ru")]
                    if events:
                        print(f"  AI (fallback): {len(events)} событий из текста")
                        return events, {"tokens": total_tokens, "cost": total_cost}
            except json.JSONDecodeError:
                pass
        print(f"  AI: модель вернула текст ({len(text)} символов), tool_calls не обнаружен")

    return None, None


def summarize_news(clusters, api_key, history=None):
    areas = ["Россия", "Северная и Центральная Америка", "Южная Америка", "Европа",
             "Ближний Восток", "Дальний Восток", "Южная и Юго-Восточная Азия",
             "Океания и Австралия", "Африка", "Мир"]

    by_area = {}
    for c in clusters:
        area = ""
        for a in c:
            if a.get("area"):
                area = a["area"]
                break
        area = area or "Мир"
        by_area.setdefault(area, []).append(c)

    all_events = []
    total_tokens = 0
    total_cost = 0.0

    for area in areas:
        cls = by_area.get(area, [])
        if not cls:
            continue
        determine_area = ""
        for a in cls[0]:
            if a.get("area"):
                determine_area = a["area"]
                break
        if area == "Мир":
            task_scope = (
                "1. Выбери из представленных новостей:\n"
                "   - 1 финансовое событие (category='finance') — глобальные финансы и экономика;\n"
                "   - 1 событие о фотографии (category='photo') — фотоиндустрия, фотографы, камеры, выставки;\n"
            )
        else:
            task_scope = (
                f"1. Выбери из новостей ареала '{area}' (все события ниже относятся к этому ареалу):\n"
                "   - 3 политических события (category='politics');\n"
                "   - 1 событие об энергетике (category='energy') — нефть, газ, электроэнергия, атомная энергетика, возобновляемые источники, энергетическая инфраструктура;\n"
                "   - 1 технологическое событие на любую тему (category='tech'), НО без рекламных новостей о гаджетах;\n"
                "   - 1 событие об искусственном интеллекте (category='ai'), если таковое есть.\n"
                "   Если каких-то из этих категорий в новостях нет — пропусти их.\n"
            )
        news_block = _build_news_block(cls, max_per=5)
        hb = _history_block(history)
        payload = _build_payload(news_block, hb, task_scope)
        events, usage = _call_ai(payload, api_key)
        if events:
            for ev in events:
                if not ev.get("area") and determine_area:
                    ev["area"] = determine_area
            all_events.extend(events)
        if usage:
            total_tokens += usage.get("tokens", 0)
            total_cost += usage.get("cost", 0)

    print(f"  Total AI: {len(all_events)} событий, {total_tokens} tokens, cost {total_cost:.4f}")
    return all_events, {"tokens": total_tokens, "cost": total_cost}
