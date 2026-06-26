import requests, json

GPTUNNEL_API = "https://gptunnel.ru/v1/chat/completions"
MODEL = "qwen3.7-max"
SYS_PROMPT = (
    "Ты — опытный политолог, беспристрастный, не имеющий собственных политических предпочтений."
)

USER_PROMPT_TEMPLATE = (
    "Вот текущая подборка новостей из RSS-лент российских и мировых СМИ:\n"
    "{news_block}\n"
    "Инструкция:\n"
    "1. Выбери до 15 важнейших мировых политических событий и тенденций за последние 7 дней.\n"
    "2. Для каждого события используй ТОЛЬКО факты из предоставленных новостей. "
    "Не придумывай события и не используй свои знания вне этого списка.\n"
    "3. Сверься со списком ранее опубликованных событий (если есть). "
    "Если событие уже было в прошлом выпуске и нет новых важных подробностей — пропусти его. "
    "Если есть существенное развитие — включи, укажи это.\n"
    "4. Если событий больше 10 — выбери 10 самых важных. Если меньше 10 — оставь сколько есть.\n"
    "5. Для каждого события обязательно укажи ссылки на источники (только из списка выше).\n"
    "6. В поле perspective напиши, как событие может оцениваться разными политическими силами "
    "(только если это следует из новостей; если неясно — укажи 'неясно').\n"
    "7. Поле perspective_type: 'from_source' если оценка из источника, "
    "'assumed' если ты её предполагаешь, 'unclear' если неясно.\n"
    "{history_block}"
)


def get_system_prompt():
    return (
        "Системная роль: " + SYS_PROMPT + "\n\n"
        "Промт пользователя:\n" + USER_PROMPT_TEMPLATE.replace("{news_block}", "<новости из RSS>")
            .replace("{history_block}", "<история предыдущих выпусков>")
    )


def summarize_news(clusters, api_key, history=None):
    news_block = ""
    for idx, cluster in enumerate(clusters, 1):
        news_block += f"\n=== Событие {idx} ===\n"
        for a in cluster:
            kw = a.get("keywords", [])
            kw_str = f" [ключевые слова: {', '.join(kw[:4])}]" if kw else ""
            news_block += (
                f"[{a['region_label']}] {a['title']}{kw_str}\n"
                f"  Источник: {a['source_name']} — {a['link']}\n"
                f"  Дата: {a.get('published', 'неизвестно')}\n"
            )

    history_block = ""
    if history:
        history_block = "\n\n=== Ранее опубликованные события ===\n"
        for ev in history[-20:]:
            history_block += (
                f"- {ev.get('title_ru', '')} ({ev.get('date', '')})\n"
                f"  Первый раз: {ev.get('first_reported', '')}\n"
            )

    prompt = USER_PROMPT_TEMPLATE.format(news_block=news_block, history_block=history_block)

    resp = requests.post(GPTUNNEL_API, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }, json={
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "tools": [{
            "type": "function",
            "function": {
                "name": "report_news",
                "description": "Сообщить важнейшие политические события",
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
                                    "perspective": {
                                        "type": "string",
                                        "description": "Как оценивается разными политическими силами"
                                    },
                                    "perspective_type": {
                                        "type": "string",
                                        "enum": ["from_source", "assumed", "unclear"]
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
                                             "perspective", "perspective_type", "sources", "links"]
                            }
                        }
                    },
                    "required": ["events"]
                }
            }
        }],
        "tool_choice": {"type": "function", "function": {"name": "report_news"}},
        "temperature": 0.3,
        "max_tokens": 4000
    }, timeout=120)

    if resp.status_code != 200:
        print(f"  [AI ERROR] {resp.status_code}: {resp.text[:200]}")
        return None, None

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
