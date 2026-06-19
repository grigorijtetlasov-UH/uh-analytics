#!/usr/bin/env python3
# reputation_056.py — відгуки брендів з 056.ua (CITYSITES) через jsonrpc showComments.
# Пише docs/reputation_056.json. Запуск: ./run.sh reputation_056.py
import json, re, datetime
from pathlib import Path
from collections import Counter
import requests

OUT = Path("docs/reputation_056.json")
# pageId беремо з URL картки магазину: 056.ua/catalog/index/<ID>/.../comments
BRANDS = [
    {"key": "sofino", "name": "Sofino", "page_id": 553023,
     "url": "https://www.056.ua/catalog/index/553023/sofino-sofino-internet-magazin-mebeli/comments"},
    # Matrasroll/Amebli — додамо як знайдемо їхні pageId на 056/044
]
HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Content-Type": "application/json-rpc",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
MON = {'січ': 1, 'лют': 2, 'бер': 3, 'кві': 4, 'тра': 5, 'чер': 6,
       'лип': 7, 'сер': 8, 'вер': 9, 'жов': 10, 'лис': 11, 'гру': 12}


def _strip(t):
    return re.sub(r'<[^>]+>', '', t or '').strip()


def _date(s):
    m = re.match(r'(\d{1,2})\s+([а-яіїє]{3})', s or '', re.I)
    y = re.search(r'(20\d{2})', s or '')
    if not (m and y):
        return ""
    mo = MON.get(m.group(2).lower()[:3])
    return f"{y.group(1)}-{mo:02d}-{int(m.group(1)):02d}" if mo else ""


def parse_reviews(html):
    """Повертає список {author,date,text,rating(/5 або None)} з result.html."""
    blocks = [b for b in re.split(r'(?=<div class="comment[^"]*" data-id=")', html)
              if re.match(r'<div class="comment[^"]*" data-id=', b)]
    out = []
    for b in blocks:
        u = re.search(r'comment__username">(.*?)</div>', b, re.S)
        name = ""
        if u:
            a = re.search(r'<a[^>]*>(.*?)</a>', u.group(1), re.S)
            name = re.sub(r'\s+', ' ', _strip(a.group(1) if a else u.group(1)))[:60]
        tm = re.search(r'comment__time[^"]*">\s*(.*?)\s*</div>', b, re.S)
        txt = re.search(r'comment__text[^"]*">(.*?)</p>', b, re.S)
        rates = [(seg.count('bottom-rating__point active'), seg.count('bottom-rating__point'))
                 for seg in re.findall(r'<div class="bottom-rating">(.*?)</div>', b, re.S)]
        rating = None
        if rates:
            a_ = sum(x[0] for x in rates); t_ = sum(x[1] for x in rates)
            if t_:
                rating = round(a_ / t_ * 5, 2)
        out.append({"author": name or "—", "date": _date(tm and tm.group(1)),
                    "text": re.sub(r'\s+', ' ', _strip(txt and txt.group(1)))[:600],
                    "rating": rating})
    return out


def fetch(page_id):
    payload = {"jsonrpc": "2.0", "method": "showComments",
               "params": {"pageType": "catalog", "pageId": page_id, "params": []}}
    r = requests.post(f"https://www.056.ua/catalog-full/{page_id}/jsonrpc",
                      headers=HDR, data=json.dumps(payload), timeout=60)
    r.raise_for_status()
    return r.json()["result"]["html"]


def main():
    out = {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "source": "056", "brands": {}}
    for b in BRANDS:
        try:
            html = fetch(b["page_id"])
        except Exception as e:
            print(f"  {b['key']}: FAIL — {e}"); continue
        revs = parse_reviews(html)
        rated = [r for r in revs if r["rating"] is not None]
        total = len(revs)
        if not rated:
            print(f"  {b['key']}: відгуків {total}, але без оцінок — пропуск"); continue
        avg = round(sum(r["rating"] for r in rated) / len(rated), 1)
        stars = Counter(round(r["rating"]) for r in rated)
        n = len(rated)
        pos = round(sum(1 for r in rated if r["rating"] >= 4) / n * 100)
        neg = round(sum(1 for r in rated if r["rating"] <= 2) / n * 100)
        neu = max(0, 100 - pos - neg)
        # для віджета: свіжі оцінені відгуки (для снапшотів/негативу)
        sample = sorted(rated, key=lambda r: r["date"], reverse=True)[:60]
        sample_out = [{"author": r["author"], "date": r["date"],
                       "stars": round(r["rating"]), "text": r["text"]} for r in sample]
        out["brands"][b["key"]] = {
            "name": b["name"], "rating": avg, "count": total,
            "sample_n": n, "pos": pos, "neu": neu, "neg": neg,
            "dist": {str(k): stars.get(k, 0) for k in range(5, 0, -1)},
            "url": b["url"], "reviews": sample_out,
        }
        print(f"  {b['key']}: {avg}★ · {total} відгуків (оцінених {n}) · +{pos}% ~{neu}% −{neg}%")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ {OUT} ({OUT.stat().st_size} байт)")


if __name__ == "__main__":
    main()
