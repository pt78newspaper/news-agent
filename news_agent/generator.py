import os, re
from datetime import datetime, timezone
from collections import defaultdict
from .analyzer import extract_keywords

TEMPLATE = None
AI = None

def load_template():
    global TEMPLATE
    if TEMPLATE:
        return TEMPLATE
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
    with open(path, encoding="utf-8") as f:
        TEMPLATE = f.read()
    return TEMPLATE

STORY = """<div class="story">
  <div class="story-card">
    <div class="story-header">
      <div class="story-number">__NUM__</div>
      <div class="story-titles">
        <div class="title-en">__TITLE_EN__</div>
        <div class="title-ru">__TITLE_RU__</div>
      </div>
    </div>
    <div class="story-body">
      __SUMMARY__
      __COMPARISON__
      __PERSPECTIVES__
    </div>
    <div class="story-footer">
      <span><strong>__REGIONS_COUNT__</strong> regions</span>
      <span class="tag">#__KEYWORDS__</span>
    </div>
  </div>
</div>"""

PERSP = """<div class="perspective" style="--region-color: __COLOR__">
  <span class="region-tag">__REGION__</span>
  <div class="meta">
    <a href="__LINK__" target="_blank" rel="noopener">__SOURCE__</a>
  </div>
  <div class="headline">__HEADLINE__</div>
  <div class="keywords">__KWS__</div>
</div>"""

SUMMARY_HTML = """<div class="summary">__TEXT__</div>"""

COMPARISON_HTML = """<div class="comparison"><div class="compare-title">Сравнение освещения</div>__ITEMS__</div>"""

def is_russian(text):
    return bool(re.search(r'[\u0400-\u04FF]', text))

def generate(clusters, output_dir="output", deepseek_key=None):
    global AI
    if deepseek_key:
        from .ai_summarizer import summarize_cluster
        AI = lambda c: summarize_cluster(c, deepseek_key)
        print(f"  AI: DeepSeek enabled")

    stories = ""
    sources = set()
    regions = set()

    for idx, cluster in enumerate(clusters[:10], 1):
        # Fallback titles (before AI)
        en_articles = [a for a in cluster if not is_russian(a["title"])]
        ru_articles = [a for a in cluster if is_russian(a["title"])]
        fallback_en = en_articles[0]["title"] if en_articles else cluster[0]["title"]
        fallback_ru = ru_articles[0]["title"] if ru_articles else fallback_en

        title_en = fallback_en
        title_ru = fallback_ru
        summary_text = ""
        comparison_text = ""

        # AI summarization
        if AI:
            try:
                ai_result = AI(cluster)
                if ai_result:
                    if ai_result.get("title_en"):
                        title_en = ai_result["title_en"]
                    if ai_result.get("title_ru"):
                        title_ru = ai_result["title_ru"]
                    if ai_result.get("summary"):
                        summary_text = ai_result["summary"]
                    if ai_result.get("comparison"):
                        comparison_text = ai_result["comparison"]
                    print(f"  Story {idx}: AI OK")
                else:
                    print(f"  Story {idx}: AI returned None")
            except Exception as e:
                print(f"  Story {idx}: AI error: {e}")

        if len(title_en) > 100:
            title_en = title_en[:97] + "..."
        if len(title_ru) > 100:
            title_ru = title_ru[:97] + "..."

        # Perspectives
        persp_html = ""
        by_region = defaultdict(list)
        for a in cluster:
            by_region[a["region_label"]].append(a)
            sources.add(a["source_name"])
            regions.add(a["region_label"])

        for rl, arts in by_region.items():
            s = arts[0]
            kw = extract_keywords(s["title"], s["summary"])
            kw_html = " ".join(f'<span class="keyword">{k}</span>' for k in kw[:4])
            p = PERSP.replace("__COLOR__", s["region_color"])
            p = p.replace("__REGION__", rl)
            p = p.replace("__LINK__", s["link"])
            p = p.replace("__SOURCE__", s["source_name"])
            p = p.replace("__HEADLINE__", s["title"])
            p = p.replace("__KWS__", kw_html)
            persp_html += p

        if not persp_html:
            continue

        kw_all = set()
        for a in cluster:
            kw_all.update(extract_keywords(a["title"], a["summary"])[:3])
        top_kw = list(kw_all)[:5]

        # Build parts
        summary_html = ""
        if summary_text:
            summary_html = SUMMARY_HTML.replace("__TEXT__", summary_text)

        comp_html = ""
        if comparison_text:
            comp_html = COMPARISON_HTML.replace("__ITEMS__", f'<div class="compare-item">{comparison_text}</div>')

        persp_section = '<div class="perspectives-title">Освещение в разных регионах</div>'
        persp_section += '<div class="perspectives">' + persp_html + '</div>'

        s = STORY.replace("__NUM__", str(idx))
        s = s.replace("__TITLE_EN__", title_en)
        s = s.replace("__TITLE_RU__", title_ru)
        s = s.replace("__SUMMARY__", summary_html)
        s = s.replace("__COMPARISON__", comp_html)
        s = s.replace("__PERSPECTIVES__", persp_section)
        s = s.replace("__REGIONS_COUNT__", str(len(by_region)))
        s = s.replace("__KEYWORDS__", " #".join(top_kw) if top_kw else "news")
        stories += s

    if not stories:
        stories = '<div class="no-news"><h2>Loading news...</h2></div>'

    html = load_template()
    utc_now = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    ai_tag = "DeepSeek" if deepseek_key else "none"
    html = html.replace("__UPDATE_TIME__", utc_now)
    html = html.replace("__TOTAL_STORIES__", str(min(len(clusters), 10)))
    html = html.replace("__TOTAL_SOURCES__", str(len(sources)))
    html = html.replace("__REGIONS_COVERED__", str(len(regions)))
    html = html.replace("__STORIES__", stories)
    html = html.replace("__AI_MODEL__", ai_tag)
    html = html.replace("__AI_BADGE__",
        f'<span class="ai-badge">AI: {ai_tag}</span>' if deepseek_key else "")

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated: {out}")
