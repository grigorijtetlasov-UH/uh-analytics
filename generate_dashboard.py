"""
generate_dashboard.py — Executive dashboard generator
Стиль: UH темний дашборд, директорський рівень деталізації
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta

HISTORY_DIR = Path("history")
DOCS_DIR    = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)

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


def build_html(data, history):
    date_disp = data.get("date_disp", "—")
    month_str = data.get("month", "—")
    uh   = data.get("uh", {})
    sh   = data.get("sh", {})
    crm  = data.get("crm", {})
    ga4  = data.get("ga4", {})
    meta = data.get("meta", {})

    uh_orders_d = uh.get("ORDERS", {}).get("day", {}).get("total", 0)
    sh_orders_d = sh.get("ORDERS", {}).get("day", {}).get("total", 0)
    uh_sales_d  = uh.get("SALES",  {}).get("day", {}).get("total", 0)
    sh_sales_d  = sh.get("SALES",  {}).get("day", {}).get("total", 0)
    uh_orders_m = uh.get("ORDERS", {}).get("month", {}).get("total", 0)
    sh_orders_m = sh.get("ORDERS", {}).get("month", {}).get("total", 0)
    uh_sales_m  = uh.get("SALES",  {}).get("month", {}).get("total", 0)
    sh_sales_m  = sh.get("SALES",  {}).get("month", {}).get("total", 0)

    total_revenue_d = uh_orders_d + sh_orders_d
    total_sales_d   = uh_sales_d + sh_sales_d
    total_revenue_m = uh_orders_m + sh_orders_m
    total_sales_m   = uh_sales_m + sh_sales_m

    crm_o   = crm.get("orders", {})
    crm_l   = crm.get("leads", {})
    crm_orders_d  = crm_o.get("total", 0)
    crm_revenue_d = crm_o.get("revenue", 0)
    crm_leads_d   = crm_l.get("new_leads", 0)
    crm_refuse_p  = crm_o.get("refuse_pct", 0)
    crm_avg_check = crm_o.get("avg_check", 0)

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

    roas = round(total_revenue_d / max(meta_spend, 1), 2) if meta_spend > 0 else 0
    site_conv = round(crm_orders_d / max(ga4_sessions, 1) * 100, 2) if ga4_sessions > 0 else 0

    prev_data = history[-2] if len(history) >= 2 else None
    prev_revenue = (prev_data.get("uh", {}).get("ORDERS", {}).get("day", {}).get("total", 0) +
                    prev_data.get("sh", {}).get("ORDERS", {}).get("day", {}).get("total", 0)) if prev_data else 0
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
    trend_refused  = [t["refused"] for t in crm_trend]

    hist_dates, hist_uh, hist_sh, hist_uh_s, hist_sh_s, hist_meta, hist_ga4, hist_crm = [], [], [], [], [], [], [], []
    for h in history:
        d = h.get("date", "")
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            hist_dates.append(dt.strftime("%d.%m"))
        except: hist_dates.append(d)
        hist_uh.append(h.get("uh", {}).get("ORDERS", {}).get("day", {}).get("total", 0))
        hist_sh.append(h.get("sh", {}).get("ORDERS", {}).get("day", {}).get("total", 0))
        hist_uh_s.append(h.get("uh", {}).get("SALES", {}).get("day", {}).get("total", 0))
        hist_sh_s.append(h.get("sh", {}).get("SALES", {}).get("day", {}).get("total", 0))
        hist_meta.append(h.get("meta", {}).get("total", {}).get("spend", 0))
        hist_ga4.append(h.get("ga4", {}).get("sessions", 0))
        hist_crm.append(h.get("crm", {}).get("orders", {}).get("total", 0))

    insights = []
    if rev_delta_cls == "up":
        insights.append({"icon": "🚀", "type": "good", "text": f"Виручка зросла на {rev_delta_txt} порівняно з попереднім днем"})
    elif rev_delta_cls == "down":
        insights.append({"icon": "⚠️", "type": "warn", "text": f"Виручка впала на {rev_delta_txt} — варто розібратись"})

    if crm_refuse_p > 8:
        insights.append({"icon": "🔴", "type": "bad", "text": f"Висока частка відмов: {crm_refuse_p}% (норма <5%)"})
    elif crm_refuse_p < 3 and crm_orders_d > 0:
        insights.append({"icon": "✅", "type": "good", "text": f"Відмінні відмови: лише {crm_refuse_p}%"})

    if roas > 0 and roas >= 5:
        insights.append({"icon": "💎", "type": "good", "text": f"Чудовий ROAS: {roas}× (на 1₴ реклами {roas}₴ виручки)"})
    elif roas > 0 and roas < 2:
        insights.append({"icon": "📉", "type": "warn", "text": f"Низький ROAS: {roas}× — реклама працює неефективно"})

    managers = crm.get("managers", [])
    if managers:
        top_mgr = managers[0]
        insights.append({"icon": "🏆", "type": "info",
                         "text": f"Топ менеджер дня: {top_mgr['name']} — {money(top_mgr['revenue'])} ₴ ({top_mgr['orders']} зам.)"})

    sites = crm.get("sites", {})
    if sites:
        top_site = max(sites.items(), key=lambda x: x[1]["revenue"])
        insights.append({"icon": "🌐", "type": "info",
                         "text": f"Топ канал: {top_site[0]} — {money(top_site[1]['revenue'])} ₴"})

    if meta.get("by_campaign"):
        top_camp = meta["by_campaign"][0]
        camp_name = top_camp['campaign'][:50]
        insights.append({"icon": "📱", "type": "info",
                         "text": f"Топ кампанія: {camp_name} — {money(top_camp['spend'])} ₴ витрат"})

    chart_data = {
        "trend_dates":    trend_dates,
        "trend_revenue":  trend_revenue,
        "trend_orders":   trend_orders,
        "trend_leads":    trend_leads,
        "trend_refused":  trend_refused,
        "hist_dates":     hist_dates,
        "hist_uh":        hist_uh,
        "hist_sh":        hist_sh,
        "hist_uh_s":      hist_uh_s,
        "hist_sh_s":      hist_sh_s,
        "hist_meta":      hist_meta,
        "hist_ga4":       hist_ga4,
        "hist_crm":       hist_crm,
        "uh_orders_podr": uh.get("ORDERS", {}).get("day", {}).get("by_podr", {}),
        "sh_orders_podr": sh.get("ORDERS", {}).get("day", {}).get("by_podr", {}),
        "uh_sales_podr":  uh.get("SALES", {}).get("day", {}).get("by_podr", {}),
        "sh_sales_podr":  sh.get("SALES", {}).get("day", {}).get("by_podr", {}),
        "managers":       managers,
        "managers_shop":  crm.get("managers_shop", []),
        "chatters":       crm.get("chatters", []),
        "sites":          sites,
        "products":       crm.get("products", []),
        "categories":     crm.get("categories", {}),
        "request_types":  crm.get("request_types", {}),
        "payment_methods": crm.get("payment_methods", {}),
        "delivery_types": crm.get("delivery_types", {}),
        "carriers":       crm.get("carriers", {}),
        "warehouses":     crm.get("warehouses", {}),
        "statuses":       crm.get("statuses", {}),
        "refuse_reasons": crm.get("refuse_reasons", {}),
        "lead_objections": crm.get("lead_objections", {}),
        "process_reasons": crm.get("process_reasons", {}),
        "meta_camps":     meta.get("by_campaign", []),
        "meta_accounts":  meta.get("accounts", []),
        "ga4_sources":    ga4.get("by_source", []),
        "ga4_pages":      ga4.get("by_page", []),
        "ga4_devices":    ga4.get("by_device", []),
    }
    chart_json = json.dumps(chart_data, ensure_ascii=False)

    insights_html = "".join([
        f'<div class="ins ins-{i["type"]}"><span class="ins-ico">{i["icon"]}</span><span class="ins-txt">{i["text"]}</span></div>'
        for i in insights
    ])

    insights_block = f'<div class="ins-wrap">{insights_html}</div>' if insights else ""
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    avg_dur_str = f'{int(ga4_avg_dur//60)}:{int(ga4_avg_dur%60):02d}'

    return f'''<!DOCTYPE html>
<html lang="uk"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>UH — Executive Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{{--bg:#0c0f1a;--s:#151929;--s2:#1c2137;--s3:#242b47;--brd:#2a3050;--brd2:#3a4170;--t:#e4e8f7;--t2:#c1c7e0;--td:#7b84a3;--td2:#5a6280;--ac:#6c5ce7;--ac2:#a29bfe;--g:#00d68f;--gd:rgba(0,214,143,.15);--o:#ffa94d;--od:rgba(255,169,77,.15);--r:#ff6b6b;--rd:rgba(255,107,107,.15);--b:#339af0;--bd:rgba(51,154,240,.15);--y:#ffd43b;--p:#da77f2;--c:#66d9e8;--lime:#94d82d}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--t);min-height:100vh;padding:14px 18px;font-size:12px;line-height:1.4}}
.hdr{{text-align:center;margin-bottom:8px}}
.hdr h1{{font-size:24px;font-weight:700;background:linear-gradient(135deg,var(--ac2),var(--g));-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-0.5px}}
.hdr .sub{{color:var(--td);font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-top:3px}}
.hdr .stamp{{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--td2);margin-top:4px;padding:2px 8px;background:var(--s);border:1px solid var(--brd);border-radius:10px}}
.ins-wrap{{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}}
.ins{{flex:1;min-width:240px;background:var(--s);border:1px solid var(--brd);border-radius:9px;padding:8px 12px;display:flex;align-items:center;gap:8px;font-size:11px}}
.ins-ico{{font-size:14px;flex-shrink:0}}
.ins-txt{{color:var(--t2);line-height:1.3}}
.ins-good{{border-left:3px solid var(--g)}}
.ins-warn{{border-left:3px solid var(--o)}}
.ins-bad{{border-left:3px solid var(--r)}}
.ins-info{{border-left:3px solid var(--b)}}
.kpi-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:9px;margin-bottom:14px}}
.kpi{{background:var(--s);border:1px solid var(--brd);border-radius:11px;padding:12px 11px;position:relative;overflow:hidden}}
.kpi::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:11px 11px 0 0}}
.kpi:nth-child(1)::before{{background:linear-gradient(90deg,var(--ac),var(--ac2))}}
.kpi:nth-child(2)::before{{background:var(--g)}}
.kpi:nth-child(3)::before{{background:var(--o)}}
.kpi:nth-child(4)::before{{background:var(--b)}}
.kpi:nth-child(5)::before{{background:var(--p)}}
.kpi:nth-child(6)::before{{background:var(--c)}}
.kpi:nth-child(7)::before{{background:var(--r)}}
.kpi:nth-child(8)::before{{background:var(--lime)}}
.kl{{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--td);margin-bottom:3px;font-weight:500}}
.kv{{font-family:'JetBrains Mono',monospace;font-size:19px;font-weight:600;line-height:1.1}}
.ku{{font-size:9px;color:var(--td);margin-left:3px;font-family:'DM Sans'}}
.ks{{font-size:9px;color:var(--td);margin-top:3px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
.dlt{{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:600;padding:1px 5px;border-radius:4px}}
.dlt.up{{background:var(--gd);color:var(--g)}}
.dlt.down{{background:var(--rd);color:var(--r)}}
.dlt.neu{{background:rgba(123,132,163,.15);color:var(--td)}}
.tabs{{display:flex;gap:2px;margin-bottom:14px;background:var(--s);border-radius:10px;padding:3px;border:1px solid var(--brd);flex-wrap:wrap}}
.tab{{flex:1;min-width:110px;padding:9px 6px;border-radius:8px;text-align:center;cursor:pointer;font-size:11px;font-weight:500;color:var(--td);border:none;background:none;transition:.15s;letter-spacing:.3px}}
.tab:hover{{color:var(--t);background:var(--s2)}}
.tab.on{{background:var(--ac);color:#fff}}
.pnl{{display:none}}
.pnl.on{{display:block;animation:fade .2s ease-in}}
@keyframes fade{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
.cd{{background:var(--s);border:1px solid var(--brd);border-radius:11px;padding:14px;margin-bottom:11px}}
.ct{{font-size:12px;font-weight:600;margin-bottom:5px;display:flex;align-items:center;gap:7px}}
.ct .dot{{width:7px;height:7px;border-radius:50%;background:var(--ac);flex-shrink:0}}
.ct .badge-tot{{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:500;color:var(--td);margin-left:auto;padding:2px 8px;background:var(--s2);border-radius:5px}}
.cd-d{{font-size:10px;color:var(--td);margin-bottom:11px;line-height:1.4}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:11px}}
.g3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:11px;margin-bottom:11px}}
.g4{{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;margin-bottom:11px}}
@media(max-width:980px){{.g2,.g3,.g4{{grid-template-columns:1fr}}}}
canvas{{max-height:280px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:var(--s2);padding:7px 9px;text-align:left;font-weight:600;color:var(--td);font-size:9px;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap;border-bottom:1px solid var(--brd)}}
th.r,td.r{{text-align:right}}
td{{padding:6px 9px;border-bottom:1px solid rgba(255,255,255,.04)}}
tbody tr:hover td{{background:rgba(108,92,231,.06)}}
.scr{{max-height:420px;overflow-y:auto}}
.scr::-webkit-scrollbar{{width:5px}}
.scr::-webkit-scrollbar-thumb{{background:var(--brd2);border-radius:3px}}
.scr::-webkit-scrollbar-track{{background:var(--s2)}}
.badge{{display:inline-block;padding:2px 7px;border-radius:5px;font-size:9px;font-weight:600;letter-spacing:.2px}}
.bg{{background:var(--gd);color:var(--g)}}.bo{{background:var(--od);color:var(--o)}}
.br{{background:var(--rd);color:var(--r)}}.bb{{background:var(--bd);color:var(--b)}}
.num{{font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:500}}
.bar-row{{display:flex;align-items:center;gap:9px;padding:5px 11px;border-bottom:1px solid rgba(255,255,255,.03)}}
.bar-row:last-child{{border-bottom:none}}
.bar-name{{font-size:11px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px}}
.bar-wrap{{flex:2;background:var(--s2);border-radius:3px;height:6px;overflow:hidden;min-width:60px}}
.bar-fill{{height:100%;background:linear-gradient(90deg,var(--ac),var(--ac2));border-radius:3px;transition:width 1s cubic-bezier(.4,0,.2,1)}}
.bar-val{{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:600;width:90px;text-align:right;color:var(--t2)}}
.mini-kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:8px;margin-bottom:11px}}
.mk{{background:var(--s2);border:1px solid var(--brd);border-radius:8px;padding:9px;text-align:center}}
.mk-l{{font-size:8px;text-transform:uppercase;letter-spacing:.5px;color:var(--td);margin-bottom:3px}}
.mk-v{{font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:600}}
.ftr{{text-align:center;color:var(--td2);font-size:10px;padding-top:18px;border-top:1px solid var(--brd);margin-top:24px;font-family:'JetBrains Mono',monospace}}
</style></head>
<body>

<div class="hdr">
  <h1>UH Executive Dashboard</h1>
  <div class="sub">United Home · {date_disp}</div>
  <div class="stamp">Період місяця: {month_str} · оновлено {timestamp}</div>
</div>

{insights_block}

<div class="kpi-row">
  <div class="kpi">
    <div class="kl">Замовлення день</div>
    <div class="kv">{money(total_revenue_d)}<span class="ku">₴</span></div>
    <div class="ks">UH+SH · <span class="dlt {rev_delta_cls}">{rev_delta_txt}</span></div>
  </div>
  <div class="kpi">
    <div class="kl">Відгрузки день</div>
    <div class="kv">{money(total_sales_d)}<span class="ku">₴</span></div>
    <div class="ks">UH+SH відгружено</div>
  </div>
  <div class="kpi">
    <div class="kl">Замовлення місяць</div>
    <div class="kv">{money_k(total_revenue_m)}<span class="ku">₴</span></div>
    <div class="ks">сум. з 1-го числа</div>
  </div>
  <div class="kpi">
    <div class="kl">CRM Заявки</div>
    <div class="kv">{crm_orders_d}</div>
    <div class="ks">{crm_leads_d} лідів · <span class="dlt {ord_delta_cls}">{ord_delta_txt}</span></div>
  </div>
  <div class="kpi">
    <div class="kl">Сер. чек CRM</div>
    <div class="kv">{money(crm_avg_check)}<span class="ku">₴</span></div>
    <div class="ks">{pct(crm_refuse_p)} відмов</div>
  </div>
  <div class="kpi">
    <div class="kl">ROAS</div>
    <div class="kv">{roas}<span class="ku">×</span></div>
    <div class="ks">виручка/витрати реклами</div>
  </div>
  <div class="kpi">
    <div class="kl">GA4 Сесії</div>
    <div class="kv">{money(ga4_sessions)}</div>
    <div class="ks">{pct(ga4_bounce)} відмов · <span class="dlt {ses_delta_cls}">{ses_delta_txt}</span></div>
  </div>
  <div class="kpi">
    <div class="kl">Meta Витрати</div>
    <div class="kv">{money(meta_spend)}<span class="ku">₴</span></div>
    <div class="ks">{meta_results} результатів · <span class="dlt {meta_delta_cls}">{meta_delta_txt}</span></div>
  </div>
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

<div class="pnl on" id="p-overview">
  <div class="cd">
    <div class="ct"><span class="dot"></span>Динаміка виручки CRM — 30 днів<span class="badge-tot" id="trend30Total"></span></div>
    <div class="cd-d">Виручка по днях з SalesDrive (без спаму). Темна область — замовлення, лінія — ліди.</div>
    <canvas id="chTrend30"></canvas>
  </div>
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--ac)"></span>Замовлення UH+SH (1С)</div>
      <canvas id="chOrders"></canvas>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--g)"></span>Відгрузки UH+SH (1С)</div>
      <canvas id="chSales"></canvas>
    </div>
  </div>
  <div class="g3">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--b)"></span>GA4 Сесії</div><canvas id="chGa4" style="max-height:200px"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--o)"></span>Meta Витрати</div><canvas id="chMeta" style="max-height:200px"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--p)"></span>Заявки CRM</div><canvas id="chCrmOrd" style="max-height:200px"></canvas></div>
  </div>
</div>

<div class="pnl" id="p-sales1c">
  <div class="mini-kpi">
    <div class="mk"><div class="mk-l">UH ORDERS день</div><div class="mk-v" style="color:var(--ac)">{money_k(uh_orders_d)}</div></div>
    <div class="mk"><div class="mk-l">SH ORDERS день</div><div class="mk-v" style="color:var(--g)">{money_k(sh_orders_d)}</div></div>
    <div class="mk"><div class="mk-l">UH SALES день</div><div class="mk-v" style="color:var(--o)">{money_k(uh_sales_d)}</div></div>
    <div class="mk"><div class="mk-l">SH SALES день</div><div class="mk-v" style="color:var(--r)">{money_k(sh_sales_d)}</div></div>
    <div class="mk"><div class="mk-l">UH ORDERS міс.</div><div class="mk-v" style="color:var(--ac)">{money_k(uh_orders_m)}</div></div>
    <div class="mk"><div class="mk-l">SH ORDERS міс.</div><div class="mk-v" style="color:var(--g)">{money_k(sh_orders_m)}</div></div>
    <div class="mk"><div class="mk-l">UH SALES міс.</div><div class="mk-v" style="color:var(--o)">{money_k(uh_sales_m)}</div></div>
    <div class="mk"><div class="mk-l">SH SALES міс.</div><div class="mk-v" style="color:var(--r)">{money_k(sh_sales_m)}</div></div>
  </div>
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--ac)"></span>UH Замовлення по підрозділах<span class="badge-tot">{money(uh_orders_d)} ₴</span></div>
      <div id="uhOrdPodr"></div>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--g)"></span>SH Замовлення по підрозділах<span class="badge-tot">{money(sh_orders_d)} ₴</span></div>
      <div id="shOrdPodr"></div>
    </div>
  </div>
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--o)"></span>UH Відгрузки по підрозділах<span class="badge-tot">{money(uh_sales_d)} ₴</span></div>
      <div id="uhSalPodr"></div>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--r)"></span>SH Відгрузки по підрозділах<span class="badge-tot">{money(sh_sales_d)} ₴</span></div>
      <div id="shSalPodr"></div>
    </div>
  </div>
</div>

<div class="pnl" id="p-crm">
  <div class="mini-kpi">
    <div class="mk"><div class="mk-l">Усього менеджерів</div><div class="mk-v">{len(managers)}</div></div>
    <div class="mk"><div class="mk-l">Магазин</div><div class="mk-v">{len(crm.get("managers_shop", []))}</div></div>
    <div class="mk"><div class="mk-l">Чатери</div><div class="mk-v">{len(crm.get("chatters", []))}</div></div>
    <div class="mk"><div class="mk-l">Виручка усіх</div><div class="mk-v">{money_k(crm_revenue_d)}</div></div>
    <div class="mk"><div class="mk-l">Сер. чек</div><div class="mk-v">{money(crm_avg_check)}</div></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot"></span>🏆 Рейтинг менеджерів (онлайн)<span class="badge-tot">{len(managers)} активних</span></div>
    <div class="cd-d">Замовлення = order+refused, Конв. = orders/(orders+leads). Сортовано за виручкою.</div>
    <div class="scr">
      <table>
        <thead><tr>
          <th>#</th><th>Менеджер</th><th class="r">Зам.</th><th class="r">Ліди</th>
          <th class="r">Виручка</th><th class="r">Сер.чек</th><th class="r">Конв.</th>
          <th class="r">Відмов</th><th class="r">% Відм.</th>
        </tr></thead>
        <tbody id="mgrBody"></tbody>
      </table>
    </div>
  </div>
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--c)"></span>🏪 Менеджери на магазині</div>
      <div class="scr" style="max-height:300px">
        <table>
          <thead><tr><th>Менеджер</th><th class="r">Зам.</th><th class="r">Виручка</th><th class="r">Сер.чек</th></tr></thead>
          <tbody id="mgrShopBody"></tbody>
        </table>
      </div>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--p)"></span>💬 Чатери</div>
      <div class="scr" style="max-height:300px">
        <table>
          <thead><tr><th>Чатер</th><th class="r">Зам.</th><th class="r">Виручка</th></tr></thead>
          <tbody id="chatterBody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<div class="pnl" id="p-crmops">
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--p)"></span>📦 Категорії товарів (звернень)</div><div class="cd-d">Що замовляють: топери, матраци, дивани, аксесуари.</div><canvas id="chCategories"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--c)"></span>📞 Тип звернення</div><div class="cd-d">Корзина / Дзвінок / Чат / GetCall.</div><canvas id="chRequestTypes"></canvas></div>
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
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--r)"></span>🚫 Причини відмов</div><div class="cd-d">Чому клієнти відмовляються.</div><canvas id="chRefuse"></canvas></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--o)"></span>🤔 Заперечення лідів</div><div class="cd-d">Чому ліди не купили.</div><canvas id="chObjections"></canvas></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--lime)"></span>🛏️ ТОП-30 товарів за день<span class="badge-tot" id="prodTotal"></span></div>
    <div class="scr">
      <table>
        <thead><tr><th>#</th><th>Товар</th><th class="r">К-сть</th><th class="r">Замовлень</th><th class="r">Виручка</th></tr></thead>
        <tbody id="prodBody"></tbody>
      </table>
    </div>
  </div>
</div>

<div class="pnl" id="p-channels">
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--g)"></span>🌐 Канали продажу — детально<span class="badge-tot">{len(sites)} активних</span></div>
    <div class="cd-d">Сайти / шоу-руми / маркетплейси. Сортовано за виручкою.</div>
    <div class="scr">
      <table>
        <thead><tr><th>#</th><th>Канал</th><th class="r">Замовлень</th><th class="r">Виручка</th><th class="r">Сер.чек</th><th>Графік</th></tr></thead>
        <tbody id="sitesBody"></tbody>
      </table>
    </div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot"></span>📊 Виручка по каналах (графік)</div>
    <canvas id="chSites"></canvas>
  </div>
</div>

<div class="pnl" id="p-ads">
  <div class="mini-kpi">
    <div class="mk"><div class="mk-l">Витрати</div><div class="mk-v" style="color:var(--ac)">{money(meta_spend)}</div></div>
    <div class="mk"><div class="mk-l">Покази</div><div class="mk-v">{money(meta_imp)}</div></div>
    <div class="mk"><div class="mk-l">Кліки</div><div class="mk-v">{money(meta_clicks)}</div></div>
    <div class="mk"><div class="mk-l">CPC</div><div class="mk-v" style="color:var(--b)">{meta_cpc} ₴</div></div>
    <div class="mk"><div class="mk-l">CTR</div><div class="mk-v" style="color:var(--g)">{meta_ctr}%</div></div>
    <div class="mk"><div class="mk-l">Результати</div><div class="mk-v" style="color:var(--p)">{meta_results}</div></div>
    <div class="mk"><div class="mk-l">CPR</div><div class="mk-v" style="color:var(--o)">{meta_cpr} ₴</div></div>
    <div class="mk"><div class="mk-l">ROAS</div><div class="mk-v" style="color:var(--g)">{roas}×</div></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot"></span>🏢 Розбивка по кабінетах Meta</div>
    <div id="metaAccounts"></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--ac)"></span>🎯 Топ кампанії Meta<span class="badge-tot" id="campTotal"></span></div>
    <div class="scr">
      <table>
        <thead><tr>
          <th>#</th><th>Кампанія</th><th>Кабінет</th><th class="r">Витрати</th><th class="r">Покази</th>
          <th class="r">Кліки</th><th class="r">CPC</th><th class="r">CTR</th><th class="r">Результ.</th>
        </tr></thead>
        <tbody id="campBody"></tbody>
      </table>
    </div>
  </div>
</div>

<div class="pnl" id="p-analytics">
  <div class="mini-kpi">
    <div class="mk"><div class="mk-l">Сесії</div><div class="mk-v" style="color:var(--ac)">{money(ga4_sessions)}</div></div>
    <div class="mk"><div class="mk-l">Користувачі</div><div class="mk-v" style="color:var(--g)">{money(ga4_users)}</div></div>
    <div class="mk"><div class="mk-l">Нові</div><div class="mk-v" style="color:var(--b)">{money(ga4.get("new_users", 0))}</div></div>
    <div class="mk"><div class="mk-l">% Відмов</div><div class="mk-v" style="color:var(--r)">{pct(ga4_bounce)}</div></div>
    <div class="mk"><div class="mk-l">Сер. час</div><div class="mk-v" style="color:var(--p)">{avg_dur_str}</div></div>
    <div class="mk"><div class="mk-l">Конв. сайту</div><div class="mk-v" style="color:var(--o)">{site_conv}%</div></div>
  </div>
  <div class="g2">
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--ac)"></span>🔗 Топ-10 джерел трафіку</div><div id="ga4Sources"></div></div>
    <div class="cd"><div class="ct"><span class="dot" style="background:var(--g)"></span>📄 Топ-10 сторінок</div><div id="ga4Pages"></div></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--o)"></span>📱 Розподіл за пристроями</div>
    <canvas id="chDevices" style="max-height:240px"></canvas>
  </div>
</div>

<div class="ftr">UH Analytics · executive dashboard · {timestamp}</div>

<script>
const D = {chart_json};

function sw(name, btn){{
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.querySelectorAll('.pnl').forEach(p=>p.classList.remove('on'));
  btn.classList.add('on');
  document.getElementById('p-'+name).classList.add('on');
}}

Chart.defaults.color = '#7b84a3';
Chart.defaults.font.family = "'DM Sans', sans-serif";
Chart.defaults.font.size = 10;

const COMMON = {{
  responsive: true, maintainAspectRatio: false,
  plugins: {{
    legend: {{ labels: {{ padding: 10, usePointStyle: true, pointStyleWidth: 8, font: {{ size: 10 }} }} }},
    tooltip: {{ backgroundColor: '#1c2137', borderColor: '#3a4170', borderWidth: 1, padding: 10 }}
  }},
  scales: {{
    x: {{ grid: {{ color: 'rgba(255,255,255,0.03)' }}, ticks: {{ maxRotation: 45, font: {{ size: 9 }} }} }},
    y: {{ grid: {{ color: 'rgba(255,255,255,0.03)' }}, ticks: {{ font: {{ size: 9 }}, callback: v => v >= 1000 ? (v/1000).toFixed(0)+'K' : v }} }}
  }}
}};
const fmt = n => (n||0).toLocaleString('uk').replace(/,/g,' ');
const fmtK = n => {{ n=Number(n)||0; if(n>=1e6)return(n/1e6).toFixed(2)+'M'; if(n>=1e3)return(n/1e3).toFixed(0)+'K'; return n.toFixed(0); }};

{{
  const totalRev = D.trend_revenue.reduce((a,b)=>a+b, 0);
  document.getElementById('trend30Total').textContent = '∑ ' + fmtK(totalRev) + ' ₴';
  new Chart(document.getElementById('chTrend30'), {{
    type: 'bar',
    data: {{
      labels: D.trend_dates,
      datasets: [
        {{ type:'bar', label: 'Виручка ₴', data: D.trend_revenue, backgroundColor: 'rgba(108,92,231,0.65)', borderColor: '#6c5ce7', borderWidth: 1, borderRadius: 4, yAxisID: 'y1', order: 2 }},
        {{ type:'line', label: 'Замовлень', data: D.trend_orders, borderColor: '#00d68f', backgroundColor: 'rgba(0,214,143,.15)', tension: .4, borderWidth: 2.5, pointRadius: 3, yAxisID: 'y2', order: 1 }},
        {{ type:'line', label: 'Лідів', data: D.trend_leads, borderColor: '#ffa94d', tension: .4, borderWidth: 2, pointRadius: 2, borderDash: [5,3], yAxisID: 'y2', order: 0, fill: false }}
      ]
    }},
    options: {{ ...COMMON, scales: {{
      x: {{ ...COMMON.scales.x }},
      y1: {{ position:'left', grid: COMMON.scales.y.grid, ticks: {{ ...COMMON.scales.y.ticks, color: '#a29bfe' }} }},
      y2: {{ position:'right', grid: {{ display: false }}, ticks: {{ font: {{ size: 9 }}, color: '#00d68f' }} }}
    }} }}
  }});
}}

new Chart(document.getElementById('chOrders'), {{
  type: 'bar',
  data: {{ labels: D.hist_dates, datasets: [
    {{ label: 'UH', data: D.hist_uh, backgroundColor: 'rgba(108,92,231,0.8)', stack: 's', borderRadius: 3 }},
    {{ label: 'SH', data: D.hist_sh, backgroundColor: 'rgba(0,214,143,0.7)', stack: 's', borderRadius: 3 }}
  ] }},
  options: {{ ...COMMON, scales: {{ ...COMMON.scales, x: {{ ...COMMON.scales.x, stacked: true }}, y: {{ ...COMMON.scales.y, stacked: true }} }} }}
}});
new Chart(document.getElementById('chSales'), {{
  type: 'bar',
  data: {{ labels: D.hist_dates, datasets: [
    {{ label: 'UH', data: D.hist_uh_s, backgroundColor: 'rgba(255,169,77,0.8)', stack: 's', borderRadius: 3 }},
    {{ label: 'SH', data: D.hist_sh_s, backgroundColor: 'rgba(255,107,107,0.7)', stack: 's', borderRadius: 3 }}
  ] }},
  options: {{ ...COMMON, scales: {{ ...COMMON.scales, x: {{ ...COMMON.scales.x, stacked: true }}, y: {{ ...COMMON.scales.y, stacked: true }} }} }}
}});

function lineChart(id, data, color){{
  new Chart(document.getElementById(id), {{
    type: 'line',
    data: {{ labels: D.hist_dates, datasets: [{{ data, borderColor: color, backgroundColor: color+'22', fill: true, tension: .4, borderWidth: 2, pointRadius: 2 }}] }},
    options: {{ ...COMMON, plugins: {{ ...COMMON.plugins, legend: {{ display: false }} }} }}
  }});
}}
lineChart('chGa4', D.hist_ga4, '#339af0');
lineChart('chMeta', D.hist_meta, '#ffa94d');
lineChart('chCrmOrd', D.hist_crm, '#da77f2');

function renderPodr(elId, podrObj, color){{
  const el = document.getElementById(elId);
  const items = Object.entries(podrObj||{{}}).sort((a,b)=>b[1]-a[1]);
  if (!items.length) {{ el.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>'; return; }}
  const max = items[0][1] || 1;
  el.innerHTML = items.map(([n,v])=>{{
    const p = Math.max(2, Math.round(v/max*100));
    return `<div class="bar-row">
      <div class="bar-name" title="${{n}}">${{n}}</div>
      <div class="bar-wrap"><div class="bar-fill" style="width:${{p}}%;background:${{color}}"></div></div>
      <div class="bar-val">${{fmtK(v)}}</div>
    </div>`;
  }}).join('');
}}
renderPodr('uhOrdPodr', D.uh_orders_podr, '#6c5ce7');
renderPodr('shOrdPodr', D.sh_orders_podr, '#00d68f');
renderPodr('uhSalPodr', D.uh_sales_podr, '#ffa94d');
renderPodr('shSalPodr', D.sh_sales_podr, '#ff6b6b');

const mgrBody = document.getElementById('mgrBody');
if (D.managers && D.managers.length) {{
  mgrBody.innerHTML = D.managers.map((m,i) => {{
    const refClass = m.refuse_pct >= 12 ? 'br' : m.refuse_pct >= 5 ? 'bo' : 'bg';
    const convClass = m.conv >= 85 ? 'bg' : m.conv >= 70 ? 'bo' : 'br';
    return `<tr>
      <td class="num" style="color:var(--td)">${{i+1}}</td>
      <td>${{m.name}}</td>
      <td class="r num">${{m.orders}}</td>
      <td class="r num" style="color:var(--td)">${{m.leads||0}}</td>
      <td class="r num" style="color:var(--g)">${{fmtK(m.revenue)}}</td>
      <td class="r num">${{fmt(m.avg_check||0)}}</td>
      <td class="r"><span class="badge ${{convClass}}">${{(m.conv||0).toFixed(0)}}%</span></td>
      <td class="r num">${{m.refused}}</td>
      <td class="r"><span class="badge ${{refClass}}">${{m.refuse_pct.toFixed(1)}}%</span></td>
    </tr>`;
  }}).join('');
}} else {{
  mgrBody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';
}}

const mgrShopBody = document.getElementById('mgrShopBody');
if (D.managers_shop && D.managers_shop.length) {{
  mgrShopBody.innerHTML = D.managers_shop.map(m => `<tr>
    <td>${{m.name}}</td>
    <td class="r num">${{m.orders}}</td>
    <td class="r num" style="color:var(--g)">${{fmtK(m.revenue)}}</td>
    <td class="r num">${{fmt(m.avg_check||0)}}</td>
  </tr>`).join('');
}} else {{
  mgrShopBody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';
}}

const chatterBody = document.getElementById('chatterBody');
if (D.chatters && D.chatters.length) {{
  chatterBody.innerHTML = D.chatters.map(c => `<tr>
    <td>${{c.name}}</td>
    <td class="r num">${{c.orders}}</td>
    <td class="r num" style="color:var(--g)">${{fmtK(c.revenue)}}</td>
  </tr>`).join('');
}} else {{
  chatterBody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:18px;color:var(--td)">Немає чатерів за день</td></tr>';
}}

function pieChart(elId, dataObj){{
  const el = document.getElementById(elId);
  if (!el) return;
  const palette = ['#6c5ce7','#a29bfe','#00d68f','#ffa94d','#339af0','#ff6b6b','#da77f2','#66d9e8','#94d82d','#ffd43b','#fd7e14','#94d2bd'];
  const entries = Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]).slice(0, 12);
  if (!entries.length) {{ el.parentElement.insertAdjacentHTML('beforeend', '<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>'); el.style.display='none'; return; }}
  new Chart(el, {{
    type: 'doughnut',
    data: {{ labels: entries.map(e=>e[0]), datasets: [{{ data: entries.map(e=>e[1]), backgroundColor: palette, borderWidth: 2, borderColor: '#151929' }}] }},
    options: {{ ...COMMON, scales: {{}}, cutout: '55%',
      plugins: {{ ...COMMON.plugins, legend: {{ position: 'right', labels: {{ font: {{ size: 9 }}, padding: 6, usePointStyle: true, boxWidth: 8 }} }} }} }}
  }});
}}
pieChart('chCategories', D.categories);
pieChart('chRequestTypes', D.request_types);
pieChart('chStatuses', D.statuses);

function listChart(elId, dataObj, color){{
  const el = document.getElementById(elId);
  if (!el) return;
  const entries = Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]);
  if (!entries.length) {{ el.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>'; return; }}
  const max = entries[0][1] || 1;
  el.innerHTML = entries.map(([n,v])=>{{
    const p = Math.max(2, Math.round(v/max*100));
    return `<div class="bar-row">
      <div class="bar-name" title="${{n}}">${{n}}</div>
      <div class="bar-wrap"><div class="bar-fill" style="width:${{p}}%;background:${{color}}"></div></div>
      <div class="bar-val">${{v}}</div>
    </div>`;
  }}).join('');
}}
listChart('paymentMethods', D.payment_methods, '#00d68f');
listChart('deliveryTypes', D.delivery_types, '#ffa94d');
listChart('carriers', D.carriers, '#339af0');
listChart('warehouses', D.warehouses, '#ffd43b');

function barChartH(elId, dataObj, color){{
  const el = document.getElementById(elId);
  if (!el) return;
  const entries = Object.entries(dataObj||{{}}).sort((a,b)=>b[1]-a[1]).slice(0, 10);
  if (!entries.length) {{ el.parentElement.insertAdjacentHTML('beforeend', '<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>'); el.style.display='none'; return; }}
  new Chart(el, {{
    type: 'bar',
    data: {{ labels: entries.map(e=>e[0].length>30?e[0].substr(0,30)+'…':e[0]), datasets: [{{ label: 'К-сть', data: entries.map(e=>e[1]), backgroundColor: color+'aa', borderColor: color, borderWidth: 1, borderRadius: 4 }}] }},
    options: {{ ...COMMON, indexAxis: 'y', plugins: {{ ...COMMON.plugins, legend: {{ display: false }} }} }}
  }});
}}
barChartH('chRefuse', D.refuse_reasons, '#ff6b6b');
barChartH('chObjections', D.lead_objections, '#ffa94d');

const prodBody = document.getElementById('prodBody');
if (D.products && D.products.length) {{
  document.getElementById('prodTotal').textContent = D.products.length + ' SKU';
  prodBody.innerHTML = D.products.map((p,i) => `<tr>
    <td class="num" style="color:var(--td)">${{i+1}}</td>
    <td title="${{p.name}}">${{p.name.length > 60 ? p.name.substr(0,60)+'…' : p.name}}</td>
    <td class="r num">${{p.qty || p.count}}</td>
    <td class="r num" style="color:var(--td)">${{p.count}}</td>
    <td class="r num" style="color:var(--g)">${{fmtK(p.revenue)}}</td>
  </tr>`).join('');
}} else {{
  prodBody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';
}}

const sitesEntries = Object.entries(D.sites || {{}}).sort((a,b)=>b[1].revenue - a[1].revenue);
const sitesBody = document.getElementById('sitesBody');
if (sitesEntries.length) {{
  const maxR = sitesEntries[0][1].revenue;
  sitesBody.innerHTML = sitesEntries.map(([n,s],i) => {{
    const p = Math.max(3, Math.round(s.revenue/maxR*100));
    return `<tr>
      <td class="num" style="color:var(--td)">${{i+1}}</td>
      <td>${{n}}</td>
      <td class="r num">${{s.orders}}</td>
      <td class="r num" style="color:var(--g)">${{fmtK(s.revenue)}}</td>
      <td class="r num">${{fmt(s.avg_check||0)}}</td>
      <td><div class="bar-wrap" style="width:120px"><div class="bar-fill" style="width:${{p}}%;background:linear-gradient(90deg,#00d68f,#94d2bd)"></div></div></td>
    </tr>`;
  }}).join('');

  new Chart(document.getElementById('chSites'), {{
    type: 'bar',
    data: {{ labels: sitesEntries.map(e=>e[0]), datasets: [
      {{ label: 'Виручка', data: sitesEntries.map(e=>e[1].revenue), backgroundColor: 'rgba(0,214,143,0.7)', borderColor: '#00d68f', borderRadius: 4 }}
    ] }},
    options: {{ ...COMMON, plugins: {{ ...COMMON.plugins, legend: {{ display: false }} }}, indexAxis: 'y' }}
  }});
}} else {{
  sitesBody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:18px;color:var(--td)">Немає даних</td></tr>';
}}

const metaAcc = document.getElementById('metaAccounts');
if (D.meta_accounts && D.meta_accounts.length) {{
  metaAcc.innerHTML = D.meta_accounts.map(a => {{
    const err = a.error ? `<span class="badge br">⚠ ${{a.error.substr(0,40)}}…</span>` : `<span class="badge bg">OK</span>`;
    return `<div class="bar-row" style="border-bottom:1px solid var(--brd)">
      <div class="bar-name" style="max-width:none;flex:none;width:160px">${{a.name}}</div>
      <div style="flex:1;display:flex;gap:14px;flex-wrap:wrap;font-size:11px">
        <span>Витрати: <b style="color:var(--ac)">${{fmt(a.spend||0)}} ₴</b></span>
        <span>Кліки: <b>${{fmt(a.clicks||0)}}</b></span>
        <span>CPC: <b>${{a.cpc||0}}</b></span>
        <span>CTR: <b>${{a.ctr||0}}%</b></span>
        <span>Результ.: <b style="color:var(--g)">${{a.results||0}}</b></span>
      </div>
      ${{err}}
    </div>`;
  }}).join('');
}} else {{
  metaAcc.innerHTML = '<div style="text-align:center;color:var(--td);padding:18px">Немає кабінетів</div>';
}}

const campBody = document.getElementById('campBody');
if (D.meta_camps && D.meta_camps.length) {{
  document.getElementById('campTotal').textContent = D.meta_camps.length + ' активних';
  campBody.innerHTML = D.meta_camps.map((c,i) => `<tr>
    <td class="num" style="color:var(--td)">${{i+1}}</td>
    <td title="${{c.campaign}}">${{c.campaign.length>40?c.campaign.substr(0,40)+'…':c.campaign}}</td>
    <td><span class="badge bb">${{c.account}}</span></td>
    <td class="r num">${{fmt(c.spend)}}</td>
    <td class="r num">${{fmt(c.impressions)}}</td>
    <td class="r num">${{c.clicks}}</td>
    <td class="r num">${{c.cpc}}</td>
    <td class="r num">${{c.ctr}}%</td>
    <td class="r num" style="color:var(--g)">${{c.results}}</td>
  </tr>`).join('');
}} else {{
  campBody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:18px;color:var(--td)">Немає кампаній</td></tr>';
}}

const ga4S = document.getElementById('ga4Sources');
if (D.ga4_sources.length) {{
  const max = D.ga4_sources[0].sessions || 1;
  ga4S.innerHTML = D.ga4_sources.map(s => {{
    const lbl = s.source + (s.medium && s.medium !== '(none)' ? ' / '+s.medium : '');
    const p = Math.max(2, Math.round(s.sessions/max*100));
    return `<div class="bar-row">
      <div class="bar-name" title="${{lbl}}">${{lbl}}</div>
      <div class="bar-wrap"><div class="bar-fill" style="width:${{p}}%"></div></div>
      <div class="bar-val">${{s.sessions}}</div>
    </div>`;
  }}).join('');
}} else {{ ga4S.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>'; }}

const ga4P = document.getElementById('ga4Pages');
if (D.ga4_pages.length) {{
  const max = D.ga4_pages[0].views || 1;
  ga4P.innerHTML = D.ga4_pages.map(p => {{
    const pp = Math.max(2, Math.round(p.views/max*100));
    return `<div class="bar-row">
      <div class="bar-name" title="${{p.path}}">${{p.title || p.path}}</div>
      <div class="bar-wrap"><div class="bar-fill" style="width:${{pp}}%;background:linear-gradient(90deg,#00d68f,#94d8a6)"></div></div>
      <div class="bar-val">${{p.views}}</div>
    </div>`;
  }}).join('');
}} else {{ ga4P.innerHTML='<div style="text-align:center;color:var(--td);padding:18px">Немає даних</div>'; }}

const chDev = document.getElementById('chDevices');
if (chDev && D.ga4_devices && D.ga4_devices.length) {{
  new Chart(chDev, {{
    type: 'doughnut',
    data: {{ labels: D.ga4_devices.map(d=>d.device), datasets: [{{ data: D.ga4_devices.map(d=>d.sessions), backgroundColor: ['#6c5ce7','#00d68f','#ffa94d','#339af0'], borderWidth: 2, borderColor: '#151929' }}] }},
    options: {{ ...COMMON, scales: {{}}, cutout: '60%' }}
  }});
}}
</script>
</body></html>
'''


def main():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"\n📊 Генерація директорського дашборду за {yesterday}")

    data = load_data(yesterday)
    if not data:
        print(f"❌ Файл history/{yesterday}.json не знайдено")
        return

    history = load_history(30)
    print(f"   📂 Завантажено історію: {len(history)} днів")

    html = build_html(data, history)

    out = DOCS_DIR / "index.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    archive_dir = DOCS_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)
    archive_path = archive_dir / f"{yesterday}.html"
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Дашборд згенеровано:")
    print(f"   → {out}")
    print(f"   → {archive_path}\n")
    print(f"🌐 https://grigorijtetlasov-uh.github.io/uh-analytics/\n")


if __name__ == "__main__":
    main()
