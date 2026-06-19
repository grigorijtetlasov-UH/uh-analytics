import re, requests
from collections import Counter
HDR={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36","Accept-Language":"uk,ru;q=0.9"}
url="https://www.056.ua/catalog/index/553023/sofino-sofino-internet-magazin-mebeli/comments"

print("=== A) звичайний GET vs AJAX (X-Requested-With) ===")
r1=requests.get(url, headers=HDR, timeout=25)
r2=requests.get(url, headers={**HDR,"X-Requested-With":"XMLHttpRequest"}, timeout=25)
print("  звичайний:", len(r1.text), "| ajax:", len(r2.text), "| різні:", len(r1.text)!=len(r2.text))
html=r1.text

print("\n=== B) дати у HTML (ознака реальних відгуків) ===")
dates=re.findall(r'\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\s+(?:січ|лют|бер|кві|тра|черв|лип|серп|вер|жов|лис|груд|янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)', html, re.I)
print("  дат:", len(dates), "| приклади:", dates[:8])

print("\n=== C) інлайн-JS ендпоінти ===")
seen=set()
for kw in ['ajax','/comment','url:','data-url','data-href','dynamic-tab','loadMore','getComment','page=']:
    for m in re.finditer(re.escape(kw), html):
        seg=re.sub(r'\s+',' ', html[m.start()-10:m.start()+130])
        if ('/' in seg or 'http' in seg or 'url' in seg.lower()) and seg not in seen:
            seen.add(seg); print(f"  [{kw}] …{seg}"); break

print("\n=== D) класи author/user/date/msg/item ===")
for pat in ['author','user','nickname','date','msg','review-text','comment-item','review-item']:
    cls=re.findall(r'class="([^"]*'+pat+r'[^"]*)"', html, re.I)
    if cls: print(f"  '{pat}':", Counter(cls).most_common(4))

print("\n=== E) середній рейтинг у HTML? ===")
for kw in ['itemprop="ratingValue"','ratingValue','averageRating','rating-value','rating__value','大','/5','зірок','із 5']:
    j=html.find(kw)
    if j>0: print(f"  [{kw}]:", re.sub(r'\s+',' ', html[max(0,j-100):j+120]))
