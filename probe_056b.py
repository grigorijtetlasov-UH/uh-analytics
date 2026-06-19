import re, requests
HDR={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36","Accept-Language":"uk,ru;q=0.9"}
url="https://www.056.ua/catalog/index/553023/sofino-sofino-internet-magazin-mebeli/comments"
r=requests.get(url, headers=HDR, timeout=25); html=r.text
print("len", len(html))
print("'review-row row':", html.count('review-row row'), "| 'review-row':", html.count('review-row'),
      "| 'rateline-item':", html.count('rateline-item'), "| 'recommend':", html.count('recommend'))

print("\n=== перші 2 блоки review-row row (обрізано ~1700) ===")
idxs=[m.start() for m in re.finditer(r'<div class="review-row row"', html)]
print("стартів review-row row:", len(idxs))
for k,i in enumerate(idxs[:2]):
    print(f"\n--- [{k}] ---\n", re.sub(r'\s+',' ', html[i:i+1700]))

print("\n=== агрегат рейтингу (recommend-section / rateline) ===")
i=html.find('recommend-section')
if i<0: i=html.find('rateline')
print(re.sub(r'\s+',' ', html[max(0,i-250):i+700]) if i>0 else "—")

print("\n=== ключові значення ===")
for kw in ['ratingValue','data-rate','rate-value','rateline-count','середн','Відгуки','star-rating','active']:
    j=html.find(kw)
    if j>0: print(f"[{kw}]:", re.sub(r'\s+',' ', html[max(0,j-120):j+160]))

print("\n=== пагінація ===")
pgs=re.findall(r'href="([^"]*(?:page|/comments)[^"]*)"', html)
print("лінки з page/comments:", sorted(set(p for p in pgs if 'page' in p.lower()))[:8])
