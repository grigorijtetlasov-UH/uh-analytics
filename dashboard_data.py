"""dashboard_data.py — реальні дані для дашборда v2 (Огляд + Продажі) → docs/data.json.

Продажі: через sales_kpi._load_raw_excel (канон дедупу/статусів — не дублюю).
MCI: зі схеми `mci` в PostgreSQL (finance.db.connection).
Запуск:  cd ~/uh-analytics && venv/bin/python dashboard_data.py
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import sales_kpi
from finance.db.connection import connect

OUT = Path("docs/data.json")
CONFIG = Path("data/manual_config.json")
_TREND_CACHE = Path("docs/mkt_trend.json")
_MON_SHORT = {1: "Січ", 2: "Лют", 3: "Бер", 4: "Кві", 5: "Тра", 6: "Чер",
              7: "Лип", 8: "Сер", 9: "Вер", 10: "Жов", 11: "Лис", 12: "Гру"}

C_SITE = "Сайт"; C_MGR = "Менеджер"; C_NAME = "Назва [Товари/Послуги]"
C_QTY = "К-ть [Товари/Послуги]"; C_LSUM = "Сума [Товари/Послуги]"
C_SUM = "Сума"; C_OID = "ID замовлення"

GROUP_META = {
    "roll":    {"name": "Ролл",    "color": "#00d68f"},
    "amebli":  {"name": "Амебли",  "color": "#a29bfe"},
    "seti":    {"name": "Сети",    "color": "#339af0"},
    "roznica": {"name": "Розниця", "color": "#ffa94d"},
}


# ── CRM статус → стадія воронки (узгоджено з таблицею statuses у PG / Callaider) ──
CRM_STATUS_CAT = {
    "Новий": "in_progress", "Контроль оператора": "in_progress", "В обробці": "in_progress",
    "Недодзвон": "in_progress", "Питання по замовленню": "in_progress",
    "Контроль оплати": "in_progress", "Потрібне уточнення/перезвон": "in_progress",
    "Відвідає шоу-рум": "in_progress", "Переадресація": "in_progress",
    "В виробництві": "production", "В черзі на відправлення": "production",
    "Прибув у відділення": "shipping", "Їде до клієнта": "shipping",
    "Створена ТТН": "shipping", "Відправлено": "shipping",
    "Закінчився термін зберігання": "shipping", "Повторне звернення": "in_progress",
    "Отримано": "sale",
    "Відмова (не відправлено)": "refused", "Відмова (відправлено)": "returned",
    "Лід (не купив)": "lead",
    "Спам на согласование": "spam", "Спам Дубль": "spam", "Рекламный спам": "spam",
    "Помилка менеджера": "junk", "Рекламація": "claim",
}


def _status_cat(status):
    return CRM_STATUS_CAT.get(str(status).strip(), "unknown")


# Продажі = замовлення + відмови. Бізнес-рішення: відмова — це теж продаж,
# який клієнт уже ПІСЛЯ оформлення повернув / не забрав / закінчився термін.
SALE_CATS = ("order", "refused")


# ── 1С-маржа (SALES-відгрузки: виручка СуммаПродажи − собівартість СебестоимостьПродажи) ──
def _num1c(v):
    try:
        return float(str(v if v is not None else 0).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except Exception:
        return 0.0


def _subdiv_group(podr):
    s = str(podr).lower()
    if "matrasroll" in s or s.startswith("matras"):
        return "roll"
    if "a-mebli" in s or "amebli" in s:
        return "amebli"
    if "шоу-рум" in s or "шоурум" in s:
        return "roznica"
    return "seti"


CAT_BUCKET = {
    "матрасы": "Матраци", "матрас": "Матраци", "безпружинні матраци": "Матраци",
    "матрасы покращений чохол": "Матраци",
    "топперы": "Топери", "топперы улучшенный чехол": "Топери",
    "диваны": "М'які меблі",
    "корпусная мебель": "Корпусні", "шкафы-купе": "Корпусні", "кровати": "Корпусні",
    "гарантии": "Послуги/Доставка", "услуги": "Послуги/Доставка",
    "доставка нп": "Послуги/Доставка", "доставка город": "Послуги/Доставка",
}


def _cat_bucket(cat):
    return CAT_BUCKET.get(str(cat).strip().lower(), "Інше")


def _fetch_1c_sales(cur_month):
    """Чисті рядки 1С SALES за місяць (без 'НЕ ТРОГАТЬ'). [] якщо API недоступне."""
    try:
        import calendar
        import fetch_data as fd
        y, mo = cur_month.split("-")
        last = calendar.monthrange(int(y), int(mo))[1]
        rows = fd.post_1c(fd.API_URL_UH, "SALES", y + mo + "01", y + mo + f"{last:02d}")
    except Exception as e:
        print("  1С SALES: пропущено (", e, ")")
        return []
    clean = []
    for r in rows:
        if fd.is_ne_trogat(r):
            continue
        d = str(r.get("Дата", "")).strip().split(".")
        if len(d) == 3 and (d[2] + "-" + d[1]) != cur_month:
            continue
        clean.append(r)
    return clean


ORDER_GROUPS = ["roll", "amebli", "seti", "roznica", "sofino", "other"]


def _order_group(podr):
    """Мапінг 1С Подразделение (ORDERS) → група Секції 1.
    Правила: Сети='Мережі', Розниця='Шоу-Рум', Ролл=Matrasroll, Амебли=A-mebli,
    Софіно=Sofino, решта (ОПТ/ДРОП/DR-TV/HabStor/Prom/Администрация…) → 'other' (Інше)."""
    p = str(podr or "").strip().lower()
    if "мереж" in p:
        return "seti"
    if "шоу" in p:                                  # Шоу-Рум / Шоу-рум
        return "roznica"
    if "matrasroll" in p:
        return "roll"
    if "a-mebli" in p or "amebli" in p or "а-мебли" in p:
        return "amebli"
    if "sofino" in p or "софіно" in p or "софино" in p:
        return "sofino"
    return "other"


def _fetch_1c_orders(cur_month):
    """Чисті рядки 1С ORDERS (Замовлення покупця) за місяць: без 'НЕ ТРОГАТЬ' і БЕЗ доставки. [] якщо недоступне."""
    try:
        import calendar
        import fetch_data as fd
        y, mo = cur_month.split("-")
        last = calendar.monthrange(int(y), int(mo))[1]
        rows = fd.post_1c(fd.API_URL_UH, "ORDERS", y + mo + "01", y + mo + f"{last:02d}")
    except Exception as e:
        print("  1С ORDERS: пропущено (", e, ")")
        return []
    clean = []
    for r in rows:
        if fd.is_ne_trogat(r) or fd.is_delivery_row(r):     # без сміття + без доставки (Нова Пошта/по місту)
            continue
        d = str(r.get("Дата", "")).strip().split(".")
        if len(d) == 3 and (d[2] + "-" + d[1]) != cur_month:
            continue
        clean.append(r)
    return clean


def orders_1c_section1(rows_cur, rows_prev, day_count):
    """Секція 1 (Огляд) з 1С ORDERS: денна `Сумма` по 6 групах (поточний місяць) + May-тотал.
    Групи: Ролл/Амебли/Сети/Розниця/Софіно/Інше (мапінг — _order_group). Доставку вже виключено.
    Факт = усі замовлення (відмови включені — як obsyag у CRM). `Сумма` по рядках → сумуємо."""
    groups = {gk: {"june": [0.0] * day_count, "may_total": 0.0} for gk in ORDER_GROUPS}
    for r in rows_cur:
        gk = _order_group(r.get("Подразделение"))
        try:
            day = int(str(r.get("Дата", "")).strip().split(".")[0])
        except Exception:
            continue
        if 1 <= day <= day_count:
            groups[gk]["june"][day - 1] += _num1c(r.get("Сумма"))
    for r in rows_prev:
        gk = _order_group(r.get("Подразделение"))
        groups[gk]["may_total"] += _num1c(r.get("Сумма"))
    for gk in groups:
        groups[gk]["june"] = [round(x) for x in groups[gk]["june"]]
        groups[gk]["may_total"] = round(groups[gk]["may_total"])
    return {"groups": groups}


ORDER_STATE_CARDS = ["Отказ (Не отправлен)", "Отказ (Отправлен)", "Рекламация",
                     "Помилка менеджера", "Потрібно уточнення/передз", "Спам/Помилка/Дубль"]


def orders_1c_section3(rows_cur, day_count):
    """Секція 3 (1С-режим): по 6 станах — к-сть УНІК. замовлень (НомерЗаказа) + сума ₴.
    + денні: відмови = «Отказ (Не отправлен)», повернення = «Отказ (Отправлен)» (унік. замовлення по днях)."""
    seen, sums = {}, {}
    ne_seen = [set() for _ in range(day_count)]
    otpr_seen = [set() for _ in range(day_count)]
    for r in rows_cur:
        st = str(r.get("СостояниеЗаказа", "")).strip()
        no = str(r.get("НомерЗаказа", "")).strip()
        sums[st] = sums.get(st, 0.0) + _num1c(r.get("Сумма"))
        seen.setdefault(st, set()).add(no)
        try:
            day = int(str(r.get("Дата", "")).strip().split(".")[0])
        except Exception:
            day = 0
        if 1 <= day <= day_count:
            if st == "Отказ (Не отправлен)":
                ne_seen[day - 1].add(no)
            elif st == "Отказ (Отправлен)":
                otpr_seen[day - 1].add(no)
    cards = {st: {"count": len(seen.get(st, set())), "sum": round(sums.get(st, 0.0))}
             for st in ORDER_STATE_CARDS}
    return {"cards": cards,
            "daily": {"ne": [len(s) for s in ne_seen],
                      "otpr": [len(s) for s in otpr_seen]}}


def fetch_1c_margin(rows):
    """Маржа з 1С SALES. rows — чисті рядки.
    Маржа рахується ЛИШЕ по рядках із заповненою собівартістю (cost>0).
    coverage = частка виручки, підкріпленої собівартістю; низьке → маржі не вірити."""
    agg = {gk: {"rev": 0.0, "cats": {}} for gk in GROUP_META}
    for r in rows:
        gk = _subdiv_group(r.get("Подразделение"))
        rev = _num1c(r.get("СуммаПродажи")); cost = _num1c(r.get("СебестоимостьПродажи"))
        qty = _num1c(r.get("КоличествоПродажи"))
        b = _cat_bucket(r.get("КатегорияНоменклатуры"))
        agg[gk]["rev"] += rev
        cb = agg[gk]["cats"].setdefault(b, {"rev": 0.0, "qty": 0.0, "rcov": 0.0, "ccov": 0.0})
        cb["rev"] += rev; cb["qty"] += qty
        if cost > 0:                      # маржу рахуємо лише з реальною собівартістю
            cb["rcov"] += rev; cb["ccov"] += cost

    out = {}
    for gk, gv in agg.items():
        grev = gv["rev"]
        if grev <= 0:
            continue
        grcov = gccov = 0.0
        cats = []
        for n, cb in gv["cats"].items():
            cr = cb["rev"]
            if cr <= 0:
                continue
            rc, cc = cb["rcov"], cb["ccov"]
            m = round((rc - cc) / rc * 100, 1) if rc > 0 else None
            ac = round(cr / cb["qty"]) if cb["qty"] else 0
            grcov += rc; gccov += cc
            cats.append({"n": n, "share": round(cr / grev, 4), "m": m, "mp": m,
                         "ac": ac, "acp": ac, "rev": round(cr), "cov": round(rc / cr, 2)})
        cats.sort(key=lambda x: -x["rev"])
        gm = round((grcov - gccov) / grcov * 100, 1) if grcov > 0 else None
        gcov = round(grcov / grev, 2) if grev > 0 else 0.0
        out[gk] = {"rev": round(grev), "margin": gm, "coverage": gcov,
                   "reliable": gcov >= 0.7, "cats": cats}
    return out


REFUSE_STATES = {"Отказ (Отправлен)"}                       # 1С: стан-відмова (єдиний)
JUNK_STATES = {"Спам/Помилка/Дубль", "Помилка менеджера"}   # сміття — не рахуємо взагалі


def fetch_1c_refuse(rows):
    """Канонічні відмови з 1С (СостояниеЗаказа): overall + по групах.
    sold = усі валідні замовлення (без JUNK); refused = стан ∈ REFUSE_STATES.
    Дедуп по НомерЗаказа (стан/група = перший рядок замовлення)."""
    state, group = {}, {}
    for r in rows:
        no = str(r.get("НомерЗаказа", "")).strip()
        if not no or no in state:
            continue
        state[no] = str(r.get("СостояниеЗаказа", "")).strip()
        group[no] = _subdiv_group(r.get("Подразделение"))

    def tally(ids):
        sold = refused = 0
        for no in ids:
            st = state[no]
            if st in JUNK_STATES:
                continue
            sold += 1
            if st in REFUSE_STATES:
                refused += 1
        return {"refused": refused, "sold": sold,
                "pct": round(refused / sold * 100, 1) if sold else 0.0}

    ids = list(state)
    return {"overall": tally(ids),
            "by_group": {gk: tally([n for n in ids if group[n] == gk]) for gk in GROUP_META}}


def _excl_sh(df):
    if C_SITE in df.columns:
        return df[~df[C_SITE].astype(str).str.contains(r"\bСХ\b", regex=True, na=False)]
    return df


def _orders(df):
    key = C_OID if C_OID in df.columns else "Номер 1С"
    return df.drop_duplicates(subset=[key], keep="last")


def _rev_by_site(df):
    o = _orders(df); o = o[o["_категорія"].isin(SALE_CATS)]
    return {str(s): float(g[C_SUM].fillna(0).sum()) for s, g in o.groupby(C_SITE)}


def _group_of(site):
    s = str(site).lower()
    if "matrasroll" in s:
        return "roll"
    if "amebli" in s:
        return "amebli"
    if "шоу-рум" in s or "шоурум" in s:
        return "roznica"
    return "seti"


def channels(df, prev_by_site):
    o = _orders(df); o = o[o["_категорія"].isin(SALE_CATS)]
    res = []
    for site, g in o.groupby(C_SITE):
        rev = float(g[C_SUM].fillna(0).sum()); n = int(len(g))
        avg = round(rev / n) if n else 0
        prev = float(prev_by_site.get(str(site), 0))
        if prev > 0:
            d = (rev - prev) / prev * 100
            dcls = "up" if d >= 0 else "down"; dtxt = ("+" if d >= 0 else "") + f"{d:.0f}%"
        else:
            dcls, dtxt = "neu", "—"
        res.append({"name": str(site), "orders": n, "revenue": round(rev), "avg_check": avg,
                    "prev_revenue": round(prev), "delta_cls": dcls, "delta_txt": dtxt})
    res.sort(key=lambda x: -x["revenue"])
    return res


def managers(df):
    o = _orders(df); res = []
    has_st = "Статус" in o.columns
    for mgr, g in o.groupby(C_MGR):
        sold = g[g["_категорія"].isin(["order", "refused"])]
        refused = g[g["_категорія"] == "refused"]
        og = g[g["_категорія"] == "order"]
        rev = float(og[C_SUM].fillna(0).sum()); n = int(len(og))
        avg = round(rev / n) if n else 0
        refp = round(len(refused) / len(sold) * 100, 1) if len(sold) else 0.0
        conv = ret = None
        if has_st:                                       # реальні конв./повернення зі статусів
            cats = g["Статус"].map(_status_cat)
            lost = int((cats == "lead").sum())           # «Лід (не купив)»
            ret = int((cats == "returned").sum())        # «Відмова (відправлено)»
            conv = round(n / (n + lost) * 100, 1) if (n + lost) else 0.0  # виграно/(виграно+втрач.)
        res.append({"name": str(mgr), "orders": n, "revenue": round(rev),
                    "avg_check": avg, "refuse_pct": refp,
                    "conversion": conv, "returns": ret})
    res.sort(key=lambda x: -x["revenue"])
    return res


def products(df, top=50):
    d = df[df[C_NAME].notna()].copy()
    d = d[d[C_NAME].apply(lambda x: sales_kpi.classify_item(x) == "main")]
    res = []
    for name, g in d.groupby(C_NAME):
        cnt = int(g[C_OID].nunique()) if C_OID in g.columns else int(len(g))
        res.append({"name": str(name), "count": cnt,
                    "revenue": round(float(g[C_LSUM].fillna(0).sum())),
                    "qty": int(g[C_QTY].fillna(0).sum())})
    res.sort(key=lambda x: -x["revenue"])
    return res[:top]


def crm_funnel(df):
    """Лічильники Секції 3 з CRM (унікальні ліди за ID замовлення)."""
    oid = C_OID if C_OID in df.columns else None
    scol = "Статус"

    def cnt(statuses):
        if scol not in df.columns:
            return 0
        d = df[df[scol].isin(statuses)]
        return int(d[oid].nunique()) if (oid and oid in d.columns) else int(len(d))

    spam = cnt(["Спам на согласование", "Рекламный спам"])
    dubli = cnt(["Спам Дубль"])
    nedodzvon = cnt(["Недодзвон"])
    lost = cnt(["Лід (не купив)"])
    return {"spam": spam, "dubli": dubli, "spam_total": spam + dubli,
            "nedodzvon": nedodzvon, "lost": lost}


def order_funnel(df):
    """Реальна воронка з CRM-статусів: унікальні замовлення (ID) по стадіях.
    Знімок — поточний статус кожного замовлення, згрупований за категорією."""
    if "Статус" not in df.columns:
        return {}
    o = _orders(df)
    c = {"in_progress": 0, "production": 0, "shipping": 0, "sale": 0,
         "refused": 0, "returned": 0, "lead": 0, "spam": 0, "claim": 0, "unknown": 0}
    detail = {}                                         # {категорія: {статус: к-сть}}
    for st in o["Статус"].astype(str):
        s = st.strip()
        cat = _status_cat(s)
        if cat == "junk":
            continue
        c[cat] = c.get(cat, 0) + 1
        detail.setdefault(cat, {})
        detail[cat][s] = detail[cat].get(s, 0) + 1
    real = ("in_progress", "production", "shipping", "sale",
            "refused", "returned", "lead", "claim")
    c["leads_total"] = sum(c[k] for k in real)          # реальні ліди (без спаму/невідомих)
    c["_detail"] = detail                               # розбивка кожної категорії по статусах
    return c


def daily_refuse(df, day_count):
    """Денні відмови/повернення з CRM (унік. замовлення по даті замовлення).
    Увага: дата = дата замовлення, не дата відмови (статус-дат у CRM-експорті нема),
    тож свіжі дні показують менше відмов (лаг до рішення про відмову)."""
    if "Статус" not in df.columns or "_дата" not in df.columns:
        return {}
    o = _orders(df).copy()
    o["_d"] = o["_дата"].dt.day
    o["_c"] = o["Статус"].map(_status_cat)
    ref = [0] * day_count
    ret = [0] * day_count
    tot = [0] * day_count
    for d, cat in zip(o["_d"], o["_c"]):
        try:
            i = int(d) - 1
        except (ValueError, TypeError):
            continue
        if not (0 <= i < day_count) or cat in ("spam", "junk", "unknown"):
            continue
        tot[i] += 1
        if cat == "refused":
            ref[i] += 1
        elif cat == "returned":
            ret[i] += 1
    pct = [round((ref[i] + ret[i]) / tot[i] * 100, 1) if tot[i] else 0.0 for i in range(day_count)]
    return {"days": [str(i + 1) for i in range(day_count)],
            "refused": ref, "returned": ret, "pct": pct}


def daily(df):
    o = _orders(df); o = o[o["_категорія"].isin(SALE_CATS)]
    s = o.groupby("_день")[C_SUM].sum().sort_index()
    return {str(k): round(float(v)) for k, v in s.items()}


def shipments(rows_cur, rows_prev, day_count):
    """Денні відгрузки з 1С SALES (СуммаПродажи по днях поточного місяця) + сума минулого."""
    def by_day(rows):
        d = {}
        for r in rows:
            dd = str(r.get("Дата", "")).strip().split(".")
            if len(dd) != 3:
                continue
            try:
                day = int(dd[0])
            except ValueError:
                continue
            d[day] = d.get(day, 0.0) + _num1c(r.get("СуммаПродажи"))
        return d
    cur = by_day(rows_cur)
    june = [round(cur.get(d, 0)) for d in range(1, day_count + 1)]
    may_total = round(sum(_num1c(r.get("СуммаПродажи")) for r in rows_prev)) if rows_prev else 0
    return {"june": june, "may_total": may_total, "plan": 0}


def groups(df, prev, day_count):
    o = _orders(df); o = o[o["_категорія"].isin(SALE_CATS)].copy()
    o["_g"] = o[C_SITE].apply(_group_of)
    out = {}
    for gk, meta in GROUP_META.items():
        g = o[o["_g"] == gk]
        n = int(len(g)); rev = float(g[C_SUM].fillna(0).sum())
        byday = {int(k): float(v) for k, v in
                 g.groupby(g["_дата"].dt.day)[C_SUM].sum().items()}
        june = [round(byday.get(d, 0)) for d in range(1, day_count + 1)]
        out[gk] = {"name": meta["name"], "color": meta["color"],
                   "june": june, "may": 0, "plan": 0,
                   "orders": n, "avg": round(rev / n) if n else 0}
    if prev is not None:
        po = _orders(prev); po = po[po["_категорія"].isin(SALE_CATS)].copy()
        po["_g"] = po[C_SITE].apply(_group_of)
        for gk in GROUP_META:
            out[gk]["may"] = round(float(po[po["_g"] == gk][C_SUM].fillna(0).sum()))
    return out


def mci_bar(daily_sales):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT snapshot_date, score, label FROM mci.snapshots "
                    "WHERE snapshot_date < CURRENT_DATE "
                    "ORDER BY snapshot_date DESC LIMIT 25")
        rows = list(reversed(cur.fetchall()))
    labels = [r[0].strftime("%d.%m") for r in rows]
    vals = [float(r[1]) for r in rows]
    sales = [round(daily_sales.get(r[0].strftime("%Y-%m-%d"), 0) / 1000) for r in rows]
    pairs = [(v, s) for v, s in zip(vals, sales) if s > 0]
    corr = None
    if len(pairs) >= 7:
        import statistics
        try:
            corr = round(statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs]), 2)
        except Exception:
            corr = None
    return {"labels": labels, "mci": vals, "sales": sales,
            "score": round(vals[-1]) if vals else None,
            "label": rows[-1][2] if rows else None,
            "date": rows[-1][0].strftime("%d.%m") if rows else None,
            "corr": corr, "days": len(vals)}


def daily_layer(df, m1c_rows):
    """Фаза 1 (Б): подобовий шар АДИТИВНИХ компонентів → docs/daily.json.
    По днях × сутність зберігаємо суми/лічильники, щоб клієнтський двигун
    підсумував будь-який діапазон і вивів ТІ САМІ формули, що й місячні блоки."""
    import pandas as pd
    day = {}

    def D(d):
        return day.setdefault(str(int(d)), {
            "ch": {}, "grp": {}, "mgr": {},
            "fun": {},                                            # _status_cat (без junk) → pipeline
            "kpi": {"order": 0, "refused": 0, "lost": 0, "lead": 0, "spam": 0},  # → конверсія
            "cf": {"spam": 0, "dubli": 0, "nedodzvon": 0, "lost": 0},            # Секція 3 (конкр. статуси)
            "prod": {}, "ship": 0.0,
            "mrg": {},                                            # {grp:{cat:{rev,qty,rcov,ccov}}} → маржа 1С
            "r1c": {"ov": {"sold": 0, "refused": 0}, "grp": {}}}) # відмови 1С (overall+групи)

    # ── CRM-замовлення (дедуп по ID): канали/групи/менеджери/воронка/kpi/Секція3 ──
    o = _orders(df).copy()
    o["_d"] = o["_дата"].dt.day
    has_st = "Статус" in o.columns
    for _, r in o.iterrows():
        dv = r["_d"]
        if pd.isna(dv):
            continue
        b = D(dv)
        site = str(r.get(C_SITE)); mgr = str(r.get(C_MGR))
        grp = _group_of(site); s = float(r.get(C_SUM) or 0)
        kcat = str(r.get("_категорія", "other"))                 # sales_kpi-категорія
        st = str(r.get("Статус")).strip() if has_st else ""
        scat = _status_cat(st) if has_st else "unknown"          # воронка-категорія
        if scat != "junk":                                       # воронка: усе крім сміття
            b["fun"][scat] = b["fun"].get(scat, 0) + 1
        if st in ("Спам на согласование", "Рекламный спам"):     # Секція 3 (конкретні статуси)
            b["cf"]["spam"] += 1
        elif st == "Спам Дубль":
            b["cf"]["dubli"] += 1
        elif st == "Недодзвон":
            b["cf"]["nedodzvon"] += 1
        elif st == "Лід (не купив)":
            b["cf"]["lost"] += 1
        if kcat in SALE_CATS:                                    # обсяг = order+refused
            c = b["ch"].setdefault(site, {"rev": 0.0, "n": 0}); c["rev"] += s; c["n"] += 1
            g = b["grp"].setdefault(grp, {"rev": 0.0, "n": 0}); g["rev"] += s; g["n"] += 1
        mg = b["mgr"].setdefault(mgr, {"won": 0, "ref": 0, "lost": 0, "ret": 0, "rev": 0.0})
        if kcat == "order":
            mg["won"] += 1; mg["rev"] += s
        elif kcat == "refused":
            mg["ref"] += 1
        if scat == "lead":
            mg["lost"] += 1
        if scat == "returned":
            mg["ret"] += 1

    # ── KPI-компоненти конверсії — ТОЧНО за sales_kpi._kpi_for_period ──
    # orders/refused/lost: ГЛОБАЛЬНИЙ дедуп по «Номер 1С» (.first), кожне замовлення → у свій
    #   перший день (уникаємо подвійного рахунку, якщо номер має рядки в різні дні + коректно для діапазонів);
    # refused/lost/lead/spam БЕЗ номера — рахуються ПО РЯДКАХ (кожен рядок = окрема заявка).
    has_num = "Номер 1С" in df.columns
    if has_num:
        onum = df.dropna(subset=["Номер 1С"]).copy()
        if not onum.empty:
            onum["_d"] = onum["_дата"].dt.day
            g = onum.groupby("Номер 1С", sort=False)
            cat_first = g["_категорія"].first()
            day_first = g["_d"].first()
            for num in cat_first.index:
                dv = day_first[num]
                if pd.isna(dv):
                    continue
                cat = cat_first[num]
                bb = D(dv)
                if cat in bb["kpi"]:
                    bb["kpi"][cat] += 1
        nonum = df[df["Номер 1С"].isna()].copy()
    else:
        nonum = df.copy()
    if not nonum.empty:
        nonum["_d"] = nonum["_дата"].dt.day
        for dv, gday in nonum.groupby("_d"):
            if pd.isna(dv):
                continue
            bb = D(dv)
            for cat in ("refused", "lost", "lead", "spam"):
                bb["kpi"][cat] += int((gday["_категорія"] == cat).sum())

    # ── товари (line-items, лише main) по днях ──
    pdf = df[df[C_NAME].notna()].copy()
    pdf = pdf[pdf[C_NAME].apply(lambda x: sales_kpi.classify_item(x) == "main")]
    if not pdf.empty:
        pdf["_d"] = pdf["_дата"].dt.day
        for (dv, name), g in pdf.groupby(["_d", C_NAME]):
            if pd.isna(dv):
                continue
            b = D(dv)
            b["prod"][str(name)] = {
                "rev": round(float(g[C_LSUM].fillna(0).sum())),
                "qty": int(g[C_QTY].fillna(0).sum()),
                "n": int(g[C_OID].nunique()) if C_OID in g.columns else int(len(g))}

    # ── 1С SALES (рядки): відгрузки + маржа по групах×категоріях ──
    for r in m1c_rows:
        ds = str(r.get("Дата", "")).strip().split(".")
        if len(ds) != 3:
            continue
        try:
            dv = int(ds[0])
        except ValueError:
            continue
        b = D(dv)
        rev = _num1c(r.get("СуммаПродажи")); cost = _num1c(r.get("СебестоимостьПродажи"))
        qty = _num1c(r.get("КоличествоПродажи"))
        gk = _subdiv_group(r.get("Подразделение"))
        cat = _cat_bucket(r.get("КатегорияНоменклатуры"))
        b["ship"] += rev
        m = b["mrg"].setdefault(gk, {}).setdefault(cat, {"rev": 0.0, "qty": 0.0, "rcov": 0.0, "ccov": 0.0})
        m["rev"] += rev; m["qty"] += qty
        if cost > 0:                                             # маржу — лише з реальною собівартістю
            m["rcov"] += rev; m["ccov"] += cost

    # ── 1С відмови (дедуп по НомерЗаказа — перший рядок = стан/група/день) ──
    seen = set()
    for r in m1c_rows:
        no = str(r.get("НомерЗаказа", "")).strip()
        if not no or no in seen:
            continue
        seen.add(no)
        st = str(r.get("СостояниеЗаказа", "")).strip()
        if st in JUNK_STATES:                                    # сміття не рахуємо взагалі
            continue
        ds = str(r.get("Дата", "")).strip().split(".")
        if len(ds) != 3:
            continue
        try:
            dv = int(ds[0])
        except ValueError:
            continue
        b = D(dv)
        gk = _subdiv_group(r.get("Подразделение"))
        ref = 1 if st in REFUSE_STATES else 0
        b["r1c"]["ov"]["sold"] += 1
        b["r1c"]["ov"]["refused"] += ref
        gg = b["r1c"]["grp"].setdefault(gk, {"sold": 0, "refused": 0})
        gg["sold"] += 1; gg["refused"] += ref

    # ── округлення для компактності JSON ──
    for b in day.values():
        for c in b["ch"].values():
            c["rev"] = round(c["rev"])
        for g in b["grp"].values():
            g["rev"] = round(g["rev"])
        for mg in b["mgr"].values():
            mg["rev"] = round(mg["rev"])
        b["ship"] = round(b["ship"])
        for cats in b["mrg"].values():
            for m in cats.values():
                m["rev"] = round(m["rev"]); m["qty"] = round(m["qty"], 1)
                m["rcov"] = round(m["rcov"]); m["ccov"] = round(m["ccov"])

    return {"day": day}


def _merge_reputation():
    """Зливає docs/reputation*.json (Vidhuk, Google, …) у мульти-платформну структуру:
    {generated, brands:{key:{name,color,platforms:{plat:{...}},agg:{rating,count,pos,neu,neg}}}}."""
    SRC = [("docs/reputation.json", "vidhuk"),
           ("docs/reputation_google.json", "google"),
           ("docs/reputation_056.json", "056"),
           ("docs/reputation_hotline.json", "hotline"),
           ("docs/reputation_prom.json", "prom"),
           ("docs/reputation_rozetka.json", "rozetka")]
    LABEL = {"vidhuk": "Vidhuk.ua", "google": "Google", "056": "056.ua", "hotline": "Hotline.ua",
             "prom": "Prom.ua", "rozetka": "Rozetka"}
    ICON = {"vidhuk": "\U0001f4ac", "google": "\U0001f50d", "056": "\U0001f3d9\ufe0f", "hotline": "\U0001f4ca",
            "prom": "\U0001f3ea", "rozetka": "\U0001f6d2"}
    brands, gen = {}, None
    for fname, plat in SRC:
        p = Path(fname)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        gen = data.get("generated") or gen
        for bk, bd in (data.get("brands") or {}).items():
            b = brands.setdefault(bk, {"name": bd.get("name", bk), "color": "#888", "platforms": {}})
            if bd.get("name"):
                b["name"] = bd["name"]
            if bd.get("color"):
                b["color"] = bd["color"]
            b["platforms"][plat] = {
                "label": LABEL.get(plat, plat), "icon": ICON.get(plat, "\U0001f4cb"),
                "rating": bd.get("rating"), "count": bd.get("count"),
                "sample_n": bd.get("sample_n", 0),
                "pos": bd.get("pos", 0), "neu": bd.get("neu", 0), "neg": bd.get("neg", 0),
                "dist": bd.get("dist"), "monthly": bd.get("monthly"),
                "reviews": bd.get("reviews", []), "url": bd.get("url", ""),
            }
    if not brands:
        return None
    for bk, b in brands.items():
        ps = list(b["platforms"].values())
        tc = sum((p["count"] or 0) for p in ps if p.get("rating") is not None)
        tw = sum((p["rating"] or 0) * (p["count"] or 0) for p in ps if p.get("rating") is not None)
        sn = sum(p.get("sample_n", 0) for p in ps)
        sp = sum(p.get("pos", 0) * p.get("sample_n", 0) for p in ps)
        snu = sum(p.get("neu", 0) * p.get("sample_n", 0) for p in ps)
        sng = sum(p.get("neg", 0) * p.get("sample_n", 0) for p in ps)
        b["agg"] = {"rating": round(tw / tc, 1) if tc else None, "count": tc,
                    "pos": round(sp / sn) if sn else 0, "neu": round(snu / sn) if sn else 0,
                    "neg": round(sng / sn) if sn else 0}
    return {"generated": gen, "brands": brands}


def _mkt_month(ym, mkt, until_override=None):
    """Marketing-обʼєкт за місяць ym (повний, або MTD якщо until_override).
    Reuse build_marketing; 1С-виручка за ym (SALES + ORDERS). None якщо нема 1С."""
    import calendar as _c
    yk, mk = int(ym[:4]), int(ym[5:7])
    lastd = _c.monthrange(yk, mk)[1]
    since = ym + "-01"
    until = until_override or (ym + "-%02d" % lastd)
    sales = _fetch_1c_sales(ym)
    if not sales:
        return None
    orders = _fetch_1c_orders(ym)
    m1c_m = fetch_1c_margin(sales)
    og = orders_1c_section1(orders, [], lastd)["groups"]
    _sl = lambda x: float(sum(x or []))
    bstats = {
        "amebli":     {"revenue": float((m1c_m.get("amebli") or {}).get("rev", 0) or 0), "orders": 0, "leads": None},
        "matrasroll": {"revenue": float((m1c_m.get("roll") or {}).get("rev", 0) or 0), "orders": 0, "leads": None},
        "total_revenue_ship":   sum((m1c_m.get(g) or {}).get("rev", 0) for g in m1c_m),
        "total_revenue_orders": sum(_sl(og[g]["june"]) for g in og),
        "other": [],
    }
    return mkt.build_marketing(since, until, bstats)


def main():
    import sys
    import calendar
    today = date.today()
    cur_now = today.strftime("%Y-%m")
    # Необов'язковий аргумент: цільовий місяць YYYY-MM (за замовч. — поточний).
    target = sys.argv[1] if len(sys.argv) > 1 else cur_now
    cur_month = target
    is_current = (target == cur_now)
    y, mo = int(target[:4]), int(target[5:7])
    pm = (date(y, mo, 1) - timedelta(days=1)).strftime("%Y-%m")
    # day_count: поточний місяць — через ВЧОРА (сьогодні ще не синхнулось);
    # минулі місяці — повний місяць (вони вже завершені).
    if is_current:
        day_count = today.day - 1
        if day_count < 1:
            day_count = today.day      # 1-ше число місяця: fallback на сьогодні
    else:
        day_count = calendar.monthrange(y, mo)[1]
    # Поточний → docs/data.json; минулі → docs/data-YYYY-MM.json
    out_path = OUT if is_current else Path("docs/data-" + target + ".json")

    raw = sales_kpi._load_raw_excel(cur_month)
    if raw is None:
        print("нема CRM-даних за", cur_month); return
    df = _excl_sh(raw)
    df = df[df["_місяць"] == cur_month]                      # канон: лише поточний місяць
    prev_raw = sales_kpi._load_raw_excel(pm)
    prev = _excl_sh(prev_raw) if prev_raw is not None else None
    if prev is not None:
        prev = prev[prev["_місяць"] == pm]                  # попередній — лише його місяць
    prev_by_site = _rev_by_site(prev) if prev is not None else {}

    ds = daily(df)
    grp = groups(df, prev, day_count)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    plans = (cfg.get("plans", {}) or {}).get(cur_month, {}) or {}
    costs = (cfg.get("costs", {}) or {}).get(cur_month, {}) or {}
    for gk in grp:
        if plans.get(gk):
            grp[gk]["plan"] = int(plans[gk])

    m1c_rows = _fetch_1c_sales(cur_month)
    pm_rows = _fetch_1c_sales(pm)                       # відгрузки минулого місяця (для порівняння)
    o1c_rows = _fetch_1c_orders(cur_month)              # ORDERS (Замовлення покупця) — Секція 1 (Огляд)
    o1c_prev = _fetch_1c_orders(pm)                     # ORDERS минулого місяця (для «Минулий місяць»)
    m1c = fetch_1c_margin(m1c_rows)
    for gk in grp:
        if gk in m1c:
            grp[gk]["margin"] = m1c[gk]["margin"]
            grp[gk]["coverage"] = m1c[gk]["coverage"]
            grp[gk]["reliable"] = m1c[gk]["reliable"]
            grp[gk]["cats"] = m1c[gk]["cats"]

    # ── KPI: конверсія з CRM, ВІДМОВИ — канонічні з 1С (СостояниеЗаказа) ──
    kpi = sales_kpi._kpi_for_period(df)
    ref = fetch_1c_refuse(m1c_rows)
    if ref["overall"]["sold"]:
        ov = ref["overall"]
        kpi["refuse"]["of_orders"] = ov["pct"]
        kpi["refuse"]["refused"] = ov["refused"]
        kpi["refuse"]["active"] = ov["sold"]
        kpi["refuse"]["source"] = "1С"
    for gk in grp:
        grp[gk]["refuse"] = ref["by_group"].get(gk, {"refused": 0, "sold": 0, "pct": 0.0})

    # ── відгрузки з 1С (Секція 4) ──
    ship = shipments(m1c_rows, pm_rows, day_count)
    ship["plan"] = int((cfg.get("shipments_plan", {}) or {}).get(cur_month, 0) or 0)

    # ── лічильники Секції 3 з CRM + реальна воронка зі статусів ──
    funnel = crm_funnel(df)
    funnel["pipeline"] = order_funnel(df)

    # ── Маркетинг: Meta+GA4 ÷ 1С (ДРР по брендах/відгрузках — SALES; «ДРР Замовлення» — ORDERS) ──
    sec1 = orders_1c_section1(o1c_rows, o1c_prev, day_count)
    marketing_obj = None
    try:
        import marketing as _mkt
        _since = date(y, mo, 1).strftime("%Y-%m-%d")
        _until = date(y, mo, day_count).strftime("%Y-%m-%d")
        _og = sec1["groups"]
        _sl = lambda x: float(sum(x or []))
        _oall = _orders(df).copy(); _oall["_g"] = _oall[C_SITE].apply(_group_of)
        _lbg = _oall.groupby("_g").size().to_dict()
        _bstats = {
            "amebli":     {"revenue": float((m1c.get("amebli") or {}).get("rev", 0) or 0),
                           "orders": (grp.get("amebli") or {}).get("orders", 0),
                           "leads": int(_lbg.get("amebli", 0))},
            "matrasroll": {"revenue": float((m1c.get("roll") or {}).get("rev", 0) or 0),
                           "orders": (grp.get("roll") or {}).get("orders", 0),
                           "leads": int(_lbg.get("roll", 0))},
            "total_revenue_ship":   _sl(ship.get("june")),
            "total_revenue_orders": sum(_sl(_og[g]["june"]) for g in _og),
            "total_leads":          int(len(_oall)),
            "other": [],
        }
        marketing_obj = _mkt.build_marketing(_since, _until, _bstats)
        _b, _t = marketing_obj["brands"], marketing_obj["totals"]
        print(f"  маркетинг: spend {_t['spend']}\u20b4 (Meta {_t['spend_meta']} + Google {_t['spend_google']}) \u00b7 "
              f"\u0414\u0420\u0420 Amebli {_b['amebli']['drr']}% / Matrasroll {_b['matrasroll']['drr']}% / "
              f"\u0412\u0456\u0434\u0433\u0440 {_t['drr_ship']}% / \u0417\u0430\u043c\u043e\u0432\u043b {_t['drr_orders']}%")
    except Exception as _e:
        print("  \u26a0\ufe0f \u043c\u0430\u0440\u043a\u0435\u0442\u0438\u043d\u0433 \u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u043e:", _e)

    # ── Тренд ДРР по місяцях (поточний + 2 попередні; кеш для завершених місяців) ──
    if marketing_obj:
        try:
            import marketing as _mkt2
            _months = []; _yy, _mm = y, mo
            for _ in range(3):
                _months.append("%04d-%02d" % (_yy, _mm))
                _mm -= 1
                if _mm == 0:
                    _mm = 12; _yy -= 1
            _months.reverse()
            _cache = {}
            try:
                _cache = json.loads(_TREND_CACHE.read_text(encoding="utf-8"))
            except Exception:
                pass
            _tr = {"labels": [], "amebli": [], "matrasroll": [], "ship": []}
            for _ym in _months:
                _iscur = (_ym == cur_now)
                if _iscur:
                    _d = {"amebli": marketing_obj["brands"]["amebli"]["drr"],
                          "matrasroll": marketing_obj["brands"]["matrasroll"]["drr"],
                          "ship": marketing_obj["totals"]["drr_ship"]}
                elif _ym in _cache:
                    _d = _cache[_ym]
                else:
                    _o = _mkt_month(_ym, _mkt2)
                    if _o is None:
                        continue
                    _d = {"amebli": _o["brands"]["amebli"]["drr"],
                          "matrasroll": _o["brands"]["matrasroll"]["drr"],
                          "ship": _o["totals"]["drr_ship"]}
                    _cache[_ym] = _d                       # кешуємо лише завершені місяці
                _tr["labels"].append(_MON_SHORT.get(int(_ym[5:7]), _ym) + (" (MTD)" if _iscur else ""))
                _tr["amebli"].append(_d["amebli"]); _tr["matrasroll"].append(_d["matrasroll"]); _tr["ship"].append(_d["ship"])
            try:
                _TREND_CACHE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            if len(_tr["labels"]) >= 2:
                marketing_obj["trend"] = _tr
                print("  \u0442\u0440\u0435\u043d\u0434 \u0414\u0420\u0420 (\u0432\u0456\u0434\u0433\u0440):",
                      " \u2192 ".join("%s %s%%" % (l, s) for l, s in zip(_tr["labels"], _tr["ship"])))
        except Exception as _te:
            print("  \u26a0\ufe0f \u0442\u0440\u0435\u043d\u0434 \u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u043e:", _te)

    # ── Репутація: мерж усіх джерел (Vidhuk + Google + …) у мульти-платформну структуру ──
    reputation_obj = _merge_reputation()
    if reputation_obj:
        _pn = sum(len(b["platforms"]) for b in reputation_obj["brands"].values())
        print("  репутація:", len(reputation_obj["brands"]), "бренди /", _pn, "платформ-джерел")
    else:
        print("  репутація: джерел немає (запусти reputation_vidhuk.py / reputation_google.py)")

    data = {
        "month": cur_month,
        "generated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "day_count": day_count,
        "channels": channels(df, prev_by_site),
        "managers": managers(df),
        "products": products(df),
        "daily": ds,
        "groups": grp,
        "costs": costs,
        "kpi": kpi,
        "shipments": ship,
        "funnel": funnel,
        "daily_refuse": daily_refuse(df, day_count),
        "mci": mci_bar(ds),
        "sec1_orders": sec1,
        "marketing": marketing_obj,
        "reputation": reputation_obj,
        "sec3_1c": orders_1c_section3(o1c_rows, day_count),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("✅ data.json:", out_path)
    if data["channels"]:
        top = data["channels"][0]
        print("  канали:", len(data["channels"]), "| топ:", top["name"], round(top["revenue"] / 1000), "K₴")
    print("  менеджери:", len(data["managers"]), "| товари:", len(data["products"]))
    print("  групи:", {k: round(sum(v["june"]) / 1000) for k, v in data["groups"].items()}, "K (факт міс.)")
    print("  плани:", {k: round(v["plan"] / 1000) for k, v in data["groups"].items()}, "K |",
          "затрати задано:" , bool(costs))
    print("  маржа 1С:", {k: v.get("margin") for k, v in data["groups"].items()
                          if v.get("margin") is not None})
    print("  coverage собівартості:", {k: f"{int((v.get('coverage') or 0) * 100)}%"
                                       for k, v in data["groups"].items() if "coverage" in v})
    k = data["kpi"]
    print("  конверсія:", k["conversion"]["value"], "% (CRM) | відмови:",
          k["refuse"]["of_orders"], "% (" + k["refuse"].get("source", "CRM") + ":",
          k["refuse"].get("refused", 0), "з", k["refuse"].get("active", 0), ")")
    print("  відмови по групах:",
          {gk: gv.get("refuse", {}).get("pct") for gk, gv in data["groups"].items()})
    sp = data["shipments"]
    print("  відгрузки 1С: факт міс.", round(sum(sp["june"]) / 1000), "K | травень",
          round(sp["may_total"] / 1000), "K | план", round(sp["plan"] / 1000), "K")
    fn = data["funnel"]
    print("  CRM Секція3: спам", fn["spam_total"], "(", fn["spam"], "+", fn["dubli"],
          "дублі) | недодзвон", fn["nedodzvon"], "| втрачені ліди", fn["lost"])
    pl = fn.get("pipeline") or {}
    if pl:
        print("  Воронка(статуси): ліди", pl.get("leads_total"), "| обробка", pl.get("in_progress"),
              "| вир-во", pl.get("production"), "| відправ", pl.get("shipping"),
              "| отримано", pl.get("sale"), "| відмова", pl.get("refused"),
              "| повернення", pl.get("returned"), "| втрач.лід", pl.get("lead"),
              "| невідомі", pl.get("unknown"))
    mm = data["managers"]
    if mm and mm[0].get("conversion") is not None:
        t = mm[0]
        print("  топ-менеджер:", t["name"], "| конв", t["conversion"], "% | повернень", t["returns"])
    dr = data.get("daily_refuse") or {}
    if dr:
        print("  денні відмови:", dr["refused"], "| повернення:", dr["returned"])
    m = data["mci"]
    print("  MCI:", m["score"], m["label"], "| днів історії:", m["days"], "| кореляція:", m["corr"])
    s1 = data["sec1_orders"]["groups"]
    _s1tot = sum(sum(s1[gk]["june"]) for gk in s1)
    print("  Секція 1 (1С ORDERS): факт міс.", round(_s1tot / 1000), "K |",
          {gk: round(sum(s1[gk]["june"]) / 1000) for gk in s1},
          "| May:", {gk: round(s1[gk]["may_total"] / 1000) for gk in s1})
    s3 = data["sec3_1c"]["cards"]
    print("  Секція 3 (1С стани, замовлень):", {k: v["count"] for k, v in s3.items()})

    # ── Фаза 1 (Б): денний шар для клієнтського діапазон-двигуна ──
    dlayer = daily_layer(df, m1c_rows)
    daily_path = OUT.parent / ("daily.json" if is_current else "daily-" + target + ".json")
    daily_path.write_text(json.dumps(dlayer, ensure_ascii=False), encoding="utf-8")
    _days = sorted(int(x) for x in dlayer["day"])
    print("✅ daily.json:", daily_path, "| днів:", len(_days),
          (f"({_days[0]}–{_days[-1]})" if _days else ""),
          "| розмір:", round(daily_path.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
