#!/usr/bin/env python3
"""
generate_muscle_frequency_analysis.py
Generates muscle_frequency/index.html from Tonal + WHOOP data.
"""

import json, os
from datetime import datetime, timedelta
from collections import defaultdict
import pytz

NY_TZ = pytz.timezone("America/New_York")
CLAWD_HOME = os.path.expanduser("~/clawd")
DATA_DIR = os.path.join(CLAWD_HOME, "data")
OUTPUT_DIR = os.path.join(CLAWD_HOME, "docs", "muscle_frequency")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TONAL_PATH = os.path.join(DATA_DIR, "tonal", "tonal_workouts_20260225_214518.json")
WHOOP_PATH = os.path.join(DATA_DIR, "whoop_v2_latest.json")

MUSCLE_COLORS = {
    "Chest":      "#e74c3c",
    "Back":       "#3498db",
    "Shoulders":  "#9b59b6",
    "Biceps":     "#1abc9c",
    "Triceps":    "#16a085",
    "Quads":      "#f39c12",
    "Hamstrings": "#e67e22",
    "Glutes":     "#d35400",
    "Calves":     "#27ae60",
    "Core":       "#2980b9",
    "Forearms":   "#8e44ad",
    "Abs":        "#f1c40f",
}
MUSCLE_GROUPS = list(MUSCLE_COLORS.keys())
RECOVERY_HOURS = {
    "Chest": 48, "Back": 48, "Shoulders": 72,
    "Biceps": 48, "Triceps": 48, "Quads": 72,
    "Hamstrings": 72, "Glutes": 48, "Calves": 48,
    "Core": 24, "Forearms": 24, "Abs": 24,
}

def label_to_muscles(label):
    label = (label or "").lower()
    muscles = []
    if any(k in label for k in ["push", "chest", "bench", "fly", "pec"]):
        muscles.append("Chest")
        muscles.append("Triceps")
    if any(k in label for k in ["pull", "back", "row", "deadlift", "lat", "shrug"]):
        muscles.append("Back")
        muscles.append("Biceps")
    if any(k in label for k in ["shoulder", "press", "lateral", "front raise", "arnold", "overhead", "ohp"]):
        muscles.append("Shoulders")
    if any(k in label for k in ["tricep", "extension", "skull"]):
        muscles.append("Triceps")
    if any(k in label for k in ["bicep", "curl", "hammer", "preacher"]):
        muscles.append("Biceps")
    if any(k in label for k in ["squat", "leg press", "leg ext", "lunge", "hack"]):
        muscles.extend(["Quads", "Glutes"])
    if any(k in label for k in ["rdl", "romanian", "leg curl", "nordic", "good morning", "hamstring"]):
        muscles.extend(["Hamstrings", "Glutes"])
    if any(k in label for k in ["hip thrust", "glute", "kickback"]):
        muscles.append("Glutes")
    if any(k in label for k in ["calf"]):
        muscles.append("Calves")
    if any(k in label for k in ["core", "plank", "crunch", "twist", "leg raise"]):
        muscles.extend(["Core", "Abs"])
    if any(k in label for k in ["ab ", "abs"]):
        muscles.append("Abs")
    if any(k in label for k in ["forearm", "wrist", "farmer"]):
        muscles.append("Forearms")
    if not muscles:
        muscles = ["Chest", "Back", "Shoulders", "Biceps", "Triceps"]
    return list(set(muscles))

with open(TONAL_PATH) as f:
    tonal_raw = json.load(f)
workouts_raw = tonal_raw.get("workouts", [])
custom_workouts = tonal_raw.get("customWorkouts", {})

mid_to_label = {}
for w in workouts_raw:
    wid = w.get("workoutId", "")
    title = None
    if isinstance(custom_workouts.get(wid), dict):
        title = custom_workouts[wid].get("title")
    if not title:
        title = w.get("workoutType", "Custom")
    for sa in (w.get("workoutSetActivity") or []):
        mid = sa.get("movementId")
        if mid and mid not in mid_to_label:
            mid_to_label[mid] = title

today_ny = datetime.now(NY_TZ).date()
cutoff_60 = today_ny - timedelta(days=60)
daily_muscle_volume = defaultdict(lambda: defaultdict(float))
daily_muscle_sets = defaultdict(lambda: defaultdict(int))

for w in workouts_raw:
    bt = w.get("beginTime", "")
    if not bt:
        continue
    try:
        dt_utc = datetime.fromisoformat(bt.replace("Z", "+00:00"))
        d = dt_utc.astimezone(NY_TZ).date()
    except Exception:
        continue
    if d < cutoff_60:
        continue
    date_str = d.isoformat()
    wid = w.get("workoutId", "")
    title = None
    if isinstance(custom_workouts.get(wid), dict):
        title = custom_workouts[wid].get("title")
    if not title:
        title = w.get("workoutType", "Custom")
    for sa in (w.get("workoutSetActivity") or []):
        mid = sa.get("movementId")
        label = mid_to_label.get(mid, title)
        vol = float(sa.get("totalVolume") or sa.get("volume") or 0)
        muscles = label_to_muscles(label)
        if muscles:
            pv = vol / len(muscles)
            for muscle in muscles:
                daily_muscle_volume[date_str][muscle] += pv
                daily_muscle_sets[date_str][muscle] += 1

with open(WHOOP_PATH) as f:
    whoop_raw = json.load(f)
recovery_records = whoop_raw.get("recovery", {}).get("records", [])
whoop_by_date = {}
for rec in recovery_records:
    d = rec.get("date", "")
    score_obj = rec.get("score", {})
    if isinstance(score_obj, dict):
        rs = score_obj.get("recovery_score")
        hrv = score_obj.get("hrv_rmssd_milli")
    else:
        rs = hrv = None
    if d and rs is not None:
        whoop_by_date[d] = {"recovery_score": rs, "hrv": hrv}

muscle_stats = {}
today_whoop = whoop_by_date.get(today_ny.isoformat(), {})
today_rs = today_whoop.get("recovery_score", 50)

for muscle in MUSCLE_GROUPS:
    total_sets = 0
    total_vol = 0.0
    last_trained = None
    training_days_count = 0
    for i in range(30):
        d = today_ny - timedelta(days=i)
        ds = d.isoformat()
        if muscle in daily_muscle_volume.get(ds, {}):
            total_vol += daily_muscle_volume[ds][muscle]
            total_sets += daily_muscle_sets[ds][muscle]
            training_days_count += 1
            if last_trained is None:
                last_trained = d
    days_since = (today_ny - last_trained).days if last_trained else 999
    rec_hours = RECOVERY_HOURS.get(muscle, 48)
    days_needed = rec_hours / 24
    if today_rs < 33:
        days_needed *= 1.5
    elif today_rs > 66:
        days_needed *= 0.9
    if days_since >= days_needed * 1.5:
        status = "ready"; color = "green"
    elif days_since >= days_needed:
        status = "recovering"; color = "yellow"
    else:
        status = "rest"; color = "red"
    muscle_stats[muscle] = {
        "total_sets": total_sets, "total_vol": round(total_vol, 0),
        "last_trained": last_trained.isoformat() if last_trained else None,
        "days_since": days_since, "training_days_count": training_days_count,
        "status": status, "color": color,
    }

whoop_14 = []
for i in range(13, -1, -1):
    d = today_ny - timedelta(days=i)
    ds = d.isoformat()
    rec = whoop_by_date.get(ds, {})
    whoop_14.append({"date": ds, "label": d.strftime("%b %d"), "score": rec.get("recovery_score")})

NUM_WEEKS = 8
weekly_muscle_vol = []
for w_idx in range(NUM_WEEKS):
    week_end = today_ny - timedelta(days=w_idx * 7)
    week_data = defaultdict(float)
    for d_off in range(7):
        d = week_end - timedelta(days=d_off)
        ds = d.isoformat()
        for muscle in MUSCLE_GROUPS:
            week_data[muscle] += daily_muscle_volume.get(ds, {}).get(muscle, 0)
    weekly_muscle_vol.append(dict(week_data))

max_week_muscle_vol = max((v for wd in weekly_muscle_vol for v in wd.values()), default=1)
max_sets = max((muscle_stats[m]["total_sets"] for m in MUSCLE_GROUPS), default=1)

ready = [m for m in MUSCLE_GROUPS if muscle_stats[m]["status"] == "ready"]
recovering = [m for m in MUSCLE_GROUPS if muscle_stats[m]["status"] == "recovering"]
rest_muscles = [m for m in MUSCLE_GROUPS if muscle_stats[m]["status"] == "rest"]

now_str = datetime.now(NY_TZ).strftime("%A, %B %d %Y at %I:%M %p ET")

def status_badge(status):
    if status == "ready":
        return '<span style="background:#2ea04322;color:#2ea043;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600">✅ Ready</span>'
    elif status == "recovering":
        return '<span style="background:#f39c1222;color:#f39c12;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600">🔄 Recovering</span>'
    return '<span style="background:#f8514922;color:#f85149;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600">😴 Rest</span>'

def days_color(days_since, rec_hours):
    t = rec_hours / 24
    if days_since >= t * 1.5: return "#2ea043"
    elif days_since >= t: return "#f39c12"
    return "#f85149"

grid_cards = ""
for muscle in MUSCLE_GROUPS:
    s = muscle_stats[muscle]
    mc = MUSCLE_COLORS[muscle]
    dc = days_color(s["days_since"], RECOVERY_HOURS[muscle])
    ds_text = f"{s['days_since']}d ago" if s["days_since"] < 999 else "Never"
    vol_text = f"{int(s['total_vol']):,} lbs" if s["total_vol"] > 0 else "—"
    grid_cards += f"""
    <div class="muscle-card" style="border-top:3px solid {mc}">
      <div class="muscle-name">{muscle}</div>
      <div class="muscle-days" style="color:{dc}">{ds_text}</div>
      <div class="muscle-meta">{s['total_sets']} sets &nbsp;·&nbsp; {vol_text} &nbsp;·&nbsp; {s['training_days_count']}d/30d</div>
      <div style="margin-top:6px">{status_badge(s['status'])}</div>
    </div>"""

# Frequency bars
BAR_W, BAR_H, BAR_LEFT, BAR_RIGHT = 700, 340, 110, 680
BAR_TOP, BAR_BOTTOM = 20, 320
bar_h_each = (BAR_BOTTOM - BAR_TOP) / len(MUSCLE_GROUPS)
freq_bars = f'<svg width="{BAR_W}" height="{BAR_H}" style="display:block;max-width:100%">\n'
sorted_muscles = sorted(MUSCLE_GROUPS, key=lambda m: muscle_stats[m]["total_sets"], reverse=True)
for i, muscle in enumerate(sorted_muscles):
    s = muscle_stats[muscle]
    y = BAR_TOP + i * bar_h_each
    bar_len = (s["total_sets"] / max(max_sets, 1)) * (BAR_RIGHT - BAR_LEFT) * 0.9
    mc = MUSCLE_COLORS[muscle]
    freq_bars += f'  <text x="{BAR_LEFT-8}" y="{y+bar_h_each*0.65:.1f}" text-anchor="end" fill="#ccc" font-size="12">{muscle}</text>\n'
    freq_bars += f'  <rect x="{BAR_LEFT}" y="{y+3:.1f}" width="{max(bar_len,2):.1f}" height="{bar_h_each-6:.1f}" fill="{mc}" rx="3"/>\n'
    if s["total_sets"] > 0:
        freq_bars += f'  <text x="{BAR_LEFT+bar_len+5:.1f}" y="{y+bar_h_each*0.65:.1f}" fill="#8b949e" font-size="11">{s["total_sets"]} sets</text>\n'
freq_bars += '</svg>'

# WHOOP chart
WW, WH = 700, 200
wh_left, wh_right, wh_top, wh_bottom = 40, 680, 15, 175
wh_w = wh_right - wh_left
wh_h = wh_bottom - wh_top
valid_scores = [pt["score"] for pt in whoop_14 if pt["score"] is not None]
score_min = min(valid_scores, default=0)
score_max = max(valid_scores, default=100)
score_range = max(score_max - score_min, 10)
def wy(s): return wh_bottom - ((s - score_min) / score_range) * wh_h
whoop_svg = f'<svg width="{WW}" height="{WH}" style="display:block;max-width:100%">\n'
for sc in [25,50,75,100]:
    if score_min-5 <= sc <= score_max+10:
        yy = wy(sc)
        if wh_top <= yy <= wh_bottom:
            whoop_svg += f'  <line x1="{wh_left}" x2="{wh_right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#21262d" stroke-width="1"/>\n'
            whoop_svg += f'  <text x="{wh_left-5}" y="{yy+4:.1f}" text-anchor="end" fill="#8b949e" font-size="10">{sc}</text>\n'
path_pts = [(wh_left + i*(wh_w/max(len(whoop_14)-1,1)), pt["score"], pt["label"]) for i,pt in enumerate(whoop_14)]
line_path = " ".join(f"{'M' if i==0 else 'L'}{x:.1f},{wy(s):.1f}" for i,(x,s,_) in enumerate(path_pts) if s is not None)
if line_path:
    whoop_svg += f'  <path d="{line_path}" fill="none" stroke="#0a84ff" stroke-width="2"/>\n'
for x,s,lbl in path_pts:
    if s is None: continue
    c = "#2ea043" if s>=67 else "#f39c12" if s>=34 else "#f85149"
    whoop_svg += f'  <circle cx="{x:.1f}" cy="{wy(s):.1f}" r="4" fill="{c}"/>\n'
    whoop_svg += f'  <text x="{x:.1f}" y="{wh_bottom+15:.1f}" text-anchor="middle" fill="#8b949e" font-size="9">{lbl}</text>\n'
whoop_svg += '</svg>'

# Heatmap
HM_W = 700
HM_LABEL_W = 100
HM_CELL_W = (HM_W - HM_LABEL_W) // NUM_WEEKS
HM_CELL_H = 22
HM_H = len(MUSCLE_GROUPS) * HM_CELL_H + 30
heatmap_svg = f'<svg width="{HM_W}" height="{HM_H}" style="display:block;max-width:100%">\n'
for w_idx in range(NUM_WEEKS):
    x = HM_LABEL_W + w_idx*HM_CELL_W + HM_CELL_W//2
    lbl = (today_ny - timedelta(days=w_idx*7)).strftime("%b %d")
    heatmap_svg += f'  <text x="{x}" y="14" text-anchor="middle" fill="#8b949e" font-size="9">{lbl}</text>\n'
for row, muscle in enumerate(MUSCLE_GROUPS):
    y = 20 + row*HM_CELL_H
    mc = MUSCLE_COLORS[muscle]
    heatmap_svg += f'  <text x="{HM_LABEL_W-5}" y="{y+HM_CELL_H*0.65:.1f}" text-anchor="end" fill="#ccc" font-size="11">{muscle}</text>\n'
    for w_idx in range(NUM_WEEKS):
        vol = weekly_muscle_vol[w_idx].get(muscle, 0)
        intensity = min(vol / max(max_week_muscle_vol, 1), 1.0)
        alpha = int(intensity*220+20) if vol > 0 else 0
        x = HM_LABEL_W + w_idx*HM_CELL_W + 2
        cw = HM_CELL_W - 4; ch = HM_CELL_H - 3
        if vol > 0:
            heatmap_svg += f'  <rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="{mc}{alpha:02x}" rx="2"/>\n'
            if intensity > 0.3:
                vl = f"{vol/1000:.1f}k" if vol>=1000 else str(int(vol))
                heatmap_svg += f'  <text x="{x+cw//2}" y="{y+ch*0.65:.1f}" text-anchor="middle" fill="white" font-size="9">{vl}</text>\n'
        else:
            heatmap_svg += f'  <rect x="{x}" y="{y}" width="{cw}" height="{ch}" fill="#21262d" rx="2"/>\n'
heatmap_svg += '</svg>'

def muscle_pill(m):
    mc = MUSCLE_COLORS[m]
    return f'<span style="background:{mc}22;color:{mc};border:1px solid {mc}44;border-radius:12px;padding:2px 10px;margin:2px;display:inline-block;font-size:13px">{m}</span>'

ready_pills = "".join(muscle_pill(m) for m in ready) or '<span style="color:#8b949e">None ready</span>'
recovering_pills = "".join(muscle_pill(m) for m in recovering) or '<span style="color:#8b949e">None</span>'
rest_pills = "".join(muscle_pill(m) for m in rest_muscles) or '<span style="color:#8b949e">None</span>'
rs_color = "#2ea043" if today_rs and today_rs>=67 else "#f39c12" if today_rs and today_rs>=34 else "#f85149"
rs_text = f"Today's WHOOP recovery: <strong style='color:{rs_color}'>{today_rs}%</strong>" if today_rs else "No WHOOP data for today"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Muscle Frequency & Recovery</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:0 0 60px}}
nav{{background:#161b22;border-bottom:1px solid #21262d;padding:10px 20px;display:flex;flex-wrap:wrap;gap:12px;align-items:center}}
nav a{{color:#8b949e;text-decoration:none;font-size:13px;padding:4px 8px;border-radius:6px;transition:background .15s,color .15s}}
nav a:hover{{background:#21262d;color:#e6edf3}}
.container{{max-width:900px;margin:0 auto;padding:28px 20px}}
h1{{font-size:26px;font-weight:700;margin-bottom:4px}}
.subtitle{{color:#8b949e;font-size:13px;margin-bottom:28px}}
h2{{font-size:17px;font-weight:600;margin-bottom:14px;color:#e6edf3}}
.section{{margin-bottom:36px}}
.card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:18px 20px}}
.muscle-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
@media(max-width:600px){{.muscle-grid{{grid-template-columns:repeat(2,1fr)}}}}
.muscle-card{{background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px 14px}}
.muscle-name{{font-weight:600;font-size:14px;margin-bottom:3px}}
.muscle-days{{font-size:13px;font-weight:500;margin-bottom:4px}}
.muscle-meta{{font-size:11px;color:#8b949e;margin-bottom:6px}}
.rec-row{{display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap;margin-bottom:10px}}
.rec-label{{font-size:13px;font-weight:600;min-width:110px;flex-shrink:0;padding-top:4px}}
.chart-wrap{{overflow-x:auto}}
</style>
</head>
<body>
<nav>
  <a href="../index.html">🏠 Home</a>
  <a href="../strength/index.html">💪 Strength</a>
  <a href="../cardio/index.html">🏃 Cardio</a>
  <a href="../recovery/index.html">🛌 Recovery</a>
  <a href="../nutrition/index.html">🥗 Nutrition</a>
  <a href="../muscle_recovery/index.html">🗺️ Muscle Map</a>
  <a href="../training_scheduler/index.html">📅 Scheduler</a>
</nav>
<div class="container">
  <h1>💪 Muscle Frequency &amp; Recovery</h1>
  <p class="subtitle">Training frequency by muscle group + recovery-based recommendations &nbsp;·&nbsp; Generated {now_str}</p>

  <div class="section">
    <h2>🎯 Today's Recommendation</h2>
    <div class="card">
      <div style="font-size:14px;margin-bottom:14px">{rs_text}</div>
      <div class="rec-row"><div class="rec-label" style="color:#2ea043">✅ Train:</div><div>{ready_pills}</div></div>
      <div class="rec-row"><div class="rec-label" style="color:#f39c12">🔄 Maybe:</div><div>{recovering_pills}</div></div>
      <div class="rec-row"><div class="rec-label" style="color:#f85149">😴 Rest:</div><div>{rest_pills}</div></div>
    </div>
  </div>

  <div class="section">
    <h2>🏋️ Muscle Group Status — Last 30 Days</h2>
    <div class="muscle-grid">{grid_cards}</div>
  </div>

  <div class="section">
    <h2>📊 Training Frequency — Sets per Muscle Group</h2>
    <div class="card"><div class="chart-wrap">{freq_bars}</div></div>
  </div>

  <div class="section">
    <h2>💚 WHOOP Recovery Score — Last 14 Days</h2>
    <div class="card"><div class="chart-wrap">{whoop_svg}</div></div>
  </div>

  <div class="section">
    <h2>🌡️ Volume Heatmap — Last 8 Weeks</h2>
    <p style="color:#8b949e;font-size:12px;margin-bottom:12px">Color intensity = volume (lbs). Most recent week on left.</p>
    <div class="card"><div class="chart-wrap">{heatmap_svg}</div></div>
  </div>
</div>
</body>
</html>"""

out_path = os.path.join(OUTPUT_DIR, "index.html")
with open(out_path, "w") as f:
    f.write(html)
print(f"SUCCESS: {out_path} ({os.path.getsize(out_path):,} bytes)")
