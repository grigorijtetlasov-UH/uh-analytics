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

def is_refused_1c(r: dict) -> bool:
    """Перевіряє чи замовлення в статусі 'Отказ' (Не отправлен / Отправлен)."""
    text = " ".join([
        str(r.get("Стан", "") or ""),
        str(r.get("Статус", "") or ""),
        str(r.get("СтатусЗамовлення", "") or ""),
        str(r.get("СтанЗамовлення", "") or ""),
    ]).lower()
    # Шукаємо "отказ" в будь-якому регістрі і мові
    return ("отказ" in text) or ("відмов" in text) or ("отказано" in text)

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
    ORDERS і ORDERSWD: розділяє на основні замовлення і відмови ("Отказ").
    SALES: реальні відгрузки.
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

            # Для ORDERS і ORDERSWD виділяємо відмови окремо
            if type_key in ("ORDERS", "ORDERSWD"):
                day_active   = [r for r in rows_day if not is_refused_1c(r)]
                day_refused  = [r for r in rows_day if is_refused_1c(r)]
                m_active     = [r for r in rows_m if not is_refused_1c(r)]
                m_refused    = [r for r in rows_m if is_refused_1c(r)]

                result[type_key] = {
                    "day":          agg_by_podr(day_active, sum_key),
                    "day_refused":  agg_by_podr(day_refused, sum_key),
                    "month": {
                        "total": round(sum(safe_float(r.get(sum_key)) for r in m_active), 2),
                        "count": len(m_active)
                    },
                    "month_refused": {
                        "total": round(sum(safe_float(r.get(sum_key)) for r in m_refused), 2),
                        "count": len(m_refused)
                    }
                }
            else:
                # SALES — без розділення (там немає "Отказ")
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
    Розширений збір з Excel SalesDrive — всі ключові поля для дашборду.
    """
    result = {
        "date":           date_str,
        "source_file":    None,
        "orders":         {},
        "leads":          {},
        "managers":       [],
        "managers_shop":  [],
        "chatters":       [],
        "statuses":       {},
        "sites":          {},
        "products":       [],
        "categories":     {},   # Категорія звернення
        "request_types":  {},   # Тип звернення (Корзина/Чат/Дзвінок)
        "payment_methods":{},   # Спосіб оплати
        "delivery_types": {},   # Тип доставки
        "carriers":       {},   # Перевізник
        "warehouses":     {},   # Склад
        "refuse_reasons": {},
        "lead_objections":{},   # Проблемне заперечення
        "process_reasons":{},   # Причина обробки
        "trend_30d":      [],   # Динаміка за 30 днів
        "month_total":    {},   # Підсумок місяця
        "error": None
    }

    try:
        import pandas as pd

        files = sorted(CRM_DATA_DIR.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            result["error"] = f"Немає файлів у {CRM_DATA_DIR}/"
            print(f"  ⚠️  CRM Excel: {result['error']}")
            return result

        latest = files[0]
        result["source_file"] = latest.name
        print(f"     📂 Читаю файл: {latest.name}")

        df = pd.read_excel(latest)
        df["_дата"] = pd.to_datetime(df["Дата"], errors="coerce")
        df["_день"] = df["_дата"].dt.strftime("%Y-%m-%d")
        df["_місяць"] = df["_дата"].dt.strftime("%Y-%m")

        target_month = date_str[:7]
        day_df = df[df["_день"] == date_str].copy()
        month_df = df[df["_місяць"] == target_month].copy()

        if day_df.empty:
            print(f"     ⚠️  Замовлень за {date_str} немає")
            result["error"] = f"Немає рядків за {date_str}"
            return result

        # ── Категоризація статусів (точне зіставлення з SalesDrive) ──
        # Замовлення (продажі) — підтверджені статуси з фільтра 1С/SD
        ORDER_STATUSES = {
            "виправити дані",
            "створена ттн",
            "їде до клієнта",
            "прибув у відділення",
            "переадресація",
            "в виробництві",
            "в черзі на відправлення",
            "контроль оператора",
            "контроль оплати",
            "відправлено",
            "отримано",
            "повернення",  # повернення це теж замовлення (вже відвантажене)
        }
        # Відмови (НЕ зараховуються в замовлення)
        REFUSED_STATUSES = {
            "відмова (відправлено)",
            "відмова (не відправлено)",
            "відмова",
            "лід (не купив)",
        }
        # Ліди (на стадії обробки, ще не замовлення)
        LEAD_STATUSES = {
            "новий",
            "недодзвон",
            "автовідповідач",
            "повторне звернення",
            "потрібне уточнення/перезвон",
            "питання по замовленню",
            "в обробці",
            "відвідає шоу-рум",
        }
        # Спам / технічні (повністю виключаються з продажів)
        SPAM_STATUSES = {
            "спам на согласовании",
            "рекламный спам",
            "спам",
            "видалений",
            "дубль",
        }

        def categorize(s):
            sl = str(s).strip().lower()
            if sl in ORDER_STATUSES:   return "order"
            if sl in REFUSED_STATUSES: return "refused"
            if sl in LEAD_STATUSES:    return "lead"
            if sl in SPAM_STATUSES:    return "spam"
            # fallback на ключові слова для невідомих
            if "відмов" in sl: return "refused"
            if "спам" in sl:   return "spam"
            if "лід" in sl:    return "lead"
            return "other"

        day_df["_категорія"] = day_df["Статус"].fillna("").apply(categorize)
        month_df["_категорія"] = month_df["Статус"].fillna("").apply(categorize)

        leads_count   = (day_df["_категорія"] == "lead").sum()
        orders_count  = (day_df["_категорія"] == "order").sum()
        refused_count = (day_df["_категорія"] == "refused").sum()
        spam_count    = (day_df["_категорія"] == "spam").sum()

        valid = day_df[day_df["_категорія"] != "spam"]
        valid_orders = valid[valid["_категорія"].isin(["order", "refused"])]

        # ── ДЕДУПЛІКАЦІЯ ─────────────────────────────────────
        # В Excel КОЖЕН ТОВАР = окремий рядок, але "Сума" = сума всього замовлення
        # яка ДУБЛЮЄТЬСЯ для кожної товарної позиції.
        # Тому групуємо по унікальній заявці (Дата + Контакт) і беремо першу "Сума".
        # Альтернатива: підсумувати "Сума [Товари/Послуги]" — це сума по позиціях.

        def dedup_key_cols(df_):
            """Колонки що ідентифікують унікальну заявку"""
            cols = []
            for c in ["Дата", "Ім'я [Контакт]", "Телефон [Контакт]"]:
                if c in df_.columns:
                    cols.append(c)
            return cols

        def unique_orders_count(df_):
            """К-сть унікальних заявок (за датою + контактом)"""
            keys = dedup_key_cols(df_)
            if not keys or df_.empty:
                return len(df_)
            return df_.drop_duplicates(subset=keys).shape[0]

        def sum_unique(df_):
            """Сума по УНІКАЛЬНИМ заявкам (без дублів за рядками-товарами)."""
            if df_.empty:
                return 0.0
            keys = dedup_key_cols(df_)
            if not keys:
                # fallback: сумуємо "Сума [Товари/Послуги]"
                if "Сума [Товари/Послуги]" in df_.columns:
                    return float(df_["Сума [Товари/Послуги]"].fillna(0).sum())
                return float(df_["Сума"].fillna(0).sum())
            uniq = df_.drop_duplicates(subset=keys)
            return float(uniq["Сума"].fillna(0).sum())

        # Точні рахунки унікальних заявок
        unique_all_count    = unique_orders_count(day_df)
        unique_valid_count  = unique_orders_count(valid)
        unique_orders_only  = unique_orders_count(valid_orders)
        unique_leads_count  = unique_orders_count(day_df[day_df["_категорія"] == "lead"])
        unique_refused_count = unique_orders_count(day_df[day_df["_категорія"] == "refused"])
        unique_spam_count   = unique_orders_count(day_df[day_df["_категорія"] == "spam"])

        # Суми (по унікальним заявкам)
        sum_all_requests   = sum_unique(day_df)
        sum_no_spam        = sum_unique(valid)
        sum_orders_only    = sum_unique(valid_orders)
        avg_check = sum_orders_only / max(unique_orders_only, 1)

        result["orders"] = {
            "total":            int(unique_orders_only),
            "all_requests":     int(unique_all_count),
            "sum_all":          round(sum_all_requests, 2),
            "sum_no_spam":      round(sum_no_spam, 2),
            "sum_orders":       round(sum_orders_only, 2),
            "revenue":          round(sum_orders_only, 2),
            "refused":          int(unique_refused_count),
            "refuse_pct":       round(unique_refused_count / max(unique_orders_only, 1) * 100, 1),
            "spam":             int(unique_spam_count),
            "all_rows":         int(len(day_df)),
            "avg_check":        round(avg_check, 2),
        }
        result["leads"] = {"new_leads": int(unique_leads_count)}

        # ── Місячний підсумок (дедупльоване) ──
        month_valid = month_df[month_df["_категорія"] != "spam"]
        month_orders = month_valid[month_valid["_категорія"].isin(["order", "refused"])]
        m_keys = dedup_key_cols(month_df)
        if m_keys:
            month_orders_uniq = month_orders.drop_duplicates(subset=m_keys)
            month_uniq_local = month_df.drop_duplicates(subset=m_keys)
        else:
            month_orders_uniq = month_orders
            month_uniq_local = month_df
        result["month_total"] = {
            "orders":  int(len(month_orders_uniq)),
            "revenue": round(float(month_orders_uniq["Сума"].fillna(0).sum()), 2),
            "leads":   int((month_uniq_local["_категорія"] == "lead").sum()),
            "refused": int((month_uniq_local["_категорія"] == "refused").sum()),
        }

        # ── Тренд 30 днів ──
        end_dt = pd.to_datetime(date_str)
        start_dt = end_dt - pd.Timedelta(days=29)
        trend_df = df[(df["_дата"] >= start_dt) & (df["_дата"] <= end_dt)].copy()
        trend_df["_категорія"] = trend_df["Статус"].fillna("").apply(categorize)
        trend_valid = trend_df[trend_df["_категорія"] != "spam"]
        # Дедуплікація по днях
        trend_keys = dedup_key_cols(trend_df) if not trend_df.empty else []
        if trend_keys:
            trend_valid_uniq = trend_valid.drop_duplicates(subset=trend_keys)
            trend_uniq = trend_df.drop_duplicates(subset=trend_keys)
        else:
            trend_valid_uniq = trend_valid
            trend_uniq = trend_df
        daily = trend_valid_uniq.groupby("_день").agg(
            orders=("Сума", "count"),
            revenue=("Сума", lambda x: float(x.fillna(0).sum())),
        ).reset_index()
        daily_leads = trend_uniq[trend_uniq["_категорія"] == "lead"].groupby("_день").size().to_dict()
        daily_refused = trend_uniq[trend_uniq["_категорія"] == "refused"].groupby("_день").size().to_dict()
        result["trend_30d"] = [
            {"date": r["_день"],
             "orders": int(r["orders"]),
             "revenue": round(float(r["revenue"]), 2),
             "leads": int(daily_leads.get(r["_день"], 0)),
             "refused": int(daily_refused.get(r["_день"], 0))}
            for _, r in daily.iterrows()
        ]

        # ── Статуси (всі) — теж дедупльовані ──
        # Дедуплікуємо для агрегаційних обчислень (одна заявка = один рядок)
        mgr_keys = dedup_key_cols(day_df)
        valid_uniq = valid.drop_duplicates(subset=mgr_keys) if mgr_keys else valid
        day_uniq = day_df.drop_duplicates(subset=mgr_keys) if mgr_keys else day_df
        result["statuses"] = day_uniq["Статус"].fillna("Невідомо").value_counts().to_dict() if not day_uniq.empty else {}

        # ── Менеджери (онлайн) ──
        # valid_uniq і day_uniq вже визначені вище (для статусів)
        mgr_df = valid_uniq[valid_uniq["Менеджер"].notna()]
        if not mgr_df.empty:
            agg = mgr_df.groupby("Менеджер").agg(
                orders=("Сума", "count"),
                revenue=("Сума", lambda x: float(x.fillna(0).sum())),
            ).reset_index()
            refused_by_mgr = mgr_df[mgr_df["_категорія"] == "refused"].groupby("Менеджер").size().to_dict()
            leads_by_mgr = day_uniq[(day_uniq["_категорія"] == "lead") & day_uniq["Менеджер"].notna()].groupby("Менеджер").size().to_dict()
            agg["refused"] = agg["Менеджер"].map(refused_by_mgr).fillna(0).astype(int)
            agg["leads"] = agg["Менеджер"].map(leads_by_mgr).fillna(0).astype(int)
            agg["refuse_pct"] = (agg["refused"] / agg["orders"].replace(0, 1) * 100).round(1)
            agg["avg_check"] = (agg["revenue"] / agg["orders"].replace(0, 1)).round(0)
            agg["conv"] = (agg["orders"] / (agg["orders"] + agg["leads"]).replace(0, 1) * 100).round(1)
            result["managers"] = [
                {"name": r["Менеджер"], "orders": int(r["orders"]),
                 "revenue": round(r["revenue"], 2),
                 "refused": int(r["refused"]), "refuse_pct": float(r["refuse_pct"]),
                 "leads": int(r["leads"]), "avg_check": float(r["avg_check"]),
                 "conv": float(r["conv"])}
                for _, r in agg.sort_values("revenue", ascending=False).iterrows()
            ]

        # ── Менеджери на магазині ──
        if "Менеджер на магазині" in day_df.columns:
            shop_df = valid_uniq[valid_uniq["Менеджер на магазині"].notna()]
            if not shop_df.empty:
                agg = shop_df.groupby("Менеджер на магазині").agg(
                    orders=("Сума", "count"),
                    revenue=("Сума", lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                agg["avg_check"] = (agg["revenue"] / agg["orders"].replace(0, 1)).round(0)
                result["managers_shop"] = [
                    {"name": r["Менеджер на магазині"], "orders": int(r["orders"]),
                     "revenue": round(r["revenue"], 2), "avg_check": float(r["avg_check"])}
                    for _, r in agg.sort_values("revenue", ascending=False).iterrows()
                ]

        # ── Чатери ──
        if "Відповідальний чатер" in day_df.columns:
            chat_df = valid_uniq[valid_uniq["Відповідальний чатер"].notna()]
            if not chat_df.empty:
                agg = chat_df.groupby("Відповідальний чатер").agg(
                    orders=("Сума", "count"),
                    revenue=("Сума", lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                result["chatters"] = [
                    {"name": r["Відповідальний чатер"], "orders": int(r["orders"]),
                     "revenue": round(r["revenue"], 2)}
                    for _, r in agg.sort_values("revenue", ascending=False).iterrows()
                ]

        # ── Сайти ──
        if "Сайт" in day_df.columns:
            sites_df = valid_uniq[valid_uniq["Сайт"].notna()]
            if not sites_df.empty:
                agg = sites_df.groupby("Сайт").agg(
                    orders=("Сума", "count"),
                    revenue=("Сума", lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                agg["avg_check"] = (agg["revenue"] / agg["orders"].replace(0, 1)).round(0)
                result["sites"] = {
                    r["Сайт"]: {"orders": int(r["orders"]),
                                "revenue": round(r["revenue"], 2),
                                "avg_check": float(r["avg_check"])}
                    for _, r in agg.sort_values("revenue", ascending=False).iterrows()
                }

        # ── Категорії звернення (Топер/Матрац/Диван) ──
        if "Категорія звернення" in day_df.columns:
            cat = day_uniq[day_uniq["Категорія звернення"].notna()]["Категорія звернення"].value_counts().head(15).to_dict()
            result["categories"] = {str(k): int(v) for k, v in cat.items()}

        # ── Тип звернення (Корзина/Чат/Дзвінок) ──
        if "Тип звернення" in day_df.columns:
            rt = day_uniq[day_uniq["Тип звернення"].notna()]["Тип звернення"].value_counts().head(10).to_dict()
            result["request_types"] = {str(k): int(v) for k, v in rt.items()}

        # ── Спосіб оплати ──
        if "Спосіб оплати" in day_df.columns:
            pm = valid_uniq[valid_uniq["Спосіб оплати"].notna()]["Спосіб оплати"].value_counts().head(10).to_dict()
            result["payment_methods"] = {str(k): int(v) for k, v in pm.items()}

        # ── Тип доставки ──
        if "Тип доставки" in day_df.columns:
            dt_ = valid_uniq[valid_uniq["Тип доставки"].notna()]["Тип доставки"].value_counts().to_dict()
            result["delivery_types"] = {str(k): int(v) for k, v in dt_.items()}

        # ── Перевізник ──
        if "Перевізник" in day_df.columns:
            cr = valid_uniq[valid_uniq["Перевізник"].notna()]["Перевізник"].value_counts().head(10).to_dict()
            result["carriers"] = {str(k): int(v) for k, v in cr.items()}

        # ── Склад ──
        if "Склад" in day_df.columns:
            wh = valid_uniq[valid_uniq["Склад"].notna()]["Склад"].value_counts().to_dict()
            result["warehouses"] = {str(k): int(v) for k, v in wh.items()}

        # ── Топ товарів ──
        if "Назва [Товари/Послуги]" in day_df.columns:
            prod_col = "Назва [Товари/Послуги]"
            sum_col  = "Сума [Товари/Послуги]" if "Сума [Товари/Послуги]" in day_df.columns else "Сума"
            qty_col  = "К-ть [Товари/Послуги]" if "К-ть [Товари/Послуги]" in day_df.columns else None
            prod_df = day_df[day_df[prod_col].notna() & (day_df["_категорія"] != "spam")].copy()
            # Фільтр доставок
            prod_df = prod_df[~prod_df[prod_col].str.lower().str.contains("доставка|нова пошта|укрпошт|самовивіз|сборка|занос", na=False)]
            if not prod_df.empty:
                grp = prod_df.groupby(prod_col).agg(
                    count=(prod_col, "count"),
                    revenue=(sum_col, lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                if qty_col and qty_col in prod_df.columns:
                    qty_grp = prod_df.groupby(prod_col)[qty_col].sum().reset_index()
                    grp = grp.merge(qty_grp, on=prod_col, how="left")
                result["products"] = [
                    {"name": r[prod_col], "count": int(r["count"]),
                     "revenue": round(r["revenue"], 2),
                     "qty": int(r.get(qty_col, r["count"])) if qty_col else int(r["count"])}
                    for _, r in grp.sort_values("revenue", ascending=False).head(30).iterrows()
                ]

        # ── Причини відмов ──
        if "Причина відмови ?" in day_df.columns:
            rr = day_uniq[day_uniq["Причина відмови ?"].notna()]["Причина відмови ?"].value_counts().head(15).to_dict()
            result["refuse_reasons"] = {str(k): int(v) for k, v in rr.items()}

        # ── Заперечення лідів ──
        if "Проблемне заперечення" in day_df.columns:
            lo = day_uniq[day_uniq["Проблемне заперечення"].notna()]["Проблемне заперечення"].value_counts().head(10).to_dict()
            result["lead_objections"] = {str(k): int(v) for k, v in lo.items()}

        # ── Причини обробки ──
        if "Причина обробки" in day_df.columns:
            pr = day_uniq[day_uniq["Причина обробки"].notna()]["Причина обробки"].value_counts().head(10).to_dict()
            result["process_reasons"] = {str(k): int(v) for k, v in pr.items()}

    except Exception as e:
        result["error"] = str(e)
        print(f"  ⚠️  CRM помилка: {e}")
        import traceback
        traceback.print_exc()

    return result



def aggregate_month_crm(target_month: str) -> dict:
    """
    Збирає повну місячну аналітику з Excel за target_month (YYYY-MM).
    Повертає всі ті ж поля, що і денний fetch_salesdrive, але за весь місяць.
    """
    result = {
        "month":           target_month,
        "source_file":     None,
        "orders":          {},
        "leads":           {},
        "managers":        [],
        "managers_shop":   [],
        "chatters":        [],
        "statuses":        {},
        "sites":           {},
        "products":        [],
        "categories":      {},
        "request_types":   {},
        "payment_methods": {},
        "delivery_types":  {},
        "carriers":        {},
        "warehouses":      {},
        "refuse_reasons":  {},
        "lead_objections": {},
        "process_reasons": {},
        "daily_trend":     [],   # тренд по днях у межах місяця
        "error":           None
    }
    try:
        import pandas as pd

        files = sorted(CRM_DATA_DIR.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            result["error"] = f"Немає файлів у {CRM_DATA_DIR}/"
            return result

        latest = files[0]
        result["source_file"] = latest.name

        df = pd.read_excel(latest)
        df["_дата"] = pd.to_datetime(df["Дата"], errors="coerce")
        df["_день"] = df["_дата"].dt.strftime("%Y-%m-%d")
        df["_місяць"] = df["_дата"].dt.strftime("%Y-%m")

        month_df = df[df["_місяць"] == target_month].copy()
        if month_df.empty:
            result["error"] = f"Немає рядків за {target_month}"
            return result

        # ── Категоризація статусів (місяць, точне зіставлення) ──
        # Замовлення (продажі) — підтверджені статуси з фільтра 1С/SD
        ORDER_STATUSES = {
            "виправити дані",
            "створена ттн",
            "їде до клієнта",
            "прибув у відділення",
            "переадресація",
            "в виробництві",
            "в черзі на відправлення",
            "контроль оператора",
            "контроль оплати",
            "відправлено",
            "отримано",
            "повернення",  # повернення це теж замовлення (вже відвантажене)
        }
        # Відмови (НЕ зараховуються в замовлення)
        REFUSED_STATUSES = {
            "відмова (відправлено)",
            "відмова (не відправлено)",
            "відмова",
            "лід (не купив)",
        }
        # Ліди (на стадії обробки, ще не замовлення)
        LEAD_STATUSES = {
            "новий",
            "недодзвон",
            "автовідповідач",
            "повторне звернення",
            "потрібне уточнення/перезвон",
            "питання по замовленню",
            "в обробці",
            "відвідає шоу-рум",
        }
        # Спам / технічні (повністю виключаються з продажів)
        SPAM_STATUSES = {
            "спам на согласовании",
            "рекламный спам",
            "спам",
            "видалений",
            "дубль",
        }

        def categorize(s):
            sl = str(s).strip().lower()
            if sl in ORDER_STATUSES:   return "order"
            if sl in REFUSED_STATUSES: return "refused"
            if sl in LEAD_STATUSES:    return "lead"
            if sl in SPAM_STATUSES:    return "spam"
            # fallback на ключові слова для невідомих
            if "відмов" in sl: return "refused"
            if "спам" in sl:   return "spam"
            if "лід" in sl:    return "lead"
            return "other"

        month_df["_категорія"] = month_df["Статус"].fillna("").apply(categorize)
        valid = month_df[month_df["_категорія"] != "spam"]
        valid_orders = valid[valid["_категорія"].isin(["order", "refused"])]

        leads_count   = (month_df["_категорія"] == "lead").sum()
        orders_count  = (month_df["_категорія"] == "order").sum()
        refused_count = (month_df["_категорія"] == "refused").sum()
        spam_count    = (month_df["_категорія"] == "spam").sum()

        # ── ДЕДУПЛІКАЦІЯ (так само як у денному) ──
        def dedup_key_cols_m(df_):
            cols = []
            for c in ["Дата", "Ім'я [Контакт]", "Телефон [Контакт]"]:
                if c in df_.columns:
                    cols.append(c)
            return cols

        def unique_count_m(df_):
            keys = dedup_key_cols_m(df_)
            if not keys or df_.empty:
                return len(df_)
            return df_.drop_duplicates(subset=keys).shape[0]

        def sum_unique_m(df_):
            if df_.empty:
                return 0.0
            keys = dedup_key_cols_m(df_)
            if not keys:
                return float(df_["Сума"].fillna(0).sum())
            return float(df_.drop_duplicates(subset=keys)["Сума"].fillna(0).sum())

        unique_all_count    = unique_count_m(month_df)
        unique_orders_only  = unique_count_m(valid_orders)
        unique_leads_count  = unique_count_m(month_df[month_df["_категорія"] == "lead"])
        unique_refused_count = unique_count_m(month_df[month_df["_категорія"] == "refused"])
        unique_spam_count   = unique_count_m(month_df[month_df["_категорія"] == "spam"])

        sum_all_requests = sum_unique_m(month_df)
        sum_no_spam      = sum_unique_m(valid)
        sum_orders_only  = sum_unique_m(valid_orders)
        avg_check        = sum_orders_only / max(unique_orders_only, 1)

        # Дедупльовані df-и для менеджерів/сайтів
        keys_m = dedup_key_cols_m(month_df)
        valid_uniq_m = valid.drop_duplicates(subset=keys_m) if keys_m else valid
        month_uniq   = month_df.drop_duplicates(subset=keys_m) if keys_m else month_df

        result["orders"] = {
            "total":            int(unique_orders_only),
            "all_requests":     int(unique_all_count),
            "sum_all":          round(sum_all_requests, 2),
            "sum_no_spam":      round(sum_no_spam, 2),
            "sum_orders":       round(sum_orders_only, 2),
            "revenue":          round(sum_orders_only, 2),
            "refused":          int(unique_refused_count),
            "refuse_pct":       round(unique_refused_count / max(unique_orders_only, 1) * 100, 1),
            "spam":             int(unique_spam_count),
            "all_rows":         int(len(month_df)),
            "avg_check":        round(avg_check, 2),
        }
        result["leads"] = {"new_leads": int(unique_leads_count)}
        result["statuses"] = month_uniq["Статус"].fillna("Невідомо").value_counts().to_dict()

        # ── Менеджери ──
        mgr_df = valid_uniq_m[valid_uniq_m["Менеджер"].notna()]
        if not mgr_df.empty:
            agg = mgr_df.groupby("Менеджер").agg(
                orders=("Сума", "count"),
                revenue=("Сума", lambda x: float(x.fillna(0).sum())),
            ).reset_index()
            refused_by_mgr = mgr_df[mgr_df["_категорія"] == "refused"].groupby("Менеджер").size().to_dict()
            leads_by_mgr   = month_uniq[(month_uniq["_категорія"] == "lead") & month_uniq["Менеджер"].notna()].groupby("Менеджер").size().to_dict()
            agg["refused"] = agg["Менеджер"].map(refused_by_mgr).fillna(0).astype(int)
            agg["leads"] = agg["Менеджер"].map(leads_by_mgr).fillna(0).astype(int)
            agg["refuse_pct"] = (agg["refused"] / agg["orders"].replace(0, 1) * 100).round(1)
            agg["avg_check"] = (agg["revenue"] / agg["orders"].replace(0, 1)).round(0)
            agg["conv"] = (agg["orders"] / (agg["orders"] + agg["leads"]).replace(0, 1) * 100).round(1)
            result["managers"] = [
                {"name": r["Менеджер"], "orders": int(r["orders"]),
                 "revenue": round(r["revenue"], 2),
                 "refused": int(r["refused"]), "refuse_pct": float(r["refuse_pct"]),
                 "leads": int(r["leads"]), "avg_check": float(r["avg_check"]),
                 "conv": float(r["conv"])}
                for _, r in agg.sort_values("revenue", ascending=False).iterrows()
            ]

        # ── Менеджери на магазині ──
        if "Менеджер на магазині" in month_df.columns:
            shop_df = valid_uniq_m[valid_uniq_m["Менеджер на магазині"].notna()]
            if not shop_df.empty:
                agg = shop_df.groupby("Менеджер на магазині").agg(
                    orders=("Сума", "count"),
                    revenue=("Сума", lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                agg["avg_check"] = (agg["revenue"] / agg["orders"].replace(0, 1)).round(0)
                result["managers_shop"] = [
                    {"name": r["Менеджер на магазині"], "orders": int(r["orders"]),
                     "revenue": round(r["revenue"], 2), "avg_check": float(r["avg_check"])}
                    for _, r in agg.sort_values("revenue", ascending=False).iterrows()
                ]

        # ── Чатери ──
        if "Відповідальний чатер" in month_df.columns:
            chat_df = valid_uniq_m[valid_uniq_m["Відповідальний чатер"].notna()]
            if not chat_df.empty:
                agg = chat_df.groupby("Відповідальний чатер").agg(
                    orders=("Сума", "count"),
                    revenue=("Сума", lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                result["chatters"] = [
                    {"name": r["Відповідальний чатер"], "orders": int(r["orders"]),
                     "revenue": round(r["revenue"], 2)}
                    for _, r in agg.sort_values("revenue", ascending=False).iterrows()
                ]

        # ── Сайти ──
        if "Сайт" in month_df.columns:
            sites_df = valid_uniq_m[valid_uniq_m["Сайт"].notna()]
            if not sites_df.empty:
                agg = sites_df.groupby("Сайт").agg(
                    orders=("Сума", "count"),
                    revenue=("Сума", lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                agg["avg_check"] = (agg["revenue"] / agg["orders"].replace(0, 1)).round(0)
                result["sites"] = {
                    r["Сайт"]: {"orders": int(r["orders"]),
                                "revenue": round(r["revenue"], 2),
                                "avg_check": float(r["avg_check"])}
                    for _, r in agg.sort_values("revenue", ascending=False).iterrows()
                }

        # ── Категорії звернення ──
        if "Категорія звернення" in month_df.columns:
            cat = month_uniq[month_uniq["Категорія звернення"].notna()]["Категорія звернення"].value_counts().head(15).to_dict()
            result["categories"] = {str(k): int(v) for k, v in cat.items()}

        # ── Тип звернення ──
        if "Тип звернення" in month_df.columns:
            rt = month_uniq[month_uniq["Тип звернення"].notna()]["Тип звернення"].value_counts().head(10).to_dict()
            result["request_types"] = {str(k): int(v) for k, v in rt.items()}

        # ── Спосіб оплати ──
        if "Спосіб оплати" in month_df.columns:
            pm = valid_uniq_m[valid_uniq_m["Спосіб оплати"].notna()]["Спосіб оплати"].value_counts().head(10).to_dict()
            result["payment_methods"] = {str(k): int(v) for k, v in pm.items()}

        # ── Тип доставки ──
        if "Тип доставки" in month_df.columns:
            dt_ = valid_uniq_m[valid_uniq_m["Тип доставки"].notna()]["Тип доставки"].value_counts().to_dict()
            result["delivery_types"] = {str(k): int(v) for k, v in dt_.items()}

        # ── Перевізник ──
        if "Перевізник" in month_df.columns:
            cr = valid_uniq_m[valid_uniq_m["Перевізник"].notna()]["Перевізник"].value_counts().head(10).to_dict()
            result["carriers"] = {str(k): int(v) for k, v in cr.items()}

        # ── Склад ──
        if "Склад" in month_df.columns:
            wh = valid_uniq_m[valid_uniq_m["Склад"].notna()]["Склад"].value_counts().to_dict()
            result["warehouses"] = {str(k): int(v) for k, v in wh.items()}

        # ── Топ товарів (по позиціях, не дедуплікуємо — кожен товар це окрема одиниця) ──
        # Тут НЕ робимо дедуплікацію, бо назви товарів унікальні і кожен товар це окрема позиція.
        # АЛЕ використовуємо "Сума [Товари/Послуги]" — там реальна сума по позиції, не дублікат.
        if "Назва [Товари/Послуги]" in month_df.columns:
            prod_col = "Назва [Товари/Послуги]"
            sum_col  = "Сума [Товари/Послуги]" if "Сума [Товари/Послуги]" in month_df.columns else "Сума"
            qty_col  = "К-ть [Товари/Послуги]" if "К-ть [Товари/Послуги]" in month_df.columns else None
            prod_df = month_df[month_df[prod_col].notna() & (month_df["_категорія"] != "spam")].copy()
            prod_df = prod_df[~prod_df[prod_col].str.lower().str.contains("доставка|нова пошта|укрпошт|самовивіз|сборка|занос", na=False)]
            if not prod_df.empty:
                grp = prod_df.groupby(prod_col).agg(
                    count=(prod_col, "count"),
                    revenue=(sum_col, lambda x: float(x.fillna(0).sum())),
                ).reset_index()
                if qty_col and qty_col in prod_df.columns:
                    qty_grp = prod_df.groupby(prod_col)[qty_col].sum().reset_index()
                    grp = grp.merge(qty_grp, on=prod_col, how="left")
                result["products"] = [
                    {"name": r[prod_col], "count": int(r["count"]),
                     "revenue": round(r["revenue"], 2),
                     "qty": int(r.get(qty_col, r["count"])) if qty_col else int(r["count"])}
                    for _, r in grp.sort_values("revenue", ascending=False).head(50).iterrows()
                ]

        # ── Причини відмов / заперечення / обробки (дедупльовані) ──
        if "Причина відмови ?" in month_df.columns:
            rr = month_uniq[month_uniq["Причина відмови ?"].notna()]["Причина відмови ?"].value_counts().head(15).to_dict()
            result["refuse_reasons"] = {str(k): int(v) for k, v in rr.items()}
        if "Проблемне заперечення" in month_df.columns:
            lo = month_uniq[month_uniq["Проблемне заперечення"].notna()]["Проблемне заперечення"].value_counts().head(10).to_dict()
            result["lead_objections"] = {str(k): int(v) for k, v in lo.items()}
        if "Причина обробки" in month_df.columns:
            pr = month_uniq[month_uniq["Причина обробки"].notna()]["Причина обробки"].value_counts().head(10).to_dict()
            result["process_reasons"] = {str(k): int(v) for k, v in pr.items()}

        # ── Daily trend по днях у межах місяця (дедупльоване) ──
        valid_for_trend = valid_uniq_m  # дедупльовані без спаму
        daily = valid_for_trend.groupby("_день").agg(
            orders=("Сума", "count"),
            revenue=("Сума", lambda x: float(x.fillna(0).sum())),
        ).reset_index()
        daily_leads = month_uniq[month_uniq["_категорія"] == "lead"].groupby("_день").size().to_dict()
        daily_refused = month_uniq[month_uniq["_категорія"] == "refused"].groupby("_день").size().to_dict()
        result["daily_trend"] = [
            {"date": r["_день"],
             "orders": int(r["orders"]),
             "revenue": round(float(r["revenue"]), 2),
             "leads": int(daily_leads.get(r["_день"], 0)),
             "refused": int(daily_refused.get(r["_день"], 0))}
            for _, r in daily.iterrows()
        ]

    except Exception as e:
        result["error"] = str(e)
        print(f"  ⚠️  Місячний CRM помилка: {e}")
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

    # ── 1С SH вимкнено за вимогою керівництва ────────────────
    # SH-збір прибрано з логіки. Залишаємо порожній dict для зворотної сумісності
    # зі старими JSON у history/ (на випадок міграції чи відкату).
    data["sh"] = {
        "label": "SH",
        "ORDERS": {"day": {"total": 0, "by_podr": {}}, "day_refused": {"total": 0, "by_podr": {}},
                   "month": {"total": 0, "count": 0}, "month_refused": {"total": 0, "count": 0}},
        "ORDERSWD": {"day": {"total": 0, "by_podr": {}}, "day_refused": {"total": 0, "by_podr": {}},
                     "month": {"total": 0, "count": 0}, "month_refused": {"total": 0, "count": 0}},
        "SALES": {"day": {"total": 0, "by_podr": {}}, "month": {"total": 0, "count": 0}},
        "_disabled": True,
    }

    # ── SalesDrive CRM ────────────────────────────────────────
    print("\n🎯 Завантаження SalesDrive CRM (Excel)...")
    data["crm"] = fetch_salesdrive(day_iso)
    crm = data["crm"]
    if crm["error"] and not crm["orders"]:
        print(f"   ⚠️  Помилка CRM: {crm['error']}")
    else:
        o = crm["orders"]
        m = crm.get("month_total", {})
        print(f"   ✅ Файл:        {crm.get('source_file', '—')}")
        print(f"   ✅ Замовлень:   {o.get('total', 0)} (всього {o.get('all_rows', 0)} рядків)")
        print(f"   ✅ Лідів:       {crm['leads'].get('new_leads', 0)}")
        print(f"   ✅ Виручка:     {o.get('revenue', 0):,.0f} ₴ | сер. чек: {o.get('avg_check', 0):,.0f}")
        print(f"   ✅ Відмови:     {o.get('refused', 0)} ({o.get('refuse_pct', 0)}%)")
        print(f"   ✅ Місяць:      {m.get('orders', 0)} зам. | {m.get('revenue', 0):,.0f} ₴")
        print(f"   ✅ Менеджерів:  {len(crm['managers'])}")
        print(f"   ✅ Сайтів:      {len(crm['sites'])}")
        print(f"   ✅ Товарів:     {len(crm['products'])}")
        print(f"   ✅ Категорій:   {len(crm['categories'])} | Типів звернень: {len(crm['request_types'])}")
        print(f"   ✅ Тренд 30 дн: {len(crm['trend_30d'])} точок")

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

    # ── МІСЯЧНА АГРЕГАЦІЯ ─────────────────────────────────────
    target_month = day_iso[:7]
    print(f"\n📅 Збір місячних даних за {target_month}...")
    data["month"] = {
        "target_month": target_month,
        "crm": aggregate_month_crm(target_month),
    }

    # FALLBACK: якщо в Excel немає даних за поточний місяць —
    # використовуємо останній доступний (Excel вигрузка може бути застарілою)
    if not data["month"]["crm"].get("orders"):
        print(f"   ⚠️  Excel не має даних за {target_month}, шукаю останній доступний місяць...")
        try:
            import pandas as pd
            files = sorted(CRM_DATA_DIR.glob("*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                df_check = pd.read_excel(files[0])
                df_check["_дата"] = pd.to_datetime(df_check["Дата"], errors="coerce")
                df_check["_місяць"] = df_check["_дата"].dt.strftime("%Y-%m")
                available_months = sorted(df_check["_місяць"].dropna().unique(), reverse=True)
                if available_months:
                    fallback_month = available_months[0]
                    print(f"   📂 Знайдено: {fallback_month} (використовую як поточний)")
                    target_month = fallback_month
                    data["month"]["target_month"] = target_month
                    data["month"]["crm"] = aggregate_month_crm(target_month)
                    data["month"]["fallback_used"] = True
        except Exception as e:
            print(f"   ⚠️  Помилка fallback: {e}")

    if data["month"]["crm"].get("orders"):
        mo = data["month"]["crm"]["orders"]
        print(f"   ✅ Поточний міс ({target_month}): {mo.get('total', 0)} зам. | {mo.get('revenue', 0):,.0f} ₴ | сер. чек {mo.get('avg_check', 0):,.0f}")
        print(f"   ✅ Менеджерів:  {len(data['month']['crm']['managers'])}")
        print(f"   ✅ Товарів:     {len(data['month']['crm']['products'])}")

    # Попередній місяць (для порівняння) — від target_month
    tm_year, tm_mon = int(target_month[:4]), int(target_month[5:7])
    if tm_mon == 1:
        prev_m_start_dt = datetime(tm_year - 1, 12, 1)
    else:
        prev_m_start_dt = datetime(tm_year, tm_mon - 1, 1)
    prev_month = prev_m_start_dt.strftime("%Y-%m")

    print(f"\n📅 CRM за попередній місяць ({prev_month})...")
    data["month"]["prev_crm"] = aggregate_month_crm(prev_month)
    if data["month"]["prev_crm"].get("orders"):
        po = data["month"]["prev_crm"]["orders"]
        print(f"   ✅ Прев. місяць: {po.get('total', 0)} зам. | {po.get('revenue', 0):,.0f} ₴")
    else:
        print(f"   ⚠️  Немає даних за {prev_month}")

    # ── Збереження ────────────────────────────────────────────
    out_path = HISTORY_DIR / f"{day_iso}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Збережено: {out_path}")
    print(f"{'='*50}\n")
    return data

if __name__ == "__main__":
    main()
