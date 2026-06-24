import os, re
from datetime import datetime
from collections import defaultdict
from .analyzer import extract_keywords, analyze_perspectives

def load_template():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
    with open(path, encoding="utf-8") as f:
        return f.read()

TEMPLATE = load_template()

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

def is_russian(text):
    return bool(re.search(r'[\u0400-\u04FF]', text))

def generate(clusters, output_dir="output"):
    stories = ""
    sources = set()
    regions = set()

    for idx, cluster in enumerate(clusters[:10], 1):
        persp_html = ""

        perspectives, comparisons = analyze_perspectives(cluster)

        for p in perspectives:
            s = p["articles"][0]
            kw_html = " ".join(f'<span class="keyword">{k}</span>' for k in p["keywords"])
            p_html = PERSP.replace("__COLOR__", p["color"])
            p_html = p_html.replace("__REGION__", p["region"])
            p_html = p_html.replace("__LINK__", s["link"])
            p_html = p_html.replace("__SOURCE__", s["source_name"])
            p_html = p_html.replace("__HEADLINE__", s["title"])
            p_html = p_html.replace("__KWS__", kw_html)
            persp_html += p_html
            sources.add(s["source_name"])
            regions.add(p["region"])

        if not persp_html:
            continue

        en_articles = [a for a in cluster if not is_russian(a["title"])]
        ru_articles = [a for a in cluster if is_russian(a["title"])]
        title_en = en_articles[0]["title"] if en_articles else ru_articles[0]["title"]
        title_ru = ru_articles[0]["title"] if ru_articles else title_en

        if len(title_en) > 100:
            title_en = title_en[:97] + "..."
        if len(title_ru) > 100:
            title_ru = title_ru[:97] + "..."

        kw_all = set()
        for a in cluster:
            kw_all.update(extract_keywords(a["title"], a["summary"])[:3])
        top_kw = list(kw_all)[:5]

        comparison_html = ""
        if comparisons:
            items = ""
            for c in comparisons:
                items += f'<div class="compare-item">{c}</div>'
            comparison_html = f'<div class="comparison"><div class="compare-title">Сравнение освещения</div>{items}</div>'

        s = STORY.replace("__NUM__", str(idx))
        s = s.replace("__TITLE_EN__", title_en)
        s = s.replace("__TITLE_RU__", title_ru)

        persp_section = '<div class="perspectives-title">Освещение в разных регионах</div>'
        persp_section += '<div class="perspectives">' + persp_html + '</div>'
        if comparison_html:
            persp_section += comparison_html
        s = s.replace("__PERSPECTIVES__", persp_section)
        s = s.replace("__REGIONS_COUNT__", str(len(perspectives)))
        s = s.replace("__KEYWORDS__", " #".join(top_kw) if top_kw else "news")
        stories += s

    if not stories:
        stories = '<div class="no-news"><h2>Loading news...</h2></div>'

    html = TEMPLATE.replace("__UPDATE_TIME__", datetime.now().strftime("%d %B %Y, %H:%M UTC"))
    html = html.replace("__TOTAL_STORIES__", str(min(len(clusters), 10)))
    html = html.replace("__TOTAL_SOURCES__", str(len(sources)))
    html = html.replace("__REGIONS_COVERED__", str(len(regions)))
    html = html.replace("__STORIES__", stories)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated: {out}")
