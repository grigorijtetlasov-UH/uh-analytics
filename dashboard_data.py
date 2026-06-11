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

C_SITE = "Сайт"; C_MGR = "Менеджер"; C_NAME = "Назва [Товари/Послуги]"
C_QTY = "К-ть [Товари/Послуги]"; C_LSUM = "Сума [Товари/Послуги]"
C_SUM = "Сума"; C_OID = "ID замовлення"

GROUP_META = {
    "roll":    {"name": "Ролл",    "color": "#00d68f"},
    "amebli":  {"name": "Амебли",  "color": "#a29bfe"},
    "seti":    {"name": "Сети",    "color": "#339af0"},
    "roznica": {"name": "Розниця", "color": "#ffa94d"},
}


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
    o = _orders(df); o = o[o["_категорія"] == "order"]
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
    o = _orders(df); o = o[o["_категорія"] == "order"]
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
    for mgr, g in o.groupby(C_MGR):
        sold = g[g["_категорія"].isin(["order", "refused"])]
        refused = g[g["_категорія"] == "refused"]
        og = g[g["_категорія"] == "order"]
        rev = float(og[C_SUM].fillna(0).sum()); n = int(len(og))
        avg = round(rev / n) if n else 0
        refp = round(len(refused) / len(sold) * 100, 1) if len(sold) else 0.0
        res.append({"name": str(mgr), "orders": n, "revenue": round(rev),
                    "avg_check": avg, "refuse_pct": refp})
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


def daily(df):
    o = _orders(df); o = o[o["_категорія"] == "order"]
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
    o = _orders(df); o = o[o["_категорія"] == "order"].copy()
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
        po = _orders(prev); po = po[po["_категорія"] == "order"].copy()
        po["_g"] = po[C_SITE].apply(_group_of)
        for gk in GROUP_META:
            out[gk]["may"] = round(float(po[po["_g"] == gk][C_SUM].fillna(0).sum()))
    return out


def mci_bar(daily_sales):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT snapshot_date, score, label FROM mci.snapshots "
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
            "corr": corr, "days": len(vals)}


def main():
    today = date.today()
    cur_month = today.strftime("%Y-%m")
    pm = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

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
    grp = groups(df, prev, today.day)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    plans = (cfg.get("plans", {}) or {}).get(cur_month, {}) or {}
    costs = (cfg.get("costs", {}) or {}).get(cur_month, {}) or {}
    for gk in grp:
        if plans.get(gk):
            grp[gk]["plan"] = int(plans[gk])

    m1c_rows = _fetch_1c_sales(cur_month)
    pm_rows = _fetch_1c_sales(pm)                       # відгрузки минулого місяця (для порівняння)
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
    ship = shipments(m1c_rows, pm_rows, today.day)
    ship["plan"] = int((cfg.get("shipments_plan", {}) or {}).get(cur_month, 0) or 0)

    # ── лічильники Секції 3 з CRM ──
    funnel = crm_funnel(df)

    data = {
        "month": cur_month,
        "generated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "day_count": today.day,
        "channels": channels(df, prev_by_site),
        "managers": managers(df),
        "products": products(df),
        "daily": ds,
        "groups": grp,
        "costs": costs,
        "kpi": kpi,
        "shipments": ship,
        "funnel": funnel,
        "mci": mci_bar(ds),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("✅ data.json:", OUT)
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
    m = data["mci"]
    print("  MCI:", m["score"], m["label"], "| днів історії:", m["days"], "| кореляція:", m["corr"])


if __name__ == "__main__":
    main()
