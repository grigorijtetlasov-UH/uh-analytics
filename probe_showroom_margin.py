"""probe_showroom_margin.py — діагностика маржі шоу-румів (roznica).
Запуск:  cd ~/uh-analytics && venv/bin/python probe_showroom_margin.py

Ключове питання: чи висока маржа М'яких — реальна націнка, чи 1С не пише
собівартість (СебестоимостьПродажи=0) для шоу-румів. Колонка 'нульСеб' = к-ть
рядків з виручкою>0, але собівартістю=0 (саме вони завищують маржу).
"""
import calendar
from collections import defaultdict
from datetime import date

import fetch_data as fd


def num(v):
    try:
        return float(str(v if v is not None else 0).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except Exception:
        return 0.0


def is_showroom(podr):
    s = str(podr).lower()
    return "шоу-рум" in s or "шоурум" in s


today = date.today()
y, mo = today.strftime("%Y"), today.strftime("%m")
cur = f"{y}-{mo}"
last = calendar.monthrange(int(y), int(mo))[1]
rows = fd.post_1c(fd.API_URL_UH, "SALES", y + mo + "01", y + mo + f"{last:02d}")


def is_month(r):
    d = str(r.get("Дата", "")).strip().split(".")
    return len(d) == 3 and (d[2] + "-" + d[1]) == cur


clean = [r for r in rows
         if not fd.is_ne_trogat(r) and is_month(r) and is_showroom(r.get("Подразделение"))]
print(f"шоу-рум рядків за {cur}: {len(clean)}")

# які саме підрозділи потрапили (перевірка фільтра)
subs = sorted({str(r.get("Подразделение", "")).strip() for r in clean})
print("підрозділи:", subs)

# ── по категоріях (сира КатегорияНоменклатуры) ──
agg = defaultdict(lambda: {"rev": 0.0, "cost": 0.0, "n": 0, "zero": 0})
for r in clean:
    cat = str(r.get("КатегорияНоменклатуры", "")).strip() or "(порожньо)"
    rev = num(r.get("СуммаПродажи"))
    cost = num(r.get("СебестоимостьПродажи"))
    a = agg[cat]
    a["rev"] += rev
    a["cost"] += cost
    a["n"] += 1
    if rev > 0 and cost == 0:
        a["zero"] += 1

print(f"\n{'категорія':30s} {'ряд':>4} {'нульСеб':>7} {'виручка':>11} {'собівар':>11} {'маржа%':>7}")
print("-" * 74)
trev = tcost = 0.0
for cat, a in sorted(agg.items(), key=lambda kv: -kv[1]["rev"]):
    m = (a["rev"] - a["cost"]) / a["rev"] * 100 if a["rev"] > 0 else 0
    trev += a["rev"]
    tcost += a["cost"]
    print(f"{cat[:30]:30s} {a['n']:4d} {a['zero']:7d} {a['rev']:11.0f} {a['cost']:11.0f} {m:7.1f}")
print("-" * 74)
tm = (trev - tcost) / trev * 100 if trev > 0 else 0
print(f"{'РАЗОМ':30s} {sum(a['n'] for a in agg.values()):4d} "
      f"{sum(a['zero'] for a in agg.values()):7d} {trev:11.0f} {tcost:11.0f} {tm:7.1f}")

# ── приклади М'яких (диваны) з нульовою собівартістю ──
print("\n-- приклади рядків М'яких/диванів із собівартістю=0 (rev>0) --")
shown = 0
for r in clean:
    cat = str(r.get("КатегорияНоменклатуры", "")).strip().lower()
    if "диван" in cat or "м'як" in cat or "мягк" in cat or "м'як" in cat:
        rev = num(r.get("СуммаПродажи"))
        cost = num(r.get("СебестоимостьПродажи"))
        if rev > 0 and cost == 0:
            print(f"  {str(r.get('Номенклатура', ''))[:50]:50s} rev={rev:.0f} cost=0")
            shown += 1
            if shown >= 12:
                break
print(f"  (показано {shown})")
