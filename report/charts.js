/*
 * report/charts.js — live SVG charts for the morning/nightly reports.
 *
 * Replaces the matplotlib PNG/SVGs the generators used to bake into each
 * page. Every chart is computed from the daily series (data/daily/<year>.json)
 * for the report's date, with the same windows, series and colours as the
 * originals in generate_morning_report_content.py.
 *
 * Exposes window.ReportCharts = { render(el, id, ctx) }.
 */
(function () {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  var W = 1000, H = 440;
  var PAD = { top: 44, right: 70, bottom: 44, left: 64 };
  var C = {
    fig: "#0a0a0c", axes: "#1c1c1e", grid: "#3a3a3c", text: "#e5e5e7", muted: "#8e8e93",
    blue: "#0a84ff", green: "#32d74b", yellow: "#ffd60a", red: "#ff453a",
    orange: "#ff9500", purple: "#bf5af2", grey: "#8e8e93",
  };
  var WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

  // ---------------------------------------------------------------- dates --
  function parseDate(s) { var p = s.split("-"); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])); }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function addDays(s, n) { var d = parseDate(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); }
  function mmdd(s) { return s.slice(5, 7) + "/" + s.slice(8, 10); }
  function weekday(s) { return (parseDate(s).getUTCDay() + 6) % 7; } // Monday = 0
  function range(end, n) { var out = []; for (var i = n - 1; i >= 0; i--) out.push(addDays(end, -i)); return out; }

  // ---------------------------------------------------------------- scale --
  function niceTicks(lo, hi, count) {
    if (!(hi > lo)) { hi = lo + 1; }
    var span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / count)));
    var err = span / count / step;
    step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
    // Round outward so every value fits inside the first and last tick.
    var ticks = [], t = Math.floor(lo / step) * step, end = Math.ceil(hi / step - 1e-9) * step;
    for (; t <= end + step * 1e-9; t += step) ticks.push(+t.toFixed(10));
    return { ticks: ticks, lo: ticks[0], hi: ticks[ticks.length - 1] };
  }
  function fmtTick(v) {
    var a = Math.abs(v);
    if (a >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
    return +v.toFixed(2) + "";
  }

  // ------------------------------------------------------------------ svg --
  function el(tag, attrs, parent, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) if (attrs[k] !== undefined && attrs[k] !== null) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function tip(node, text) { el("title", {}, node, text); return node; }

  /*
   * spec = {
   *   title, x: [labels], xFull: [iso dates for tooltips],
   *   axes: [{label, min, max}],              // 0 = left, 1 = right, 2 = far right
   *   bands: [{from, to, color, label}],      // horizontal zones on axis 0
   *   series: [{type: line|bar|scatter, axis, data, color, label, width, alpha,
   *             marker: circle|triangle|square|down, stack, fmt}]
   * }
   */
  function plot(container, spec) {
    var hasFar = spec.axes.length > 2;
    var pad = { top: PAD.top, right: PAD.right + (hasFar ? 56 : 0), bottom: PAD.bottom, left: PAD.left };
    var pw = W - pad.left - pad.right, ph = H - pad.top - pad.bottom;
    var n = spec.x.length;
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, class: "rc-svg", role: "img", "aria-label": spec.title });
    el("rect", { x: 0, y: 0, width: W, height: H, fill: C.fig }, svg);
    el("rect", { x: pad.left, y: pad.top, width: pw, height: ph, fill: C.axes }, svg);
    el("text", { x: W / 2, y: 26, "text-anchor": "middle", class: "rc-title" }, svg, spec.title);

    // stacked bars: accumulate per x per axis
    var stackTops = {};
    spec.series.forEach(function (s) {
      if (s.type === "bar" && s.stack) {
        s._base = s.data.map(function (_, i) { return (stackTops[s.axis + ":" + i] || 0); });
        s.data.forEach(function (v, i) { stackTops[s.axis + ":" + i] = (stackTops[s.axis + ":" + i] || 0) + (v || 0); });
      }
    });

    var scales = spec.axes.map(function (ax, ai) {
      var vals = [];
      spec.series.forEach(function (s) {
        if ((s.axis || 0) !== ai) return;
        s.data.forEach(function (v, i) {
          if (v === null || v === undefined || isNaN(v)) return;
          vals.push(s._base ? s._base[i] + v : v);
        });
      });
      var lo = ax.min !== undefined ? ax.min : Math.min.apply(null, ax.zero === false ? vals : vals.concat([0]));
      var hi = ax.max !== undefined ? ax.max : Math.max.apply(null, vals.concat([lo + 1]));
      if (ax.max === undefined) hi += (hi - lo) * 0.06;
      if (ax.zero === false && ax.min === undefined) lo -= (hi - lo) * 0.06;
      var t = ax.min !== undefined && ax.max !== undefined ? niceTicks(ax.min, ax.max, 5) : niceTicks(lo, hi, 6);
      if (ax.min !== undefined) t.lo = ax.min;
      if (ax.max !== undefined) t.hi = ax.max;
      t.ticks = t.ticks.filter(function (v) { return v >= t.lo - 1e-9 && v <= t.hi + 1e-9; });
      return { lo: t.lo, hi: t.hi, ticks: t.ticks, y: function (v) { return pad.top + ph - (v - t.lo) / (t.hi - t.lo) * ph; } };
    });

    var band = pw / Math.max(n, 1);
    function xc(i) { return pad.left + band * (i + 0.5); }

    // zones
    (spec.bands || []).forEach(function (b) {
      var y1 = scales[0].y(b.to), y2 = scales[0].y(b.from);
      el("rect", { x: pad.left, y: y1, width: pw, height: y2 - y1, fill: b.color, "fill-opacity": 0.15 }, svg);
    });

    // grid + axes
    var g = el("g", { class: "rc-axis" }, svg);
    scales[0].ticks.forEach(function (v) {
      var y = scales[0].y(v);
      el("line", { x1: pad.left, x2: pad.left + pw, y1: y, y2: y, stroke: C.grid, "stroke-dasharray": "4 4", "stroke-width": 0.8 }, g);
      el("text", { x: pad.left - 8, y: y + 4, "text-anchor": "end" }, g, fmtTick(v));
    });
    scales.slice(1).forEach(function (sc, k) {
      var x0 = pad.left + pw + (k === 1 ? 56 : 0);
      el("line", { x1: x0, x2: x0, y1: pad.top, y2: pad.top + ph, stroke: C.muted, "stroke-width": 0.8 }, g);
      sc.ticks.forEach(function (v) { el("text", { x: x0 + 8, y: sc.y(v) + 4 }, g, fmtTick(v)); });
    });
    spec.axes.forEach(function (ax, ai) {
      if (!ax.label) return;
      var x = ai === 0 ? 16 : ai === 1 ? pad.left + pw + 50 : pad.left + pw + 106;
      el("text", { x: x, y: pad.top + ph / 2, transform: "rotate(-90 " + x + " " + (pad.top + ph / 2) + ")", "text-anchor": "middle", class: "rc-axlabel" }, g, ax.label);
    });
    var every = Math.max(1, Math.ceil(n / 8));
    spec.x.forEach(function (lab, i) {
      if (i % every !== (n - 1) % every) return;
      el("text", { x: xc(i), y: pad.top + ph + 20, "text-anchor": "middle" }, g, lab);
    });

    // series
    var bars = spec.series.filter(function (s) { return s.type === "bar"; });
    var sideBars = bars.filter(function (s) { return !s.stack; });
    spec.series.forEach(function (s) {
      var sc = scales[s.axis || 0], fmt = s.fmt || fmtTick;
      var layer = el("g", {}, svg);
      if (s.type === "bar") {
        var k = sideBars.indexOf(s), groups = s.stack ? 1 : Math.max(sideBars.length, 1);
        var bw = band * 0.7 / groups;
        s.data.forEach(function (v, i) {
          if (!v) return;
          var base = s._base ? s._base[i] : 0;
          var x = xc(i) - band * 0.35 + (s.stack ? 0 : k * bw);
          var y1 = sc.y(base + v), y2 = sc.y(base);
          tip(el("rect", { x: x, y: y1, width: bw, height: Math.max(y2 - y1, 0.5), fill: s.color, "fill-opacity": s.alpha || 0.85 }, layer),
            (spec.xFull ? spec.xFull[i] : spec.x[i]) + " · " + s.label + ": " + fmt(v));
        });
      } else {
        var path = "", pen = false;
        s.data.forEach(function (v, i) {
          if (v === null || v === undefined || isNaN(v)) { pen = false; return; }
          path += (pen ? "L" : "M") + xc(i).toFixed(1) + " " + sc.y(v).toFixed(1);
          pen = true;
        });
        if (s.type === "line" && path && s.fill) {
          // area under the line, per contiguous run
          path.split("M").filter(Boolean).forEach(function (run) {
            var pts = run.split("L"), first = pts[0].split(" ")[0], last = pts[pts.length - 1].split(" ")[0];
            el("path", { d: "M" + first + " " + sc.y(sc.lo) + "L" + run + "L" + last + " " + sc.y(sc.lo) + "Z", fill: s.color, "fill-opacity": s.fill }, layer);
          });
        }
        if (s.type === "line" && path) {
          el("path", { d: path, fill: "none", stroke: s.color, "stroke-width": s.width || 2.5, "stroke-opacity": s.alpha || 1, "stroke-linejoin": "round", "stroke-dasharray": s.dash || null }, layer);
        }
        if (s.marker !== false) {
          s.data.forEach(function (v, i) {
            if (v === null || v === undefined || isNaN(v)) return;
            var x = xc(i), y = sc.y(v), m, label = (spec.xFull ? spec.xFull[i] : spec.x[i]) + " · " + s.label + ": " + fmt(v);
            var r = s.type === "scatter" ? 7 : 4.5;
            if (s.marker === "triangle") m = el("path", { d: "M" + x + " " + (y - r) + "L" + (x + r) + " " + (y + r * 0.8) + "L" + (x - r) + " " + (y + r * 0.8) + "Z" }, layer);
            else if (s.marker === "down") m = el("path", { d: "M" + x + " " + (y + r) + "L" + (x + r) + " " + (y - r * 0.8) + "L" + (x - r) + " " + (y - r * 0.8) + "Z" }, layer);
            else if (s.marker === "square") m = el("rect", { x: x - r * 0.85, y: y - r * 0.85, width: r * 1.7, height: r * 1.7 }, layer);
            else m = el("circle", { cx: x, cy: y, r: r * 0.85 }, layer);
            m.setAttribute("fill", s.color);
            m.setAttribute("fill-opacity", s.alpha || 1);
            tip(m, label);
          });
        }
      }
    });

    // legend (matplotlib 'upper left')
    var items = (spec.bands || []).map(function (b) { return { label: b.label, color: b.color, kind: "band" }; })
      .concat(spec.series.filter(function (s) { return s.label && !s.noLegend; }).map(function (s) { return { label: s.label, color: s.color, kind: s.type }; }));
    if (items.length) {
      var lg = el("g", { class: "rc-legend" }, svg);
      var lw = 16 + 8.2 * Math.max.apply(null, items.map(function (it) { return it.label.length; })) + 26;
      el("rect", { x: pad.left + 8, y: pad.top + 8, width: lw, height: items.length * 19 + 8, rx: 4, fill: C.fig, "fill-opacity": 0.72, stroke: C.grid }, lg);
      items.forEach(function (it, i) {
        var y = pad.top + 22 + i * 19, x = pad.left + 16;
        if (it.kind === "line") el("line", { x1: x, x2: x + 20, y1: y - 4, y2: y - 4, stroke: it.color, "stroke-width": 2.5 }, lg);
        else el("rect", { x: x + 2, y: y - 10, width: 16, height: 11, fill: it.color, "fill-opacity": it.kind === "band" ? 0.35 : 0.85 }, lg);
        el("text", { x: x + 28, y: y }, lg, it.label);
      });
    }

    container.innerHTML = "";
    container.appendChild(svg);
  }

  // Pie chart: spec = { title, slices: [{label, value, color}] }
  function pie(container, spec) {
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, class: "rc-svg", role: "img", "aria-label": spec.title });
    el("rect", { x: 0, y: 0, width: W, height: H, fill: C.fig }, svg);
    el("text", { x: W / 2, y: 30, "text-anchor": "middle", class: "rc-title" }, svg, spec.title);
    var total = spec.slices.reduce(function (a, s) { return a + s.value; }, 0);
    var cx = W / 2, cy = H / 2 + 18, r = 165, a0 = -Math.PI / 2 + (50 / 180) * Math.PI;
    spec.slices.forEach(function (s) {
      var frac = s.value / total, a1 = a0 + frac * 2 * Math.PI, mid = (a0 + a1) / 2;
      var large = frac > 0.5 ? 1 : 0;
      var d = "M" + cx + " " + cy + "L" + (cx + r * Math.cos(a0)) + " " + (cy + r * Math.sin(a0))
        + "A" + r + " " + r + " 0 " + large + " 1 " + (cx + r * Math.cos(a1)) + " " + (cy + r * Math.sin(a1)) + "Z";
      tip(el("path", { d: d, fill: s.color, stroke: C.fig, "stroke-width": 2 }, svg), s.label + ": " + Math.round(s.value) + " g/day avg");
      el("text", { x: cx + r * 0.6 * Math.cos(mid), y: cy + r * 0.6 * Math.sin(mid) + 6, "text-anchor": "middle", class: "rc-pie-pct" }, svg, (frac * 100).toFixed(1) + "%");
      el("text", { x: cx + (r + 34) * Math.cos(mid), y: cy + (r + 34) * Math.sin(mid) + 6, "text-anchor": Math.cos(mid) >= 0 ? "start" : "end", class: "rc-pie-label" }, svg, s.label);
      a0 = a1;
    });
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function empty(container, msg) {
    container.innerHTML = '<div class="rc-empty">' + msg + "</div>";
  }

  // ------------------------------------------------------------- metrics --
  function composite(row) {
    // WHOOP 50% + Garmin Sleep Score 30% + 8Sleep 20% (missing counts as 0),
    // matching calculate_composite_recovery().
    if (!row) return null;
    if (row.recovery == null && row.g_sleep_score == null && row.e_score == null) return null;
    return (row.recovery || 0) * 0.5 + (row.g_sleep_score || 0) * 0.3 + (row.e_score || 0) * 0.2;
  }
  function nz(v) { return v === null || v === undefined || v === 0 ? null : v; }
  function r1(v) { return v === null || v === undefined ? null : Math.round(v * 10) / 10; }

  // --------------------------------------------------------------- charts --
  var CHARTS = {
    "recovery-trends": function (ctx) {
      var days = range(ctx.date, 14), get = ctx.day;
      return {
        title: "Recovery Trends (Multi-Source)",
        x: days.map(mmdd), xFull: days,
        axes: [{ label: "Score (0-100)", min: 0, max: 105 }],
        bands: [
          { from: 0, to: 30, color: C.red, label: "Critical (<30%)" },
          { from: 30, to: 60, color: C.yellow, label: "Moderate (30-60%)" },
          { from: 60, to: 105, color: C.green, label: "Good (>60%)" },
        ],
        series: [
          { type: "line", label: "WHOOP Recovery", color: C.blue, data: days.map(function (d) { return nz(get(d).recovery); }) },
          { type: "line", label: "Garmin Sleep Score", color: C.green, marker: "triangle", data: days.map(function (d) { return nz(get(d).g_sleep_score); }) },
          { type: "line", label: "8Sleep Fitness Score", color: C.purple, marker: "square", data: days.map(function (d) { return nz(get(d).e_score); }) },
          {
            type: "scatter", label: "Away from home (no 8Sleep)", color: C.orange, marker: "down",
            data: days.map(function (d) { var r = get(d); return !r.e_score && (r.recovery || r.g_bb) ? 5 : null; }),
            fmt: function () { return "no 8Sleep data"; },
          },
        ],
      };
    },

    "strength-benchmark": function (ctx) {
      // Average lifting volume per weekday (lifting days only) over the trailing 26 weeks.
      var days = range(ctx.date, 182), sum = [0, 0, 0, 0, 0, 0, 0], cnt = [0, 0, 0, 0, 0, 0, 0];
      days.forEach(function (d) {
        var v = ctx.day(d).volume_lbs, w = weekday(d);
        if (v) { sum[w] += v; cnt[w] += 1; }
      });
      var avg = sum.map(function (s, i) { return cnt[i] ? Math.round(s / cnt[i]) : 0; });
      var today = weekday(ctx.date);
      return {
        title: "Avg Weekly Lifting Volume (" + ctx.date + ")",
        x: WEEKDAYS, axes: [{ label: "Lifting Volume (lbs)" }],
        series: [
          { type: "bar", label: "Avg volume", noLegend: true, color: C.green, alpha: 0.8, data: avg.map(function (v, i) { return i === today ? null : v; }) },
          { type: "bar", stack: true, label: WEEKDAYS[today] + " (report day)", color: C.blue, data: avg.map(function (v, i) { return i === today ? v : null; }) },
        ],
      };
    },

    "cardio-intensity": function (ctx) {
      var days = range(ctx.date, 14), get = ctx.day;
      return {
        title: "Cardio Intensity",
        x: days.map(mmdd), xFull: days,
        axes: [{ label: "Running Distance (mi)", min: 0 }, { label: "WHOOP Activity Strain", min: 0 }, { label: "Garmin Training Effect (0-5)", min: 0, max: 5.2 }],
        series: [
          { type: "line", label: "Running Distance (mi)", color: C.red, data: days.map(function (d) { return r1(get(d).run_mi || 0); }) },
          { type: "line", axis: 1, label: "WHOOP Activity Strain", color: C.blue, data: days.map(function (d) { return r1(get(d).workout_strain || 0); }) },
          { type: "line", axis: 2, label: "Garmin Aerobic TE", color: C.green, width: 1.8, data: days.map(function (d) { return get(d).aero_te || 0; }) },
          { type: "line", axis: 2, label: "Garmin Anaerobic TE", color: C.yellow, width: 1.8, data: days.map(function (d) { return get(d).anaero_te || 0; }) },
        ],
      };
    },

    "weekly-load": function (ctx) {
      // Last 8 Monday-start weeks: lifting lbs + running mi×1000 + BJJ strain×500.
      var endMonday = addDays(ctx.date, -weekday(ctx.date)), weeks = [];
      for (var i = 7; i >= 0; i--) weeks.push(addDays(endMonday, -7 * i));
      function total(field, mult) {
        return weeks.map(function (w) {
          var s = 0;
          for (var k = 0; k < 7; k++) { var d = addDays(w, k); if (d <= ctx.date) s += (ctx.day(d)[field] || 0) * mult; }
          return Math.round(s);
        });
      }
      return {
        title: "Weekly Load Progression",
        x: weeks.map(mmdd), xFull: weeks.map(function (w) { return "Week of " + w; }),
        axes: [{ label: "Total Load (lbs equivalent)" }],
        series: [
          { type: "bar", stack: true, label: "Lifting (lbs)", color: C.green, data: total("volume_lbs", 1) },
          { type: "bar", stack: true, label: "Running (mi x 1,000)", color: C.blue, data: total("run_mi", 1000) },
          { type: "bar", stack: true, label: "BJJ (strain x 500)", color: C.purple, data: total("bjj_strain", 500) },
        ],
      };
    },

    "fueling": function (ctx) {
      // 14 days, excluding the (partial) report day.
      var days = range(addDays(ctx.date, -1), 14), get = ctx.day;
      return {
        title: "Fueling vs Output",
        x: days.map(mmdd), xFull: days,
        axes: [{ label: "Consumed (kcal)", min: 0 }, { label: "Burned (kcal)", min: 0 }],
        series: [
          { type: "bar", axis: 1, label: "Calories Burned (kcal)", color: C.orange, alpha: 0.5, data: days.map(function (d) { return get(d).kcal_out || 0; }) },
          { type: "line", label: "Calories Consumed (kcal)", color: C.yellow, data: days.map(function (d) { return get(d).kcal_in || 0; }) },
        ],
      };
    },

    "sleep-debt": function (ctx) {
      // Composite recovery and its 7-day rolling mean over 14 days.
      var days = range(ctx.date, 14);
      var comp = days.map(function (d) { return composite(ctx.day(d)); });
      var roll = days.map(function (d) {
        var vals = range(d, 7).map(function (x) { return composite(ctx.day(x)); }).filter(function (v) { return v !== null; });
        return vals.length ? vals.reduce(function (a, b) { return a + b; }, 0) / vals.length : null;
      });
      return {
        title: "Recovery Debt Trendline",
        x: days.map(mmdd), xFull: days,
        axes: [{ label: "Recovery Score" }],
        series: [
          { type: "line", label: "Composite Recovery", color: C.grey, alpha: 0.55, width: 1.6, marker: false, data: comp.map(r1) },
          { type: "line", label: "7-day Rolling Avg", color: C.blue, width: 3.5, marker: false, data: roll.map(r1) },
        ],
      };
    },
  };

  // ---------------------------------------------- historical (all-time) --
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function dateLabels(days) {
    var long = days.length > 1 && (parseDate(days[days.length - 1]) - parseDate(days[0])) > 200 * 864e5;
    return days.map(function (d) { return long ? MONTHS[+d.slice(5, 7) - 1] + " '" + d.slice(2, 4) : mmdd(d); });
  }
  // Days up to the report date where fn(row) is truthy (historical charts plot every recorded day).
  function recorded(ctx, fn) {
    return ctx.allDays().filter(function (d) { return d <= ctx.date && fn(ctx.day(d)); });
  }
  function hline(days, v, label, color) {
    return { type: "line", label: label, color: color, width: 2, dash: "8 6", marker: false, data: days.map(function () { return v; }) };
  }

  CHARTS["hist-weight"] = function (ctx) {
    var days = recorded(ctx, function (r) { return r.weight_lbs; });
    var ys = days.map(function (d) { return ctx.day(d).weight_lbs; });
    var n = ys.length, sx = 0, sy = 0, sxx = 0, sxy = 0;
    ys.forEach(function (y, i) { sx += i; sy += y; sxx += i * i; sxy += i * y; });
    var slope = n > 1 ? (n * sxy - sx * sy) / (n * sxx - sx * sx) : 0, icpt = n ? (sy - slope * sx) / n : 0;
    var series = [{ type: "line", label: "Weight (lbs)", color: "#ff375f", width: 3, data: ys }];
    if (n > 2) series.push({ type: "line", label: "Trend", color: "#ffffff", alpha: 0.5, width: 2, dash: "8 6", marker: false, data: ys.map(function (_, i) { return Math.round((icpt + slope * i) * 10) / 10; }) });
    return { title: "Weight Progression", x: dateLabels(days), xFull: days, axes: [{ label: "Weight (lbs)", zero: false }], series: series };
  };

  CHARTS["hist-energy"] = function (ctx) {
    var days = recorded(ctx, function (r) { return r.kcal_in > 0; });
    return {
      title: "Historical Energy Intake", x: dateLabels(days), xFull: days,
      axes: [{ label: "Calories (kcal)", min: 0 }],
      series: [
        { type: "bar", label: "Energy (kcal)", color: C.green, alpha: 0.7, data: days.map(function (d) { return ctx.day(d).kcal_in; }) },
        hline(days, 3800, "Target (3800 kcal)", C.orange),
      ],
    };
  };

  CHARTS["hist-macros"] = function (ctx) {
    var days = recorded(ctx, function (r) { return r.kcal_in > 0; });
    function avg(f) { return days.reduce(function (a, d) { return a + (ctx.day(d)[f] || 0); }, 0) / (days.length || 1); }
    return {
      title: "Average Macro Distribution", pie: true,
      slices: [
        { label: "Fat", value: avg("fat_g"), color: C.yellow },
        { label: "Carbs", value: avg("carbs_g"), color: C.blue },
        { label: "Protein", value: avg("protein_g"), color: C.purple },
      ],
    };
  };

  CHARTS["hist-recovery"] = function (ctx) {
    var days = recorded(ctx, function (r) { return r.recovery != null; });
    return {
      title: "Recovery Trends (Whoop)", x: dateLabels(days), xFull: days,
      axes: [{ label: "Recovery Score", min: 0, max: 100 }],
      series: [
        { type: "line", label: "Recovery Score", color: C.blue, width: 1.5, fill: 0.3, marker: false, data: days.map(function (d) { return ctx.day(d).recovery; }) },
        hline(days, 60, "Target (60%)", C.yellow),
      ],
    };
  };

  CHARTS["hist-volume"] = function (ctx) {
    // 7-session rolling average (min 3); a deload is a >20% drop in that average.
    var days = recorded(ctx, function (r) { return r.volume_lbs > 0; });
    var vol = days.map(function (d) { return ctx.day(d).volume_lbs; });
    var roll = vol.map(function (_, i) {
      var w = vol.slice(Math.max(0, i - 6), i + 1);
      return w.length >= 3 ? Math.round(w.reduce(function (a, b) { return a + b; }, 0) / w.length) : null;
    });
    var deloads = roll.map(function (v, i) { return i && v && roll[i - 1] && (v - roll[i - 1]) / roll[i - 1] < -0.2 ? vol[i] : null; });
    var count = deloads.filter(function (v) { return v; }).length;
    return {
      title: "Training Volume with Deload Detection", x: dateLabels(days), xFull: days,
      axes: [{ label: "Volume (lbs)", min: 0 }],
      series: [
        { type: "bar", label: "Daily Volume", color: "#af52de", alpha: 0.7, data: vol },
        { type: "line", label: "7-Session Avg", color: C.yellow, width: 2, marker: false, data: roll },
        { type: "scatter", label: "Deloads (" + count + ")", color: "#ff375f", marker: "down", data: deloads },
      ],
    };
  };

  function render(container, id, ctx) {
    var build = CHARTS[id];
    if (!build) return empty(container, "Unknown chart: " + id);
    var spec = build(ctx);
    if (spec.pie) {
      return spec.slices.some(function (s) { return s.value > 0; }) ? pie(container, spec) : empty(container, "No nutrition data recorded yet.");
    }
    var any = spec.series.some(function (s) { return s.data.some(function (v) { return v; }); });
    if (!any) return empty(container, "No data recorded for this window.");
    plot(container, spec);
  }

  window.ReportCharts = { render: render, ids: Object.keys(CHARTS) };
})();
