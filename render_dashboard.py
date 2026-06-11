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
    html = TEMPLATE.read_text(encoding="utf-8")
    data = json.loads(DATA.read_text(encoding="utf-8"))

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
    desc = ("<b>Market Conditions Index</b> — композитний індекс ринкових умов "
            "(макро + сезон + воєнні фактори). Сьогодні <b>" + str(score) + "%</b> — " + phrase +
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
        if not any(v.get("plan") for v in g.values()):
            html = re.sub(r"\s*\{label:'План',data:planLine,[^}]*\},", "", html, count=1)

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
        ">📣 Маркетинг</button>",
        ">🛒 Корзина & ціноутворення</button>",
        ">⭐ Репутація</button>",
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
        html = re.sub(r"const shipPlan=\d+,", "const shipPlan=" + str(plan) + ",", html, count=1)
        html = html.replace("const shipPlanPct=((shipProj/shipPlan)*100).toFixed(0);",
                            "const shipPlanPct=(shipPlan>0?((shipProj/shipPlan)*100).toFixed(0):'—');")
        if plan <= 0:   # плану нема → ховаємо лінію плану
            html = re.sub(r"\s*\{label:'План',data:shipLabels\.map\(\(\)=>shipPlanDaily\),[^}]*\},",
                          "", html, count=1)

    # 8) Ховаємо Секцію 2 (Маркетинг/ДРР) — джерела рекламних витрат поки нема
    html = re.sub(r"<!-- ═══ SECTION 2 — MARKETING ═══ -->.*?(?=<!-- ═══ SECTION 3)",
                  "", html, count=1, flags=re.DOTALL)

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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print("preview.html:", OUT, "|", len(html), "симв")
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
