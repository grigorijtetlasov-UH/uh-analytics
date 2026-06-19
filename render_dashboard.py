"""render_dashboard.py — вливає docs/data.json у шаблон v2 → docs/preview.html.
Огляд + Продажі; Маркетинг/Фінанси сховані; MCI-бар + графік Секції 1 реальні.
    cd ~/uh-analytics && venv/bin/python render_dashboard.py
"""
import json
import re
from pathlib import Path

TEMPLATE = Path("dashboard_template.html")
DATA = Path("docs/data.json")
OUT = Path("docs/preview.html")


def band(score):
    if score is None:
        return ("--td", "--s2", "даних поки нема")
    if score >= 60:
        return ("--g", "--gd", "сприятливий період для меблевого ринку")
    if score >= 40:
        return ("--o", "--od", "нейтральний період")
    return ("--r", "--rd", "обережний період — ринок під тиском")


def main():
    import sys
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    html = TEMPLATE.read_text(encoding="utf-8")
    data = json.loads(data_path.read_text(encoding="utf-8"))

    # 1) D object (channels / managers / products)
    D = {"channels": data["channels"], "managers": data["managers"], "products": data["products"]}
    html = re.sub(r"const D = \{.*?\n\};",
                  "const D = " + json.dumps(D, ensure_ascii=False) + ";",
                  html, count=1, flags=re.DOTALL)

    # 2) MCI bar — gauge / status / desc
    m = data["mci"]
    score = m["score"]
    label = m["label"] or "—"
    clr, dim, phrase = band(score)
    html = html.replace(
        '<div class="mci-pct" id="mci-value" style="color:var(--g)">78%</div>',
        '<div class="mci-pct" id="mci-value" style="color:var(' + clr + ')">' + str(score) + '%</div>')
    html = html.replace(
        '<div class="mci-status" id="mci-status" style="background:var(--gd);color:var(--g)">Сприятливий</div>',
        '<div class="mci-status" id="mci-status" style="background:var(' + dim + ');color:var(' + clr + ')">' + label + '</div>')
    corr = m.get("corr")
    if corr is None:
        corr_txt = "накопичується (<b>" + str(m.get("days", 0)) + " дн.</b>)"
    else:
        corr_txt = "<b>" + ("+" if corr >= 0 else "") + str(corr) + "</b>"
    _when = ("Станом на <b>" + m["date"] + "</b> — <b>" + str(score) + "%</b>") if m.get("date") else ("Поточний бал <b>" + str(score) + "%</b>")
    desc = ("<b>Market Conditions Index</b> — композитний індекс ринкових умов "
            "(макро + сезон + воєнні фактори). " + _when + ", " + phrase +
            ". Кореляція з продажами " + corr_txt + ".")
    html = re.sub(r'(<div class="mci-desc">\s*).*?(\s*</div>)',
                  lambda mt: mt.group(1) + desc + mt.group(2), html, count=1, flags=re.DOTALL)

    # 3) MCI chart arrays
    html = re.sub(r"const mciLabels=[^\n]*;",
                  "const mciLabels=" + json.dumps(m["labels"], ensure_ascii=False) + ";", html, count=1)
    html = re.sub(r"const mciVals=[^\n]*;",
                  "const mciVals=" + json.dumps(m["mci"]) + ";", html, count=1)
    html = re.sub(r"const mciSales=[^\n]*;",
                  "const mciSales=" + json.dumps(m["sales"]) + ";", html, count=1)

    # 4) Section-1 groups → CH (Факт/Минулий/Тренд реальні)
    g = data.get("groups")
    if g:
        CH = {k: {"name": v["name"], "color": v["color"], "june": v["june"],
                  "may": v["may"], "plan": v["plan"]} for k, v in g.items()}
        html = re.sub(r"const CH = \{.*?\n\};",
                      "const CH = " + json.dumps(CH, ensure_ascii=False) + ";",
                      html, count=1, flags=re.DOTALL)
        # CHO — Секція 1 (Огляд) з 1С ORDERS: june/may з 1С; назва/колір/план — з CRM-груп, а для Софіно/Інше — свої
        so = (data.get("sec1_orders") or {}).get("groups") or {}
        if so:
            _ometa = {"sofino": ("Софіно", "#ff6b9d"), "other": ("Інше", "#9aa0b5")}
            CHO = {}
            for gk, grp in so.items():
                if gk in g:
                    nm, col, pl = g[gk]["name"], g[gk]["color"], int(g[gk].get("plan") or 0)
                else:
                    nm, col = _ometa.get(gk, (gk, "#9aa0b5")); pl = 0
                CHO[gk] = {"name": nm, "color": col, "june": grp.get("june", []),
                           "may": grp.get("may_total", 0), "plan": pl}
            html = html.replace("const CHO = CH;",
                                "const CHO = " + json.dumps(CHO, ensure_ascii=False) + ";", 1)
        if not any(v.get("plan") for v in g.values()):
            html = re.sub(r"\s*\{label:'План',data:planLine,[^}]*\},", "", html, count=1)

    # 4a2) Секція 3 — дані 1С-режиму (стани + денні відмови/повернення)
    s3_1c = data.get("sec3_1c")
    if s3_1c:
        html = html.replace("window.SEC3_1C=null;",
                            "window.SEC3_1C=" + json.dumps(s3_1c, ensure_ascii=False) + ";", 1)

    # 4a3) Маркетинг — реальний обʼєкт у MKT (фолбек у шаблоні = мок у initMktCharts)
    mkt = data.get("marketing")
    if mkt:
        html = html.replace("const MKT = null;",
                            "const MKT = " + json.dumps(mkt, ensure_ascii=False) + ";", 1)

    rep = data.get("reputation")
    if rep:
        html = html.replace("const REP = null;",
                            "const REP = " + json.dumps(rep, ensure_ascii=False) + ";", 1)

    # 4a4) Callider — AI-дзвінки (окремий docs/callaider.json, не в data.json)
    cal_path = Path("docs/callaider.json")
    if cal_path.exists():
        try:
            cal = json.loads(cal_path.read_text(encoding="utf-8"))
            html = html.replace("const CALLAIDER = null;",
                                "const CALLAIDER = " + json.dumps(cal, ensure_ascii=False) + ";", 1)
            print("  ✓ Callider:", (cal.get("totals") or {}).get("calls", 0), "дзвінків")
        except Exception as e:
            print("  ⚠ callaider.json:", e)

    # 4b) реальний середній чек у бренди (BRANDS[].avg ← groups[].avg)
    if g:
        for gk, gv in g.items():
            if gv.get("avg"):
                html = re.sub(r"(ch:'" + gk + r"',avg:)\d+", r"\g<1>" + str(gv["avg"]), html, count=1)

    # 4c) захист «виконання плану» від ділення на нуль (план не заданий → «—»)
    html = html.replace("(proj/planTotal*100).toFixed(0)",
                        "(planTotal>0?(proj/planTotal*100).toFixed(0):'—')")
    html = html.replace("((proj/planTotal)*100).toFixed(0)",
                        "(planTotal>0?((proj/planTotal)*100).toFixed(0):'—')")

    # 4d) реальні категорії/маржа з 1С → REAL_CATS + перемикаємо джерело cats
    if g:
        real_cats = {}
        for gk, gv in g.items():
            cs = gv.get("cats")
            if not cs:
                continue
            fixed = []
            for c in cs:
                c = dict(c)
                cov = c.get("cov", 1)
                if c.get("m") is None:          # зовсім нема собівартості → маржа невідома
                    c["m"] = c["mp"] = 0
                    c["n"] = c["n"] + " ⚠нд"
                elif cov < 0.7:                 # часткова собівартість → маржі не вірити
                    c["n"] = c["n"] + " ⚠"
                fixed.append(c)
            real_cats[gk] = fixed
        if real_cats:
            html = html.replace(
                "window._brandProd={};",
                "window._brandProd={};\nconst REAL_CATS = " + json.dumps(real_cats, ensure_ascii=False) + ";")
            html = html.replace(
                "const cats=b.cats.map(c=>({...c,rev:Math.round(actual*c.share)}));",
                "const cats=(window.REAL_CATS&&REAL_CATS[b.ch]&&REAL_CATS[b.ch].length)"
                "?REAL_CATS[b.ch]:b.cats.map(c=>({...c,rev:Math.round(actual*c.share)}));")
            html = html.replace("const dom=b.cats[0].m;", "const dom=cats[0].m;")

    # 5) Позначаємо ненаповнені вкладки «в розробці» (наповнюємо по черзі реальними даними)
    wip_tabs = [
        ">🛒 Корзина & ціноутворення</button>",
        ">🧠 IRIS</button>",
        ">📈 Фінанси P&L</button>",
    ]
    for t in wip_tabs:
        html = html.replace(t, t.replace("</button>", '<sup class="wip">в розробці</sup></button>'), 1)

    # 6) Канонічні відмови з 1С → Секція 3 (всього + Matrasroll + Amebli)
    rf = (data.get("kpi") or {}).get("refuse") or {}
    grp_data = data.get("groups") or {}

    def _gref(gk):
        r = (grp_data.get(gk) or {}).get("refuse") or {}
        return r.get("pct", 0), r.get("refused", 0), r.get("sold", 0)

    if rf.get("active"):
        html = html.replace(
            '<div class="kpi c2"><div class="kl">Відмови всього</div><div class="kv" style="color:var(--g)">2.6<span class="ku">%</span></div><div class="ks">15 з 573 · було 50% <span class="dlt up">−47пп</span></div></div>',
            '<div class="kpi c2"><div class="kl">Відмови всього</div><div class="kv" style="color:var(--g)">'
            + str(rf["of_orders"]) + '<span class="ku">%</span></div><div class="ks">'
            + str(rf["refused"]) + ' з ' + str(rf["active"]) + ' · 1С відгрузки</div></div>')
        pr, rr, sr = _gref("roll")
        html = html.replace(
            '<div class="kpi c2"><div class="kl">Відмови Matrasroll</div><div class="kv">2.6<span class="ku">%</span></div><div class="ks">13 замовлень</div></div>',
            '<div class="kpi c2"><div class="kl">Відмови Matrasroll</div><div class="kv">'
            + str(pr) + '<span class="ku">%</span></div><div class="ks">'
            + str(rr) + ' з ' + str(sr) + ' зам.</div></div>')
        pa, ra, sa = _gref("amebli")
        html = html.replace(
            '<div class="kpi c2"><div class="kl">Відмови Amebli</div><div class="kv">2.2<span class="ku">%</span></div><div class="ks">5 замовлень</div></div>',
            '<div class="kpi c2"><div class="kl">Відмови Amebli</div><div class="kv">'
            + str(pa) + '<span class="ku">%</span></div><div class="ks">'
            + str(ra) + ' з ' + str(sa) + ' зам.</div></div>')

    # 7) Відгрузки (Секція 4) з 1С SALES → реальні shipJune / shipMay / shipPlan
    sh = data.get("shipments") or {}
    if sh.get("june"):
        html = re.sub(r"const shipJune=\[[^\]]*\];",
                      "const shipJune=" + json.dumps(sh["june"]) + ";", html, count=1)
        html = re.sub(r"const shipMay=rampDaily\(\d+\),",
                      "const shipMay=rampDaily(" + str(sh.get("may_total", 0)) + "),", html, count=1)
        plan = int(sh.get("plan", 0) or 0)
        html = re.sub(r"const shipPlan=\d+,", "const shipPlan=(window.PLAN_SHIP!=null?window.PLAN_SHIP:" + str(plan) + "),", html, count=1)
        html = html.replace("const shipPlanPct=((shipProj/shipPlan)*100).toFixed(0);",
                            "const shipPlanPct=(shipPlan>0?((shipProj/shipPlan)*100).toFixed(0):'—');")
        if plan <= 0:   # плану нема → ховаємо лінію плану
            html = re.sub(r"\s*\{label:'План',data:shipLabels\.map\(\(\)=>shipPlanDaily\),[^}]*\},",
                          "", html, count=1)

    # 8) Секція 2 (Маркетинг/ДРР) — ТЕПЕР показуємо: KPI-картки + тренд завʼязані на MKT у JS
    #    (AI-блок усередині лишається схований глобальним .ai-block{display:none})

    # 9) Секція 3 — реальні лічильники з CRM (спам / недодзвон / втрачені ліди)
    fn = data.get("funnel") or {}
    if fn:
        html = html.replace(
            '<div class="kpi c3"><div class="kl">Повернення</div><div class="kv">~1.8<span class="ku">%</span></div><div class="ks">оцінка по відгрузках</div></div>',
            '<div class="kpi c3"><div class="kl">Втрачені ліди</div><div class="kv">'
            + str(fn.get("lost", 0)) + '</div><div class="ks">«Лід (не купив)»</div></div>')
        html = html.replace(
            '<div class="kpi c7"><div class="kl">Спам / дублі</div><div class="kv">236</div><div class="ks">221 спам + 15 дублів</div></div>',
            '<div class="kpi c7"><div class="kl">Спам / дублі</div><div class="kv">'
            + str(fn.get("spam_total", 0)) + '</div><div class="ks">'
            + str(fn.get("spam", 0)) + ' спам + ' + str(fn.get("dubli", 0)) + ' дублі</div></div>')
        html = html.replace(
            '<div class="kpi c4"><div class="kl">Недодзвон</div><div class="kv">51</div><div class="ks">потребує обробки</div></div>',
            '<div class="kpi c4"><div class="kl">Недодзвон</div><div class="kv">'
            + str(fn.get("nedodzvon", 0)) + '</div><div class="ks">потребує обробки</div></div>')

    # 10) Стилі: ховаємо статичні AI-висновки + бейдж «в розробці»
    html = html.replace(
        "</head>",
        "<style>.ai-block{display:none}"
        ".wip{font-size:7px;color:#ffa94d;vertical-align:super;margin-left:4px;"
        "opacity:.85;letter-spacing:.2px;font-weight:700;text-transform:uppercase}"
        "</style>\n</head>", 1)

    # 11) Продажі — реальний headline KPI-рядок (панель «Всі»)
    import calendar as _cal
    gg = data.get("groups") or {}
    kp = data.get("kpi") or {}
    if gg:
        obsyag = sum(sum(v.get("june", [])) for v in gg.values())
        orders = sum(v.get("orders", 0) for v in gg.values())
        avg = round(obsyag / orders) if orders else 0
        mnum = sum(sum(v.get("june", [])) * v["margin"] for v in gg.values() if v.get("margin") is not None)
        mden = sum(sum(v.get("june", [])) for v in gg.values() if v.get("margin") is not None)
        margin = round(mnum / mden) if mden else 0
        dc = data.get("day_count", 1) or 1
        try:
            yy, mm = data.get("month", "2026-06").split("-")
            dim = _cal.monthrange(int(yy), int(mm))[1]
        except Exception:
            dim = 30
        proj = round(obsyag / dc * dim) if dc else obsyag
        conv = (kp.get("conversion") or {}).get("value", 0)

        def _sp(n):
            return f"{int(n):,}".replace(",", " ")

        def _kv(label_pat, value, tail):
            nonlocal html
            html = re.sub(label_pat + r'(<div class="kv"[^>]*>)[^<]*(' + tail + r')',
                          r'\g<1>\g<2>' + str(value) + r'\g<3>', html, count=1)

        _kv(r'(<div class="kl">Обсяг продажів[^<]*</div>)', f"{obsyag / 1e6:.1f}M", r'<span class="ku">')
        _kv(r'(<div class="kl">Замовлень</div>)', _sp(orders), r'</div>')
        _kv(r'(<div class="kl">Середній чек</div>)', _sp(avg), r'<span class="ku">')
        _kv(r'(<div class="kl">Маржинальність</div>)', margin, r'<span class="ku">')
        _kv(r'(<div class="kl">Прогноз місяць</div>)', f"{proj / 1e6:.1f}M", r'<span class="ku">')
        _kv(r'(<div class="kl">Конверсія лід→зам</div>)', conv, r'<span class="ku">')
        html = html.replace("Обсяг продажів (1–25)", "Обсяг продажів", 1)

    # 12) Реальні дати: хедер-підзаголовок + мітки «факт 1–N» + кнопки періоду
    dc = data.get("day_count", 0) or 0
    today_str = (data.get("generated", "") or "").split(" ")[0]
    MON_GEN = {"01": "січня", "02": "лютого", "03": "березня", "04": "квітня",
               "05": "травня", "06": "червня", "07": "липня", "08": "серпня",
               "09": "вересня", "10": "жовтня", "11": "листопада", "12": "грудня"}
    mon = MON_GEN.get(data.get("month", "2026-06").split("-")[1], "")
    if dc:
        if today_str:
            html = re.sub(r"Дані за 1[–-]\d+ числа · Оновлено \d{2}\.\d{2}\.\d{4}",
                          f"Дані за 1–{dc} числа · Оновлено {today_str}", html, count=1)
        html = re.sub(r"факт 1[–-]\d+:", f"факт 1–{dc}:", html)
        if mon:
            html = re.sub(r"1[–-]\d+ " + mon, f"1–{dc} {mon}", html)

    # 13) Продажі «Всі» + воронка: реальні дані замість демо
    gg = data.get("groups") or {}
    pl = (data.get("funnel") or {}).get("pipeline") or {}

    # 13a) агрегат категорій з groups[].cats (зважена маржа/coverage)
    agg = {}
    for gv in gg.values():
        for c in (gv.get("cats") or []):
            base = c["n"].split(" ⚠")[0]
            a = agg.setdefault(base, {"rev": 0.0, "crev": 0.0, "cost": 0.0, "acn": 0.0})
            rev = c.get("rev", 0) or 0
            cov = c.get("cov", 0) or 0
            mg = c.get("m")
            a["rev"] += rev
            if mg is not None and cov > 0:
                cr = rev * cov
                a["crev"] += cr
                a["cost"] += cr * (1 - mg / 100.0)
            a["acn"] += (c.get("ac", 0) or 0) * rev
    agg_list = []
    for base, a in agg.items():
        if a["rev"] <= 0:
            continue
        if a["crev"] > 0:
            mg = round((a["crev"] - a["cost"]) / a["crev"] * 100, 1)
            covf = a["crev"] / a["rev"]
            nm = base if covf >= 0.7 else base + " ⚠"
        else:
            mg = 0; nm = base + " ⚠нд"
        ac = round(a["acn"] / a["rev"]) if a["rev"] else 0
        agg_list.append({"n": nm, "rev": round(a["rev"]), "m": mg, "mp": mg, "ac": ac, "acp": ac})
    agg_list.sort(key=lambda x: -x["rev"])

    # 13b) інжект FUNNEL_REAL + AGG_CATS
    inj = ""
    if pl:
        inj += "\nconst FUNNEL_REAL = " + json.dumps(pl, ensure_ascii=False) + ";"
    if agg_list:
        inj += "\nconst AGG_CATS = " + json.dumps(agg_list, ensure_ascii=False) + ";"
    rd = data.get("daily_refuse") or {}
    if rd:
        inj += "\nconst REF_DAILY = " + json.dumps(rd, ensure_ascii=False) + ";"
    if inj:
        html = html.replace("window._brandProd={};", "window._brandProd={};" + inj, 1)

    # 13c) воронка «Всі» — реальні стадії зі статусів
    if pl:
        real_stages = (
            "const stages=[\n"
            "    {n:'📥 Всього лідів',v:FUNNEL_REAL.leads_total,c:'#339af0'},\n"
            "    {n:'⚙️ В обробці',v:FUNNEL_REAL.in_progress,c:'#4dabf7'},\n"
            "    {n:'🏭 У виробництві',v:FUNNEL_REAL.production,c:'#a29bfe'},\n"
            "    {n:'🚚 Відправлення',v:FUNNEL_REAL.shipping,c:'#9775fa'},\n"
            "    {n:'🎁 Отримано',v:FUNNEL_REAL.sale,c:'#94d82d'},\n"
            "    {n:'🚫 Відмова',v:FUNNEL_REAL.refused,c:'#ff6b6b'},\n"
            "    {n:'↩️ Повернення',v:FUNNEL_REAL.returned,c:'#ff8787'},\n"
            "    {n:'😴 Втрачені ліди',v:FUNNEL_REAL.lead,c:'#ffd43b'}\n"
            "  ];")
        html = re.sub(r"const stages=\[\s*\{n:'📥 Всього лідів',v:660,.*?\];",
                      real_stages, html, count=1, flags=re.DOTALL)
        conv_v = (data.get("kpi") or {}).get("conversion", {}).get("value", 0)
        ref_v = (data.get("kpi") or {}).get("refuse", {}).get("of_orders", 0)
        lt = pl.get("leads_total") or 1
        ret_pct = round(pl.get("returned", 0) / lt * 100, 1)
        html = re.sub(
            r"Конв\. лід→продаж: <b[^>]*>[^<]*</b> · Відмов: <b[^>]*>[^<]*</b> · Повернень[^<]*<b[^>]*>[^<]*</b>",
            ("Конв. лід→продаж: <b style=\"color:#00d68f\">" + str(conv_v) + "%</b> · "
             "Відмов: <b style=\"color:#ff6b6b\">" + str(ref_v) + "%</b> · "
             "Повернень: <b style=\"color:#ff8787\">" + str(ret_pct) + "%</b>"),
            html, count=1)

    # 13d) категорії «Всі» → AGG_CATS (замість хардкоду Матраци 18M)
    if agg_list:
        html = re.sub(r"const cats=\[\s*\{n:'Матраци',rev:18000000,.*?\];",
                      "const cats=AGG_CATS;", html, count=1, flags=re.DOTALL)

    # 13e) продавці — реальні конв/повернення (обидва рендери)
    html = html.replace("const conv=m.orders? Math.min(95, 80+((m.orders*7)%14)) : 0;",
                        "const conv=(m.conversion!=null?m.conversion:0);")
    html = html.replace("const returns=Math.round(m.orders*0.018);",
                        "const returns=(m.returns!=null?m.returns:0);")
    html = html.replace("const conv=Math.min(95,80+((m.orders*7)%14));const returns=Math.round(ord*0.018);",
                        "const conv=(m.conversion!=null?m.conversion:0);const returns=(m.returns!=null?m.returns:0);")

    # 13f) ТОП-10 маржа → реальна маржа категорії
    html = html.replace(
        "const catMargin=n=>/матрас|матрац|cocos|handy|foam|orange|smart|family|chocolate|cacao|tiramisu|soft/i.test(n)?44:/топер|топпер|bionica|purple|base/i.test(n)?40:/диван|крісло|voss/i.test(n)?33:/ліжко|шафа|новелти|homefort|ridnetut johnson/i.test(n)?28:35;",
        "const _CM=(typeof AGG_CATS!=='undefined')?Object.fromEntries(AGG_CATS.map(c=>[c.n.split(' ⚠')[0],c.m])):{};"
        "const catMargin=n=>/матрас|матрац|cocos|handy|foam|orange|smart|family|chocolate|cacao|tiramisu|soft/i.test(n)?(_CM['Матраци']||0):"
        "/топер|топпер|bionica|purple|base/i.test(n)?(_CM['Топери']||0):"
        "/диван|крісло|voss/i.test(n)?(_CM[\"М'які меблі\"]||0):"
        "/ліжко|шафа|новелти|homefort/i.test(n)?(_CM['Корпусні']||0):(_CM['Інше']||0);")

    # 13g) KPI-підписи «Всі» — прибрати статичні дельти, лишити реальне
    if gg:
        orders_all = sum(v.get("orders", 0) for v in gg.values())
        per_day = round(orders_all / dc) if dc else 0
        html = html.replace('<div class="ks">~208 зам/день</div>',
                            '<div class="ks">~' + str(per_day) + ' зам/день</div>')
        html = re.sub(r'<div class="ks"><span class="dlt down">[^<]*</span> vs 7\s?371₴</div>',
                      '<div class="ks">за 1–' + str(dc) + ' ' + mon + '</div>', html, count=1)
        html = re.sub(r'<div class="ks"><span class="dlt down">[^<]*</span> vs 46%</div>',
                      '<div class="ks">по 1С-собівартості</div>', html, count=1)
        html = re.sub(r'<div class="ks">факт червня · <span class="dlt up">[^<]*</span></div>',
                      '<div class="ks">факт за 1–' + str(dc) + ' ' + mon + '</div>', html, count=1)

    # 13h) «23 активних» → реальна к-ть менеджерів
    html = html.replace('<span class="btot">23 активних</span>',
                        '<span class="btot">' + str(len(data.get("managers", []))) + ' активних</span>')

    # 13i) мітка «(1–25)» у підписі денного графіка
    if dc:
        html = re.sub(r"\(1[–-]25\)", "(1–" + str(dc) + ")", html)

    # 13j) Секція-3 денний графік — реальні денні відмови/повернення (CRM по днях)
    if rd:
        html = html.replace("data:[2,5,5,4,4,3,5,4,3,2,1,3,2,2,1,1,5,4,4,4,3,6,5,3,2]", "data:REF_DAILY.refused")
        html = html.replace("data:[2,3,3,4,2,2,2,3,0,1,1,2,0,1,2,3,1,2,3,4,2,3,3,4,2]", "data:REF_DAILY.returned")
        html = re.sub(r"data:\[1\.1,2\.5,2\.3,.*?\],borderColor:'#66d9e8'",
                      "data:REF_DAILY.pct,borderColor:'#66d9e8'", html, count=1)
        html = re.sub(r"data:\{labels:dayL,datasets:\[\s*\{label:'Відмови \(шт\)'",
                      "data:{labels:REF_DAILY.days,datasets:[\n      {label:'Відмови (шт)'", html, count=1)
    else:
        html = html.replace(".ai-block{display:none}", ".ai-block{display:none}#ch-sec3{display:none}")

    # 14) Блок «Діагностика даних» угорі Огляду — звірка джерел + автоперевірки
    kp = data.get("kpi") or {}
    plp = (data.get("funnel") or {}).get("pipeline") or {}
    shp = data.get("shipments") or {}
    mci = data.get("mci") or {}

    def _mln(n):
        return f"{(n or 0) / 1e6:.1f}M"

    def _spc(n):
        return f"{int(n or 0):,}".replace(",", " ")

    d_obsyag = sum(sum(v.get("june", [])) for v in gg.values())
    d_orders = sum(v.get("orders", 0) for v in gg.values())
    d_avg = round(d_obsyag / d_orders) if d_orders else 0
    d_mnum = sum(sum(v.get("june", [])) * v["margin"] for v in gg.values() if v.get("margin") is not None)
    d_mden = sum(sum(v.get("june", [])) for v in gg.values() if v.get("margin") is not None)
    d_margin = round(d_mnum / d_mden) if d_mden else 0
    d_conv = (kp.get("conversion") or {}).get("value", 0)
    rfz = kp.get("refuse") or {}
    leads = plp.get("leads_total", 0)
    stg = ("in_progress", "production", "shipping", "sale", "refused", "returned", "lead", "claim")
    stage_sum = sum(plp.get(k, 0) for k in stg)
    ship_fact = sum(shp.get("june", []) or [])
    ship_plan = shp.get("plan", 0) or 0
    cov_ok = all((v.get("coverage") or 0) >= 0.7 for v in gg.values() if v.get("margin") is not None)

    def _badge(ok, warn=False, wip=False):
        if wip:
            return '<span style="color:#ffa94d;font-weight:600">🔧 в розробці</span>'
        if warn:
            return '<span style="color:#ffd43b;font-weight:600">⚠ оцінка</span>'
        return ('<span style="color:#00d68f;font-weight:600">✅ реальне</span>' if ok
                else '<span style="color:#ff6b6b;font-weight:600">❌ перевір</span>')

    d_rows = [
        ("Обсяг продажів", _mln(d_obsyag) + "₴", "CRM · факт по групах", _badge(True)),
        ("Замовлень", _spc(d_orders), "CRM · унік. ID", _badge(True)),
        ("Середній чек", _spc(d_avg) + "₴", "CRM", _badge(True)),
        ("Маржинальність", str(d_margin) + "%", "1С · собівартість", _badge(cov_ok, warn=not cov_ok)),
        ("Конверсія лід→зам", str(d_conv) + "%", "CRM · статуси", _badge(True)),
        ("Воронка — лідів", _spc(leads), "CRM · статуси (знімок)", _badge(True)),
        ("Відмови", f"{rfz.get('of_orders', 0)}% ({rfz.get('refused', 0)}/{rfz.get('active', 0)})",
         "1С · СостояниеЗаказа", _badge(True)),
        ("Відгрузки — факт", _mln(ship_fact) + "₴", "1С · SALES", _badge(True)),
        ("Відгрузки — план", (_mln(ship_plan) + "₴") if ship_plan else "не задано",
         "manual_config.json", _badge(ship_plan > 0, wip=ship_plan <= 0)),
        ("Категорії (маржа)", f"{len(agg_list)} кат.", "1С · агрегат груп", _badge(bool(agg_list))),
        ("Продавці: конв/поверн", f"{len(data.get('managers', []))} ос.", "CRM · статуси", _badge(True)),
        ("MCI індекс", f"{mci.get('score')} {mci.get('label') or ''}", "mci schema", _badge(mci.get("score") is not None)),
        ("Маркетинг / ДРР", "нема джерела витрат", "—", _badge(False, wip=True)),
        ("Денний графік відмов (Огляд)", "по днях", "CRM · дата замовлення", _badge(bool(data.get("daily_refuse")))),
    ]
    d_tbody = "".join(
        f'<tr><td style="padding:3px 8px">{r[0]}</td>'
        f'<td style="padding:3px 8px;font-weight:600">{r[1]}</td>'
        f'<td style="padding:3px 8px;color:#7b84a3">{r[2]}</td>'
        f'<td style="padding:3px 8px">{r[3]}</td></tr>' for r in d_rows)
    chk = "✅" if leads == stage_sum else f"❌ ({stage_sum}≠{leads})"
    covs = " · ".join(f"{k} {int((v.get('coverage') or 0) * 100)}%"
                      for k, v in gg.items() if "coverage" in v)
    d_checks = (f"Автоперевірки: воронка Σстадій={stage_sum} vs ліди={leads} {chk}"
                f" · спам поза лідами={plp.get('spam', 0)} · невідомі статуси={plp.get('unknown', 0)}"
                f" · coverage собівартості: {covs}")
    diag = (
        '<details style="margin-bottom:16px;background:rgba(102,217,232,.05);'
        'border:1px solid rgba(102,217,232,.22);border-radius:10px;padding:10px 14px">'
        '<summary style="cursor:pointer;font-weight:700;color:#66d9e8;font-size:13px">'
        f'🩺 Діагностика даних — джерела і перевірки · дані 1–{dc} {mon}, оновлено {data.get("generated", "")}'
        '</summary>'
        '<div style="margin-top:10px;overflow-x:auto">'
        '<table style="width:100%;border-collapse:collapse;font-size:11.5px">'
        '<thead><tr style="color:#7b84a3;text-align:left;border-bottom:1px solid rgba(255,255,255,.08)">'
        '<th style="padding:4px 8px">Блок</th><th style="padding:4px 8px">Значення</th>'
        '<th style="padding:4px 8px">Джерело</th><th style="padding:4px 8px">Статус</th></tr></thead>'
        f'<tbody>{d_tbody}</tbody></table>'
        f'<div style="margin-top:8px;color:#7b84a3;font-size:10.5px;line-height:1.6">{d_checks}</div>'
        '</div></details>')
    html = html.replace('<div class="mpnl on" id="mp-overview">',
                        '<div class="mpnl on" id="mp-overview">\n' + diag, 1)

    # 15) Блок «Плани місяця» — поля плану + генерація JSON для manual_config.json
    pm_key = data.get("month", "")
    grp_plan_rows = ""
    for gk in gg:
        nm = gg[gk].get("name", gk)
        pv = int(gg[gk].get("plan") or 0)
        grp_plan_rows += (
            '<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
            '<span style="width:90px;color:#c1c7e0">' + nm + '</span>'
            '<input data-pg="' + gk + '" type="number" value="' + str(pv) + '" '
            'style="width:150px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);'
            'border-radius:6px;color:#fff;padding:5px 8px;font-size:12px">'
            '<span style="color:#7b84a3;font-size:11px">₴</span></div>')
    ship_plan_cur = int((data.get("shipments") or {}).get("plan") or 0)
    plan_script = (
        '<script>function genPlanJSON(){'
        'var m="' + pm_key + '";'
        'var plans={};document.querySelectorAll("[data-pg]").forEach(function(i){plans[i.dataset.pg]=Number(i.value)||0;});'
        'var sp=Number(document.getElementById("planShip").value)||0;'
        'var o={plans:{},shipments_plan:{}};o.plans[m]=plans;o.shipments_plan[m]=sp;'
        'var t=document.getElementById("planOut");t.value=JSON.stringify(o,null,2);t.style.display="block";'
        't.select();try{document.execCommand("copy");}catch(e){}'
        '}'
        'function applyPlansLive(){'
        'var m="' + pm_key + '";'
        'var plans={};document.querySelectorAll("[data-pg]").forEach(function(i){plans[i.dataset.pg]=Number(i.value)||0;});'
        'var sp=Number(document.getElementById("planShip").value)||0;'
        'try{localStorage.setItem("iris_plans_"+m,JSON.stringify({plans:plans,ship:sp}));}catch(e){}'
        'location.reload();'
        '}'
        'function resetPlansLive(){'
        'var m="' + pm_key + '";try{localStorage.removeItem("iris_plans_"+m);}catch(e){}location.reload();'
        '}</script>')
    plan_block = (
        '<details style="margin-bottom:16px;background:rgba(165,155,254,.05);'
        'border:1px solid rgba(165,155,254,.25);border-radius:10px;padding:10px 14px">'
        '<summary style="cursor:pointer;font-weight:700;color:#a29bfe;font-size:13px">'
        '📋 Плани місяця (' + pm_key + ') — заповнення</summary>'
        '<div style="margin-top:10px;font-size:12px">'
        '<div style="color:#7b84a3;margin-bottom:6px">План продажів по групах:</div>'
        + grp_plan_rows +
        '<div style="display:flex;align-items:center;gap:8px;margin:10px 0 4px">'
        '<span style="width:90px;color:#c1c7e0">План відгрузок</span>'
        '<input id="planShip" type="number" value="' + str(ship_plan_cur) + '" '
        'style="width:150px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);'
        'border-radius:6px;color:#fff;padding:5px 8px;font-size:12px">'
        '<span style="color:#7b84a3;font-size:11px">₴</span></div>'
        '<button onclick="applyPlansLive()" style="margin-top:10px;margin-right:8px;background:#00d68f;color:#08240f;'
        'border:none;border-radius:7px;padding:7px 14px;font-weight:700;cursor:pointer;font-size:12px">✅ Застосувати на дашборді</button>'
        '<button onclick="resetPlansLive()" style="margin-top:10px;margin-right:8px;background:rgba(255,255,255,.08);color:#c1c7e0;'
        'border:1px solid rgba(255,255,255,.15);border-radius:7px;padding:7px 14px;font-weight:600;cursor:pointer;font-size:12px">↺ Серверні плани</button>'
        '<button onclick="genPlanJSON()" style="margin-top:10px;background:#a29bfe;color:#1a1a2e;'
        'border:none;border-radius:7px;padding:7px 14px;font-weight:600;cursor:pointer;font-size:12px">'
        'Згенерувати JSON (копіюється)</button>'
        '<div style="color:#7b84a3;font-size:10.5px;margin-top:8px">'
        '<b style="color:#00d68f">Застосувати на дашборді</b> — одразу (зберігається у браузері). '
        '<b>Згенерувати JSON</b> — для постійного збереження: онови <b>plans</b>/<b>shipments_plan</b> у '
        '<b>data/manual_config.json</b> на сервері → перезапусти пайплайн. '
        '<b>↺ Серверні плани</b> — скинути локальні й показати серверні.</div>'
        '<textarea id="planOut" readonly style="display:none;width:100%;height:160px;margin-top:8px;'
        'background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.12);border-radius:7px;color:#9ae6b4;'
        'padding:8px;font-family:monospace;font-size:11px"></textarea>'
        '</div></details>' + plan_script)
    html = html.replace('<div class="mpnl on" id="mp-overview">',
                        '<div class="mpnl on" id="mp-overview">\n' + plan_block, 1)

    # 16) Графіки — реальні дні місяця + «минулий місяць» рівним середнім/день (не синтетичний шейп)
    import calendar as _cal2
    try:
        _yy, _mm = data.get("month", "2026-06").split("-")
        dim2 = _cal2.monthrange(int(_yy), int(_mm))[1]
    except Exception:
        dim2 = 30
    _plan_override = ("\ntry{var _pl=JSON.parse(localStorage.getItem('iris_plans_" + str(data.get("month", "")) + "')||'null');"
                      "if(_pl){if(_pl.plans){for(var _g in _pl.plans){var _pv=_pl.plans[_g];"
                      "if(typeof CH!=='undefined'&&CH[_g])CH[_g].plan=_pv;"
                      "if(typeof CHO!=='undefined'&&CHO[_g])CHO[_g].plan=_pv;}}"
                      "if(_pl.ship!=null)window.PLAN_SHIP=_pl.ship;}}catch(e){}")
    html = html.replace("const O_DIM=30, O_ACT=4, O_FULL=3;",
                        "const O_DIM=" + str(dim2) + ", O_ACT=" + str(dc) + ", O_FULL=" + str(dc) + ";" + _plan_override)
    html = re.sub(
        r"function rampDaily\(monthly\)\{.*?return w\.map\(x=>Math\.round\(monthly\*x/ws\)\);\s*\}",
        "function rampDaily(monthly){const d=Math.round(monthly/O_DIM);return Array.from({length:O_DIM},()=>d);}",
        html, count=1, flags=re.DOTALL)
    html = html.replace("Минулий місяць (факт)", "Минулий місяць (сер./день)")

    # 17) Go-live перших 2 сторінок: сховати 5 вкладок «в розробці» + фейкову per-brand воронку
    html = html.replace(
        ".ai-block{display:none}",
        ".ai-block{display:none}"
        ".mtab:has(.wip){display:none!important}"
        '.cd:has([id$="-funnel"]){display:none!important}')

    # 18) Робочий перемикач періоду: навігація між сторінками місяців.
    #     Поточний → index.html; минулі → dash-YYYY-MM.html.
    from datetime import date as _date, timedelta as _td
    _today = _date.today()
    _cur = _today.strftime("%Y-%m")
    _p1d = _date(_today.year, _today.month, 1) - _td(days=1)
    _p1 = _p1d.strftime("%Y-%m")
    _p2 = (_date(_p1d.year, _p1d.month, 1) - _td(days=1)).strftime("%Y-%m")
    pages = {"current": "index.html",
             _p1: "dash-" + _p1 + ".html",
             _p2: "dash-" + _p2 + ".html"}
    this_month = data.get("month", _cur)
    sel = "current" if this_month == _cur else this_month

    # динамічні опції періоду (value+label) під фактичні місяці + прибрати неробочі
    MON_UA = {1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень", 5: "Травень",
              6: "Червень", 7: "Липень", 8: "Серпень", 9: "Вересень", 10: "Жовтень",
              11: "Листопад", 12: "Грудень"}

    def _mlabel(ym):
        return MON_UA[int(ym[5:7])] + " " + ym[:4]

    html = html.replace('<option value="current">Червень 2026 (поточний)</option>',
                        '<option value="current">' + _mlabel(_cur) + ' (поточний)</option>')
    html = html.replace('<option value="2026-05">Травень 2026</option>',
                        '<option value="' + _p1 + '">' + _mlabel(_p1) + '</option>')
    html = html.replace('<option value="2026-04">Квітень 2026</option>',
                        '<option value="' + _p2 + '">' + _mlabel(_p2) + '</option>')
    # лишаємо custom/last7/last30 для режиму діапазону; прибираємо лише березень (нема даних)
    html = html.replace('<option value="2026-03">Березень 2026</option>', "")

    nav = ("\n<script>(function(){\n"
           "  window.MONTH_PAGES=" + json.dumps(pages, ensure_ascii=False) + ";\n"
           "  var SEL=" + json.dumps(sel) + ";\n"
           "  window.applyGlobalPeriod=function(){\n"
           "    var p=document.getElementById('globalPeriod'); if(!p) return;\n"
           "    var v=p.value;\n"
           "    if(v==='custom'||v==='last7'||v==='last30'){ if(window.IRISApplyRange) window.IRISApplyRange(v); return; }\n"
           "    if(window.IRISExitRange) window.IRISExitRange();\n"
           "    var dest=window.MONTH_PAGES[v];\n"
           "    if(dest && v!==SEL){location.href=dest;}\n"
           "  };\n"
           "  document.addEventListener('DOMContentLoaded',function(){\n"
           "    var p=document.getElementById('globalPeriod');\n"
           "    if(p){try{p.value=SEL;}catch(e){}}\n"
           "  });\n"
           "})();</script>\n")
    if "</body>" in html:
        html = html.replace("</body>", nav + "</body>", 1)
    else:
        html += nav

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print("rendered:", out_path, "|", len(html), "симв")
    print("  D: channels", len(D["channels"]), "managers", len(D["managers"]), "products", len(D["products"]))
    if g:
        print("  CH груп:", list(g.keys()), "| план-лінію прибрано:", not any(v.get("plan") for v in g.values()))
        print("  маржа/coverage:", {k: (v.get("margin"), f"{int((v.get('coverage') or 0) * 100)}%",
                                        "ok" if v.get("reliable") else "⚠")
                                    for k, v in g.items() if "coverage" in v})
    print("  MCI:", score, label, "| corr:", corr, "| днів:", m["days"])
    if rf.get("active"):
        print("  відмови 1С влито:", rf["of_orders"], "% (", rf["refused"], "з", rf["active"],
              ") | roll", _gref("roll")[0], "% amebli", _gref("amebli")[0], "%")
    if sh.get("june"):
        print("  відгрузки влито: факт", round(sum(sh["june"]) / 1000), "K | травень",
              round(sh.get("may_total", 0) / 1000), "K | план", round(sh.get("plan", 0) / 1000), "K")
    print("  Секцію 2 (Маркетинг в Огляді) приховано:", "SECTION 2 — MARKETING" not in html)
    print("  бейджі «в розробці»:", html.count('class="wip"'), "вкладок")
    if fn:
        print("  Секція 3 з CRM: спам", fn.get("spam_total"), "| недодзвон", fn.get("nedodzvon"),
              "| втрачені ліди", fn.get("lost"))
    print("  AI-висновки приховано:", ".ai-block{display:none}" in html)


if __name__ == "__main__":
    main()
