#!/usr/bin/env python3
# probe_vidhuk.py — РАЗОВИЙ probe: дивимось структуру сторінок Vidhuk,
# щоб написати надійний парсер. Нічого не пише, лише фетчить і друкує.
# Запуск на сервері:  ./run.sh probe_vidhuk.py
import re, json
import requests

URLS = {
    "matrasroll": "https://www.vidhuk.ua/uk/internet-magazin-matrasroll",
    "amebli":     "https://www.vidhuk.ua/uk/ameblicomua",
    "sofino":     "https://www.vidhuk.ua/uk/internet-magazina-mebeli-sofinoua",
}
H = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "uk,uk-UA;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml",
}

for name, url in URLS.items():
    print("\n" + "=" * 72)
    try:
        r = requests.get(url, headers=H, timeout=25)
        html = r.text
    except Exception as e:
        print(f"{name}: FETCH FAIL — {e}")
        continue
    print(f"{name} :: {url}")
    print(f"  HTTP {r.status_code} :: {len(html)} символів :: ct={r.headers.get('content-type','?')}")

    # 1) JSON-LD — найнадійніше джерело (schema.org Review/AggregateRating)
    lds = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE)
    print(f"  JSON-LD блоків: {len(lds)}")
    for i, ld in enumerate(lds):
        try:
            j = json.loads(ld.strip())
        except Exception as e:
            print(f"    [{i}] не-JSON ({e}): {ld.strip()[:150]}")
            continue
        for o in (j if isinstance(j, list) else [j]):
            if not isinstance(o, dict):
                continue
            print(f"    [{i}] @type={o.get('@type')} keys={list(o.keys())}")
            ar = o.get("aggregateRating")
            if isinstance(ar, dict):
                print(f"        aggregateRating = {json.dumps(ar, ensure_ascii=False)}")
            rv = o.get("review")
            if rv:
                rv = rv[:1] if isinstance(rv, list) else [rv]
                if rv:
                    print(f"        review[0] keys = {list(rv[0].keys())}")
                    print(f"        review[0] = {json.dumps(rv[0], ensure_ascii=False)[:400]}")

    # 2) рейтинг + кількість з HTML (кандидати, якщо JSON-LD нема/бідний)
    print("  rating-cand:", re.findall(r'ratingValue["\']?[:\s>]+["\']?([0-9]+[.,]?[0-9]*)', html)[:3])
    print("  count-cand :", re.findall(r'(\d[\d\s]*)\s*відгук', html)[:6])
    # розподіл по зірках (іноді в розмітці графіка)
    print("  star-cand  :", re.findall(r'(Відмінно|Добре|Нормально|Погано|Жахливо)[^0-9]{0,40}(\d+)', html)[:6])

    # 3) перший блок відгуку (для CSS-селекторів)
    m = re.search(
        r'<[^>]+(itemprop=["\']review["\']|class=["\'][^"\']*(review|comment|otzyv|feedback|item-review)[^"\']*["\'])',
        html, re.IGNORECASE)
    if m:
        s = max(0, m.start())
        print("  --- HTML навколо 1-го відгуку (1000 симв) ---")
        print(html[s:s + 1000])
    else:
        print("  ⚠️ блок відгуку за тегами НЕ знайдено (можливо AJAX-підвантаження).")
        b = re.search(r'<body', html, re.IGNORECASE)
        if b:
            print("  --- перші 700 симв <body> ---")
            print(html[b.start():b.start() + 700])
