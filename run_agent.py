import sys, os, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from news_agent.fetcher import fetch_all
from news_agent.analyzer import cluster_news
from news_agent.ai_summarizer import summarize_news

HISTORY_FILE = "output/history.json"


def load_history():
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(events):
    os.makedirs("output", exist_ok=True)
    old = load_history()
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
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(old[-100:], f, ensure_ascii=False, indent=2)


def hash_event(e):
    raw = (e.get("title_ru", "") + e.get("title_en", "") + e.get("date", "")).strip().lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def generate_html(events):
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
      <div class="summary">{ev.get("summary", "")}</div>
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

    from datetime import datetime, timezone
    utc_now = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    html = html.replace("__UPDATE_TIME__", utc_now)
    html = html.replace("__TOTAL_STORIES__", str(len(events)))
    html = html.replace("__TOTAL_SOURCES__", str(sum(len(e.get("sources", [])) for e in events)))
    html = html.replace("__REGIONS_COVERED__", str(len(set(s for e in events for s in e.get("sources", [])))))
    html = html.replace("__STORIES__", stories_html)
    html = html.replace("__AI_MODEL__", "Qwen 3.7 Max")
    html = html.replace("__AI_BADGE__", '<span class="ai-badge">AI: Qwen 3.7 Max</span>')

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
        print(f"  AI: GPTunnel (qwen3.7-max) enabled")
    else:
        print("  AI: DISABLED (no API key)")

    articles = fetch_all(config)
    if not articles:
        print("No news.")
        generate_html([])
        return

    clusters = cluster_news(articles)
    print(f"Total clusters: {len(clusters)}")

    history = load_history()
    print(f"History: {len(history)} past events")

    if api_key:
        events = summarize_news(clusters[:30], api_key, history)
    else:
        events = None

    if not events:
        print("AI failed or disabled, generating empty page.")
        events = []

    save_history(events)
    generate_html(events)


if __name__ == "__main__":
    main()
