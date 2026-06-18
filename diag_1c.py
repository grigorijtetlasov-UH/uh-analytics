#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Діагностика 1С-відгрузок за 1–16 червня.
Тягне РІВНО те саме, що й дашборд (dashboard_data._fetch_1c_sales),
сумує СуммаПродажи по днях 1–16 і розбиває по категоріях + підрозділах,
щоб порівняти з твоїм 1С-звітом «РОСТ вал.прибуль» (Итого 10 731 469,19 ₴).

Запуск на сервері:
    cd ~/uh-analytics && venv/bin/python diag_1c.py
"""
from collections import defaultdict
import dashboard_data as dd

REPORT_TOTAL = 10_731_469.19  # Итого «Виручка» зі звіту за 01–16.06

rows = dd._fetch_1c_sales("2026-06")          # те саме джерело, що в дашборді
print(f"Усього рядків 1С SALES за місяць (після фільтра 'НЕ ТРОГАТЬ'): {len(rows)}")

tot = 0.0
n = 0
bycat = defaultdict(float)
catcnt = defaultdict(int)
bysub = defaultdict(float)

for r in rows:
    d = str(r.get("Дата", "")).strip().split(".")
    if len(d) != 3:
        continue
    try:
        day = int(d[0])
    except ValueError:
        continue
    if not (1 <= day <= 16):                   # тільки 1–16, як у звіті
        continue
    s = dd._num1c(r.get("СуммаПродажи"))
    tot += s
    n += 1
    cat = str(r.get("КатегорияНоменклатуры", "?")).strip()
    sub = str(r.get("Подразделение", "?")).strip()
    bycat[cat] += s
    catcnt[cat] += 1
    bysub[sub] += s

print(f"\n=== 1С SALES 1–16.06 — як рахує ДАШБОРД ===")
print(f"Рядків у вікні 1–16: {n}")
print(f"СУМА СуммаПродажи:   {tot:,.2f} ₴")

print(f"\n--- по КАТЕГОРІЯХ (звір зі звітом: Матраси 3.64M, Топпери 3.44M, ...) ---")
for k, v in sorted(bycat.items(), key=lambda x: -x[1]):
    print(f"  {k:<42s} {v:>14,.2f}   ({catcnt[k]} рядків)")

print(f"\n--- по ПІДРОЗДІЛАХ/юрособах (тут видно, якщо тягнемо зайве) ---")
for k, v in sorted(bysub.items(), key=lambda x: -x[1]):
    print(f"  {k:<42s} {v:>14,.2f}")

print(f"\n=== ПІДСУМОК ===")
print(f"Звіт 1С (твій):  {REPORT_TOTAL:>14,.2f} ₴")
print(f"Дашборд:         {tot:>14,.2f} ₴")
print(f"Різниця:         {tot - REPORT_TOTAL:>+14,.2f} ₴")
