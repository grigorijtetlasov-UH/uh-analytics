"""probe_refuse.py — розвідка для канонічних відмов з 1С.
Запуск:  cd ~/uh-analytics && venv/bin/python probe_refuse.py
Показує: (1) поточний код _kpi_for_period; (2) розподіл СостояниеЗаказа в 1С SALES.
"""
import calendar
import inspect
from collections import Counter
from datetime import date

import sales_kpi
import fetch_data as fd

# ── 1) поточна логіка KPI ───────────────────────────────────────────────
print("=" * 64)
print("ДЖЕРЕЛО sales_kpi._kpi_for_period:")
print("=" * 64)
try:
    print(inspect.getsource(sales_kpi._kpi_for_period))
except Exception as e:
    print("  не вдалося дістати джерело:", e)

# ── 2) 1С SALES стани за поточний місяць ────────────────────────────────
today = date.today()
y = today.strftime("%Y")
mo = today.strftime("%m")
cur = f"{y}-{mo}"
last = calendar.monthrange(int(y), int(mo))[1]
rows = fd.post_1c(fd.API_URL_UH, "SALES", y + mo + "01", y + mo + f"{last:02d}")
print("\n" + "=" * 64)
print(f"1С SALES за {cur}: усього рядків = {len(rows)}")
print("=" * 64)


def is_month(r):
    d = str(r.get("Дата", "")).strip().split(".")
    return len(d) == 3 and (d[2] + "-" + d[1]) == cur


clean = [r for r in rows if not fd.is_ne_trogat(r) and is_month(r)]
print("чистих рядків (без НЕ ТРОГАТЬ, поточний міс.):", len(clean))

# розподіл по РЯДКАХ
by_rows = Counter(str(r.get("СостояниеЗаказа", "")).strip() for r in clean)
print("\n-- СостояниеЗаказа: к-ть РЯДКІВ --")
for s, c in by_rows.most_common():
    print(f"  {c:6d}   {s!r}")

# розподіл по УНІКАЛЬНИХ замовленнях (дедуп по НомерЗаказа)
seen = {}
for r in clean:
    no = str(r.get("НомерЗаказа", "")).strip()
    if no and no not in seen:
        seen[no] = str(r.get("СостояниеЗаказа", "")).strip()
by_ord = Counter(seen.values())
print("\n-- СостояниеЗаказа: к-ть ЗАМОВЛЕНЬ (унік. НомерЗаказа) --")
for s, c in by_ord.most_common():
    print(f"  {c:6d}   {s!r}")
print("\nразом унікальних замовлень у SALES:", len(seen))

# службово: які ще поля є в рядку (раптом стан лежить деінде)
if clean:
    print("\n-- приклад полів рядка SALES --")
    print(sorted(clean[0].keys()))
