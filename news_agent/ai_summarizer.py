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
    "Каждое событие помечено меткой источника (в квадратных скобках) и списком ключевых слов.\n"
    "{news_block}\n"
    "Инструкция:\n"
    "1. Выбери из подборки события, которые дают целостную картину дня по следующим темам. Это группы новостей выпуска:\n"
    "   • «Технологический рост мира» (category='tech') — где в мире что-то создаётся и развивается. Наибольший приоритет — энергетика: новые энерготехнологии и энергоинфраструктура (АЭС, возобновляемые источники, электроэнергетика, добыча и транспортировка энергии). Затем — новое промышленное производство, добыча полезных ископаемых, сельское хозяйство, медицина, космос и значимые научные результаты.\n"
    "   • «Искусственный интеллект» (category='ai') — события, где ГЛАВНЫЙ предмет — технология ИИ: нейросети, ИИ-модели, ИИ-продукты, государственные и корпоративные решения об ИИ. Если ИИ лишь упоминается вскользь, а суть новости в другом — это другая группа.\n"
    "   • «Жизнь людей» (category='life') — где и как меняются условия жизни людей в лучшую или худшую сторону: цены, доходы, работа, социальная политика, здравоохранение, катастрофы и природные явления, экологические последствия, влияние конфликтов на мирное население.\n"
    "   • «Конфликты и их суть» (category='conflicts') — где конфликт назревает, обостряется или идёт: события, отражающие конфликт, его причина и предмет. События важнее заявлений — заявления не включай (единственное заявление дня выносится отдельной позицией п.2). Слова значимы, когда превращаются в действие: закон, указ, санкции, судебное решение, военная операция, договор.\n"
    "   • «Экономическая база стран» (category='economy') — на чём держится экономика (ресурсы, промышленность, торговля, финансы, бюджет), что в ней меняется, кто усиливается, кто ослабевает. Это макроэкономические сдвиги, а не котировки отдельных бумаг.\n"
    "   • «Внутренняя и внешняя политика» (category='politics') — как страны решают внутренние проблемы и какие серьёзные шаги делают наружу: реформы и законы, крупные решения, выборы и их последствия, тенденции международных отношений (реальные действия, а не риторика).\n"
    "2. Дополнительные одиночные позиции, по одной, только если есть по-настоящему достойное:\n"
    "   • «Главное политическое заявление дня» (category='statement') — не более 1: самое громкое политическое заявление дня. Это ЕДИНСТВЕННОЕ заявление в выпуске — другие заявления не включай ни в какую группу.\n"
    "   • культура (category='culture') — искусство, музеи, кино, музыка, литература, театр, фестивали;\n"
    "   • фотография (category='photo') — фотоиндустрия, фотографы, камеры, выставки;\n"
    "   • экология (category='ecology') — климат, загрязнение, отходы, природа, биоразнообразие (если событие подлинно значимо и не дублирует «Жизнь людей»).\n"
    "3. Количество. Всего в выпуске 10–20 событий. По каждой основной группе из п.1 — от 1 до 4 событий; если за день по теме нет ничего стоящего — допустимо 0, не дозаполняй натянутыми новостями. Географический баланс внутри каждой группы — по возможности: 1–2 события из России, 1 о крупной стране (не Россия), 1 о некрупной стране; если по некрупным странам нет ничего стоящего, этот слот можно занять Россией или крупной страной. Если набралось больше 20 — отбрось наименее значимые, начиная с низовых позиций приоритетов п.1.\n"
    "4. Избегай однообразия: если в выпуске уже есть событие крупного игрока (Иран, США, Китай и т.п.), следующее выбирай о другом действии или другой стране, а не продолжение словесной перестрелки того же участника.\n"
    "5. Для каждого события используй ТОЛЬКО факты из предоставленных новостей. Каждый блок «=== Событие N ===» во входном списке — это ОДНА отдельная новость (в конце блока могут быть ссылки на несколько источников об одном и том же). Строго запрещено:\n"
    "   - выдумывать события или факты, которых нет в списке: запрещено использовать свои знания вне списка, додумывать детали, даты, места, цифры;\n"
    "   - объединять несколько разных новостей в одно событие. Если у новостей разные суть, места или объекты — это РАЗНЫЕ события, включай их отдельно. Не смешивай выдержки из разных блоков «=== Событие N ===» в одном summary;\n"
    "   - приписывать новости факты, регион или ссылки из другой новости;\n"
    "   - переносить в summary то, чего нет в самой новости.\n"
    "   Если внутри одного блока «=== Событие N ===» оказалось несколько независимых новостей — РАЗДЕЛИ его на несколько отдельных событий, каждое со своими ссылками. Объединять соседние блоки «=== Событие N ===» в одно событие — запрещено.\n"
    "6. Категорически НЕ включай маркетингово-рекламные новости о потребительских гаджетах, особенно смартфонах. Это реклама, а не новость. Всегда пропускай (даже если тема связана с tech/ai): анонсы и презентации новых моделей смартфонов/планшетов/ноутбуков; тесты, бенчмарки, скорость и производительность конкретных устройств; дизайн, характеристики, комплектации конкретной модели; даты продаж, предзаказы, «поступил в продажу», «цена в России»; слухи и утечки о не вышедших устройствах; новости-«ожидания» и прогнозы будущих анонсов; объёмы спроса, продаж и цены конкретной модели («спрос вырос на 310%», «рекордные продажи», «модель X стала хитом»).\n"
    "   Исключения: (1) в группе «Искусственный интеллект» допустима ОДНА такая новость, только если это единственная значимая новость об ИИ за день; (2) в группе «Фотография» рекламные новости допустимы без ограничений; (3) массовые индустриальные события (закрытие завода, массовые увольнения, санкции, банкротство производителя) допустимы в «Технологическом росте мира».\n"
    "7. Сверься со списком ранее опубликованных событий (если есть). Если событие уже было в прошлом выпуске и нет новых важных подробностей — пропусти его. Если есть существенное развитие — включи и укажи это.\n"
    "8. Поля каждого события: title_ru — заголовок на русском; title_en — заголовок на английском (как в источнике); date — дата события; summary — суть на русском, 2-3 предложения; category — группа (tech, ai, life, conflicts, economy, politics, statement, culture, photo, ecology); region — страна или регион, где событие произошло или кого затрагивает (например: 'США', 'Азербайджан', 'Европа', 'Ближний Восток'; 'Мир' — для глобального события). Регион определяй по содержанию, а не по ленте-источнику; sources — названия источников (только из списка выше); links — ссылки (только из списка выше); perspective — для категорий conflicts и politics: как событие может оцениваться разными сторонами, для остальных — пусто; perspective_type — 'from_source', 'assumed', 'unclear' или пустая строка; is_development — true, если это развитие ранее освещённого события.\n"
    "9. Критично: ОДНО событие = ОДНА новость = ОДИН заголовок = ОДНО summary со своими ссылками. Нельзя в одном title_ru или summary упоминать факты из разных блоков «=== Событие N ===» (никаких «X и Y», «одновременно также Z»).\n"
    "10. Верни события, упорядоченные по группам в этом порядке: tech, ai, life, conflicts, economy, politics, statement, culture, photo, ecology.\n"
    "{history_block}"
)

CAT_HINTS = {
    "politics": "политика",
    "tech": "технологии",
    "ai": "ИИ",
    "energy": "энергетика",
    "finance": "экономика",
    "photo": "фото",
    "culture": "культура",
    "ecology": "экология",
}


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
            cat = CAT_HINTS.get(a.get("category", "politics"), a.get("category", "politics"))
            news_block += (
                f"[{a['region_label']}] ({cat}) {a['title']}{kw_str}\n"
                f"  Регион: {area} | Источник: {a['source_name']} — {a['link']}\n"
                f"  Дата: {a.get('published', 'неизвестно')}\n"
            )
    return news_block


def _build_payload(news_block, history_block):
    prompt = USER_PROMPT_TEMPLATE.format(news_block=news_block, history_block=history_block)
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
                "description": "Сообщить важнейшие события дня по выбранным группам",
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
                                        "enum": ["tech", "ai", "life", "conflicts", "economy", "politics", "statement", "culture", "photo", "ecology"],
                                        "description": "Группа новостей: tech, ai, life, conflicts, economy, politics, statement, culture, photo, ecology"
                                    },
                                    "region": {
                                        "type": "string",
                                        "description": "Страна или регион события, например 'США', 'Азербайджан', 'Европа', 'Мир'"
                                    },
                                    "perspective": {
                                        "type": "string",
                                        "description": "Для conflicts/politics: как оценивается разными сторонами. Для остальных: пусто."
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
                                             "category", "region", "sources", "links"]
                            }
                        }
                    },
                    "required": ["events"]
                }
            }
        }],
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": 8192
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
    p_tokens = usage.get("prompt_tokens", total_tokens)
    c_tokens = usage.get("completion_tokens", 0)
    print(f"  AI: {total_tokens} tokens (in {p_tokens} / out {c_tokens}), cost {total_cost}")

    msg = data["choices"][0]["message"]
    if msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            if tc["function"]["name"] == "report_news":
                try:
                    parsed = json.loads(tc["function"]["arguments"])
                    events = parsed.get("events", []) if isinstance(parsed, dict) else parsed
                except json.JSONDecodeError:
                    args_raw = tc["function"]["arguments"]
                    fixed = args_raw.rsplit("}", 1)[0] + "}]}"
                    try:
                        parsed = json.loads(fixed)
                        events = parsed.get("events", []) if isinstance(parsed, dict) else parsed
                    except Exception:
                        print(f"  AI: обрезанный JSON ({len(args_raw)} символов), fallback")
                        events = []
                if isinstance(events, dict):
                    events = list(events.values())
                events = [e for e in events if isinstance(e, dict) and e.get("title_ru")]
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
    news_block = _build_news_block(clusters, max_per=5)
    hb = _history_block(history)
    payload = _build_payload(news_block, hb)
    events, usage = _call_ai(payload, api_key)
    if not events:
        print("  Total AI: 0 событий")
        return [], usage or {}

    print(f"  Total AI: {len(events)} событий, {usage.get('tokens', 0)} tokens, cost {usage.get('cost', 0):.4f}")
    return events, usage