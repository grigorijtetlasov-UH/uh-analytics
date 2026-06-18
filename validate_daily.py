"""validate_daily.py — ПОВНА звірка денного шару (Б, Фаза 1) з місячними числами.
Агрегує всі дні з docs/daily*.json тими ж формулами, що будуть у JS-двигуні,
і порівнює КОЖЕН блок із docs/data*.json. Якщо все ✅ — Фаза 1 готова.
Запуск:  cd ~/uh-analytics && venv/bin/python validate_daily.py
"""
import json
from pathlib import Path

GROUPS = ("roll", "amebli", "seti", "roznica")
PIPE = ("in_progress", "production", "shipping", "sale",
        "refused", "returned", "lead", "claim")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def aggregate(day, keys):
    R = {"ch": {}, "grp": {}, "mgr": {}, "fun": {},
         "kpi": {"order": 0, "refused": 0, "lost": 0, "lead": 0, "spam": 0},
         "cf": {"spam": 0, "dubli": 0, "nedodzvon": 0, "lost": 0},
         "prod": {}, "ship": 0,
         "mrg": {}, "r1c": {"ov": {"sold": 0, "refused": 0}, "grp": {}}}
    for k in keys:
        d = day[k]
        for s, v in d["ch"].items():
            t = R["ch"].setdefault(s, {"rev": 0, "n": 0}); t["rev"] += v["rev"]; t["n"] += v["n"]
        for g, v in d["grp"].items():
            t = R["grp"].setdefault(g, {"rev": 0, "n": 0}); t["rev"] += v["rev"]; t["n"] += v["n"]
        for m, v in d["mgr"].items():
            t = R["mgr"].setdefault(m, {"won": 0, "ref": 0, "lost": 0, "ret": 0, "rev": 0})
            for kk in ("won", "ref", "lost", "ret", "rev"):
                t[kk] += v[kk]
        for c, n in d["fun"].items():
            R["fun"][c] = R["fun"].get(c, 0) + n
        for c in R["kpi"]:
            R["kpi"][c] += d["kpi"].get(c, 0)
        for c in R["cf"]:
            R["cf"][c] += d["cf"].get(c, 0)
        for nm, v in d["prod"].items():
            t = R["prod"].setdefault(nm, {"rev": 0, "qty": 0, "n": 0})
            t["rev"] += v["rev"]; t["qty"] += v["qty"]; t["n"] += v["n"]
        R["ship"] += d["ship"]
        for g, cats in d["mrg"].items():
            tg = R["mrg"].setdefault(g, {})
            for cat, v in cats.items():
                t = tg.setdefault(cat, {"rev": 0, "qty": 0, "rcov": 0, "ccov": 0})
                for kk in ("rev", "qty", "rcov", "ccov"):
                    t[kk] += v[kk]
        ro = d["r1c"]["ov"]; R["r1c"]["ov"]["sold"] += ro["sold"]; R["r1c"]["ov"]["refused"] += ro["refused"]
        for g, v in d["r1c"]["grp"].items():
            t = R["r1c"]["grp"].setdefault(g, {"sold": 0, "refused": 0})
            t["sold"] += v["sold"]; t["refused"] += v["refused"]
    return R


def derive(R):
    out = {}
    out["obsyag"] = round(sum(g["rev"] for g in R["grp"].values()))
    out["ship"] = round(R["ship"])
    k = R["kpi"]; sold = k["order"] + k["refused"]
    out["conversion"] = round(sold / (sold + k["lost"]) * 100, 1) if (sold + k["lost"]) else 0.0
    ov = R["r1c"]["ov"]
    out["refuse"] = {"refused": ov["refused"], "sold": ov["sold"],
                     "pct": round(ov["refused"] / ov["sold"] * 100, 1) if ov["sold"] else 0.0}
    pipe = {c: R["fun"].get(c, 0) for c in PIPE}
    pipe["unknown"] = R["fun"].get("unknown", 0)
    pipe["leads_total"] = sum(R["fun"].get(c, 0) for c in PIPE)
    out["pipeline"] = pipe
    out["cf"] = dict(R["cf"])
    mrg = {}
    for g, cats in R["mrg"].items():
        grev = sum(c["rev"] for c in cats.values())
        grcov = sum(c["rcov"] for c in cats.values())
        gccov = sum(c["ccov"] for c in cats.values())
        mrg[g] = {"margin": round((grcov - gccov) / grcov * 100, 1) if grcov else None,
                  "coverage": round(grcov / grev, 2) if grev else 0.0}
    out["margin"] = mrg
    if R["prod"]:
        nm = max(R["prod"], key=lambda x: R["prod"][x]["rev"])
        out["top_prod"] = {"name": nm, **R["prod"][nm]}
    if R["mgr"]:
        nm = max(R["mgr"], key=lambda x: R["mgr"][x]["rev"])
        m = R["mgr"][nm]
        out["top_mgr"] = {"name": nm, "won": m["won"], "ret": m["ret"],
                          "conv": round(m["won"] / (m["won"] + m["lost"]) * 100, 1) if (m["won"] + m["lost"]) else 0.0}
    return out


def check(data_f, daily_f):
    data = load(data_f)
    day = load(daily_f)["day"]
    dc = int(data.get("day_count", 31))
    cur = data_f.endswith("data.json")
    keys_obs = [k for k in day if (int(k) <= dc if cur else True)]   # обсяг/відгрузки: зріз по day_count
    keys_all = list(day.keys())                                       # 1С-маржа/відмови: весь місяць (як data.json)
    Aobs = derive(aggregate(day, keys_obs))
    A = derive(aggregate(day, keys_all))
    A["obsyag"] = Aobs["obsyag"]; A["ship"] = Aobs["ship"]            # ці два — зі зрізаного діапазону
    keys = keys_obs

    print(f"\n== {daily_f}  (днів={len(keys)}, day_count={dc}, {'поточний' if cur else 'минулий'})")
    fails = []

    def row(label, expect, got, tol=0):
        ok = (abs((got or 0) - (expect or 0)) <= tol)
        print(f"  {'OK ' if ok else 'XX '} {label:<24} data={expect}  daily={got}"
              + ("" if ok else f"  d={(got or 0)-(expect or 0):+}"))
        if not ok:
            fails.append(label)

    d_obs = round(sum(sum(g.get("june", [])) for g in data["groups"].values()))
    row("obsyag", d_obs, A["obsyag"])
    row("vidgruzky", round(sum(data["shipments"].get("june", []))), A["ship"])
    row("conversion %", data["kpi"]["conversion"]["value"], A["conversion"], tol=0.2)
    rf = data["kpi"]["refuse"]
    row("refuse refused", rf.get("refused", 0), A["refuse"]["refused"])
    row("refuse sold", rf.get("active", 0), A["refuse"]["sold"])
    row("refuse %", rf.get("of_orders", 0), A["refuse"]["pct"], tol=0.2)
    pl = data["funnel"].get("pipeline", {})
    for c in ("leads_total", "in_progress", "production", "shipping", "sale",
              "refused", "returned", "lead", "unknown"):
        row(f"funnel.{c}", pl.get(c, 0), A["pipeline"].get(c, 0))
    for c in ("spam", "dubli", "nedodzvon", "lost"):
        row(f"sec3.{c}", data["funnel"].get(c, 0), A["cf"].get(c, 0))
    for g in GROUPS:
        dm = data["groups"].get(g, {}).get("margin")
        am = A["margin"].get(g, {}).get("margin")
        if dm is not None or am is not None:
            row(f"margin.{g} %", dm, am, tol=0.2)
            row(f"coverage.{g}", data["groups"].get(g, {}).get("coverage"),
                A["margin"].get(g, {}).get("coverage"), tol=0.01)
    if data.get("products") and A.get("top_prod"):
        dp = data["products"][0]; ap = A["top_prod"]
        ok = dp["name"] == ap["name"]
        print(f"  {'OK ' if ok else 'XX '} top-product            data='{dp['name']}'  daily='{ap['name']}'")
        if not ok:
            fails.append("top-product")
        row("top-product revenue", dp["revenue"], ap["rev"])
        row("top-product qty", dp["qty"], ap["qty"])
        row("top-product count", dp.get("count", 0), ap["n"])
    if data.get("managers") and A.get("top_mgr"):
        dm = data["managers"][0]; am = A["top_mgr"]
        ok = dm["name"] == am["name"]
        print(f"  {'OK ' if ok else 'XX '} top-manager            data='{dm['name']}'  daily='{am['name']}'")
        if not ok:
            fails.append("top-manager")
        if dm.get("conversion") is not None:
            row("top-mgr conv %", dm["conversion"], am["conv"], tol=0.2)
        row("top-mgr returns", dm.get("returns", 0), am["ret"])

    print("  ->", "ALL MATCH" if not fails else f"MISMATCH: {fails}")
    return not fails


pairs = [
    ("docs/data.json", "docs/daily.json"),
    ("docs/data-2026-05.json", "docs/daily-2026-05.json"),
    ("docs/data-2026-04.json", "docs/daily-2026-04.json"),
]
allok = True
for d, dl in pairs:
    try:
        allok &= check(d, dl)
    except FileNotFoundError as e:
        print("\nskip (no file):", e.filename)
print("\n" + ("ALL MONTHS CONSISTENT ACROSS ALL BLOCKS - Phase 1 done"
              if allok else "MISMATCHES - paste full output, I will fix the daily layer"))
