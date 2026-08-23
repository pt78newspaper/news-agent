import os, requests, json, time

GPTUNNEL_API = "https://gptunnel.ru/v1/chat/completions"
MODEL = "deepseek-v4-pro"
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
    "Вот текущая подборка новостей из RSS-лент:\n"
    "{news_block}\n"
    "Инструкция:\n"
    "1. Выбери ровно 11 событий: 5 политических (category='politics'), 2 об ИИ (category='ai'), 3 о технологиях/науке/промышленности (category='tech'), 1 из мира финансов и экономики (category='finance'). Это обязательное требование — 11 событий, распределение по категориям строгое.\n"
    "2. Для каждого события используй ТОЛЬКО факты из предоставленных новостей. "
    "Не придумывай события и не используй свои знания вне этого списка.\n"
    "3. Сверься со списком ранее опубликованных событий (если есть). "
    "Если событие уже было в прошлом выпуске и нет новых важных подробностей — пропусти его. "
    "Если есть существенное развитие — включи, укажи это.\n"
    "4. Если нужного количества событий какой-то категории нет в новостях — оставь сколько есть, но общее число 11 должно сохраниться за счёт других категорий.\n"
    "5. Для каждого события напиши краткую суть (2-3 предложения) на английском (поле summary_en) и на русском (поле summary).\n"
    "6. Для каждого события обязательно укажи ссылки на источники (только из списка выше).\n"
    "7. В поле category укажи 'politics' для политических событий, 'ai' для новостей об ИИ, 'tech' для технологий/науки, 'finance' для финансов и экономики.\n"
    "8. Для политических событий (category='politics') в поле perspective напиши, как событие может оцениваться разными политическими силами; для остальных категорий оставь пустым.\n"
    "9. Поле perspective_type: 'from_source', 'assumed', 'unclear' или пустая строка.\n"
    "{history_block}"
)


def get_system_prompt():
    prompt = USER_PROMPT_TEMPLATE.replace("{news_block}", "<новости из RSS>").replace("{history_block}", "<история предыдущих выпусков>")
    return "Системная роль: " + SYS_PROMPT + "\n\nПромт пользователя:\n" + prompt


def summarize_news(clusters, api_key, history=None):
    news_block = ""
    for idx, cluster in enumerate(clusters, 1):
        news_block += f"\n=== Событие {idx} ===\n"
        for a in cluster:
            kw = a.get("keywords", [])
            kw_str = f" [ключевые слова: {', '.join(kw[:4])}]" if kw else ""
            cat = a.get("category", "politics")
            news_block += (
                f"[{a['region_label']}] ({cat}) {a['title']}{kw_str}\n"
                f"  Источник: {a['source_name']} — {a['link']}\n"
                f"  Дата: {a.get('published', 'неизвестно')}\n"
            )

    history_block = ""
    if history:
        history_block = "\n\n=== Ранее опубликованные события ===\n"
        for ev in history[-10:]:
            history_block += (
                f"- {ev.get('title_ru', '')} ({ev.get('date', '')})\n"
                f"  Первый раз: {ev.get('first_reported', '')}\n"
            )

    prompt = USER_PROMPT_TEMPLATE.format(news_block=news_block, history_block=history_block)

    payload = {
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
                                    "summary_en": {
                                        "type": "string",
                                        "description": "Summary in English, 2-3 sentences"
                                    },
                                    "summary": {
                                        "type": "string",
                                        "description": "Суть на русском, 2-3 предложения"
                                    },
                                    "category": {
                                        "type": "string",
                                        "enum": ["politics", "ai", "tech", "finance"],
                                        "description": "Категория: politics, ai, tech, finance"
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
                                "required": ["title_ru", "title_en", "date", "summary_en", "summary",
                                             "category", "sources", "links"]
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
                events = json.loads(tc["function"]["arguments"]).get("events", [])
                print(f"  AI: {len(events)} событий")
                return events, {"tokens": total_tokens, "cost": total_cost}
    return None, None
