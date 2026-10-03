#!/usr/bin/env python3
"""Generate Sleep → Next-Day Strength Prediction page."""

import json
import os
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

EIGHT_SLEEP_DIR = os.path.expanduser("~/clawd/data/eight_sleep/")
TONAL_FILE = os.path.expanduser("~/clawd/data/tonal/tonal_workouts_20260225_214518.json")
OUTPUT_DIR = os.path.expanduser("~/clawd/docs/sleep_strength_prediction/")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "index.html")

NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load 8Sleep
sleep_scores = {}
for fname in os.listdir(EIGHT_SLEEP_DIR):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(EIGHT_SLEEP_DIR, fname)
    try:
        with open(fpath) as f:
            d = json.load(f)
        date_str = d.get("date")
        score = d.get("sleep_score") or d.get("score")
        if date_str and score is not None:
            sleep_scores[date_str] = int(score)
    except Exception:
        pass

print(f"Loaded {len(sleep_scores)} 8Sleep records")

# Load Tonal
with open(TONAL_FILE) as f:
    tonal_data = json.load(f)

workouts = tonal_data.get("workouts", [])
tonal_volumes = {}
for w in workouts:
    begin = w.get("beginTime", "")
    volume = w.get("totalVolume", 0)
    if not begin or not volume:
        continue
    try:
        if begin.endswith("Z"):
            begin = begin[:-1] + "+00:00"
        dt_utc = datetime.fromisoformat(begin).replace(tzinfo=UTC_TZ)
        dt_ny = dt_utc.astimezone(NY_TZ)
        date_str = dt_ny.strftime("%Y-%m-%d")
        tonal_volumes[date_str] = tonal_volumes.get(date_str, 0) + int(volume)
    except Exception:
        pass

print(f"Loaded {len(tonal_volumes)} Tonal workout days")

# Pair: prev-night sleep + next-day volume
paired = []
for tonal_date, volume in tonal_volumes.items():
    try:
        tonal_dt = datetime.strptime(tonal_date, "%Y-%m-%d")
        prev_night = (tonal_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        if prev_night in sleep_scores:
            paired.append({
                "date": tonal_date,
                "sleep_score": sleep_scores[prev_night],
                "volume": volume,
                "prev_night": prev_night,
            })
    except Exception:
        pass

paired.sort(key=lambda x: x["date"])
print(f"Paired data points: {len(paired)}")

if len(paired) < 3:
    print("ERROR: Not enough paired data points")
    exit(1)

n = len(paired)
xs = [p["sleep_score"] for p in paired]
ys = [p["volume"] for p in paired]

mean_x = sum(xs) / n
mean_y = sum(ys) / n

cov = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
r = cov / (std_x * std_y) if (std_x * std_y) != 0 else 0

if abs(r) < 1.0 and n > 2:
    t_stat = r * math.sqrt(n - 2) / math.sqrt(1 - r ** 2)
    abs_t = abs(t_stat)
    if abs_t > 3.0:
        p_label = "p < 0.01 (highly significant)"
    elif abs_t > 2.0:
        p_label = "p < 0.05 (significant)"
    elif abs_t > 1.5:
        p_label = "p < 0.15 (marginal)"
    else:
        p_label = "p > 0.15 (not significant)"
else:
    p_label = "insufficient data"

slope = cov / (std_x ** 2) if std_x != 0 else 0
intercept = mean_y - slope * mean_x

bins = {
    "Poor":      {"range": "< 60",  "color": "#e74c3c", "scores": [], "volumes": []},
    "Fair":      {"range": "60–75", "color": "#f39c12", "scores": [], "volumes": []},
    "Good":      {"range": "75–90", "color": "#2ecc71", "scores": [], "volumes": []},
    "Excellent": {"range": "> 90",  "color": "#3498db", "scores": [], "volumes": []},
}
for p in paired:
    s, v = p["sleep_score"], p["volume"]
    if s < 60:
        bins["Poor"]["scores"].append(s); bins["Poor"]["volumes"].append(v)
    elif s < 75:
        bins["Fair"]["scores"].append(s); bins["Fair"]["volumes"].append(v)
    elif s <= 90:
        bins["Good"]["scores"].append(s); bins["Good"]["volumes"].append(v)
    else:
        bins["Excellent"]["scores"].append(s); bins["Excellent"]["volumes"].append(v)

for b in bins.values():
    b["avg_volume"] = int(sum(b["volumes"]) / len(b["volumes"])) if b["volumes"] else 0
    b["count"] = len(b["volumes"])

filled_bins = [(k, v) for k, v in bins.items() if v["count"] > 0]
if filled_bins:
    best_bin = max(filled_bins, key=lambda x: x[1]["avg_volume"])
    worst_bin = min(filled_bins, key=lambda x: x[1]["avg_volume"])
    if worst_bin[1]["avg_volume"] > 0:
        pct_diff = ((best_bin[1]["avg_volume"] - worst_bin[1]["avg_volume"]) / worst_bin[1]["avg_volume"]) * 100
        insight = f'On <strong>{best_bin[0]}</strong> sleep nights, you lift <strong>~{pct_diff:.0f}% more volume</strong> than on <strong>{worst_bin[0]}</strong> sleep nights ({best_bin[1]["avg_volume"]:,} vs {worst_bin[1]["avg_volume"]:,} lbs avg).'
    else:
        insight = f"Higher sleep scores tend to predict higher next-day training volume (r = {r:.2f})."
else:
    insight = f"Correlation between sleep score and next-day Tonal volume: r = {r:.2f}."

# SVG Scatter
SVG_W, SVG_H = 820, 500
PAD_L, PAD_R, PAD_T, PAD_B = 72, 30, 30, 60
min_x_plot, max_x_plot = 30, 100
min_y_plot = max(0, min(ys) - 2000)
max_y_plot = max(ys) + 2000

def sx(val):
    return PAD_L + (val - min_x_plot) / (max_x_plot - min_x_plot) * (SVG_W - PAD_L - PAD_R)

def sy(val):
    return SVG_H - PAD_B - (val - min_y_plot) / (max_y_plot - min_y_plot) * (SVG_H - PAD_T - PAD_B)

x_ticks = list(range(30, 101, 10))
x_grid = "".join(f'<line x1="{sx(xt):.1f}" y1="{PAD_T}" x2="{sx(xt):.1f}" y2="{SVG_H-PAD_B}" stroke="#2a3040" stroke-width="1"/>' for xt in x_ticks)
x_labels = "".join(f'<text x="{sx(xt):.1f}" y="{SVG_H-PAD_B+18}" fill="#8b949e" font-size="12" text-anchor="middle">{xt}</text>' for xt in x_ticks)

y_step = 5000
y_ticks = list(range(int(min_y_plot // y_step) * y_step, int(max_y_plot) + y_step, y_step))
y_grid = "".join(f'<line x1="{PAD_L}" y1="{sy(yt):.1f}" x2="{SVG_W-PAD_R}" y2="{sy(yt):.1f}" stroke="#2a3040" stroke-width="1"/>' for yt in y_ticks if min_y_plot <= yt <= max_y_plot)
y_labels = "".join(f'<text x="{PAD_L-8}" y="{sy(yt)+4:.1f}" fill="#8b949e" font-size="11" text-anchor="end">{yt//1000}k</text>' for yt in y_ticks if min_y_plot <= yt <= max_y_plot)

trend_y1 = slope * min_x_plot + intercept
trend_y2 = slope * max_x_plot + intercept
trend_line = f'<line x1="{sx(min_x_plot):.1f}" y1="{sy(trend_y1):.1f}" x2="{sx(max_x_plot):.1f}" y2="{sy(trend_y2):.1f}" stroke="#2ea043" stroke-width="2" stroke-dasharray="6,3" opacity="0.85"/>'

max_v, min_v = max(ys), min(ys)
def dot_color(v):
    t = (v - min_v) / (max_v - min_v) if max_v != min_v else 0.5
    ri = int(243 * t + 46 * (1 - t))
    gi = int(156 * t + 160 * (1 - t))
    bi = int(18 * t + 67 * (1 - t))
    return f"rgb({ri},{gi},{bi})"

dots = "".join(
    f'<circle cx="{sx(p["sleep_score"]):.1f}" cy="{sy(p["volume"]):.1f}" r="5" fill="{dot_color(p["volume"])}" opacity="0.8"><title>{p["date"]}: Sleep {p["sleep_score"]}, Vol {p["volume"]:,} lbs</title></circle>'
    for p in paired
)

mean_cx, mean_cy = sx(mean_x), sy(mean_y)
crosshairs = f'<line x1="{mean_cx:.1f}" y1="{PAD_T}" x2="{mean_cx:.1f}" y2="{SVG_H-PAD_B}" stroke="#f39c12" stroke-width="1" stroke-dasharray="4,4" opacity="0.35"/><line x1="{PAD_L}" y1="{mean_cy:.1f}" x2="{SVG_W-PAD_R}" y2="{mean_cy:.1f}" stroke="#f39c12" stroke-width="1" stroke-dasharray="4,4" opacity="0.35"/>'

scatter_svg = f'''<svg width="{SVG_W}" height="{SVG_H}" style="background:#0d1117;border-radius:8px;display:block;max-width:100%">
  {x_grid}{y_grid}{crosshairs}{trend_line}{dots}
  <line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{SVG_H-PAD_B}" stroke="#3d444d" stroke-width="1.5"/>
  <line x1="{PAD_L}" y1="{SVG_H-PAD_B}" x2="{SVG_W-PAD_R}" y2="{SVG_H-PAD_B}" stroke="#3d444d" stroke-width="1.5"/>
  {x_labels}{y_labels}
  <text x="{(PAD_L+SVG_W-PAD_R)/2:.1f}" y="{SVG_H-6}" fill="#8b949e" font-size="13" text-anchor="middle">Previous Night Sleep Score</text>
  <text x="18" y="{(PAD_T+SVG_H-PAD_B)/2:.1f}" fill="#8b949e" font-size="13" text-anchor="middle" transform="rotate(-90,18,{(PAD_T+SVG_H-PAD_B)/2:.1f})">Tonal Volume (lbs)</text>
  <line x1="690" y1="45" x2="720" y2="45" stroke="#2ea043" stroke-width="2" stroke-dasharray="6,3"/>
  <text x="725" y="49" fill="#8b949e" font-size="11">Trend</text>
  <line x1="690" y1="62" x2="720" y2="62" stroke="#f39c12" stroke-width="1" stroke-dasharray="4,4" opacity="0.6"/>
  <text x="725" y="66" fill="#8b949e" font-size="11">Mean</text>
</svg>'''

max_avg = max(b["avg_volume"] for b in bins.values()) or 1
bin_cards = ""
for name, b in bins.items():
    bar_w = int((b["avg_volume"] / max_avg) * 100)
    count_label = f"n={b['count']}" if b["count"] > 0 else "no data"
    bin_cards += f'''<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;flex:1;min-width:140px;border-top:3px solid {b["color"]}">
      <div style="color:{b["color"]};font-size:0.85em;font-weight:600;margin-bottom:4px;">{name}</div>
      <div style="color:#8b949e;font-size:0.75em;margin-bottom:12px;">Sleep {b["range"]} &middot; {count_label}</div>
      <div style="font-size:1.5em;font-weight:700;color:#e6edf3;margin-bottom:8px;">{b["avg_volume"]:,}<span style="font-size:0.5em;color:#8b949e;margin-left:4px">lbs</span></div>
      <div style="background:#0d1117;border-radius:4px;height:6px;overflow:hidden;"><div style="background:{b["color"]};height:100%;width:{bar_w}%;border-radius:4px;"></div></div>
    </div>'''

NAV_LINKS = [
    ("🏠 Hub", "../hub_index.html"),
    ("💪 Strength", "../strength/index.html"),
    ("😴 Sleep", "../sleep_dashboard.html"),
    ("🔄 Recovery", "../recovery/index.html"),
    ("📈 Velocity", "../velocity/index.html"),
    ("🎯 Sweet Spot", "../sweet_spot/index.html"),
]
nav_items = "".join(f'<a href="{href}" style="color:#8b949e;text-decoration:none;padding:6px 12px;border-radius:6px;font-size:0.85em">{label}</a>' for label, href in NAV_LINKS)

r_strength = "positive" if r > 0 else "negative"
r_label = "Strong" if abs(r) > 0.5 else ("Moderate" if abs(r) > 0.3 else "Weak")
r_color = "#2ecc71" if r > 0.3 else ("#e74c3c" if r < -0.3 else "#f39c12")

p_main = p_label.split("(")[0].strip()
p_sub = p_label.split("(")[1].rstrip(")") if "(" in p_label else ""

now_str = datetime.now(NY_TZ).strftime("%Y-%m-%d %H:%M %Z")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sleep \u2192 Next-Day Strength</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}}
nav{{background:#161b22;border-bottom:1px solid #30363d;padding:10px 24px;display:flex;align-items:center;gap:4px;flex-wrap:wrap}}
nav .brand{{color:#f39c12;font-weight:700;font-size:0.9em;margin-right:12px}}
nav a:hover{{color:#f39c12!important}}
.container{{max-width:1000px;margin:0 auto;padding:32px 20px}}
h1{{font-size:2em;font-weight:700;margin-bottom:6px}}
.subtitle{{color:#8b949e;font-size:1em;margin-bottom:32px}}
.stats-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:32px}}
.stat-card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px 24px;flex:1;min-width:160px}}
.stat-label{{color:#8b949e;font-size:0.8em;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}}
.stat-value{{font-size:1.8em;font-weight:700;color:#f39c12}}
.stat-sub{{color:#8b949e;font-size:0.78em;margin-top:4px}}
.section{{margin-bottom:36px}}
.section-title{{font-size:1.1em;font-weight:600;color:#8b949e;margin-bottom:16px;text-transform:uppercase;letter-spacing:.05em}}
.chart-wrap{{overflow-x:auto}}
.bins{{display:flex;gap:16px;flex-wrap:wrap}}
.insight-box{{background:#161b22;border:1px solid #30363d;border-left:4px solid #f39c12;border-radius:8px;padding:18px 22px;line-height:1.6}}
.generated{{color:#484f58;font-size:.75em;margin-top:40px;text-align:center}}
</style>
</head>
<body>
<nav>
  <span class="brand">\U0001f338 ARIA Fitness</span>
  {nav_items}
</nav>
<div class="container">
  <h1>\U0001f634 \u2192 \U0001f4aa Sleep \u2192 Next-Day Strength</h1>
  <p class="subtitle">Does last night\u2019s sleep predict today\u2019s workout volume?</p>

  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-label">Correlation (r)</div>
      <div class="stat-value" style="color:{r_color}">{r:+.3f}</div>
      <div class="stat-sub">{r_label} {r_strength} correlation</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Sample Size</div>
      <div class="stat-value">{n}</div>
      <div class="stat-sub">paired workout days</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Significance</div>
      <div class="stat-value" style="font-size:1.1em;padding-top:6px">{p_main}</div>
      <div class="stat-sub">{p_sub}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg Sleep Score</div>
      <div class="stat-value">{mean_x:.0f}</div>
      <div class="stat-sub">avg next-day vol {mean_y:,.0f} lbs</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Scatter Plot \u2014 Sleep Score vs Next-Day Volume</div>
    <div class="chart-wrap">
      {scatter_svg}
    </div>
    <p style="color:#484f58;font-size:.78em;margin-top:8px">Each dot = one workout day. Hover for details. Orange/warm = higher volume. Dashed green = trend line. Dashed orange = mean.</p>
  </div>

  <div class="section">
    <div class="section-title">Average Volume by Sleep Quality</div>
    <div class="bins">{bin_cards}</div>
  </div>

  <div class="section">
    <div class="section-title">Key Insight</div>
    <div class="insight-box">{insight}</div>
  </div>

  <p class="generated">Generated {now_str} \u00b7 {n} paired data points \u00b7 8Sleep + Tonal</p>
</div>
</body>
</html>"""

with open(OUTPUT_FILE, "w") as f:
    f.write(html)

size = os.path.getsize(OUTPUT_FILE)
print(f"Output: {OUTPUT_FILE} ({size:,} bytes)")
if size < 3000:
    print("ERROR: Output too small")
    exit(1)
print("SUCCESS")
