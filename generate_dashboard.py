"""
generate_dashboard.py
─────────────────────────────────────────────────────────
Генерує щоденний HTML дашборд продажів UH у фірмовому стилі.

Вхід: history/YYYY-MM-DD.json (виходить з fetch_data.py)
Вихід: docs/index.html (для GitHub Pages)
─────────────────────────────────────────────────────────
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta

HISTORY_DIR = Path("history")
DOCS_DIR    = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)

# ──────────────────────── HELPERS ─────────────────────────────

def money(x: float) -> str:
    """123456.78 → '123 457'"""
    try:
        return f"{float(x):,.0f}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"

def money_k(x: float) -> str:
    """123456.78 → '123K'"""
    try:
        v = float(x)
        if v >= 1_000_000:
            return f"{v/1_000_000:.1f}M"
        elif v >= 1_000:
            return f"{v/1_000:.0f}K"
        return f"{v:.0f}"
    except (ValueError, TypeError):
        return "0"

def pct(x: float) -> str:
    try:
        return f"{float(x):.1f}%"
    except (ValueError, TypeError):
        return "0.0%"

def load_data(date_iso: str) -> dict:
    """Завантажує дані за конкретну дату."""
    path = HISTORY_DIR / f"{date_iso}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_history(days: int = 30) -> list:
    """Завантажує дані за останні N днів."""
    files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)[:days]
    history = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                history.append(json.load(fp))
        except Exception:
            continue
    return list(reversed(history))  # старі → нові

# ──────────────────────── HTML GENERATION ─────────────────────

def build_html(data: dict, history: list) -> str:
    """Будує повний HTML дашборду."""

    date_disp = data.get("date_disp", "—")
    month_str = data.get("month", "—")

    uh = data.get("uh", {})
    sh = data.get("sh", {})
    crm = data.get("crm", {})
    ga4 = data.get("ga4", {})
    meta = data.get("meta", {})

    # ── KPI блок ──
    uh_orders_day  = uh.get("ORDERS",   {}).get("day",   {}).get("total", 0)
    uh_sales_day   = uh.get("SALES",    {}).get("day",   {}).get("total", 0)
    uh_orders_m    = uh.get("ORDERS",   {}).get("month", {}).get("total", 0)
    uh_sales_m     = uh.get("SALES",    {}).get("month", {}).get("total", 0)

    sh_orders_day  = sh.get("ORDERS",   {}).get("day",   {}).get("total", 0)
    sh_sales_day   = sh.get("SALES",    {}).get("day",   {}).get("total", 0)
    sh_orders_m    = sh.get("ORDERS",   {}).get("month", {}).get("total", 0)
    sh_sales_m     = sh.get("SALES",    {}).get("month", {}).get("total", 0)

    total_orders_day = uh_orders_day + sh_orders_day
    total_sales_day  = uh_sales_day + sh_sales_day
    total_orders_m   = uh_orders_m + sh_orders_m
    total_sales_m    = uh_sales_m + sh_sales_m

    # CRM
    crm_orders   = crm.get("orders", {}).get("total", 0)
    crm_revenue  = crm.get("orders", {}).get("revenue", 0)
    crm_refused  = crm.get("orders", {}).get("refused", 0)
    crm_refuse_p = crm.get("orders", {}).get("refuse_pct", 0)
    crm_leads    = crm.get("leads",  {}).get("new_leads", 0)

    # GA4
    ga4_sessions = ga4.get("sessions", 0)
    ga4_users    = ga4.get("users", 0)
    ga4_bounce   = ga4.get("bounce_rate", 0)

    # Meta
    meta_spend   = meta.get("total", {}).get("spend", 0)
    meta_clicks  = meta.get("total", {}).get("clicks", 0)
    meta_results = meta.get("total", {}).get("results", 0)
    meta_cpc     = meta.get("total", {}).get("cpc", 0)

    # ── Дані для графіків (історія) ──
    hist_dates    = []
    hist_uh_ord   = []
    hist_sh_ord   = []
    hist_uh_sales = []
    hist_sh_sales = []
    hist_ga4_sess = []
    hist_meta_sp  = []
    hist_crm_ord  = []

    for h in history:
        d = h.get("date", "")
        if not d:
            continue
        # Формат "YYYY-MM-DD" → "DD.MM"
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            hist_dates.append(dt.strftime("%d.%m"))
        except Exception:
            hist_dates.append(d)
        hist_uh_ord.append(h.get("uh", {}).get("ORDERS", {}).get("day", {}).get("total", 0))
        hist_sh_ord.append(h.get("sh", {}).get("ORDERS", {}).get("day", {}).get("total", 0))
        hist_uh_sales.append(h.get("uh", {}).get("SALES", {}).get("day", {}).get("total", 0))
        hist_sh_sales.append(h.get("sh", {}).get("SALES", {}).get("day", {}).get("total", 0))
        hist_ga4_sess.append(h.get("ga4", {}).get("sessions", 0))
        hist_meta_sp.append(h.get("meta", {}).get("total", {}).get("spend", 0))
        hist_crm_ord.append(h.get("crm", {}).get("orders", {}).get("total", 0))

    # ── Підрозділи UH і SH ──
    uh_orders_podr = uh.get("ORDERS", {}).get("day", {}).get("by_podr", {})
    sh_orders_podr = sh.get("ORDERS", {}).get("day", {}).get("by_podr", {})
    uh_sales_podr  = uh.get("SALES",  {}).get("day", {}).get("by_podr", {})
    sh_sales_podr  = sh.get("SALES",  {}).get("day", {}).get("by_podr", {})

    # ── Менеджери CRM ──
    managers = crm.get("managers", [])

    # ── Топ кампанії Meta ──
    meta_campaigns = meta.get("by_campaign", [])[:10]

    # ── GA4 джерела і сторінки ──
    ga4_sources = ga4.get("by_source", [])[:10]
    ga4_pages   = ga4.get("by_page", [])[:10]
    ga4_devices = ga4.get("by_device", [])

    # JSON для графіків
    chart_data = {
        "dates":      hist_dates,
        "uh_orders":  hist_uh_ord,
        "sh_orders":  hist_sh_ord,
        "uh_sales":   hist_uh_sales,
        "sh_sales":   hist_sh_sales,
        "ga4_sess":   hist_ga4_sess,
        "meta_spend": hist_meta_sp,
        "crm_orders": hist_crm_ord,
        "uh_orders_podr": uh_orders_podr,
        "sh_orders_podr": sh_orders_podr,
        "uh_sales_podr":  uh_sales_podr,
        "sh_sales_podr":  sh_sales_podr,
        "managers":    managers,
        "meta_camps":  meta_campaigns,
        "ga4_sources": ga4_sources,
        "ga4_pages":   ga4_pages,
        "ga4_devices": ga4_devices,
    }

    chart_json = json.dumps(chart_data, ensure_ascii=False)

    # ═══════════════════════════════════════════════════════
    # HTML
    # ═══════════════════════════════════════════════════════
    html = '''<!DOCTYPE html>
<html lang="uk"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>UH — Щоденний дашборд продажів</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--bg:#0c0f1a;--s:#151929;--s2:#1c2137;--brd:#2a3050;--t:#e4e8f7;--td:#7b84a3;--ac:#6c5ce7;--ac2:#a29bfe;--g:#00d68f;--gd:rgba(0,214,143,.15);--o:#ffa94d;--od:rgba(255,169,77,.15);--r:#ff6b6b;--rd:rgba(255,107,107,.15);--b:#339af0;--bd:rgba(51,154,240,.15)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--t);min-height:100vh;padding:14px 18px;font-size:12px}
.hdr{text-align:center;margin-bottom:6px}
.hdr h1{font-size:22px;font-weight:700;background:linear-gradient(135deg,var(--ac2),var(--g));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr .sub{color:var(--td);font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-top:2px}
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px;margin-bottom:12px}
.kpi{background:var(--s);border:1px solid var(--brd);border-radius:10px;padding:11px;text-align:center;position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:10px 10px 0 0}
.kpi:nth-child(1)::before{background:var(--ac)}.kpi:nth-child(2)::before{background:var(--g)}
.kpi:nth-child(3)::before{background:var(--o)}.kpi:nth-child(4)::before{background:var(--b)}
.kpi:nth-child(5)::before{background:#da77f2}.kpi:nth-child(6)::before{background:#20c997}
.kpi:nth-child(7)::before{background:var(--r)}.kpi:nth-child(8)::before{background:#66d9e8}
.kl{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:var(--td);margin-bottom:2px}
.kv{font-family:'JetBrains Mono',monospace;font-size:17px;font-weight:600}
.ks{font-size:9px;color:var(--td);margin-top:2px}
.tabs{display:flex;gap:2px;margin-bottom:12px;background:var(--s);border-radius:9px;padding:2px;border:1px solid var(--brd);flex-wrap:wrap}
.tab{flex:1;min-width:120px;padding:8px;border-radius:7px;text-align:center;cursor:pointer;font-size:11px;font-weight:500;color:var(--td);border:none;background:none;transition:.15s}
.tab:hover{color:var(--t);background:var(--s2)}.tab.on{background:var(--ac);color:#fff}
.pnl{display:none}.pnl.on{display:block}
.cd{background:var(--s);border:1px solid var(--brd);border-radius:10px;padding:14px;margin-bottom:12px}
.ct{font-size:12px;font-weight:600;margin-bottom:4px;display:flex;align-items:center;gap:6px}
.ct .dot{width:6px;height:6px;border-radius:50%;background:var(--ac)}
.cd-d{font-size:10px;color:var(--td);margin-bottom:10px;line-height:1.4}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
@media(max-width:768px){.g2{grid-template-columns:1fr}.tab{min-width:90px;font-size:10px}}
canvas{max-height:300px}
.tbl{background:var(--s);border:1px solid var(--brd);border-radius:10px;overflow:hidden;margin-bottom:12px}
.tbl-h{padding:9px 12px;font-size:12px;font-weight:600;border-bottom:1px solid var(--brd);display:flex;justify-content:space-between;align-items:center}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:var(--s2);padding:6px 8px;text-align:left;font-weight:600;color:var(--td);font-size:9px;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}
th.r,td.r{text-align:right}
td{padding:5px 8px;border-bottom:1px solid var(--brd)}
tr:hover td{background:rgba(108,92,231,.05)}
.scr{max-height:460px;overflow-y:auto}
.scr::-webkit-scrollbar{width:4px}.scr::-webkit-scrollbar-thumb{background:var(--brd);border-radius:2px}
.badge{display:inline-block;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:600}
.bg{background:var(--gd);color:var(--g)}.bo{background:var(--od);color:var(--o)}.br{background:var(--rd);color:var(--r)}.bb{background:var(--bd);color:var(--b)}
.num{font-family:'JetBrains Mono',monospace;font-size:11px}
.split-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:768px){.split-row{grid-template-columns:1fr}}
.podr-row{display:flex;align-items:center;justify-content:space-between;padding:6px 10px;border-bottom:1px solid var(--brd)}
.podr-row:last-child{border-bottom:none}
.podr-name{font-size:11px}
.podr-val{font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:600;color:var(--ac2)}
.bar-row{display:flex;align-items:center;gap:8px;padding:5px 10px}
.bar-name{font-size:11px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px}
.bar-wrap{flex:2;background:var(--s2);border-radius:3px;height:6px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--ac),var(--ac2));border-radius:3px}
.bar-val{font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:600;width:80px;text-align:right}
.ftr{text-align:center;color:var(--td);font-size:10px;letter-spacing:.5px;padding-top:18px;border-top:1px solid var(--brd);margin-top:24px}
</style></head>
<body>

<div class="hdr">
  <h1>Щоденний дашборд продажів</h1>
  <div class="sub">UH (United Home) · ''' + date_disp + '''</div>
  <div style="font-size:10px;color:var(--td);margin-top:4px">Місяць: ''' + month_str + '''</div>
</div>

<div class="kpi-row">
  <div class="kpi"><div class="kl">Замовлення (день)</div><div class="kv">''' + money(total_orders_day) + '''</div><div class="ks">UH+SH ₴</div></div>
  <div class="kpi"><div class="kl">Відгрузки (день)</div><div class="kv">''' + money(total_sales_day) + '''</div><div class="ks">UH+SH ₴</div></div>
  <div class="kpi"><div class="kl">Замовлення (місяць)</div><div class="kv">''' + money_k(total_orders_m) + '''</div><div class="ks">UH+SH ₴</div></div>
  <div class="kpi"><div class="kl">Відгрузки (місяць)</div><div class="kv">''' + money_k(total_sales_m) + '''</div><div class="ks">UH+SH ₴</div></div>
  <div class="kpi"><div class="kl">CRM Заявки</div><div class="kv">''' + str(crm_orders) + '''</div><div class="ks">''' + str(crm_leads) + ''' лідів · ''' + pct(crm_refuse_p) + ''' відмов</div></div>
  <div class="kpi"><div class="kl">GA4 Сесії</div><div class="kv">''' + money(ga4_sessions) + '''</div><div class="ks">''' + money(ga4_users) + ''' юзерів · ''' + pct(ga4_bounce) + ''' відмов</div></div>
  <div class="kpi"><div class="kl">Meta Витрати</div><div class="kv">''' + money(meta_spend) + '''</div><div class="ks">''' + money(meta_clicks) + ''' кліків · CPC ''' + str(meta_cpc) + '''</div></div>
  <div class="kpi"><div class="kl">Meta Результати</div><div class="kv">''' + str(meta_results) + '''</div><div class="ks">конверсій</div></div>
</div>

<div class="tabs">
  <button class="tab on" onclick="sw('overview')">📊 Огляд</button>
  <button class="tab" onclick="sw('sales1c')">💰 1С Продажі</button>
  <button class="tab" onclick="sw('crm')">👥 CRM</button>
  <button class="tab" onclick="sw('ads')">📱 Реклама</button>
  <button class="tab" onclick="sw('analytics')">📈 Аналітика</button>
</div>

<!-- ════════ ОГЛЯД ════════ -->
<div class="pnl on" id="p-overview">
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot"></span>Замовлення UH+SH (₴) — динаміка</div>
      <div class="cd-d">Сума замовлень з 1С по днях. Стек: UH (фіолетовий) + SH (зелений).</div>
      <canvas id="chOrdersHist"></canvas>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--g)"></span>Відгрузки UH+SH (₴) — динаміка</div>
      <div class="cd-d">Реальні відгрузки клієнтам по днях. Без доставок (НП тощо).</div>
      <canvas id="chSalesHist"></canvas>
    </div>
  </div>
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--b)"></span>GA4 Сесії — динаміка</div>
      <div class="cd-d">Кількість сесій на сайті. Допомагає зрозуміти трафік.</div>
      <canvas id="chSessions"></canvas>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--o)"></span>Meta Витрати — динаміка</div>
      <div class="cd-d">Витрати на рекламу Meta по днях (UAH).</div>
      <canvas id="chMetaSpend"></canvas>
    </div>
  </div>
</div>

<!-- ════════ 1С ПРОДАЖІ ════════ -->
<div class="pnl" id="p-sales1c">
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot"></span>Замовлення UH по підрозділах (день)</div>
      <div class="cd-d">Сума ₴: ''' + money(uh_orders_day) + '''</div>
      <div id="uhOrdersPodr"></div>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--g)"></span>Замовлення SH по підрозділах (день)</div>
      <div class="cd-d">Сума ₴: ''' + money(sh_orders_day) + '''</div>
      <div id="shOrdersPodr"></div>
    </div>
  </div>
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--o)"></span>Відгрузки UH по підрозділах (день)</div>
      <div class="cd-d">Сума ₴: ''' + money(uh_sales_day) + '''</div>
      <div id="uhSalesPodr"></div>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--r)"></span>Відгрузки SH по підрозділах (день)</div>
      <div class="cd-d">Сума ₴: ''' + money(sh_sales_day) + '''</div>
      <div id="shSalesPodr"></div>
    </div>
  </div>
</div>

<!-- ════════ CRM ════════ -->
<div class="pnl" id="p-crm">
  <div class="cd">
    <div class="ct"><span class="dot"></span>SalesDrive — Менеджери</div>
    <div class="cd-d">Виручка, замовлення та відмови по кожному менеджеру за день.</div>
    <div class="scr">
      <table>
        <thead><tr>
          <th>Менеджер</th>
          <th class="r">Замовлень</th>
          <th class="r">Виручка ₴</th>
          <th class="r">Відмов</th>
          <th class="r">% Відмов</th>
        </tr></thead>
        <tbody id="mgrBody"></tbody>
      </table>
    </div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--b)"></span>CRM Замовлення (історія)</div>
    <canvas id="chCrm"></canvas>
  </div>
</div>

<!-- ════════ РЕКЛАМА ════════ -->
<div class="pnl" id="p-ads">
  <div class="kpi-row">
    <div class="kpi"><div class="kl">Витрати Meta</div><div class="kv">''' + money(meta_spend) + '''</div><div class="ks">UAH</div></div>
    <div class="kpi"><div class="kl">Покази</div><div class="kv">''' + money(meta.get("total", {}).get("impressions", 0)) + '''</div><div class="ks">imp</div></div>
    <div class="kpi"><div class="kl">Кліки</div><div class="kv">''' + money(meta_clicks) + '''</div><div class="ks">clicks</div></div>
    <div class="kpi"><div class="kl">CPC</div><div class="kv">''' + str(meta_cpc) + '''</div><div class="ks">UAH/click</div></div>
    <div class="kpi"><div class="kl">CTR</div><div class="kv">''' + str(meta.get("total", {}).get("ctr", 0)) + '''%</div><div class="ks">click-through</div></div>
    <div class="kpi"><div class="kl">Результати</div><div class="kv">''' + str(meta_results) + '''</div><div class="ks">конверсій</div></div>
    <div class="kpi"><div class="kl">CPR</div><div class="kv">''' + str(meta.get("total", {}).get("cpr", 0)) + '''</div><div class="ks">UAH/результат</div></div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot"></span>Топ кампанії Meta</div>
    <div class="cd-d">Розбивка по кабінетах: Amebli 2024, Amebli, MatrasRoll 2024.</div>
    <div class="scr">
      <table>
        <thead><tr>
          <th>Кампанія</th>
          <th>Кабінет</th>
          <th class="r">Витрати</th>
          <th class="r">Покази</th>
          <th class="r">Кліки</th>
          <th class="r">CPC</th>
          <th class="r">CTR</th>
          <th class="r">Результати</th>
        </tr></thead>
        <tbody id="campBody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ════════ АНАЛІТИКА ════════ -->
<div class="pnl" id="p-analytics">
  <div class="kpi-row">
    <div class="kpi"><div class="kl">Сесії</div><div class="kv">''' + money(ga4_sessions) + '''</div></div>
    <div class="kpi"><div class="kl">Користувачі</div><div class="kv">''' + money(ga4_users) + '''</div></div>
    <div class="kpi"><div class="kl">Нові</div><div class="kv">''' + money(ga4.get("new_users", 0)) + '''</div></div>
    <div class="kpi"><div class="kl">Відмови</div><div class="kv">''' + pct(ga4_bounce) + '''</div></div>
    <div class="kpi"><div class="kl">Сер. час</div><div class="kv">''' + str(int(ga4.get("avg_duration", 0)//60)) + ':' + str(int(ga4.get("avg_duration", 0)%60)).zfill(2) + '''</div></div>
  </div>
  <div class="g2">
    <div class="cd">
      <div class="ct"><span class="dot"></span>Топ джерела трафіку</div>
      <div id="ga4Sources"></div>
    </div>
    <div class="cd">
      <div class="ct"><span class="dot" style="background:var(--g)"></span>Топ сторінки</div>
      <div id="ga4Pages"></div>
    </div>
  </div>
  <div class="cd">
    <div class="ct"><span class="dot" style="background:var(--o)"></span>Пристрої</div>
    <canvas id="chDevices" style="max-height:200px"></canvas>
  </div>
</div>

<div class="ftr">UH Analytics · згенеровано ''' + datetime.now().strftime("%d.%m.%Y %H:%M") + '''</div>

<script>
const D = ''' + chart_json + ''';

// ═══════════════════════════ TABS ═══════════════════════════
function sw(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  document.querySelectorAll('.pnl').forEach(p => p.classList.remove('on'));
  event.target.classList.add('on');
  document.getElementById('p-' + name).classList.add('on');
}

// ═══════════════════════════ CHART DEFAULTS ═══════════════
Chart.defaults.color = '#7b84a3';
Chart.defaults.font.family = "'DM Sans', sans-serif";
Chart.defaults.font.size = 10;

const COMMON = {
  responsive: true, maintainAspectRatio: false,
  plugins: {
    legend: { labels: { padding: 12, usePointStyle: true, pointStyleWidth: 10, font: { size: 11 } } },
    tooltip: { backgroundColor: '#1c2137', borderColor: '#2a3050', borderWidth: 1, padding: 10 }
  },
  scales: {
    x: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { maxRotation: 45 } },
    y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { callback: v => v >= 1000 ? (v/1000).toFixed(0)+'K' : v } }
  }
};

// ═══════════════════════════ ORDERS HISTORY ═══════════════
new Chart(document.getElementById('chOrdersHist'), {
  type: 'bar',
  data: {
    labels: D.dates,
    datasets: [
      { label: 'UH', data: D.uh_orders, backgroundColor: 'rgba(108,92,231,0.8)', borderColor: '#6c5ce7', borderWidth: 1, stack: 's' },
      { label: 'SH', data: D.sh_orders, backgroundColor: 'rgba(0,214,143,0.7)', borderColor: '#00d68f', borderWidth: 1, stack: 's' },
    ]
  },
  options: { ...COMMON, scales: { ...COMMON.scales, x: { ...COMMON.scales.x, stacked: true }, y: { ...COMMON.scales.y, stacked: true } } }
});

// ═══════════════════════════ SALES HISTORY ════════════════
new Chart(document.getElementById('chSalesHist'), {
  type: 'bar',
  data: {
    labels: D.dates,
    datasets: [
      { label: 'UH', data: D.uh_sales, backgroundColor: 'rgba(255,169,77,0.8)', borderColor: '#ffa94d', borderWidth: 1, stack: 's' },
      { label: 'SH', data: D.sh_sales, backgroundColor: 'rgba(255,107,107,0.7)', borderColor: '#ff6b6b', borderWidth: 1, stack: 's' },
    ]
  },
  options: { ...COMMON, scales: { ...COMMON.scales, x: { ...COMMON.scales.x, stacked: true }, y: { ...COMMON.scales.y, stacked: true } } }
});

// ═══════════════════════════ GA4 SESSIONS ═════════════════
new Chart(document.getElementById('chSessions'), {
  type: 'line',
  data: {
    labels: D.dates,
    datasets: [{ label: 'Сесії', data: D.ga4_sess, borderColor: '#339af0', backgroundColor: 'rgba(51,154,240,0.15)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 3 }]
  },
  options: COMMON
});

// ═══════════════════════════ META SPEND ═══════════════════
new Chart(document.getElementById('chMetaSpend'), {
  type: 'line',
  data: {
    labels: D.dates,
    datasets: [{ label: 'Витрати ₴', data: D.meta_spend, borderColor: '#ffa94d', backgroundColor: 'rgba(255,169,77,0.15)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 3 }]
  },
  options: COMMON
});

// ═══════════════════════════ CRM HISTORY ══════════════════
const chCrm = document.getElementById('chCrm');
if (chCrm) new Chart(chCrm, {
  type: 'line',
  data: {
    labels: D.dates,
    datasets: [{ label: 'Замовлень', data: D.crm_orders, borderColor: '#a29bfe', backgroundColor: 'rgba(162,155,254,0.15)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 3 }]
  },
  options: COMMON
});

// ═══════════════════════════ PODR LISTS ═══════════════════
function renderPodr(elId, podrObj) {
  const el = document.getElementById(elId);
  if (!el) return;
  const items = Object.entries(podrObj).sort((a,b) => b[1] - a[1]);
  if (!items.length) { el.innerHTML = '<div style="text-align:center;color:var(--td);padding:20px">Немає даних</div>'; return; }
  const max = items[0][1] || 1;
  el.innerHTML = items.map(([name, val]) => {
    const pct = Math.max(2, Math.round(val / max * 100));
    return `<div class="bar-row">
      <div class="bar-name" title="${name}">${name}</div>
      <div class="bar-wrap"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="bar-val">${val.toLocaleString('uk').replace(/,/g,' ')}</div>
    </div>`;
  }).join('');
}
renderPodr('uhOrdersPodr', D.uh_orders_podr);
renderPodr('shOrdersPodr', D.sh_orders_podr);
renderPodr('uhSalesPodr',  D.uh_sales_podr);
renderPodr('shSalesPodr',  D.sh_sales_podr);

// ═══════════════════════════ MANAGERS ═════════════════════
const mgrBody = document.getElementById('mgrBody');
if (mgrBody) {
  if (!D.managers.length) {
    mgrBody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--td)">Немає даних</td></tr>';
  } else {
    mgrBody.innerHTML = D.managers.map(m => {
      const refuseBadge = m.refuse_pct >= 12 ? 'br' : m.refuse_pct >= 5 ? 'bo' : 'bg';
      return `<tr>
        <td>${m.name}</td>
        <td class="r num">${m.orders}</td>
        <td class="r num">${m.revenue.toLocaleString('uk').replace(/,/g,' ')}</td>
        <td class="r num">${m.refused}</td>
        <td class="r"><span class="badge ${refuseBadge}">${m.refuse_pct.toFixed(1)}%</span></td>
      </tr>`;
    }).join('');
  }
}

// ═══════════════════════════ CAMPAIGNS ════════════════════
const campBody = document.getElementById('campBody');
if (campBody) {
  if (!D.meta_camps.length) {
    campBody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--td)">Немає кампаній за день</td></tr>';
  } else {
    campBody.innerHTML = D.meta_camps.map(c => `<tr>
      <td title="${c.campaign}">${c.campaign.length > 35 ? c.campaign.substr(0, 35)+'...' : c.campaign}</td>
      <td><span class="badge bb">${c.account}</span></td>
      <td class="r num">${c.spend.toLocaleString('uk')}</td>
      <td class="r num">${c.impressions.toLocaleString('uk').replace(/,/g,' ')}</td>
      <td class="r num">${c.clicks}</td>
      <td class="r num">${c.cpc}</td>
      <td class="r num">${c.ctr}%</td>
      <td class="r num">${c.results}</td>
    </tr>`).join('');
  }
}

// ═══════════════════════════ GA4 SOURCES ══════════════════
const ga4Sources = document.getElementById('ga4Sources');
if (ga4Sources) {
  if (!D.ga4_sources.length) {
    ga4Sources.innerHTML = '<div style="text-align:center;color:var(--td);padding:20px">Немає даних</div>';
  } else {
    const max = D.ga4_sources[0].sessions || 1;
    ga4Sources.innerHTML = D.ga4_sources.map(s => {
      const pct = Math.max(2, Math.round(s.sessions / max * 100));
      const label = s.source + (s.medium && s.medium !== '(none)' ? ' / ' + s.medium : '');
      return `<div class="bar-row">
        <div class="bar-name" title="${label}">${label}</div>
        <div class="bar-wrap"><div class="bar-fill" style="width:${pct}%"></div></div>
        <div class="bar-val">${s.sessions}</div>
      </div>`;
    }).join('');
  }
}

// ═══════════════════════════ GA4 PAGES ════════════════════
const ga4Pages = document.getElementById('ga4Pages');
if (ga4Pages) {
  if (!D.ga4_pages.length) {
    ga4Pages.innerHTML = '<div style="text-align:center;color:var(--td);padding:20px">Немає даних</div>';
  } else {
    const max = D.ga4_pages[0].views || 1;
    ga4Pages.innerHTML = D.ga4_pages.map(p => {
      const pct = Math.max(2, Math.round(p.views / max * 100));
      return `<div class="bar-row">
        <div class="bar-name" title="${p.path}">${p.title || p.path}</div>
        <div class="bar-wrap"><div class="bar-fill" style="width:${pct}%;background:linear-gradient(90deg,var(--g),#34d399)"></div></div>
        <div class="bar-val">${p.views}</div>
      </div>`;
    }).join('');
  }
}

// ═══════════════════════════ DEVICES ══════════════════════
const chDevices = document.getElementById('chDevices');
if (chDevices && D.ga4_devices.length) {
  new Chart(chDevices, {
    type: 'doughnut',
    data: {
      labels: D.ga4_devices.map(d => d.device),
      datasets: [{ data: D.ga4_devices.map(d => d.sessions), backgroundColor: ['#6c5ce7', '#00d68f', '#ffa94d', '#339af0'], borderWidth: 2, borderColor: '#151929' }]
    },
    options: { ...COMMON, scales: {}, cutout: '65%' }
  });
}
</script>
</body></html>
'''
    return html


# ──────────────────────── MAIN ────────────────────────────────

def main():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"\n📊 Генерація дашборду за {yesterday}")

    data = load_data(yesterday)
    if not data:
        print(f"❌ Файл history/{yesterday}.json не знайдено")
        print("   Спочатку запусти: python fetch_data.py")
        return

    history = load_history(30)
    print(f"   📂 Завантажено історію: {len(history)} днів")

    html = build_html(data, history)

    out = DOCS_DIR / "index.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    # Архів за конкретну дату
    archive_dir = DOCS_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)
    archive_path = archive_dir / f"{yesterday}.html"
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Дашборд згенеровано:")
    print(f"   → {out}")
    print(f"   → {archive_path}")
    print(f"\n🌐 Після push на GitHub: https://grigorijtetlasov-uh.github.io/uh-analytics/\n")

if __name__ == "__main__":
    main()
