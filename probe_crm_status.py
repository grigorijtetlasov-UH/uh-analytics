"""probe_crm_status.py — які CRM-статуси є (для Секції 3: спам / недодзвон / повернення).
Запуск:  cd ~/uh-analytics && venv/bin/python probe_crm_status.py
"""
from collections import Counter
from datetime import date

import sales_kpi

cur = date.today().strftime("%Y-%m")
raw = sales_kpi._load_raw_excel(cur)
if raw is None:
    print("нема CRM-даних за", cur)
    raise SystemExit

df = raw[raw["_місяць"] == cur].copy()
print("рядків за", cur, ":", len(df))

# знайти колонку статусу
status_col = None
for c in df.columns:
    if "статус" in str(c).lower():
        status_col = c
        break
print("колонка статусу:", status_col)
print("усі колонки:", [c for c in df.columns if not str(c).startswith("_")])

key = "Номер 1С" if "Номер 1С" in df.columns else None

# ── сирі статуси: по рядках і по унікальних замовленнях ──
if status_col:
    print("\n-- сирі статуси (РЯДКИ) --")
    for s, c in Counter(df[status_col].astype(str)).most_common(50):
        print(f"  {c:6d}   {s!r}")

    if key:
        first = df.dropna(subset=[key]).groupby(key)[status_col].first()
        print("\n-- сирі статуси (унік. ЗАМОВЛЕННЯ за Номер 1С) --")
        for s, c in Counter(first.astype(str)).most_common(50):
            print(f"  {c:6d}   {s!r}")

# ── похідна _категорія (як sales_kpi класифікує) ──
if "_категорія" in df.columns:
    print("\n-- _категорія (рядки) --")
    for s, c in Counter(df["_категорія"].astype(str)).most_common():
        print(f"  {c:6d}   {s}")
