import re, requests
from collections import Counter
HDR={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36","Accept-Language":"uk,ru;q=0.9"}
url="https://www.056.ua/catalog/index/553023/sofino-sofino-internet-magazin-mebeli/comments"
r=requests.get(url, headers=HDR, timeout=25); html=r.text
print("HTTP", r.status_code, "| len", len(html))

print("\n=== 1) мікродата itemprop ===")
for ip in ['ratingValue','reviewCount','ratingCount','bestRating','review','author','reviewBody','datePublished','name']:
    txt=re.findall(r'itemprop=["\']'+ip+r'["\'][^>]*>([^<]{0,60})', html)
    cont=re.findall(r'itemprop=["\']'+ip+r'["\'][^>]*content=["\']([^"\']{0,60})', html)
    if txt or cont: print(f"  {ip}: text={txt[:2]} content={cont[:2]}")

print("\n=== 2) класи коментарів/рейтингу ===")
for pat in ['comment','review','feedback','otzyv','rating','star','rate']:
    cls=re.findall(r'class=["\']([^"\']*'+pat+r'[^"\']*)["\']', html, re.I)
    if cls: print(f"  '{pat}':", Counter(cls).most_common(5))

print("\n=== 3) перший блок коментаря (обрізано) ===")
m=re.search(r'(<(div|li|article)[^>]*class=["\'][^"\']*(comment|review|feedback)[^"\']*["\'][^>]*>.*?</\2>)', html, re.S|re.I)
if m: print(re.sub(r'\s+',' ', m.group(1))[:1400])
else:
    i=html.lower().find('відгук')
    print("евристика не знайшла; навколо 'відгук':", re.sub(r'\s+',' ', html[max(0,i-200):i+600]) if i>0 else "—")

print("\n=== 4) агрегат (навколо к-сті) ===")
i=next((html.find(x) for x in ['1 834','1834','оцінк'] if x in html), -1)
if i>0: print(re.sub(r'\s+',' ', html[max(0,i-350):i+200]))
