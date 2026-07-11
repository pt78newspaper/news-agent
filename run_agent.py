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
        pass
    # Also try without output/ prefix (gh-pages stores at root)
    alt = path.replace("output/", "", 1)
    if alt != path:
        try:
            with open(alt, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_history(events, stats=None):
    old = load_json(HISTORY_FILE, [])
    if isinstance(old, dict) and "_events" in old:
        old_events = old["_events"]
        old_stats = old.get("_stats", {"total_tokens": 0, "total_cost": 0})
    else:
        old_events = old if isinstance(old, list) else []
        old_stats = {"total_tokens": 0, "total_cost": 0}
    seen = {hash_event(e) for e in old_events}
    for e in events:
        h = hash_event(e)
        if h not in seen:
            e["first_reported"] = e.get("date", "")
            e["id"] = h
            old_events.append(e)
            seen.add(h)
        else:
            for oe in old_events:
                if hash_event(oe) == h:
                    oe["last_reported"] = e.get("date", "")
                    break
    if stats:
        old_stats["total_tokens"] += stats.get("tokens", 0)
        old_stats["total_cost"] += stats.get("cost", 0)
    save_json(HISTORY_FILE, {"_events": old_events[-100:], "_stats": old_stats})


def hash_event(e):
    raw = (e.get("title_ru", "") + e.get("title_en", "") + e.get("date", "")).strip().lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def generate_html(events, config, usage=None, api_key=None):
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_agent", "template.html")
    with open(tpl_path, encoding="utf-8") as f:
        html = f.read()

    cat_counts = {"politics": 0, "ai": 0, "tech": 0}
    stories_html = ""
    for idx, ev in enumerate(events, 1):
        cat = ev.get("category", "politics")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

        sources_str = ", ".join(ev.get("sources", []))
        links_html = " | ".join(
            f'<a href="{l}" target="_blank" rel="noopener">{l.split("/")[2] if "//" in l else l}</a>'
            for l in ev.get("links", [])[:3]
        )

        cat_label = {"politics": "ÐŸÐ¾Ð»Ð¸Ñ‚Ð¸ÐºÐ°", "ai": "AI", "tech": "Ð¢ÐµÑ…Ð½Ð¾/ÐÐ°ÑƒÐºÐ°"}.get(cat, "")
        cat_badge = f'<span class="cat-badge cat-{cat}">{cat_label}</span>' if cat_label else ""

        perspective = ev.get("perspective", "").strip()
        perspective_type = ev.get("perspective_type", "").strip()
        perspective_label = {
            "from_source": "Ð¸Ð· Ð¸ÑÑ‚Ð¾Ñ‡Ð½Ð¸ÐºÐ°",
            "assumed": "Ð¿Ñ€ÐµÐ´Ð¿Ð¾Ð»Ð¾Ð¶Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾",
            "unclear": "Ð½ÐµÑÑÐ½Ð¾"
        }.get(perspective_type, "")

        summ_en = ev.get("summary_en", "")
        summ_ru = ev.get("summary", "")
        if summ_en:
            summ_en_html = f'<div class="summ-en"><span class="summ-label">English</span>{summ_en}</div>'
        else:
            summ_en_html = ""
        summ_ru_html = f'<div class="summ-ru">{summ_ru}</div>' if summ_ru else ""

        if perspective:
            comparison_html = f'<div class="comparison"><div class="compare-title">ÐžÑ†ÐµÐ½ÐºÐ¸ {'(' + perspective_label + ')' if perspective_label else ''}</div><div class="compare-item">{perspective}</div></div>'
        else:
            comparison_html = ""

        story = f"""
<div class="story">
  <div class="story-card">
    <div class="story-header">
      <div class="story-number">{idx}</div>
      <div class="story-titles">
        <div class="title-en">{ev.get("title_en", "")} {cat_badge}</div>
        <div class="title-ru">{ev.get("title_ru", "")}</div>
      </div>
    </div>
    <div class="story-body">
      <div class="summary">{summ_en_html}{summ_ru_html}</div>
      {comparison_html}
      <div class="story-footer">
        <span class="tag">{ev.get("date", "")}</span>
        <span>Ð˜ÑÑ‚Ð¾Ñ‡Ð½Ð¸ÐºÐ¸: {sources_str}</span>
        <span>{links_html}</span>
      </div>
    </div>
  </div>
</div>"""
        stories_html += story

    if not stories_html:
        stories_html = '<div class="no-news"><h2>ÐÐ¾Ð²Ð¾ÑÑ‚ÐµÐ¹ Ð½ÐµÑ‚</h2><p>ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ Ð¿Ð¾Ð·Ð¶Ðµ</p></div>'

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
                balance_text = f" | Ð‘Ð°Ð»Ð°Ð½Ñ: {bal:.2f} Ñ€ÑƒÐ±."
        except:
            pass

    # Usage info
    if usage:
        total_tokens = usage.get("total_tokens", usage.get("tokens", 0))
        total_cost = usage.get("total_cost", usage.get("cost", 0))
        usage_text = (
            f"Ð—Ð°Ð¿ÑƒÑÐº: {usage.get('tokens', 0)} Ñ‚Ð¾ÐºÐµÐ½Ð¾Ð², "
            f"ÑÑ‚Ð¾Ð¸Ð¼Ð¾ÑÑ‚ÑŒ {usage.get('cost', 0):.4f} Ñ€ÑƒÐ±."
            f"{balance_text}"
            f" | Ð’ÑÐµÐ³Ð¾ Ð·Ð° Ð²ÑÑ‘ Ð²Ñ€ÐµÐ¼Ñ: {total_tokens} Ñ‚Ð¾ÐºÐµÐ½Ð¾Ð², "
            f"{total_cost:.4f} Ñ€ÑƒÐ±."
        )
    else:
        usage_text = ""

    from datetime import datetime, timezone
    utc_now = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    html = html.replace("__UPDATE_TIME__", utc_now)
    html = html.replace("__USAGE_INFO__", usage_text)
    html = html.replace("__TOTAL_STORIES__", str(len(events)))
    html = html.replace("__TOTAL_SOURCES__", str(sum(len(e.get("sources", [])) for e in events)))
    cat_display = " | ".join(f'{l}: {cat_counts.get(k,0)}' for k,l in [("politics","ÐŸÐ¾Ð»Ð¸Ñ‚Ð¸ÐºÐ°"),("ai","AI"),("tech","Ð¢ÐµÑ…Ð½Ð¾")] if cat_counts.get(k,0))
    html = html.replace("__REGIONS_COVERED__", cat_display)
    html = html.replace("__STORIES__", stories_html)
    from news_agent.ai_summarizer import MODEL as AI_MODEL_NAME
    html = html.replace("__AI_MODEL__", AI_MODEL_NAME)
    html = html.replace("__AI_BADGE__", f'<span class="ai-badge">AI: {AI_MODEL_NAME}</span>')
    html = html.replace("__SYSTEM_PROMPT__", get_system_prompt())
    html = html.replace("__COUNTRIES_LIST__", countries_list)
    html = html.replace("__SOURCES_HTML__", sources_html)
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    html = html.replace("__ADMIN_TOKEN__", admin_token)

    # Archive from history
    archive_html = ""
    history_raw = load_json(HISTORY_FILE, [])
    if isinstance(history_raw, dict) and "_events" in history_raw:
        history = history_raw["_events"]
    else:
        history = history_raw if isinstance(history_raw, list) else []
    current_ids = {hash_event(e) for e in events}
    past_events = [e for e in history if hash_event(e) not in current_ids]
    if past_events:
        by_date = {}
        for e in past_events:
            d = (e.get("date") or e.get("first_reported", ""))[:10]
            by_date.setdefault(d, []).append(e)
        archive_html = '<div class="archive-section"><div class="archive-title">ÐÑ€Ñ…Ð¸Ð²</div>'
        for date_key in sorted(by_date.keys(), reverse=True):
            day_events = by_date[date_key]
            archive_html += f'<div class="archive-day"><div class="archive-day-header" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')"><span>{date_key} ({len(day_events)})</span><span class="arrow">â–¶</span></div><div class="archive-day-body">'
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

    # Separate politics and tech clusters, ensure tech/AI reach the AI
    pol_clusters = [c for c in clusters if c[0].get("category", "politics") == "politics"]
    tech_clusters = [c for c in clusters if c[0].get("category", "politics") != "politics"]
    print(f"  Political clusters: {len(pol_clusters)}, Tech/AI clusters: {len(tech_clusters)}")

    # Take top 8 political + up to 5 tech, cap at 10 total
    selected = pol_clusters[:8]
    selected.extend(tech_clusters[:min(5, max(2, 10 - len(selected)))])
    selected = selected[:10]
    print(f"  Selected for AI: {len(selected)} clusters")

    history_raw = load_json(HISTORY_FILE, [])
    if isinstance(history_raw, dict) and "_events" in history_raw:
        history = history_raw["_events"]
        old_stats = history_raw.get("_stats", {})
    else:
        history = history_raw if isinstance(history_raw, list) else []
        old_stats = {}
    print(f"History: {len(history)} past events")

    usage = None
    events = None
    if api_key:
        events, usage = summarize_news(selected, api_key, history)
        if events:
            from collections import Counter
            cat_dist = Counter(e.get("category", "politics") for e in events)
            print(f"  Cat distribution: {dict(cat_dist)}")
        if usage:
            cumul_tokens = old_stats.get("total_tokens", 0) + usage.get("tokens", 0)
            cumul_cost = old_stats.get("total_cost", 0) + usage.get("cost", 0)
            usage["total_tokens"] = round(cumul_tokens, 2)
            usage["total_cost"] = round(cumul_cost, 4)

    if not events:
        print("AI failed or disabled, generating empty page.")
        events = []

    save_history(events, usage)
    generate_html(events, config, usage, api_key)


if __name__ == "__main__":
    main()
