#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Патч sales_kpi.py: переводить 2 статуси в «продажі» (ORDER):
  + «закінчився термін зберігання»  (був 'other' — взагалі не рахувався)
  + «повторне звернення»            (був активний лід → тепер продаж)
Запуск на сервері: cd ~/uh-analytics && venv/bin/python patch_skpi.py
Бекап робиться автоматично у sales_kpi.py.bak
"""
import shutil
import sys

p = "sales_kpi.py"
s = open(p, encoding="utf-8").read()

# 1) ORDER_STATUSES: додати 2 статуси після рядка з "повернення",
before_order = '    "повернення",\n}'
after_order = ('    "повернення",\n'
               '    "закінчився термін зберігання", "повторне звернення",\n}')
if before_order not in s:
    sys.exit("❌ Не знайдено якір ORDER_STATUSES — перевір файл вручну")
s = s.replace(before_order, after_order, 1)

# 2) LEAD_STATUSES: прибрати "повторне звернення" (тепер воно в ORDER)
before_lead = '    "новий", "недодзвон", "автовідповідач", "повторне звернення",\n'
after_lead = '    "новий", "недодзвон", "автовідповідач",\n'
if before_lead not in s:
    sys.exit("❌ Не знайдено якір LEAD_STATUSES — перевір файл вручну")
s = s.replace(before_lead, after_lead, 1)

shutil.copy(p, p + ".bak")
open(p, "w", encoding="utf-8").write(s)
print("✅ sales_kpi.py пропатчено (бекап: sales_kpi.py.bak)")
print("   ORDER += закінчился термін зберігання, повторне звернення")
