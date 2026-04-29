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

# SalesDrive CRM
SD_API_KEY  = os.getenv("SD_API_KEY", "l-gTmE_eWopdwozFM9AW78imyzIMOErc52dBd8tTCGXBeTE_TeFvcs6AhjHC4A2kKTVCoL3ufp5fZ7xhRIZ1pU-rpD1GckOAkHEq")
SD_BASE_URL = "https://matrasroll.salesdrive.me"

# Google Sheets (GA4 + Meta)
GSHEET_ID  = os.getenv("GSHEET_ID", "1f92jFNkwG1QS_LswItj01SwVAcDiyg-Tbw0CEfOrqZA")
GSHEET_URL = f"https://docs.google.com/spreadsheets/d/{GSHEET_ID}/export?format=csv&gid=0"


# Meta Ads
META_ACCOUNTS = [
    {"id": "498543759542047",  "name": "Amebli 2024",     "token": "EAAOJViuNgBgBRZArQ2iCiHZCHNj0YGRZCL5LOH0GYDQczs63XLz88BZBDR6wpxNbYfOy7mpHOZCAfHBtltbIVZBwkV9zbqOBTVObYTkPN6WlsOAUgvDPL1evn3eNskpL4n47aQOHRqqtRzkZCPZBDTZAHZBA4MsVzPZA2IaIRXFuhgfijXkE9ZAea57tUZCVIxFNe7UIzOgZDZD"},
    {"id": "785104883775481",  "name": "Amebli",          "token": "EAAyQRTaR3igBRT9cEqsf4uBeNNAa8uPnaGnKkEDQdp01JxAPBOLgY3TWZBrdOmUBYdwv1lIQ3jqlyfQEO5VInfE0utqKCLkJs091QEmAli5EbbvkC05GOxeYCLsrIefhZCLm3L8aEsWRQMk28lS9CIFJp2cOWKPKVDKo60BFYQ7gWzELgWTbB8SSmMfGCgVC4tC8rPCW9M7iZBXZApm0ZCQqUCRs3SeU4aPmN530M"},
    {"id": "1071880631226950", "name": "MatrasRoll 2024", "token": "EAAyQRTaR3igBRT9cEqsf4uBeNNAa8uPnaGnKkEDQdp01JxAPBOLgY3TWZBrdOmUBYdwv1lIQ3jqlyfQEO5VInfE0utqKCLkJs091QEmAli5EbbvkC05GOxeYCLsrIefhZCLm3L8aEsWRQMk28lS9CIFJp2cOWKPKVDKo60BFYQ7gWzELgWTbB8SSmMfGCgVC4tC8rPCW9M7iZBXZApm0ZCQqUCRs3SeU4aPmN530M"},
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

# Статуси SalesDrive
SD_STATUSES = {
    1:  "Нова",          2:  "В обробці",      3:  "Контроль оператора",
    4:  "Відправлено",   5:  "Отримано",        6:  "Відмова (не відпр)",
    7:  "Рекламація",    8:  "Видалений",       9:  "Контроль оплати",
    12: "Спам/Дубль",   14: "Недозвон",        15: "Питання по замовленню",
    16: "Відмова (відпр)", 17: "Внесено в 1С", 18: "Лід (не купив)",
    19: "Сервісний дзвінок", 20: "Перепродзвон", 21: "Автовідповідач",
    22: "Прозвон обробки",   23: "Виправити дані", 24: "Лід недодзвон",
    33: "Лід ЧАТИ",     34: "Перенесено UH",   35: "Обробка Чати",
    36: "Створена ТТН",  37: "Їде до клієнта",  38: "Прибув у відділення",
    39: "Переадресація", 40: "Закінч. термін",  41: "Виробництво",
    42: "Йде на шоу-рум", 51: "Повторне звернення", 69: "В виробництві",
    70: "В черзі відпр",   75: "Рекламний спам",    77: "На прорахунку",
    79: "Створена з TG",   80: "Спам на узгодження",
}
# Групи статусів
SD_LEADS    = {1, 2, 18, 20, 21, 22, 24, 33}          # ліди
SD_ORDERS   = {3, 4, 5, 9, 15, 17, 36, 37, 38, 42, 69, 70}  # замовлення
SD_REFUSED  = {6, 16, 7}                               # відмови
SD_SPAM     = {8, 12, 75, 80}                          # виключаємо

def fetch_salesdrive(date_str: str) -> dict:
    """
    date_str — YYYY-MM-DD
    Фільтрує по полю orderTime (реальне поле дати в SalesDrive API)
    """
    result = {"date": date_str, "orders": {}, "leads": {}, "managers": [], "statuses": {}, "error": None}
    try:
        # Завантажуємо всі замовлення з пагінацією, фільтруємо по orderTime на стороні клієнта
        all_orders = []
        page = 1
        while True:
            resp = sd_get("/api/order/list/", {"limit": 100, "page": page})
            batch = resp.get("data", resp.get("list", []))
            if not batch:
                break
            # Фільтр по orderTime == date_str
            day_orders = [o for o in batch if str(o.get("orderTime", ""))[:10] == date_str]
            all_orders.extend(day_orders)
            # Якщо перший запис вже старіший — зупиняємось
            if batch:
                oldest = str(batch[-1].get("orderTime", ""))[:10]
                if oldest < date_str:
                    break
            if len(batch) < 100:
                break
            page += 1
            if page > 20:
                break

        total_revenue = 0.0
        status_counts = {}
        manager_stats = {}
        refused = 0
        leads_count = 0
        orders_count = 0

        for o in all_orders:
            status_id = int(o.get("statusId") or 0)
            # Пропускаємо спам
            if status_id in SD_SPAM:
                continue

            status_name = SD_STATUSES.get(status_id, f"Статус {status_id}")
            revenue = safe_float(o.get("leadsSalesAmount") or o.get("paymentAmount") or 0)

            # Рахуємо тільки замовлення (не ліди) у виручку
            if status_id in SD_ORDERS or status_id in SD_REFUSED:
                total_revenue += revenue
                orders_count += 1
            if status_id in SD_LEADS:
                leads_count += 1
            if status_id in SD_REFUSED:
                refused += 1

            status_counts[status_name] = status_counts.get(status_name, 0) + 1

            # Менеджер — беремо з formId як ідентифікатор (userId порожній)
            mgr_id = str(o.get("userId") or o.get("formId") or "?")
            mgr_name = f"Менеджер {mgr_id}"
            if mgr_id not in manager_stats:
                manager_stats[mgr_id] = {"name": mgr_name, "orders": 0, "revenue": 0.0, "refused": 0}
            if status_id in SD_ORDERS or status_id in SD_REFUSED:
                manager_stats[mgr_id]["orders"] += 1
                manager_stats[mgr_id]["revenue"] += revenue
            if status_id in SD_REFUSED:
                manager_stats[mgr_id]["refused"] += 1

        result["orders"] = {
            "total":      orders_count,
            "revenue":    round(total_revenue, 2),
            "refused":    refused,
            "refuse_pct": round(refused / max(orders_count, 1) * 100, 1),
            "leads":      leads_count,
        }
        result["leads"]    = {"new_leads": leads_count}
        result["statuses"] = status_counts
        result["managers"] = [
            {"name": s["name"], "orders": s["orders"], "revenue": round(s["revenue"], 2),
             "refused": s["refused"], "refuse_pct": round(s["refused"] / max(s["orders"], 1) * 100, 1)}
            for s in sorted(manager_stats.values(), key=lambda x: x["revenue"], reverse=True)
        ]
    except Exception as e:
        result["error"] = str(e)
        print(f"  ⚠️  SalesDrive помилка: {e}")
    return result


# ──────────────────────── GOOGLE SHEETS ───────────────────────

def fetch_gsheet(date_str: str) -> dict:
    """
    Завантажує дані GA4 + Meta з Google Sheets за конкретну дату.
    Колонки: Day | Source | Campaign | Sessions | Total users |
             Ads cost | Ads clicks | Ads cost per click
    """
    result = {
        "date":     date_str,
        "sessions": 0,
        "users":    0,
        "ads_cost": 0.0,
        "ads_clicks": 0,
        "cpc":      0.0,
        "by_source":   {},
        "by_campaign": {},
        "error":    None
    }
    try:
        r = requests.get(GSHEET_URL, timeout=(5, 30))
        r.raise_for_status()

        # Парсимо CSV (перший рядок — заголовок таблиці, другий — колонки)
        lines = r.content.decode("utf-8")
        reader = csv.reader(io.StringIO(lines))
        next(reader)  # пропускаємо рядок з назвою таблиці
        headers = next(reader)  # Day, Source, Campaign, Sessions, ...

        # Індекси колонок
        idx = {h.strip(): i for i, h in enumerate(headers)}

        total_sessions = 0
        total_users    = 0
        total_cost     = 0.0
        total_clicks   = 0
        by_source      = {}
        by_campaign    = {}

        for row in reader:
            if not row or not row[0]:
                continue
            row_date = row[idx.get("Day", 0)].strip()
            if row_date != date_str:
                continue

            source   = row[idx.get("Source", 1)].strip()
            campaign = row[idx.get("Campaign", 2)].strip()
            sessions = int(row[idx.get("Sessions", 3)] or 0)
            users    = int(row[idx.get("Total users", 4)] or 0)

            # Витрати — прибираємо $ та пробіли
            cost_raw = row[idx.get("Ads cost", 5)].replace("$","").replace(",",".").strip()
            cost     = safe_float(cost_raw)
            clicks   = int(row[idx.get("Ads clicks", 6)] or 0)

            total_sessions += sessions
            total_users    += users
            total_cost     += cost
            total_clicks   += clicks

            # Агрегація по джерелах
            if source not in by_source:
                by_source[source] = {"sessions": 0, "cost": 0.0, "clicks": 0}
            by_source[source]["sessions"] += sessions
            by_source[source]["cost"]     += cost
            by_source[source]["clicks"]   += clicks

            # Агрегація по кампаніях (тільки платні)
            if cost > 0 and campaign and campaign not in ["(not set)", "(direct)"]:
                if campaign not in by_campaign:
                    by_campaign[campaign] = {"sessions": 0, "cost": 0.0, "clicks": 0}
                by_campaign[campaign]["sessions"] += sessions
                by_campaign[campaign]["cost"]     += cost
                by_campaign[campaign]["clicks"]   += clicks

        cpc = round(total_cost / max(total_clicks, 1), 2)

        result["sessions"]    = total_sessions
        result["users"]       = total_users
        result["ads_cost"]    = round(total_cost, 2)
        result["ads_clicks"]  = total_clicks
        result["cpc"]         = cpc
        result["by_source"]   = dict(sorted(
            by_source.items(), key=lambda x: x[1]["sessions"], reverse=True
        )[:10])
        result["by_campaign"] = dict(sorted(
            by_campaign.items(), key=lambda x: x[1]["cost"], reverse=True
        )[:10])

    except Exception as e:
        result["error"] = str(e)
        print(f"  ⚠️  Google Sheets помилка: {e}")

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
    print("\n🎯 Завантаження SalesDrive CRM...")
    data["crm"] = fetch_salesdrive(day_iso)
    if data["crm"]["error"]:
        print(f"   ⚠️  Помилка CRM: {data['crm']['error']}")
    else:
        print(f"   ✅ Замовлень: {data['crm']['orders']['total']}")
        print(f"   ✅ Виручка:   {data['crm']['orders']['revenue']}")
        print(f"   ✅ Відмови:   {data['crm']['orders']['refuse_pct']}%")
        print(f"   ✅ Менеджерів: {len(data['crm']['managers'])}")

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

    # ── Google Sheets (GA4 + Meta) ───────────────────────────────
    print("\n📊 Завантаження Google Sheets (GA4 + Meta)...")
    data["gsheet"] = fetch_gsheet(day_iso)
    if data["gsheet"]["error"]:
        print(f"   ⚠️  Помилка: {data['gsheet']['error']}")
    else:
        print(f"   ✅ Сесій:     {data['gsheet']['sessions']}")
        print(f"   ✅ Витрати:   ${data['gsheet']['ads_cost']}")
        print(f"   ✅ Кліки:     {data['gsheet']['ads_clicks']}")
        print(f"   ✅ CPC:       ${data['gsheet']['cpc']}")

    # ── Збереження ────────────────────────────────────────────
    out_path = HISTORY_DIR / f"{day_iso}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Збережено: {out_path}")
    print(f"{'='*50}\n")
    return data

if __name__ == "__main__":
    main()
