import requests, json, re

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"
MODEL = "openrouter/free"
SYS_PROMPT = "Ты новостной аналитик. Отвечай только на русском, кратко, по делу."


def call_ai(prompt, api_key, provider="openrouter"):
    api_url = OPENROUTER_API if provider == "openrouter" else DEEPSEEK_API
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://pt78newspaper.github.io/news-agent/"
        headers["X-Title"] = "NewsAgentPT78"

    model = MODEL if provider == "openrouter" else "deepseek-chat"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 600,
    }

    resp = requests.post(api_url, headers=headers, json=body, timeout=60)
    if resp.status_code != 200:
        print(f"  [AI ERROR {provider}] {resp.status_code}: {resp.text[:150]}")
        return None
    return resp.json()["choices"][0]["message"]["content"]


def summarize_cluster(cluster, api_key, provider="openrouter"):
    articles_by_region = {}
    for a in cluster:
        region = a["region_label"]
        if region not in articles_by_region:
            articles_by_region[region] = []
        articles_by_region[region].append({
            "title": a["title"],
            "source": a["source_name"]
        })

    news_block = ""
    for region, articles in articles_by_region.items():
        news_block += f"\n{region}:\n"
        for art in articles:
            news_block += f"  - {art['title']} ({art['source']})\n"

    prompt = (
        "Вот заголовки новостей из разных стран на одну тему:\n"
        f"{news_block}\n"
        "Сделай три вещи:\n"
        "1. [EN] — Напиши английский заголовок (если его нет, переведи с русского)\n"
        "2. [RU] — Напиши русский заголовок (если его нет, переведи с английского)\n"
        "3. [SUMMARY] — Суть новости на русском, 2-3 предложения\n"
        "4. [COMPARISON] — Одно-два предложения: как отличаются взгляды в России, на Западе, "
        "в странах БРИКС. Совпадают или расходятся оценки?\n\n"
        "Формат ответа:\n"
        "EN: ...\n"
        "RU: ...\n"
        "SUMMARY: ...\n"
        "COMPARISON: ..."
    )

    result = call_ai(prompt, api_key, provider)
    if not result:
        return None

    parsed = {
        "title_en": None,
        "title_ru": None,
        "summary": None,
        "comparison": None
    }

    en_match = re.search(r"EN:\s*(.*?)(?:\n|$)", result)
    ru_match = re.search(r"RU:\s*(.*?)(?:\n|$)", result)
    summary_match = re.search(r"SUMMARY:\s*(.*?)(?:\nCOMPARISON:|$)", result, re.DOTALL)
    comparison_match = re.search(r"COMPARISON:\s*(.*)", result, re.DOTALL)

    if en_match:
        parsed["title_en"] = en_match.group(1).strip()
    if ru_match:
        parsed["title_ru"] = ru_match.group(1).strip()
    if summary_match:
        parsed["summary"] = summary_match.group(1).strip()
    if comparison_match:
        parsed["comparison"] = comparison_match.group(1).strip()

    return parsed
