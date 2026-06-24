import re
from collections import defaultdict
from difflib import SequenceMatcher

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

def tokenize(text):
    tokens = re.findall(r"[a-zA-ZЀ-ӿ]{3,}", text.lower())
    return [t for t in tokens if t not in STOP_WORDS]

def extract_keywords(title, summary=""):
    freq = defaultdict(int)
    for t in tokenize(title + " " + summary):
        freq[t] += 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:10]]

def title_similarity(t1, t2):
    return SequenceMatcher(None,
        re.sub(r"[^\w\s]","",t1.lower()),
        re.sub(r"[^\w\s]","",t2.lower())).ratio()

def cluster_news(articles, threshold=0.30):
    clusters = []
    used = set()
    for i, a in enumerate(articles):
        if i in used: continue
        cluster = [a]
        used.add(i)
        for j in range(i+1, len(articles)):
            if j in used: continue
            if title_similarity(a["title"], articles[j]["title"]) >= threshold:
                cluster.append(articles[j])
                used.add(j)
        clusters.append(cluster)
    clusters.sort(key=lambda c: len(c), reverse=True)
    return clusters
