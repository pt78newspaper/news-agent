import re
from collections import defaultdict

STOP_WORDS = {
    "the","a","an","and","or","but","in","on","at","to","for",
    "of","by","with","from","as","is","are","was","were","be",
    "been","being","have","has","had","do","does","did","will",
    "would","could","should","may","might","shall","can","need",
    "it","its","this","that","these","those","i","you","he",
    "she","we","they","my","your","his","her","our","their",
    "not","no","nor","so","up","out","if","about","into","than",
    "also","just","more","some","very","after","before","between",
    "over","under","again","further","then","once","here","there",
    "when","where","why","how","all","each","every","both","few",
    "most","other","such","only","own","same","too","very",
    "says","said","report","reported","according","new","news",
    "first","last","after","year","years","time","one","two",
}

POSITIVE = {
    "deal","agreement","peace","success","growth","boost","support",
    "aid","help","improve","breakthrough","progress","cooperation",
    "victory","win","good","strong","stable","recovery","hope",
    "opportunity","development","investment","partnership"
}

NEGATIVE = {
    "war","conflict","crisis","sanctions","death","attack","strike",
    "kill","destroy","damage","threat","danger","fear","loss",
    "fail","failure","problem","disaster","emergency","collapse",
    "violence","weapon","military","blame","accuse","condemn"
}

def tokenize(text):
    return [t for t in re.findall(r"[a-zA-Z\u0400-\u04FF]{3,}", text.lower()) if t not in STOP_WORDS]

def extract_keywords(title, summary=""):
    freq = defaultdict(int)
    for t in tokenize(title + " " + summary):
        freq[t] += 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:10]]

def detect_sentiment(text):
    words = tokenize(text)
    pos = sum(1 for w in words if w in POSITIVE)
    neg = sum(1 for w in words if w in NEGATIVE)
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"

def cluster_news(articles, threshold=0.28):
    clusters = []
    used = set()
    for i, a in enumerate(articles):
        if i in used: continue
        cluster = [a]
        used.add(i)
        for j in range(i+1, len(articles)):
            if j in used: continue
            kw_i = set(extract_keywords(a["title"], a["summary"]))
            kw_j = set(extract_keywords(articles[j]["title"], articles[j]["summary"]))
            overlap = len(kw_i & kw_j)
            if overlap >= 2:
                cluster.append(articles[j])
                used.add(j)
        clusters.append(cluster)
    clusters.sort(key=lambda c: len(c), reverse=True)
    return clusters

def analyze_perspectives(cluster):
    regions = defaultdict(list)
    for a in cluster:
        regions[a["region_label"]].append(a)

    results = []
    all_sentiments = {}
    region_keywords = {}

    for rl, arts in regions.items():
        kw = set()
        titles = []
        for a in arts:
            kw.update(extract_keywords(a["title"], a["summary"])[:5])
            titles.append(a["title"])
        combined = " ".join(titles)
        sentiment = detect_sentiment(combined)
        all_sentiments[rl] = sentiment
        region_keywords[rl] = list(kw)[:5]
        results.append({
            "region": rl,
            "articles": arts,
            "keywords": list(kw)[:5],
            "sentiment": sentiment,
            "color": arts[0]["region_color"],
        })

    present = {r["region"] for r in results}
    comparison = []

    ru_label = [r for r in present if "Рос" in r or "Rossiya" in r.replace("Rossiya","Россия")]
    ru_label = ru_label[0] if ru_label else "Россия"
    west_label = [r for r in present if "Зап" in r or "Zapad" in r.replace("Zapad","Запад")]
    west_label = west_label[0] if west_label else "Запад"

    if ru_label in all_sentiments and west_label in all_sentiments:
        rs = all_sentiments[ru_label]
        ws = all_sentiments[west_label]
        if rs != ws:
            comparison.append(f"Россия и Запад освещают в разном ключе: {rs} vs {ws}")
        else:
            comparison.append(f"Россия и Запад оценивают ситуацию сходно ({rs}).")

    if ru_label in region_keywords and west_label in region_keywords:
        ru_kw = set(region_keywords[ru_label])
        west_kw = set(region_keywords[west_label])
        only_ru = ru_kw - west_kw
        only_west = west_kw - ru_kw
        if only_ru:
            comparison.append(f"Россия акцентирует: {', '.join(list(only_ru)[:3])}.")
        if only_west:
            comparison.append(f"Запад акцентирует: {', '.join(list(only_west)[:3])}.")

    brics = {r for r in present if r in ("Россия", "Китай", "Индия", "Индонезия")}
    if len(brics) >= 2 and west_label in present:
        brics_sentiments = [all_sentiments[r] for r in brics if r in all_sentiments]
        west_sent = all_sentiments.get(west_label, "")
        if brics_sentiments and west_sent and any(s != west_sent for s in brics_sentiments):
            comparison.append("Страны БРИКС придерживаются иного взгляда, чем Запад.")

    return results, comparison
