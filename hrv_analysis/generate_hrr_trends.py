#!/usr/bin/env python3
"""Generate Heart Rate Reserve (HRR) Trends section and append to hrv_analysis/index.html"""

import json
import os
import glob
from datetime import datetime, timedelta, date
from pathlib import Path

BASE = Path("/Users/tobyglennpeters/clawd")
DATA_GARMIN_DIR = BASE / "data" / "garmin"
DATA_WHOOP = BASE / "data" / "whoop_v2_latest.json"
DATA_ACTIVITIES = BASE / "data" / "garmin_all_activities.json"
OUTPUT_FILE = BASE / "docs" / "hrv_analysis" / "index.html"

# Load Garmin daily data
print("Loading Garmin daily data...")
garmin_daily = {}
for fp in sorted(glob.glob(str(DATA_GARMIN_DIR / "20*.json"))):
    day = os.path.basename(fp).replace(".json", "")
    try:
        with open(fp) as f:
            d = json.load(f)
        stats = d.get("stats", {})
        rhr = stats.get("restingHeartRate")
        max_hr = stats.get("maxHeartRate")
        if rhr and max_hr and rhr > 30 and max_hr > 60:
            garmin_daily[day] = {"rhr": rhr, "max_hr": max_hr, "hrr": max_hr - rhr}
    except Exception:
        pass

print(f"  Loaded {len(garmin_daily)} days with valid HRR data")

# Load WHOOP recovery
print("Loading WHOOP data...")
whoop_by_date = {}
try:
    with open(DATA_WHOOP) as f:
        wd = json.load(f)
    for rec in wd.get("recovery", {}).get("records", []):
        score_obj = rec.get("score", {})
        created = rec.get("created_at", "")[:10]
        rs = score_obj.get("recovery_score")
        rhr = score_obj.get("resting_heart_rate")
        hrv = score_obj.get("hrv_rmssd_milli")
        if created and rs is not None:
            whoop_by_date[created] = {"recovery_score": rs, "rhr": rhr, "hrv": hrv}
    print(f"  Loaded {len(whoop_by_date)} WHOOP records")
except Exception as e:
    print(f"  WHOOP load failed: {e}")

# Load Garmin activities
print("Loading Garmin activities...")
workout_hr_by_date = {}
try:
    with open(DATA_ACTIVITIES) as f:
        ad = json.load(f)
    activities = ad.get("activities", [])
    for act in activities:
        d = act.get("date", "")
        avg_hr = act.get("averageHR")
        max_hr_act = act.get("maxHR")
        if d and avg_hr:
            if d not in workout_hr_by_date:
                workout_hr_by_date[d] = []
            workout_hr_by_date[d].append({"avgHR": avg_hr, "maxHR": max_hr_act})
    print(f"  Loaded workout HR data for {len(workout_hr_by_date)} days")
except Exception as e:
    print(f"  Activities load failed: {e}")

# Build timeline (last 365 days)
today = date.today()
start = today - timedelta(days=364)
timeline = []
for i in range(365):
    d = start + timedelta(days=i)
    ds = d.strftime("%Y-%m-%d")
    g = garmin_daily.get(ds, {})
    w = whoop_by_date.get(ds, {})
    if g:
        timeline.append({
            "date": ds,
            "hrr": g["hrr"],
            "rhr": g["rhr"],
            "max_hr": g["max_hr"],
            "recovery_score": w.get("recovery_score"),
            "whoop_rhr": w.get("rhr"),
        })

print(f"  Timeline has {len(timeline)} points")

# Stats
hrr_vals = [t["hrr"] for t in timeline]
current_hrr = hrr_vals[-1] if hrr_vals else 0
avg_30 = sum(hrr_vals[-30:]) / max(len(hrr_vals[-30:]), 1)
best_hrr = max(hrr_vals) if hrr_vals else 0

# Trend
if len(hrr_vals) >= 28:
    recent14 = sum(hrr_vals[-14:]) / 14
    prior14 = sum(hrr_vals[-28:-14]) / 14
    diff = recent14 - prior14
    trend_indicator = "↑ Improving" if diff > 2 else ("↓ Declining" if diff < -2 else "→ Stable")
    trend_color = "#2ea043" if diff > 2 else ("#f85149" if diff < -2 else "#f39c12")
else:
    trend_indicator = "→ Stable"
    trend_color = "#f39c12"

def rolling_avg(vals, window=30):
    result = []
    for i in range(len(vals)):
        start_i = max(0, i - window + 1)
        chunk = vals[start_i:i+1]
        result.append(sum(chunk) / len(chunk))
    return result

roll30 = rolling_avg(hrr_vals, 30)

# Scatter: HRR vs WHOOP recovery
scatter_pts = [(t["hrr"], t["recovery_score"]) for t in timeline if t["recovery_score"] is not None]

# Zone distribution
zone_counts = {"Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0, "Z5": 0}
for ds, workouts in workout_hr_by_date.items():
    g = garmin_daily.get(ds, {})
    if not g:
        continue
    rhr = g["rhr"]
    hrr = g["hrr"]
    if hrr <= 0:
        continue
    for w in workouts:
        avg_hr = w["avgHR"]
        pct = (avg_hr - rhr) / hrr * 100
        if pct < 60:
            zone_counts["Z1"] += 1
        elif pct < 70:
            zone_counts["Z2"] += 1
        elif pct < 80:
            zone_counts["Z3"] += 1
        elif pct < 90:
            zone_counts["Z4"] += 1
        else:
            zone_counts["Z5"] += 1

total_zone = max(sum(zone_counts.values()), 1)
zone_pcts = {k: round(v / total_zone * 100, 1) for k, v in zone_counts.items()}

# Build SVG: HRR trend
def make_hrr_trend_svg():
    if not hrr_vals:
        return "<p>No data</p>"
    vals90 = hrr_vals[-90:]
    roll90 = roll30[-90:]
    dates90 = [t["date"] for t in timeline[-90:]]
    
    CHART_W, CHART_H = 860, 220
    PAD_L, PAD_R, PAD_T, PAD_B = 50, 20, 20, 40
    PW = CHART_W - PAD_L - PAD_R
    PH = CHART_H - PAD_T - PAD_B
    
    mn = min(vals90) - 5
    mx = max(vals90) + 5
    rng = mx - mn or 1
    n = len(vals90)
    
    def px(i, v):
        x = PAD_L + (i / max(n - 1, 1)) * PW
        y = PAD_T + (1 - (v - mn) / rng) * PH
        return x, y
    
    area_pts = [f"{px(i,v)[0]:.1f},{px(i,v)[1]:.1f}" for i, v in enumerate(vals90)]
    x_last = px(n-1, vals90[-1])[0]
    x_first = px(0, vals90[0])[0]
    area_d = f"M {area_pts[0]} L {' L '.join(area_pts)} L {x_last:.1f},{PAD_T+PH} L {x_first:.1f},{PAD_T+PH} Z"
    line_d = "M " + " L ".join(area_pts)
    
    roll_pts = [f"{px(i,v)[0]:.1f},{px(i,v)[1]:.1f}" for i, v in enumerate(roll90)]
    roll_d = "M " + " L ".join(roll_pts)
    
    grid = ""
    step = 10
    for tick in range(int(mn // step) * step, int(mx) + step, step):
        if mn <= tick <= mx:
            _, y = px(0, tick)
            grid += f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{CHART_W-PAD_R}" y2="{y:.1f}" stroke="#2d333b" stroke-width="1"/>'
            grid += f'<text x="{PAD_L-5}" y="{y+4:.1f}" fill="#8b949e" font-size="10" text-anchor="end">{tick}</text>'
    
    xlabels = ""
    for i in [0, 29, 59, 89]:
        if i < len(dates90):
            x, _ = px(i, mn)
            xlabels += f'<text x="{x:.1f}" y="{PAD_T+PH+18}" fill="#8b949e" font-size="10" text-anchor="middle">{dates90[i][5:]}</text>'
    
    return f'''<svg width="100%" viewBox="0 0 {CHART_W} {CHART_H}" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="hrrGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#f39c12" stop-opacity="0.4"/>
    <stop offset="100%" stop-color="#f39c12" stop-opacity="0.02"/>
  </linearGradient></defs>
  {grid}
  <path d="{area_d}" fill="url(#hrrGrad)"/>
  <path d="{line_d}" fill="none" stroke="#f39c12" stroke-width="2"/>
  <path d="{roll_d}" fill="none" stroke="#0a84ff" stroke-width="2" stroke-dasharray="4,2"/>
  <line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{PAD_T+PH}" stroke="#3d444d" stroke-width="1"/>
  <line x1="{PAD_L}" y1="{PAD_T+PH}" x2="{CHART_W-PAD_R}" y2="{PAD_T+PH}" stroke="#3d444d" stroke-width="1"/>
  {xlabels}
  <text x="{PAD_L+10}" y="{PAD_T+15}" fill="#f39c12" font-size="11">— Daily HRR</text>
  <text x="{PAD_L+110}" y="{PAD_T+15}" fill="#0a84ff" font-size="11">-- 30-day avg</text>
</svg>'''

def make_scatter_svg():
    if not scatter_pts:
        return "<p>No scatter data</p>"
    W, H = 500, 260
    PL, PR, PT, PB = 50, 20, 20, 40
    pw = W - PL - PR
    ph = H - PT - PB
    y_vals = [p[0] for p in scatter_pts]
    ymn = min(y_vals) - 5
    ymx = max(y_vals) + 5
    yrng = ymx - ymn or 1
    
    dots = ""
    for hrr_v, rec in scatter_pts:
        cx = PL + (rec / 100) * pw
        cy = PT + (1 - (hrr_v - ymn) / yrng) * ph
        color = "#2ea043" if rec >= 70 else ("#f39c12" if rec >= 40 else "#f85149")
        dots += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{color}" fill-opacity="0.7"/>'
    
    grid = ""
    for tick in range(int(ymn // 10) * 10, int(ymx) + 10, 10):
        if ymn <= tick <= ymx:
            y = PT + (1 - (tick - ymn) / yrng) * ph
            grid += f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="#2d333b" stroke-width="1"/>'
            grid += f'<text x="{PL-5}" y="{y+4:.1f}" fill="#8b949e" font-size="10" text-anchor="end">{tick}</text>'
    
    xlabels = "".join(f'<text x="{PL+(xv/100)*pw:.1f}" y="{PT+ph+18}" fill="#8b949e" font-size="10" text-anchor="middle">{xv}</text>' for xv in [0,25,50,75,100])
    
    return f'''<svg width="100%" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
  {grid}{dots}
  <line x1="{PL}" y1="{PT}" x2="{PL}" y2="{PT+ph}" stroke="#3d444d" stroke-width="1"/>
  <line x1="{PL}" y1="{PT+ph}" x2="{W-PR}" y2="{PT+ph}" stroke="#3d444d" stroke-width="1"/>
  {xlabels}
  <text x="{W//2}" y="{PT+ph+35}" fill="#8b949e" font-size="11" text-anchor="middle">WHOOP Recovery Score</text>
</svg>'''

def make_zone_bar_svg():
    W, H = 600, 80
    zone_colors = {"Z1": "#2ea043", "Z2": "#0a84ff", "Z3": "#f39c12", "Z4": "#f85149", "Z5": "#8b0000"}
    zone_labels = {"Z1": "Z1 <60%", "Z2": "Z2 60-70%", "Z3": "Z3 70-80%", "Z4": "Z4 80-90%", "Z5": "Z5 >90%"}
    bars = ""
    legend = ""
    x = 0
    for zone in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
        pct = zone_pcts[zone]
        bw = (pct / 100) * W
        bars += f'<rect x="{x:.1f}" y="10" width="{bw:.1f}" height="30" fill="{zone_colors[zone]}"/>'
        if bw > 30:
            bars += f'<text x="{x+bw/2:.1f}" y="30" fill="white" font-size="11" text-anchor="middle">{pct}%</text>'
        x += bw
    lx = 0
    for zone in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
        legend += f'<rect x="{lx}" y="50" width="12" height="12" fill="{zone_colors[zone]}"/>'
        legend += f'<text x="{lx+15}" y="61" fill="#8b949e" font-size="10">{zone_labels[zone]}</text>'
        lx += 115
    return f'<svg width="100%" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">{bars}{legend}</svg>'

# Build section
hrr_trend_svg = make_hrr_trend_svg()
scatter_svg = make_scatter_svg()
zone_svg = make_zone_bar_svg()

zone_pct_cells = "".join(
    f'<div style="font-size:0.8rem;"><div style="color:#e6edf3;font-weight:600;">{zone_pcts[z]}%</div><div style="color:#8b949e;font-size:0.7rem;">Z{i+1}</div></div>'
    for i, z in enumerate(["Z1","Z2","Z3","Z4","Z5"])
)

hrr_section = f"""
<!-- HRR TRENDS SECTION START -->
<section id="hrr-trends" style="margin-top:48px;border-top:2px solid #2d333b;padding-top:32px;padding-bottom:48px;">
  <h2 style="color:#f39c12;font-size:1.6rem;margin-bottom:8px;">&#128147; Heart Rate Reserve (HRR) Trends</h2>
  <p style="color:#8b949e;margin-bottom:24px;font-size:0.9rem;">
    HRR = Max HR &minus; Resting HR. Higher reserve = more cardiac capacity for intense effort.
    <a href="../recovery/index.html" style="color:#0a84ff;margin-left:12px;">&#8592; Back to Recovery</a>
  </p>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:32px;">
    <div style="background:#161b22;border-radius:10px;padding:20px;border:1px solid #2d333b;text-align:center;">
      <div style="color:#8b949e;font-size:0.8rem;margin-bottom:6px;">CURRENT HRR</div>
      <div style="color:#f39c12;font-size:2.2rem;font-weight:700;">{current_hrr}<span style="font-size:1rem;color:#8b949e;"> bpm</span></div>
    </div>
    <div style="background:#161b22;border-radius:10px;padding:20px;border:1px solid #2d333b;text-align:center;">
      <div style="color:#8b949e;font-size:0.8rem;margin-bottom:6px;">30-DAY AVG</div>
      <div style="color:#e6edf3;font-size:2.2rem;font-weight:700;">{avg_30:.0f}<span style="font-size:1rem;color:#8b949e;"> bpm</span></div>
    </div>
    <div style="background:#161b22;border-radius:10px;padding:20px;border:1px solid #2d333b;text-align:center;">
      <div style="color:#8b949e;font-size:0.8rem;margin-bottom:6px;">TREND</div>
      <div style="color:{trend_color};font-size:1.5rem;font-weight:700;">{trend_indicator}</div>
    </div>
    <div style="background:#161b22;border-radius:10px;padding:20px;border:1px solid #2d333b;text-align:center;">
      <div style="color:#8b949e;font-size:0.8rem;margin-bottom:6px;">BEST HRR (1yr)</div>
      <div style="color:#2ea043;font-size:2.2rem;font-weight:700;">{best_hrr}<span style="font-size:1rem;color:#8b949e;"> bpm</span></div>
    </div>
  </div>
  <div style="background:#161b22;border-radius:10px;padding:20px;border:1px solid #2d333b;margin-bottom:24px;">
    <h3 style="color:#e6edf3;margin-bottom:16px;font-size:1.1rem;">HRR Over Time (Last 90 Days)</h3>
    {hrr_trend_svg}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px;">
    <div style="background:#161b22;border-radius:10px;padding:20px;border:1px solid #2d333b;">
      <h3 style="color:#e6edf3;margin-bottom:8px;font-size:1.1rem;">HRR vs WHOOP Recovery</h3>
      <p style="color:#8b949e;font-size:0.8rem;margin-bottom:12px;">{len(scatter_pts)} matched days &mdash; <span style="color:#2ea043;">&#9679;</span> &ge;70 <span style="color:#f39c12;">&#9679;</span> 40-69 <span style="color:#f85149;">&#9679;</span> &lt;40</p>
      {scatter_svg}
    </div>
    <div style="background:#161b22;border-radius:10px;padding:20px;border:1px solid #2d333b;">
      <h3 style="color:#e6edf3;margin-bottom:8px;font-size:1.1rem;">Workout HR Zone Distribution</h3>
      <p style="color:#8b949e;font-size:0.8rem;margin-bottom:12px;">{sum(zone_counts.values())} workout sessions by % HRR used</p>
      {zone_svg}
      <div style="margin-top:12px;display:grid;grid-template-columns:repeat(5,1fr);gap:4px;text-align:center;">{zone_pct_cells}</div>
    </div>
  </div>
  <div style="background:#1c2128;border:1px solid #f39c12;border-left:4px solid #f39c12;border-radius:8px;padding:16px 20px;">
    <p style="color:#e6edf3;margin:0;font-size:0.95rem;">
      &#128161; <strong>Insight:</strong> Your HRR currently averages <strong style="color:#f39c12;">{avg_30:.0f} bpm</strong>.
      A higher HRR means your heart has more range to ramp up during intense effort.
      Consistent cardio lowers resting HR over time, naturally expanding your reserve.
      Your recent 14-day trend is <strong style="color:{trend_color};">{trend_indicator}</strong>.
    </p>
  </div>
</section>
<!-- HRR TRENDS SECTION END -->
"""

print(f"Appending HRR section to {OUTPUT_FILE}...")
with open(OUTPUT_FILE, "r") as f:
    html = f.read()

if "<!-- HRR TRENDS SECTION START -->" in html:
    print("HRR section already present — skipping.")
elif "</body>" in html:
    html = html.replace("</body>", hrr_section + "\n</body>")
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)
    print(f"SUCCESS: {OUTPUT_FILE}")
else:
    with open(OUTPUT_FILE, "a") as f:
        f.write(hrr_section)
    print(f"SUCCESS (appended): {OUTPUT_FILE}")

size = OUTPUT_FILE.stat().st_size
print(f"Output file size: {size:,} bytes")
if size < 3000:
    print("ERROR: file too small!")
    import sys; sys.exit(1)
