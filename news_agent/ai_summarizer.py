import os, requests, json, time

GPTUNNEL_API = "https://gptunnel.ru/v1/chat/completions"
MODEL = "deepseek-v4-pro"
MAX_RETRIES = 3
SYS_PROMPT = (
    "Ð¢Ñ‹ â€” Ð¾Ð¿Ñ‹Ñ‚Ð½Ñ‹Ð¹ Ð°Ð½Ð°Ð»Ð¸Ñ‚Ð¸Ðº, Ð¾ÑÐ²ÐµÑ‰Ð°ÑŽÑ‰Ð¸Ð¹ Ð¿Ð¾Ð»Ð¸Ñ‚Ð¸ÐºÑƒ, Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¸ Ð¸ Ð½Ð°ÑƒÐºÑƒ. Ð‘ÐµÑÐ¿Ñ€Ð¸ÑÑ‚Ñ€Ð°ÑÑ‚ÐµÐ½."
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
    "Ð’Ð¾Ñ‚ Ñ‚ÐµÐºÑƒÑ‰Ð°Ñ Ð¿Ð¾Ð´Ð±Ð¾Ñ€ÐºÐ° Ð½Ð¾Ð²Ð¾ÑÑ‚ÐµÐ¹ Ð¸Ð· RSS-Ð»ÐµÐ½Ñ‚:\n"
    "{news_block}\n"
    "Ð˜Ð½ÑÑ‚Ñ€ÑƒÐºÑ†Ð¸Ñ:\n"
    "1. Ð’Ñ‹Ð±ÐµÑ€Ð¸ Ñ€Ð¾Ð²Ð½Ð¾ 7 ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹: 5 Ð¿Ð¾Ð»Ð¸Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸Ñ… (category='politics'), 1 Ð¾Ð± Ð˜Ð˜ (category='ai'), 1 Ð¸Ð· Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¹/Ð½Ð°ÑƒÐºÐ¸/Ð¿Ñ€Ð¾Ð¼Ñ‹ÑˆÐ»ÐµÐ½Ð½Ð¾ÑÑ‚Ð¸ (category='tech'). Ð­Ñ‚Ð¾ Ð¾Ð±ÑÐ·Ð°Ñ‚ÐµÐ»ÑŒÐ½Ð¾Ðµ Ñ‚Ñ€ÐµÐ±Ð¾Ð²Ð°Ð½Ð¸Ðµ â€” 7 ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹, Ñ€Ð°ÑÐ¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ðµ Ð¿Ð¾ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑÐ¼ ÑÑ‚Ñ€Ð¾Ð³Ð¾Ðµ.\n"
    "2. Ð”Ð»Ñ ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ñ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹ Ð¢ÐžÐ›Ð¬ÐšÐž Ñ„Ð°ÐºÑ‚Ñ‹ Ð¸Ð· Ð¿Ñ€ÐµÐ´Ð¾ÑÑ‚Ð°Ð²Ð»ÐµÐ½Ð½Ñ‹Ñ… Ð½Ð¾Ð²Ð¾ÑÑ‚ÐµÐ¹. "
    "ÐÐµ Ð¿Ñ€Ð¸Ð´ÑƒÐ¼Ñ‹Ð²Ð°Ð¹ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ñ Ð¸ Ð½Ðµ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐ¹ ÑÐ²Ð¾Ð¸ Ð·Ð½Ð°Ð½Ð¸Ñ Ð²Ð½Ðµ ÑÑ‚Ð¾Ð³Ð¾ ÑÐ¿Ð¸ÑÐºÐ°.\n"
    "3. Ð¡Ð²ÐµÑ€ÑŒÑÑ ÑÐ¾ ÑÐ¿Ð¸ÑÐºÐ¾Ð¼ Ñ€Ð°Ð½ÐµÐµ Ð¾Ð¿ÑƒÐ±Ð»Ð¸ÐºÐ¾Ð²Ð°Ð½Ð½Ñ‹Ñ… ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹ (ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ). "
    "Ð•ÑÐ»Ð¸ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ðµ ÑƒÐ¶Ðµ Ð±Ñ‹Ð»Ð¾ Ð² Ð¿Ñ€Ð¾ÑˆÐ»Ð¾Ð¼ Ð²Ñ‹Ð¿ÑƒÑÐºÐµ Ð¸ Ð½ÐµÑ‚ Ð½Ð¾Ð²Ñ‹Ñ… Ð²Ð°Ð¶Ð½Ñ‹Ñ… Ð¿Ð¾Ð´Ñ€Ð¾Ð±Ð½Ð¾ÑÑ‚ÐµÐ¹ â€” Ð¿Ñ€Ð¾Ð¿ÑƒÑÑ‚Ð¸ ÐµÐ³Ð¾. "
    "Ð•ÑÐ»Ð¸ ÐµÑÑ‚ÑŒ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÐµÐ½Ð½Ð¾Ðµ Ñ€Ð°Ð·Ð²Ð¸Ñ‚Ð¸Ðµ â€” Ð²ÐºÐ»ÑŽÑ‡Ð¸, ÑƒÐºÐ°Ð¶Ð¸ ÑÑ‚Ð¾.\n"
    "4. Ð•ÑÐ»Ð¸ Ð½ÑƒÐ¶Ð½Ð¾Ð³Ð¾ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð° ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹ ÐºÐ°ÐºÐ¾Ð¹-Ñ‚Ð¾ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸ Ð½ÐµÑ‚ Ð² Ð½Ð¾Ð²Ð¾ÑÑ‚ÑÑ… â€” Ð¾ÑÑ‚Ð°Ð²ÑŒ ÑÐºÐ¾Ð»ÑŒÐºÐ¾ ÐµÑÑ‚ÑŒ, Ð½Ð¾ Ð¾Ð±Ñ‰ÐµÐµ Ñ‡Ð¸ÑÐ»Ð¾ 7 Ð´Ð¾Ð»Ð¶Ð½Ð¾ ÑÐ¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒÑÑ Ð·Ð° ÑÑ‡Ñ‘Ñ‚ Ð´Ñ€ÑƒÐ³Ð¸Ñ… ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¹.\n"
    "5. Ð”Ð»Ñ ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ñ Ð½Ð°Ð¿Ð¸ÑˆÐ¸ ÐºÑ€Ð°Ñ‚ÐºÑƒÑŽ ÑÑƒÑ‚ÑŒ (2-3 Ð¿Ñ€ÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ) Ð½Ð° Ð°Ð½Ð³Ð»Ð¸Ð¹ÑÐºÐ¾Ð¼ (Ð¿Ð¾Ð»Ðµ summary_en) Ð¸ Ð½Ð° Ñ€ÑƒÑÑÐºÐ¾Ð¼ (Ð¿Ð¾Ð»Ðµ summary).\n"
    "6. Ð”Ð»Ñ ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ñ Ð¾Ð±ÑÐ·Ð°Ñ‚ÐµÐ»ÑŒÐ½Ð¾ ÑƒÐºÐ°Ð¶Ð¸ ÑÑÑ‹Ð»ÐºÐ¸ Ð½Ð° Ð¸ÑÑ‚Ð¾Ñ‡Ð½Ð¸ÐºÐ¸ (Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¸Ð· ÑÐ¿Ð¸ÑÐºÐ° Ð²Ñ‹ÑˆÐµ).\n"
    "7. Ð’ Ð¿Ð¾Ð»Ðµ category ÑƒÐºÐ°Ð¶Ð¸ 'politics' Ð´Ð»Ñ Ð¿Ð¾Ð»Ð¸Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸Ñ… ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹, 'ai' Ð´Ð»Ñ Ð½Ð¾Ð²Ð¾ÑÑ‚ÐµÐ¹ Ð¾Ð± Ð˜Ð˜, 'tech' Ð´Ð»Ñ Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¹/Ð½Ð°ÑƒÐºÐ¸.\n"
    "8. Ð”Ð»Ñ Ð¿Ð¾Ð»Ð¸Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸Ñ… ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹ (category='politics') Ð² Ð¿Ð¾Ð»Ðµ perspective Ð½Ð°Ð¿Ð¸ÑˆÐ¸, ÐºÐ°Ðº ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ðµ Ð¼Ð¾Ð¶ÐµÑ‚ Ð¾Ñ†ÐµÐ½Ð¸Ð²Ð°Ñ‚ÑŒÑÑ Ñ€Ð°Ð·Ð½Ñ‹Ð¼Ð¸ Ð¿Ð¾Ð»Ð¸Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸Ð¼Ð¸ ÑÐ¸Ð»Ð°Ð¼Ð¸; Ð´Ð»Ñ tech/ai Ð½Ð¾Ð²Ð¾ÑÑ‚ÐµÐ¹ Ð¾ÑÑ‚Ð°Ð²ÑŒ Ð¿ÑƒÑÑ‚Ñ‹Ð¼.\n"
    "9. ÐŸÐ¾Ð»Ðµ perspective_type: 'from_source', 'assumed', 'unclear' Ð¸Ð»Ð¸ Ð¿ÑƒÑÑ‚Ð°Ñ ÑÑ‚Ñ€Ð¾ÐºÐ°.\n"
    "{history_block}"
)


def get_system_prompt():
    prompt = USER_PROMPT_TEMPLATE.replace("{news_block}", "<Ð½Ð¾Ð²Ð¾ÑÑ‚Ð¸ Ð¸Ð· RSS>").replace("{history_block}", "<Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ñ Ð¿Ñ€ÐµÐ´Ñ‹Ð´ÑƒÑ‰Ð¸Ñ… Ð²Ñ‹Ð¿ÑƒÑÐºÐ¾Ð²>")
    return "Ð¡Ð¸ÑÑ‚ÐµÐ¼Ð½Ð°Ñ Ñ€Ð¾Ð»ÑŒ: " + SYS_PROMPT + "\n\nÐŸÑ€Ð¾Ð¼Ñ‚ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ:\n" + prompt


def summarize_news(clusters, api_key, history=None):
    news_block = ""
    for idx, cluster in enumerate(clusters, 1):
        news_block += f"\n=== Ð¡Ð¾Ð±Ñ‹Ñ‚Ð¸Ðµ {idx} ===\n"
        for a in cluster:
            kw = a.get("keywords", [])
            kw_str = f" [ÐºÐ»ÑŽÑ‡ÐµÐ²Ñ‹Ðµ ÑÐ»Ð¾Ð²Ð°: {', '.join(kw[:4])}]" if kw else ""
            cat = a.get("category", "politics")
            news_block += (
                f"[{a['region_label']}] ({cat}) {a['title']}{kw_str}\n"
                f"  Ð˜ÑÑ‚Ð¾Ñ‡Ð½Ð¸Ðº: {a['source_name']} â€” {a['link']}\n"
                f"  Ð”Ð°Ñ‚Ð°: {a.get('published', 'Ð½ÐµÐ¸Ð·Ð²ÐµÑÑ‚Ð½Ð¾')}\n"
            )

    history_block = ""
    if history:
        history_block = "\n\n=== Ð Ð°Ð½ÐµÐµ Ð¾Ð¿ÑƒÐ±Ð»Ð¸ÐºÐ¾Ð²Ð°Ð½Ð½Ñ‹Ðµ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ñ ===\n"
        for ev in history[-10:]:
            history_block += (
                f"- {ev.get('title_ru', '')} ({ev.get('date', '')})\n"
                f"  ÐŸÐµÑ€Ð²Ñ‹Ð¹ Ñ€Ð°Ð·: {ev.get('first_reported', '')}\n"
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
                "description": "Ð¡Ð¾Ð¾Ð±Ñ‰Ð¸Ñ‚ÑŒ Ð²Ð°Ð¶Ð½ÐµÐ¹ÑˆÐ¸Ðµ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ñ (Ð¿Ð¾Ð»Ð¸Ñ‚Ð¸ÐºÐ°, Ð˜Ð˜, Ñ‚ÐµÑ…Ð½Ð¾Ð»Ð¾Ð³Ð¸Ð¸)",
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
                                        "description": "Ð—Ð°Ð³Ð¾Ð»Ð¾Ð²Ð¾Ðº Ð½Ð° Ñ€ÑƒÑÑÐºÐ¾Ð¼"
                                    },
                                    "title_en": {
                                        "type": "string",
                                        "description": "Ð—Ð°Ð³Ð¾Ð»Ð¾Ð²Ð¾Ðº Ð½Ð° Ð°Ð½Ð³Ð»Ð¸Ð¹ÑÐºÐ¾Ð¼"
                                    },
                                    "date": {
                                        "type": "string",
                                        "description": "Ð”Ð°Ñ‚Ð° ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ñ"
                                    },
                                    "summary_en": {
                                        "type": "string",
                                        "description": "Summary in English, 2-3 sentences"
                                    },
                                    "summary": {
                                        "type": "string",
                                        "description": "Ð¡ÑƒÑ‚ÑŒ Ð½Ð° Ñ€ÑƒÑÑÐºÐ¾Ð¼, 2-3 Ð¿Ñ€ÐµÐ´Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ"
                                    },
                                    "category": {
                                        "type": "string",
                                        "enum": ["politics", "ai", "tech"],
                                        "description": "ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ: politics, ai, tech"
                                    },
                                    "perspective": {
                                        "type": "string",
                                        "description": "Ð”Ð»Ñ politics: ÐºÐ°Ðº Ð¾Ñ†ÐµÐ½Ð¸Ð²Ð°ÐµÑ‚ÑÑ Ñ€Ð°Ð·Ð½Ñ‹Ð¼Ð¸ Ð¿Ð¾Ð»Ð¸Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸Ð¼Ð¸ ÑÐ¸Ð»Ð°Ð¼Ð¸. Ð”Ð»Ñ ai/tech: Ð¾ÑÑ‚Ð°Ð²ÑŒ Ð¿ÑƒÑÑ‚Ñ‹Ð¼."
                                    },
                                    "perspective_type": {
                                        "type": "string",
                                        "enum": ["from_source", "assumed", "unclear", ""]
                                    },
                                    "sources": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "ÐÐ°Ð·Ð²Ð°Ð½Ð¸Ñ Ð¸ÑÑ‚Ð¾Ñ‡Ð½Ð¸ÐºÐ¾Ð²"
                                    },
                                    "links": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Ð¡ÑÑ‹Ð»ÐºÐ¸ Ð½Ð° Ð¸ÑÑ‚Ð¾Ñ‡Ð½Ð¸ÐºÐ¸"
                                    },
                                    "is_development": {
                                        "type": "boolean",
                                        "description": "True ÐµÑÐ»Ð¸ ÑÑ‚Ð¾ Ñ€Ð°Ð·Ð²Ð¸Ñ‚Ð¸Ðµ Ñ€Ð°Ð½ÐµÐµ Ð¾ÑÐ²ÐµÑ‰Ñ‘Ð½Ð½Ð¾Ð³Ð¾ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ñ"
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
                print(f"  AI: {len(events)} ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹")
                return events, {"tokens": total_tokens, "cost": total_cost}
    return None, None
