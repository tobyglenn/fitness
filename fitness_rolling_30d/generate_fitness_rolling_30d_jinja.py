#!/usr/bin/env python3
"""Generator for 30-Day Rolling Fitness Score page."""

import json
import os
import glob
import csv
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from collections import defaultdict
import math

DOCS_DIR = os.path.expanduser("~/clawd/docs")
DATA_DIR = os.path.expanduser("~/clawd/data")
OUTPUT_DIR = os.path.join(DOCS_DIR, "fitness_rolling_30d")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "index.html")
TZ = ZoneInfo("America/New_York")

os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = date.today()
START_DATE = TODAY - timedelta(days=90)

def load_tonal():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "tonal/tonal_workouts_*.json")), reverse=True)
    if not files:
        return {}
    data = json.load(open(files[0]))
    daily = defaultdict(float)
    for w in data.get("workouts", []):
        bt = w.get("beginTime", "")
        if not bt:
            continue
        try:
            dt = datetime.fromisoformat(bt.replace("Z", "+00:00")).astimezone(TZ).date()
        except Exception:
            continue
        vol = w.get("totalVolume", 0) or 0
        daily[str(dt)] += vol
    return daily

def load_garmin():
    path = os.path.join(DATA_DIR, "garmin_all_activities.json")
    if not os.path.exists(path):
        return {}
    data = json.load(open(path))
    daily = defaultdict(lambda: {"distance": 0, "duration": 0, "count": 0})
    for a in data.get("activities", []):
        dt_str = str(a.get("startTimeLocal", ""))[:10]
        if not dt_str:
            continue
        activity_type = str(a.get("activityType", "")).lower()
        if "run" in activity_type or "walk" in activity_type or "cycling" in activity_type or "cardio" in activity_type:
            daily[dt_str]["distance"] += a.get("distance", 0) or 0
            daily[dt_str]["duration"] += a.get("duration", 0) or 0
            daily[dt_str]["count"] += 1
    return daily

def load_whoop():
    path = os.path.join(DATA_DIR, "whoop_v2_latest.json")
    if not os.path.exists(path):
        return {}
    data = json.load(open(path))
    daily = {}
    for rec in data.get("recovery", {}).get("records", []):
        score = rec.get("score", {}) or {}
        created = rec.get("created_at", "")[:10]
        if not created:
            continue
        daily[created] = {
            "recovery_score": score.get("recovery_score", 0) or 0,
            "hrv": score.get("hrv_rmssd_milli", 0) or 0,
            "rhr": score.get("resting_heart_rate", 0) or 0,
        }
    return daily

def load_eight_sleep():
    files = glob.glob(os.path.join(DATA_DIR, "eight_sleep/*.json"))
    daily = {}
    for f in files:
        try:
            d = json.load(open(f))
            dt_str = d.get("date", os.path.basename(f).replace(".json", ""))
            score = d.get("sleep_score") or d.get("score") or d.get("sleep_quality_score") or 0
            if dt_str and score:
                daily[dt_str] = float(score)
        except Exception:
            pass
    return daily

def load_cronometer():
    path = os.path.join(DATA_DIR, "cronometer_historical.csv")
    if not os.path.exists(path):
        return {}
    daily = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = row.get("Date", "")
            if not dt:
                continue
            daily[dt] = {
                "protein": float(row.get("Protein (g)", 0) or 0),
                "calories": float(row.get("Energy (kcal)", 0) or 0),
            }
    return daily

def rolling_avg(data_dict, key_fn, days=30, end_date=None):
    if end_date is None:
        end_date = TODAY
    vals = []
    for i in range(days):
        d = str(end_date - timedelta(days=i))
        v = key_fn(d)
        if v is not None and v > 0:
            vals.append(v)
    return sum(vals) / len(vals) if vals else 0

def compute_strength_score(tonal, end_date, baseline):
    avg = rolling_avg(tonal, lambda d: tonal.get(d, 0), 30, end_date)
    if baseline <= 0:
        return 50
    ratio = avg / baseline
    return min(100, max(0, ratio * 60 + 20))

def compute_cardio_score(garmin, end_date):
    count = 0
    total_dist = 0
    for i in range(30):
        d = str(end_date - timedelta(days=i))
        rec = garmin.get(d, {})
        count += rec.get("count", 0)
        total_dist += rec.get("distance", 0)
    freq_score = min(100, count / 8 * 100)
    dist_score = min(100, total_dist / 50000 * 100)
    return (freq_score * 0.6 + dist_score * 0.4)

def compute_recovery_score(whoop, end_date):
    vals = []
    for i in range(30):
        d = str(end_date - timedelta(days=i))
        rec = whoop.get(d, {})
        s = rec.get("recovery_score", 0)
        if s > 0:
            vals.append(s)
    return sum(vals) / len(vals) if vals else 50

def compute_sleep_score(eight_sleep, end_date):
    vals = []
    for i in range(30):
        d = str(end_date - timedelta(days=i))
        s = eight_sleep.get(d, 0)
        if s > 0:
            vals.append(s)
    return sum(vals) / len(vals) if vals else 50

def compute_nutrition_score(cronometer, end_date, protein_target=150):
    hits = 0
    total = 0
    for i in range(30):
        d = str(end_date - timedelta(days=i))
        rec = cronometer.get(d)
        if rec:
            total += 1
            if rec["protein"] >= protein_target * 0.9:
                hits += 1
    if total == 0:
        return 50
    return (hits / total) * 100

def compute_composite(s, c, r, sl, n):
    return s * 0.30 + c * 0.20 + r * 0.25 + sl * 0.15 + n * 0.10

def build_timeline():
    tonal = load_tonal()
    garmin = load_garmin()
    whoop = load_whoop()
    eight_sleep = load_eight_sleep()
    cronometer = load_cronometer()
    baseline_vol = rolling_avg(tonal, lambda d: tonal.get(d, 0), 90, TODAY)
    timeline = []
    for i in range(90, -1, -1):
        d = TODAY - timedelta(days=i)
        ds = str(d)
        s = compute_strength_score(tonal, d, baseline_vol)
        c = compute_cardio_score(garmin, d)
        r = compute_recovery_score(whoop, d)
        sl = compute_sleep_score(eight_sleep, d)
        n = compute_nutrition_score(cronometer, d)
        comp = compute_composite(s, c, r, sl, n)
        timeline.append({"date": ds, "composite": round(comp, 1), "strength": round(s, 1),
                         "cardio": round(c, 1), "recovery": round(r, 1), "sleep": round(sl, 1), "nutrition": round(n, 1)})
    return timeline, tonal, garmin, whoop, eight_sleep, cronometer

def make_area_chart(data_points, width=900, height=280, color="#f39c12"):
    pad_l, pad_r, pad_t, pad_b = 50, 20, 20, 40
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b
    vals = [p["composite"] for p in data_points]
    dates = [p["date"] for p in data_points]
    n = len(vals)
    if n < 2:
        return "<svg></svg>"
    x_step = w / (n - 1)
    def px(i): return pad_l + i * x_step
    def py(v): return pad_t + h - v / 100 * h
    grid = ""
    for yv in [25, 50, 75]:
        yp = py(yv)
        grid += f'<line x1="{pad_l}" y1="{yp:.1f}" x2="{pad_l+w}" y2="{yp:.1f}" stroke="#2a3040" stroke-dasharray="4,4"/>'
        grid += f'<text x="{pad_l-5}" y="{yp+4:.1f}" text-anchor="end" fill="#888" font-size="11">{yv}</text>'
    pts = [(px(i), py(v)) for i, v in enumerate(vals)]
    path_d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}" + "".join(f"L{x:.1f},{y:.1f}" for x, y in pts[1:])
    area_d = path_d + f"L{pts[-1][0]:.1f},{pad_t+h:.1f}L{pts[0][0]:.1f},{pad_t+h:.1f}Z"
    xlabels = ""
    for i in range(0, n, 15):
        xp = px(i)
        d_label = dates[i][5:]
        xlabels += f'<text x="{xp:.1f}" y="{pad_t+h+18}" text-anchor="middle" fill="#888" font-size="10">{d_label}</text>'
    return f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{color}" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0.05"/>
    </linearGradient>
  </defs>
  {grid}
  <path d="{area_d}" fill="url(#areaGrad)" stroke="none"/>
  <path d="{path_d}" fill="none" stroke="{color}" stroke-width="2.5"/>
  {xlabels}
</svg>'''

def make_mini_chart(vals, width=160, height=80, color="#f39c12"):
    n = len(vals)
    if n < 2:
        return "<svg></svg>"
    pad = 6
    w = width - pad * 2
    h = height - pad * 2
    vmin = min(vals) if vals else 0
    vmax = max(vals) if vals else 100
    rng = vmax - vmin if vmax != vmin else 1
    def px(i): return pad + i * w / (n - 1)
    def py(v): return pad + h - (v - vmin) / rng * h
    pts = [(px(i), py(v)) for i, v in enumerate(vals)]
    path_d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}" + "".join(f"L{x:.1f},{y:.1f}" for x, y in pts[1:])
    area_d = path_d + f"L{pts[-1][0]:.1f},{pad+h:.1f}L{pts[0][0]:.1f},{pad+h:.1f}Z"
    cid = color.strip('#')
    return f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="mg{cid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{color}" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  <path d="{area_d}" fill="url(#mg{cid})" stroke="none"/>
  <path d="{path_d}" fill="none" stroke="{color}" stroke-width="2"/>
</svg>'''

def make_circular_gauge(value, size=90, color="#f39c12", label=""):
    cx, cy, r = size // 2, size // 2, size // 2 - 10
    sweep = 270
    start_angle = 135
    angle = start_angle + sweep * (value / 100)
    def polar(cx, cy, r, deg):
        rad = math.radians(deg)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)
    x0, y0 = polar(cx, cy, r, start_angle)
    x1, y1 = polar(cx, cy, r, angle)
    bg_x0, bg_y0 = polar(cx, cy, r, start_angle)
    bg_x1, bg_y1 = polar(cx, cy, r, start_angle + sweep)
    large_arc = 1 if sweep * (value / 100) > 180 else 0
    return f'''<svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
  <path d="M{bg_x0:.1f},{bg_y0:.1f} A{r},{r} 0 1,1 {bg_x1:.1f},{bg_y1:.1f}"
        fill="none" stroke="#2a3040" stroke-width="8" stroke-linecap="round"/>
  <path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 {large_arc},1 {x1:.1f},{y1:.1f}"
        fill="none" stroke="{color}" stroke-width="8" stroke-linecap="round"/>
  <text x="{cx}" y="{cy+4}" text-anchor="middle" fill="white" font-size="16" font-weight="bold">{int(value)}</text>
  <text x="{cx}" y="{cy+18}" text-anchor="middle" fill="#888" font-size="9">{label}</text>
</svg>'''

def generate_html(timeline):
    today_data = timeline[-1]
    data_30d_ago = timeline[-31] if len(timeline) >= 31 else timeline[0]
    data_60d_ago = timeline[-61] if len(timeline) >= 61 else timeline[0]
    data_90d_ago = timeline[0]
    current = today_data["composite"]
    diff_30 = current - data_30d_ago["composite"]
    diff_60 = current - data_60d_ago["composite"]
    diff_90 = current - data_90d_ago["composite"]
    trend_arrow = "↑" if diff_30 > 0 else "↓" if diff_30 < 0 else "→"
    trend_color = "#2ea043" if diff_30 > 0 else "#f85149" if diff_30 < 0 else "#888"

    def diff_badge(val, label):
        color = "#2ea043" if val >= 0 else "#f85149"
        sign = "+" if val >= 0 else ""
        return f'<span style="background:{color}22;color:{color};border:1px solid {color};padding:4px 12px;border-radius:20px;font-size:13px">{sign}{val:.1f} {label}</span>'

    main_chart = make_area_chart(timeline, width=900, height=280)
    last30 = timeline[-30:]
    components = [
        ("Strength", "strength", "#0a84ff"),
        ("Cardio", "cardio", "#2ea043"),
        ("Recovery", "recovery", "#f39c12"),
        ("Sleep", "sleep", "#a371f7"),
        ("Nutrition", "nutrition", "#f85149"),
    ]
    mini_charts_html = ""
    for name, key, color in components:
        vals = [d[key] for d in last30]
        chart = make_mini_chart(vals, 160, 80, color)
        avg_val = sum(vals) / len(vals) if vals else 0
        mini_charts_html += f'''
        <div style="background:#161b22;border-radius:10px;padding:12px;text-align:center;min-width:150px">
          <div style="color:{color};font-size:12px;font-weight:600;margin-bottom:4px">{name}</div>
          {chart}
          <div style="color:white;font-size:18px;font-weight:bold;margin-top:4px">{avg_val:.0f}</div>
        </div>'''

    gauges_html = ""
    for (name, key, color) in components:
        val = today_data[key]
        gauges_html += f'<div style="text-align:center">{make_circular_gauge(val, 90, color, name)}</div>'

    recent_avg = sum(d["composite"] for d in timeline[-7:]) / 7
    prior_avg = sum(d["composite"] for d in timeline[-14:-7]) / 7
    if recent_avg > prior_avg + 2:
        trajectory_text = "📈 On an upward trend"
        trajectory_color = "#2ea043"
    elif recent_avg < prior_avg - 2:
        trajectory_text = "📉 Showing a declining trend"
        trajectory_color = "#f85149"
    else:
        trajectory_text = "➡️ Plateaued — stable performance"
        trajectory_color = "#f39c12"

    comp_vals = {name: today_data[key] for name, key, _ in components}
    best_comp = max(comp_vals, key=comp_vals.get)
    worst_comp = min(comp_vals, key=comp_vals.get)

    def table_row(label, d):
        return f"""<tr>
          <td style="padding:10px 12px;color:#ccc">{label}</td>
          <td style="padding:10px 12px;color:#f39c12;font-weight:bold;text-align:center">{d['composite']:.1f}</td>
          <td style="padding:10px 12px;text-align:center;color:#0a84ff">{d['strength']:.0f}</td>
          <td style="padding:10px 12px;text-align:center;color:#2ea043">{d['cardio']:.0f}</td>
          <td style="padding:10px 12px;text-align:center;color:#f39c12">{d['recovery']:.0f}</td>
          <td style="padding:10px 12px;text-align:center;color:#a371f7">{d['sleep']:.0f}</td>
          <td style="padding:10px 12px;text-align:center;color:#f85149">{d['nutrition']:.0f}</td>
        </tr>"""

    table_rows = (
        table_row("Today", today_data)
        + table_row("30 days ago", data_30d_ago)
        + table_row("60 days ago", data_60d_ago)
        + table_row("90 days ago", data_90d_ago)
    )

    def score_color(v):
        if v >= 75: return "#2ea043"
        if v >= 50: return "#f39c12"
        return "#f85149"

    sc = score_color(current)
    updated = datetime.now(TZ).strftime("%B %d, %Y at %I:%M %p")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>30-Day Rolling Fitness Score</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #0d1117; color: white; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
nav {{ background: #161b22; border-bottom: 1px solid #30363d; padding: 12px 24px; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }}
nav a {{ color: #58a6ff; text-decoration: none; font-size: 13px; padding: 4px 10px; border-radius: 6px; transition: background 0.2s; }}
nav a:hover {{ background: #21262d; }}
nav a.active {{ background: #21262d; color: #f39c12; }}
.container {{ max-width: 1000px; margin: 0 auto; padding: 24px 20px; }}
h1 {{ font-size: 28px; margin-bottom: 4px; }}
.subtitle {{ color: #888; margin-bottom: 20px; }}
.hero {{ display: flex; align-items: center; gap: 24px; margin-bottom: 24px; flex-wrap: wrap; }}
.big-score {{ font-size: 80px; font-weight: 900; line-height: 1; color: {sc}; }}
.trend-arrow {{ font-size: 48px; color: {trend_color}; }}
.badges {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
.card h2 {{ font-size: 16px; color: #888; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.5px; }}
.gauges {{ display: flex; gap: 20px; flex-wrap: wrap; justify-content: space-around; }}
.mini-charts {{ display: flex; gap: 12px; flex-wrap: wrap; justify-content: space-between; }}
.chart-scroll {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ padding: 10px 12px; color: #888; font-size: 12px; text-transform: uppercase; border-bottom: 1px solid #30363d; text-align: center; }}
th:first-child {{ text-align: left; }}
tr:hover {{ background: #1c2128; }}
.trajectory-box {{ padding: 16px 20px; border-radius: 10px; background: {trajectory_color}18; border: 1px solid {trajectory_color}44; }}
.driver-list {{ margin-top: 12px; color: #ccc; font-size: 14px; line-height: 1.8; }}
.updated {{ color: #555; font-size: 12px; margin-top: 20px; text-align: center; }}
</style>
</head>
<body>
<nav>
  <a href="/index.html">🏠 Hub</a>
  <a href="/strength/index.html">💪 Strength</a>
  <a href="/cardio/index.html">🏃 Cardio</a>
  <a href="/recovery/index.html">💚 Recovery</a>
  <a href="/nutrition/index.html">🥗 Nutrition</a>
  <a href="/fitness_rolling_30d/index.html" class="active">📊 Rolling Score</a>
</nav>
<div class="container">
  <h1>30-Day Rolling Fitness Score</h1>
  <p class="subtitle">Your composite fitness trajectory — updated daily</p>
  <div class="hero">
    <div>
      <div class="big-score">{current:.0f}</div>
      <div style="color:#888;font-size:14px;margin-top:4px">Composite Score / 100</div>
    </div>
    <div class="trend-arrow">{trend_arrow}</div>
    <div>
      <div class="badges">
        {diff_badge(diff_30, "vs 30d ago")}
        {diff_badge(diff_60, "vs 60d ago")}
        {diff_badge(diff_90, "vs 90d ago")}
      </div>
    </div>
  </div>
  <div class="card">
    <h2>Score Breakdown — Today</h2>
    <div class="gauges">{gauges_html}</div>
  </div>
  <div class="card">
    <h2>Composite Score — Last 90 Days</h2>
    <div class="chart-scroll">{main_chart}</div>
  </div>
  <div class="card">
    <h2>Component Trends — Last 30 Days</h2>
    <div class="mini-charts">{mini_charts_html}</div>
  </div>
  <div class="card">
    <h2>Trajectory Analysis</h2>
    <div class="trajectory-box">
      <div style="font-size:18px;font-weight:600;color:{trajectory_color}">{trajectory_text}</div>
      <div class="driver-list">
        🏆 Best component: <strong style="color:#f39c12">{best_comp}</strong> ({comp_vals[best_comp]:.0f}/100)<br>
        ⚠️ Focus area: <strong style="color:#f85149">{worst_comp}</strong> ({comp_vals[worst_comp]:.0f}/100)<br>
        📅 7-day avg: <strong>{recent_avg:.1f}</strong> vs prior 7-day: <strong>{prior_avg:.1f}</strong>
      </div>
    </div>
  </div>
  <div class="card">
    <h2>Historical Comparison</h2>
    <div class="chart-scroll">
      <table>
        <thead>
          <tr>
            <th>Period</th>
            <th style="color:#f39c12">Composite</th>
            <th style="color:#0a84ff">Strength</th>
            <th style="color:#2ea043">Cardio</th>
            <th style="color:#f39c12">Recovery</th>
            <th style="color:#a371f7">Sleep</th>
            <th style="color:#f85149">Nutrition</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
  </div>
  <p class="updated">Last updated: {updated}</p>
</div>
</body>
</html>"""

if __name__ == "__main__":
    print("Loading data sources...")
    timeline, tonal, garmin, whoop, eight_sleep, cronometer = build_timeline()
    print(f"  Tonal: {len(tonal)} workout days")
    print(f"  Garmin: {len(garmin)} activity days")
    print(f"  WHOOP: {len(whoop)} recovery days")
    print(f"  8Sleep: {len(eight_sleep)} sleep days")
    print(f"  Cronometer: {len(cronometer)} nutrition days")
    print(f"  Timeline: {len(timeline)} days")
    today_data = timeline[-1]
    print(f"\nToday scores — Composite: {today_data['composite']} | S:{today_data['strength']} C:{today_data['cardio']} R:{today_data['recovery']} Sl:{today_data['sleep']} N:{today_data['nutrition']}")
    print("\nGenerating HTML...")
    html = generate_html(timeline)
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)
    size = os.path.getsize(OUTPUT_FILE)
    print(f"Output: {OUTPUT_FILE} ({size:,} bytes)")
    assert size > 3000, f"Output too small: {size} bytes"
    print("SUCCESS")
