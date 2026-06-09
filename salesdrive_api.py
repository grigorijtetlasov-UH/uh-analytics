"""
salesdrive_api.py — автоматичний фетч замовлень із SalesDrive REST API.

Заміняє ручне завантаження xlsx з SalesDrive UI. Тягне всі замовлення за період
сторінками (по 100), розгортає масив products у плоский DataFrame з товарними
позиціями (одна позиція = один рядок), додає колонку "Сайт" з полем sajt
(matrasroll, amebli, sofino, ...) — формат на 100% сумісний з ручною xlsx-
вивантажкою, яку зараз чекає sales_kpi._load_raw_excel().

ЗАСТОСУВАННЯ
------------
CLI (раз на день, перед запуском fetch_data.py):
    python salesdrive_api.py --month 2026-05
    python salesdrive_api.py --month 2026-05 --out data/crm/months/
    python salesdrive_api.py --from 2026-05-01 --to 2026-05-21

Імпорт як бібліотека:
    from salesdrive_api import fetch_orders_to_dataframe
    df = fetch_orders_to_dataframe(month="2026-05")

ВИХІД
-----
Файл XLSX зі стандартним іменем salesdrive_<YYYY-MM>_api.xlsx (або кастомне ім'я
через --out-file), готовий для sales_kpi._load_raw_excel().

ВАЖЛИВО
-------
Ключ читається з .env (SD_API_KEY) або з аргументу --api-key. НЕ хардкодьте в коді.

Створено: 2026-05-21
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

# ─────────────────────────── Конфіг ─────────────────────────────────
DEFAULT_BASE_URL = "https://matrasroll.salesdrive.me"
DEFAULT_PAGE_SIZE = 100  # ліміт SalesDrive API
# SalesDrive ліміти:
#   1 хв       — 10 запитів
#   1 година   — 100 запитів  ← це найжорсткіший на практиці
#   24 години  — 1000 запитів
# 40с між запитами = 90/год — є запас.
DEFAULT_RATE_LIMIT_SLEEP = 40.0
MAX_RETRIES = 5
RETRY_BACKOFF = 4.0
DEFAULT_OUT_DIR = Path("data/crm/months")

# ─────────────────── Словники з API (з документа) ───────────────────
# Витягнуто з документації SalesDrive для matrasroll-акаунту.
# Якщо в API додаються нові статуси/менеджери — оновити тут.

STATUS_ID_TO_NAME = {
    43:  "Новий",
    47:  "Контроль оператора",
    48:  "Відмова (відправлено)",
    49:  "Відмова (не відправлено)",
    50:  "Видалений",
    52:  "Спам Дубль",
    53:  "Недодзвон",
    54:  "Отримано",
    55:  "Відвідає шоу-рум",
    56:  "Повторне звернення",
    57:  "Відправлено",
    58:  "Закінчився термін зберігання",
    59:  "Переадресація",
    60:  "Прибув у відділення",
    61:  "Їде до клієнта",
    62:  "Створена ТТН",
    63:  "Помилка менеджера",
    64:  "Питання по замовленню",
    65:  "Лід ЧАТИ",
    66:  "Контроль оплати",
    67:  "В обробці",
    68:  "Лід (не купив)",
    71:  "В виробництві",
    72:  "В черзі на відправлення",
    73:  "Рекламація",
    74:  "Спам на согласование",
    76:  "Рекламный спам",
    78:  "Створена з телеграму",
    81:  "НЕОБРОБЛЕНІ",
    82:  "Потрібне уточнення/перезвон",
}

SAJT_ID_TO_NAME = {
    869:  "matrasroll.com.ua",
    871:  "amebli.com.ua",
    796:  "DR-TV",
    1045: "sofino",
    1046: "hubstore.com.ua",
    1017: "Епіцентр ЮХ",
    954:  "Епіцентр ЮХ",
    1015: "Епіцентр СХ",
    1049: "Rozetka UnitedHomes",
    1044: "Розетка ЮХ",
    1048: "Розетка СХ",
    1053: "UnitedHome",
    1027: "АЛЛО UnitedHome",
    893:  "Шоу-Рум Якова Гніздовського",
    894:  "Шоу-Рум Дрім Таун",
    1025: "Шоу-Рум Ретровіль",
    1050: "ST Даринок",
    1051: "ST Ретровіль",
    1052: "ST ДрімТаун",
}

USER_ID_TO_NAME = {
    1:   "Адміністратор",
    4:   "Юлія Горбань",
    7:   "Анастасія Любарец",
    8:   "Руслан Сава",
    11:  "Ростислав Куций",
    18:  "Інтегратор Бази",
    29:  "TechSupport",
    30:  "Олександр Коваленко",
    32:  "Timur",
    39:  "Відділ Операторів",
    50:  "Игорь Воловой",
    54:  "Вікторія Кудрицька",
    69:  "MarketPlace Networks",
    74:  "Анна Глотова",
    97:  "Анастасія Калюта",
    102: "Вікторія Шегедин",
    121: "Шоу Рум Дарынок",
    136: "ШоуРум ДрімТаун",
    153: "Тетяна Молянко",
    154: "Олена Вус",
    155: "Катерина Мещерiна",
    157: "Ольга Галишин",
    159: "Денис Лисак",
    160: "Надія Карпенко",
    163: "Руслан Шабалин",
    164: "Александр Шамардин",
    167: "Богдан Малик",
    169: "SolarWeb",
    170: "Дарʼя Маменко",
    176: "Марта Онищук",
    177: "Олександр Радзіховський",
    179: "Антон Гуркін",
    180: "Володимир Шамін",
    181: "Діана Дзюба",
    184: "Григорій Тетляшов",
    185: "Валерія Захожа",
    195: "Анна Романенко",
    198: "СТ ПРОДАКШН",
    199: "Вікторія Кирієнко",
    200: "Яков Маншилін",
    201: "Анна Карпенко",
    202: "Ірина Молянко",
    204: "Шоу-Рум Ретровіль",
    205: "Артур Прізвище",
    206: "Мария Волохата",
    207: "Едуард Бутенко",
}

# Колонки, які чекає sales_kpi._load_raw_excel().
# КРИТИЧНО: імена мають точно збігатися з тими, що зчитує fetch_data.py і sales_kpi.py
# з ручної xlsx-вивантажки SalesDrive. Зокрема:
#   "Сума"           — сума замовлення (НЕ "Сума замовлення"!)
#   "К-ть [Товари/Послуги]"   — кількість (НЕ "Кількість")
#   "Ціна за од. [Товари/Послуги]" — ціна (НЕ "Ціна")
OUTPUT_COLUMNS = [
    "Дата",
    "Номер 1С",
    "Статус",
    "Сайт",
    "Менеджер",
    "ID замовлення",
    "Назва [Товари/Послуги]",
    "К-ть [Товари/Послуги]",
    "Ціна за од. [Товари/Послуги]",
    "Сума [Товари/Послуги]",
    "Собівартість [Товари/Послуги]",
    "Знижка [Товари/Послуги]",
    "Сума",
    "Прибуток",
    "Оплачено",
    "Спосіб оплати",
    "UTM Source",
    "UTM Medium",
    "UTM Campaign",
    "UTM Term",
    "UTM Content",
    "Сайт ID",
    "Менеджер ID",
    "Статус ID",
    "AI Оцінка КЛН",
    "AI Коментар",
    "Категорія звернення",
    "Причина відмови",
    "Тип звернення",
    "Дата оновлення",
]


# ───────────────────────── API клієнт ───────────────────────────────


class SalesDriveAPIError(Exception):
    """Помилки звернень до SalesDrive API."""


def _make_session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Form-Api-Key": api_key,
    })
    return s


def _safe_get(session: requests.Session, url: str, params: dict = None,
              timeout: int = 30) -> dict:
    """GET з ретраями на 429/5xx/rate-limit, експоненційний backoff."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()

            # SalesDrive повертає 400 з message="API limit reached..." при rate-limit
            if r.status_code == 400:
                try:
                    body = r.json()
                    msg = (body.get("message") or "").lower()
                    if "api limit" in msg or "limit reached" in msg:
                        # Треба чекати ДО кінця хвилини (60с з запасом)
                        wait = 65
                        print(f"  ⚠ rate limit на endpoint — чекаю {wait}s до скидання вікна ({attempt}/{MAX_RETRIES})",
                              file=sys.stderr)
                        time.sleep(wait)
                        continue
                except Exception:
                    pass
                # Інший 400 — фатальний
                raise SalesDriveAPIError(f"HTTP 400 {url}\n{r.text[:500]}")

            if r.status_code == 429 or 500 <= r.status_code < 600:
                wait = RETRY_BACKOFF ** attempt
                print(f"  ⚠ {r.status_code} {url} — ретрай через {wait:.1f}s ({attempt}/{MAX_RETRIES})",
                      file=sys.stderr)
                time.sleep(wait)
                continue

            # 401, 403, 404 — не ретраїмо
            raise SalesDriveAPIError(
                f"HTTP {r.status_code} {url}\n{r.text[:500]}")
        except requests.RequestException as e:
            last_exc = e
            wait = RETRY_BACKOFF ** attempt
            print(f"  ⚠ {type(e).__name__} — ретрай через {wait:.1f}s ({attempt}/{MAX_RETRIES})",
                  file=sys.stderr)
            time.sleep(wait)
    raise SalesDriveAPIError(f"Не вдалось дістати {url} за {MAX_RETRIES} спроб: {last_exc}")


def fetch_orders_raw(api_key: str,
                     date_from: str,
                     date_to: str,
                     base_url: str = DEFAULT_BASE_URL,
                     page_size: int = DEFAULT_PAGE_SIZE,
                     filter_field: str = "orderTime",
                     verbose: bool = True) -> list[dict]:
    """
    Тягне всі замовлення з API за період [date_from, date_to] включно.

    date_from / date_to: "YYYY-MM-DD"
    filter_field: яке поле фільтрувати — "orderTime" (за датою заявки) або
                  "updateAt" (за датою останньої зміни). Для інкременту
                  використовуй "updateAt" — підхопить нові заявки і зміни статусів.

    Повертає список замовлень як вони приходять з API (з вкладеними products,
    contacts, ord_delivery_data тощо).
    """
    session = _make_session(api_key)
    url = f"{base_url.rstrip('/')}/api/order/list/"

    all_orders: list[dict] = []
    page = 1
    total_expected = None

    while True:
        params = {
            "page":  page,
            "limit": page_size,
            f"filter[{filter_field}][from]": date_from,
            f"filter[{filter_field}][to]":   date_to,
        }

        if verbose:
            if total_expected:
                pages_left = max(0, (total_expected - len(all_orders) + page_size - 1) // page_size)
                eta_sec = pages_left * DEFAULT_RATE_LIMIT_SLEEP
                eta_min = eta_sec / 60
                print(f"  → сторінка {page} (отримано {len(all_orders)}/{total_expected}, "
                      f"ще ~{pages_left} стор · ~{eta_min:.1f} хв)", file=sys.stderr)
            else:
                print(f"  → сторінка {page} (отримано {len(all_orders)})", file=sys.stderr)

        data = _safe_get(session, url, params=params)
        chunk = data.get("data") or []
        totals = data.get("totals") or {}

        if total_expected is None:
            total_expected = totals.get("count")
            if verbose and total_expected is not None:
                expected_pages = (total_expected + page_size - 1) // page_size
                eta_total_min = expected_pages * DEFAULT_RATE_LIMIT_SLEEP / 60
                print(f"  → у відповідях вказано всього: {total_expected} "
                      f"({expected_pages} стор, ~{eta_total_min:.1f} хв)", file=sys.stderr)

        if not chunk:
            break

        all_orders.extend(chunk)

        if len(chunk) < page_size:
            break  # остання сторінка

        page += 1
        time.sleep(DEFAULT_RATE_LIMIT_SLEEP)

    if verbose:
        print(f"  ✓ отримано всього: {len(all_orders)}", file=sys.stderr)

    return all_orders


# ─────────────────── Конвертація в DataFrame ────────────────────────


def _safe_str(v) -> str:
    return "" if v is None else str(v)


def _safe_float(v) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (ValueError, TypeError):
        return 0.0


# Маркери позицій-доставок (рядки в назві товару, регістр не важливий).
# Такі позиції приходять з SalesDrive API, але в ручній xlsx-вивантажці їх немає.
# Якщо їх не відфільтрувати — псуються розрахунки крос-сейлу, гарантій+чохлів і виручки.
_DELIVERY_MARKERS = (
    "оплата послуги доставка",   # точна назва зі SalesDrive
    "оплата послуги",
    "плата за доставку",
    "вартість доставки",
    "доставка нова пошта",
    "доставка укрпошта",
    "доставка meest",
    "доставка rozetka",
)


def _is_delivery_position(name_lower: str) -> bool:
    """Перевіряє чи це службова позиція-доставка (а не товар)."""
    if not name_lower:
        return False
    return any(m in name_lower for m in _DELIVERY_MARKERS)


def _parse_order_to_rows(o: dict) -> list[dict]:
    """
    Розгортає одне замовлення в N рядків (по одному на кожну товарну позицію).
    Якщо у замовленні products порожній — повертає один рядок без товарної інфи.
    """
    order_time = o.get("orderTime") or ""
    # API повертає дату в форматі "2026-05-20 14:32:11" — це підхопить pandas

    # ВАЖЛИВО: SalesDrive API повертає id як string ("72") у JSON.
    # Словники мають int ключі — треба явне приведення, інакше .get() поверне None.
    def _to_int(v):
        try:
            return int(v) if v is not None and v != "" else None
        except (ValueError, TypeError):
            return None

    status_id = _to_int(o.get("statusId"))
    sajt_id = _to_int(o.get("sajt"))
    user_id = _to_int(o.get("userId"))

    # Базові поля рядка (повторюються для кожної позиції)
    base = {
        "Дата":                    order_time,
        "Номер 1С":                o.get("nomer1S") or None,
        "Статус":                  STATUS_ID_TO_NAME.get(status_id, f"id={status_id}"),
        "Сайт":                    SAJT_ID_TO_NAME.get(sajt_id, f"id={sajt_id}" if sajt_id else ""),
        "Менеджер":                USER_ID_TO_NAME.get(user_id, f"id={user_id}" if user_id else ""),
        "ID замовлення":           o.get("id"),
        "Сума":                    _safe_float(o.get("paymentAmount")),
        "Прибуток":                _safe_float(o.get("profitAmount")),
        "Оплачено":                _safe_float(o.get("payedAmount")),
        "Спосіб оплати":           _safe_str(o.get("payment_method")),
        "UTM Source":              _safe_str(o.get("utmSource")),
        "UTM Medium":              _safe_str(o.get("utmMedium")),
        "UTM Campaign":            _safe_str(o.get("utmCampaign")),
        "UTM Term":                _safe_str(o.get("utmTerm")),
        "UTM Content":             _safe_str(o.get("utmContent")),
        "Сайт ID":                 sajt_id,
        "Менеджер ID":             user_id,
        "Статус ID":               status_id,
        "AI Оцінка КЛН":           o.get("ocenkaKLN"),
        "AI Коментар":             _safe_str(o.get("komentarAI")),
        "Категорія звернення":     o.get("kategoriaZvernenna"),
        "Причина відмови":         o.get("pricinaVidmovi"),
        "Тип звернення":           o.get("tipStvorennaZaavki"),
        "Дата оновлення":          o.get("updateAt") or "",
    }

    products = o.get("products") or []
    if not products:
        # Замовлення без товарних позицій (буває для лідів)
        row = dict(base)
        row["Назва [Товари/Послуги]"]            = ""
        row["К-ть [Товари/Послуги]"]             = 0.0
        row["Ціна за од. [Товари/Послуги]"]      = 0.0
        row["Сума [Товари/Послуги]"]             = 0.0
        row["Собівартість [Товари/Послуги]"]     = 0.0
        row["Знижка [Товари/Послуги]"]           = 0.0
        return [row]

    rows = []
    for p in products:
        # Назва: пріоритет UA-перекладу, фолбек на основну
        name = p.get("nameTranslate") or p.get("name") or p.get("documentName") or ""
        name_str = _safe_str(name).lower()

        # ПРОПУСКАЄМО позиції-доставки: API повертає їх як окремий рядок у products[],
        # але в ручній xlsx-вивантажці їх немає. Якщо не відфільтрувати — псує крос-сейл,
        # гарантії+чохли і суму замовлень.
        if _is_delivery_position(name_str):
            continue

        row = dict(base)
        amount = _safe_float(p.get("amount"))
        price = _safe_float(p.get("price"))
        row["Назва [Товари/Послуги]"]            = _safe_str(name)
        row["К-ть [Товари/Послуги]"]             = amount
        row["Ціна за од. [Товари/Послуги]"]      = price
        row["Сума [Товари/Послуги]"]             = amount * price
        row["Собівартість [Товари/Послуги]"]     = _safe_float(p.get("costPrice"))
        row["Знижка [Товари/Послуги]"]           = _safe_float(p.get("discount"))
        rows.append(row)

    # Якщо ВСІ позиції були доставкою — повертаємо порожній рядок-замовлення (як лід)
    if not rows:
        row = dict(base)
        row["Назва [Товари/Послуги]"]            = ""
        row["К-ть [Товари/Послуги]"]             = 0.0
        row["Ціна за од. [Товари/Послуги]"]      = 0.0
        row["Сума [Товари/Послуги]"]             = 0.0
        row["Собівартість [Товари/Послуги]"]     = 0.0
        row["Знижка [Товари/Послуги]"]           = 0.0
        rows.append(row)

    return rows


def orders_to_dataframe(orders: list[dict]) -> pd.DataFrame:
    """Конвертує сирий список замовлень з API у плоский DataFrame."""
    rows = []
    for o in orders:
        rows.extend(_parse_order_to_rows(o))

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = pd.DataFrame(rows)

    # Гарантуємо що ВСІ очікувані колонки є (порядок збережено).
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[OUTPUT_COLUMNS]

    return df


def fetch_orders_to_dataframe(api_key: Optional[str] = None,
                              month: Optional[str] = None,
                              date_from: Optional[str] = None,
                              date_to: Optional[str] = None,
                              base_url: str = DEFAULT_BASE_URL,
                              filter_field: str = "orderTime",
                              verbose: bool = True) -> pd.DataFrame:
    """
    Зручна обгортка: тягне з API і одразу повертає DataFrame.

    Параметри:
      api_key:      ключ SalesDrive (якщо None — береться з env SD_API_KEY)
      month:        "2026-05" — тоді date_from = перше число, date_to = сьогодні
      date_from:    "2026-05-01"
      date_to:      "2026-05-21"
      filter_field: "orderTime" (за датою заявки) або "updateAt" (за зміною)
    """
    if api_key is None:
        api_key = os.getenv("SD_API_KEY", "").strip()
    if not api_key:
        raise SalesDriveAPIError(
            "API ключ не вказаний. Додайте --api-key, або експортуйте SD_API_KEY в env."
        )

    if month:
        if not date_from:
            date_from = f"{month}-01"
        if not date_to:
            # До поточного дня, або до кінця місяця якщо місяць у минулому
            today = date.today()
            month_dt = datetime.strptime(month, "%Y-%m").date()
            if month_dt.year == today.year and month_dt.month == today.month:
                date_to = today.strftime("%Y-%m-%d")
            else:
                # Кінець місяця: пара хитрих рядків без зайвих залежностей
                next_month = month_dt.replace(day=28) + pd.Timedelta(days=4)
                last_day = (pd.Timestamp(next_month) - pd.Timedelta(days=next_month.day)).date()
                date_to = last_day.strftime("%Y-%m-%d")

    if not date_from or not date_to:
        raise SalesDriveAPIError(
            "Не вказано період. Передайте month='YYYY-MM' або date_from + date_to."
        )

    if verbose:
        print(f"📥 SalesDrive API: тягну замовлення з {date_from} по {date_to} "
              f"(filter: {filter_field})", file=sys.stderr)

    orders = fetch_orders_raw(
        api_key=api_key,
        date_from=date_from,
        date_to=date_to,
        base_url=base_url,
        filter_field=filter_field,
        verbose=verbose,
    )
    df = orders_to_dataframe(orders)

    if verbose:
        print(f"✓ DataFrame: {len(df)} рядків (товарних позицій)", file=sys.stderr)
        if len(df):
            unique_orders = df["ID замовлення"].nunique()
            print(f"✓ Унікальних замовлень: {unique_orders}", file=sys.stderr)
            print(f"✓ Розбивка по сайтах:", file=sys.stderr)
            for site, n in df.drop_duplicates("ID замовлення")["Сайт"].value_counts().items():
                print(f"    {site}: {n}", file=sys.stderr)

    return df


# ──────────────────────────── CLI ───────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Завантажує замовлення з SalesDrive API у xlsx-файл "
                    "(формат сумісний з ручною вивантажкою)."
    )
    ap.add_argument("--month", help="Місяць у форматі YYYY-MM (приклад: 2026-05). "
                                    "Якщо вказаний — тягне за весь місяць.")
    ap.add_argument("--from", dest="date_from", help="Дата ВІД (YYYY-MM-DD).")
    ap.add_argument("--to", dest="date_to", help="Дата ДО (YYYY-MM-DD).")
    ap.add_argument("--incremental", action="store_true",
                    help="Інкремент: тягне замовлення зі змінами за останні N днів "
                         "(--inc-days, default 14) по полю updateAt, зливає з існуючим "
                         "місячним файлом. Швидко (~5-10 хв).")
    ap.add_argument("--inc-days", type=int, default=14,
                    help="Скільки днів назад тягнути в режимі --incremental (default: 14).")
    ap.add_argument("--filter-by", choices=["orderTime", "updateAt"], default="orderTime",
                    help="За яким полем фільтрувати (default: orderTime). "
                         "Для інкременту автоматично updateAt.")
    ap.add_argument("--api-key", help="API ключ. За замовчуванням з env SD_API_KEY.")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help=f"База URL (default: {DEFAULT_BASE_URL})")
    ap.add_argument("--out", default=str(DEFAULT_OUT_DIR),
                    help=f"Папка куди класти xlsx (default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--out-file", help="Повний шлях до файлу. Перебиває --out.")
    ap.add_argument("--quiet", action="store_true", help="Без прогресу в stderr.")

    args = ap.parse_args()
    verbose = not args.quiet

    # ──────── Режим: інкремент ────────
    if args.incremental:
        from datetime import timedelta
        today = date.today()
        inc_from = (today - timedelta(days=args.inc_days)).strftime("%Y-%m-%d")
        inc_to = today.strftime("%Y-%m-%d")
        current_month = today.strftime("%Y-%m")

        if verbose:
            print(f"⚡ Інкремент: тягну замовлення зі змінами за {args.inc_days} днів "
                  f"({inc_from} → {inc_to})", file=sys.stderr)

        try:
            inc_df = fetch_orders_to_dataframe(
                api_key=args.api_key,
                date_from=inc_from,
                date_to=inc_to,
                base_url=args.base_url,
                filter_field="updateAt",
                verbose=verbose,
            )
        except SalesDriveAPIError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 2

        # Куди мерджимо
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        target_path = Path(args.out_file) if args.out_file else \
                      out_dir / f"salesdrive_{current_month}_api.xlsx"

        if target_path.exists():
            if verbose:
                print(f"📂 Зливаю з існуючим: {target_path}", file=sys.stderr)
            try:
                existing = pd.read_excel(target_path)
                # Замовлення які прийшли в інкременті — заміняють старі версії в existing
                changed_ids = set(inc_df["ID замовлення"].dropna().unique())
                if changed_ids:
                    keep_mask = ~existing["ID замовлення"].isin(changed_ids)
                    if verbose:
                        kept = keep_mask.sum()
                        dropped = (~keep_mask).sum()
                        print(f"   існуючий: {len(existing)} рядків, "
                              f"замінено {dropped} (з {len(changed_ids)} замовлень), "
                              f"залишено {kept}",
                              file=sys.stderr)
                    existing = existing[keep_mask]
                # Додаємо інкремент
                merged = pd.concat([existing, inc_df], ignore_index=True, sort=False)
                # Сортуємо по даті, щоб файл був охайний
                merged = merged.sort_values("Дата").reset_index(drop=True)
                df_out = merged
            except Exception as e:
                print(f"⚠ Не вдалось злити з існуючим ({e}). Зберігаю тільки інкремент.",
                      file=sys.stderr)
                df_out = inc_df
        else:
            if verbose:
                print(f"⚠ Місячний файл ще не існує: {target_path}", file=sys.stderr)
                print(f"   ВАЖЛИВО: за межами 14-денного вікна даних не буде!", file=sys.stderr)
                print(f"   Запусти спершу один раз --month {current_month} для повного знімка.",
                      file=sys.stderr)
            df_out = inc_df

        df_out.to_excel(target_path, index=False, engine="openpyxl")
        if verbose:
            unique = df_out["ID замовлення"].nunique() if "ID замовлення" in df_out.columns else 0
            print(f"💾 Збережено: {target_path} ({len(df_out)} рядків, "
                  f"{unique} замовлень)", file=sys.stderr)
        return 0

    # ──────── Режим: повний місяць або діапазон ────────
    if not args.month and not (args.date_from and args.date_to):
        ap.error("Вкажіть --month YYYY-MM, або обидва --from / --to, або --incremental.")

    try:
        df = fetch_orders_to_dataframe(
            api_key=args.api_key,
            month=args.month,
            date_from=args.date_from,
            date_to=args.date_to,
            base_url=args.base_url,
            filter_field=args.filter_by,
            verbose=verbose,
        )
    except SalesDriveAPIError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    # Куди зберігати
    if args.out_file:
        out_path = Path(args.out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.month:
            stem = f"salesdrive_{args.month}_api.xlsx"
        else:
            stem = f"salesdrive_{args.date_from}_to_{args.date_to}_api.xlsx"
        out_path = out_dir / stem

    df.to_excel(out_path, index=False, engine="openpyxl")

    if verbose:
        print(f"💾 Збережено: {out_path} ({len(df)} рядків)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
