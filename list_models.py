import os, json, urllib.request

key = os.environ.get("GPTUNNEL_KEY", "")
req = urllib.request.Request(
    "https://gptunnel.ru/v1/models",
    headers={"Authorization": f"Bearer {key}"}
)
try:
    data = json.loads(urllib.request.urlopen(req).read())
    models = data.get("data", [])
    print(f"== MODELS ({len(models)}) ==")
    for m in models:
        print(m.get("id", ""))
except Exception as e:
    print(f"models endpoint failed: {e}")
