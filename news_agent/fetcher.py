import feedparser, requests, hashlib
from datetime import datetime, timezone
from dateutil import parser as dateparser
from urllib.parse import urlparse

USER_AGENT = "NewsAgentPT78/1.0"

def fetch_rss(url, timeout=20):
    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = []
        for entry in feed.entries:
            pub = None
            if hasattr(entry, "published"):
                try: pub = dateparser.parse(entry.published)
                except: pub = datetime.now(timezone.utc)
            else:
                pub = datetime.now(timezone.utc)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            link = getattr(entry, "link", "")
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            entries.append({
                "title": title, "link": link,
                "summary": summary or content,
                "published": pub,
                "source_url": url,
                "source_name": urlparse(url).netloc,
                "id": hashlib.md5((title + link).encode()).hexdigest(),
            })
        return entries
    except Exception as e:
        print(f"  [WARN] {urlparse(url).netloc}: {e}")
        return []

def fetch_all(config):
    all_news = []
    seen = set()
    for rkey, rcfg in config["sources"].items():
        print(f"[{rcfg['label']}] {len(rcfg['feeds'])} feeds...")
        for url in rcfg["feeds"]:
            for e in fetch_rss(url):
                if e["id"] not in seen:
                    e["region"] = rkey
                    e["region_label"] = rcfg["label"]
                    e["region_color"] = rcfg.get("color", "#333")
                    all_news.append(e)
                    seen.add(e["id"])
    all_news.sort(key=lambda x: x["published"], reverse=True)
    print(f"Total: {len(all_news)} articles")
    return all_news
