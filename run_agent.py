import sys, os, json, hashlib, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from news_agent.fetcher import fetch_all
from news_agent.analyzer import cluster_news
from news_agent.ai_summarizer import summarize_news, get_system_prompt

STATS_FILE = "output/stats.json"
HISTORY_FILE = "output/history.json"


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_history(events):
    old = load_json(HISTORY_FILE, [])
    seen = {hash_event(e) for e in old}
    for e in events:
        h = hash_event(e)
        if h not in seen:
            e["first_reported"] = e.get("date", "")
            e["id"] = h
            old.append(e)
            seen.add(h)
        else:
            for oe in old:
                if hash_event(oe) == h:
                    oe["last_reported"] = e.get("date", "")
                    break
    save_json(HISTORY_FILE, old[-100:])


def hash_event(e):
    raw = (e.get("title_ru", "") + e.get("title_en", "") + e.get("date", "")).strip().lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def generate_html(events, config, usage=None, api_key=None):
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_agent", "template.html")
    with open(tpl_path, encoding="utf-8") as f:
        html = f.read()

    stories_html = ""
    for idx, ev in enumerate(events, 1):
        sources_str = ", ".join(ev.get("sources", []))
        links_html = " | ".join(
            f'<a href="{l}" target="_blank" rel="noopener">{l.split("/")[2] if "//" in l else l}</a>'
            for l in ev.get("links", [])[:3]
        )
        perspective_label = {
            "from_source": "из источника",
            "assumed": "предположительно",
            "unclear": "неясно"
        }.get(ev.get("perspective_type", ""), "")

        summ_en = ev.get("summary_en", "")
        summ_ru = ev.get("summary", "")
        if summ_en:
            summ_en_html = f'<div class="summ-en"><span class="summ-label">English</span>{summ_en}</div>'
        else:
            summ_en_html = ""
        summ_ru_html = f'<div class="summ-ru">{summ_ru}</div>' if summ_ru else ""

        story = f"""
<div class="story">
  <div class="story-card">
    <div class="story-header">
      <div class="story-number">{idx}</div>
      <div class="story-titles">
        <div class="title-en">{ev.get("title_en", "")}</div>
        <div class="title-ru">{ev.get("title_ru", "")}</div>
      </div>
    </div>
    <div class="story-body">
      <div class="summary">{summ_en_html}{summ_ru_html}</div>
      <div class="comparison">
        <div class="compare-title">Оценки {'(' + perspective_label + ')' if perspective_label else ''}</div>
        <div class="compare-item">{ev.get("perspective", "не указано")}</div>
      </div>
      <div class="story-footer">
        <span class="tag">{ev.get("date", "")}</span>
        <span>Источники: {sources_str}</span>
        <span>{links_html}</span>
      </div>
    </div>
  </div>
</div>"""
        stories_html += story

    if not stories_html:
        stories_html = '<div class="no-news"><h2>Новостей нет</h2><p>Попробуйте позже</p></div>'

    # System info
    sources = config.get("sources", {})
    active_sources = {k: v for k, v in sources.items() if v.get("feeds")}
    countries_list = ", ".join(s["label"] for s in active_sources.values())
    sources_html = ""
    for key, s in active_sources.items():
        sources_html += f'<div class="country"><span class="country-name">{s["label"]}</span>'
        for feed in s.get("feeds", []):
            short = feed.replace("https://", "").replace("http://", "").split("/")[0]
            sources_html += f'<span class="feed">{short}</span>'
        sources_html += "</div>"

    # Balance info
    balance_text = ""
    if api_key:
        try:
            br = requests.get("https://gptunnel.ru/v1/balance?useWalletBalance=true",
                headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
            if br.status_code == 200:
                bal = br.json().get("balance", 0)
                balance_text = f" | Баланс: {bal:.2f} руб."
        except:
            pass

    # Usage info
    if usage:
        usage_text = (
            f"Запуск: {usage.get('tokens', 0)} токенов, "
            f"стоимость {usage.get('cost', 0):.4f} руб."
            f"{balance_text}"
            f" | Всего за всё время: {usage.get('total_tokens', 0)} токенов, "
            f"{usage.get('total_cost', 0):.4f} руб."
        )
    else:
        usage_text = ""

    from datetime import datetime, timezone
    utc_now = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    html = html.replace("__UPDATE_TIME__", utc_now)
    html = html.replace("__USAGE_INFO__", usage_text)
    html = html.replace("__TOTAL_STORIES__", str(len(events)))
    html = html.replace("__TOTAL_SOURCES__", str(sum(len(e.get("sources", [])) for e in events)))
    html = html.replace("__REGIONS_COVERED__", str(len(set(s for e in events for s in e.get("sources", [])))))
    html = html.replace("__STORIES__", stories_html)
    from news_agent.ai_summarizer import MODEL as AI_MODEL_NAME
    html = html.replace("__AI_MODEL__", AI_MODEL_NAME)
    html = html.replace("__AI_BADGE__", f'<span class="ai-badge">AI: {AI_MODEL_NAME}</span>')
    html = html.replace("__SYSTEM_PROMPT__", get_system_prompt())
    html = html.replace("__COUNTRIES_LIST__", countries_list)
    html = html.replace("__SOURCES_HTML__", sources_html)

    # Archive from history
    archive_html = ""
    history = load_json(HISTORY_FILE, [])
    current_ids = {hash_event(e) for e in events}
    past_events = [e for e in history if hash_event(e) not in current_ids]
    if past_events:
        by_date = {}
        for e in past_events:
            d = (e.get("date") or e.get("first_reported", ""))[:10]
            by_date.setdefault(d, []).append(e)
        archive_html = '<div class="archive-section"><div class="archive-title">Архив</div>'
        for date_key in sorted(by_date.keys(), reverse=True):
            day_events = by_date[date_key]
            archive_html += f'<div class="archive-day"><div class="archive-day-header" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')"><span>{date_key} ({len(day_events)})</span><span class="arrow">▶</span></div><div class="archive-day-body">'
            for pe in day_events:
                summ_en = pe.get("summary_en", "")
                summ_ru = pe.get("summary", "")
                if summ_en:
                    summ_en_html = f'<div class="summ-en"><span class="summ-label">English</span>{summ_en}</div>'
                else:
                    summ_en_html = ""
                summ_ru_html = f'<div class="summ-ru">{summ_ru}</div>' if summ_ru else ""
                links = " | ".join(
                    f'<a href="{l}" target="_blank" rel="noopener">{l.split("/")[2] if "//" in l else l}</a>'
                    for l in pe.get("links", [])[:3]
                )
                archive_html += f'<div class="story"><div class="story-card"><div class="story-header"><div class="story-titles"><div class="title-en">{pe.get("title_en", "")}</div><div class="title-ru">{pe.get("title_ru", "")}</div></div></div><div class="story-body"><div class="summary">{summ_en_html}{summ_ru_html}</div></div><div class="story-footer"><span class="tag">{pe.get("date", "")}</span><span>{links}</span></div></div></div>'
            archive_html += '</div></div>'
        archive_html += '</div>'
    html = html.replace("__ARCHIVE__", archive_html)

    os.makedirs("output", exist_ok=True)
    out = os.path.join("output", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated: {out}")


def main():
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    api_key = os.environ.get("GPTUNNEL_KEY", "").strip()
    if not api_key:
        api_key = config.get("gptunnel_api_key", "").strip()

    print("NewsAgentPT78")
    print("=" * 40)
    if api_key:
        from news_agent.ai_summarizer import MODEL
        print(f"  AI: GPTunnel ({MODEL}) enabled")
    else:
        print("  AI: DISABLED (no API key)")

    articles = fetch_all(config)
    if not articles:
        print("No news.")
        generate_html([], config)
        return

    clusters = cluster_news(articles)
    print(f"Total clusters: {len(clusters)}")

    history = load_json(HISTORY_FILE, [])
    print(f"History: {len(history)} past events")

    usage = None
    events = None
    if api_key:
        events, usage = summarize_news(clusters[:7], api_key, history)
        if usage:
            stats = load_json(STATS_FILE, {"total_tokens": 0, "total_cost": 0})
            stats["total_tokens"] += usage.get("tokens", 0)
            stats["total_cost"] += usage.get("cost", 0)
            usage["total_tokens"] = round(stats["total_tokens"], 2)
            usage["total_cost"] = round(stats["total_cost"], 4)
            save_json(STATS_FILE, stats)

    if not events:
        print("AI failed or disabled, generating empty page.")
        events = []

    save_history(events)
    generate_html(events, config, usage, api_key)


if __name__ == "__main__":
    main()
