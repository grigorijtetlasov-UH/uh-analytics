#!/usr/bin/env python3
# marketing.py — дата-шар сторінки «Маркетинг»
# Тягне MTD-діапазон Meta Ads + GA4 (сесії + Google-spend), мапить по брендах
# (Amebli / Matrasroll), рахує ДРР і збирає обʼєкт `marketing` у формі, яку очікує фронт.
#
# Переюзає КОНСТАНТИ з fetch_data (META_ACCOUNTS/токени/версію API, GA4-креди),
# але має власний компактний range-fetch — fetch_data.py не чіпаємо.
#
# Standalone-тест (перевірити лише spend/сесії, без виручки):
#   ./run.sh marketing.py
import os, json, time, datetime
import requests
import fetch_data as fd

# GA4-property (purple виключено — мертвий)
GA4_PROPS = [
    {"id": "349048143", "name": "matrasroll.com.ua", "brand": "matrasroll"},
    {"id": "350293168", "name": "amebli.com.ua",     "brand": "amebli"},
]

ACTION_TYPES = ("purchase", "lead", "offsite_conversion.fb_pixel_purchase")


def _brand_from_name(name: str):
    n = (name or "").lower()
    if "amebli" in n:
        return "amebli"
    if "matrasroll" in n or "matras" in n:
        return "matrasroll"
    return None  # все інше (зокрема purple) — поза маркетингом по брендах


# ──────────────────────────── META (MTD range) ────────────────────────────
def _meta_get(url, params, retries=4):
    for i in range(retries):
        try:
            d = requests.get(url, params=params, timeout=30).json()
            if "error" in d:
                code = d["error"].get("code")
                msg = str(d["error"].get("message", "")).lower()
                if ("limit reached" in msg or code in (4, 17, 32, 613)) and i < retries - 1:
                    time.sleep(2 ** (i + 2))
                    continue
            return d
        except Exception as ex:
            if i < retries - 1:
                time.sleep(2 ** (i + 1))
                continue
            return {"error": {"message": str(ex)}}
    return {"error": {"message": "max retries"}}


def fetch_meta_mtd(since, until):
    """Сумарні Meta-витрати/кліки/результати за діапазон [since..until], по брендах."""
    out = {
        "amebli":     {"spend": 0.0, "clicks": 0, "impressions": 0, "results": 0},
        "matrasroll": {"spend": 0.0, "clicks": 0, "impressions": 0, "results": 0},
        "accounts": [], "total_spend": 0.0,
    }
    last_token = None
    for acc in fd.META_ACCOUNTS:
        if last_token == acc["token"]:
            time.sleep(2.0)            # та сама пауза проти app-level rate limit
        last_token = acc["token"]

        rec = {"name": acc["name"], "spend": 0.0, "clicks": 0,
               "impressions": 0, "results": 0, "error": None}
        d = _meta_get(
            f"https://graph.facebook.com/{fd.META_API_VERSION}/act_{acc['id']}/insights",
            {
                "access_token": acc["token"],
                "time_range":   json.dumps({"since": since, "until": until}),
                "fields":       "spend,impressions,clicks,actions",
                "level":        "account",
            },
        )
        if "error" in d:
            rec["error"] = "API error"          # НЕ зберігаємо текст — у ньому буває токен
        elif d.get("data"):
            row = d["data"][0]
            rec["spend"]       = round(fd.safe_float(row.get("spend", 0)), 2)
            rec["clicks"]      = int(row.get("clicks", 0) or 0)
            rec["impressions"] = int(row.get("impressions", 0) or 0)
            res = 0
            for a in row.get("actions", []) or []:
                if a.get("action_type") in ACTION_TYPES:
                    res += int(a.get("value", 0) or 0)
            rec["results"] = res

        b = _brand_from_name(acc["name"])
        if b and not rec["error"]:
            out[b]["spend"]       += rec["spend"]
            out[b]["clicks"]      += rec["clicks"]
            out[b]["impressions"] += rec["impressions"]
            out[b]["results"]     += rec["results"]
            out["total_spend"]    += rec["spend"]
        out["accounts"].append(rec)

    for b in ("amebli", "matrasroll"):
        out[b]["spend"] = round(out[b]["spend"], 2)
    out["total_spend"] = round(out["total_spend"], 2)
    return out


# ──────────────────────────── GA4 (MTD range) ────────────────────────────
def fetch_ga4_mtd(since, until):
    """Сесії + Google-spend (advertiserAdCost) за діапазон, по брендах/сайтах."""
    out = {
        "amebli":     {"sessions": 0, "ads_cost": 0.0, "ads_clicks": 0},
        "matrasroll": {"sessions": 0, "ads_cost": 0.0, "ads_clicks": 0},
        "properties": [],
    }
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = fd.GA4_CREDENTIALS
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension

    client = BetaAnalyticsDataClient()
    dr = [DateRange(start_date=since, end_date=until)]

    for p in GA4_PROPS:
        rec = {"name": p["name"], "sessions": 0, "ads_cost": 0.0,
               "ads_clicks": 0, "error": None}
        prop = f"properties/{p['id']}"
        try:
            r1 = client.run_report(RunReportRequest(
                property=prop, date_ranges=dr, metrics=[Metric(name="sessions")]))
            if r1.rows:
                rec["sessions"] = int(r1.rows[0].metric_values[0].value or 0)
            # Google Ads spend через GA4↔Google Ads link (потребує dimension з кампанією)
            try:
                r2 = client.run_report(RunReportRequest(
                    property=prop, date_ranges=dr,
                    metrics=[Metric(name="advertiserAdCost"), Metric(name="advertiserAdClicks")],
                    dimensions=[Dimension(name="sessionCampaignName")], limit=500))
                cost = 0.0
                clicks = 0
                for row in r2.rows:
                    cost   += float(row.metric_values[0].value or 0)
                    clicks += int(row.metric_values[1].value or 0)
                rec["ads_cost"]   = round(cost, 2)
                rec["ads_clicks"] = clicks
            except Exception as ex:
                rec["ads_note"] = f"ads_cost недоступний: {ex}"
        except Exception as ex:
            rec["error"] = str(ex)

        out[p["brand"]]["sessions"]   += rec["sessions"]
        out[p["brand"]]["ads_cost"]   += rec["ads_cost"]
        out[p["brand"]]["ads_clicks"] += rec["ads_clicks"]
        out["properties"].append(rec)

    for b in ("amebli", "matrasroll"):
        out[b]["ads_cost"] = round(out[b]["ads_cost"], 2)
    return out


# ──────────────────────────── BUILD marketing object ────────────────────────────
def build_marketing(since, until, brand_stats):
    """
    brand_stats (передається з dashboard_data, рахується з 1С/CRM):
      {
        'amebli':     {'revenue': float, 'orders': int, 'leads': int|None},  # SALES-виручка бренду
        'matrasroll': {'revenue': float, 'orders': int, 'leads': int|None},
        'other':      [ {'ch': 'Sofino', 'revenue': .., 'orders': .., 'leads': ..}, ... ],
        'total_revenue_orders': float,   # вся 1С ЗАМОВЛЕННЯ MTD  → «ДРР Замовлення»
        'total_revenue_ship':   float,   # вся 1С ВІДГРУЗКИ (SALES) MTD → «ДРР Відгрузки»
        'total_leads':          int|None,
      }
    """
    d0 = datetime.date.fromisoformat(since)
    d1 = datetime.date.fromisoformat(until)
    days = (d1 - d0).days + 1

    meta = fetch_meta_mtd(since, until)
    ga   = fetch_ga4_mtd(since, until)

    brands = {}
    for b, label in (("amebli", "Amebli"), ("matrasroll", "Matrasroll")):
        sm = meta[b]["spend"]
        sg = ga[b]["ads_cost"]
        st = round(sm + sg, 2)
        rev = float((brand_stats.get(b) or {}).get("revenue", 0) or 0)
        clk = meta[b]["clicks"] + ga[b]["ads_clicks"]
        res = meta[b]["results"]
        brands[b] = {
            "name": label,
            "spend_meta":   round(sm, 2),
            "spend_google": round(sg, 2),
            "spend":        st,
            "sessions":     ga[b]["sessions"],
            "clicks":       clk,
            "results":      res,
            "cpc":          round(st / clk, 2) if clk else 0.0,
            "cpa":          round(st / res, 2) if res else 0.0,
            "revenue":      round(rev),
            "drr":          round(st / rev * 100, 2) if rev else 0.0,
        }

    total_spend = round(brands["amebli"]["spend"] + brands["matrasroll"]["spend"], 2)
    rev_ord = float(brand_stats.get("total_revenue_orders", 0) or 0)
    rev_shp = float(brand_stats.get("total_revenue_ship", 0) or 0)
    drr_ord = round(total_spend / rev_ord * 100, 2) if rev_ord else 0.0
    drr_shp = round(total_spend / rev_shp * 100, 2) if rev_shp else 0.0

    drr_bars = [
        {"name": "ДРР Amebli",     "val": brands["amebli"]["drr"],     "target": 15, "color": "#ff6b6b"},
        {"name": "ДРР Matrasroll", "val": brands["matrasroll"]["drr"], "target": 15, "color": "#ffa94d"},
        {"name": "ДРР Відгрузки",  "val": drr_shp,                     "target": 15, "color": "#94d82d"},
    ]
    if rev_ord > 0:
        drr_bars.append({"name": "ДРР Замовлення", "val": drr_ord, "target": 7, "color": "#00d68f"})

    def chrow(label, traffic, leads, orders, revenue, spend):
        traffic = int(traffic or 0); leads = int(leads or 0); orders = int(orders or 0)
        revenue = float(revenue or 0); spend = float(spend or 0)
        drr = round(spend / revenue * 100, 1) if revenue else 0.0
        dc = "neu" if spend == 0 else ("bad" if drr > 22 else "warn" if drr > 15 else "good")
        return {
            "ch": label, "traffic": traffic, "leads": leads,
            "cr_tl": round(leads / traffic * 100, 1) if (traffic and leads) else 0.0,
            "orders": orders,
            "cr_lo": round(orders / leads * 100) if (leads and orders) else 0.0,
            "budget_day": round(spend / days) if days else 0,
            "drr": drr, "drr_cls": dc,
        }

    channels = [
        chrow("matrasroll.com.ua", ga["matrasroll"]["sessions"],
              (brand_stats.get("matrasroll") or {}).get("leads"),
              (brand_stats.get("matrasroll") or {}).get("orders"),
              brands["matrasroll"]["revenue"], brands["matrasroll"]["spend"]),
        chrow("amebli.com.ua", ga["amebli"]["sessions"],
              (brand_stats.get("amebli") or {}).get("leads"),
              (brand_stats.get("amebli") or {}).get("orders"),
              brands["amebli"]["revenue"], brands["amebli"]["spend"]),
    ]
    for o in brand_stats.get("other", []) or []:
        channels.append(chrow(o.get("ch", "?"), o.get("traffic", 0),
                              o.get("leads"), o.get("orders"),
                              o.get("revenue", 0), 0.0))

    return {
        "period": {"since": since, "until": until, "days": days},
        "brands": brands,
        "totals": {
            "spend":         total_spend,
            "spend_meta":    round(brands["amebli"]["spend_meta"] + brands["matrasroll"]["spend_meta"], 2),
            "spend_google":  round(brands["amebli"]["spend_google"] + brands["matrasroll"]["spend_google"], 2),
            "budget_per_day": round(total_spend / days) if days else 0,
            "revenue_orders": round(rev_ord),
            "revenue_ship":   round(rev_shp),
            "drr_orders":     drr_ord,
            "drr_ship":       drr_shp,
            "leads":          brand_stats.get("total_leads"),
        },
        "drr_bars": drr_bars,
        "channels": channels,
        "meta_accounts": meta["accounts"],   # для діагностики (без токенів)
        "ga_properties": ga["properties"],
    }


# ──────────────────────────── STANDALONE TEST ────────────────────────────
if __name__ == "__main__":
    ref   = datetime.date.today() - datetime.timedelta(days=1)   # вчора — останній ПОВНИЙ день
    since = ref.replace(day=1).isoformat()                       # MTD до вчора включно
    until = ref.isoformat()
    print(f"Звітний період (MTD до вчора включно): {since} .. {until}")
    m = build_marketing(since, until, {
        "amebli": {}, "matrasroll": {},
        "total_revenue_orders": 0, "total_revenue_ship": 0, "other": [],
    })
    print("\nПо брендах (spend/сесії — без виручки, тому ДРР=0):")
    for b, v in m["brands"].items():
        print(f"  {v['name']:<11} Meta={v['spend_meta']:>9} + Google={v['spend_google']:>9} "
              f"= {v['spend']:>9}₴ · сесій {v['sessions']:>6} · клік {v['clicks']:>6} · CPC {v['cpc']}")
    tt = m["totals"]
    print(f"\n  TOTAL spend: {tt['spend']}₴  (Meta {tt['spend_meta']} + Google {tt['spend_google']}) "
          f"· бюджет/день ~{tt['budget_per_day']}₴ · днів {m['period']['days']}")
    print("\n  Кабінети Meta:")
    for a in m["meta_accounts"]:
        print(f"    {a['name']:<16} spend={a['spend']} clicks={a['clicks']} "
              f"results={a['results']}" + (f"  [{a['error']}]" if a["error"] else ""))
    print("  GA4-property:")
    for p in m["ga_properties"]:
        note = p.get("ads_note") or p.get("error") or ""
        print(f"    {p['name']:<20} sessions={p['sessions']} ads_cost={p['ads_cost']} "
              f"{('· ' + note) if note else ''}")
