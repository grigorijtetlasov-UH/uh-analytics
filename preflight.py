#!/usr/bin/env python3
# preflight.py — перевірка готовності перед збіркою Секції 2 «Маркетинг»
# Запуск: ./run.sh preflight.py   (щоб підхопився .env із токенами/шляхами)
import os, sys, datetime

YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
results = []  # (назва, passed, деталь)

def check(name, passed, detail=""):
    results.append((name, passed, detail))
    print(f"  [{'OK ' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

print("=" * 66)
print(f"PRE-FLIGHT МАРКЕТИНГ · дані перевіряємо за: {YESTERDAY}")
print("=" * 66)

# ── 1. ENV ──────────────────────────────────────────────────────────
print("\n1) Змінні оточення (.env через run.sh):")
for k in ("META_TOKEN_BM1", "META_TOKEN_BM2"):
    v = os.getenv(k)
    check(k, bool(v), f"{len(v)} симв." if v else "ВІДСУТНІЙ")  # друкуємо лише довжину, не токен
gc = os.getenv("GA4_CREDENTIALS", "")
check("GA4_CREDENTIALS", bool(gc), gc if gc else "не задано (буде дефолтний шлях)")
print("   — Google Ads (опційно, для майбутньої деталі по кампаніях, НЕ блокує):")
for k in ("GADS_CLIENT_ID", "GADS_CLIENT_SECRET", "GADS_REFRESH_TOKEN",
          "DEVELOPER_TOKEN", "LOGIN_CUSTOMER_ID"):
    print(f"       {'•' if os.getenv(k) else '·'} {k}: {'є' if os.getenv(k) else '—'}")

# ── 2. GA4 service-account файл ──────────────────────────────────────
print("\n2) Файл GA4 service-account:")
ga4_path = gc or "uh-sh-analitics-c316f4cad6c0.json"
ga4_exists = os.path.isfile(ga4_path)
check("GA4 SA JSON на диску", ga4_exists, ga4_path if ga4_exists else f"НЕ знайдено: {ga4_path}")

# ── 3. Python-бібліотеки ─────────────────────────────────────────────
print("\n3) Python-бібліотеки:")
try:
    import requests  # noqa: F401
    check("requests (Meta)", True)
except Exception as e:
    check("requests (Meta)", False, str(e)[:80])
try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient  # noqa: F401
    check("google-analytics-data (GA4)", True)
except Exception:
    check("google-analytics-data (GA4)", False, "venv/bin/pip install google-analytics-data")

# ── модуль fetch_data ────────────────────────────────────────────────
try:
    import fetch_data as fd
except Exception as e:
    print(f"\n❌ Не імпортується fetch_data: {e}")
    print("=" * 66)
    sys.exit(1)

# ── 4. META live ─────────────────────────────────────────────────────
print(f"\n4) Meta Ads (live за {YESTERDAY}):")
try:
    r = fd.fetch_meta(YESTERDAY)
    accs = r.get("accounts", []) or []
    n_err = sum(1 for a in accs if a.get("error"))
    brand = {"Amebli": [0.0, 0], "MatrasRoll": [0.0, 0]}
    for a in accs:
        st = "ERR" if a.get("error") else "OK"
        # НЕ друкуємо a["error"] — у ньому буває токен (саме так вони й протікали в JSON)
        print(f"     {str(a.get('name','?')):<16} spend={a.get('spend')} "
              f"clicks={a.get('clicks')} results={a.get('results')} [{st}]")
        nm = str(a.get("name", ""))
        key = "Amebli" if "Amebli" in nm else ("MatrasRoll" if "MatrasRoll" in nm else None)
        if key and not a.get("error"):
            brand[key][0] += float(a.get("spend") or 0)
            brand[key][1] += int(a.get("results") or 0)
    print(f"     ──> Amebli: {brand['Amebli'][0]:.2f}₴ / {brand['Amebli'][1]} res    "
          f"MatrasRoll: {brand['MatrasRoll'][0]:.2f}₴ / {brand['MatrasRoll'][1]} res")
    print(f"     ──> TOTAL spend: {r.get('total', {}).get('spend')}₴")
    meta_ok = (len(accs) == 4 and n_err == 0)
    check("Meta: усі 4 кабінети тягнуть", meta_ok,
          "усі OK" if meta_ok else f"{n_err} з {len(accs)} з помилкою")
except Exception as e:
    check("Meta: усі 4 кабінети тягнуть", False, str(e)[:120])

# ── 5. GA4 + Google-spend live ───────────────────────────────────────
print(f"\n5) GA4 + Google-spend (live за {YESTERDAY}):")
try:
    g = fd.fetch_ga4(YESTERDAY)
    sess = g.get("sessions")
    cost = g.get("ads_cost")
    bp = g.get("by_property", []) or []
    sum_sess = 0; sum_cost = 0.0
    for p in bp:
        if isinstance(p, dict):
            ps, pc = p.get("sessions"), p.get("ads_cost")
            print(f"     {str(p.get('name', p.get('property', '?'))):<22} "
                  f"sessions={ps} ads_cost={pc}")
            sum_sess += int(ps or 0); sum_cost += float(pc or 0)
    if bp:
        print(f"     ──> Σ по сайтах: sessions={sum_sess}  Google-spend={sum_cost:.2f}₴")
    print(f"     ──> top-level: sessions={sess}  ads_cost={cost}")
    ga4_ok = sess is not None
    check("GA4: сесії тягнуться", ga4_ok, f"{sess} сесій (деф. property)" if ga4_ok else "немає даних")
    has_gspend = bool(cost) or sum_cost > 0
    check("GA4: Google-spend (ads_cost) присутній", has_gspend,
          "є" if has_gspend else "0 — лінк GA4↔Google Ads не активний/немає за цей день")
except Exception as e:
    check("GA4: сесії тягнуться", False, str(e)[:120])

# ── ВЕРДИКТ ──────────────────────────────────────────────────────────
print("\n" + "=" * 66)
BLOCKERS = {
    "META_TOKEN_BM1", "META_TOKEN_BM2", "GA4 SA JSON на диску",
    "requests (Meta)", "google-analytics-data (GA4)",
    "Meta: усі 4 кабінети тягнуть", "GA4: сесії тягнуться",
}
hard_fail = [n for n, p, _ in results if not p and n in BLOCKERS]
if not hard_fail:
    print("✅ ВСЕ ГОТОВО — можна будувати Секцію 2 «Маркетинг».")
    print("   Google-spend для ДРР тягнеться з GA4; Google Ads API (деталь по")
    print("   кампаніях) підключимо пізніше — НЕ блокує збірку.")
else:
    print("❌ Є блокери — спершу полагодь:")
    for n in hard_fail:
        print(f"     · {n}")
print("=" * 66)
