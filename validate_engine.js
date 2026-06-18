/* validate_engine.js — real-data доказ Фази 2.
 * Ганяє JS-двигун (iris_range.js) на docs/daily*.json і звіряє з docs/data*.json.
 * Точний аналог validate_daily.py, але через браузерний двигун.
 * Запуск на сервері:  cd ~/uh-analytics && node validate_engine.js
 * (потрібен Node. Перевір: node --version)
 */
const fs = require("fs");
const path = require("path");
const IRIS = require("./iris_range.js");

const GROUPS = ["roll", "amebli", "seti", "roznica"];
const PIPEK = ["leads_total", "in_progress", "production", "shipping",
               "sale", "refused", "returned", "lead", "unknown"];

function load(p) { return JSON.parse(fs.readFileSync(p, "utf-8")); }
function lastDay(ym) { const a = ym.split("-").map(Number); return new Date(a[0], a[1], 0).getDate(); }
function pad2(d) { return ("" + d).padStart(2, "0"); }
function sum(arr) { return (arr || []).reduce((s, x) => s + x, 0); }

function check(dataF, dailyF) {
  if (!fs.existsSync(dataF) || !fs.existsSync(dailyF)) {
    console.log("\nskip (no file): " + (fs.existsSync(dataF) ? dailyF : dataF));
    return true;
  }
  const data = load(dataF);
  const layer = load(dailyF);
  const ym = data.month;
  const months = {}; months[ym] = layer;
  const dc = data.day_count || 31;
  const cur = dataF.endsWith("data.json");
  const ld = lastDay(ym);
  const from = ym + "-01";
  const Aobs = IRIS.range(months, from, ym + "-" + pad2(cur ? dc : ld));  // обсяг/відгрузки: зріз по day_count
  const A = IRIS.range(months, from, ym + "-" + pad2(ld));                 // 1С/CRM: весь місяць

  console.log("\n== " + dailyF + "  (day_count=" + dc + ", " + (cur ? "поточний" : "минулий") + ")");
  let fails = [];
  function row(label, exp, got, tol) {
    tol = tol || 0;
    const ok = Math.abs((got || 0) - (exp || 0)) <= tol;
    console.log("  " + (ok ? "OK " : "XX ") + label.padEnd(22) + " data=" + exp + "  js=" + got + (ok ? "" : "  d=" + ((got || 0) - (exp || 0))));
    if (!ok) fails.push(label);
  }

  let dObs = 0; for (const g of GROUPS) dObs += sum((data.groups[g] || {}).june);
  row("obsyag", Math.round(dObs), Aobs.obsyag);
  row("vidgruzky", Math.round(sum(data.shipments.june)), Aobs.shipments.total);
  row("conversion %", data.kpi.conversion.value, A.conversion.value, 0.2);
  const rf = data.kpi.refuse || {};
  row("refuse refused", rf.refused || 0, A.refuse.refused);
  row("refuse sold", rf.active || 0, A.refuse.active);
  row("refuse %", rf.of_orders || 0, A.refuse.of_orders, 0.2);
  const pl = (data.funnel || {}).pipeline || {};
  for (const c of PIPEK) row("funnel." + c, pl[c] || 0, A.pipeline[c] || 0);
  for (const c of ["spam", "dubli", "nedodzvon", "lost"]) row("sec3." + c, data.funnel[c] || 0, A.section3[c] || 0);
  for (const g of GROUPS) {
    const dm = (data.groups[g] || {}).margin, jm = (A.groups[g] || {}).margin;
    if (dm != null || jm != null) {
      row("margin." + g + " %", dm, jm, 0.2);
      row("coverage." + g, (data.groups[g] || {}).coverage, (A.groups[g] || {}).coverage, 0.01);
    }
  }
  if (data.products && data.products[0] && A.products[0]) {
    const dp = data.products[0], ap = A.products[0];
    const ok = dp.name === ap.name;
    console.log("  " + (ok ? "OK " : "XX ") + "top-product".padEnd(22) + " data='" + dp.name + "' js='" + ap.name + "'");
    if (!ok) fails.push("top-product");
    row("top-product revenue", dp.revenue, ap.revenue);
    row("top-product qty", dp.qty, ap.qty);
    row("top-product count", dp.count || 0, ap.count);
  }
  if (data.managers && data.managers[0] && A.managers[0]) {
    const dm = data.managers[0], am = A.managers[0];
    const ok = dm.name === am.name;
    console.log("  " + (ok ? "OK " : "XX ") + "top-manager".padEnd(22) + " data='" + dm.name + "' js='" + am.name + "'");
    if (!ok) fails.push("top-manager");
    if (dm.conversion != null) row("top-mgr conv %", dm.conversion, am.conversion, 0.2);
    row("top-mgr returns", dm.returns || 0, am.returns);
  }
  console.log("  -> " + (fails.length ? "MISMATCH: " + fails.join(", ") : "ALL MATCH"));
  return fails.length === 0;
}

const pairs = [
  ["docs/data.json", "docs/daily.json"],
  ["docs/data-2026-05.json", "docs/daily-2026-05.json"],
  ["docs/data-2026-04.json", "docs/daily-2026-04.json"],
];
let allok = true;
for (const [d, dl] of pairs) { try { allok = check(d, dl) && allok; } catch (e) { console.log("ERR " + dl + ": " + e.message); allok = false; } }
console.log("\n" + (allok ? "JS ENGINE == MONTH PAGES on real data — Phase 2 engine proven"
                           : "MISMATCHES — paste output, I will fix the engine"));
