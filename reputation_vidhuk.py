#!/usr/bin/env python3
# reputation_vidhuk.py — збирає репутацію брендів з Vidhuk.ua (через JSON-LD schema.org).
# Пише docs/reputation.json (поточний стан) + docs/reputation_trend.json (forward-тренд рейтингу).
import re, json, time, hashlib, datetime
from pathlib import Path
from collections import Counter, defaultdict
import requests

OUT   = Path("docs/reputation.json")
TREND = Path("docs/reputation_trend.json")

BRANDS = [
    {"key": "matrasroll", "name": "Matrasroll", "color": "#00d68f",
     "url": "https://www.vidhuk.ua/uk/internet-magazin-matrasroll"},
    {"key": "amebli", "name": "Amebli", "color": "#ff6b6b",
     "url": "https://www.vidhuk.ua/uk/ameblicomua"},
    {"key": "sofino", "name": "Sofino", "color": "#4dabf7",
     "url": "https://www.vidhuk.ua/uk/internet-magazina-mebeli-sofinoua"},
]
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
     "Accept-Language": "uk,uk-UA;q=0.9,en;q=0.8",
     "Accept": "text/html,application/xhtml+xml"}

TARGET_REVIEWS = 100
MAX_PAGES      = 6
MON_SHORT = {1:"Січ",2:"Лют",3:"Бер",4:"Кві",5:"Тра",6:"Чер",
             7:"Лип",8:"Сер",9:"Вер",10:"Жов",11:"Лис",12:"Гру"}


def _jsonld_store(html):
    for ld in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                         html, re.DOTALL | re.IGNORECASE):
        try:
            j = json.loads(ld.strip())
        except Exception:
            continue
        for o in (j if isinstance(j, list) else [j]):
            if isinstance(o, dict) and isinstance(o.get("aggregateRating"), dict):
                return o
    return None


def _norm_reviews(obj):
    out = []
    rv = obj.get("review") or []
    if isinstance(rv, dict):
        rv = [rv]
    for r in rv:
        if not isinstance(r, dict):
            continue
        rr = r.get("reviewRating") or {}
        try:
            stars = int(float(rr.get("ratingValue"))) if rr.get("ratingValue") is not None else None
        except Exception:
            stars = None
        au = r.get("author") or {}
        out.append({
            "author": (au.get("name") if isinstance(au, dict) else str(au)) or "—",
            "date":   (r.get("datePublished") or "")[:10],
            "stars":  stars,
            "title":  (r.get("name") or "")[:120],
            "text":   (r.get("reviewBody") or "").strip()[:600],
        })
    return out


def _rid(r):
    return hashlib.md5((r["author"] + r["date"] + r["text"][:60]).encode("utf-8")).hexdigest()


def collect_brand(b):
    base = b["url"]
    rating = count = None
    reviews, pages_used = {}, 0
    for page in range(1, MAX_PAGES + 1):
        url = base if page == 1 else f"{base}?page={page}"
        try:
            html = requests.get(url, headers=H, timeout=25).text
        except Exception as e:
            print(f"    {b['key']} p{page}: fetch fail — {e}")
            break
        obj = _jsonld_store(html)
        if not obj:
            print(f"    {b['key']} p{page}: JSON-LD не знайдено")
            break
        if rating is None:
            ar = obj["aggregateRating"]
            try: rating = float(ar.get("ratingValue"))
            except Exception: rating = None
            try: count = int(ar.get("reviewCount") or ar.get("ratingCount"))
            except Exception: count = None
        new = 0
        for r in _norm_reviews(obj):
            k = _rid(r)
            if k not in reviews:
                reviews[k] = r; new += 1
        pages_used = page
        if new == 0:
            break
        if len(reviews) >= TARGET_REVIEWS:
            break
        time.sleep(0.6)

    revs = sorted(reviews.values(), key=lambda x: x["date"], reverse=True)
    dist = Counter(r["stars"] for r in revs if r["stars"])
    n = sum(dist.values())
    pos = round((dist.get(5,0)+dist.get(4,0))/n*100) if n else 0
    neu = round(dist.get(3,0)/n*100) if n else 0
    neg = round((dist.get(2,0)+dist.get(1,0))/n*100) if n else 0

    by_m = defaultdict(list)
    for r in revs:
        if r["stars"] and len(r["date"]) >= 7:
            by_m[r["date"][:7]].append(r["stars"])
    months = sorted(by_m.keys())[-6:]
    monthly = [{"m": MON_SHORT.get(int(m[5:7]), m), "ym": m,
                "avg": round(sum(by_m[m])/len(by_m[m]), 2), "n": len(by_m[m])} for m in months]

    return {
        "name": b["name"], "color": b["color"], "url": base,
        "rating": rating, "count": count,
        "sample_n": n, "pages": pages_used,
        "dist": {str(s): dist.get(s, 0) for s in (5,4,3,2,1)},
        "pos": pos, "neu": neu, "neg": neg,
        "monthly": monthly,
        "reviews": revs[:30],
    }


def main():
    out = {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "source": "vidhuk.ua", "brands": {}}
    for b in BRANDS:
        print(f"  {b['key']}: {b['url']}")
        d = collect_brand(b)
        out["brands"][b["key"]] = d
        print(f"    -> {d['rating']} зірок · всього {d['count']} · вибірка {d['sample_n']} "
              f"({d['pages']} стор.) · +{d['pos']}% ~{d['neu']}% -{d['neg']}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK {OUT} ({OUT.stat().st_size} bytes)")

    try:
        tr = json.loads(TREND.read_text(encoding="utf-8")) if TREND.exists() else {}
    except Exception:
        tr = {}
    today = datetime.date.today().isoformat()
    for k, d in out["brands"].items():
        arr = [x for x in tr.get(k, []) if x.get("date") != today]
        if d["rating"] is not None:
            arr.append({"date": today, "rating": d["rating"], "count": d["count"]})
        tr[k] = arr[-180:]
    TREND.write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
    print(f"OK {TREND} (forward-trend updated)")


if __name__ == "__main__":
    main()
