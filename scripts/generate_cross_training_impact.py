#!/usr/bin/env python3
"""Cross-Training Impact Analysis generator."""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/tobyglennpeters/clawd")
OUT_DIR = BASE / "docs" / "cross_training_impact"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TONAL_FILE   = BASE / "data/tonal/tonal_workouts_20260225_214518.json"
GARMIN_FILE  = BASE / "data/garmin_all_activities.json"
WHOOP_FILE   = BASE / "data/whoop_v2_latest.json"
EIGHT_FILE   = BASE / "data/eight_sleep_historical.csv"

def parse_utc_to_et(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        et = dt - timedelta(hours=5)
        return et.strftime("%Y-%m-%d")
    except Exception:
        return ts_str[:10] if ts_str else None

with open(TONAL_FILE) as f:
    tonal_raw = json.load(f)
tonal_workouts = tonal_raw["workouts"]

with open(GARMIN_FILE) as f:
    garmin_raw = json.load(f)
garmin_acts = garmin_raw["activities"]

with open(WHOOP_FILE) as f:
    whoop_raw = json.load(f)
whoop_records = whoop_raw["recovery"]["records"]

with open(EIGHT_FILE) as f:
    eight_records = json.load(f)

daily = defaultdict(lambda: {
    "tonal_volume": 0, "tonal_sessions": 0,
    "run_miles": 0.0, "run_count": 0, "run_avg_hr": None, "_run_hr_sum": 0, "_run_hr_count": 0,
    "recovery_score": None, "hrv": None, "rhr": None,
    "sleep_score": None,
})

for w in tonal_workouts:
    if not w.get("completed"):
        continue
    d = parse_utc_to_et(w.get("beginTime", ""))
    if not d:
        continue
    vol = w.get("totalVolume", 0) or 0
    daily[d]["tonal_volume"] += vol
    daily[d]["tonal_sessions"] += 1

for a in garmin_acts:
    d = str(a.get("date", a.get("startTimeLocal", "")))[:10]
    if not d:
        continue
    miles = a.get("distance_miles", 0) or 0
    hr = a.get("averageHR")
    daily[d]["run_miles"] += miles
    daily[d]["run_count"] += 1
    if hr:
        daily[d]["_run_hr_sum"] += hr
        daily[d]["_run_hr_count"] += 1

for r in whoop_records:
    d = r.get("created_at", "")[:10]
    score = r.get("score")
    if score and d:
        daily[d]["recovery_score"] = score.get("recovery_score")
        daily[d]["hrv"] = score.get("hrv_rmssd_milli")
        daily[d]["rhr"] = score.get("resting_heart_rate")

for r in eight_records:
    d = r.get("date", "")
    if d:
        daily[d]["sleep_score"] = r.get("sleep_score")

for d, v in daily.items():
    if v["_run_hr_count"] > 0:
        v["run_avg_hr"] = v["_run_hr_sum"] / v["_run_hr_count"]

all_dates = sorted(daily.keys())

def tonal_intensity(vol):
    if vol == 0: return "None"
    if vol < 5000: return "Light"
    if vol < 10000: return "Medium"
    return "Heavy"

pairs = []
for i, d in enumerate(all_dates[:-1]):
    nd = all_dates[i+1]
    try:
        d_dt = datetime.strptime(d, "%Y-%m-%d")
        nd_dt = datetime.strptime(nd, "%Y-%m-%d")
        if (nd_dt - d_dt).days != 1:
            continue
    except:
        continue
    pairs.append((d, nd))

all_recovery = [daily[d]["recovery_score"] for d in all_dates if daily[d]["recovery_score"] is not None]
all_hrv = [daily[d]["hrv"] for d in all_dates if daily[d]["hrv"] is not None]
all_tonal_vol = [daily[d]["tonal_volume"] for d in all_dates if daily[d]["tonal_volume"] > 0]

baseline_recovery = sum(all_recovery) / len(all_recovery) if all_recovery else 70
baseline_hrv = sum(all_hrv) / len(all_hrv) if all_hrv else 30
baseline_vol = sum(all_tonal_vol) / len(all_tonal_vol) if all_tonal_vol else 5000

matrix_data = {intensity: {"Recovery": [], "HRV": [], "RHR": [], "Tonal Volume": []}
               for intensity in ["None", "Light", "Medium", "Heavy"]}

for d, nd in pairs:
    intensity = tonal_intensity(daily[d]["tonal_volume"])
    nd_rec = daily[nd]["recovery_score"]
    nd_hrv = daily[nd]["hrv"]
    nd_rhr = daily[nd]["rhr"]
    nd_vol = daily[nd]["tonal_volume"]
    if nd_rec is not None: matrix_data[intensity]["Recovery"].append(nd_rec)
    if nd_hrv is not None: matrix_data[intensity]["HRV"].append(nd_hrv)
    if nd_rhr is not None: matrix_data[intensity]["RHR"].append(nd_rhr)
    if nd_vol > 0: matrix_data[intensity]["Tonal Volume"].append(nd_vol)

def avg(lst): return sum(lst)/len(lst) if lst else None
def pct_change(val, base):
    if val is None or base == 0: return None
    return ((val - base) / base) * 100

matrix_pct = {}
for intensity in ["None", "Light", "Medium", "Heavy"]:
    matrix_pct[intensity] = {}
    for metric in ["Recovery", "HRV", "RHR", "Tonal Volume"]:
        vals = matrix_data[intensity][metric]
        a = avg(vals)
        if metric == "Recovery": base = baseline_recovery
        elif metric == "HRV": base = baseline_hrv
        elif metric == "RHR": base = 65
        else: base = baseline_vol
        p = pct_change(a, base)
        matrix_pct[intensity][metric] = round(p, 1) if p is not None else 0

run_vs_recovery = []
run_vs_tonal = []
for d, nd in pairs:
    miles = daily[d]["run_miles"]
    hr = daily[d]["run_avg_hr"]
    nd_rec = daily[nd]["recovery_score"]
    nd_vol = daily[nd]["tonal_volume"]
    if miles > 0 and nd_rec is not None:
        run_vs_recovery.append((miles, nd_rec, d))
    if hr is not None and nd_vol > 0:
        run_vs_tonal.append((hr, nd_vol, d))

dow_data = defaultdict(lambda: {"tonal_vol": [], "run_miles": [], "next_recovery": []})
dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
for d, nd in pairs:
    try:
        dow = datetime.strptime(d, "%Y-%m-%d").weekday()
    except: continue
    dow_data[dow]["tonal_vol"].append(daily[d]["tonal_volume"])
    dow_data[dow]["run_miles"].append(daily[d]["run_miles"])
    nd_rec = daily[nd]["recovery_score"]
    if nd_rec is not None:
        dow_data[dow]["next_recovery"].append(nd_rec)

dow_summary = []
for i in range(7):
    v = dow_data[i]
    dow_summary.append({
        "name": dow_names[i],
        "avg_tonal": avg(v["tonal_vol"]) or 0,
        "avg_run": avg(v["run_miles"]) or 0,
        "avg_recovery": avg(v["next_recovery"]),
    })

after_tonal_pairs = [(d, nd) for d, nd in pairs if daily[d]["tonal_volume"] > 0]
after_run_pairs = [(d, nd) for d, nd in pairs if daily[d]["run_miles"] > 0]
after_tonal_recovery = [daily[nd]["recovery_score"] for _, nd in after_tonal_pairs if daily[nd]["recovery_score"] is not None]
after_run_tonal_vol = [daily[nd]["tonal_volume"] for _, nd in after_run_pairs if daily[nd]["tonal_volume"] > 0]

stat_tonal_recovery_pct = pct_change(avg(after_tonal_recovery), baseline_recovery)
stat_run_tonal_pct = pct_change(avg(after_run_tonal_vol), baseline_vol)

best_dow = max(range(7), key=lambda i: dow_summary[i]["avg_recovery"] or 0)
best_dow_name = dow_names[best_dow]

heavy_run_pairs = [(d, nd) for d, nd in pairs if daily[d]["tonal_volume"] >= 10000 and daily[d]["run_miles"] > 2]
heavy_run_recovery = [daily[nd]["recovery_score"] for _, nd in heavy_run_pairs if daily[nd]["recovery_score"] is not None]
hardest_combo_rec = avg(heavy_run_recovery)
hardest_pct = pct_change(hardest_combo_rec, baseline_recovery)

def linreg(points):
    n = len(points)
    if n < 2: return 0, 0
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sx2 = sum(p[0]**2 for p in points)
    sxy = sum(p[0]*p[1] for p in points)
    denom = n*sx2 - sx**2
    if denom == 0: return 0, sy/n
    slope = (n*sxy - sx*sy) / denom
    intercept = (sy - slope*sx) / n
    return slope, intercept

def color_for_pct(pct):
    if pct is None: return "#555"
    clamped = max(-25, min(25, pct))
    if clamped >= 0:
        t = clamped / 25
        r = int(13 + (46 - 13)*t)
        g = int(17 + (160 - 17)*t)
        b = int(23 + (67 - 23)*t)
        return f"rgb({r},{g},{b})"
    else:
        t = abs(clamped) / 25
        r = int(13 + (248 - 13)*t)
        g = int(17 + (81 - 17)*t)
        b = int(23 + (73 - 23)*t)
        return f"rgb({r},{g},{b})"

def svg_impact_matrix():
    w, h = 520, 380
    rows = ["None", "Light", "Medium", "Heavy"]
    cols = ["Recovery", "HRV", "RHR", "Tonal Volume"]
    margin = {"top": 60, "left": 90, "right": 20, "bottom": 20}
    cw = (w - margin["left"] - margin["right"]) / len(cols)
    ch = (h - margin["top"] - margin["bottom"]) / len(rows)
    svg = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<rect width="{w}" height="{h}" fill="#161b22" rx="8"/>')
    for ci, col in enumerate(cols):
        x = margin["left"] + ci*cw + cw/2
        svg.append(f'<text x="{x}" y="30" text-anchor="middle" fill="#8b949e" font-size="11" font-family="monospace">{col}</text>')
    for ri, row in enumerate(rows):
        y = margin["top"] + ri*ch
        svg.append(f'<text x="{margin["left"]-8}" y="{y+ch/2+4}" text-anchor="end" fill="#e6edf3" font-size="12" font-family="monospace">{row}</text>')
        for ci, col in enumerate(cols):
            x = margin["left"] + ci*cw
            pct = matrix_pct[row][col]
            fill = color_for_pct(pct)
            sign = "+" if pct > 0 else ""
            text_fill = "#e6edf3" if abs(pct) > 8 else "#8b949e"
            svg.append(f'<rect x="{x+2}" y="{y+2}" width="{cw-4}" height="{ch-4}" fill="{fill}" rx="4"/>')
            svg.append(f'<text x="{x+cw/2}" y="{y+ch/2+4}" text-anchor="middle" fill="{text_fill}" font-size="12" font-weight="bold" font-family="monospace">{sign}{pct}%</text>')
    legend_x = margin["left"]
    legend_y = h - 14
    for i, (label, color) in enumerate([("Negative", "#f85149"), ("Neutral", "#555"), ("Positive", "#2ea043")]):
        lx = legend_x + i * 120
        svg.append(f'<rect x="{lx}" y="{legend_y-8}" width="12" height="12" fill="{color}" rx="2"/>')
        svg.append(f'<text x="{lx+16}" y="{legend_y+2}" fill="#8b949e" font-size="10" font-family="monospace">{label}</text>')
    svg.append('</svg>')
    return "\n".join(svg)

def svg_scatter(points, xlabel, ylabel, title, xunit="", yunit=""):
    w, h = 400, 300
    margin = {"top": 30, "left": 55, "right": 20, "bottom": 45}
    pw = w - margin["left"] - margin["right"]
    ph = h - margin["top"] - margin["bottom"]
    if not points:
        return f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg"><rect width="{w}" height="{h}" fill="#161b22" rx="8"/><text x="{w//2}" y="{h//2}" text-anchor="middle" fill="#8b949e" font-size="14" font-family="monospace">No data</text></svg>'
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xrange = xmax - xmin or 1
    yrange = ymax - ymin or 1
    def px(x): return margin["left"] + (x - xmin) / xrange * pw
    def py(y): return margin["top"] + ph - (y - ymin) / yrange * ph
    svg = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<rect width="{w}" height="{h}" fill="#161b22" rx="8"/>')
    svg.append(f'<text x="{w//2}" y="18" text-anchor="middle" fill="#e6edf3" font-size="11" font-family="monospace">{title}</text>')
    ax1, ay1 = margin["left"], margin["top"]
    ax2, ay2 = margin["left"]+pw, margin["top"]+ph
    svg.append(f'<line x1="{ax1}" y1="{ay1}" x2="{ax1}" y2="{ay2}" stroke="#30363d" stroke-width="1"/>')
    svg.append(f'<line x1="{ax1}" y1="{ay2}" x2="{ax2}" y2="{ay2}" stroke="#30363d" stroke-width="1"/>')
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        xv = xmin + tick*xrange
        yv = ymin + tick*yrange
        tx, ty = px(xv), py(yv)
        svg.append(f'<line x1="{tx}" y1="{ay2}" x2="{tx}" y2="{ay2+4}" stroke="#30363d"/>')
        svg.append(f'<text x="{tx}" y="{ay2+14}" text-anchor="middle" fill="#8b949e" font-size="9" font-family="monospace">{xv:.1f}</text>')
        svg.append(f'<line x1="{ax1-4}" y1="{ty}" x2="{ax1}" y2="{ty}" stroke="#30363d"/>')
        svg.append(f'<text x="{ax1-6}" y="{ty+3}" text-anchor="end" fill="#8b949e" font-size="9" font-family="monospace">{yv:.0f}</text>')
    svg.append(f'<text x="{margin["left"]+pw//2}" y="{h-5}" text-anchor="middle" fill="#8b949e" font-size="10" font-family="monospace">{xlabel} {xunit}</text>')
    svg.append(f'<text x="10" y="{margin["top"]+ph//2}" text-anchor="middle" fill="#8b949e" font-size="10" font-family="monospace" transform="rotate(-90,10,{margin["top"]+ph//2})">{ylabel} {yunit}</text>')
    slope, intercept = linreg([(p[0], p[1]) for p in points])
    tx1, ty1 = px(xmin), py(slope*xmin + intercept)
    tx2, ty2 = px(xmax), py(slope*xmax + intercept)
    svg.append(f'<line x1="{tx1}" y1="{ty1}" x2="{tx2}" y2="{ty2}" stroke="#0a84ff" stroke-width="2" stroke-dasharray="4,3" opacity="0.8"/>')
    for p in points:
        cx, cy = px(p[0]), py(p[1])
        label = p[2] if len(p) > 2 else ""
        svg.append(f'<circle cx="{cx}" cy="{cy}" r="5" fill="#f39c12" opacity="0.75"><title>{label}: {xlabel}={p[0]:.1f}{xunit}, {ylabel}={p[1]:.0f}{yunit}</title></circle>')
    svg.append('</svg>')
    return "\n".join(svg)

def svg_dow_bar():
    w, h = 700, 350
    margin = {"top": 30, "left": 55, "right": 55, "bottom": 50}
    pw = w - margin["left"] - margin["right"]
    ph = h - margin["top"] - margin["bottom"]
    n = 7
    bar_w = pw / n
    max_tonal = max((d["avg_tonal"] for d in dow_summary), default=1) or 1
    max_run = max((d["avg_run"] for d in dow_summary), default=1) or 1
    max_combined = max(max_tonal / 1000, max_run * 10) or 1
    svg = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<rect width="{w}" height="{h}" fill="#161b22" rx="8"/>')
    for tick in [0.25, 0.5, 0.75, 1.0]:
        gy = margin["top"] + ph - tick*ph
        svg.append(f'<line x1="{margin["left"]}" y1="{gy}" x2="{margin["left"]+pw}" y2="{gy}" stroke="#21262d" stroke-width="1"/>')
    for i, d in enumerate(dow_summary):
        bx = margin["left"] + i * bar_w
        by = margin["top"] + ph
        tonal_h = (d["avg_tonal"] / 1000 / max_combined) * ph if max_combined > 0 else 0
        run_h = (d["avg_run"] * 10 / max_combined) * ph if max_combined > 0 else 0
        if tonal_h > 0:
            svg.append(f'<rect x="{bx+4}" y="{by-tonal_h}" width="{bar_w-8}" height="{tonal_h}" fill="#f39c12" rx="2" opacity="0.85"><title>Avg Tonal: {d["avg_tonal"]/1000:.1f}k lbs</title></rect>')
        if run_h > 0:
            svg.append(f'<rect x="{bx+4}" y="{by-tonal_h-run_h}" width="{bar_w-8}" height="{run_h}" fill="#0a84ff" rx="2" opacity="0.85"><title>Avg Run: {d["avg_run"]:.1f} mi</title></rect>')
        svg.append(f'<text x="{bx+bar_w/2}" y="{by+16}" text-anchor="middle" fill="#e6edf3" font-size="11" font-family="monospace">{d["name"]}</text>')
    rec_vals = [d["avg_recovery"] for d in dow_summary]
    valid_rec = [(i, v) for i, v in enumerate(rec_vals) if v is not None]
    if valid_rec:
        rec_min = min(v for _, v in valid_rec)
        rec_max = max(v for _, v in valid_rec)
        rec_range = rec_max - rec_min or 1
        def rec_y(v): return margin["top"] + ph - ((v - rec_min) / rec_range) * ph * 0.6 - ph*0.2
        pts = [(margin["left"] + i*bar_w + bar_w/2, rec_y(v)) for i, v in valid_rec]
        if len(pts) >= 2:
            path = f"M {pts[0][0]},{pts[0][1]} " + " ".join(f"L {x},{y}" for x, y in pts[1:])
            svg.append(f'<path d="{path}" stroke="#2ea043" stroke-width="2" fill="none"/>')
        for x, y in pts:
            svg.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#2ea043"/>')
        svg.append(f'<text x="{w-10}" y="{margin["top"]+ph//2}" text-anchor="middle" fill="#2ea043" font-size="10" font-family="monospace" transform="rotate(90,{w-10},{margin["top"]+ph//2})">Recovery Score</text>')
    leg_items = [("#f39c12", "Tonal Volume"), ("#0a84ff", "Run Miles"), ("#2ea043", "Next-Day Recovery")]
    for idx, (color, label) in enumerate(leg_items):
        lx = margin["left"] + idx * 180
        svg.append(f'<rect x="{lx}" y="{h-18}" width="12" height="12" fill="{color}" rx="2"/>')
        svg.append(f'<text x="{lx+16}" y="{h-6}" fill="#8b949e" font-size="10" font-family="monospace">{label}</text>')
    svg.append('</svg>')
    return "\n".join(svg)

combos = []
lt_nr = [(d, nd) for d, nd in pairs if tonal_intensity(daily[d]["tonal_volume"]) == "Light" and daily[d]["run_miles"] == 0]
lt_nr_rec = avg([daily[nd]["recovery_score"] for _, nd in lt_nr if daily[nd]["recovery_score"] is not None])
combos.append(("Light Tonal + No Run", lt_nr_rec, pct_change(lt_nr_rec, baseline_recovery), len(lt_nr)))
nt = [(d, nd) for d, nd in pairs if daily[d]["tonal_volume"] == 0 and daily[d]["run_miles"] == 0]
nt_rec = avg([daily[nd]["recovery_score"] for _, nd in nt if daily[nd]["recovery_score"] is not None])
combos.append(("Rest Day (no training)", nt_rec, pct_change(nt_rec, baseline_recovery), len(nt)))
mt_nr = [(d, nd) for d, nd in pairs if tonal_intensity(daily[d]["tonal_volume"]) == "Medium" and daily[d]["run_miles"] == 0]
mt_nr_rec = avg([daily[nd]["recovery_score"] for _, nd in mt_nr if daily[nd]["recovery_score"] is not None])
combos.append(("Medium Tonal + No Run", mt_nr_rec, pct_change(mt_nr_rec, baseline_recovery), len(mt_nr)))
rh = [(d, nd) for d, nd in pairs if tonal_intensity(daily[d]["tonal_volume"]) == "Heavy" and daily[d]["run_miles"] > 0]
rh_rec = avg([daily[nd]["recovery_score"] for _, nd in rh if daily[nd]["recovery_score"] is not None])
combos.append(("Heavy Tonal + Run", rh_rec, pct_change(rh_rec, baseline_recovery), len(rh)))
ro = [(d, nd) for d, nd in pairs if daily[d]["run_miles"] > 0 and daily[d]["tonal_volume"] == 0]
ro_rec = avg([daily[nd]["recovery_score"] for _, nd in ro if daily[nd]["recovery_score"] is not None])
combos.append(("Run Only (no Tonal)", ro_rec, pct_change(ro_rec, baseline_recovery), len(ro)))
combos = [(c, r, p, n) for c, r, p, n in combos if r is not None and n >= 2]
combos.sort(key=lambda x: x[2] or 0, reverse=True)

NAV = """<nav style="background:#161b22;border-bottom:1px solid #30363d;padding:12px 24px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;font-family:monospace;font-size:13px;">
  <a href="../index.html" style="color:#f39c12;text-decoration:none;font-weight:bold;">Home</a>
  <a href="../strength/index.html" style="color:#8b949e;text-decoration:none;">Strength</a>
  <a href="../cardio/index.html" style="color:#8b949e;text-decoration:none;">Cardio</a>
  <a href="../recovery/index.html" style="color:#8b949e;text-decoration:none;">Recovery</a>
  <a href="../velocity/index.html" style="color:#8b949e;text-decoration:none;">Velocity</a>
  <a href="../running/index.html" style="color:#8b949e;text-decoration:none;">Running</a>
  <a href="../muscle_groups/index.html" style="color:#8b949e;text-decoration:none;">Muscles</a>
  <a href="../sleep_dashboard.html" style="color:#8b949e;text-decoration:none;">Sleep</a>
  <span style="color:#f39c12;margin-left:auto;">Cross-Training Impact</span>
</nav>"""

def fmt_pct(p):
    if p is None: return "N/A"
    sign = "+" if p >= 0 else ""
    return f"{sign}{p:.1f}%"

def pct_color(p):
    if p is None: return "#8b949e"
    return "#2ea043" if p >= 0 else "#f85149"

stat_cards = [
    ("After Tonal - Next-Day Recovery", fmt_pct(stat_tonal_recovery_pct), pct_color(stat_tonal_recovery_pct), "vs baseline"),
    ("After Running - Next-Day Tonal Volume", fmt_pct(stat_run_tonal_pct), pct_color(stat_run_tonal_pct), "vs baseline"),
    (f"Best Recovery Day", best_dow_name, "#f39c12", "highest avg next-day recovery"),
    ("Hardest Combo Impact", fmt_pct(hardest_pct) if hardest_pct is not None else "Low data", pct_color(hardest_pct), "Heavy Tonal + Long Run"),
]

cards_html = ""
for title, val, color, sub in stat_cards:
    cards_html += f"""
    <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;flex:1;min-width:180px;">
      <div style="color:#8b949e;font-size:12px;margin-bottom:8px;">{title}</div>
      <div style="color:{color};font-size:28px;font-weight:bold;margin-bottom:4px;">{val}</div>
      <div style="color:#8b949e;font-size:11px;">{sub}</div>
    </div>"""

combo_rows = ""
for combo, rec_val, pct, n in combos:
    pct_str = fmt_pct(pct)
    clr = pct_color(pct)
    rec_display = f"{rec_val:.0f}" if rec_val else "-"
    combo_rows += f"""<tr>
      <td style="padding:10px 16px;color:#e6edf3;">{combo}</td>
      <td style="padding:10px 16px;text-align:center;color:#8b949e;">{n}</td>
      <td style="padding:10px 16px;text-align:center;color:#e6edf3;">{rec_display}</td>
      <td style="padding:10px 16px;text-align:center;color:{clr};font-weight:bold;">{pct_str}</td>
    </tr>"""

scatter1 = svg_scatter(run_vs_recovery, "Distance", "Recovery Score", "Run Distance - Next-Day Recovery", xunit=" mi")
scatter2 = svg_scatter(run_vs_tonal, "Avg HR", "Tonal Volume", "Run Intensity - Next-Day Tonal", xunit=" bpm", yunit=" lbs")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Cross-Training Impact Analysis</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',monospace;}}
h1,h2,h3{{font-family:monospace;}}
a{{color:#0a84ff;}}
table{{width:100%;border-collapse:collapse;}}
th{{background:#21262d;color:#8b949e;font-size:11px;text-transform:uppercase;letter-spacing:.05em;padding:10px 16px;text-align:left;}}
tr:hover td{{background:#1c2128;}}
td{{border-top:1px solid #21262d;}}
.section{{padding:32px 24px;max-width:1100px;margin:0 auto;}}
.card-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px;}}
.chart-row{{display:flex;gap:24px;flex-wrap:wrap;align-items:flex-start;}}
</style>
</head>
<body>
{NAV}
<div class="section">
  <h1 style="font-size:24px;margin-bottom:6px;">Cross-Training Impact Analysis</h1>
  <p style="color:#8b949e;font-size:13px;margin-bottom:28px;">How Tonal strength training and running affect each other and your recovery</p>

  <h2 style="font-size:14px;color:#8b949e;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em;">How Your Training Types Affect Each Other</h2>
  <div class="card-row">{cards_html}</div>

  <h2 style="font-size:14px;color:#8b949e;margin-top:32px;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em;">Tonal Intensity - Next-Day Impact Matrix</h2>
  <p style="color:#8b949e;font-size:12px;margin-bottom:16px;">How today's Tonal volume affects tomorrow's key metrics (% change from your average)</p>
  <div style="overflow-x:auto;margin-bottom:32px;">
    {svg_impact_matrix()}
  </div>

  <h2 style="font-size:14px;color:#8b949e;margin-top:32px;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em;">Running - Next-Day Impact</h2>
  <p style="color:#8b949e;font-size:12px;margin-bottom:16px;">Each dot = one day. Dashed blue line shows trend.</p>
  <div class="chart-row" style="margin-bottom:32px;">
    <div>{scatter1}</div>
    <div>{scatter2}</div>
  </div>

  <h2 style="font-size:14px;color:#8b949e;margin-top:32px;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em;">Optimal Training Combinations</h2>
  <p style="color:#8b949e;font-size:12px;margin-bottom:16px;">Ranked by next-day recovery impact. Baseline: {baseline_recovery:.0f}</p>
  <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden;margin-bottom:32px;">
    <table>
      <thead><tr>
        <th>Training Combination</th>
        <th style="text-align:center;">Days</th>
        <th style="text-align:center;">Avg Next-Day Recovery</th>
        <th style="text-align:center;">vs Baseline</th>
      </tr></thead>
      <tbody>{combo_rows}</tbody>
    </table>
  </div>

  <h2 style="font-size:14px;color:#8b949e;margin-top:32px;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em;">Day-of-Week Training and Recovery</h2>
  <p style="color:#8b949e;font-size:12px;margin-bottom:16px;">Average training load by day + next-day recovery trend (green line)</p>
  <div style="overflow-x:auto;margin-bottom:32px;">
    {svg_dow_bar()}
  </div>

  <h2 style="font-size:14px;color:#8b949e;margin-top:32px;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em;">Recommendations</h2>
  <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;">
    <ul style="list-style:none;display:flex;flex-direction:column;gap:14px;">
      <li style="display:flex;gap:12px;align-items:flex-start;">
        <span style="color:#f39c12;">-</span>
        <span>Schedule heavy Tonal sessions on <strong style="color:#f39c12;">{best_dow_name}</strong> - your data shows highest next-day recovery after training on this day.</span>
      </li>
      <li style="display:flex;gap:12px;align-items:flex-start;">
        <span style="color:#f85149;">-</span>
        <span>Avoid combining <strong style="color:#f85149;">Heavy Tonal + Running</strong> on the same day - this pairing shows the largest recovery penalty ({fmt_pct(hardest_pct)}).</span>
      </li>
      <li style="display:flex;gap:12px;align-items:flex-start;">
        <span style="color:#2ea043;">-</span>
        <span>Your best recovery comes after <strong style="color:#2ea043;">{combos[0][0] if combos else 'light training days'}</strong> - consider sequencing this before important workouts.</span>
      </li>
      <li style="display:flex;gap:12px;align-items:flex-start;">
        <span style="color:#0a84ff;">-</span>
        <span>Running has a <strong style="color:#{'f85149' if (stat_run_tonal_pct or 0) < 0 else '2ea043'}">{fmt_pct(stat_run_tonal_pct)}</strong> effect on next-day Tonal volume - plan accordingly when targeting strength PRs.</span>
      </li>
    </ul>
  </div>

  <p style="color:#30363d;font-size:11px;text-align:right;margin-top:24px;">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} - {len(all_dates)} days analyzed - {len(pairs)} consecutive day-pairs</p>
</div>
</body>
</html>"""

out_path = OUT_DIR / "index.html"
out_path.write_text(html)
print(f"Written: {out_path}")
print(f"Size: {out_path.stat().st_size:,} bytes")
