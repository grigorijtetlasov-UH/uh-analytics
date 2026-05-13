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
    "лід (не купив)",  # ← в наш процес: лід що відмовився купувати = відмова
}
LEAD_STATUSES = {
    "новий", "недодзвон", "автовідповідач", "повторне звернення",
    "потрібне уточнення/перезвон", "питання по замовленню",
    "в обробці", "відвідає шоу-рум",
}
SPAM_STATUSES = {
    "спам на согласовании", "рекламный спам", "спам", "видалений", "дубль",
}


def _categorize_status(s) -> str:
    sl = str(s).strip().lower()
    if sl in ORDER_STATUSES:   return "order"
    if sl in REFUSED_STATUSES: return "refused"
    if sl in LEAD_STATUSES:    return "lead"
    if sl in SPAM_STATUSES:    return "spam"
    if "відмов" in sl: return "refused"
    if "спам" in sl:   return "spam"
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
    Читає всі Excel-файли з daily/ БЕЗ дедупу по заявках.
    Залишає всі товарні позиції цілими — дедупимо тільки по (Номер 1С + Назва товару)
    щоб прибрати дублі історії змін статусу.
    """
    frames = []

    for d in (CRM_DAILY_DIR, CRM_FLAT_DIR):
        files = sorted(d.glob("*.xlsx"), key=lambda f: f.stat().st_mtime)
        for f in files:
            try:
                df = pd.read_excel(f)
                if "Дата" in df.columns:
                    frames.append(df)
            except Exception:
                continue
        if frames:
            break

    if CRM_MONTHS_DIR.exists():
        month_files = sorted(CRM_MONTHS_DIR.glob("*.xlsx"))
        for f in month_files:
            if target_month in f.name:
                try:
                    df = pd.read_excel(f)
                    if "Дата" in df.columns:
                        frames.append(df)
                except Exception:
                    continue

    if not frames:
        return None

    df = pd.concat(frames, ignore_index=True, sort=False)

    # Дедуп: тільки дублі ІСТОРІЇ (один Номер 1С + одна Назва товару).
    # Залишає всі окремі позиції в межах одного замовлення.
    if "Номер 1С" in df.columns and "Назва [Товари/Послуги]" in df.columns:
        df = df.drop_duplicates(
            subset=["Номер 1С", "Назва [Товари/Послуги]", "Сума [Товари/Послуги]"],
            keep="last"
        )

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
    """Розраховує 4 KPI для df з усіма позиціями (НЕ дедуплений по замовленнях)."""
    if df is None or df.empty:
        return _empty_kpi()

    if "Номер 1С" not in df.columns:
        return _empty_kpi()

    # Заявки без NaN-номера. Категорія однакова для всіх позицій 1 замовлення —
    # тому беремо першу.
    orders_df = df.dropna(subset=["Номер 1С"]).copy()
    if orders_df.empty:
        return _empty_kpi()

    order_cats = orders_df.groupby("Номер 1С")["_категорія"].first()

    n_all = len(order_cats)
    n_orders = int((order_cats == "order").sum())
    n_refused = int((order_cats == "refused").sum())
    n_leads = int((order_cats == "lead").sum())
    n_spam = int((order_cats == "spam").sum())
    n_no_spam = n_all - n_spam

    # ── 1. КОНВЕРСІЯ (за еталоном) ──
    # Формула: замовлення / (замовлення + ліди). Спам та pending виключені.
    # "with_spam" зберігаємо як sanity-check (orders / all_requests).
    conv_denom = n_orders + n_leads
    conv_value = (n_orders / conv_denom * 100) if conv_denom else 0.0
    conv_with_spam = (n_orders / n_all * 100) if n_all else 0.0  # для довідки

    # ── 2 + 3. Крос-сейл і гарантії+чохли (тільки на замовленнях зі статусом order) ──
    order_ids = order_cats[order_cats == "order"].index
    items = orders_df[orders_df["Номер 1С"].isin(order_ids)].copy()

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
    # Формула: Відмова(відпр) + Відмова(не відпр) як % від замовлень
    # Знаменник = тільки замовлення (order), без refused.
    refuse_of_orders = (n_refused / n_orders * 100) if n_orders else 0.0
    refuse_of_requests = (n_refused / n_no_spam * 100) if n_no_spam else 0.0

    return {
        "conversion": {
            "value":     round(conv_value, 1),       # ← головне значення (за еталоном)
            "with_spam": round(conv_with_spam, 1),   # для довідки
            "no_spam":   round(conv_value, 1),       # alias щоб дашборд продовжував працювати
            "target":    85,
            "orders":    n_orders,
            "leads":     n_leads,
            "all":       n_all,
            "no_spam_count": n_no_spam,
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
            "of_orders":           round(refuse_of_orders, 1),
            "of_requests_no_spam": round(refuse_of_requests, 1),
            "target":              5,
            "refused":             n_refused,
            "active":              n_orders,  # знаменник = замовлення (як в еталоні)
        },
    }


# ── Публічна функція ───────────────────────────────────────────────
def compute_sales_kpi(date_str: str) -> dict:
    """
    Головна функція. Викликається з fetch_data.py:
        result["sales_kpi"] = compute_sales_kpi(date_str)

    Повертає:
        {"day": {... 4 метрики ...}, "month": {... 4 метрики ...}}
    """
    target_month = date_str[:7]

    df = _load_raw_excel(target_month)
    if df is None:
        return {"day": _empty_kpi(), "month": _empty_kpi()}

    day_df = df[df["_день"] == date_str]
    month_df = df[df["_місяць"] == target_month]

    return {
        "day":   _kpi_for_period(day_df),
        "month": _kpi_for_period(month_df),
    }
