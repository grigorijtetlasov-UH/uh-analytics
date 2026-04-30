"""
fetch_data.py
─────────────────────────────────────────────────────────
Збір даних для щоденного дашборду UH Analytics.

Джерела:
  1. 1С UH  — ORDERS, ORDERSWD, SALES
  2. 1С SH  — ORDERS, ORDERSWD, SALES
  3. SalesDrive CRM — заявки (ліди + замовлення)

Результат: зберігає history/YYYY-MM-DD.json
─────────────────────────────────────────────────────────
"""

import os
import json
import re
import base64
import csv
import io
import glob
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ─────────────────────────── CONFIG ───────────────────────────
# Можна задати через .env або напряму тут

API_URL_UH  = os.getenv("API_URL",    "http://142.132.252.184:58300/ST_UNF/ws/request.1cws")
API_URL_SH  = os.getenv("API_URL_SH", "https://saleshub1.apic.com.ua:8443/mtrs/ws/request.1cws")
API_URL_SH_WD = os.getenv("API_URL_SH_WD", "https://saleshub1.apic.com.ua:8443/mtrs/ws/request.1cws")
API_SH_USER = os.getenv("API_SH_USER", "WS")
API_SH_PASS = os.getenv("API_SH_PASS", "q1w2E#")

# SalesDrive CRM (Excel-вигрузка)
CRM_DATA_DIR = Path("data/crm")
CRM_DATA_DIR.mkdir(parents=True, exist_ok=True)

# (deprecated) SalesDrive API
SD_API_KEY  = os.getenv("SD_API_KEY", "l-gTmE_eWopdwozFM9AW78imyzIMOErc52dBd8tTCGXBeTE_TeFvcs6AhjHC4A2kKTVCoL3ufp5fZ7xhRIZ1pU-rpD1GckOAkHEq")
SD_BASE_URL = "https://matrasroll.salesdrive.me"

# Google Sheets (GA4 + Meta)
GSHEET_ID  = os.getenv("GSHEET_ID", "1f92jFNkwG1QS_LswItj01SwVAcDiyg-Tbw0CEfOrqZA")
GSHEET_URL = f"https://docs.google.com/spreadsheets/d/{GSHEET_ID}/export?format=csv&gid=0"


# Meta Ads
META_TOKEN_BM1 = os.getenv("META_TOKEN_BM1", "EAAOJViuNgBgBRZArQ2iCiHZCHNj0YGRZCL5LOH0GYDQczs63XLz88BZBDR6wpxNbYfOy7mpHOZCAfHBtltbIVZBwkV9zbqOBTVObYTkPN6WlsOAUgvDPL1evn3eNskpL4n47aQOHRqqtRzkZCPZBDTZAHZBA4MsVzPZA2IaIRXFuhgfijXkE9ZAea57tUZCVIxFNe7UIzOgZDZD")
META_TOKEN_BM2 = os.getenv("META_TOKEN_BM2", "EAAyQRTaR3igBRT9cEqsf4uBeNNAa8uPnaGnKkEDQdp01JxAPBOLgY3TWZBrdOmUBYdwv1lIQ3jqlyfQEO5VInfE0utqKCLkJs091QEmAli5EbbvkC05GOxeYCLsrIefhZCLm3L8aEsWRQMk28lS9CIFJp2cOWKPKVDKo60BFYQ7gWzELgWTbB8SSmMfGCgVC4tC8rPCW9M7iZBXZApm0ZCQqUCRs3SeU4aPmN530M")

META_ACCOUNTS = [
    {"id": "498543759542047",  "name": "Amebli 2024",     "token": META_TOKEN_BM1},
    {"id": "785104883775481",  "name": "Amebli",          "token": META_TOKEN_BM2},
    {"id": "1071880631226950", "name": "MatrasRoll 2024", "token": META_TOKEN_BM2},
]
META_API_VERSION = "v19.0"
# Google Analytics 4
GA4_PROPERTY_ID  = os.getenv("GA4_PROPERTY_ID", "349048143")
GA4_CREDENTIALS  = os.getenv("GA4_CREDENTIALS", "uh-sh-analitics-c316f4cad6c0.json")

# Папка для збереження історії
HISTORY_DIR = Path("history")
HISTORY_DIR.mkdir(exist_ok=True)

# ──────────────────────── HELPERS ─────────────────────────────

def fmt_yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")

def fmt_display(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y")

def safe_float(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace("\u00A0", "").replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return 0.0

def norm(s: str) -> str:
    s = (s or "").replace("\u00A0", " ").replace("_", " ")
    return re.sub(r"\s+", " ", s).strip().upper()

def parse_1c_date(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.strptime(s[:10], "%d.%m.%Y")
        return dt.strftime("%Y%m%d")
    except Exception:
        return None

def filter_rows_by_day(rows: list, day_yyyymmdd: str) -> list:
    return [r for r in rows if parse_1c_date(r.get("Дата")) == day_yyyymmdd]

def get_podr(r: dict) -> str:
    for k in ("Подразделение", "Підрозділ", "Подраздел"):
        v = r.get(k)
        if v:
            return str(v).strip()
    return "Невідомо"

# ──────────────────────── 1С API ──────────────────────────────

SH_DELIVERY_KEYWORDS = [
    "доставка", "нова пошта", "новапошта", " нп",
    "укр пошта", "укрпошта", "міст експрес", "по місту",
    "збірка", "сборка", "занос", "підйом",
]

def build_soap_body(start: str, end: str, type_value: str) -> str:
    return f"""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <m:GetData xmlns:m="http://localhost/request">
      <m:StartDate>{start}</m:StartDate>
      <m:EndDate>{end}</m:EndDate>
      <m:Type>{type_value}</m:Type>
    </m:GetData>
  </soap:Body>
</soap:Envelope>"""

def extract_json_from_soap(text: str):
    start = text.find("[")
    end   = text.rfind("]")
    if start == -1 or end == -1:
        raise RuntimeError("JSON не знайдено у відповіді 1С")
    return json.loads(text[start:end + 1])

def post_1c(api_url: str, type_value: str, start: str, end: str,
            user: str = None, password: str = None) -> list:
    body = build_soap_body(start, end, type_value)
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "Accept":       "text/xml",
        "SOAPAction":   "http://localhost/request/GetData",
    }
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"

    r = requests.post(api_url, data=body.encode("utf-8"),
                      headers=headers, timeout=(10, 90))
    r.raise_for_status()
    return extract_json_from_soap(r.text)

def is_delivery_row(r: dict) -> bool:
    text = " ".join([
        str(r.get("Номенклатура", "") or ""),
        str(r.get("КатегорияНоменклатуры", "") or ""),
    ]).lower()
    return any(kw in text for kw in SH_DELIVERY_KEYWORDS)

def is_ne_trogat(r: dict) -> bool:
    return "НЕ ТРОГАТЬ" in norm(" ".join(str(v) for v in r.values()))

def agg_by_podr(rows: list, sum_key: str) -> dict:
    total = 0.0
    by_podr = {}
    for r in rows:
        s = safe_float(r.get(sum_key))
        total += s
        podr = get_podr(r)
        by_podr[podr] = by_podr.get(podr, 0.0) + s
    return {
        "total": round(total, 2),
        "count": len(rows),
        "by_podr": {k: round(v, 2) for k, v in
                    sorted(by_podr.items(), key=lambda x: x[1], reverse=True)}
    }

def fetch_1c_block(label: str, api_url: str, day: str,
                   m_start: str, m_end: str,
                   user: str = None, password: str = None,
                   exclude_delivery_on_sales: bool = False) -> dict:
    """
    Повертає dict з даними по всіх трьох типах за день і місяць.
    """
    result = {"label": label}

    for type_key, sum_key in [("ORDERS", "Сумма"), ("ORDERSWD", "Сумма"), ("SALES", "СуммаПродажи")]:
        try:
            # --- ДЕНЬ ---
            rows_day = post_1c(api_url, type_key, day, day, user, password)
            rows_day = filter_rows_by_day(rows_day, day)
            rows_day = [r for r in rows_day if not is_ne_trogat(r)]
            if exclude_delivery_on_sales and type_key == "SALES":
                rows_day = [r for r in rows_day if not is_delivery_row(r)]

            # --- МІСЯЦЬ ---
            rows_m = post_1c(api_url, type_key, m_start, m_end, user, password)
            rows_m = [r for r in rows_m if not is_ne_trogat(r)]
            if exclude_delivery_on_sales and type_key == "SALES":
                rows_m = [r for r in rows_m if not is_delivery_row(r)]

            result[type_key] = {
                "day":   agg_by_podr(rows_day, sum_key),
                "month": {
                    "total": round(sum(safe_float(r.get(sum_key)) for r in rows_m), 2),
                    "count": len(rows_m)
                }
            }
        except Exception as e:
            result[type_key] = {"error": str(e)}

    return result

# ──────────────────────── SALESDRIVE CRM ──────────────────────

def sd_get(endpoint: str, params: dict = None) -> dict:
    """GET запит до SalesDrive API."""
    url = f"{SD_BASE_URL}{endpoint}"
    headers = {"Accept": "application/json", "X-Api-Key": SD_API_KEY}
    # API key передається як параметр запиту
    
    # X-Api-Key передається через заголовок
    r = requests.get(url, headers=headers, params=params or {}, timeout=(5, 30))
    r.raise_for_status()
    return r.json()

def fetch_salesdrive(date_str: str) -> dict:
    """
    Читає останній xlsx файл з папки data/crm/.
    Фільтрує по даті date_str (YYYY-MM-DD) колонкою "Дата".

    Очікувані колонки в Excel:
      Дата, Менеджер, Сайт, Сума, Статус, Назва [Товари/Послуги],
      Причина відмови ?, Менеджер на магазині, UTM_SOURCE_Чат
    """
    result = {
        "date": date_str,
        "source_file": None,
        "orders": {},
        "leads": {},
        "managers": [],
        "managers_shop": [],
        "statuses": {},
        "sites": {},
        "products": [],
        "refuse_reasons": {},
        "error": None
    }

    try:
        import pandas as pd

        # Знаходимо найсвіжіший xlsx у папці data/crm/
        files = sorted(CRM_DATA_DIR.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            result["error"] = f"Немає файлів у {CRM_DATA_DIR}/"
            print(f"  ⚠️  CRM Excel: {result['error']}")
            return result

        latest = files[0]
        result["source_file"] = latest.name
        print(f"     📂 Читаю файл: {latest.name}")

        df = pd.read_excel(latest)

        # Парсимо дату
        df["_дата"] = pd.to_datetime(df["Дата"], errors="coerce")
        df["_день"] = df["_дата"].dt.strftime("%Y-%m-%d")

        # Фільтр на потрібну дату
        day_df = df[df["_день"] == date_str].copy()

        if day_df.empty:
            print(f"     ⚠️  Замовлень за {date_str} в файлі немає")
            result["error"] = f"Немає рядків за {date_str}"
            return result

        total_orders  = len(day_df)
        total_revenue = float(day_df["Сума"].fillna(0).sum())

        # ── Статуси ──
        status_counts = day_df["Статус"].fillna("Невідомо").value_counts().to_dict()
        result["statuses"] = status_counts

        # ── Ліди / Замовлення / Відмови (за статусом) ──
        leads_keywords    = ["лід", "недодзвон", "перепродзвон", "автовідповідач", "прозвон обробки", "обробці"]
        refused_keywords  = ["відмова", "відмов"]
        order_keywords    = ["отримано", "відправлено", "їде", "ттн", "контроль", "1с", "виробництв", "черз"]
        spam_keywords     = ["спам", "видалений", "дубль"]

        def categorize(s):
            sl = str(s).lower()
            if any(k in sl for k in spam_keywords):    return "spam"
            if any(k in sl for k in refused_keywords): return "refused"
            if any(k in sl for k in leads_keywords):   return "lead"
            if any(k in sl for k in order_keywords):   return "order"
            return "other"

        day_df["_категорія"] = day_df["Статус"].fillna("").apply(categorize)

        leads_count   = (day_df["_категорія"] == "lead").sum()
        orders_count  = (day_df["_категорія"] == "order").sum()
        refused_count = (day_df["_категорія"] == "refused").sum()
        spam_count    = (day_df["_категорія"] == "spam").sum()

        # Ефективні (не спам)
        valid = day_df[day_df["_категорія"] != "spam"]

        result["orders"] = {
            "total":      int(orders_count + refused_count),
            "revenue":    round(float(valid[valid["_категорія"].isin(["order", "refused"])]["Сума"].fillna(0).sum()), 2),
            "refused":    int(refused_count),
            "refuse_pct": round(refused_count / max(orders_count + refused_count, 1) * 100, 1),
            "spam":       int(spam_count),
            "all_rows":   int(total_orders),
        }
        result["leads"] = {"new_leads": int(leads_count)}

        # ── Менеджери (онлайн) ──
        mgr_df = valid[valid["Менеджер"].notna()]
        managers_agg = mgr_df.groupby("Менеджер").agg(
            orders=("Сума", "count"),
            revenue=("Сума", lambda x: float(x.fillna(0).sum())),
        ).reset_index()
        # Відмови по менеджерах
        refused_by_mgr = mgr_df[mgr_df["_категорія"] == "refused"].groupby("Менеджер").size().to_dict()
        managers_agg["refused"] = managers_agg["Менеджер"].map(refused_by_mgr).fillna(0).astype(int)
        managers_agg["refuse_pct"] = (managers_agg["refused"] / managers_agg["orders"].replace(0, 1) * 100).round(1)

        result["managers"] = [
            {"name": r["Менеджер"], "orders": int(r["orders"]),
             "revenue": round(r["revenue"], 2),
             "refused": int(r["refused"]), "refuse_pct": float(r["refuse_pct"])}
            for _, r in managers_agg.sort_values("revenue", ascending=False).iterrows()
        ]

        # ── Менеджери на магазині ──
        if "Менеджер на магазині" in day_df.columns:
            shop_df = valid[valid["Менеджер на магазині"].notna()]
            shop_agg = shop_df.groupby("Менеджер на магазині").agg(
                orders=("Сума", "count"),
                revenue=("Сума", lambda x: float(x.fillna(0).sum())),
            ).reset_index()
            result["managers_shop"] = [
                {"name": r["Менеджер на магазині"], "orders": int(r["orders"]),
                 "revenue": round(r["revenue"], 2)}
                for _, r in shop_agg.sort_values("revenue", ascending=False).iterrows()
            ]

        # ── Сайти ──
        if "Сайт" in day_df.columns:
            sites_agg = valid[valid["Сайт"].notna()].groupby("Сайт").agg(
                orders=("Сума", "count"),
                revenue=("Сума", lambda x: float(x.fillna(0).sum())),
            ).reset_index()
            result["sites"] = {
                r["Сайт"]: {"orders": int(r["orders"]), "revenue": round(r["revenue"], 2)}
                for _, r in sites_agg.sort_values("revenue", ascending=False).iterrows()
            }

        # ── Топ товарів ──
        if "Назва [Товари/Послуги]" in day_df.columns:
            prod_col = "Назва [Товари/Послуги]"
            prod_df = day_df[day_df[prod_col].notna() & (day_df["_категорія"] != "spam")].copy()
            if "Сума [Товари/Послуги]" in prod_df.columns:
                prod_agg = prod_df.groupby(prod_col).agg(
                    count=(prod_col, "count"),
                    revenue=("Сума [Товари/Послуги]", lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                result["products"] = [
                    {"name": r[prod_col], "count": int(r["count"]), "revenue": round(r["revenue"], 2)}
                    for _, r in prod_agg.sort_values("revenue", ascending=False).head(20).iterrows()
                ]

        # ── Причини відмов ──
        if "Причина відмови ?" in day_df.columns:
            ref_df = day_df[day_df["Причина відмови ?"].notna()]
            if not ref_df.empty:
                reasons = ref_df["Причина відмови ?"].value_counts().head(10).to_dict()
                result["refuse_reasons"] = {str(k): int(v) for k, v in reasons.items()}

    except Exception as e:
        result["error"] = str(e)
        print(f"  ⚠️  CRM помилка: {e}")
        import traceback
        traceback.print_exc()

    return result


# ──────────────────────── META ADS ───────────────────────────

def fetch_meta(date_str: str) -> dict:
    """
    Тягне з Meta Ads API за конкретну дату по всіх кабінетах:
      - Витрати, покази, кліки, CPM, CPC, CTR
      - Результати (конверсії), CPR
      - Розбивка по кампаніях
    """
    result = {
        "date":      date_str,
        "accounts":  [],
        "total": {
            "spend":       0.0,
            "impressions": 0,
            "clicks":      0,
            "cpc":         0.0,
            "cpm":         0.0,
            "ctr":         0.0,
            "results":     0,
            "cpr":         0.0,
        },
        "by_campaign": [],
        "error": None
    }

    total_spend       = 0.0
    total_impressions = 0
    total_clicks      = 0
    total_results     = 0
    all_campaigns     = []

    for acc in META_ACCOUNTS:
        acc_result = {
            "id":          acc["id"],
            "name":        acc["name"],
            "spend":       0.0,
            "impressions": 0,
            "clicks":      0,
            "results":     0,
            "cpc":         0.0,
            "ctr":         0.0,
            "error":       None
        }
        try:
            # ── Загальні метрики по кабінету ──────────────────
            r = requests.get(
                f"https://graph.facebook.com/{META_API_VERSION}/act_{acc['id']}/insights",
                params={
                    "access_token": acc["token"],
                    "time_range":   json.dumps({"since": date_str, "until": date_str}),
                    "fields":       "spend,impressions,clicks,cpc,cpm,ctr,actions,cost_per_action_type",
                    "level":        "account",
                }
            )
            d = r.json()
            if "error" in d:
                acc_result["error"] = d["error"]["message"]
            elif d.get("data"):
                row = d["data"][0]
                spend       = safe_float(row.get("spend", 0))
                impressions = int(row.get("impressions", 0))
                clicks      = int(row.get("clicks", 0))
                cpc         = safe_float(row.get("cpc", 0))
                cpm         = safe_float(row.get("cpm", 0))
                ctr         = safe_float(row.get("ctr", 0))

                # Конверсії (purchase або lead)
                results = 0
                actions = row.get("actions", [])
                for a in actions:
                    if a.get("action_type") in ["purchase", "lead", "offsite_conversion.fb_pixel_purchase"]:
                        results += int(a.get("value", 0))

                acc_result.update({
                    "spend":       round(spend, 2),
                    "impressions": impressions,
                    "clicks":      clicks,
                    "cpc":         round(cpc, 2),
                    "cpm":         round(cpm, 2),
                    "ctr":         round(ctr, 2),
                    "results":     results,
                })
                total_spend       += spend
                total_impressions += impressions
                total_clicks      += clicks
                total_results     += results

            # ── Топ кампанії по кабінету ──────────────────────
            r2 = requests.get(
                f"https://graph.facebook.com/{META_API_VERSION}/act_{acc['id']}/insights",
                params={
                    "access_token": acc["token"],
                    "time_range":   json.dumps({"since": date_str, "until": date_str}),
                    "fields":       "campaign_name,spend,impressions,clicks,cpc,ctr,actions",
                    "level":        "campaign",
                    "limit":        10,
                }
            )
            d2 = r2.json()
            for camp in d2.get("data", []):
                results_c = 0
                for a in camp.get("actions", []):
                    if a.get("action_type") in ["purchase", "lead", "offsite_conversion.fb_pixel_purchase"]:
                        results_c += int(a.get("value", 0))
                all_campaigns.append({
                    "account":     acc["name"],
                    "campaign":    camp.get("campaign_name", ""),
                    "spend":       round(safe_float(camp.get("spend", 0)), 2),
                    "impressions": int(camp.get("impressions", 0)),
                    "clicks":      int(camp.get("clicks", 0)),
                    "cpc":         round(safe_float(camp.get("cpc", 0)), 2),
                    "ctr":         round(safe_float(camp.get("ctr", 0)), 2),
                    "results":     results_c,
                })

        except Exception as e:
            acc_result["error"] = str(e)

        result["accounts"].append(acc_result)

    # Загальні підсумки
    result["total"]["spend"]       = round(total_spend, 2)
    result["total"]["impressions"] = total_impressions
    result["total"]["clicks"]      = total_clicks
    result["total"]["results"]     = total_results
    result["total"]["cpc"]         = round(total_spend / max(total_clicks, 1), 2)
    result["total"]["cpm"]         = round(total_spend / max(total_impressions, 1) * 1000, 2)
    result["total"]["ctr"]         = round(total_clicks / max(total_impressions, 1) * 100, 2)
    result["total"]["cpr"]         = round(total_spend / max(total_results, 1), 2)
    result["by_campaign"]          = sorted(all_campaigns, key=lambda x: x["spend"], reverse=True)

    return result

# ──────────────────────── GOOGLE ANALYTICS 4 ─────────────────

def fetch_ga4(date_str: str) -> dict:
    """
    Тягне з GA4 за конкретну дату:
      - Сесії, користувачі, нові користувачі
      - Відмови, тривалість сесії
      - Топ джерела трафіку
      - Топ сторінки
      - Розбивка по пристроях
    """
    result = {
        "date":          date_str,
        "sessions":      0,
        "users":         0,
        "new_users":     0,
        "bounce_rate":   0.0,
        "avg_duration":  0.0,
        "by_source":     [],
        "by_page":       [],
        "by_device":     [],
        "error":         None
    }
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GA4_CREDENTIALS
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Metric, Dimension, OrderBy
        )

        client   = BetaAnalyticsDataClient()
        prop     = f"properties/{GA4_PROPERTY_ID}"
        dr       = [DateRange(start_date=date_str, end_date=date_str)]

        # ── 1. Загальні метрики ──────────────────────────────
        req = RunReportRequest(
            property=prop, date_ranges=dr,
            metrics=[
                Metric(name="sessions"),
                Metric(name="totalUsers"),
                Metric(name="newUsers"),
                Metric(name="bounceRate"),
                Metric(name="averageSessionDuration"),
            ],
            dimensions=[Dimension(name="date")]
        )
        resp = client.run_report(req)
        if resp.rows:
            v = resp.rows[0].metric_values
            result["sessions"]     = int(v[0].value)
            result["users"]        = int(v[1].value)
            result["new_users"]    = int(v[2].value)
            result["bounce_rate"]  = round(float(v[3].value) * 100, 1)
            result["avg_duration"] = round(float(v[4].value), 0)

        # ── 2. Топ джерела трафіку ───────────────────────────
        req2 = RunReportRequest(
            property=prop, date_ranges=dr,
            metrics=[Metric(name="sessions"), Metric(name="conversions")],
            dimensions=[Dimension(name="sessionSource"), Dimension(name="sessionMedium")],
            limit=10,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)]
        )
        resp2 = client.run_report(req2)
        result["by_source"] = [
            {
                "source":      r.dimension_values[0].value,
                "medium":      r.dimension_values[1].value,
                "sessions":    int(r.metric_values[0].value),
                "conversions": int(r.metric_values[1].value),
            }
            for r in resp2.rows
        ]

        # ── 3. Топ сторінки ──────────────────────────────────
        req3 = RunReportRequest(
            property=prop, date_ranges=dr,
            metrics=[Metric(name="screenPageViews"), Metric(name="bounceRate")],
            dimensions=[Dimension(name="pagePath"), Dimension(name="pageTitle")],
            limit=10,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)]
        )
        resp3 = client.run_report(req3)
        result["by_page"] = [
            {
                "path":   r.dimension_values[0].value,
                "title":  r.dimension_values[1].value,
                "views":  int(r.metric_values[0].value),
                "bounce": round(float(r.metric_values[1].value) * 100, 1),
            }
            for r in resp3.rows
        ]

        # ── 4. Пристрої ──────────────────────────────────────
        req4 = RunReportRequest(
            property=prop, date_ranges=dr,
            metrics=[Metric(name="sessions")],
            dimensions=[Dimension(name="deviceCategory")],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)]
        )
        resp4 = client.run_report(req4)
        total = result["sessions"] or 1
        result["by_device"] = [
            {
                "device":  r.dimension_values[0].value,
                "sessions": int(r.metric_values[0].value),
                "pct":     round(int(r.metric_values[0].value) / total * 100, 1),
            }
            for r in resp4.rows
        ]

    except Exception as e:
        result["error"] = str(e)
        print(f"  ⚠️  GA4 помилка: {e}")

    return result

# ──────────────────────── MAIN ────────────────────────────────

def main():
    # Дата: вчора
    yesterday = datetime.now() - timedelta(days=1)
    day        = fmt_yyyymmdd(yesterday)           # 20260412
    day_iso    = yesterday.strftime("%Y-%m-%d")    # 2026-04-12
    day_disp   = fmt_display(yesterday)            # 12.04.2026

    # Місяць: з 1-го числа до вчора
    m_start_dt = datetime(yesterday.year, yesterday.month, 1)
    m_start    = fmt_yyyymmdd(m_start_dt)
    m_end      = day

    print(f"\n{'='*50}")
    print(f"  UH Analytics — збір даних за {day_disp}")
    print(f"{'='*50}\n")

    data = {
        "date":      day_iso,
        "date_disp": day_disp,
        "month":     f"{m_start_dt.strftime('%d.%m')} – {day_disp}",
        "generated": datetime.now().isoformat(),
    }

    # ── 1С UH ─────────────────────────────────────────────────
    print("📦 Завантаження 1С UH...")
    data["uh"] = fetch_1c_block(
        label="UH",
        api_url=API_URL_UH,
        day=day, m_start=m_start, m_end=m_end,
        user=None, password=None,
        exclude_delivery_on_sales=True,   # Без НП у SALES
    )
    print(f"   ✅ UH ORDERS день:  {data['uh'].get('ORDERS', {}).get('day', {}).get('total', '—')}")
    print(f"   ✅ UH SALES  день:  {data['uh'].get('SALES',  {}).get('day', {}).get('total', '—')}")

    # ── 1С SH ─────────────────────────────────────────────────
    print("\n📦 Завантаження 1С SH...")
    data["sh"] = fetch_1c_block(
        label="SH",
        api_url=API_URL_SH,
        day=day, m_start=m_start, m_end=m_end,
        user=API_SH_USER, password=API_SH_PASS,
        exclude_delivery_on_sales=True,   # Без доставок у SALES
    )
    print(f"   ✅ SH ORDERS день:  {data['sh'].get('ORDERS', {}).get('day', {}).get('total', '—')}")
    print(f"   ✅ SH SALES  день:  {data['sh'].get('SALES',  {}).get('day', {}).get('total', '—')}")

    # ── SalesDrive CRM ────────────────────────────────────────
    print("\n🎯 Завантаження SalesDrive CRM (Excel)...")
    data["crm"] = fetch_salesdrive(day_iso)
    if data["crm"]["error"]:
        print(f"   ⚠️  Помилка CRM: {data['crm']['error']}")
    else:
        print(f"   ✅ Файл:        {data['crm'].get('source_file', '—')}")
        print(f"   ✅ Замовлень:   {data['crm']['orders']['total']}")
        print(f"   ✅ Лідів:       {data['crm']['leads']['new_leads']}")
        print(f"   ✅ Виручка:     {data['crm']['orders']['revenue']:,.0f} ₴")
        print(f"   ✅ Відмови:     {data['crm']['orders']['refused']} ({data['crm']['orders']['refuse_pct']}%)")
        print(f"   ✅ Менеджерів:  {len(data['crm']['managers'])}")
        print(f"   ✅ Сайтів:      {len(data['crm']['sites'])}")
        print(f"   ✅ Товарів:     {len(data['crm']['products'])}")

    # ── Meta Ads ─────────────────────────────────────────────────
    print("\n📱 Завантаження Meta Ads...")
    data["meta"] = fetch_meta(day_iso)
    print(f"   ✅ Витрати:    {data['meta']['total']['spend']} UAH")
    print(f"   ✅ Кліки:      {data['meta']['total']['clicks']}")
    print(f"   ✅ Результати: {data['meta']['total']['results']}")
    print(f"   ✅ CPC:        {data['meta']['total']['cpc']} UAH")
    print(f"   ✅ Кампаній:   {len(data['meta']['by_campaign'])}")

    # ── Google Analytics 4 ───────────────────────────────────────
    print("\n📈 Завантаження Google Analytics 4...")
    data["ga4"] = fetch_ga4(day_iso)
    if data["ga4"]["error"]:
        print(f"   ⚠️  Помилка GA4: {data['ga4']['error']}")
    else:
        print(f"   ✅ Сесії:        {data['ga4']['sessions']}")
        print(f"   ✅ Користувачі:  {data['ga4']['users']}")
        print(f"   ✅ Відмови:      {data['ga4']['bounce_rate']}%")
        print(f"   ✅ Топ джерел:   {len(data['ga4']['by_source'])}")
        print(f"   ✅ Топ сторінок: {len(data['ga4']['by_page'])}")

    # ── Збереження ────────────────────────────────────────────
    out_path = HISTORY_DIR / f"{day_iso}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Збережено: {out_path}")
    print(f"{'='*50}\n")
    return data

if __name__ == "__main__":
    main()
