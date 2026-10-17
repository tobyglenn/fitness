#!/usr/bin/env python3
"""Generate correlation matrix dashboard."""

import json
import csv
import math
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

BASE = os.path.expanduser("~/clawd/data")
OUT  = os.path.expanduser("~/clawd/docs/correlation/index.html")
ET = ZoneInfo("America/New_York")

def load_tonal():
    path = os.path.join(BASE, "tonal/tonal_workouts_20260225_214518.json")
    d = json.load(open(path))
    by_day = defaultdict(lambda: {"volume": 0, "sessions": 0})
    for w in d.get("workouts", []):
        if not w.get("completed"):
            continue
        bt = w.get("beginTime","")
        if not bt:
            continue
        try:
            dt = datetime.fromisoformat(bt.replace("Z","+00:00")).astimezone(ET)
            day = dt.strftime("%Y-%m-%d")
        except Exception:
            continue
        vol = w.get("totalVolume", 0) or 0
        by_day[day]["volume"] += vol
        by_day[day]["sessions"] += 1
    return dict(by_day)

def load_garmin():
    path = os.path.join(BASE, "garmin_all_activities.json")
    d = json.load(open(path))
    acts = d if isinstance(d, list) else d.get("activities", [])
    by_day = defaultdict(lambda: {"miles": 0.0, "runs": 0, "avg_hr": []})
    for a in acts:
        day = a.get("date") or (a.get("startTimeLocal","")[:10])
        if not day:
            continue
        dist = a.get("distance_miles", a.get("distance", 0)) or 0
        by_day[day]["miles"] += dist
        by_day[day]["runs"] += 1
        hr = a.get("averageHR")
        if hr:
            by_day[day]["avg_hr"].append(hr)
    result = {}
    for day, v in by_day.items():
        hrs = v["avg_hr"]
        result[day] = {"miles": v["miles"], "runs": v["runs"],
                       "avg_hr": sum(hrs)/len(hrs) if hrs else None}
    return result

def load_whoop():
    path = os.path.join(BASE, "whoop_v2_latest.json")
    d = json.load(open(path))
    records = d.get("recovery", {}).get("records", [])
    by_day = {}
    for r in records:
        if r.get("score_state") != "SCORED":
            continue
        sc = r.get("score", {})
        created = r.get("created_at","")
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z","+00:00")).astimezone(ET)
            day = dt.strftime("%Y-%m-%d")
        except Exception:
            continue
        by_day[day] = {
            "recovery": sc.get("recovery_score"),
            "hrv": sc.get("hrv_rmssd_milli"),
            "rhr": sc.get("resting_heart_rate"),
        }
    return by_day

def load_eight_sleep():
    path = os.path.join(BASE, "eight_sleep_historical.csv")
    with open(path) as f:
        records = json.load(f)
    by_day = {}
    for r in records:
        day = r.get("date","")
        score = r.get("sleep_score") or r.get("last_sleep_score")
        if day and score is not None:
            by_day[day] = {"sleep_score": score}
    return by_day

def load_cronometer():
    path = os.path.join(BASE, "cronometer_historical.csv")
    by_day = {}
    for row in csv.DictReader(open(path)):
        day = row.get("Date","")
        if not day:
            continue
        try:
            cals = float(row.get("Energy (kcal)", 0) or 0)
            protein = float(row.get("Protein (g)", 0) or 0)
        except ValueError:
            continue
        by_day[day] = {"calories": cals, "protein": protein}
    return by_day

tonal   = load_tonal()
garmin  = load_garmin()
whoop   = load_whoop()
sleep8  = load_eight_sleep()
crono   = load_cronometer()

all_days = sorted(set(list(tonal) + list(garmin) + list(whoop) + list(sleep8) + list(crono)))

METRICS = {
    "Tonal Volume":   [],
    "Garmin Miles":   [],
    "WHOOP Recovery": [],
    "HRV":            [],
    "RHR":            [],
    "Sleep Score":    [],
    "Calories":       [],
    "Protein":        [],
}

for day in all_days:
    t = tonal.get(day, {})
    g = garmin.get(day, {})
    w = whoop.get(day, {})
    s = sleep8.get(day, {})
    c = crono.get(day, {})
    METRICS["Tonal Volume"].append(t.get("volume"))
    METRICS["Garmin Miles"].append(g.get("miles"))
    METRICS["WHOOP Recovery"].append(w.get("recovery"))
    METRICS["HRV"].append(w.get("hrv"))
    METRICS["RHR"].append(w.get("rhr"))
    METRICS["Sleep Score"].append(s.get("sleep_score"))
    METRICS["Calories"].append(c.get("calories"))
    METRICS["Protein"].append(c.get("protein"))

def pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None, n
    xs2, ys2 = zip(*pairs)
    mx = sum(xs2)/n; my = sum(ys2)/n
    num = sum((x-mx)*(y-my) for x,y in zip(xs2,ys2))
    dx  = math.sqrt(sum((x-mx)**2 for x in xs2))
    dy  = math.sqrt(sum((y-my)**2 for y in ys2))
    if dx == 0 or dy == 0:
        return None, n
    return round(num/(dx*dy), 4), n

metric_names = list(METRICS.keys())
n_metrics = len(metric_names)

corr_matrix = []
for i, mi in enumerate(metric_names):
    row = []
    for j, mj in enumerate(metric_names):
        if i == j:
            row.append((1.0, len([x for x in METRICS[mi] if x is not None])))
        else:
            c, cnt = pearson(METRICS[mi], METRICS[mj])
            row.append((c, cnt))
    corr_matrix.append(row)

corr_pairs = []
for i in range(n_metrics):
    for j in range(i+1, n_metrics):
        c, cnt = corr_matrix[i][j]
        if c is not None:
            corr_pairs.append((c, cnt, metric_names[i], metric_names[j]))

corr_pairs.sort(key=lambda x: -abs(x[0]))
top_positive = [p for p in corr_pairs if p[0] > 0][:5]
top_negative = [p for p in corr_pairs if p[0] < 0][:5]

def coverage(vals, days):
    present = [(d, v) for d, v in zip(days, vals) if v is not None]
    if not present:
        return {"count": 0, "start": "N/A", "end": "N/A"}
    return {"count": len(present), "start": present[0][0], "end": present[-1][0]}

cov_stats = {m: coverage(METRICS[m], all_days) for m in metric_names}

def lerp_color(t):
    if t is None:
        return "#333333"
    t = max(-1, min(1, t))
    if t < 0:
        r = int(248 + (13-248)*(-t))
        g = int(81  + (17-81)*(-t))
        b = int(73  + (23-73)*(-t))
    else:
        r = int(13  + (46 -13)*t)
        g = int(17  + (160-17)*t)
        b = int(23  + (67 -23)*t)
    return f"#{r:02x}{g:02x}{b:02x}"

def text_color_for(t):
    if t is None or abs(t) < 0.3:
        return "#cccccc"
    return "#ffffff"

CELL = 78
LABEL_W = 110
LABEL_H = 110
SVG_W = LABEL_W + n_metrics * CELL + 20
SVG_H = LABEL_H + n_metrics * CELL + 60

def make_matrix_svg():
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" style="font-family:monospace">']
    for j, name in enumerate(metric_names):
        x = LABEL_W + j * CELL + CELL/2
        y = LABEL_H - 8
        short = name.replace("WHOOP ","W.").replace("Tonal ","T.").replace("Garmin ","G.")
        parts.append(f'<text x="{x}" y="{y}" font-size="10" fill="#aaa" text-anchor="end" transform="rotate(-45,{x},{y})">{short}</text>')
    for i, name in enumerate(metric_names):
        y = LABEL_H + i * CELL + CELL/2 + 4
        short = name.replace("WHOOP ","W.").replace("Tonal ","T.").replace("Garmin ","G.")
        parts.append(f'<text x="{LABEL_W-6}" y="{y}" font-size="10" fill="#aaa" text-anchor="end">{short}</text>')
    for i in range(n_metrics):
        for j in range(n_metrics):
            c, cnt = corr_matrix[i][j]
            x = LABEL_W + j * CELL
            y = LABEL_H + i * CELL
            bg = lerp_color(c)
            tc = text_color_for(c)
            val_str = f"{c:.2f}" if c is not None else "N/A"
            title = f"{metric_names[i]} vs {metric_names[j]}: r={val_str} (n={cnt})"
            parts.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" fill="{bg}" stroke="#0d1117" stroke-width="2" rx="3"><title>{title}</title></rect>')
            parts.append(f'<text x="{x+CELL/2}" y="{y+CELL/2+5}" font-size="12" fill="{tc}" text-anchor="middle" font-weight="bold">{val_str}</text>')
            if cnt and i != j:
                parts.append(f'<text x="{x+CELL/2}" y="{y+CELL-8}" font-size="8" fill="{tc}80" text-anchor="middle">n={cnt}</text>')
    lg_y = LABEL_H + n_metrics * CELL + 15
    lg_x = LABEL_W
    lg_w = n_metrics * CELL
    parts.append(f'<defs><linearGradient id="lg" x1="0" x2="1" y1="0" y2="0"><stop offset="0%" stop-color="#f85149"/><stop offset="50%" stop-color="#0d1117"/><stop offset="100%" stop-color="#2ea043"/></linearGradient></defs>')
    parts.append(f'<rect x="{lg_x}" y="{lg_y}" width="{lg_w}" height="14" fill="url(#lg)" rx="3"/>')
    parts.append(f'<text x="{lg_x}" y="{lg_y+26}" font-size="10" fill="#aaa">-1.0</text>')
    parts.append(f'<text x="{lg_x+lg_w/2}" y="{lg_y+26}" font-size="10" fill="#aaa" text-anchor="middle">0</text>')
    parts.append(f'<text x="{lg_x+lg_w}" y="{lg_y+26}" font-size="10" fill="#aaa" text-anchor="end">+1.0</text>')
    parts.append('</svg>')
    return '\n'.join(parts)

def make_scatter(x_metric, y_metric, width=380, height=260):
    xi = metric_names.index(x_metric)
    yi = metric_names.index(y_metric)
    xs_v = METRICS[x_metric]
    ys_v = METRICS[y_metric]
    pairs = [(x, y, all_days[i]) for i,(x,y) in enumerate(zip(xs_v,ys_v)) if x is not None and y is not None]
    if len(pairs) < 3:
        return f'<svg width="{width}" height="{height}"><rect width="{width}" height="{height}" fill="#161b22" rx="8"/><text x="10" y="20" fill="#aaa" font-size="12">Insufficient data ({len(pairs)} points)</text></svg>'
    PAD = 45
    pw = width - PAD - 10
    ph = height - PAD - 20
    xvals = [p[0] for p in pairs]
    yvals = [p[1] for p in pairs]
    xmin, xmax = min(xvals), max(xvals)
    ymin, ymax = min(yvals), max(yvals)
    def sx(v):
        if xmax == xmin: return PAD + pw/2
        return PAD + (v - xmin) / (xmax - xmin) * pw
    def sy(v):
        if ymax == ymin: return PAD
        return PAD + ph - (v - ymin) / (ymax - ymin) * ph
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="font-family:monospace">']
    parts.append(f'<rect width="{width}" height="{height}" fill="#161b22" rx="8"/>')
    parts.append(f'<line x1="{PAD}" y1="{PAD}" x2="{PAD}" y2="{PAD+ph}" stroke="#444" stroke-width="1"/>')
    parts.append(f'<line x1="{PAD}" y1="{PAD+ph}" x2="{PAD+pw}" y2="{PAD+ph}" stroke="#444" stroke-width="1"/>')
    short_x = x_metric.replace("WHOOP ","").replace("Tonal ","").replace("Garmin ","")
    short_y = y_metric.replace("WHOOP ","").replace("Tonal ","").replace("Garmin ","")
    parts.append(f'<text x="{PAD+pw/2}" y="{height-4}" font-size="10" fill="#888" text-anchor="middle">{short_x}</text>')
    parts.append(f'<text x="10" y="{PAD+ph/2}" font-size="10" fill="#888" text-anchor="middle" transform="rotate(-90,10,{PAD+ph/2})">{short_y}</text>')
    for xv, yv, day in pairs:
        cx = sx(xv); cy = sy(yv)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#f39c12" fill-opacity="0.7" stroke="#f39c12" stroke-width="1"><title>{day}: {x_metric}={xv:.1f}, {y_metric}={yv:.1f}</title></circle>')
    n = len(pairs)
    mx2 = sum(xvals)/n; my2 = sum(yvals)/n
    num2 = sum((x-mx2)*(y-my2) for x,y in zip(xvals,yvals))
    den2 = sum((x-mx2)**2 for x in xvals)
    if den2 > 0:
        slope = num2/den2
        intercept = my2 - slope*mx2
        x1v, x2v = xmin, xmax
        y1v = slope*x1v + intercept
        y2v = slope*x2v + intercept
        parts.append(f'<line x1="{sx(x1v):.1f}" y1="{sy(y1v):.1f}" x2="{sx(x2v):.1f}" y2="{sy(y2v):.1f}" stroke="#0a84ff" stroke-width="2" stroke-dasharray="4,2"/>')
    c_val, _ = corr_matrix[xi][yi]
    if c_val is not None:
        col = "#2ea043" if c_val > 0 else "#f85149"
        parts.append(f'<text x="{PAD+pw-5}" y="{PAD+14}" font-size="11" fill="{col}" text-anchor="end" font-weight="bold">r={c_val:.2f}</text>')
    parts.append('</svg>')
    return '\n'.join(parts)

def insight(c, n1, n2):
    mag = abs(c)
    direction = "higher" if c > 0 else "lower"
    if mag > 0.7: strength = "strongly"
    elif mag > 0.4: strength = "moderately"
    else: strength = "slightly"
    pct = int(mag * 100)
    return f"When {n1} is high, {n2} tends to be {strength} {direction} ({pct}% correlation strength)."

scatter_pairs = [
    ("Sleep Score", "WHOOP Recovery"),
    ("WHOOP Recovery", "Tonal Volume"),
    ("Tonal Volume", "RHR"),
]

scatters = [(p[0], p[1], make_scatter(p[0], p[1])) for p in scatter_pairs]

NAV_LINKS = [
    ("🏠 Home", "../hub_index.html"),
    ("💪 Strength", "../strength/index.html"),
    ("🏃 Cardio", "../cardio/index.html"),
    ("😴 Sleep", "../sleep_dashboard.html"),
    ("❤️ Recovery", "../recovery/index.html"),
    ("🥗 Nutrition", "../nutrition/index.html"),
    ("📊 Correlation", "index.html"),
]
nav_html = "".join(f'<a href="{url}">{label}</a>' for label, url in NAV_LINKS)

matrix_svg = make_matrix_svg()
ts = datetime.now(ET).strftime("%B %d, %Y at %I:%M %p ET")

def corr_color(c):
    if c is None: return "#888"
    if c > 0: return "#2ea043"
    return "#f85149"

def bar_width(c):
    return int(abs(c) * 100)

html_parts = []
html_parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cross-Source Correlation Matrix</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh}}
nav{{background:#161b22;border-bottom:1px solid #30363d;padding:12px 24px;display:flex;gap:20px;flex-wrap:wrap;align-items:center}}
nav a{{color:#8b949e;text-decoration:none;font-size:13px;padding:4px 8px;border-radius:6px;transition:all .2s}}
nav a:hover{{background:#21262d;color:#f39c12}}
.container{{max-width:1200px;margin:0 auto;padding:24px}}
h1{{font-size:28px;color:#f0f6fc;margin-bottom:6px}}
.subtitle{{color:#8b949e;font-size:14px;margin-bottom:32px}}
.section{{margin-bottom:40px}}
h2{{font-size:20px;color:#f39c12;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #30363d}}
.matrix-wrap{{overflow-x:auto;background:#161b22;border-radius:12px;padding:20px;border:1px solid #30363d}}
.corr-list{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:700px){{.corr-list{{grid-template-columns:1fr}}}}
.corr-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}}
.corr-pair{{font-size:14px;color:#e6edf3;font-weight:600;margin-bottom:6px}}
.corr-score{{font-size:22px;font-weight:700;margin-bottom:6px}}
.corr-bar-bg{{background:#21262d;border-radius:4px;height:6px;margin-bottom:10px}}
.corr-bar{{height:6px;border-radius:4px}}
.corr-insight{{font-size:12px;color:#8b949e;line-height:1.5}}
.corr-n{{font-size:11px;color:#6e7681;margin-top:4px}}
.scatter-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:20px}}
.scatter-card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}}
.scatter-title{{font-size:13px;color:#8b949e;margin-bottom:10px;font-weight:600}}
.cov-table{{width:100%;border-collapse:collapse}}
.cov-table th,.cov-table td{{padding:10px 14px;text-align:left;border-bottom:1px solid #21262d;font-size:13px}}
.cov-table th{{color:#8b949e;font-weight:600;background:#161b22}}
.cov-table td{{color:#e6edf3}}
.cov-table tr:last-child td{{border-bottom:none}}
.badge{{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}}
.badge-good{{background:#2ea04320;color:#2ea043}}
.badge-warn{{background:#f39c1220;color:#f39c12}}
.badge-low{{background:#f8514920;color:#f85149}}
.ts{{font-size:11px;color:#484f58;margin-top:40px;text-align:right}}
</style>
</head>
<body>
<nav>{nav_html}</nav>
<div class="container">
  <h1>&#128202; Cross-Source Correlation Matrix</h1>
  <p class="subtitle">Generated {ts} &middot; {len(all_days)} days of data across {len(metric_names)} metrics</p>

  <div class="section">
    <h2>Correlation Heatmap</h2>
    <p style="font-size:13px;color:#8b949e;margin-bottom:12px">Green = positive correlation &middot; Red = negative &middot; Hover cells for exact values.</p>
    <div class="matrix-wrap">
      {matrix_svg}
    </div>
  </div>

  <div class="section">
    <h2>Top Positive Correlations</h2>
    <div class="corr-list">
""")

for c, cnt, n1, n2 in top_positive:
    html_parts.append(f"""      <div class="corr-card">
        <div class="corr-pair">{n1} &#8596; {n2}</div>
        <div class="corr-score" style="color:{corr_color(c)}">{c:+.2f}</div>
        <div class="corr-bar-bg"><div class="corr-bar" style="width:{bar_width(c)}%;background:#2ea043"></div></div>
        <div class="corr-insight">{insight(c, n1, n2)}</div>
        <div class="corr-n">Based on {cnt} overlapping days</div>
      </div>""")

html_parts.append("""    </div>
  </div>

  <div class="section">
    <h2>Top Negative Correlations</h2>
    <div class="corr-list">
""")

for c, cnt, n1, n2 in top_negative:
    html_parts.append(f"""      <div class="corr-card">
        <div class="corr-pair">{n1} &#8596; {n2}</div>
        <div class="corr-score" style="color:{corr_color(c)}">{c:+.2f}</div>
        <div class="corr-bar-bg"><div class="corr-bar" style="width:{bar_width(c)}%;background:#f85149"></div></div>
        <div class="corr-insight">{insight(c, n1, n2)}</div>
        <div class="corr-n">Based on {cnt} overlapping days</div>
      </div>""")

html_parts.append("""    </div>
  </div>

  <div class="section">
    <h2>Scatter Plot Highlights</h2>
    <div class="scatter-grid">
""")

for x_m, y_m, svg in scatters:
    xi2 = metric_names.index(x_m)
    yi2 = metric_names.index(y_m)
    c_val, _ = corr_matrix[xi2][yi2]
    c_str = f"r={c_val:.2f}" if c_val is not None else "r=N/A"
    html_parts.append(f"""      <div class="scatter-card">
        <div class="scatter-title">{x_m} vs {y_m} <span style="color:{corr_color(c_val)}">{c_str}</span></div>
        {svg}
      </div>""")

html_parts.append("""    </div>
  </div>

  <div class="section">
    <h2>Data Coverage</h2>
    <table class="cov-table">
      <thead><tr><th>Metric</th><th>Source</th><th>Data Points</th><th>Date Range</th><th>Quality</th></tr></thead>
      <tbody>
""")

source_map = {
    "Tonal Volume": "Tonal", "Garmin Miles": "Garmin",
    "WHOOP Recovery": "WHOOP", "HRV": "WHOOP", "RHR": "WHOOP",
    "Sleep Score": "8Sleep", "Calories": "Cronometer", "Protein": "Cronometer",
}

for m in metric_names:
    cov = cov_stats[m]
    cnt2 = cov["count"]
    if cnt2 > 50: badge_cls, badge_lbl = "badge-good", "Good"
    elif cnt2 > 15: badge_cls, badge_lbl = "badge-warn", "Moderate"
    else: badge_cls, badge_lbl = "badge-low", "Limited"
    html_parts.append(f"""        <tr>
          <td><strong>{m}</strong></td>
          <td style="color:#8b949e">{source_map.get(m,'?')}</td>
          <td>{cnt2}</td>
          <td style="color:#8b949e">{cov['start']} &rarr; {cov['end']}</td>
          <td><span class="badge {badge_cls}">{badge_lbl}</span></td>
        </tr>""")

html_parts.append(f"""      </tbody>
    </table>
  </div>

  <div class="ts">Generated by generate_correlation_matrix.py &middot; {ts}</div>
</div>
</body>
</html>""")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    f.write("\n".join(html_parts))

size = os.path.getsize(OUT)
print(f"SUCCESS: {OUT}")
print(f"File size: {size:,} bytes ({size//1024} KB)")
