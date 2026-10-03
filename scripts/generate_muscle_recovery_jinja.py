#!/usr/bin/env python3
"""
Muscle Recovery Map + Split Optimizer Generator
Generates muscle_recovery/index.html from Tonal, WHOOP, and 8Sleep data.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import zoneinfo
import statistics

# ── Paths ─────────────────────────────────────────────────────────────────────
CLAWD_HOME = os.path.expanduser("~/clawd")
TONAL_DIR = os.path.join(CLAWD_HOME, "data", "tonal")
WHOOP_FILE = os.path.join(CLAWD_HOME, "data", "whoop_v2_latest.json")
EIGHT_SLEEP_DIR = os.path.join(CLAWD_HOME, "data", "eight_sleep")
OUTPUT_DIR = os.path.join(CLAWD_HOME, "docs", "muscle_recovery")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "index.html")

NY_TZ = zoneinfo.ZoneInfo("America/New_York")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Tonal Data ────────────────────────────────────────────────────────────────
tonal_files = sorted([f for f in os.listdir(TONAL_DIR) if f.startswith("tonal_workouts_") and f.endswith(".json")], reverse=True)
if not tonal_files:
    raise FileNotFoundError("No Tonal workout files found")
TONAL_FILE = os.path.join(TONAL_DIR, tonal_files[0])

with open(TONAL_FILE) as f:
    tonal_data = json.load(f)

workouts_raw = tonal_data.get("workouts", [])
custom_workouts = tonal_data.get("customWorkouts", {})

# ── Muscle Group Mapping ───────────────────────────────────────────────────────
MUSCLE_GROUPS = ["Chest", "Back", "Shoulders", "Biceps", "Triceps", "Legs", "Core"]

LABEL_TO_MUSCLES = {
    "Chest and Back Drop Sets": ["Chest", "Back"],
    "Beginner Back and Biceps": ["Back", "Biceps"],
    "Hip/Legs": ["Legs"],
    "Glute Gains": ["Legs"],
    "Efficient Lower Body": ["Legs"],
    "Efficient Upper Body": ["Chest", "Back", "Shoulders"],
    "Upper Body Basics": ["Chest", "Back", "Shoulders"],
    "Quick Fit: Bis and Tris": ["Biceps", "Triceps"],
    "Biceps/Sumo": ["Biceps", "Legs"],
    "Core": ["Core"],
    "Overhead/Biceps": ["Shoulders", "Biceps"],
    "Lat Ex": ["Back"],
    "Bench+": ["Chest"],
    "Handles Bench": ["Chest"],
    "Barbell Blast": ["Chest", "Back", "Shoulders", "Biceps", "Triceps"],
    "Rip and Rotate": ["Core", "Back", "Shoulders"],
    "Shoulder Stretch": ["Shoulders"],
    "NG Deadlift/Dead Bug/raise": ["Back", "Core", "Legs"],
    "Bcep, Dead Bug, FRaise": ["Biceps", "Core", "Shoulders"],
    "Less Is More": ["Chest", "Back", "Shoulders"],
    "Morning": ["Core", "Shoulders"],
    "Quick Refresh": ["Core", "Shoulders"],
    "Strength Essentials": ["Chest", "Back", "Shoulders", "Legs"],
    "Strength with Brendon": ["Chest", "Back", "Shoulders", "Legs"],
    "Strength with Woody": ["Chest", "Back", "Legs"],
}

def label_to_muscles(label):
    label_lower = label.lower()
    if label in LABEL_TO_MUSCLES:
        return LABEL_TO_MUSCLES[label]
    muscles = []
    if any(k in label_lower for k in ["chest", "bench", "push", "pec"]):
        muscles.append("Chest")
    if any(k in label_lower for k in ["back", "lat", "row", "pull", "deadlift", "rdl"]):
        muscles.append("Back")
    if any(k in label_lower for k in ["shoulder", "delt", "press", "overhead", "ohp"]):
        muscles.append("Shoulders")
    if any(k in label_lower for k in ["bicep", "curl", "bic"]):
        muscles.append("Biceps")
    if any(k in label_lower for k in ["tricep", "tri", "dip", "extension"]):
        muscles.append("Triceps")
    if any(k in label_lower for k in ["leg", "squat", "lunge", "hip", "glute", "quad", "hamstring", "calf", "sumo", "rdl"]):
        muscles.append("Legs")
    if any(k in label_lower for k in ["core", "ab", "plank", "crunch", "rotation", "rotate"]):
        muscles.append("Core")
    if not muscles:
        muscles = ["Chest", "Back", "Shoulders", "Biceps", "Triceps", "Legs"]
    return list(set(muscles))

# Build movementId -> workout label
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

# ── Parse Tonal: volume per muscle group per day ─────────────────────────────
today_ny = datetime.now(NY_TZ).date()
cutoff = today_ny - timedelta(days=30)

daily_muscle_volume = defaultdict(lambda: defaultdict(float))
daily_volume = defaultdict(float)

for w in workouts_raw:
    begin_time = w.get("beginTime")
    if not begin_time:
        continue
    try:
        dt_utc = datetime.fromisoformat(begin_time.replace("Z", "+00:00"))
        dt_ny = dt_utc.astimezone(NY_TZ)
        date_str = dt_ny.strftime("%Y-%m-%d")
        date_obj = dt_ny.date()
    except Exception:
        continue
    if date_obj < cutoff:
        continue
    for sa in (w.get("workoutSetActivity") or []):
        mid = sa.get("movementId")
        if not mid:
            continue
        label = mid_to_label.get(mid, "Custom")
        muscles = label_to_muscles(label)
        vol = float(sa.get("volume") or 0)
        if vol > 0 and muscles:
            per_muscle_vol = vol / len(muscles)
            for muscle in muscles:
                daily_muscle_volume[date_str][muscle] += per_muscle_vol
        daily_volume[date_str] += float(sa.get("volume") or 0)

# ── WHOOP Data ────────────────────────────────────────────────────────────────
with open(WHOOP_FILE) as f:
    whoop_data = json.load(f)

cycle_id_to_date = {}
for cyc in (whoop_data.get("cycle", {}).get("records") or []):
    cid = cyc.get("id")
    start = cyc.get("start", "")
    if cid and start:
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(NY_TZ)
            cycle_id_to_date[cid] = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

date_to_recovery = {}
for rec in (whoop_data.get("recovery", {}).get("records") or []):
    cycle_id = rec.get("cycle_id")
    score_obj = rec.get("score") or {}
    recovery_score = score_obj.get("recovery_score")
    hrv = score_obj.get("hrv_rmssd_milli")
    rhr = score_obj.get("resting_heart_rate")
    if recovery_score is not None:
        date_str = cycle_id_to_date.get(cycle_id)
        if date_str:
            date_to_recovery[date_str] = {
                "recovery_score": recovery_score,
                "hrv": hrv,
                "rhr": rhr,
            }

# ── 8Sleep Data ───────────────────────────────────────────────────────────────
date_to_sleep = {}
if os.path.exists(EIGHT_SLEEP_DIR):
    for fn in os.listdir(EIGHT_SLEEP_DIR):
        if not fn.endswith(".json"):
            continue
        date_key = fn.replace(".json", "")
        fp = os.path.join(EIGHT_SLEEP_DIR, fn)
        try:
            with open(fp) as f:
                sd = json.load(f)
            score = sd.get("sleep_score") or sd.get("score") or sd.get("fitness_score")
            duration = sd.get("total_sleep_duration_hours") or sd.get("duration_hours")
            if score is not None:
                date_to_sleep[date_key] = {"score": score, "hours": duration}
        except Exception:
            pass

# ── Calculate Recovery Status Per Muscle Group ───────────────────────────────
today_str = today_ny.strftime("%Y-%m-%d")
yesterday_str = (today_ny - timedelta(days=1)).strftime("%Y-%m-%d")

hrv_values = []
for i in range(30):
    d = (today_ny - timedelta(days=i)).strftime("%Y-%m-%d")
    r = date_to_recovery.get(d, {})
    if r.get("hrv"):
        hrv_values.append(r["hrv"])

hrv_baseline = statistics.mean(hrv_values) if hrv_values else 50
hrv_std = statistics.stdev(hrv_values) if len(hrv_values) > 1 else 10

rec_values = []
for i in range(30):
    d = (today_ny - timedelta(days=i)).strftime("%Y-%m-%d")
    r = date_to_recovery.get(d, {})
    if r.get("recovery_score") is not None:
        rec_values.append(r["recovery_score"])
rec_baseline = statistics.mean(rec_values) if rec_values else 50

today_recovery = date_to_recovery.get(today_str) or date_to_recovery.get(yesterday_str) or {}
today_hrv = today_recovery.get("hrv") or hrv_baseline
today_rec_score = today_recovery.get("recovery_score") or rec_baseline

muscle_status = {}
for muscle in MUSCLE_GROUPS:
    last_trained_date = None
    last_volume = 0.0
    total_volume_7d = 0.0
    for i in range(30):
        d = (today_ny - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in daily_muscle_volume and muscle in daily_muscle_volume[d]:
            vol = daily_muscle_volume[d][muscle]
            if vol > 0:
                if last_trained_date is None:
                    last_trained_date = d
                    last_volume = vol
                if i < 7:
                    total_volume_7d += vol

    days_since = 999
    if last_trained_date:
        last_date_obj = datetime.strptime(last_trained_date, "%Y-%m-%d").date()
        days_since = (today_ny - last_date_obj).days

    hrv_factor = (today_hrv - hrv_baseline) / max(hrv_std, 1)
    if days_since == 999:
        time_recovery = 100
    elif days_since == 0:
        time_recovery = 0
    elif days_since == 1:
        time_recovery = 35
    elif days_since == 2:
        time_recovery = 65
    else:
        time_recovery = 90

    hrv_modifier = hrv_factor * 8
    final_score = min(100, max(0, time_recovery + hrv_modifier))

    if final_score >= 70:
        status = "green"
        status_label = "Ready"
    elif final_score >= 40:
        status = "yellow"
        status_label = "Moderate"
    else:
        status = "red"
        status_label = "Rest"

    muscle_status[muscle] = {
        "score": round(final_score),
        "status": status,
        "status_label": status_label,
        "last_trained": last_trained_date or "No data",
        "days_since": days_since if days_since < 999 else 30,
        "last_volume": round(last_volume),
        "volume_7d": round(total_volume_7d),
    }

# ── 7-Day Muscle Load Data ────────────────────────────────────────────────────
seven_days = []
for i in range(6, -1, -1):
    d = (today_ny - timedelta(days=i)).strftime("%Y-%m-%d")
    day_data = {"date": d, "label": (today_ny - timedelta(days=i)).strftime("%a")}
    for muscle in MUSCLE_GROUPS:
        day_data[muscle] = round(daily_muscle_volume[d].get(muscle, 0) / 1000, 1)
    day_data["total"] = round(sum(day_data[m] for m in MUSCLE_GROUPS), 1)
    seven_days.append(day_data)

max_day_vol = max((d["total"] for d in seven_days), default=1)
if max_day_vol == 0:
    max_day_vol = 1

# ── 30-Day Recovery Trend ─────────────────────────────────────────────────────
recovery_trend = []
for i in range(29, -1, -1):
    d = (today_ny - timedelta(days=i)).strftime("%Y-%m-%d")
    rec = date_to_recovery.get(d, {})
    vol = daily_volume.get(d, 0)
    recovery_trend.append({
        "date": d,
        "recovery": rec.get("recovery_score"),
        "hrv": rec.get("hrv"),
        "volume": vol,
        "label": datetime.strptime(d, "%Y-%m-%d").strftime("%b %d"),
    })

recent_vols = [d["volume"] for d in recovery_trend if d["volume"] > 0]
weekly_avg_vol = statistics.mean(recent_vols) if recent_vols else 1
heavy_threshold = weekly_avg_vol * 0.8

STATUS_COLORS = {
    "green": "#2ea043",
    "yellow": "#f39c12",
    "red": "#f85149",
}

def body_diagram_svg():
    W, H = 380, 580
    parts = []
    parts.append(f'<svg id="bodySvg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="display:block;margin:0 auto">')
    parts.append(f'<rect width="{W}" height="{H}" fill="#0d1117" rx="12"/>')
    # Body shapes
    parts.append('<ellipse cx="190" cy="55" rx="32" ry="38" fill="#21262d" stroke="#30363d" stroke-width="2"/>')
    parts.append('<rect x="178" y="87" width="24" height="22" fill="#21262d"/>')
    parts.append('<path d="M 125 115 L 255 115 L 272 325 L 215 330 L 190 315 L 165 330 L 108 325 Z" fill="#161b22" stroke="#30363d" stroke-width="2"/>')
    parts.append('<path d="M 125 118 Q 82 148 76 248 Q 74 275 84 280 Q 94 285 97 258 L 105 170 L 133 148 Z" fill="#161b22" stroke="#30363d" stroke-width="2"/>')
    parts.append('<path d="M 255 118 Q 298 148 304 248 Q 306 275 296 280 Q 286 285 283 258 L 275 170 L 247 148 Z" fill="#161b22" stroke="#30363d" stroke-width="2"/>')
    parts.append('<path d="M 148 326 L 125 326 L 114 472 Q 111 498 126 500 Q 141 502 144 478 L 152 395 Z" fill="#161b22" stroke="#30363d" stroke-width="2"/>')
    parts.append('<path d="M 232 326 L 255 326 L 266 472 Q 269 498 254 500 Q 239 502 236 478 L 228 395 Z" fill="#161b22" stroke="#30363d" stroke-width="2"/>')

    regions = {
        "Chest": [("ellipse", 148, 178, 36, 24), ("ellipse", 232, 178, 36, 24)],
        "Back": [("rect-c", 148, 138, 84, 70, 6)],
        "Shoulders": [("ellipse", 105, 148, 24, 18), ("ellipse", 275, 148, 24, 18)],
        "Biceps": [("ellipse", 90, 205, 16, 28), ("ellipse", 290, 205, 16, 28)],
        "Triceps": [("ellipse", 84, 210, 12, 24), ("ellipse", 296, 210, 12, 24)],
        "Core": [("rect-c", 155, 208, 70, 88, 6)],
        "Legs": [("ellipse", 160, 388, 36, 72), ("ellipse", 220, 388, 36, 72)],
    }

    label_pos = {
        "Chest": (190, 184), "Back": (190, 178), "Shoulders": (190, 118),
        "Biceps": None, "Triceps": None, "Core": (190, 255), "Legs": (190, 388),
    }

    for muscle, shapes in regions.items():
        status = muscle_status[muscle]["status"]
        color = STATUS_COLORS[status]
        ms = muscle_status[muscle]
        parts.append(f'<g class="muscle-region" data-muscle="{muscle}" style="cursor:pointer">')
        parts.append(f'<title>{muscle}: {ms["status_label"]} ({ms["score"]}%) | Last: {ms["last_trained"]} ({ms["days_since"]}d ago) | Vol: {ms["last_volume"]:,} lbs</title>')
        for shape in shapes:
            if shape[0] == "ellipse":
                _, cx, cy, rx, ry = shape
                parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{color}" fill-opacity="0.75" stroke="{color}" stroke-width="1.5"/>')
            elif shape[0] == "rect-c":
                _, x, y, w, h, r = shape
                parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{color}" fill-opacity="0.75" stroke="{color}" stroke-width="1.5"/>')
        parts.append('</g>')

    for muscle, pos in label_pos.items():
        if pos:
            sc = muscle_status[muscle]["score"]
            parts.append(f'<text x="{pos[0]}" y="{pos[1]}" text-anchor="middle" fill="white" font-size="10" font-weight="bold" pointer-events="none">{muscle} {sc}%</text>')

    parts.append('</svg>')
    return "\n".join(parts)

def muscle_load_svg():
    W, H = 760, 210
    ml, mr, mt, mb = 55, 20, 20, 38
    cw = W - ml - mr
    ch = H - mt - mb

    parts = [f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-width:{W}px;background:#161b22;border-radius:8px">']

    muscle_colors = {
        "Chest": "#58a6ff", "Back": "#3fb950", "Shoulders": "#f39c12",
        "Biceps": "#d2a8ff", "Triceps": "#ff7b72", "Legs": "#79c0ff", "Core": "#ffa657",
    }

    n = len(seven_days)
    bw = (cw / n) * 0.65
    bg = (cw / n) * 0.35

    for i, day in enumerate(seven_days):
        x = ml + i * (cw / n) + bg / 2
        y_off = mt + ch
        for muscle in MUSCLE_GROUPS:
            vk = day.get(muscle, 0)
            if vk <= 0:
                continue
            sh = (vk / max_day_vol) * ch
            y_off -= sh
            c = muscle_colors[muscle]
            parts.append(f'<rect x="{x:.1f}" y="{y_off:.1f}" width="{bw:.1f}" height="{sh:.1f}" fill="{c}" fill-opacity="0.85"><title>{day["label"]}: {muscle} {vk:.1f}K lbs</title></rect>')

        lx = x + bw / 2
        parts.append(f'<text x="{lx:.1f}" y="{mt+ch+16:.1f}" text-anchor="middle" fill="#8b949e" font-size="11">{day["label"]}</text>')
        if day["total"] > 0:
            parts.append(f'<text x="{lx:.1f}" y="{y_off-4:.1f}" text-anchor="middle" fill="#e6edf3" font-size="9">{day["total"]:.0f}K</text>')

    for pct in [0, 0.5, 1.0]:
        y = mt + ch - pct * ch
        val = pct * max_day_vol
        parts.append(f'<text x="{ml-5}" y="{y+4:.1f}" text-anchor="end" fill="#8b949e" font-size="10">{val:.0f}K</text>')
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" stroke="#30363d" stroke-width="0.5"/>')

    # Legend
    for i, muscle in enumerate(MUSCLE_GROUPS):
        lx = ml + i * (cw / len(MUSCLE_GROUPS))
        parts.append(f'<rect x="{lx:.0f}" y="5" width="9" height="9" fill="{muscle_colors[muscle]}" rx="2"/>')
        parts.append(f'<text x="{lx+12:.0f}" y="13" fill="#8b949e" font-size="9">{muscle}</text>')

    parts.append('</svg>')
    return "\n".join(parts)

def recovery_trend_svg():
    W, H = 760, 250
    ml, mr, mt, mb = 48, 20, 20, 38
    cw = W - ml - mr
    ch = H - mt - mb

    valid = [(i, d) for i, d in enumerate(recovery_trend) if d["recovery"] is not None]
    parts = [f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-width:{W}px;background:#161b22;border-radius:8px">']

    if not valid:
        parts.append(f'<text x="{W//2}" y="{H//2}" text-anchor="middle" fill="#8b949e" font-size="14">No recovery data</text>')
        parts.append('</svg>')
        return "\n".join(parts)

    n = len(recovery_trend)

    for pct in [0, 0.25, 0.5, 0.75, 1.0]:
        y = mt + ch - pct * ch
        parts.append(f'<text x="{ml-5}" y="{y+4:.1f}" text-anchor="end" fill="#8b949e" font-size="10">{int(pct*100)}%</text>')
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" stroke="#30363d" stroke-width="0.5"/>')

    # Heavy day markers
    for i, d in enumerate(recovery_trend):
        if d["volume"] >= heavy_threshold:
            x = ml + (i / max(n-1, 1)) * cw
            parts.append(f'<line x1="{x:.1f}" y1="{mt:.1f}" x2="{x:.1f}" y2="{mt+ch:.1f}" stroke="#f39c12" stroke-width="1" stroke-opacity="0.25"/>')

    # Recovery polyline
    pts = []
    for i, d in valid:
        x = ml + (i / max(n-1, 1)) * cw
        y = mt + ch - (d["recovery"] / 100) * ch
        pts.append(f"{x:.1f},{y:.1f}")
    if len(pts) > 1:
        parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#58a6ff" stroke-width="2" stroke-linejoin="round"/>')

    for i, d in valid:
        x = ml + (i / max(n-1, 1)) * cw
        y = mt + ch - (d["recovery"] / 100) * ch
        col = "#2ea043" if d["recovery"] >= 67 else ("#f39c12" if d["recovery"] >= 34 else "#f85149")
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{col}"><title>{d["label"]}: {d["recovery"]:.0f}%</title></circle>')

    # Baseline
    yb = mt + ch - (rec_baseline / 100) * ch
    parts.append(f'<line x1="{ml}" y1="{yb:.1f}" x2="{W-mr}" y2="{yb:.1f}" stroke="#f39c12" stroke-width="1" stroke-dasharray="4,3"/>')
    parts.append(f'<text x="{W-mr-4}" y="{yb-4:.1f}" text-anchor="end" fill="#f39c12" font-size="10">Avg {rec_baseline:.0f}%</text>')

    # X labels every 5 days
    for i, d in enumerate(recovery_trend):
        if i % 5 == 0:
            x = ml + (i / max(n-1, 1)) * cw
            lbl = datetime.strptime(d["date"], "%Y-%m-%d").strftime("%b %d")
            parts.append(f'<text x="{x:.1f}" y="{mt+ch+16:.1f}" text-anchor="middle" fill="#8b949e" font-size="10">{lbl}</text>')

    parts.append(f'<circle cx="{ml+10}" cy="11" r="4" fill="#58a6ff"/>')
    parts.append(f'<text x="{ml+18}" y="15" fill="#8b949e" font-size="10">Recovery Score</text>')
    parts.append(f'<line x1="{ml+108}" y1="11" x2="{ml+118}" y2="11" stroke="#f39c12" stroke-width="1.5" stroke-dasharray="3,2"/>')
    parts.append(f'<text x="{ml+122}" y="15" fill="#8b949e" font-size="10">30d Average</text>')
    parts.append('</svg>')
    return "\n".join(parts)

# ── Recommendations ───────────────────────────────────────────────────────────
train_today = [m for m in MUSCLE_GROUPS if muscle_status[m]["status"] == "green"]
train_tomorrow = [m for m in MUSCLE_GROUPS if muscle_status[m]["status"] == "yellow"]
rest_muscles = [m for m in MUSCLE_GROUPS if muscle_status[m]["status"] == "red"]
needs_rest = len(rest_muscles) >= len(MUSCLE_GROUPS) * 0.5

body_svg = body_diagram_svg()
load_svg = muscle_load_svg()
trend_svg = recovery_trend_svg()

today_sleep = date_to_sleep.get(today_str) or date_to_sleep.get(yesterday_str) or {}

rec_color = "green-text" if today_rec_score >= 67 else ("yellow-text" if today_rec_score >= 34 else "red-text")
rdy_color = "green-text" if len(train_today) >= 4 else ("yellow-text" if len(train_today) >= 2 else "red-text")
sleep_stat = f"<div class='stat'><div class='stat-val blue-text'>{today_sleep.get('score','—')}</div><div class='stat-lbl'>Sleep Score</div></div>" if today_sleep.get('score') else ""
rest_alert = "<div style='background:#f8514922;border:1px solid #f85149;border-radius:8px;padding:12px 16px;margin-bottom:16px;color:#f85149;font-weight:600'>⚠️ Recovery Alert: More than half your muscle groups need rest. Consider active recovery or a rest day today.</div>" if needs_rest else ""

muscle_cards = ""
for muscle in MUSCLE_GROUPS:
    ms = muscle_status[muscle]
    st = ms["status"]
    ds = ms["days_since"]
    ds_str = "Today" if ds == 0 else (f"{ds}d ago" if ds < 30 else "30d+")
    muscle_cards += f"""
        <div class="muscle-card {st}">
          <div class="muscle-name">{muscle}<span class="badge {st}">{ms['status_label']} {ms['score']}%</span></div>
          <div class="muscle-meta">Last: {ms['last_trained']} &nbsp;|&nbsp; {ds_str} &nbsp;|&nbsp; Last vol: {ms['last_volume']:,} lbs &nbsp;|&nbsp; 7d vol: {ms['volume_7d']:,} lbs</div>
        </div>"""

train_items = "".join(f'<span class="reco-item" style="border:1px solid #2ea04344;color:#2ea043">{m}</span>' for m in train_today) or '<span style="color:#8b949e;font-size:13px">No fully recovered muscles</span>'
tmrw_items = "".join(f'<span class="reco-item" style="border:1px solid #f39c1244;color:#f39c12">{m}</span>' for m in train_tomorrow) or '<span style="color:#8b949e;font-size:13px">None</span>'
rest_items = "".join(f'<span class="reco-item" style="border:1px solid #f8514944;color:#f85149">{m}</span>' for m in rest_muscles) or "<span style=\"color:#8b949e;font-size:13px\">None — you're fully recovered!</span>"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Muscle Recovery Map</title>
<style>
*,*::before,*::after{{box-sizing:border-box}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh;margin:0}}
nav{{background:#161b22;border-bottom:1px solid #30363d;padding:12px 24px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
nav a{{color:#8b949e;text-decoration:none;padding:6px 12px;border-radius:6px;font-size:14px;font-weight:500;transition:all .15s}}
nav a:hover{{background:#21262d;color:#e6edf3}}
nav a.active{{background:#f39c12;color:#000;font-weight:600}}
.container{{max-width:1200px;margin:0 auto;padding:24px}}
h1{{font-size:24px;font-weight:700;margin:0 0 4px}}
.subtitle{{color:#8b949e;font-size:14px;margin:0 0 24px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:20px}}
h2{{font-size:18px;font-weight:600;margin:0 0 16px;color:#e6edf3}}
h3{{font-size:14px;font-weight:600;margin:0 0 10px;color:#8b949e}}
.grid-2{{display:grid;grid-template-columns:380px 1fr;gap:24px}}
@media(max-width:768px){{.grid-2{{grid-template-columns:1fr}}}}
.muscle-legend{{display:flex;flex-direction:column;gap:10px;overflow-y:auto}}
.muscle-card{{background:#0d1117;border-radius:8px;padding:11px 14px;border-left:4px solid}}
.muscle-card.green{{border-color:#2ea043}}
.muscle-card.yellow{{border-color:#f39c12}}
.muscle-card.red{{border-color:#f85149}}
.muscle-name{{font-weight:600;font-size:14px;display:flex;align-items:center;justify-content:space-between;gap:8px}}
.muscle-meta{{font-size:11px;color:#8b949e;margin-top:4px}}
.badge{{display:inline-block;border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600;white-space:nowrap}}
.badge.green{{background:#2ea04322;color:#2ea043}}
.badge.yellow{{background:#f39c1222;color:#f39c12}}
.badge.red{{background:#f8514922;color:#f85149}}
.reco-section{{display:flex;gap:14px;flex-wrap:wrap}}
.reco-col{{flex:1;min-width:160px;background:#0d1117;border-radius:8px;padding:14px}}
.reco-item{{display:inline-block;background:#21262d;border-radius:5px;padding:3px 9px;margin:3px;font-size:12px}}
.stats-row{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
.stat{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:110px;text-align:center}}
.stat-val{{font-size:24px;font-weight:700}}
.stat-lbl{{font-size:11px;color:#8b949e;margin-top:2px}}
.green-text{{color:#2ea043}}
.yellow-text{{color:#f39c12}}
.red-text{{color:#f85149}}
.blue-text{{color:#58a6ff}}
.muscle-region{{transition:opacity .15s}}
.muscle-region:hover{{opacity:.75}}
</style>
</head>
<body>
<nav>
  <a href="../index.html">🏠 Home</a>
  <a href="../hub_index.html">📊 Hub</a>
  <a href="../calendars/2026-02-calendar.html">📅 Calendar</a>
  <a href="../strength/index.html">💪 Strength</a>
  <a href="../cardio/index.html">🏃 Cardio</a>
  <a href="../recovery/index.html">💤 Recovery</a>
  <a href="../nutrition/index.html">🥗 Nutrition</a>
  <a href="index.html" class="active">🗺️ Muscle Map</a>
  <a href="../exercises/index.html">🏋️ Exercises</a>
  <a href="../training_load/index.html">📈 Load</a>
</nav>
<div class="container">
  <h1>🗺️ Muscle Recovery Map</h1>
  <p class="subtitle">Generated {datetime.now(NY_TZ).strftime("%A, %B %d %Y at %I:%M %p")} ET &nbsp;·&nbsp; Data via Tonal + WHOOP + 8Sleep</p>

  <div class="stats-row">
    <div class="stat"><div class="stat-val {rec_color}">{today_rec_score:.0f}%</div><div class="stat-lbl">WHOOP Recovery</div></div>
    <div class="stat"><div class="stat-val blue-text">{today_hrv:.1f} ms</div><div class="stat-lbl">HRV (RMSSD)</div></div>
    <div class="stat"><div class="stat-val {rdy_color}">{len(train_today)}/{len(MUSCLE_GROUPS)}</div><div class="stat-lbl">Muscles Ready</div></div>
    {sleep_stat}
    <div class="stat"><div class="stat-val yellow-text">{hrv_baseline:.1f} ms</div><div class="stat-lbl">HRV 30d Baseline</div></div>
  </div>

  <div class="card">
    <h2>Today's Muscle Recovery Status</h2>
    <div class="grid-2">
      <div>{body_svg}</div>
      <div class="muscle-legend">{muscle_cards}</div>
    </div>
  </div>

  <div class="card">
    <h2>Training Recommendations</h2>
    {rest_alert}
    <div class="reco-section">
      <div class="reco-col"><h3>✅ Train Today (Ready)</h3>{train_items}</div>
      <div class="reco-col"><h3>🟡 Maybe Tomorrow</h3>{tmrw_items}</div>
      <div class="reco-col"><h3>🔴 Rest / Active Recovery</h3>{rest_items}</div>
    </div>
  </div>

  <div class="card">
    <h2>7-Day Muscle Load Timeline</h2>
    <p style="color:#8b949e;font-size:13px;margin:0 0 12px">Volume in thousands of lbs per muscle group per day (stacked bars)</p>
    {load_svg}
  </div>

  <div class="card">
    <h2>30-Day Recovery Score Trend</h2>
    <p style="color:#8b949e;font-size:13px;margin:0 0 12px">WHOOP recovery score. Vertical orange lines = heavy training days (&gt;80% of recent avg volume).</p>
    {trend_svg}
  </div>
</div>
</body>
</html>"""

with open(OUTPUT_FILE, "w") as f:
    f.write(html)

print(f"Generated: {OUTPUT_FILE}")
print(f"File size: {os.path.getsize(OUTPUT_FILE):,} bytes")
