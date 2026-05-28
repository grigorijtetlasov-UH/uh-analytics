"""
sales_kpi.py — розрахунок KPI відділу продажів для UH Analytics dashboard.

KPI відповідають Контексту бізнесу United Home v1.0:
  1. Конверсія (ціль 85%) — orders / requests (з і без спаму)
  2. Крос-сейл (ціль 35%) — % замовлень з допродажами (окрім гарантії/чохла)
  3. Гарантії + Чохли (ціль 35%) — % замовлень де є гарантія АБО чохол
  4. Відмови (ціль ≤5%) — від замовлень і від заявок без спаму

Розраховується за день і за поточний місяць.

ВАЖЛИВО: Цей модуль читає Excel-файли НАПРЯМУ з папок data/crm/daily/ і
data/crm/months/, оскільки в основному потоці fetch_data.py відбувається
дедуп по (Дата+Контакт+Сума+Статус) який вилучає всі товарні позиції окрім
однієї. А для KPI крос-сейлу і гарантій нам потрібні ВСІ позиції замовлення.
"""

import re
from pathlib import Path
from typing import Optional

import pandas as pd


# ── Шляхи (як у fetch_data.py) ─────────────────────────────────────
CRM_DAILY_DIR  = Path("data/crm/daily")
CRM_MONTHS_DIR = Path("data/crm/months")
CRM_FLAT_DIR   = Path("data/crm")


# ── Статуси (синхронізовано з fetch_data.py) ───────────────────────
ORDER_STATUSES = {
    "виправити дані", "створена ттн", "їде до клієнта", "прибув у відділення",
    "переадресація", "в виробництві", "в черзі на відправлення",
    "контроль оператора", "контроль оплати", "відправлено", "отримано",
    "повернення",
}
REFUSED_STATUSES = {
    "відмова (відправлено)", "відмова (не відправлено)", "відмова",
}
LOST_LEAD_STATUSES = {
    # Втрачені ліди (заявки які не дійшли до замовлення)
    "лід (не купив)",
}
LEAD_STATUSES = {
    # Активні ліди (в обробці, ще можуть стати замовленнями)
    "новий", "недодзвон", "автовідповідач", "повторне звернення",
    "потрібне уточнення/перезвон", "питання по замовленню",
    "в обробці", "відвідає шоу-рум",
}
SPAM_STATUSES = {
    "спам на согласовании", "рекламный спам", "спам", "видалений", "дубль",
}


def _categorize_status(s) -> str:
    sl = str(s).strip().lower()
    if sl in ORDER_STATUSES:        return "order"
    if sl in REFUSED_STATUSES:      return "refused"
    if sl in LOST_LEAD_STATUSES:    return "lost"        # ← новий: втрачений лід
    if sl in LEAD_STATUSES:         return "lead"
    if sl in SPAM_STATUSES:         return "spam"
    if "відмов" in sl: return "refused"
    if "спам" in sl:   return "spam"
    if "не купив" in sl: return "lost"
    if "лід" in sl:    return "lead"
    return "other"


# ── Класифікація товарних позицій ──────────────────────────────────
_RE_GUARANTEE = re.compile(r"гаранті", re.IGNORECASE)
_RE_SERVICE   = re.compile(r"^доставк|^занос на поверх", re.IGNORECASE)
_RE_COVER_UPSELL = re.compile(
    r"^покращенн?ий чохол|^змінний чохол|^чохол ",
    re.IGNORECASE
)


def classify_item(name) -> str:
    """Класифікує позицію за назвою: 'service' | 'guarantee' | 'cover' | 'main'."""
    if pd.isna(name):
        return "main"
    s = str(name).strip()
    if _RE_SERVICE.search(s):
        return "service"
    if _RE_GUARANTEE.search(s):
        return "guarantee"
    if _RE_COVER_UPSELL.search(s):
        return "cover"
    return "main"


# ── Читання сирих Excel (без агресивного дедупу) ───────────────────
def _load_raw_excel(target_month: str) -> Optional[pd.DataFrame]:
    """
    Читає Excel-файли CRM за вказаний місяць ТІЛЬКИ з months/.
    Залишає всі товарні позиції цілими — дедупимо тільки по (Номер 1С + Назва товару)
    щоб прибрати дублі історії змін статусу.

    Чому тільки months/: daily-файли SalesDrive містять заявки за один день із
    "застиглими" статусами на момент вивантаження. Актуальні "дозрілі" статуси є
    тільки в свіжому місячному знімку (ручному *_full.xlsx або API *_api.xlsx).

    ПРІОРИТЕТ: якщо для місяця є *_api.xlsx (свіжі дані з SalesDrive API) — беремо
    ТІЛЬКИ його, ігноруючи *_full.xlsx (ручна вивантажка), щоб не подвоювати дані.
    """
    frames = []

    if CRM_MONTHS_DIR.exists():
        month_files = sorted(CRM_MONTHS_DIR.glob("*.xlsx"))
        target_files = [f for f in month_files if target_month in f.name]

        api_files = [f for f in target_files if "_api" in f.name.lower()]
        files_to_load = api_files if api_files else target_files

        for f in files_to_load:
            try:
                df = pd.read_excel(f)
                if "Дата" in df.columns:
                    frames.append(df)
            except Exception:
                continue

    if not frames:
        return None

    df = pd.concat(frames, ignore_index=True, sort=False)

    # Розумний дедуп, щоб не губити ліди:
    #  - Рядки З Номер 1С: дедуп по (Номер 1С + Назва + Сума) — прибирає дублі
    #    історії змін статусу, але залишає всі товарні позиції замовлення.
    #  - Рядки БЕЗ Номер 1С (переважно ліди "Лід (не купив)"): дедуп по
    #    "ID замовлення" (унікальний на заявку). Інакше всі ліди з порожньою
    #    назвою/сумою схлопуються в один рядок і конверсія завищується.
    if "Номер 1С" in df.columns and "Назва [Товари/Послуги]" in df.columns:
        with_num = df[df["Номер 1С"].notna()].copy()
        no_num = df[df["Номер 1С"].isna()].copy()

        with_num = with_num.drop_duplicates(
            subset=["Номер 1С", "Назва [Товари/Послуги]", "Сума [Товари/Послуги]"],
            keep="last"
        )

        # Для рядків без Номер 1С — дедуп по ID замовлення, якщо колонка є.
        if "ID замовлення" in no_num.columns:
            no_num = no_num.drop_duplicates(subset=["ID замовлення"], keep="last")
        else:
            # Fallback (старі ручні xlsx без ID замовлення): дедуп по даті+статусу
            no_num = no_num.drop_duplicates(
                subset=["Дата", "Статус", "Назва [Товари/Послуги]", "Сума [Товари/Послуги]"],
                keep="last"
            )

        df = pd.concat([with_num, no_num], ignore_index=True, sort=False)

    df["_дата"] = pd.to_datetime(df["Дата"], errors="coerce")
    df["_день"] = df["_дата"].dt.strftime("%Y-%m-%d")
    df["_місяць"] = df["_дата"].dt.strftime("%Y-%m")
    df["_категорія"] = df["Статус"].fillna("").apply(_categorize_status)

    return df


# ── Розрахунок KPI ─────────────────────────────────────────────────
def _empty_kpi() -> dict:
    return {
        "conversion": {"value": 0.0, "with_spam": 0.0, "no_spam": 0.0, "target": 85,
                       "orders": 0, "leads": 0, "all": 0, "no_spam_count": 0},
        "cross_sell": {"value": 0.0, "orders": 0, "of": 0, "target": 35},
        "guarantee_cover": {"value": 0.0, "orders": 0, "of": 0, "target": 35},
        "refuse": {"of_orders": 0.0, "of_requests_no_spam": 0.0, "target": 5,
                   "refused": 0, "active": 0},
    }


def _kpi_for_period(df: pd.DataFrame) -> dict:
    """Розраховує 4 KPI за логікою еталонного дашборду (uh_sellers_dashboard).

    Базова модель воронки:
      Заявка → Лід (активний) → ПРОДАЖ (order або refused) АБО ЛІД-НЕ-КУПИВ (lost)

    Формули:
      - sold  = orders + refused       (все що дійшло до замовлення)
      - lost  = "Лід (не купив)"       (втрачені перед оформленням)
      - dec   = sold + lost            (знаменник конверсії)
      - КОНВЕРСІЯ = sold / dec * 100
      - ВІДМОВИ   = refused / sold * 100

    Підрахунок:
      - Замовлення (orders + refused) — мають Номер 1С, дедуп по ньому
      - Втрачені ліди (lost) — мають Статус "Лід (не купив)", часто БЕЗ Номера 1С,
        тому рахуємо КОЖЕН РЯДОК як окрему заявку
    """
    if df is None or df.empty:
        return _empty_kpi()

    if "Номер 1С" not in df.columns:
        return _empty_kpi()

    # ── ЗАМОВЛЕННЯ та ВІДМОВИ (потрібен Номер 1С — дивимось позиції товарів) ──
    orders_df = df.dropna(subset=["Номер 1С"]).copy()
    if not orders_df.empty:
        order_cats_num = orders_df.groupby("Номер 1С")["_категорія"].first()
        n_orders = int((order_cats_num == "order").sum())
        n_refused = int((order_cats_num == "refused").sum())
    else:
        order_cats_num = pd.Series(dtype=str)
        n_orders = 0
        n_refused = 0

    # ── ВТРАЧЕНІ ЛІДИ "Лід (не купив)" ──
    # Беремо ВСІ рядки з категорією "lost" (з номером 1С і без)
    n_lost_with_num = int((order_cats_num == "lost").sum())
    no_num_df = df[df["Номер 1С"].isna()]
    n_lost_no_num = int((no_num_df["_категорія"] == "lost").sum())
    n_lost = n_lost_with_num + n_lost_no_num

    # ── ВТРАЧЕНІ ВІДМОВИ БЕЗ НОМЕРА (рідко але можливо) ──
    n_refused_no_num = int((no_num_df["_категорія"] == "refused").sum())
    n_refused += n_refused_no_num

    # ── АКТИВНІ ЛІДИ і СПАМ (для довідки) ──
    n_leads_active_with_num = int((order_cats_num == "lead").sum())
    n_leads_active_no_num = int((no_num_df["_категорія"] == "lead").sum())
    n_leads_active = n_leads_active_with_num + n_leads_active_no_num
    n_spam_with_num = int((order_cats_num == "spam").sum())
    n_spam_no_num = int((no_num_df["_категорія"] == "spam").sum())
    n_spam = n_spam_with_num + n_spam_no_num

    # ── 1. КОНВЕРСІЯ (за еталоном) ──
    # sold = orders + refused (все що дійшло до замовлення)
    # dec  = sold + lost
    # КОНВЕРСІЯ = sold / dec * 100
    n_sold = n_orders + n_refused
    conv_denom = n_sold + n_lost
    conv_value = (n_sold / conv_denom * 100) if conv_denom else 0.0

    # Загальна довідкова конверсія (з усіма заявками)
    n_all = n_orders + n_refused + n_lost + n_leads_active + n_spam
    conv_with_spam = (n_orders / n_all * 100) if n_all else 0.0

    # ── 2 + 3. Крос-сейл і гарантії+чохли (тільки на замовленнях зі статусом order) ──
    order_ids = order_cats_num[order_cats_num == "order"].index
    items = orders_df[orders_df["Номер 1С"].isin(order_ids)].copy() if not orders_df.empty else pd.DataFrame()

    cross_sell_orders = 0
    gc_orders = 0
    if not items.empty and "Назва [Товари/Послуги]" in items.columns:
        items["_kind"] = items["Назва [Товари/Послуги]"].apply(classify_item)
        items = items[items["_kind"] != "service"]

        # Крос-сейл: 2+ різних main-позиції
        main_counts = items[items["_kind"] == "main"].groupby("Номер 1С").size()
        cross_sell_orders = int((main_counts >= 2).sum())

        # Гарантії+чохли: замовлення з хоча б однією такою позицією
        gc_order_ids = items[items["_kind"].isin(["guarantee", "cover"])]["Номер 1С"].unique()
        gc_orders = int(len(gc_order_ids))

    cross_sell_pct = (cross_sell_orders / n_orders * 100) if n_orders else 0.0
    gc_pct = (gc_orders / n_orders * 100) if n_orders else 0.0

    # ── 4. ВІДМОВИ (за еталоном) ──
    # ВІДМОВИ = refused / sold * 100  (тільки серед проданих)
    refuse_of_orders = (n_refused / n_sold * 100) if n_sold else 0.0
    refuse_of_requests = (n_refused / (n_all - n_spam) * 100) if (n_all - n_spam) else 0.0

    return {
        "conversion": {
            "value":     round(conv_value, 1),       # ← головне (sold/(sold+lost))
            "with_spam": round(conv_with_spam, 1),   # для довідки
            "no_spam":   round(conv_value, 1),       # alias
            "target":    85,
            "orders":    n_orders,
            "sold":      n_sold,            # orders + refused
            "lost":      n_lost,            # "Лід (не купив)"
            "leads":     n_leads_active,    # активні ліди (для довідки)
            "all":       n_all,
            "no_spam_count": n_all - n_spam,
        },
        "cross_sell": {
            "value":  round(cross_sell_pct, 1),
            "orders": cross_sell_orders,
            "of":     n_orders,
            "target": 35,
        },
        "guarantee_cover": {
            "value":  round(gc_pct, 1),
            "orders": gc_orders,
            "of":     n_orders,
            "target": 35,
        },
        "refuse": {
            "of_orders":           round(refuse_of_orders, 1),  # refused/sold (як в еталоні)
            "of_requests_no_spam": round(refuse_of_requests, 1),
            "target":              5,
            "refused":             n_refused,
            "active":              n_sold,  # знаменник = sold (orders+refused)
        },
    }


# ── Публічна функція ───────────────────────────────────────────────

# Мапа проектів: CRM "Сайт" → 1С "Подразделение"
PROJECTS = {
    "matrasroll": {
        "label":     "Matrasroll",
        "crm_site":  "matrasroll.com.ua",
        "uh_podr":   "Matrasroll",
    },
    "amebli": {
        "label":     "Amebli",
        "crm_site":  "amebli.com.ua",
        "uh_podr":   "A-mebli",
    },
}


def _apply_1c_refuse(period_block: dict, refused_data: dict, total_data: dict) -> None:
    """Замінює період_block['refuse'] на цифри з 1С (НЕ з CRM)."""
    n_refused_1c = int(refused_data.get("count", 0) or 0)
    n_orders_1c = int(total_data.get("count", 0) or 0)
    n_sold_1c = n_orders_1c + n_refused_1c

    refuse_pct = round(n_refused_1c / n_sold_1c * 100, 1) if n_sold_1c > 0 else 0.0

    period_block["refuse"] = {
        "of_orders":           refuse_pct,
        "of_requests_no_spam": refuse_pct,
        "target":              5,
        "refused":             n_refused_1c,
        "active":              n_sold_1c,
        "source":              "1C",
        "sum_refused":         round(float(refused_data.get("total", 0) or 0), 0),
        "sum_orders":          round(float(total_data.get("total", 0) or 0), 0),
    }


def _by_podr_count_and_total(by_podr: dict) -> tuple:
    """Допоміжна: у block.by_podr може бути {назва: сума} або {назва: {total, count}}.
    Повертає (count, total) для одного підрозділу."""
    if isinstance(by_podr, dict):
        # формат {назва: {total, count}}
        if "total" in by_podr or "count" in by_podr:
            return int(by_podr.get("count", 0) or 0), float(by_podr.get("total", 0) or 0)
        # формат {назва: сума}
        return 0, float(by_podr or 0)
    if isinstance(by_podr, (int, float)):
        return 0, float(by_podr)
    return 0, 0.0


def _project_1c_data(uh_1c_data: dict, podr_name: str) -> dict:
    """Витягує з uh_1c_data ORDERS блок саме для одного підрозділу.
    Повертає структуру така ж як ORDERS: {day, day_refused, month, month_refused}."""
    if not uh_1c_data or not isinstance(uh_1c_data, dict):
        return {}
    ord_block = uh_1c_data.get("ORDERS", {}) or {}
    result = {}
    for period_key in ("day", "day_refused", "month", "month_refused"):
        block = ord_block.get(period_key, {}) or {}
        by_podr = block.get("by_podr", {}) or {}
        by_podr_count = block.get("by_podr_count", {}) or {}

        # Знайти підрозділ (case-insensitive)
        match_total = 0.0
        match_count = 0
        for name in by_podr.keys():
            if str(name).strip().lower() == podr_name.strip().lower():
                match_total = float(by_podr.get(name, 0) or 0)
                match_count = int(by_podr_count.get(name, 0) or 0)
                break

        result[period_key] = {"count": match_count, "total": match_total}
    return {"ORDERS": result}


def _filter_by_crm_site(df, site_name: str):
    """Фільтрує DataFrame по полю Сайт (case-insensitive, точне співпадіння)."""
    if df is None or df.empty or "Сайт" not in df.columns:
        return df.iloc[0:0] if df is not None else df
    return df[df["Сайт"].astype(str).str.strip().str.lower() == site_name.strip().lower()]


def compute_sales_kpi(date_str: str, uh_1c_data: dict = None) -> dict:
    """
    Головна функція. Викликається з fetch_data.py:
        result["sales_kpi"] = compute_sales_kpi(date_str, uh_1c_data=...)

    Повертає:
        {
            "day":   {... 4 метрики, загалом ...},
            "month": {... 4 метрики, загалом ...},
            "by_project": {
                "matrasroll": {"day": {...}, "month": {...}, "label": "Matrasroll"},
                "amebli":     {"day": {...}, "month": {...}, "label": "Amebli"}
            }
        }
    """
    target_month = date_str[:7]

    df = _load_raw_excel(target_month)
    if df is None:
        empty_kpi = _empty_kpi()
        return {
            "day": empty_kpi,
            "month": empty_kpi,
            "by_project": {
                key: {"day": empty_kpi, "month": empty_kpi, "label": p["label"]}
                for key, p in PROJECTS.items()
            }
        }

    day_df = df[df["_день"] == date_str]
    month_df = df[df["_місяць"] == target_month]

    # ── 1. ЗАГАЛЬНІ KPI ──
    result = {
        "day":   _kpi_for_period(day_df),
        "month": _kpi_for_period(month_df),
    }

    # Заміняємо refuse на 1С (якщо є дані 1С)
    if uh_1c_data and isinstance(uh_1c_data, dict):
        ord_block = uh_1c_data.get("ORDERS", {}) or {}
        _apply_1c_refuse(result["day"],
                         ord_block.get("day_refused", {}) or {},
                         ord_block.get("day", {}) or {})
        _apply_1c_refuse(result["month"],
                         ord_block.get("month_refused", {}) or {},
                         ord_block.get("month", {}) or {})

    # ── 2. KPI ПО ПРОЕКТАХ ──
    result["by_project"] = {}
    for key, p in PROJECTS.items():
        # Фільтруємо CRM по сайту
        day_p = _filter_by_crm_site(day_df, p["crm_site"])
        month_p = _filter_by_crm_site(month_df, p["crm_site"])

        project_kpi = {
            "label": p["label"],
            "day":   _kpi_for_period(day_p),
            "month": _kpi_for_period(month_p),
        }

        # Заміняємо refuse на 1С (по підрозділу)
        project_1c = _project_1c_data(uh_1c_data, p["uh_podr"])
        if project_1c:
            p_ord = project_1c.get("ORDERS", {}) or {}
            _apply_1c_refuse(project_kpi["day"],
                             p_ord.get("day_refused", {}) or {},
                             p_ord.get("day", {}) or {})
            _apply_1c_refuse(project_kpi["month"],
                             p_ord.get("month_refused", {}) or {},
                             p_ord.get("month", {}) or {})

        result["by_project"][key] = project_kpi

    return result
