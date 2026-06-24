import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from news_agent.fetcher import fetch_all
from news_agent.analyzer import cluster_news
from news_agent.generator import generate

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

openrouter_key = os.environ.get("OPENROUTER_KEY", "").strip()
deepseek_key = os.environ.get("DEEPSEEK_KEY", "").strip()
if not deepseek_key:
    deepseek_key = config.get("deepseek_api_key", "").strip()

ai_key = openrouter_key or deepseek_key
ai_provider = "openrouter" if openrouter_key else ("deepseek" if deepseek_key else None)

print("NewsAgentPT78")
print("=" * 40)
if ai_provider == "openrouter":
    print(f"  AI: OpenRouter enabled (key: {openrouter_key[:8]}...)")
elif ai_provider == "deepseek":
    print(f"  AI: DeepSeek enabled (key: {deepseek_key[:8]}...)")
else:
    print("  AI: DISABLED (no API key)")

articles = fetch_all(config)

if not articles:
    print("No news. Generating empty page.")
    generate([], "output", ai_key=ai_key, ai_provider=ai_provider)
    sys.exit(0)

clusters = cluster_news(articles)
russia_clusters = [c for c in clusters if any(a["region"] == "russia" for a in c)]
other_clusters = [c for c in clusters if not any(a["region"] == "russia" for a in c)]
min_russia = config.get("min_russia_news", 3)
max_news = config.get("max_news_per_day", 10)
selected = russia_clusters[:min_russia]
remaining = max_news - len(selected)
if remaining > 0:
    selected += other_clusters[:remaining]

print(f"Russia stories: {len(russia_clusters)}, in feed: {len(selected)}")
generate(selected, "output", ai_key=ai_key, ai_provider=ai_provider)
