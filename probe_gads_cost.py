#!/usr/bin/env python3
# probe_gads_cost.py — перевірка, чи Google-spend (GA4 advertiserAdCost) реальний,
# чи роздувається при розбивці по sessionCampaignName.
# Міряємо ОДИН І ТОЙ САМИЙ показник трьома способами. Запуск: ./run.sh probe_gads_cost.py
import os, datetime
import fetch_data as fd

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = fd.GA4_CREDENTIALS
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, Dimension, OrderBy
)

client = BetaAnalyticsDataClient()
ref   = datetime.date.today() - datetime.timedelta(days=1)
since = ref.replace(day=1).isoformat()
until = ref.isoformat()
dr = [DateRange(start_date=since, end_date=until)]
PROPS = [("matrasroll.com.ua", "349048143"), ("amebli.com.ua", "350293168")]

print(f"Період: {since} .. {until}\n")


def total_nodim(prop):
    r = client.run_report(RunReportRequest(
        property=prop, date_ranges=dr, metrics=[Metric(name="advertiserAdCost")]))
    return float(r.rows[0].metric_values[0].value) if r.rows else 0.0


def total_by(prop, dim):
    r = client.run_report(RunReportRequest(
        property=prop, date_ranges=dr,
        metrics=[Metric(name="advertiserAdCost")],
        dimensions=[Dimension(name=dim)], limit=5000))
    return sum(float(x.metric_values[0].value or 0) for x in r.rows), len(r.rows)


def by_date(prop):
    r = client.run_report(RunReportRequest(
        property=prop, date_ranges=dr,
        metrics=[Metric(name="advertiserAdCost")],
        dimensions=[Dimension(name="date")],
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))]))
    return [(x.dimension_values[0].value, float(x.metric_values[0].value or 0)) for x in r.rows]


for name, pid in PROPS:
    prop = f"properties/{pid}"
    print(f"── {name} ──")
    checks = [
        ("A) без виміру (канон)",              lambda: total_nodim(prop)),
        ("B) Σ по sessionCampaignName (зараз)", lambda: total_by(prop, "sessionCampaignName")),
        ("C) Σ по date",                        lambda: total_by(prop, "date")),
    ]
    for label, fn in checks:
        try:
            v = fn()
            if isinstance(v, tuple):
                print(f"   {label:<40} {v[0]:>14,.2f} ₴   ({v[1]} рядків)")
            else:
                print(f"   {label:<40} {v:>14,.2f} ₴")
        except Exception as e:
            print(f"   {label:<40} помилка: {str(e)[:70]}")
    try:
        rows = by_date(prop)
        if rows:
            mx = max(rows, key=lambda t: t[1])
            print(f"   днів із витратами: {sum(1 for _,c in rows if c>0)} · "
                  f"макс. день: {mx[0]} = {mx[1]:,.2f} ₴")
    except Exception as e:
        print(f"   денний розріз: помилка {str(e)[:70]}")
    print()

print("Як читати:")
print("  • A ≈ B ≈ C  →  Google-spend РЕАЛЬНИЙ, рахуємо ДРР як є.")
print("  • B (sessionCampaignName) значно > A/C  →  GA4 роздуває; перейду на A/C.")
