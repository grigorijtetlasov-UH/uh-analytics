/* iris_range.js — IRIS range engine (Фаза 2, Б)
 * Підсумовує денний шар (docs/daily*.json) за довільний діапазон [from,to]
 * і виводить ВСІ блоки тими самими формулами, що й Python-еталон (validate_daily.py).
 * Працює і в Node (module.exports), і в браузері (window.IRIS).
 *
 * months: { "2026-06": <dayDict>, "2026-05": <dayDict>, ... }
 *   де dayDict — це обʼєкт "day" з daily*.json: { "1": {...}, "2": {...}, ... }
 * from/to: "YYYY-MM-DD" (включно).
 */
(function (global) {
  "use strict";

  var GROUPS = ["roll", "amebli", "seti", "roznica"];
  var PIPE = ["in_progress", "production", "shipping", "sale",
              "refused", "returned", "lead", "claim"];

  // Python-сумісне округлення (half-to-even), щоб точно збігатись із round(x, nd)
  function pyround(x, nd) {
    if (x === null || x === undefined || isNaN(x)) return x;
    var m = Math.pow(10, nd || 0);
    var v = x * m;
    var r = Math.round(v);
    // межовий випадок рівно .5 → до парного (як у Python)
    if (Math.abs(v - Math.trunc(v) - 0.5) < 1e-9) {
      var fl = Math.floor(v);
      r = (fl % 2 === 0) ? fl : fl + 1;
    }
    return r / m;
  }
  function r0(x) { return pyround(x, 0); }

  function pad2(d) { return ("" + d).length < 2 ? "0" + d : "" + d; }

  // ── АГРЕГАЦІЯ компонентів за діапазоном [from,to] ──
  function aggregate(months, from, to) {
    var R = {
      ch: {}, grp: {}, mgr: {}, fun: {},
      kpi: { order: 0, refused: 0, lost: 0, lead: 0, spam: 0 },
      cf: { spam: 0, dubli: 0, nedodzvon: 0, lost: 0 },
      prod: {}, ship: 0, mrg: {},
      r1c: { ov: { sold: 0, refused: 0 }, grp: {} },
      dchart: {}
    };
    for (var ym in months) {
      if (!months.hasOwnProperty(ym)) continue;
      var day = months[ym].day ? months[ym].day : months[ym];
      for (var dk in day) {
        if (!day.hasOwnProperty(dk)) continue;
        var iso = ym + "-" + pad2(dk);
        if (iso < from || iso > to) continue;
        var d = day[dk], k, t, v, g, cat;

        for (k in d.ch) { t = R.ch[k] || (R.ch[k] = { rev: 0, n: 0 }); t.rev += d.ch[k].rev; t.n += d.ch[k].n; }
        for (k in d.grp) { t = R.grp[k] || (R.grp[k] = { rev: 0, n: 0 }); t.rev += d.grp[k].rev; t.n += d.grp[k].n; }
        for (k in d.mgr) { v = d.mgr[k]; t = R.mgr[k] || (R.mgr[k] = { won: 0, ref: 0, lost: 0, ret: 0, rev: 0 }); t.won += v.won; t.ref += v.ref; t.lost += v.lost; t.ret += v.ret; t.rev += v.rev; }
        for (k in d.fun) { R.fun[k] = (R.fun[k] || 0) + d.fun[k]; }
        for (k in R.kpi) { R.kpi[k] += (d.kpi && d.kpi[k]) || 0; }
        for (k in R.cf) { R.cf[k] += (d.cf && d.cf[k]) || 0; }
        for (k in d.prod) { v = d.prod[k]; t = R.prod[k] || (R.prod[k] = { rev: 0, qty: 0, n: 0 }); t.rev += v.rev; t.qty += v.qty; t.n += v.n; }
        R.ship += d.ship || 0;
        for (g in d.mrg) {
          var tg = R.mrg[g] || (R.mrg[g] = {});
          for (cat in d.mrg[g]) { v = d.mrg[g][cat]; t = tg[cat] || (tg[cat] = { rev: 0, qty: 0, rcov: 0, ccov: 0 }); t.rev += v.rev; t.qty += v.qty; t.rcov += v.rcov; t.ccov += v.ccov; }
        }
        if (d.r1c) {
          R.r1c.ov.sold += d.r1c.ov.sold; R.r1c.ov.refused += d.r1c.ov.refused;
          for (g in d.r1c.grp) { v = d.r1c.grp[g]; t = R.r1c.grp[g] || (R.r1c.grp[g] = { sold: 0, refused: 0 }); t.sold += v.sold; t.refused += v.refused; }
        }
        var dr = 0; for (k in d.ch) dr += d.ch[k].rev;
        R.dchart[iso] = (R.dchart[iso] || 0) + dr;
      }
    }
    return R;
  }

  // ── ПОХІДНІ блоки (= формули місячних блоків) ──
  function derive(R, topProducts) {
    var out = {}, k, g, cats, t;

    // обсяг / замовлення / середній чек
    var obs = 0, ord = 0;
    for (g in R.grp) { obs += R.grp[g].rev; ord += R.grp[g].n; }
    out.obsyag = r0(obs);
    out.orders = ord;
    out.avg_check = ord ? r0(obs / ord) : 0;

    // конверсія = (order+refused)/(order+refused+lost)
    var sold = R.kpi.order + R.kpi.refused, dec = sold + R.kpi.lost;
    out.conversion = { value: dec ? pyround(sold / dec * 100, 1) : 0.0,
                       sold: sold, lost: R.kpi.lost, orders: R.kpi.order };

    // відмови (1С)
    var ov = R.r1c.ov;
    out.refuse = { refused: ov.refused, active: ov.sold,
                   of_orders: ov.sold ? pyround(ov.refused / ov.sold * 100, 1) : 0.0 };

    // канали
    out.channels = [];
    for (k in R.ch) { t = R.ch[k]; out.channels.push({ name: k, revenue: r0(t.rev), orders: t.n, avg_check: t.n ? r0(t.rev / t.n) : 0 }); }
    out.channels.sort(function (a, b) { return b.revenue - a.revenue; });

    // групи (обсяг CRM + маржа 1С)
    out.groups = {};
    for (var gi = 0; gi < GROUPS.length; gi++) {
      g = GROUPS[gi];
      var gr = R.grp[g] || { rev: 0, n: 0 };
      var blk = { rev: r0(gr.rev), n: gr.n, margin: null, coverage: 0.0, reliable: false, cats: [] };
      if (R.mrg[g]) {
        var grev = 0, grcov = 0, gccov = 0;
        cats = R.mrg[g];
        for (k in cats) { grev += cats[k].rev; grcov += cats[k].rcov; gccov += cats[k].ccov; }
        if (grev > 0) {
          blk.margin = grcov > 0 ? pyround((grcov - gccov) / grcov * 100, 1) : null;
          blk.coverage = pyround(grcov / grev, 2);
          blk.reliable = blk.coverage >= 0.7;
          // розбивка по категоріях (за спаданням виручки)
          for (k in cats) {
            var cr = cats[k].rev; if (cr <= 0) continue;
            var rc = cats[k].rcov, cc = cats[k].ccov;
            blk.cats.push({ n: k, rev: r0(cr), share: pyround(cr / grev, 4),
                            m: rc > 0 ? pyround((rc - cc) / rc * 100, 1) : null,
                            cov: pyround(rc / cr, 2),
                            ac: cats[k].qty ? r0(cr / cats[k].qty) : 0 });
          }
          blk.cats.sort(function (a, b) { return b.rev - a.rev; });
        }
      }
      out.groups[g] = blk;
    }

    // менеджери
    out.managers = [];
    for (k in R.mgr) {
      t = R.mgr[k];
      var msold = t.won + t.ref;
      out.managers.push({
        name: k, orders: t.won, revenue: r0(t.rev),
        avg_check: t.won ? r0(t.rev / t.won) : 0,
        refuse_pct: msold ? pyround(t.ref / msold * 100, 1) : 0.0,
        conversion: (t.won + t.lost) ? pyround(t.won / (t.won + t.lost) * 100, 1) : 0.0,
        returns: t.ret
      });
    }
    out.managers.sort(function (a, b) { return b.revenue - a.revenue; });

    // товари (топ N)
    var prods = [];
    for (k in R.prod) { t = R.prod[k]; prods.push({ name: k, revenue: r0(t.rev), qty: t.qty, count: t.n }); }
    prods.sort(function (a, b) { return b.revenue - a.revenue; });
    out.products = prods.slice(0, topProducts || 50);

    // воронка (pipeline) + Секція 3
    var pipe = { leads_total: 0 };
    for (var pi = 0; pi < PIPE.length; pi++) { pipe[PIPE[pi]] = R.fun[PIPE[pi]] || 0; pipe.leads_total += R.fun[PIPE[pi]] || 0; }
    pipe.unknown = R.fun.unknown || 0;
    out.pipeline = pipe;
    out.section3 = { spam: R.cf.spam, dubli: R.cf.dubli, nedodzvon: R.cf.nedodzvon, lost: R.cf.lost };

    // відгрузки 1С (сума по діапазону)
    out.shipments = { total: r0(R.ship) };

    // денний графік обсягу (для лінії)
    out.daily = R.dchart;
    return out;
  }

  // зручний фасад: одразу діапазон → готові блоки
  function range(months, from, to, topProducts) {
    return derive(aggregate(months, from, to), topProducts);
  }

  var IRIS = { aggregate: aggregate, derive: derive, range: range, pyround: pyround, GROUPS: GROUPS, PIPE: PIPE };

  if (typeof module !== "undefined" && module.exports) module.exports = IRIS;
  else global.IRIS = IRIS;

})(typeof window !== "undefined" ? window : globalThis);
