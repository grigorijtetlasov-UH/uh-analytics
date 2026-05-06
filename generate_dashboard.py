"""
generate_dashboard.py — генерує денний (index.html) та місячний (month.html) дашборди.
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta

HISTORY_DIR = Path("history")
DOCS_DIR    = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)

# ──────────────────── HELPERS ────────────────────
def money(x):
    try:    return f"{float(x):,.0f}".replace(",", " ")
    except: return "0"

def money_k(x):
    try:
        v = float(x)
        if v >= 1_000_000: return f"{v/1_000_000:.2f}M"
        if v >= 1_000:     return f"{v/1_000:.0f}K"
        return f"{v:.0f}"
    except: return "0"

def pct(x):
    try:    return f"{float(x):.1f}%"
    except: return "0.0%"

def delta_str(curr, prev):
    if not prev or prev == 0:
        return ("neu", "—")
    d = (curr - prev) / prev * 100
    if d > 0:   return ("up", f"+{d:.1f}%")
    if d < 0:   return ("down", f"{d:.1f}%")
    return ("neu", "0%")


def build_multi_month_summary(multi_month: list, source_label: str = "CRM") -> str:
    """
    Будує HTML-блок з текстовим резюме по multi_month масиву (3 місяці).
    Кожен місяць — окрема картка з: total, топ-день, мін-день, середнє, тренд.
    Знизу — крос-місячне порівняння.
    """
    if not multi_month:
        return ""

    cards = []
    totals_by_month = []  # для крос-порівняння

    for mm in multi_month:
        days = mm.get("days", [])
        label = mm.get("label", mm.get("month", ""))
        if not days:
            cards.append(f'''
            <div class="mm-card mm-empty">
              <div class="mm-h">{label}</div>
              <div class="mm-empty-msg">немає даних</div>
            </div>''')
            totals_by_month.append({"label": label, "month": mm.get("month"), "revenue": 0, "orders": 0, "days_count": 0})
            continue

        total_rev = sum(d["revenue"] for d in days)
        total_ord = sum(d["orders"] for d in days)
        total_lds = sum(d.get("leads", 0) for d in days)
        avg_rev = total_rev / len(days) if days else 0

        top_day = max(days, key=lambda x: x["revenue"])
        min_day = min(days, key=lambda x: x["revenue"]) if len(days) > 1 else top_day

        # Тренд: ділимо на дві половини, рахуємо середню виручку, порівнюємо
        trend_html = ""
        if len(days) >= 4:
            half = len(days) // 2
            first_avg = sum(d["revenue"] for d in days[:half]) / half
            second_avg = sum(d["revenue"] for d in days[half:]) / (len(days) - half)
            if first_avg > 0:
                tr_pct = (second_avg - first_avg) / first_avg * 100
                if tr_pct > 5:
                    trend_html = f'<div class="mm-trend up">↗ Тренд росте: {tr_pct:+.1f}% (2-га половина vs 1-ша)</div>'
                elif tr_pct < -5:
                    trend_html = f'<div class="mm-trend down">↘ Тренд падає: {tr_pct:+.1f}% (2-га половина vs 1-ша)</div>'
                else:
                    trend_html = f'<div class="mm-trend neu">→ Стабільно ({tr_pct:+.1f}%)</div>'

        cards.append(f'''
        <div class="mm-card">
          <div class="mm-h">{label}</div>
          <div class="mm-rows">
            <div class="mm-r"><span class="mm-l">Всього:</span><span class="mm-v"><b>{money(total_rev)} ₴</b> · {total_ord} зам.{f" · {total_lds} лід" if total_lds else ""}</span></div>
            <div class="mm-r"><span class="mm-l">Середнє/день:</span><span class="mm-v">{money(avg_rev)} ₴</span></div>
            <div class="mm-r"><span class="mm-l">🏆 Топ-день:</span><span class="mm-v">{top_day["day"]:02d} — {money(top_day["revenue"])} ₴ ({top_day["orders"]} зам.)</span></div>
            <div class="mm-r"><span class="mm-l">📉 Мін-день:</span><span class="mm-v">{min_day["day"]:02d} — {money(min_day["revenue"])} ₴ ({min_day["orders"]} зам.)</span></div>
            <div class="mm-r"><span class="mm-l">Активних днів:</span><span class="mm-v">{len(days)}</span></div>
          </div>
          {trend_html}
        </div>''')
        totals_by_month.append({
            "label": label, "month": mm.get("month"),
            "revenue": total_rev, "orders": total_ord,
            "days_count": len(days), "avg": avg_rev
        })

    # Крос-порівняння: останній (поточний) vs кожен попередній
    cross_lines = []
    if len(totals_by_month) >= 2:
        newest = totals_by_month[-1]
        nd = newest["days_count"]
        if nd > 0:
            for prev in totals_by_month[:-1]:
                # Same-period: беремо ті самі N днів з прев місяця для чесного порівняння
                # (треба взяти з multi_month оригінальні дні — нижче)
                prev_days_full = next((m["days"] for m in multi_month if m["month"] == prev["month"]), [])
                same_period_days = [d for d in prev_days_full if d["day"] <= nd]
                same_rev = sum(d["revenue"] for d in same_period_days)
                same_ord = sum(d["orders"] for d in same_period_days)

                cls, txt = delta_str(newest["revenue"], same_rev)
                cross_lines.append(
                    f'<div class="mm-cmp"><span class="mm-cmp-l">{newest["label"]} vs {prev["label"]} (1-{nd:02d}):</span> '
                    f'<b>{money(newest["revenue"])} ₴</b> vs <b>{money(same_rev)} ₴</b> '
                    f'<span class="dlt {cls}">{txt}</span> '
                    f'<span class="mm-cmp-sub">· зам.: {newest["orders"]} vs {same_ord}</span></div>'
                )

    cross_html = ""
    if cross_lines:
        cross_html = f'<div class="mm-cross"><div class="mm-cross-h">📊 Same-period порівняння ({source_label})</div>{"".join(cross_lines)}</div>'

    return f'''
    <div class="mm-summary">
      <div class="mm-cards">{"".join(cards)}</div>
      {cross_html}
    </div>'''

def load_data(date_iso):
    p = HISTORY_DIR / f"{date_iso}.json"
    if not p.exists(): return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def load_history(days=30):
    files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)[:days]
    history = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                history.append(json.load(fp))
        except: pass
    return list(reversed(history))


# ──────────────────── CSS (загальний стиль) ────────────────────
SHARED_CSS = '''
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{--bg:#0c0f1a;--s:#151929;--s2:#1c2137;--s3:#242b47;--brd:#2a3050;--brd2:#3a4170;--t:#e4e8f7;--t2:#c1c7e0;--td:#7b84a3;--td2:#5a6280;--ac:#6c5ce7;--ac2:#a29bfe;--g:#00d68f;--gd:rgba(0,214,143,.15);--o:#ffa94d;--od:rgba(255,169,77,.15);--r:#ff6b6b;--rd:rgba(255,107,107,.15);--b:#339af0;--bd:rgba(51,154,240,.15);--y:#ffd43b;--p:#da77f2;--c:#66d9e8;--lime:#94d82d;--drr-good:#00d68f;--drr-ok:#94d82d;--drr-warn:#ffa94d;--drr-bad:#ff6b6b;--drr-neu:#7b84a3}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--t);min-height:100vh;padding:14px 18px;font-size:12px;line-height:1.4}
.hdr{text-align:center;margin-bottom:8px;position:relative}
.hdr h1{font-size:24px;font-weight:700;background:linear-gradient(135deg,var(--ac2),var(--g));-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-0.5px}
.hdr .sub{color:var(--td);font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-top:3px}
.hdr .stamp{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--td2);margin-top:4px;padding:2px 8px;background:var(--s);border:1px solid var(--brd);border-radius:10px}
.view-switch{position:absolute;top:0;right:0;display:flex;gap:2px;background:var(--s);border:1px solid var(--brd);border-radius:8px;padding:3px}
.view-switch a{padding:6px 14px;border-radius:6px;text-decoration:none;color:var(--td);font-size:11px;font-weight:500;transition:.15s}
.view-switch a.on{background:var(--ac);color:#fff}
.view-switch a:hover:not(.on){color:var(--t);background:var(--s2)}
.ins-wrap{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
.ins{flex:1;min-width:240px;background:var(--s);border:1px solid var(--brd);border-radius:9px;padding:8px 12px;display:flex;align-items:center;gap:8px;font-size:11px}
.ins-ico{font-size:14px;flex-shrink:0}
.ins-txt{color:var(--t2);line-height:1.3}
.ins-good{border-left:3px solid var(--g)}
.ins-warn{border-left:3px solid var(--o)}
.ins-bad{border-left:3px solid var(--r)}
.ins-info{border-left:3px solid var(--b)}
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:9px;margin-bottom:14px}
.kpi{background:var(--s);border:1px solid var(--brd);border-radius:11px;padding:12px 11px;position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:11px 11px 0 0}
.kpi:nth-child(1)::before{background:linear-gradient(90deg,var(--ac),var(--ac2))}
.kpi:nth-child(2)::before{background:var(--g)}
.kpi:nth-child(3)::before{background:var(--o)}
.kpi:nth-child(4)::before{background:var(--b)}
.kpi:nth-child(5)::before{background:var(--p)}
.kpi:nth-child(6)::before{background:var(--c)}
.kpi:nth-child(7)::before{background:var(--r)}
.kpi:nth-child(8)::before{background:var(--lime)}
.kl{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--td);margin-bottom:3px;font-weight:500}
.kv{font-family:'JetBrains Mono',monospace;font-size:19px;font-weight:600;line-height:1.1}
.ku{font-size:9px;color:var(--td);margin-left:3px;font-family:'DM Sans'}
.ks{font-size:9px;color:var(--td);margin-top:3px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.dlt{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:600;padding:1px 5px;border-radius:4px}
.dlt.up{background:var(--gd);color:var(--g)}
.dlt.down{background:var(--rd);color:var(--r)}
.dlt.neu{background:rgba(123,132,163,.15);color:var(--td)}
.tabs{display:flex;gap:2px;margin-bottom:14px;background:var(--s);border-radius:10px;padding:3px;border:1px solid var(--brd);flex-wrap:wrap}
.tab{flex:1;min-width:110px;padding:9px 6px;border-radius:8px;text-align:center;cursor:pointer;font-size:11px;font-weight:500;color:var(--td);border:none;background:none;transition:.15s;letter-spacing:.3px}
.tab:hover{color:var(--t);background:var(--s2)}
.tab.on{background:var(--ac);color:#fff}
.pnl{display:none}
.pnl.on{display:block;animation:fade .2s ease-in}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.cd{background:var(--s);border:1px solid var(--brd);border-radius:11px;padding:14px;margin-bottom:11px}
.ct{font-size:12px;font-weight:600;margin-bottom:5px;display:flex;align-items:center;gap:7px}
.ct .dot{width:7px;height:7px;border-radius:50%;background:var(--ac);flex-shrink:0}
.ct .badge-tot{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:500;color:var(--td);margin-left:auto;padding:2px 8px;background:var(--s2);border-radius:5px}
.cd-d{font-size:10px;color:var(--td);margin-bottom:11px;line-height:1.4}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:11px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:11px;margin-bottom:11px}
.g4{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:11px}
@media(max-width:980px){.g2,.g3,.g4{grid-template-columns:1fr}}
canvas{max-height:280px}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:var(--s2);padding:7px 9px;text-align:left;font-weight:600;color:var(--td);font-size:9px;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap;border-bottom:1px solid var(--brd)}
th.r,td.r{text-align:right}
td{padding:6px 9px;border-bottom:1px solid rgba(255,255,255,.04)}
tbody tr:hover td{background:rgba(108,92,231,.06)}
.scr{max-height:420px;overflow-y:auto}
.scr::-webkit-scrollbar{width:5px}
.scr::-webkit-scrollbar-thumb{background:var(--brd2);border-radius:3px}
.scr::-webkit-scrollbar-track{background:var(--s2)}
.badge{display:inline-block;padding:2px 7px;border-radius:5px;font-size:9px;font-weight:600;letter-spacing:.2px}
.bg{background:var(--gd);color:var(--g)}.bo{background:var(--od);color:var(--o)}
.br{background:var(--rd);color:var(--r)}.bb{background:var(--bd);color:var(--b)}
.num{font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:500}
.bar-row{display:flex;align-items:center;gap:9px;padding:5px 11px;border-bottom:1px solid rgba(255,255,255,.03)}
.bar-row:last-child{border-bottom:none}
.bar-name{font-size:11px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px}
.bar-wrap{flex:2;background:var(--s2);border-radius:3px;height:6px;overflow:hidden;min-width:60px}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--ac),var(--ac2));border-radius:3px;transition:width 1s cubic-bezier(.4,0,.2,1)}
.bar-val{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:600;width:90px;text-align:right;color:var(--t2)}
.mini-kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px;margin-bottom:11px}
.mk{background:var(--s2);border:1px solid var(--brd);border-radius:8px;padding:9px;text-align:center}
.mk-l{font-size:8px;text-transform:uppercase;letter-spacing:.5px;color:var(--td);margin-bottom:3px}
.mk-v{font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:600}
.mk-d{font-size:8px;margin-top:2px}
.cmp-row{display:grid;grid-template-columns:1fr 90px 90px 80px;gap:10px;padding:7px 11px;border-bottom:1px solid rgba(255,255,255,.04);align-items:center;font-size:11px}
.cmp-row:hover{background:rgba(108,92,231,.05)}
.cmp-name{font-weight:500}
.cmp-val{font-family:'JetBrains Mono',monospace;text-align:right;font-weight:500}
.ftr{text-align:center;color:var(--td2);font-size:10px;padding-top:18px;border-top:1px solid var(--brd);margin-top:24px;font-family:'JetBrains Mono',monospace}

/* PDF Export Button */
.pdf-btn{position:absolute;top:0;left:0;display:flex;align-items:center;gap:6px;background:linear-gradient(135deg,var(--ac),var(--ac2));color:#fff;border:none;padding:8px 14px;border-radius:8px;font-size:11px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;letter-spacing:.3px;box-shadow:0 2px 8px rgba(108,92,231,.25);transition:.15s}
.pdf-btn:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(108,92,231,.4)}
.pdf-btn:disabled{opacity:.6;cursor:wait;transform:none}
.pdf-btn .ic{font-size:13px}

/* PDF EXPORT MODE — show all panels (without forced page-breaks; pages added manually in JS) */
body.pdf-mode .pnl{display:block !important;padding-top:14px;break-inside:avoid}
body.pdf-mode .pnl.pdf-first{padding-top:0}
body.pdf-mode .tabs{display:none !important}
body.pdf-mode .pdf-btn{display:none !important}
body.pdf-mode .view-switch{display:none !important}
body.pdf-mode{padding:20px}
body.pdf-mode .pnl-title{font-size:18px;font-weight:700;color:var(--ac2);margin:0 0 12px;border-bottom:1px solid var(--brd);padding-bottom:6px;display:block !important}
.pnl-title{display:none}

/* Multi-month summary cards */
.mm-summary{margin-top:14px}
.mm-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-bottom:14px}
.mm-card{background:linear-gradient(180deg,rgba(108,92,231,.06),rgba(108,92,231,.02));border:1px solid var(--brd);border-radius:10px;padding:12px 14px}
.mm-card.mm-empty{opacity:.5}
.mm-h{font-size:13px;font-weight:700;color:var(--ac2);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--brd)}
.mm-rows{display:flex;flex-direction:column;gap:5px}
.mm-r{display:flex;justify-content:space-between;gap:8px;font-size:11.5px;line-height:1.35}
.mm-l{color:var(--td);flex-shrink:0}
.mm-v{color:var(--tx);text-align:right}
.mm-trend{margin-top:8px;padding:5px 8px;border-radius:6px;font-size:11px;font-weight:600;text-align:center}
.mm-trend.up{background:var(--gd);color:var(--g)}
.mm-trend.down{background:var(--rd);color:var(--r)}
.mm-trend.neu{background:rgba(123,132,163,.12);color:var(--td)}
.mm-empty-msg{text-align:center;color:var(--td);font-size:12px;padding:20px 0}
.mm-cross{background:rgba(108,92,231,.05);border:1px solid var(--brd);border-radius:10px;padding:12px 14px}
.mm-cross-h{font-size:12px;font-weight:700;color:var(--ac2);margin-bottom:10px}
.mm-cmp{font-size:11.5px;line-height:1.7;color:var(--tx)}
.mm-cmp-l{color:var(--td)}
.mm-cmp-sub{color:var(--td);font-size:11px}
'''


# ──────────────────── ДЕННИЙ ДАШБОРД ────────────────────
def build_daily(data, history):
    date_disp = data.get("date_disp", "—")
    # У старій версії data["month"] був рядком "01.05 – 03.05.2026"
    # У новій — це dict з місячними даними. Беремо month_str з date_disp або target_month
    month_raw = data.get("month")
    if isinstance(month_raw, dict):
        month_str = month_raw.get("target_month", data.get("date_disp", "—"))
    else:
        month_str = month_raw or "—"
    uh   = data.get("uh", {})
    crm  = data.get("crm", {})
    ga4  = data.get("ga4", {})
    meta = data.get("meta", {})

    uh_orders_d = uh.get("ORDERS", {}).get("day", {}).get("total", 0)
    uh_sales_d  = uh.get("SALES",  {}).get("day", {}).get("total", 0)
    uh_orders_m = uh.get("ORDERS", {}).get("month", {}).get("total", 0)
    uh_sales_m  = uh.get("SALES",  {}).get("month", {}).get("total", 0)

    # Відмови 1С (Отказ Не отправлен / Отказ Отправлен)
    uh_refused_d = uh.get("ORDERS", {}).get("day_refused", {}).get("total", 0)
    uh_refused_m = uh.get("ORDERS", {}).get("month_refused", {}).get("total", 0)

    total_orders_d  = uh_orders_d   # 1С Замовлення (без відмов)
    total_sales_d   = uh_sales_d     # 1С Відгрузки (фактичний заробіток)
    total_refused_d = uh_refused_d # 1С Відмови
    total_orders_m  = uh_orders_m
    total_sales_m   = uh_sales_m
    total_refused_m = uh_refused_m
    total_revenue_d = total_orders_d  # сумісність

    crm_o   = crm.get("orders", {})
    crm_l   = crm.get("leads", {})
    crm_orders_d   = crm_o.get("total", 0)
    crm_all_req    = crm_o.get("all_requests", crm_o.get("all_rows", 0))
    crm_sum_all    = crm_o.get("sum_all", crm_o.get("revenue", 0))      # ВСІ заявки
    crm_sum_nospam = crm_o.get("sum_no_spam", crm_o.get("revenue", 0))  # БЕЗ СПАМУ
    crm_sum_orders = crm_o.get("sum_orders", crm_o.get("revenue", 0))   # тільки замовлення+відмови
    crm_revenue_d  = crm_sum_orders  # сумісність
    crm_leads_d    = crm_l.get("new_leads", 0)
    crm_refuse_p   = crm_o.get("refuse_pct", 0)
    crm_avg_check  = crm_o.get("avg_check", 0)
    crm_spam       = crm_o.get("spam", 0)

    ga4_sessions = ga4.get("sessions", 0)
    ga4_users    = ga4.get("users", 0)
    ga4_bounce   = ga4.get("bounce_rate", 0)
    ga4_avg_dur  = ga4.get("avg_duration", 0)

    meta_t = meta.get("total", {})
    meta_spend   = meta_t.get("spend", 0)
    meta_clicks  = meta_t.get("clicks", 0)
    meta_results = meta_t.get("results", 0)
    meta_cpc     = meta_t.get("cpc", 0)
    meta_ctr     = meta_t.get("ctr", 0)
    meta_cpr     = meta_t.get("cpr", 0)
    meta_imp     = meta_t.get("impressions", 0)

    # ROAS — два значення: по замовленням і по відгрузкам
    roas_orders = round(total_orders_d / max(meta_spend, 1), 2) if meta_spend > 0 else 0
    roas_sales  = round(total_sales_d  / max(meta_spend, 1), 2) if meta_spend > 0 else 0
    roas = roas_sales  # для сумісності з insights
    site_conv = round(crm_orders_d / max(ga4_sessions, 1) * 100, 2) if ga4_sessions > 0 else 0

    # ── ДРР (Доля Рекламних Витрат) ──
    # Чисельник: Meta Ads + Google Ads
    # Пріоритет джерела Google: точний Google Ads API → fallback на GA4 ads_cost
    gads_block = data.get("google_ads", {}) or {}
    gads_spend = float(gads_block.get("total_spend", 0) or 0)
    if gads_spend > 0:
        google_spend = gads_spend
        google_source = "Google Ads API"
    else:
        google_spend = float(ga4.get("ads_cost", 0) or 0)
        google_source = "GA4 (приблизно)"

    total_ad_spend = meta_spend + google_spend

    # Знаменник: 1С виручка БЕЗ ШОУРУМІВ (бо реклама Meta/Google не веде в офлайн)
    def _revenue_no_showroom(by_podr_dict):
        if not by_podr_dict:
            return 0.0
        total = 0.0
        for podr, amt in by_podr_dict.items():
            if podr and "шоу" in str(podr).lower():
                continue
            total += float(amt or 0)
        return total

    sales_by_podr  = data.get("uh", {}).get("SALES",  {}).get("day", {}).get("by_podr", {})
    orders_by_podr = data.get("uh", {}).get("ORDERS", {}).get("day", {}).get("by_podr", {})
    sales_no_sh  = _revenue_no_showroom(sales_by_podr)
    orders_no_sh = _revenue_no_showroom(orders_by_podr)

    # Якщо by_podr порожнє (старі JSON-и) — fallback на повну суму
    if sales_no_sh == 0 and total_sales_d > 0:
        sales_no_sh = total_sales_d
    if orders_no_sh == 0 and total_orders_d > 0:
        orders_no_sh = total_orders_d

    # ДРР по замовленням і відгрузкам (без шоурумів), в %
    drr_orders = round(total_ad_spend / orders_no_sh * 100, 2) if orders_no_sh > 0 else 0
    drr_sales  = round(total_ad_spend / sales_no_sh  * 100, 2) if sales_no_sh  > 0 else 0

    # Категоризація для розфарбовки плитки
    def _drr_class(drr):
        if drr <= 0:        return "neu"
        if drr < 10:        return "good"
        if drr < 20:        return "ok"
        if drr < 30:        return "warn"
        return "bad"
    drr_orders_cls = _drr_class(drr_orders)
    drr_sales_cls  = _drr_class(drr_sales)

    prev_data = history[-2] if len(history) >= 2 else None
    prev_revenue = prev_data.get("uh", {}).get("ORDERS", {}).get("day", {}).get("total", 0) if prev_data else 0
    prev_orders = prev_data.get("crm", {}).get("orders", {}).get("total", 0) if prev_data else 0
    prev_sessions = prev_data.get("ga4", {}).get("sessions", 0) if prev_data else 0
    prev_meta_spend = prev_data.get("meta", {}).get("total", {}).get("spend", 0) if prev_data else 0

    rev_delta_cls, rev_delta_txt = delta_str(total_revenue_d, prev_revenue)
    ord_delta_cls, ord_delta_txt = delta_str(crm_orders_d, prev_orders)
    ses_delta_cls, ses_delta_txt = delta_str(ga4_sessions, prev_sessions)
    meta_delta_cls, meta_delta_txt = delta_str(meta_spend, prev_meta_spend)

    crm_trend = crm.get("trend_30d", [])
    trend_dates    = [t["date"][5:] for t in crm_trend]
    trend_revenue  = [t["revenue"] for t in crm_trend]
    trend_orders   = [t["orders"] for t in crm_trend]
    trend_leads    = [t["leads"] for t in crm_trend]

    hist_dates, hist_uh, hist_uh_s, hist_meta, hist_ga4, hist_crm = [], [], [], [], [], []
    for h in history:
        d = h.get("date", "")
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            hist_dates.append(dt.strftime("%d.%m"))
        except: hist_dates.append(d)
        hist_uh.append(h.get("uh", {}).get("ORDERS", {}).get("day", {}).get("total", 0))
        hist_uh_s.append(h.get("uh", {}).get("SALES", {}).get("day", {}).get("total", 0))
        hist_meta.append(h.get("meta", {}).get("total", {}).get("spend", 0))
        hist_ga4.append(h.get("ga4", {}).get("sessions", 0))
        hist_crm.append(h.get("crm", {}).get("orders", {}).get("total", 0))

    insights = []
    if rev_delta_cls == "up":
        insights.append({"icon": "🚀", "type": "good", "text": f"Замовлення зросли на {rev_delta_txt} порівняно з попереднім днем"})
    elif rev_delta_cls == "down":
        insights.append({"icon": "⚠️", "type": "warn", "text": f"Замовлення впали на {rev_delta_txt} — варто розібратись"})

    if crm_refuse_p > 8:
        insights.append({"icon": "🔴", "type": "bad", "text": f"Висока частка відмов CRM: {crm_refuse_p}% (норма <5%)"})
    elif crm_refuse_p < 3 and crm_orders_d > 0:
        insights.append({"icon": "✅", "type": "good", "text": f"Відмінні відмови CRM: лише {crm_refuse_p}%"})

    if total_refused_d > 0:
        insights.append({"icon": "⚠️", "type": "warn", "text": f"Відмови 1С за день: {money(total_refused_d)} ₴"})

    if roas_sales > 0 and roas_sales >= 5:
        insights.append({"icon": "💎", "type": "good", "text": f"Чудовий ROAS Відгрузок: {roas_sales}× (на 1₴ реклами {roas_sales}₴ заробітку)"})
    elif roas_sales > 0 and roas_sales < 2:
        insights.append({"icon": "📉", "type": "warn", "text": f"Низький ROAS Відгрузок: {roas_sales}× — реклама працює неефективно"})

    # ДРР інсайти
    if drr_sales > 0 and drr_sales > 30:
        insights.append({"icon": "🚨", "type": "bad", "text": f"Критична ДРР по відгрузкам: {drr_sales}% — реклама зʼїдає прибуток"})
    elif drr_sales > 0 and drr_sales > 20:
        insights.append({"icon": "⚠️", "type": "warn", "text": f"Висока ДРР по відгрузкам: {drr_sales}% — варто оптимізувати кампанії"})
    elif drr_sales > 0 and drr_sales < 10:
        insights.append({"icon": "🎯", "type": "good", "text": f"Чудова ДРР по відгрузкам: {drr_sales}% (норма 10-20%)"})

    managers = crm.get("managers", [])
    if managers:
        top_mgr = managers[0]
        insights.append({"icon": "🏆", "type": "info",
                         "text": f"Топ менеджер дня: {top_mgr['name']} — {money(top_mgr['revenue'])} ₴ замовлень ({top_mgr['orders']} зам.)"})

    sites = crm.get("sites", {})
    if sites:
        top_site = max(sites.items(), key=lambda x: x[1]["revenue"])
        insights.append({"icon": "🌐", "type": "info",
                         "text": f"Топ канал: {top_site[0]} — {money(top_site[1]['revenue'])} ₴ замовлень"})

    if meta.get("by_campaign"):
        top_camp = meta["by_campaign"][0]
        insights.append({"icon": "📱", "type": "info",
                         "text": f"Топ кампанія: {top_camp['campaign'][:50]} — {money(top_camp['spend'])} ₴ витрат"})

    chart_data = {
        "trend_dates": trend_dates, "trend_revenue": trend_revenue,
        "trend_orders": trend_orders, "trend_leads": trend_leads,
        "hist_dates": hist_dates, "hist_uh": hist_uh,
        "hist_uh_s": hist_uh_s,
        "hist_meta": hist_meta, "hist_ga4": hist_ga4, "hist_crm": hist_crm,
        "uh_orders_podr": uh.get("ORDERS", {}).get("day", {}).get("by_podr", {}),
        "uh_refused_podr": uh.get("ORDERS", {}).get("day_refused", {}).get("by_podr", {}),
        "uh_sales_podr":  uh.get("SALES", {}).get("day", {}).get("by_podr", {}),
        "managers": managers, "managers_shop": crm.get("managers_shop", []),
        "chatters": crm.get("chatters", []), "sites": sites,
        "products": crm.get("products", []), "categories": crm.get("categories", {}),
        "request_types": crm.get("request_types", {}),
        "payment_methods": crm.get("payment_methods", {}),
        "delivery_types": crm.get("delivery_types", {}),
        "carriers": crm.get("carriers", {}), "warehouses": crm.get("warehouses", {}),
        "statuses": crm.get("statuses", {}),
        "refuse_reasons": crm.get("refuse_reasons", {}),
        "lead_objections": crm.get("lead_objections", {}),
        "meta_camps": meta.get("by_campaign", []),
        "meta_accounts": meta.get("accounts", []),
        "ga4_sources": ga4.get("by_source", []),
        "ga4_pages": ga4.get("by_page", []),
        "ga4_devices": ga4.get("by_device", []),
    }
    chart_json = json.dumps(chart_data, ensure_ascii=False)

    insights_html = "".join([
        f'<div class="ins ins-{i["type"]}"><span class="ins-ico">{i["icon"]}</span><span class="ins-txt">{i["text"]}</span></div>'
        for i in insights
    ])
    insights_block = f'<div class="ins-wrap">{insights_html}</div>' if insights else ""
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    avg_dur_str = f'{int(ga4_avg_dur//60)}:{int(ga4_avg_dur%60):02d}'

    return DAILY_TEMPLATE.format(
        date_disp=date_disp, month_str=month_str, timestamp=timestamp,
        insights_block=insights_block,
        # 1С
        total_orders_d=money(total_orders_d),
        total_sales_d=money(total_sales_d),
        total_refused_d=money(total_refused_d),
        total_orders_m=money_k(total_orders_m),
        total_sales_m=money_k(total_sales_m),
        total_refused_m=money_k(total_refused_m),
        uh_orders_d=money(uh_orders_d),
        uh_sales_d=money(uh_sales_d),
        uh_refused_d=money(uh_refused_d),
        uh_orders_d_k=money_k(uh_orders_d),
        uh_sales_d_k=money_k(uh_sales_d),
        uh_refused_d_k=money_k(uh_refused_d),
        uh_orders_m_k=money_k(uh_orders_m),
        uh_sales_m_k=money_k(uh_sales_m),
        # CRM
        crm_orders_d=crm_orders_d,
        crm_all_req=crm_all_req,
        crm_sum_all=money(crm_sum_all),
        crm_sum_nospam=money(crm_sum_nospam),
        crm_sum_orders=money(crm_sum_orders),
        crm_leads_d=crm_leads_d,
        crm_avg_check=money(crm_avg_check),
        crm_avg_check_str=money(crm_avg_check),
        crm_refuse_p_str=pct(crm_refuse_p),
        crm_revenue_d_k=money_k(crm_sum_orders),
        crm_spam=crm_spam,
        # ROAS
        roas_orders=roas_orders,
        roas_sales=roas_sales,
        # ДРР
        drr_orders=drr_orders,
        drr_sales=drr_sales,
        drr_orders_cls=drr_orders_cls,
        drr_sales_cls=drr_sales_cls,
        total_ad_spend=money(total_ad_spend),
        ga4_ads_cost_str=money(google_spend),
        # GA4 / Meta
        ga4_sessions=money(ga4_sessions),
        ga4_bounce_str=pct(ga4_bounce),
        meta_spend=money(meta_spend), meta_results=meta_results,
        rev_delta_cls=rev_delta_cls, rev_delta_txt=rev_delta_txt,
        ord_delta_cls=ord_delta_cls, ord_delta_txt=ord_delta_txt,
        ses_delta_cls=ses_delta_cls, ses_delta_txt=ses_delta_txt,
        meta_delta_cls=meta_delta_cls, meta_delta_txt=meta_delta_txt,
        managers_count=len(managers), managers_shop_count=len(crm.get("managers_shop", [])),
        chatters_count=len(crm.get("chatters", [])),
        sites_count=len(sites),
        meta_imp=money(meta_imp), meta_clicks=money(meta_clicks), meta_cpc=meta_cpc,
        meta_ctr=meta_ctr, meta_cpr=meta_cpr,
        ga4_users=money(ga4_users), ga4_new_users=money(ga4.get("new_users", 0)),
        avg_dur_str=avg_dur_str, site_conv=site_conv, chart_json=chart_json,
        css=SHARED_CSS,
    )


# ──────────────────── МІСЯЧНИЙ ДАШБОРД ────────────────────
def build_monthly(data, history):
    """Збирає month.html з порівнянням з попереднім місяцем."""
    target_month = data.get("month", {}).get("target_month", datetime.now().strftime("%Y-%m"))
    month_data = data.get("month", {})
    curr_crm = month_data.get("crm", {})
    prev_crm = month_data.get("prev_crm", {})

    if not curr_crm.get("orders"):
        return f'<html><body style="background:#0c0f1a;color:#e4e8f7;font-family:sans-serif;padding:40px;text-align:center"><h1>Місячний дашборд</h1><p>Немає даних за {target_month}</p></body></html>'

    # Поточні дані
    co = curr_crm.get("orders", {})
    cl = curr_crm.get("leads", {})
    c_orders = co.get("total", 0)
    c_revenue = co.get("revenue", 0)
    c_leads = cl.get("new_leads", 0)
    c_refused = co.get("refused", 0)
    c_refuse_p = co.get("refuse_pct", 0)
    c_avg_check = co.get("avg_check", 0)

    # Попередні дані
    po = prev_crm.get("orders", {}) if prev_crm else {}
    pl = prev_crm.get("leads", {}) if prev_crm else {}
    p_orders = po.get("total", 0)
    p_revenue = po.get("revenue", 0)
    p_leads = pl.get("new_leads", 0)
    p_refused = po.get("refused", 0)
    p_refuse_p = po.get("refuse_pct", 0)
    p_avg_check = po.get("avg_check", 0)

    # Дельти
    rev_d_cls, rev_d_txt = delta_str(c_revenue, p_revenue)
    ord_d_cls, ord_d_txt = delta_str(c_orders, p_orders)
    led_d_cls, led_d_txt = delta_str(c_leads, p_leads)
    chk_d_cls, chk_d_txt = delta_str(c_avg_check, p_avg_check)
    ref_d_cls, ref_d_txt = delta_str(c_refused, p_refused)

    # Інсайти
    insights = []
    if rev_d_cls == "up":
        insights.append({"icon": "🚀", "type": "good", "text": f"Замовлення місяця зросли на {rev_d_txt} vs попередній"})
    elif rev_d_cls == "down":
        insights.append({"icon": "📉", "type": "warn", "text": f"Замовлення впали на {rev_d_txt} vs попередній місяць"})

    if c_refuse_p > 8:
        insights.append({"icon": "🔴", "type": "bad", "text": f"Висока частка відмов за місяць: {c_refuse_p}%"})

    mgrs = curr_crm.get("managers", [])
    if mgrs:
        top = mgrs[0]
        insights.append({"icon": "🏆", "type": "info",
                         "text": f"Топ менеджер місяця: {top['name']} — {money(top['revenue'])} ₴ ({top['orders']} зам.)"})

    sites = curr_crm.get("sites", {})
    if sites:
        top_s = max(sites.items(), key=lambda x: x[1]["revenue"])
        insights.append({"icon": "🌐", "type": "info",
                         "text": f"Топ канал місяця: {top_s[0]} — {money(top_s[1]['revenue'])} ₴"})

    products = curr_crm.get("products", [])
    if products:
        insights.append({"icon": "🛏️", "type": "info",
                         "text": f"Топ товар: {products[0]['name'][:50]} — {money(products[0]['revenue'])} ₴"})

    insights_html = "".join([
        f'<div class="ins ins-{i["type"]}"><span class="ins-ico">{i["icon"]}</span><span class="ins-txt">{i["text"]}</span></div>'
        for i in insights
    ])
    insights_block = f'<div class="ins-wrap">{insights_html}</div>' if insights else ""

    # Daily trend
    daily = curr_crm.get("daily_trend", [])
    daily_dates = [d["date"][8:] for d in daily]
    daily_revenue = [d["revenue"] for d in daily]
    daily_orders = [d["orders"] for d in daily]
    daily_leads = [d["leads"] for d in daily]

    # Збираємо співставлення менеджерів
    prev_mgrs_dict = {m["name"]: m for m in prev_crm.get("managers", [])}
    mgr_compare = []
    for m in mgrs:
        prev_m = prev_mgrs_dict.get(m["name"], {})
        rev_delta = delta_str(m["revenue"], prev_m.get("revenue", 0))
        mgr_compare.append({
            "name": m["name"],
            "orders": m["orders"],
            "revenue": m["revenue"],
            "avg_check": m.get("avg_check", 0),
            "refuse_pct": m.get("refuse_pct", 0),
            "prev_revenue": prev_m.get("revenue", 0),
            "delta_cls": rev_delta[0],
            "delta_txt": rev_delta[1],
        })

    prev_sites = prev_crm.get("sites", {})
    sites_compare = []
    for name, s in sites.items():
        prev_s = prev_sites.get(name, {})
        rev_delta = delta_str(s["revenue"], prev_s.get("revenue", 0))
        sites_compare.append({
            "name": name,
            "orders": s["orders"],
            "revenue": s["revenue"],
            "avg_check": s.get("avg_check", 0),
            "prev_revenue": prev_s.get("revenue", 0),
            "delta_cls": rev_delta[0],
            "delta_txt": rev_delta[1],
        })
    sites_compare.sort(key=lambda x: x["revenue"], reverse=True)

    # Multi-month trend (3 місяці назад)
    multi_month = month_data.get("multi_month_trend", [])
    multi_month_1c = month_data.get("multi_month_1c_uh", {}) or {}
    mm_1c_orders = multi_month_1c.get("ORDERS", [])
    mm_1c_sales  = multi_month_1c.get("SALES",  [])

    # ── ДРР по місяцях: рекламні витрати + 1С виручка БЕЗ ШОУРУМІВ (з history) ──
    def _is_showroom(podr_name):
        return podr_name and "шоу" in str(podr_name).lower()

    def _agg_month_ad_spend(month_str, day_limit=None):
        """Сумує Meta + Google Ads за місяць (опційно обмежено першими N днями).
        Пріоритет джерела Google: точний Google Ads API → fallback GA4 ads_cost."""
        spend = 0.0
        for h in history:
            d_str = h.get("date", "")
            if d_str[:7] != month_str:
                continue
            if day_limit:
                try:
                    d_num = int(d_str[8:10])
                except Exception:
                    continue
                if d_num > day_limit:
                    continue
            meta_d = float(h.get("meta", {}).get("total", {}).get("spend", 0) or 0)
            # Google: спочатку API, якщо нема — GA4
            gads_d = float(h.get("google_ads", {}).get("total_spend", 0) or 0)
            if gads_d == 0:
                gads_d = float(h.get("ga4", {}).get("ads_cost", 0) or 0)
            spend += meta_d + gads_d
        return spend

    def _agg_month_revenue_no_sh(month_str, key="SALES", day_limit=None):
        """Сумує 1С виручку за місяць, виключаючи шоуруми. key='SALES' або 'ORDERS'."""
        revenue = 0.0
        for h in history:
            d_str = h.get("date", "")
            if d_str[:7] != month_str:
                continue
            if day_limit:
                try:
                    d_num = int(d_str[8:10])
                except Exception:
                    continue
                if d_num > day_limit:
                    continue
            by_podr = h.get("uh", {}).get(key, {}).get("day", {}).get("by_podr", {}) or {}
            day_total = h.get("uh", {}).get(key, {}).get("day", {}).get("total", 0)
            if by_podr:
                # Сумуємо тільки не-шоурум підрозділи
                for podr, amt in by_podr.items():
                    if not _is_showroom(podr):
                        revenue += float(amt or 0)
            else:
                # fallback на total якщо by_podr немає у старих JSON-ах
                revenue += float(day_total or 0)
        return revenue

    # Попередній місяць у форматі YYYY-MM
    prev_month_str = prev_crm.get("month") if prev_crm else None
    day_limit_for_drr = month_data.get("prev_crm_day_limit")

    curr_ad_spend   = _agg_month_ad_spend(target_month)
    prev_ad_spend   = _agg_month_ad_spend(prev_month_str, day_limit=day_limit_for_drr) if prev_month_str else 0

    curr_orders_rev = _agg_month_revenue_no_sh(target_month, key="ORDERS")
    prev_orders_rev = _agg_month_revenue_no_sh(prev_month_str, key="ORDERS", day_limit=day_limit_for_drr) if prev_month_str else 0

    curr_sales_rev  = _agg_month_revenue_no_sh(target_month, key="SALES")
    prev_sales_rev  = _agg_month_revenue_no_sh(prev_month_str, key="SALES",  day_limit=day_limit_for_drr) if prev_month_str else 0

    # Розраховуємо ДРР
    def _drr(spend, revenue):
        if revenue <= 0:
            return 0
        return round(spend / revenue * 100, 2)

    def _drr_class(drr):
        if drr <= 0:        return "neu"
        if drr < 10:        return "good"
        if drr < 20:        return "ok"
        if drr < 30:        return "warn"
        return "bad"

    curr_drr_orders = _drr(curr_ad_spend, curr_orders_rev)
    prev_drr_orders = _drr(prev_ad_spend, prev_orders_rev)
    curr_drr_sales  = _drr(curr_ad_spend, curr_sales_rev)
    prev_drr_sales  = _drr(prev_ad_spend, prev_sales_rev)

    # Дельта: ДРР що падає = добре (зелений), росте = погано (червоний)
    # Тому інвертуємо delta_str
    def _drr_delta(curr_d, prev_d):
        if prev_d <= 0 or curr_d <= 0:
            return ("neu", "—")
        diff = curr_d - prev_d
        if diff < 0:  return ("up", f"{diff:.1f}пп")    # ↓ ДРР = добре
        if diff > 0:  return ("down", f"+{diff:.1f}пп") # ↑ ДРР = погано
        return ("neu", "0пп")

    drr_orders_delta_cls, drr_orders_delta_txt = _drr_delta(curr_drr_orders, prev_drr_orders)
    drr_sales_delta_cls,  drr_sales_delta_txt  = _drr_delta(curr_drr_sales,  prev_drr_sales)

    chart_data = {
        "daily_dates": daily_dates,
        "daily_revenue": daily_revenue,
        "daily_orders": daily_orders,
        "daily_leads": daily_leads,
        "multi_month": multi_month,
        "multi_month_1c_uh": multi_month_1c,
        "managers": mgr_compare,
        "managers_shop": curr_crm.get("managers_shop", []),
        "chatters": curr_crm.get("chatters", []),
        "sites": sites_compare,
        "products": products[:50],
        "categories": curr_crm.get("categories", {}),
        "request_types": curr_crm.get("request_types", {}),
        "payment_methods": curr_crm.get("payment_methods", {}),
        "delivery_types": curr_crm.get("delivery_types", {}),
        "carriers": curr_crm.get("carriers", {}),
        "warehouses": curr_crm.get("warehouses", {}),
        "statuses": curr_crm.get("statuses", {}),
        "refuse_reasons": curr_crm.get("refuse_reasons", {}),
        "lead_objections": curr_crm.get("lead_objections", {}),
        # Попередній місяць — для довідки
        "prev_revenue": p_revenue,
        "prev_orders": p_orders,
    }
    chart_json = json.dumps(chart_data, ensure_ascii=False)

    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Мітка діапазону для same-period порівняння
    day_limit = month_data.get("prev_crm_day_limit") or prev_crm.get("day_limit")
    if day_limit:
        period_label = f"1–{day_limit:02d}"
        compare_note = f"за {period_label} число"  # "за 1-04 число"
    else:
        period_label = "повний місяць"
        compare_note = "повний місяць"

    return MONTHLY_TEMPLATE.format(
        target_month=target_month,
        prev_month=prev_crm.get("month", "—"),
        period_label=period_label,
        compare_note=compare_note,
        timestamp=timestamp,
        insights_block=insights_block,
        multi_month_summary=build_multi_month_summary(multi_month, source_label="CRM"),
        summary_1c_orders=build_multi_month_summary(mm_1c_orders, source_label="1С UH ORDERS"),
        summary_1c_sales=build_multi_month_summary(mm_1c_sales,  source_label="1С UH SALES"),
        c_revenue=money(c_revenue), c_orders=c_orders, c_leads=c_leads,
        c_avg_check=money(c_avg_check), c_refused=c_refused, c_refuse_p_str=pct(c_refuse_p),
        p_revenue=money(p_revenue), p_orders=p_orders, p_leads=p_leads,
        p_avg_check=money(p_avg_check), p_refused=p_refused, p_refuse_p_str=pct(p_refuse_p),
        rev_d_cls=rev_d_cls, rev_d_txt=rev_d_txt,
        ord_d_cls=ord_d_cls, ord_d_txt=ord_d_txt,
        led_d_cls=led_d_cls, led_d_txt=led_d_txt,
        chk_d_cls=chk_d_cls, chk_d_txt=chk_d_txt,
        ref_d_cls=ref_d_cls, ref_d_txt=ref_d_txt,
        managers_count=len(mgrs),
        managers_shop_count=len(curr_crm.get("managers_shop", [])),
        sites_count=len(sites),
        products_count=len(products),
        # ДРР помісячно
        curr_drr_orders=curr_drr_orders, prev_drr_orders=prev_drr_orders,
        curr_drr_sales=curr_drr_sales,   prev_drr_sales=prev_drr_sales,
        curr_drr_orders_cls=_drr_class(curr_drr_orders),
        curr_drr_sales_cls=_drr_class(curr_drr_sales),
        drr_orders_delta_cls=drr_orders_delta_cls, drr_orders_delta_txt=drr_orders_delta_txt,
        drr_sales_delta_cls=drr_sales_delta_cls,   drr_sales_delta_txt=drr_sales_delta_txt,
        curr_ad_spend=money(curr_ad_spend),
        chart_json=chart_json,
        css=SHARED_CSS,
    )


# ──────────────────── DAILY TEMPLATE ────────────────────
DAILY_TEMPLATE = '''<!DOCTYPE html>
<html lang="uk"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>UH — Daily Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<style>{css}</style></head>
<body>

<div class="hdr">
  <button class="pdf-btn" id="pdfBtn" onclick="exportPDF()"><span class="ic">📄</span><span>Експорт PDF</span></button>
  <div class="view-switch">
    <a href="index.html" class="on">📊 День</a>
    <a href="month.html">📅 Місяць</a>
  </div>
  <h1>UH Executive Dashboard</h1>
  <div class="sub">United Home · {date_disp}</div>
  <div class="stamp">Період місяця: {month_str} · оновлено {timestamp}</div>
</div>

{insights_block}

<div class="kpi-row">
  <div class="kpi"><div class="kl">Замовлення день (1С)</div><div class="kv">{total_orders_d}<span class="ku">₴</span></div><div class="ks">без відмов · <span class="dlt {rev_delta_cls}">{rev_delta_txt}</span></div></div>
  <div class="kpi"><div class="kl">Відгрузки день (1С)</div><div class="kv">{total_sales_d}<span class="ku">₴</span></div><div class="ks">фактичний заробіток</div></div>
  <div class="kpi"><div class="kl">Відмови день (1С)</div><div class="kv">{total_refused_d}<span class="ku">₴</span></div><div class="ks">Отказ Не/Відправлений</div></div>
  <div class="kpi"><div class="kl">Замовлення місяць</div><div class="kv">{total_orders_m}<span class="ku">₴</span></div><div class="ks">сум. з 1-го числа</div></div>
  <div class="kpi"><div class="kl">CRM Заявки (всі)</div><div class="kv">{crm_all_req}</div><div class="ks">{crm_sum_all} ₴ · усі статуси · <span class="dlt {ord_delta_cls}">{ord_delta_txt}</span></div></div>
  <div class="kpi"><div class="kl">CRM Замовлення</div><div class="kv">{crm_orders_d}</div><div class="ks">{crm_sum_orders} ₴ · {crm_refuse_p_str} відмов · сер.чек {crm_avg_check_str}</div></div>
  <div class="kpi"><div class="kl">ROAS</div><div class="kv">{roas_sales}<span class="ku">×</span></div><div class="ks">відгрузки/реклама · замовл. {roas_orders}×</div></div>
  <div class="kpi"><div class="kl">ДРР Відгрузки</div><div class="kv" style="color:var(--drr-{drr_sales_cls})">{drr_sales}<span class="ku">%</span></div><div class="ks">{total_ad_spend} ₴ реклами / SALES</div></div>
  <div class="kpi"><div class="kl">ДРР Замовлення</div><div class="kv" style="color:var(--drr-{drr_orders_cls})">{drr_orders}<span class="ku">%</span></div><div class="ks">{total_ad_spend} ₴ реклами / ORDERS</div></div>
  <div class="kpi"><div class="kl">Витрати на рекламу</div><div class="kv">{total_ad_spend}<span class="ku">₴</span></div><div class="ks">Meta {meta_spend}₴ + Google {ga4_ads_cost_str}₴</div></div>
</div>

<div class="tabs">
  <button class="tab on" onclick="sw('overview', this)">📊 Огляд</button>
  <button class="tab" onclick="sw('sales1c', this)">💰 1С Продажі</button>
  <button class="tab" onclick="sw('crm', this)">👥 CRM Менеджери</button>
  <button class="tab" onclick="sw('crmops', this)">🏭 CRM Операції</button>
  <button class="tab" onclick="sw('channels', this)">🌐 Канали</button>
  <button class="tab" onclick="sw('ads', this)">📱 Реклама</button>
  <button class="tab" onclick="sw('analytics', this)">📈 Аналітика</button>
</div>

<div class="pnl on" id="p-overview"><h2 class="pnl-title">📊 Огляд</h2>
  <div class="cd">
    <div class="ct"><span class="dot"></span>Динаміка замовлень CRM — поточний місяць<span class="badge-tot" id="trend30Total"></span></div>
    <div class="cd-d">Сума замовлень по днях з SalesDrive (без спаму). Стовпчики — сума замовлень, лінія — ліди.</div>
    <canvas id="chTrend30"></canvas>
  </div>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--ac)"></span>Замовлення (1С) — без відмов</div><canvas id="chOrders"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--g)"></span>Відгрузки (1С) — фактичний заробіток</div><canvas id="chSales"></canvas></div>
  </div>
  <div class="g3">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--b)"></span>GA4 Сесії</div><canvas id="chGa4" style="max-height:200px"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--o)"></span>Meta Витрати</div><canvas id="chMeta" style="max-height:200px"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--p)"></span>Заявки CRM</div><canvas id="chCrmOrd" style="max-height:200px"></canvas></div>
  </div>
</div>

<div class="pnl" id="p-sales1c"><h2 class="pnl-title">💰 1С Продажі</h2>
  <div class="mini-kpi">
    <div class="mk"><div class="mk-l">ORDERS день</div><div class="mk-v" style="color:var(--ac)">{uh_orders_d_k}</div></div>
    <div class="mk"><div class="mk-l">ВІДМОВИ день</div><div class="mk-v" style="color:var(--r)">{uh_refused_d_k}</div></div>
    <div class="mk"><div class="mk-l">SALES день</div><div class="mk-v" style="color:var(--o)">{uh_sales_d_k}</div></div>
    <div class="mk"><div class="mk-l">ORDERS міс.</div><div class="mk-v" style="color:var(--ac)">{uh_orders_m_k}</div></div>
    <div class="mk"><div class="mk-l">SALES міс.</div><div class="mk-v" style="color:var(--o)">{uh_sales_m_k}</div></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--ac)"></span>Замовлення по підрозділах<span class="badge-tot">{uh_orders_d} ₴</span></div>
    <div class="cd-d">Без статусу "Отказ"</div>
    <div id="uhOrdPodr"></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--r)"></span>Відмови (1С)<span class="badge-tot">{uh_refused_d} ₴</span></div>
    <div class="cd-d">Статус "Отказ Не отправлен" + "Отказ Отправлен"</div>
    <div id="uhRefPodr"></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--o)"></span>Відгрузки по підрозділах<span class="badge-tot">{uh_sales_d} ₴</span></div>
    <div class="cd-d">Реальний заробіток (без доставок)</div>
    <div id="uhSalPodr"></div>
  </div>
</div>

<div class="pnl" id="p-crm"><h2 class="pnl-title">👥 CRM Менеджери</h2>
  <div class="mini-kpi">
    <div class="mk"><div class="mk-l">Усього менеджерів</div><div class="mk-v">{managers_count}</div></div>
    <div class="mk"><div class="mk-l">Магазин</div><div class="mk-v">{managers_shop_count}</div></div>
    <div class="mk"><div class="mk-l">Чатери</div><div class="mk-v">{chatters_count}</div></div>
    <div class="mk"><div class="mk-l">Сума замовлень</div><div class="mk-v">{crm_revenue_d_k}</div></div>
    <div class="mk"><div class="mk-l">Сер. чек</div><div class="mk-v">{crm_avg_check_str}</div></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot"></span>🏆 Рейтинг менеджерів (онлайн)<span class="badge-tot">{managers_count} активних</span></div>
    <div class="cd-d">Конв. = orders/(orders+leads). Сортовано за виручкою.</div>
    <div class="scr">
      <table>
        <thead><tr><th>#</th><th>Менеджер</th><th class="r">Зам.</th><th class="r">Ліди</th><th class="r">Замовлення ₴</th><th class="r">Сер.чек</th><th class="r">Конв.</th><th class="r">Відмов</th><th class="r">% Відм.</th></tr></thead>
        <tbody id="mgrBody"></tbody>
      </table>
    </div>
  </div>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--c)"></span>🏪 Менеджери на магазині</div><div class="scr" style="max-height:300px"><table><thead><tr><th>Менеджер</th><th class="r">Зам.</th><th class="r">Замовлення ₴</th><th class="r">Сер.чек</th></tr></thead><tbody id="mgrShopBody"></tbody></table></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--p)"></span>💬 Чатери</div><div class="scr" style="max-height:300px"><table><thead><tr><th>Чатер</th><th class="r">Зам.</th><th class="r">Замовлення ₴</th></tr></thead><tbody id="chatterBody"></tbody></table></div></div>
  </div>
</div>

<div class="pnl" id="p-crmops"><h2 class="pnl-title">🏭 CRM Операції</h2>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--p)"></span>📦 Категорії товарів</div><canvas id="chCategories"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--c)"></span>📞 Тип звернення</div><canvas id="chRequestTypes"></canvas></div>
  </div>
  <div class="g3">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--g)"></span>💳 Спосіб оплати</div><div id="paymentMethods"></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--o)"></span>🚚 Тип доставки</div><div id="deliveryTypes"></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--b)"></span>📮 Перевізник</div><div id="carriers"></div></div>
  </div>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--y)"></span>🏭 Склад відправки</div><div id="warehouses"></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--ac2)"></span>📊 Розподіл статусів</div><canvas id="chStatuses" style="max-height:280px"></canvas></div>
  </div>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--r)"></span>🚫 Причини відмов</div><canvas id="chRefuse"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--o)"></span>🤔 Заперечення лідів</div><canvas id="chObjections"></canvas></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--lime)"></span>🛏️ ТОП-30 товарів<span class="badge-tot" id="prodTotal"></span></div>
    <div class="scr"><table><thead><tr><th>#</th><th>Товар</th><th class="r">К-сть</th><th class="r">Зам.</th><th class="r">Замовлення ₴</th></tr></thead><tbody id="prodBody"></tbody></table></div>
  </div>
</div>

<div class="pnl" id="p-channels"><h2 class="pnl-title">🌐 Канали</h2>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--g)"></span>🌐 Канали продажу<span class="badge-tot">{sites_count} активних</span></div>
    <div class="scr"><table><thead><tr><th>#</th><th>Канал</th><th class="r">Зам.</th><th class="r">Замовлення ₴</th><th class="r">Сер.чек</th><th>Графік</th></tr></thead><tbody id="sitesBody"></tbody></table></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot"></span>📊 Замовлення по каналах</div>
    <canvas id="chSites"></canvas>
  </div>
</div>

<div class="pnl" id="p-ads"><h2 class="pnl-title">📱 Реклама</h2>
  <div class="mini-kpi">
    <div class="mk"><div class="mk-l">Витрати</div><div class="mk-v" style="color:var(--ac)">{meta_spend}</div></div>
    <div class="mk"><div class="mk-l">Покази</div><div class="mk-v">{meta_imp}</div></div>
    <div class="mk"><div class="mk-l">Кліки</div><div class="mk-v">{meta_clicks}</div></div>
    <div class="mk"><div class="mk-l">CPC</div><div class="mk-v" style="color:var(--b)">{meta_cpc} ₴</div></div>
    <div class="mk"><div class="mk-l">CTR</div><div class="mk-v" style="color:var(--g)">{meta_ctr}%</div></div>
    <div class="mk"><div class="mk-l">Результати</div><div class="mk-v" style="color:var(--p)">{meta_results}</div></div>
    <div class="mk"><div class="mk-l">CPR</div><div class="mk-v" style="color:var(--o)">{meta_cpr} ₴</div></div>
    <div class="mk"><div class="mk-l">ROAS Замовл.</div><div class="mk-v" style="color:var(--g)">{roas_orders}×</div></div>
    <div class="mk"><div class="mk-l">ROAS Відгр.</div><div class="mk-v" style="color:var(--lime)">{roas_sales}×</div></div>
    <div class="mk"><div class="mk-l">ДРР Замовл.</div><div class="mk-v" style="color:var(--drr-{drr_orders_cls})">{drr_orders}%</div></div>
    <div class="mk"><div class="mk-l">ДРР Відгр.</div><div class="mk-v" style="color:var(--drr-{drr_sales_cls})">{drr_sales}%</div></div>
    <div class="mk"><div class="mk-l">Всі реклам. витрати</div><div class="mk-v" style="color:var(--ac2)">{total_ad_spend} ₴</div></div>
  </div>
  <div class="cd"><div class="ct"><span class="dot"></span>🏢 Розбивка по кабінетах</div><div id="metaAccounts"></div></div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--ac)"></span>🎯 Топ кампанії<span class="badge-tot" id="campTotal"></span></div>
    <div class="scr"><table><thead><tr><th>#</th><th>Кампанія</th><th>Кабінет</th><th class="r">Витрати</th><th class="r">Покази</th><th class="r">Кліки</th><th class="r">CPC</th><th class="r">CTR</th><th class="r">Результ.</th></tr></thead><tbody id="campBody"></tbody></table></div>
  </div>
</div>

<div class="pnl" id="p-analytics"><h2 class="pnl-title">📈 Аналітика</h2>
  <div class="mini-kpi">
    <div class="mk"><div class="mk-l">Сесії</div><div class="mk-v" style="color:var(--ac)">{ga4_sessions}</div></div>
    <div class="mk"><div class="mk-l">Користувачі</div><div class="mk-v" style="color:var(--g)">{ga4_users}</div></div>
    <div class="mk"><div class="mk-l">Нові</div><div class="mk-v" style="color:var(--b)">{ga4_new_users}</div></div>
    <div class="mk"><div class="mk-l">% Відмов</div><div class="mk-v" style="color:var(--r)">{ga4_bounce_str}</div></div>
    <div class="mk"><div class="mk-l">Сер. час</div><div class="mk-v" style="color:var(--p)">{avg_dur_str}</div></div>
    <div class="mk"><div class="mk-l">Конв. сайту</div><div class="mk-v" style="color:var(--o)">{site_conv}%</div></div>
  </div>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--ac)"></span>🔗 Топ джерела</div><div id="ga4Sources"></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--g)"></span>📄 Топ сторінки</div><div id="ga4Pages"></div></div>
  </div>
  <div class="cd"><div class="ct"><span class="dot" style="background:var(--o)"></span>📱 Пристрої</div><canvas id="chDevices" style="max-height:240px"></canvas></div>
</div>

<div class="ftr">UH Analytics · daily · {timestamp}</div>

<script>
const D = {chart_json};
function sw(name, btn){{document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));document.querySelectorAll('.pnl').forEach(p=>p.classList.remove('on'));btn.classList.add('on');document.getElementById('p-'+name).classList.add('on');}}
Chart.defaults.color='#7b84a3';Chart.defaults.font.family="'DM Sans', sans-serif";Chart.defaults.font.size=10;
const COMMON={{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{labels:{{padding:10,usePointStyle:true,pointStyleWidth:8,font:{{size:10}}}}}},tooltip:{{backgroundColor:'#1c2137',borderColor:'#3a4170',borderWidth:1,padding:10}}}},scales:{{x:{{grid:{{color:'rgba(255,255,255,0.03)'}},ticks:{{maxRotation:45,font:{{size:9}}}}}},y:{{grid:{{color:'rgba(255,255,255,0.03)'}},ticks:{{font:{{size:9}},callback:v=>v>=1000?(v/1000).toFixed(0)+'K':v}}}}}}}};
const fmt=n=>{{n=Number(n)||0;const isInt=Number.isInteger(n);return n.toLocaleString('uk',{{minimumFractionDigits:isInt?0:2,maximumFractionDigits:2}}).replace(/\u00a0/g,' ').replace(',','.');}};
const fmtK=n=>{{n=Number(n)||0;if(n>=1e6)return(n/1e6).toFixed(2)+'M';if(n>=1e3)return(n/1e3).toFixed(0)+'K';return n.toFixed(0);}};

{{const totalRev=D.trend_revenue.reduce((a,b)=>a+b,0);document.getElementById('trend30Total').textContent='∑ '+fmtK(totalRev)+' ₴';
new Chart(document.getElementById('chTrend30'),{{type:'bar',data:{{labels:D.trend_dates,datasets:[
{{type:'bar',label:'Замовлення ₴',data:D.trend_revenue,backgroundColor:'rgba(108,92,231,0.65)',borderColor:'#6c5ce7',borderWidth:1,borderRadius:4,yAxisID:'y1',order:2}},
{{type:'line',label:'Замовлень',data:D.trend_orders,borderColor:'#00d68f',backgroundColor:'rgba(0,214,143,.15)',tension:.4,borderWidth:2.5,pointRadius:3,yAxisID:'y2',order:1}},
{{type:'line',label:'Лідів',data:D.trend_leads,borderColor:'#ffa94d',tension:.4,borderWidth:2,pointRadius:2,borderDash:[5,3],yAxisID:'y2',order:0,fill:false}}]}},
options:{{...COMMON,scales:{{x:{{...COMMON.scales.x}},y1:{{position:'left',grid:COMMON.scales.y.grid,ticks:{{...COMMON.scales.y.ticks,color:'#a29bfe'}}}},y2:{{position:'right',grid:{{display:false}},ticks:{{font:{{size:9}},color:'#00d68f'}}}}}}}}}});}}

new Chart(document.getElementById('chOrders'),{{type:'bar',data:{{labels:D.hist_dates,datasets:[{{label:'Замовлення',data:D.hist_uh,backgroundColor:'rgba(108,92,231,0.85)',borderColor:'#6c5ce7',borderWidth:1,borderRadius:3}}]}},options:{{...COMMON,plugins:{{...COMMON.plugins,legend:{{display:false}}}}}}}});
new Chart(document.getElementById('chSales'),{{type:'bar',data:{{labels:D.hist_dates,datasets:[{{label:'Відгрузки',data:D.hist_uh_s,backgroundColor:'rgba(255,169,77,0.85)',borderColor:'#ffa94d',borderWidth:1,borderRadius:3}}]}},options:{{...COMMON,plugins:{{...COMMON.plugins,legend:{{display:false}}}}}}}});

function lineChart(id,data,color){{new Chart(document.getElementById(id),{{type:'line',data:{{labels:D.hist_dates,datasets:[{{data,borderColor:color,backgroundColor:color+'22',fill:true,tension:.4,borderWidth:2,pointRadius:2}}]}},options:{{...COMMON,plugins:{{...COMMON.plugins,legend:{{display:false}}}}}}}});}}
lineChart('chGa4',D.hist_ga4,'#339af0');lineChart('chMeta',D.hist_meta,'#ffa94d');lineChart('chCrmOrd',D.hist_crm,'#da77f2');

function renderPodr(elId,podrObj,color){{const el=document.getElementById(elId);const items=Object.entries(podrObj||{{}}).sort((a,b)=>b[1]-a[1]);if(!items.length){{el.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>';return;}}const max=items[0][1]||1;el.innerHTML=items.map(([n,v])=>{{const p=Math.max(2,Math.round(v/max*100));return `<div class="bar-row"><div class="bar-name" title="${{n}}">${{n}}</div><div class="bar-wrap"><div class="bar-fill" style="width:${{p}}%;background:${{color}}"></div></div><div class="bar-val">${{fmtK(v)}}</div></div>`;}}).join('');}}
renderPodr('uhOrdPodr',D.uh_orders_podr,'#6c5ce7');
renderPodr('uhRefPodr',D.uh_refused_podr,'#ff6b6b');
renderPodr('uhSalPodr',D.uh_sales_podr,'#ffa94d');

const mgrBody=document.getElementById('mgrBody');
if(D.managers&&D.managers.length){{mgrBody.innerHTML=D.managers.map((m,i)=>{{const refClass=m.refuse_pct>=12?'br':m.refuse_pct>=5?'bo':'bg';const convClass=m.conv>=85?'bg':m.conv>=70?'bo':'br';return `<tr><td class="num" style="color:var(--td)">${{i+1}}</td><td>${{m.name}}</td><td class="r num">${{m.orders}}</td><td class="r num" style="color:var(--td)">${{m.leads||0}}</td><td class="r num" style="color:var(--g)">${{fmtK(m.revenue)}}</td><td class="r num">${{fmt(m.avg_check||0)}}</td><td class="r"><span class="badge ${{convClass}}">${{(m.conv||0).toFixed(0)}}%</span></td><td class="r num">${{m.refused}}</td><td class="r"><span class="badge ${{refClass}}">${{m.refuse_pct.toFixed(1)}}%</span></td></tr>`;}}).join('');}}else{{mgrBody.innerHTML='<tr><td colspan="9" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

const mgrShopBody=document.getElementById('mgrShopBody');
if(D.managers_shop&&D.managers_shop.length){{mgrShopBody.innerHTML=D.managers_shop.map(m=>`<tr><td>${{m.name}}</td><td class="r num">${{m.orders}}</td><td class="r num" style="color:var(--g)">${{fmtK(m.revenue)}}</td><td class="r num">${{fmt(m.avg_check||0)}}</td></tr>`).join('');}}else{{mgrShopBody.innerHTML='<tr><td colspan="4" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

const chatterBody=document.getElementById('chatterBody');
if(D.chatters&&D.chatters.length){{chatterBody.innerHTML=D.chatters.map(c=>`<tr><td>${{c.name}}</td><td class="r num">${{c.orders}}</td><td class="r num" style="color:var(--g)">${{fmtK(c.revenue)}}</td></tr>`).join('');}}else{{chatterBody.innerHTML='<tr><td colspan="3" style="text-align:center;padding:18px;color:var(--td)">Немає чатерів</td></tr>';}}

function pieChart(elId,dataObj){{const el=document.getElementById(elId);if(!el)return;const palette=['#6c5ce7','#a29bfe','#00d68f','#ffa94d','#339af0','#ff6b6b','#da77f2','#66d9e8','#94d82d','#ffd43b','#fd7e14','#94d2bd'];const entries=Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]).slice(0,12);if(!entries.length){{el.parentElement.insertAdjacentHTML('beforeend','<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>');el.style.display='none';return;}}new Chart(el,{{type:'doughnut',data:{{labels:entries.map(e=>e[0]),datasets:[{{data:entries.map(e=>e[1]),backgroundColor:palette,borderWidth:2,borderColor:'#151929'}}]}},options:{{...COMMON,scales:{{}},cutout:'55%',plugins:{{...COMMON.plugins,legend:{{position:'right',labels:{{font:{{size:9}},padding:6,usePointStyle:true,boxWidth:8}}}}}}}}}});}}
pieChart('chCategories',D.categories);pieChart('chRequestTypes',D.request_types);pieChart('chStatuses',D.statuses);

function listChart(elId,dataObj,color){{const el=document.getElementById(elId);if(!el)return;const entries=Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]);if(!entries.length){{el.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>';return;}}const max=entries[0][1]||1;el.innerHTML=entries.map(([n,v])=>{{const p=Math.max(2,Math.round(v/max*100));return `<div class="bar-row"><div class="bar-name" title="${{n}}">${{n}}</div><div class="bar-wrap"><div class="bar-fill" style="width:${{p}}%;background:${{color}}"></div></div><div class="bar-val">${{v}}</div></div>`;}}).join('');}}
listChart('paymentMethods',D.payment_methods,'#00d68f');listChart('deliveryTypes',D.delivery_types,'#ffa94d');
listChart('carriers',D.carriers,'#339af0');listChart('warehouses',D.warehouses,'#ffd43b');

function barChartH(elId,dataObj,color){{const el=document.getElementById(elId);if(!el)return;const entries=Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]).slice(0,10);if(!entries.length){{el.parentElement.insertAdjacentHTML('beforeend','<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>');el.style.display='none';return;}}new Chart(el,{{type:'bar',data:{{labels:entries.map(e=>e[0].length>30?e[0].substr(0,30)+'…':e[0]),datasets:[{{label:'К-сть',data:entries.map(e=>e[1]),backgroundColor:color+'aa',borderColor:color,borderWidth:1,borderRadius:4}}]}},options:{{...COMMON,indexAxis:'y',plugins:{{...COMMON.plugins,legend:{{display:false}}}}}}}});}}
barChartH('chRefuse',D.refuse_reasons,'#ff6b6b');barChartH('chObjections',D.lead_objections,'#ffa94d');

const prodBody=document.getElementById('prodBody');
if(D.products&&D.products.length){{document.getElementById('prodTotal').textContent=D.products.length+' SKU';prodBody.innerHTML=D.products.map((p,i)=>`<tr><td class="num" style="color:var(--td)">${{i+1}}</td><td title="${{p.name}}">${{p.name.length>60?p.name.substr(0,60)+'…':p.name}}</td><td class="r num">${{p.qty||p.count}}</td><td class="r num" style="color:var(--td)">${{p.count}}</td><td class="r num" style="color:var(--g)">${{fmtK(p.revenue)}}</td></tr>`).join('');}}else{{prodBody.innerHTML='<tr><td colspan="5" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

const sitesEntries=Object.entries(D.sites||{{}}).sort((a,b)=>b[1].revenue-a[1].revenue);
const sitesBody=document.getElementById('sitesBody');
if(sitesEntries.length){{const maxR=sitesEntries[0][1].revenue;sitesBody.innerHTML=sitesEntries.map(([n,s],i)=>{{const p=Math.max(3,Math.round(s.revenue/maxR*100));return `<tr><td class="num" style="color:var(--td)">${{i+1}}</td><td>${{n}}</td><td class="r num">${{s.orders}}</td><td class="r num" style="color:var(--g)">${{fmtK(s.revenue)}}</td><td class="r num">${{fmt(s.avg_check||0)}}</td><td><div class="bar-wrap" style="width:120px"><div class="bar-fill" style="width:${{p}}%;background:linear-gradient(90deg,#00d68f,#94d2bd)"></div></div></td></tr>`;}}).join('');new Chart(document.getElementById('chSites'),{{type:'bar',data:{{labels:sitesEntries.map(e=>e[0]),datasets:[{{label:'Замовлення',data:sitesEntries.map(e=>e[1].revenue),backgroundColor:'rgba(0,214,143,0.7)',borderColor:'#00d68f',borderRadius:4}}]}},options:{{...COMMON,plugins:{{...COMMON.plugins,legend:{{display:false}}}},indexAxis:'y'}}}});}}else{{sitesBody.innerHTML='<tr><td colspan="6" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

const metaAcc=document.getElementById('metaAccounts');
if(D.meta_accounts&&D.meta_accounts.length){{metaAcc.innerHTML=D.meta_accounts.map(a=>{{const err=a.error?`<span class="badge br">⚠ ${{a.error.substr(0,40)}}…</span>`:`<span class="badge bg">OK</span>`;return `<div class="bar-row" style="border-bottom:1px solid var(--brd)"><div class="bar-name" style="max-width:none;flex:none;width:160px">${{a.name}}</div><div style="flex:1;display:flex;gap:14px;flex-wrap:wrap;font-size:11px"><span>Витрати: <b style="color:var(--ac)">${{fmt(a.spend||0)}} ₴</b></span><span>Кліки: <b>${{fmt(a.clicks||0)}}</b></span><span>CPC: <b>${{a.cpc||0}}</b></span><span>CTR: <b>${{a.ctr||0}}%</b></span><span>Результ.: <b style="color:var(--g)">${{a.results||0}}</b></span></div>${{err}}</div>`;}}).join('');}}else{{metaAcc.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає кабінетів</div>';}}

const campBody=document.getElementById('campBody');
if(D.meta_camps&&D.meta_camps.length){{document.getElementById('campTotal').textContent=D.meta_camps.length+' активних';campBody.innerHTML=D.meta_camps.map((c,i)=>`<tr><td class="num" style="color:var(--td)">${{i+1}}</td><td title="${{c.campaign}}">${{c.campaign.length>40?c.campaign.substr(0,40)+'…':c.campaign}}</td><td><span class="badge bb">${{c.account}}</span></td><td class="r num">${{fmt(c.spend)}}</td><td class="r num">${{fmt(c.impressions)}}</td><td class="r num">${{c.clicks}}</td><td class="r num">${{c.cpc}}</td><td class="r num">${{c.ctr}}%</td><td class="r num" style="color:var(--g)">${{c.results}}</td></tr>`).join('');}}else{{campBody.innerHTML='<tr><td colspan="9" style="text-align:center;padding:18px;color:var(--td)">Немає кампаній</td></tr>';}}

const ga4S=document.getElementById('ga4Sources');
if(D.ga4_sources.length){{const max=D.ga4_sources[0].sessions||1;ga4S.innerHTML=D.ga4_sources.map(s=>{{const lbl=s.source+(s.medium&&s.medium!=='(none)'?' / '+s.medium:'');const p=Math.max(2,Math.round(s.sessions/max*100));return `<div class="bar-row"><div class="bar-name" title="${{lbl}}">${{lbl}}</div><div class="bar-wrap"><div class="bar-fill" style="width:${{p}}%"></div></div><div class="bar-val">${{s.sessions}}</div></div>`;}}).join('');}}else{{ga4S.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>';}}

const ga4P=document.getElementById('ga4Pages');
if(D.ga4_pages.length){{const max=D.ga4_pages[0].views||1;ga4P.innerHTML=D.ga4_pages.map(p=>{{const pp=Math.max(2,Math.round(p.views/max*100));return `<div class="bar-row"><div class="bar-name" title="${{p.path}}">${{p.title||p.path}}</div><div class="bar-wrap"><div class="bar-fill" style="width:${{pp}}%;background:linear-gradient(90deg,#00d68f,#94d8a6)"></div></div><div class="bar-val">${{p.views}}</div></div>`;}}).join('');}}else{{ga4P.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>';}}

const chDev=document.getElementById('chDevices');
if(chDev&&D.ga4_devices&&D.ga4_devices.length){{new Chart(chDev,{{type:'doughnut',data:{{labels:D.ga4_devices.map(d=>d.device),datasets:[{{data:D.ga4_devices.map(d=>d.sessions),backgroundColor:['#6c5ce7','#00d68f','#ffa94d','#339af0'],borderWidth:2,borderColor:'#151929'}}]}},options:{{...COMMON,scales:{{}},cutout:'60%'}}}});}}

// === PDF EXPORT (по панелях, без зміщення сторінок) ===
async function exportPDF() {{
  console.log('[PDF] Старт експорту');
  const btn = document.getElementById('pdfBtn');
  if (!btn) {{ console.error('[PDF] Кнопка #pdfBtn не знайдена'); return; }}

  // Перевірка наявності бібліотек
  if (typeof html2canvas === 'undefined') {{
    alert('html2canvas не завантажився. Перезавантаж сторінку (Ctrl+F5).');
    console.error('[PDF] html2canvas undefined');
    return;
  }}
  if (!window.jspdf || !window.jspdf.jsPDF) {{
    alert('jsPDF не завантажився. Перезавантаж сторінку (Ctrl+F5).');
    console.error('[PDF] window.jspdf undefined');
    return;
  }}

  const originalHTML = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="ic">⏳</span><span>Готую PDF...</span>';

  // Включаємо PDF-режим — показуємо всі панелі
  document.body.classList.add('pdf-mode');
  await new Promise(r => setTimeout(r, 600)); // дай чартам перерендеритись
  console.log('[PDF] PDF-режим увімкнено');

  const today = new Date();
  const stamp = today.getFullYear() + '-' + String(today.getMonth()+1).padStart(2,'0') + '-' + String(today.getDate()).padStart(2,'0');
  const isMonthly = document.title.includes('Monthly');
  const fileName = (isMonthly ? 'UH_Monthly_' : 'UH_Daily_') + stamp + '.pdf';

  // Збираємо все що треба в PDF: шапка + KPI + всі панелі
  const sections = [];
  const hdr = document.querySelector('.hdr');
  const kpiRow = document.querySelector('.kpi-row');
  const insWrap = document.querySelector('.ins-wrap');

  // Перша сторінка: шапка + інсайти + KPI
  const firstWrap = document.createElement('div');
  firstWrap.style.background = 'var(--bg, #0c0f1a)';
  firstWrap.style.padding = '0';
  if (hdr) firstWrap.appendChild(hdr.cloneNode(true));
  if (insWrap) firstWrap.appendChild(insWrap.cloneNode(true));
  if (kpiRow) firstWrap.appendChild(kpiRow.cloneNode(true));
  sections.push(firstWrap);

  // Кожна панель — окрема сторінка
  document.querySelectorAll('.pnl').forEach(p => sections.push(p));

  // Готуємо jsPDF (a3 landscape)
  const {{ jsPDF }} = window.jspdf;
  const pdf = new jsPDF({{ unit: 'mm', format: 'a3', orientation: 'landscape', compress: true }});
  const pageW = pdf.internal.pageSize.getWidth();   // 420
  const pageH = pdf.internal.pageSize.getHeight();  // 297
  const margin = 8;
  const usableW = pageW - margin * 2;
  const usableH = pageH - margin * 2;

  // Тимчасово підставимо контейнер для рендеру (поза вʼюпортом, але з фіксованою шириною)
  const stage = document.createElement('div');
  stage.style.position = 'fixed';
  stage.style.left = '-99999px';
  stage.style.top = '0';
  stage.style.width = '1400px';
  stage.style.background = '#0c0f1a';
  stage.style.padding = '20px';
  document.body.appendChild(stage);

  try {{
    console.log('[PDF] Рендерю ' + sections.length + ' секцій...');
    for (let i = 0; i < sections.length; i++) {{
      const node = sections[i].cloneNode(true);
      stage.innerHTML = '';
      stage.appendChild(node);
      // Дай DOM перемалюватись
      await new Promise(r => setTimeout(r, 80));
      console.log('[PDF] Секція ' + (i+1) + '/' + sections.length);

      const canvas = await html2canvas(stage, {{
        scale: 1.5,
        useCORS: true,
        backgroundColor: '#0c0f1a',
        logging: false,
        windowWidth: 1440,
      }});

      const imgData = canvas.toDataURL('image/jpeg', 0.92);
      // Скейлимо щоб влізло у сторінку зі збереженням пропорцій
      const ratio = canvas.height / canvas.width;
      let imgW = usableW;
      let imgH = imgW * ratio;
      if (imgH > usableH) {{
        imgH = usableH;
        imgW = imgH / ratio;
      }}
      const x = (pageW - imgW) / 2;
      const y = margin;

      if (i > 0) pdf.addPage();
      pdf.addImage(imgData, 'JPEG', x, y, imgW, imgH);
    }}

    pdf.save(fileName);
  }} catch (e) {{
    console.error('PDF export error:', e);
    alert('Помилка експорту PDF: ' + (e.message || e));
  }} finally {{
    stage.remove();
    document.body.classList.remove('pdf-mode');
    btn.disabled = false;
    btn.innerHTML = originalHTML;
  }}
}}
</script>
</body></html>
'''


# ──────────────────── MONTHLY TEMPLATE ────────────────────
MONTHLY_TEMPLATE = '''<!DOCTYPE html>
<html lang="uk"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>UH — Monthly Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<style>{css}</style></head>
<body>

<div class="hdr">
  <button class="pdf-btn" id="pdfBtn" onclick="exportPDF()"><span class="ic">📄</span><span>Експорт PDF</span></button>
  <div class="view-switch">
    <a href="index.html">📊 День</a>
    <a href="month.html" class="on">📅 Місяць</a>
  </div>
  <h1>UH Monthly Dashboard</h1>
  <div class="sub">United Home · {target_month}</div>
  <div class="stamp">Поточний: {target_month} ({compare_note}) · Порівняння з {prev_month} ({compare_note}) · оновлено {timestamp}</div>
</div>

{insights_block}

<div class="kpi-row">
  <div class="kpi"><div class="kl">Замовлення місяць</div><div class="kv">{c_revenue}<span class="ku">₴</span></div><div class="ks">vs {p_revenue} ₴ · <span class="dlt {rev_d_cls}">{rev_d_txt}</span></div></div>
  <div class="kpi"><div class="kl">Замовлень місяць</div><div class="kv">{c_orders}</div><div class="ks">vs {p_orders} · <span class="dlt {ord_d_cls}">{ord_d_txt}</span></div></div>
  <div class="kpi"><div class="kl">Лідів місяць</div><div class="kv">{c_leads}</div><div class="ks">vs {p_leads} · <span class="dlt {led_d_cls}">{led_d_txt}</span></div></div>
  <div class="kpi"><div class="kl">Сер. чек</div><div class="kv">{c_avg_check}<span class="ku">₴</span></div><div class="ks">vs {p_avg_check} ₴ · <span class="dlt {chk_d_cls}">{chk_d_txt}</span></div></div>
  <div class="kpi"><div class="kl">Відмов</div><div class="kv">{c_refused}</div><div class="ks">{c_refuse_p_str} · vs {p_refuse_p_str} · <span class="dlt {ref_d_cls}">{ref_d_txt}</span></div></div>
  <div class="kpi"><div class="kl">Менеджерів</div><div class="kv">{managers_count}</div><div class="ks">активних</div></div>
  <div class="kpi"><div class="kl">Каналів</div><div class="kv">{sites_count}</div><div class="ks">продажу</div></div>
  <div class="kpi"><div class="kl">SKU товарів</div><div class="kv">{products_count}</div><div class="ks">унікальних</div></div>
  <div class="kpi"><div class="kl">ДРР Відгрузки</div><div class="kv" style="color:var(--drr-{curr_drr_sales_cls})">{curr_drr_sales}<span class="ku">%</span></div><div class="ks">vs {prev_drr_sales}% · <span class="dlt {drr_sales_delta_cls}">{drr_sales_delta_txt}</span></div></div>
  <div class="kpi"><div class="kl">ДРР Замовлення</div><div class="kv" style="color:var(--drr-{curr_drr_orders_cls})">{curr_drr_orders}<span class="ku">%</span></div><div class="ks">{curr_ad_spend} ₴ реклами · <span class="dlt {drr_orders_delta_cls}">{drr_orders_delta_txt}</span></div></div>
</div>

<div class="tabs">
  <button class="tab on" onclick="sw('overview', this)">📊 Огляд</button>
  <button class="tab" onclick="sw('crm', this)">👥 Менеджери</button>
  <button class="tab" onclick="sw('crmops', this)">🏭 Операції</button>
  <button class="tab" onclick="sw('channels', this)">🌐 Канали</button>
  <button class="tab" onclick="sw('products', this)">🛏️ Товари</button>
</div>

<div class="pnl on" id="p-overview"><h2 class="pnl-title">📊 Огляд</h2>
  <div class="cd">
    <div class="ct"><span class="dot"></span>📈 CRM SalesDrive — останні 3 місяці<span class="badge-tot" id="trend30Total"></span></div>
    <div class="cd-d">Stacked-бар: кожен день показує всі місяці накопичено. Наведіть курсор для порівняння.</div>
    <canvas id="chDaily" style="max-height:400px"></canvas>
    {multi_month_summary}
  </div>

  <div class="cd" style="margin-top:14px">
    <div class="ct"><span class="dot" style="background:var(--g)"></span>🏭 1С UH ORDERS — замовлення (всі статуси) · 3 місяці<span class="badge-tot" id="trend1cOrdTotal"></span></div>
    <div class="cd-d">Дані з 1С: всі замовлення (включно з відмовами). Stacked по місяцях, день-в-день.</div>
    <canvas id="ch1cOrders" style="max-height:380px"></canvas>
    {summary_1c_orders}
  </div>

  <div class="cd" style="margin-top:14px">
    <div class="ct"><span class="dot" style="background:var(--o)"></span>📦 1С UH SALES — фактичні відгрузки · 3 місяці<span class="badge-tot" id="trend1cSalTotal"></span></div>
    <div class="cd-d">Реальні відгрузки за днями. Stacked по місяцях, день-в-день.</div>
    <canvas id="ch1cSales" style="max-height:380px"></canvas>
    {summary_1c_sales}
  </div>
</div>

<div class="pnl" id="p-crm"><h2 class="pnl-title">👥 Менеджери</h2>
  <div class="cd">
    <div class="ct"><span class="dot"></span>🏆 Рейтинг менеджерів за місяць<span class="badge-tot">{managers_count} активних</span></div>
    <div class="cd-d">Дельта = зміна виручки vs попередній місяць.</div>
    <div class="scr">
      <table>
        <thead><tr><th>#</th><th>Менеджер</th><th class="r">Зам.</th><th class="r">Замовлення ₴</th><th class="r">Сер.чек</th><th class="r">Поп. міс.</th><th class="r">Δ</th><th class="r">% Відм.</th></tr></thead>
        <tbody id="mgrBody"></tbody>
      </table>
    </div>
  </div>

  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--c)"></span>🏪 Менеджери на магазині</div><div class="scr" style="max-height:300px"><table><thead><tr><th>Менеджер</th><th class="r">Зам.</th><th class="r">Замовлення ₴</th><th class="r">Сер.чек</th></tr></thead><tbody id="mgrShopBody"></tbody></table></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--p)"></span>💬 Чатери</div><div class="scr" style="max-height:300px"><table><thead><tr><th>Чатер</th><th class="r">Зам.</th><th class="r">Замовлення ₴</th></tr></thead><tbody id="chatterBody"></tbody></table></div></div>
  </div>
</div>

<div class="pnl" id="p-crmops"><h2 class="pnl-title">🏭 Операції</h2>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--p)"></span>📦 Категорії товарів</div><canvas id="chCategories"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--c)"></span>📞 Тип звернення</div><canvas id="chRequestTypes"></canvas></div>
  </div>
  <div class="g3">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--g)"></span>💳 Спосіб оплати</div><div id="paymentMethods"></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--o)"></span>🚚 Тип доставки</div><div id="deliveryTypes"></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--b)"></span>📮 Перевізник</div><div id="carriers"></div></div>
  </div>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--y)"></span>🏭 Склад</div><div id="warehouses"></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--ac2)"></span>📊 Статуси замовлень</div><canvas id="chStatuses" style="max-height:280px"></canvas></div>
  </div>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--r)"></span>🚫 Причини відмов</div><canvas id="chRefuse"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--o)"></span>🤔 Заперечення лідів</div><canvas id="chObjections"></canvas></div>
  </div>
</div>

<div class="pnl" id="p-channels"><h2 class="pnl-title">🌐 Канали</h2>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--g)"></span>🌐 Канали продажу — порівняння з попереднім<span class="badge-tot">{sites_count}</span></div>
    <div class="scr">
      <table>
        <thead><tr><th>#</th><th>Канал</th><th class="r">Зам.</th><th class="r">Замовлення ₴</th><th class="r">Сер.чек</th><th class="r">Поп. міс.</th><th class="r">Δ</th></tr></thead>
        <tbody id="sitesBody"></tbody>
      </table>
    </div>
  </div>
  <div class="cd"><div class="ct"><span class="dot"></span>📊 Графік замовлень</div><canvas id="chSites"></canvas></div>
</div>

<div class="pnl" id="p-products"><h2 class="pnl-title">🛏️ Товари</h2>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--lime)"></span>🛏️ ТОП-50 товарів за місяць<span class="badge-tot">{products_count} SKU</span></div>
    <div class="scr">
      <table>
        <thead><tr><th>#</th><th>Товар</th><th class="r">Од.</th><th class="r">Замовл.</th><th class="r">Замовлення ₴</th></tr></thead>
        <tbody id="prodBody"></tbody>
      </table>
    </div>
  </div>
</div>

<div class="ftr">UH Analytics · monthly · {timestamp}</div>

<script>
const D = {chart_json};
function sw(name, btn){{document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));document.querySelectorAll('.pnl').forEach(p=>p.classList.remove('on'));btn.classList.add('on');document.getElementById('p-'+name).classList.add('on');}}
Chart.defaults.color='#7b84a3';Chart.defaults.font.family="'DM Sans', sans-serif";Chart.defaults.font.size=10;
const COMMON={{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{labels:{{padding:10,usePointStyle:true,pointStyleWidth:8,font:{{size:10}}}}}},tooltip:{{backgroundColor:'#1c2137',borderColor:'#3a4170',borderWidth:1,padding:10}}}},scales:{{x:{{grid:{{color:'rgba(255,255,255,0.03)'}},ticks:{{maxRotation:45,font:{{size:9}}}}}},y:{{grid:{{color:'rgba(255,255,255,0.03)'}},ticks:{{font:{{size:9}},callback:v=>v>=1000?(v/1000).toFixed(0)+'K':v}}}}}}}};
const fmt=n=>{{n=Number(n)||0;const isInt=Number.isInteger(n);return n.toLocaleString('uk',{{minimumFractionDigits:isInt?0:2,maximumFractionDigits:2}}).replace(/\u00a0/g,' ').replace(',','.');}};
const fmtK=n=>{{n=Number(n)||0;if(n>=1e6)return(n/1e6).toFixed(2)+'M';if(n>=1e3)return(n/1e3).toFixed(0)+'K';return n.toFixed(0);}};

// === Multi-month trend chart (reusable for CRM, 1C ORDERS, 1C SALES) ===
function renderMultiMonthChart(canvasId, mm, opts) {{
  opts = opts || {{}};
  const palettes = opts.palette || ['rgba(120,140,180,0.55)', 'rgba(162,155,254,0.75)', 'rgba(108,92,231,0.95)'];
  const borders = opts.border || ['#7888b4', '#a29bfe', '#6c5ce7'];
  const showLeads = opts.showLeads !== false;
  const unit = opts.unit || ' ₴';
  const totalBadgeId = opts.totalBadgeId || null;

  const el = document.getElementById(canvasId);
  if (!el || !mm || !mm.length) {{
    if (el && el.parentElement) {{
      el.style.display = 'none';
      el.parentElement.insertAdjacentHTML('beforeend',
        '<div style="text-align:center;color:var(--td);padding:30px;font-size:12px">Немає даних для побудови графіка</div>');
    }}
    return;
  }}

  const maxDay = 31;
  const labels = Array.from({{length: maxDay}}, (_, i) => String(i+1).padStart(2,'0'));

  const datasets = mm.map((m, idx) => {{
    const byDay = {{}};
    (m.days || []).forEach(d => {{ byDay[d.day] = d; }});
    const revData = labels.map((_, i) => {{ const day = i+1; return byDay[day] ? byDay[day].revenue : 0; }});
    const ordersData = labels.map((_, i) => {{ const day = i+1; return byDay[day] ? byDay[day].orders : 0; }});
    const leadsData = labels.map((_, i) => {{ const day = i+1; return byDay[day] ? byDay[day].leads : 0; }});
    return {{
      type: 'bar', label: m.label, data: revData,
      _orders: ordersData, _leads: leadsData, _month: m.month,
      backgroundColor: palettes[idx] || palettes[0],
      borderColor: borders[idx] || borders[0],
      borderWidth: 1, borderRadius: 3,
      stack: 'months', order: mm.length - idx,
    }};
  }});

  const grandTotal = datasets.reduce((s, ds) => s + ds.data.reduce((a,b)=>a+b,0), 0);
  if (totalBadgeId) {{
    const badge = document.getElementById(totalBadgeId);
    if (badge) badge.textContent = '∑ ' + fmtK(grandTotal) + unit;
  }}

  new Chart(el, {{
    type: 'bar',
    data: {{ labels, datasets }},
    options: {{
      ...COMMON,
      scales: {{
        x: {{ ...COMMON.scales.x, stacked: true, title: {{ display: true, text: 'День місяця', color: '#7c869b', font: {{size:10}} }} }},
        y: {{ ...COMMON.scales.y, stacked: true, ticks: {{ ...COMMON.scales.y.ticks, callback: v => fmtK(v)+unit }} }}
      }},
      plugins: {{
        ...COMMON.plugins,
        legend: {{ position: 'top', labels: {{ color: '#cfd6e6', font: {{size: 11}}, usePointStyle: true, boxWidth: 10 }} }},
        tooltip: {{
          mode: 'index', intersect: false,
          backgroundColor: 'rgba(20,25,40,0.96)',
          borderColor: '#2b3247', borderWidth: 1, padding: 12,
          titleColor: '#fff', titleFont: {{size: 13, weight: 'bold'}},
          bodyColor: '#cfd6e6', bodyFont: {{size: 11}},
          callbacks: {{
            title: (items) => 'День ' + items[0].label,
            label: (ctx) => {{
              const ds = ctx.dataset;
              const rev = ctx.parsed.y;
              const orders = (ds._orders || [])[ctx.dataIndex] || 0;
              const leads = (ds._leads || [])[ctx.dataIndex] || 0;
              let s = ds.label + ': ' + fmtK(rev) + unit + ' · ' + orders + ' зам.';
              if (showLeads && leads) s += ' · ' + leads + ' лід';
              return s;
            }},
            afterBody: (items) => {{
              if (items.length < 2) return '';
              const sorted = items.slice().sort((a,b) => {{
                const ma = a.dataset._month || ''; const mb = b.dataset._month || '';
                return mb.localeCompare(ma);
              }});
              const out = ['', '— Порівняння —'];
              const newest = sorted[0];
              const newRev = newest.parsed.y;
              for (let i = 1; i < sorted.length; i++) {{
                const oldRev = sorted[i].parsed.y;
                if (oldRev === 0 && newRev === 0) {{ out.push(newest.dataset.label + ' vs ' + sorted[i].dataset.label + ': обидва порожні'); continue; }}
                if (oldRev === 0) {{ out.push(newest.dataset.label + ' vs ' + sorted[i].dataset.label + ': +∞ (попередній 0)'); continue; }}
                const diff = newRev - oldRev;
                const pct = (diff / oldRev * 100);
                const sign = diff >= 0 ? '↑' : '↓';
                out.push(newest.dataset.label + ' vs ' + sorted[i].dataset.label + ': ' + sign + ' ' + Math.abs(pct).toFixed(1) + '% (' + (diff>=0?'+':'') + fmtK(diff) + unit + ')');
              }}
              return out.join('\\n');
            }}
          }}
        }}
      }}
    }}
  }});
}}

// CRM (фіолетова палітра)
renderMultiMonthChart('chDaily', D.multi_month || [], {{ totalBadgeId: 'trend30Total' }});

// 1С UH ORDERS — зелена палітра
renderMultiMonthChart('ch1cOrders', (D.multi_month_1c_uh && D.multi_month_1c_uh.ORDERS) || [], {{
  totalBadgeId: 'trend1cOrdTotal',
  showLeads: false,
  palette: ['rgba(100,160,140,0.55)', 'rgba(100,200,170,0.75)', 'rgba(0,214,143,0.95)'],
  border:  ['#64a08c', '#64c8aa', '#00d68f'],
}});

// 1С UH SALES — оранжева палітра
renderMultiMonthChart('ch1cSales', (D.multi_month_1c_uh && D.multi_month_1c_uh.SALES) || [], {{
  totalBadgeId: 'trend1cSalTotal',
  showLeads: false,
  palette: ['rgba(180,140,100,0.55)', 'rgba(220,170,120,0.75)', 'rgba(255,169,77,0.95)'],
  border:  ['#b48c64', '#dcaa78', '#ffa94d'],
}});

// Managers
const mgrBody=document.getElementById('mgrBody');
if(D.managers&&D.managers.length){{mgrBody.innerHTML=D.managers.map((m,i)=>{{const refClass=m.refuse_pct>=12?'br':m.refuse_pct>=5?'bo':'bg';const dCls=m.delta_cls||'neu';return `<tr><td class="num" style="color:var(--td)">${{i+1}}</td><td>${{m.name}}</td><td class="r num">${{m.orders}}</td><td class="r num" style="color:var(--g)">${{fmtK(m.revenue)}}</td><td class="r num">${{fmt(m.avg_check||0)}}</td><td class="r num" style="color:var(--td)">${{fmtK(m.prev_revenue||0)}}</td><td class="r"><span class="dlt ${{dCls}}">${{m.delta_txt}}</span></td><td class="r"><span class="badge ${{refClass}}">${{(m.refuse_pct||0).toFixed(1)}}%</span></td></tr>`;}}).join('');}}else{{mgrBody.innerHTML='<tr><td colspan="8" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

const mgrShopBody=document.getElementById('mgrShopBody');
if(D.managers_shop&&D.managers_shop.length){{mgrShopBody.innerHTML=D.managers_shop.map(m=>`<tr><td>${{m.name}}</td><td class="r num">${{m.orders}}</td><td class="r num" style="color:var(--g)">${{fmtK(m.revenue)}}</td><td class="r num">${{fmt(m.avg_check||0)}}</td></tr>`).join('');}}else{{mgrShopBody.innerHTML='<tr><td colspan="4" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

const chatterBody=document.getElementById('chatterBody');
if(D.chatters&&D.chatters.length){{chatterBody.innerHTML=D.chatters.map(c=>`<tr><td>${{c.name}}</td><td class="r num">${{c.orders}}</td><td class="r num" style="color:var(--g)">${{fmtK(c.revenue)}}</td></tr>`).join('');}}else{{chatterBody.innerHTML='<tr><td colspan="3" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

// Pie charts
function pieChart(elId,dataObj){{const el=document.getElementById(elId);if(!el)return;const palette=['#6c5ce7','#a29bfe','#00d68f','#ffa94d','#339af0','#ff6b6b','#da77f2','#66d9e8','#94d82d','#ffd43b','#fd7e14','#94d2bd'];const entries=Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]).slice(0,12);if(!entries.length){{el.parentElement.insertAdjacentHTML('beforeend','<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>');el.style.display='none';return;}}new Chart(el,{{type:'doughnut',data:{{labels:entries.map(e=>e[0]),datasets:[{{data:entries.map(e=>e[1]),backgroundColor:palette,borderWidth:2,borderColor:'#151929'}}]}},options:{{...COMMON,scales:{{}},cutout:'55%',plugins:{{...COMMON.plugins,legend:{{position:'right',labels:{{font:{{size:9}},padding:6,usePointStyle:true,boxWidth:8}}}}}}}}}});}}
pieChart('chCategories',D.categories);pieChart('chRequestTypes',D.request_types);pieChart('chStatuses',D.statuses);

function listChart(elId,dataObj,color){{const el=document.getElementById(elId);if(!el)return;const entries=Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]);if(!entries.length){{el.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>';return;}}const max=entries[0][1]||1;el.innerHTML=entries.map(([n,v])=>{{const p=Math.max(2,Math.round(v/max*100));return `<div class="bar-row"><div class="bar-name" title="${{n}}">${{n}}</div><div class="bar-wrap"><div class="bar-fill" style="width:${{p}}%;background:${{color}}"></div></div><div class="bar-val">${{v}}</div></div>`;}}).join('');}}
listChart('paymentMethods',D.payment_methods,'#00d68f');listChart('deliveryTypes',D.delivery_types,'#ffa94d');
listChart('carriers',D.carriers,'#339af0');listChart('warehouses',D.warehouses,'#ffd43b');

function barChartH(elId,dataObj,color){{const el=document.getElementById(elId);if(!el)return;const entries=Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]).slice(0,10);if(!entries.length){{el.parentElement.insertAdjacentHTML('beforeend','<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>');el.style.display='none';return;}}new Chart(el,{{type:'bar',data:{{labels:entries.map(e=>e[0].length>30?e[0].substr(0,30)+'…':e[0]),datasets:[{{label:'К-сть',data:entries.map(e=>e[1]),backgroundColor:color+'aa',borderColor:color,borderWidth:1,borderRadius:4}}]}},options:{{...COMMON,indexAxis:'y',plugins:{{...COMMON.plugins,legend:{{display:false}}}}}}}});}}
barChartH('chRefuse',D.refuse_reasons,'#ff6b6b');barChartH('chObjections',D.lead_objections,'#ffa94d');

// Sites
const sitesBody=document.getElementById('sitesBody');
if(D.sites&&D.sites.length){{sitesBody.innerHTML=D.sites.map((s,i)=>{{const dCls=s.delta_cls||'neu';return `<tr><td class="num" style="color:var(--td)">${{i+1}}</td><td>${{s.name}}</td><td class="r num">${{s.orders}}</td><td class="r num" style="color:var(--g)">${{fmtK(s.revenue)}}</td><td class="r num">${{fmt(s.avg_check||0)}}</td><td class="r num" style="color:var(--td)">${{fmtK(s.prev_revenue||0)}}</td><td class="r"><span class="dlt ${{dCls}}">${{s.delta_txt}}</span></td></tr>`;}}).join('');new Chart(document.getElementById('chSites'),{{type:'bar',data:{{labels:D.sites.map(s=>s.name),datasets:[{{label:'Замовлення',data:D.sites.map(s=>s.revenue),backgroundColor:'rgba(0,214,143,0.7)',borderColor:'#00d68f',borderRadius:4}}]}},options:{{...COMMON,plugins:{{...COMMON.plugins,legend:{{display:false}}}},indexAxis:'y'}}}});}}else{{sitesBody.innerHTML='<tr><td colspan="7" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

// Products
const prodBody=document.getElementById('prodBody');
if(D.products&&D.products.length){{prodBody.innerHTML=D.products.map((p,i)=>`<tr><td class="num" style="color:var(--td)">${{i+1}}</td><td title="${{p.name}}">${{p.name.length>70?p.name.substr(0,70)+'…':p.name}}</td><td class="r num">${{p.qty||p.count}}</td><td class="r num" style="color:var(--td)">${{p.count}}</td><td class="r num" style="color:var(--g)">${{fmtK(p.revenue)}}</td></tr>`).join('');}}else{{prodBody.innerHTML='<tr><td colspan="5" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';}}

// === PDF EXPORT (по панелях, без зміщення сторінок) ===
async function exportPDF() {{
  console.log('[PDF] Старт експорту');
  const btn = document.getElementById('pdfBtn');
  if (!btn) {{ console.error('[PDF] Кнопка #pdfBtn не знайдена'); return; }}

  // Перевірка наявності бібліотек
  if (typeof html2canvas === 'undefined') {{
    alert('html2canvas не завантажився. Перезавантаж сторінку (Ctrl+F5).');
    console.error('[PDF] html2canvas undefined');
    return;
  }}
  if (!window.jspdf || !window.jspdf.jsPDF) {{
    alert('jsPDF не завантажився. Перезавантаж сторінку (Ctrl+F5).');
    console.error('[PDF] window.jspdf undefined');
    return;
  }}

  const originalHTML = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="ic">⏳</span><span>Готую PDF...</span>';

  // Включаємо PDF-режим — показуємо всі панелі
  document.body.classList.add('pdf-mode');
  await new Promise(r => setTimeout(r, 600)); // дай чартам перерендеритись
  console.log('[PDF] PDF-режим увімкнено');

  const today = new Date();
  const stamp = today.getFullYear() + '-' + String(today.getMonth()+1).padStart(2,'0') + '-' + String(today.getDate()).padStart(2,'0');
  const isMonthly = document.title.includes('Monthly');
  const fileName = (isMonthly ? 'UH_Monthly_' : 'UH_Daily_') + stamp + '.pdf';

  // Збираємо все що треба в PDF: шапка + KPI + всі панелі
  const sections = [];
  const hdr = document.querySelector('.hdr');
  const kpiRow = document.querySelector('.kpi-row');
  const insWrap = document.querySelector('.ins-wrap');

  // Перша сторінка: шапка + інсайти + KPI
  const firstWrap = document.createElement('div');
  firstWrap.style.background = 'var(--bg, #0c0f1a)';
  firstWrap.style.padding = '0';
  if (hdr) firstWrap.appendChild(hdr.cloneNode(true));
  if (insWrap) firstWrap.appendChild(insWrap.cloneNode(true));
  if (kpiRow) firstWrap.appendChild(kpiRow.cloneNode(true));
  sections.push(firstWrap);

  // Кожна панель — окрема сторінка
  document.querySelectorAll('.pnl').forEach(p => sections.push(p));

  // Готуємо jsPDF (a3 landscape)
  const {{ jsPDF }} = window.jspdf;
  const pdf = new jsPDF({{ unit: 'mm', format: 'a3', orientation: 'landscape', compress: true }});
  const pageW = pdf.internal.pageSize.getWidth();   // 420
  const pageH = pdf.internal.pageSize.getHeight();  // 297
  const margin = 8;
  const usableW = pageW - margin * 2;
  const usableH = pageH - margin * 2;

  // Тимчасово підставимо контейнер для рендеру (поза вʼюпортом, але з фіксованою шириною)
  const stage = document.createElement('div');
  stage.style.position = 'fixed';
  stage.style.left = '-99999px';
  stage.style.top = '0';
  stage.style.width = '1400px';
  stage.style.background = '#0c0f1a';
  stage.style.padding = '20px';
  document.body.appendChild(stage);

  try {{
    console.log('[PDF] Рендерю ' + sections.length + ' секцій...');
    for (let i = 0; i < sections.length; i++) {{
      const node = sections[i].cloneNode(true);
      stage.innerHTML = '';
      stage.appendChild(node);
      // Дай DOM перемалюватись
      await new Promise(r => setTimeout(r, 80));
      console.log('[PDF] Секція ' + (i+1) + '/' + sections.length);

      const canvas = await html2canvas(stage, {{
        scale: 1.5,
        useCORS: true,
        backgroundColor: '#0c0f1a',
        logging: false,
        windowWidth: 1440,
      }});

      const imgData = canvas.toDataURL('image/jpeg', 0.92);
      // Скейлимо щоб влізло у сторінку зі збереженням пропорцій
      const ratio = canvas.height / canvas.width;
      let imgW = usableW;
      let imgH = imgW * ratio;
      if (imgH > usableH) {{
        imgH = usableH;
        imgW = imgH / ratio;
      }}
      const x = (pageW - imgW) / 2;
      const y = margin;

      if (i > 0) pdf.addPage();
      pdf.addImage(imgData, 'JPEG', x, y, imgW, imgH);
    }}

    pdf.save(fileName);
  }} catch (e) {{
    console.error('PDF export error:', e);
    alert('Помилка експорту PDF: ' + (e.message || e));
  }} finally {{
    stage.remove();
    document.body.classList.remove('pdf-mode');
    btn.disabled = false;
    btn.innerHTML = originalHTML;
  }}
}}
</script>
</body></html>
'''


# ──────────────────── MAIN ────────────────────
def main():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"\n📊 Генерація дашбордів за {yesterday}")

    data = load_data(yesterday)
    if not data:
        print(f"❌ Файл history/{yesterday}.json не знайдено")
        return

    history = load_history(30)
    print(f"   📂 Завантажено історію: {len(history)} днів")

    # Денний дашборд
    print(f"\n   📊 Генерація index.html (денний)...")
    daily_html = build_daily(data, history)
    with open(DOCS_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(daily_html)

    # Архів денного
    archive_dir = DOCS_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)
    with open(archive_dir / f"{yesterday}.html", "w", encoding="utf-8") as f:
        f.write(daily_html)

    # Місячний дашборд
    print(f"   📅 Генерація month.html (місячний)...")
    monthly_html = build_monthly(data, history)
    with open(DOCS_DIR / "month.html", "w", encoding="utf-8") as f:
        f.write(monthly_html)

    # Архів місячного по місяцях
    target_month = data.get("month", {}).get("target_month", yesterday[:7])
    monthly_archive = archive_dir / f"month-{target_month}.html"
    with open(monthly_archive, "w", encoding="utf-8") as f:
        f.write(monthly_html)

    print(f"\n✅ Згенеровано:")
    print(f"   → docs/index.html (день)")
    print(f"   → docs/month.html (місяць)")
    print(f"   → docs/archive/{yesterday}.html")
    print(f"   → docs/archive/month-{target_month}.html\n")
    print(f"🌐 День:   https://grigorijtetlasov-uh.github.io/uh-analytics/")
    print(f"🌐 Місяць: https://grigorijtetlasov-uh.github.io/uh-analytics/month.html\n")


if __name__ == "__main__":
    main()
