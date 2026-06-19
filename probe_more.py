import re, json, requests
HDR={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36","Accept-Language":"uk,ru;q=0.9"}
URLS=[
  ("Hotline Matrasroll", "https://hotline.ua/ua/yp/35999/"),
  ("Hotline Matrasroll reviews", "https://hotline.ua/ua/yp/35999/reviews/"),
  ("056.ua Sofino", "https://www.056.ua/catalog/index/553023/sofino-sofino-internet-magazin-mebeli/comments"),
]
for name,url in URLS:
    print("="*64); print(name, "→", url)
    try:
        r=requests.get(url, headers=HDR, timeout=25); html=r.text
        print("  HTTP", r.status_code, "| len", len(html))
        lds=re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S)
        print("  JSON-LD блоків:", len(lds))
        for i,ld in enumerate(lds):
            try: d=json.loads(ld.strip())
            except Exception as e: print(f"    [{i}] parse-fail {e}"); continue
            for o in (d if isinstance(d,list) else [d]):
                if not isinstance(o,dict): continue
                ar=o.get("aggregateRating"); rv=o.get("review")
                if ar or rv:
                    arr={k:ar.get(k) for k in ('ratingValue','reviewCount','ratingCount','bestRating')} if isinstance(ar,dict) else ar
                    nrv=len(rv) if isinstance(rv,list) else (1 if rv else 0)
                    print(f"    [{i}] @type={o.get('@type')} aggregateRating={arr} reviews={nrv}")
                    if isinstance(rv,list) and rv: print("        review[0] keys:", list(rv[0].keys()))
        if not lds:
            print("  (нема JSON-LD) згадки:", {w:bool(re.search(w,html,re.I)) for w in ('рейтинг','оцінк','відгук','rating','data-rating')})
    except Exception as e:
        print("  FAIL:", e)
