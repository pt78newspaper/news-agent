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
        
    from datetime import datetime, timedelta

    cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    recent = [e for e in old_events if (e.get("date") or e.get("first_reported", ""))[:10] >= cutoff]
    save_json(HISTORY_FILE, {"_events": recent, "_stats": old_stats})


def hash_event(e):
    raw = (e.get("title_ru", "") + e.get("title_en", "") + e.get("date", "")).strip().lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


AREAS_ORDER = ["Россия", "Северная и Центральная Америка", "Южная Америка", "Европа", "Ближний Восток", "Дальний Восток", "Южная и Юго-Восточная Азия", "Океания и Австралия", "Африка"]
RUSSIA_AREA = "Россия"
PER_AREA_RU = {"politics": 3, "energy": 1, "tech": 1, "ai": 1, "finance": 1}
PER_AREA = {"politics": 2, "energy": 1, "tech": 1, "ai": 1}
GLOBAL = {"photo": 1, "culture": 1, "finance": 1, "ecology": 1}
CAT_ORDER = ["tech", "ai", "life", "conflicts", "economy", "politics", "statement", "culture", "photo", "ecology"]
CAT_LABELS = {
    "tech": "Технологический рост",
    "ai": "Искусственный интеллект",
    "life": "Жизнь людей",
    "conflicts": "Конфликты",
    "economy": "Экономика стран",
    "politics": "Внутренняя и внешняя политика",
    "statement": "Заявление дня",
    "culture": "Культура",
    "photo": "Фото",
    "ecology": "Экология",
}
CAT_LABELS_SHORT = {
    "tech": "Технологии",
    "ai": "ИИ",
    "life": "Жизнь людей",
    "conflicts": "Конфликты",
    "economy": "Экономика",
    "politics": "Политика",
    "statement": "Заявление",
    "culture": "Культура",
    "photo": "Фото",
    "ecology": "Экология",
}


def sort_events(events):
    cat_idx = {c: i for i, c in enumerate(CAT_ORDER)}
    return sorted(events, key=lambda e: (
        cat_idx.get(e.get("category", "politics"), 99),
        (e.get("region") or e.get("area") or "").lower()
    ))


def dedup_events(events):
    seen_links = set()
    out = []
    for e in events:
        links = set(e.get("links", []))
        if links & seen_links:
            continue
        seen_links |= links
        out.append(e)
    return out


def looks_like_ai(cluster):
    kw = ("ai", "artificial intelligence", "openai", "chatgpt", "gpt-", "llm",
          "neural network", "machine learning", "deepseek", "gemini", "claude",
          "ии", "искусственн", "нейросет")
    text = ""
    for a in cluster:
        text += (a.get("title", "") + " " + a.get("summary", ""))[:400].lower()
    return any(k in text for k in kw)


def looks_like_energy(cluster):
    kw = ("energy", "oil", "gas", "coal", "nuclear power", "power plant", "renewable",
          "wind", "solar", "electricity", "grid", "нефт", "газ", "энерг", "атом",
          "уголь", "ветер", "солнечн", "электроэнерг", "топлив", "нефтегаз",
          "opec", "санкции на энергосектор", "lng", "дизел", "бензин")
    nk = ("naval", "destroyer", "missile", "submarine", "warship", "nuclear weapon",
          "nuclear-capable", "atomic bomb", "военн", "ракет")
    text = ""
    for a in cluster:
        text += (a.get("title", "") + " " + a.get("summary", ""))[:400].lower()
    if any(k in text for k in nk):
        return False
    return any(k in text for k in kw)


def _cluster_text(cluster):
    text = ""
    for a in cluster:
        text += (a.get("title", "") + " " + a.get("summary", ""))[:400].lower()
    return text


def looks_like_culture(cluster):
    kw = ("art", "artist", "museum", "exhibition", "film", "cinema", "movie", "actor",
          "music", "concert", "festival", "theater", "theatre", "literature", "book",
          "writer", "opera", "architecture", "культур", "искусств", "музе", "выстав",
          "кино", "фильм", "актёр", "актер", "концерт", "фестивал", "театр", "книг",
          "писател", "архитектур", "премиа")
    return any(k in _cluster_text(cluster) for k in kw)


def looks_like_ecology(cluster):
    kw = ("climate", "emission", "carbon", "greenhouse", "pollution", "recycl", "waste",
          "environment", "deforestation", "wildfire", "flood", "экологи", "климат",
          "выброс", "углерод", "отход", "загрязн", "переработ", "природ", "лес",
          "биоразнообраз", "наводнени", "пожар", "мусор")
    return any(k in _cluster_text(cluster) for k in kw)


def _get_area(cluster):
    for a in cluster:
        area = a.get("area")
        if area:
            return area
    return ""


def select_clusters(clusters, config=None):
    areas = {conf.get("area") for conf in (config.get("sources", {}).values() if config else {})} if config else set()
    if not areas:
        areas = set(AREAS_ORDER)

    by_area_cat = {}
    for c in clusters:
        cat = c[0].get("category", "politics") if c else "politics"
        for a in c:
            a["category"] = cat
        area = _get_area(c) or "Неизвестный регион"
        if cat == "tech":
            if looks_like_ai(c):
                cat = "ai"
            elif looks_like_energy(c):
                cat = "energy"
            elif looks_like_ecology(c):
                cat = "ecology"
            elif looks_like_culture(c):
                cat = "culture"
        elif cat not in ("finance", "ai", "photo", "energy", "culture", "ecology"):
            if looks_like_culture(c):
                cat = "culture"
            elif looks_like_ecology(c):
                cat = "ecology"
            else:
                cat = "politics"
        for a in c:
            a["category"] = cat
        by_area_cat.setdefault(area, {}).setdefault(cat, []).append(c)

    selected = []
    chosen = set()
    for area in sorted(areas):
        area_clusters = by_area_cat.get(area, {})
        quota = PER_AREA_RU if area == RUSSIA_AREA else PER_AREA
        for cat, n in quota.items():
            take = area_clusters.get(cat, [])[:n]
            for c in take:
                if id(c) not in chosen:
                    selected.append(c)
                    chosen.add(id(c))
    for cat, n in GLOBAL.items():
        pool = list(by_area_cat.get("Мир", {}).get(cat, []))
        for area in sorted(areas):
            if area != "Мир":
                pool.extend(by_area_cat.get(area, {}).get(cat, []))
        take = pool[:n]
        for c in take:
            if id(c) not in chosen:
                selected.append(c)
                chosen.add(id(c))
    return selected


def generate_html(events, config, usage=None, api_key=None):
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_agent", "template.html")
    with open(tpl_path, encoding="utf-8") as f:
        html = f.read()

    cat_counts = {k: 0 for k in CAT_ORDER}
    cat_events = {}
    cat_order = []
    for ev in events:
        cat = ev.get("category", "politics")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if cat not in cat_events:
            cat_events[cat] = []
            cat_order.append(cat)
        cat_events[cat].append(ev)

    stories_html = ""
    for cat_name in ([c for c in CAT_ORDER if c in cat_order] + [c for c in cat_order if c not in CAT_ORDER]):
        cat_evs = cat_events[cat_name]
        inner = ""
        for idx, ev in enumerate(cat_evs, 1):
            cat = ev.get("category", "politics")

            sources_str = ", ".join(ev.get("sources", []))
            links_html = " | ".join(
                f'<a href="{l}" target="_blank" rel="noopener">{l.split("/")[2] if "//" in l else l}</a>'
                for l in ev.get("links", [])[:3]
            )

            cat_label = CAT_LABELS_SHORT.get(cat, cat)
            cat_badge = f'<span class="cat-badge cat-{cat}">{cat_label}</span>' if cat_label else ""
            region = ev.get("region") or ev.get("area") or ""
            region_badge = f'<span class="area-badge">{region}</span>' if region else ""

            perspective = ev.get("perspective", "").strip()
            perspective_type = ev.get("perspective_type", "").strip()
            perspective_label = {
                "from_source": "из источника",
                "assumed": "предположительно",
                "unclear": "неясно"
            }.get(perspective_type, "")

            summ_en = ev.get("summary_en", "")
            summ_ru = ev.get("summary", "")
            if summ_en:
                summ_en_html = f'<div class="summ-en"><span class="summ-label">English</span>{summ_en}</div>'
            else:
                summ_en_html = ""
            summ_ru_html = f'<div class="summ-ru">{summ_ru}</div>' if summ_ru else ""

            if perspective:
                comparison_html = f'<div class="comparison"><div class="compare-title">Оценки {'(' + perspective_label + ')' if perspective_label else ''}</div><div class="compare-item">{perspective}</div></div>'
            else:
                comparison_html = ""

            story = f"""
<div class="story">
  <div class="story-card">
    <div class="story-header">
      <div class="story-number">{idx}</div>
      <div class="story-titles">
        <div class="title-en">{ev.get("title_en", "")} {region_badge}{cat_badge}</div>
        <div class="title-ru">{ev.get("title_ru", "")}</div>
      </div>
    </div>
    <div class="story-body">
      <div class="summary">{summ_en_html}{summ_ru_html}</div>
      {comparison_html}
      <div class="story-footer">
        <span class="tag">{ev.get("date", "")}</span>
        <span>Источники: {sources_str}</span>
        <span>{links_html}</span>
      </div>
    </div>
  </div>
</div>"""
            inner += story

        stories_html += (
            f'<div class="area-section">'
            f'<div class="area-header" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')">'
            f'<span class="area-plus"></span>'
            f'<span class="area-name">{CAT_LABELS.get(cat_name, cat_name)}</span>'
            f'<span class="area-count">{idx}</span>'
            f'</div>'
            f'<div class="area-body">{inner}'
            f'<div class="area-close-row"><button class="area-close" onclick="var s=this.closest(\'.area-section\');s.querySelector(\'.area-header\').classList.remove(\'open\');s.querySelector(\'.area-body\').classList.remove(\'open\')">Свернуть</button></div>'
            f'</div>'
            f'</div>'
        )

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
        total_tokens = usage.get("total_tokens", usage.get("tokens", 0))
        total_cost = usage.get("total_cost", usage.get("cost", 0))
        usage_text = (
            f"Запуск: {usage.get('tokens', 0)} токенов, "
            f"стоимость {usage.get('cost', 0):.4f} руб."
            f"{balance_text}"
            f" | Всего за всё время: {total_tokens} токенов, "
            f"{total_cost:.4f} руб."
        )
    else:
        usage_text = ""

    from datetime import datetime, timezone
    utc_now = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    html = html.replace("__UPDATE_TIME__", utc_now)
    html = html.replace("__USAGE_INFO__", usage_text)
    html = html.replace("__TOTAL_STORIES__", str(len(events)))
    html = html.replace("__TOTAL_SOURCES__", str(sum(len(e.get("sources", [])) for e in events)))
    cat_display = " | ".join(f'{l}: {cat_counts.get(k,0)}' for k,l in [(k, CAT_LABELS_SHORT[k]) for k in CAT_ORDER] if cat_counts.get(k,0))
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
        archive_html = '<div class="archive-section"><div class="archive-title">Архив</div>'
        for date_key in sorted(by_date.keys(), reverse=True):
            day_events = by_date[date_key]
            archive_html += f'<div class="archive-day"><div class="archive-day-header" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')"><span>{date_key} ({len(day_events)})</span><span class="arrow">▶</span></div><div class="archive-day-body">'
            for pe in day_events:
                cat = pe.get("category", "politics")
                cat_label = (CAT_LABELS_SHORT.get(cat) or {
                    "politics": "Политика", "ai": "AI", "tech": "Техно/Наука",
                    "energy": "Энергетика", "finance": "Финансы",
                }.get(cat, ""))
                cat_badge = f'<span class="cat-badge cat-{cat}">{cat_label}</span>' if cat_label else ""
                region = pe.get("region") or pe.get("area", "")
                region_badge = f'<span class="area-badge">{region}</span>' if region else ""
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
                archive_html += f'<div class="story"><div class="story-card"><div class="story-header"><div class="story-titles"><div class="title-en">{pe.get("title_en", "")} {region_badge}{cat_badge}</div><div class="title-ru">{pe.get("title_ru", "")}</div></div></div><div class="story-body"><div class="summary">{summ_en_html}{summ_ru_html}</div></div><div class="story-footer"><span class="tag">{pe.get("date", "")}</span><span>{links}</span></div></div></div>'
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

    selected = select_clusters(clusters, config)
    from collections import Counter
    sel_cats = Counter(c[0].get("category", "politics") for c in selected)
    print(f"  Selected for AI: {len(selected)} clusters ({dict(sel_cats)})")

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
    events = dedup_events(sort_events(events))
    generate_html(events, config, usage, api_key)


if __name__ == "__main__":
    main()
