import os, json, time, datetime
from pathlib import Path
from collections import Counter
import requests
OUT = Path("docs/reputation_google.json")
KEY = os.environ.get("GOOGLE_PLACES_KEY", "")
BRANDS = [
    {"key": "matrasroll", "name": "Matrasroll", "place_id": "ChIJ116jiRLb1EARi8yUEHPU8qA"},
    {"key": "amebli",     "name": "Amebli",     "place_id": "ChIJf1Up_9zb1EARXpwEHhfJZ1w"},
]
def fetch(pid):
    r = requests.get("https://maps.googleapis.com/maps/api/place/details/json",
                     params={"place_id": pid, "fields": "name,rating,user_ratings_total,reviews,url",
                             "language": "uk", "key": KEY}, timeout=25)
    j = r.json()
    if j.get("status") != "OK":
        raise RuntimeError(f"{j.get('status')}: {j.get('error_message', '')}")
    return j["result"]
def main():
    if not KEY:
        print("❌ нема GOOGLE_PLACES_KEY у .env"); raise SystemExit(1)
    out = {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "source": "google", "brands": {}}
    for b in BRANDS:
        try:
            res = fetch(b["place_id"])
        except Exception as e:
            print(f"  {b['key']}: FAIL — {e}"); continue
        revs = []
        for rv in res.get("reviews", []):
            t = rv.get("time"); d = datetime.date.fromtimestamp(t).isoformat() if t else ""
            revs.append({"author": rv.get("author_name", "—"), "date": d, "stars": rv.get("rating"),
                         "text": (rv.get("text") or "").strip()[:600]})
        dist = Counter(r["stars"] for r in revs if r["stars"]); n = sum(dist.values())
        pos = round((dist.get(5,0)+dist.get(4,0))/n*100) if n else 0
        neu = round(dist.get(3,0)/n*100) if n else 0
        neg = round((dist.get(2,0)+dist.get(1,0))/n*100) if n else 0
        out["brands"][b["key"]] = {"name": b["name"], "rating": res.get("rating"), "count": res.get("user_ratings_total"),
            "sample_n": n, "pos": pos, "neu": neu, "neg": neg, "url": res.get("url", ""), "reviews": revs}
        print(f"  {b['key']}: {res.get('rating')}★ · {res.get('user_ratings_total')} відгуків · вибірка {n} (+{pos}% ~{neu}% −{neg}%)")
        time.sleep(0.3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ {OUT} ({OUT.stat().st_size} байт)")
main()
