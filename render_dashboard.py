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
        real_cats = {gk: gv["cats"] for gk, gv in g.items() if gv.get("cats")}
        if real_cats:
            html = html.replace(
                "window._brandProd={};",
                "window._brandProd={};\nconst REAL_CATS = " + json.dumps(real_cats, ensure_ascii=False) + ";")
            html = html.replace(
                "const cats=b.cats.map(c=>({...c,rev:Math.round(actual*c.share)}));",
                "const cats=(window.REAL_CATS&&REAL_CATS[b.ch]&&REAL_CATS[b.ch].length)"
                "?REAL_CATS[b.ch]:b.cats.map(c=>({...c,rev:Math.round(actual*c.share)}));")
            html = html.replace("const dom=b.cats[0].m;", "const dom=cats[0].m;")

    # 5) hide Marketing + Finance tabs
    lines = [ln for ln in html.split("\n")
             if "swMain('marketing'" not in ln and "swMain('finance'" not in ln]
    html = "\n".join(lines)

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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print("preview.html:", OUT, "|", len(html), "симв")
    print("  D: channels", len(D["channels"]), "managers", len(D["managers"]), "products", len(D["products"]))
    if g:
        print("  CH груп:", list(g.keys()), "| план-лінію прибрано:", not any(v.get("plan") for v in g.values()))
    print("  MCI:", score, label, "| corr:", corr, "| днів:", m["days"])
    if rf.get("active"):
        print("  відмови 1С влито:", rf["of_orders"], "% (", rf["refused"], "з", rf["active"],
              ") | roll", _gref("roll")[0], "% amebli", _gref("amebli")[0], "%")


if __name__ == "__main__":
    main()
