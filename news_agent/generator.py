import os
from datetime import datetime
from collections import defaultdict
from .analyzer import extract_keywords

def load_template():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
    with open(path, encoding="utf-8") as f:
        return f.read()

TEMPLATE = load_template()

STORY = '''<div class="story">
  <div class="story-card">
    <div class="story-header">
      <div class="story-number">__NUM__</div>
      <div class="story-title">__TITLE__</div>
    </div>
    <div class="story-body">
      __PERSPECTIVES__
    </div>
    <div class="story-footer">
      <span><strong>__REGIONS_COUNT__</strong> regions cover this</span>
      <span class="tag">#__KEYWORDS__</span>
    </div>
  </div>
</div>'''

PERSP = '''<div class="perspective" style="--region-color: __COLOR__">
  <span class="region-tag">__REGION__</span>
  <div class="meta">
    <a href="__LINK__" target="_blank" rel="noopener">__SOURCE__</a>
  </div>
  <div class="headline">__HEADLINE__</div>
  <div class="keywords">__KWS__</div>
</div>'''

def generate(clusters, output_dir="output"):
    stories = ""
    sources = set()
    regions = set()

    for idx, cluster in enumerate(clusters[:10], 1):
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
            p = PERSP
            for old, new in [("__COLOR__", s["region_color"]), ("__REGION__", rl),
                             ("__LINK__", s["link"]), ("__SOURCE__", s["source_name"]),
                             ("__HEADLINE__", s["title"]), ("__KWS__", kw_html)]:
                p = p.replace(old, new)
            persp_html += p

        if not persp_html:
            continue

        title = cluster[0]["title"]
        if len(title) > 120: title = title[:117] + "..."

        kw_all = set()
        for a in cluster:
            kw_all.update(extract_keywords(a["title"], a["summary"]))
        top_kw = list(kw_all)[:5]

        s = STORY
        for old, new in [("__NUM__", str(idx)), ("__TITLE__", title),
                         ("__PERSPECTIVES__", '<div class="perspectives-title">Coverage across regions</div><div class="perspectives">' + persp_html + '</div>'),
                         ("__REGIONS_COUNT__", str(len(by_region))),
                         ("__KEYWORDS__", " #".join(top_kw) if top_kw else "news")]:
            s = s.replace(old, new)
        stories += s

    if not stories:
        stories = '<div class="no-news"><h2>Loading news...</h2></div>'

    html = TEMPLATE
    for old, new in [("__UPDATE_TIME__", datetime.now().strftime("%d %B %Y, %H:%M UTC")),
                     ("__TOTAL_STORIES__", str(min(len(clusters), 10))),
                     ("__TOTAL_SOURCES__", str(len(sources))),
                     ("__REGIONS_COVERED__", str(len(regions))),
                     ("__STORIES__", stories)]:
        html = html.replace(old, new)

    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated: {out}")
