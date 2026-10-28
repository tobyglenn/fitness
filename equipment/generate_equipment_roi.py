#!/usr/bin/env python3
"""Equipment ROI Analysis Generator"""
import json, glob, os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

BASE = os.path.expanduser("~/clawd")
DATA_DIR = os.path.join(BASE, "data")
OUT_DIR  = os.path.join(BASE, "docs", "equipment")
OUT_FILE = os.path.join(OUT_DIR, "index.html")
os.makedirs(OUT_DIR, exist_ok=True)

ET = timezone(timedelta(hours=-5))
NOW = datetime.now(ET)

# ── Load data ──────────────────────────────────────────────────────────────
tonal_files = sorted(glob.glob(os.path.join(DATA_DIR, "tonal", "tonal_workouts_*.json")))
tonal_workouts = []; strength_history = []
if tonal_files:
    with open(tonal_files[-1]) as f: td = json.load(f)
    tonal_workouts = td.get("workouts", [])
    strength_history = td.get("strengthScoreHistory", [])

speediance_file = os.path.join(DATA_DIR, "speediance_full_history.json")
speediance_workouts = []
if os.path.exists(speediance_file):
    with open(speediance_file) as f: sd = json.load(f)
    speediance_workouts = sd.get("all_workouts", [])

garmin_file = os.path.join(DATA_DIR, "garmin_all_activities.json")
garmin_activities = []
if os.path.exists(garmin_file):
    with open(garmin_file) as f: gd = json.load(f)
    garmin_activities = gd.get("activities", [])

# ── Parse ──────────────────────────────────────────────────────────────────
def parse_utc(s):
    try: return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(ET)
    except: return None

def parse_local(s):
    try: return datetime.strptime(s,"%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
    except: return None

tonal_records = []
for w in tonal_workouts:
    if not w.get("completed"): continue
    dt = parse_utc(w.get("beginTime",""))
    if dt is None: continue
    tonal_records.append({"dt":dt,"volume_lbs":w.get("totalVolume",0) or 0,
        "duration_sec":w.get("totalDuration") or w.get("activeDuration") or 0})

speediance_records = []
for w in speediance_workouts:
    if not w.get("isFinish"): continue
    dt = parse_local(w.get("finishTime",""))
    if dt is None: continue
    speediance_records.append({"dt":dt,"volume_lbs":w.get("totalCapacity",0) or 0,
        "duration_sec":w.get("trainingTime",0) or 0})

garmin_records = []
for a in garmin_activities:
    try: dt = datetime.strptime(a["startTimeLocal"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
    except: continue
    garmin_records.append({"dt":dt,"distance_mi":(a.get("distance",0) or 0)/1609.344,
        "duration_sec":a.get("duration",0) or 0,"type":a.get("activityType","")})

# ── Stats ──────────────────────────────────────────────────────────────────
def stats(records, window=None):
    if window: records = [r for r in records if r["dt"] >= NOW-timedelta(days=window)]
    if not records: return dict(count=0,total_volume=0,total_distance=0,total_hours=0,avg_min=0,wk_per_week=0)
    dates = sorted(r["dt"] for r in records)
    span_weeks = max(1,(dates[-1]-dates[0]).days+1)/7
    sec = sum(r.get("duration_sec",0) for r in records)
    return dict(
        count=len(records),
        total_volume=round(sum(r.get("volume_lbs",0) for r in records)),
        total_distance=round(sum(r.get("distance_mi",0) for r in records),1),
        total_hours=round(sec/3600,1),
        avg_min=round(sec/len(records)/60,1),
        wk_per_week=round(len(records)/span_weeks,2)
    )

def weekly_counts(records, n=26):
    labels=[]; counts=[]
    for i in range(n-1,-1,-1):
        ws=NOW-timedelta(weeks=i+1); we=NOW-timedelta(weeks=i)
        labels.append(ws.strftime("%b %d"))
        counts.append(sum(1 for r in records if ws<=r["dt"]<we))
    return labels, counts

wk_labels, tonal_wk  = weekly_counts(tonal_records)
_,          spd_wk   = weekly_counts(speediance_records)
_,          garmin_wk= weekly_counts(garmin_records)

t_all=stats(tonal_records); t_90=stats(tonal_records,90); t_180=stats(tonal_records,180)
s_all=stats(speediance_records); s_90=stats(speediance_records,90); s_180=stats(speediance_records,180)
g_all=stats(garmin_records); g_90=stats(garmin_records,90); g_180=stats(garmin_records,180)

def eff(s, dist=False):
    if s["total_hours"]==0: return 0
    v = s["total_distance"] if dist else s["total_volume"]
    return round(v/s["total_hours"],1)

# Strength score history
strength_pts=[]
for e in strength_history[-8:]:
    dt_s=e.get("date",e.get("createdAt",""))
    sc=e.get("score",e.get("strengthScore",0))
    if dt_s and sc: strength_pts.append((dt_s[:10],round(sc,1)))

# Speediance monthly
spd_monthly=defaultdict(float)
for r in speediance_records: spd_monthly[r["dt"].strftime("%Y-%m")]+=r["volume_lbs"]
spd_monthly=dict(sorted(spd_monthly.items())[-12:])

# Verdict
def winner(vals): return max(vals, key=lambda k:vals[k])
best_consistency=winner({"Tonal":t_all["wk_per_week"],"Speediance":s_all["wk_per_week"],"Garmin Cardio":g_all["wk_per_week"]})
best_volume=winner({"Tonal":t_all["total_volume"],"Speediance":s_all["total_volume"]})

# ── SVG ────────────────────────────────────────────────────────────────────
def grouped_bar_svg(labels, series_list, colors, w=760, h=200, unit=""):
    all_vals=[v for s in series_list for v in s]
    mv=max(all_vals) if all_vals and max(all_vals)>0 else 1
    ns=len(series_list); ng=len(labels)
    bw=max(10,min(30,(w-60)//(ng*(ns+0.5))))
    pad_l,pad_r,pad_t,pad_b=50,10,15,40
    cw=w-pad_l-pad_r; ch=h-pad_t-pad_b
    svg=[f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{w}px">',
         f'<rect width="{w}" height="{h}" fill="#161b22" rx="8"/>']
    for p in [.25,.5,.75,1.]:
        y=pad_t+ch*(1-p)
        svg.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w-pad_r}" y2="{y:.0f}" stroke="#30363d" stroke-width="1"/>')
        svg.append(f'<text x="{pad_l-4}" y="{y+4:.0f}" fill="#8b949e" font-size="10" text-anchor="end">{mv*p:.0f}{unit}</text>')
    gw=cw/ng
    for gi,label in enumerate(labels):
        gx=pad_l+gi*gw+gw*0.1
        for si,(series,color) in enumerate(zip(series_list,colors)):
            val=series[gi]; bh=(val/mv)*ch
            bx=gx+si*(bw+2); by=pad_t+ch-bh
            svg.append(f'<rect x="{bx:.0f}" y="{by:.0f}" width="{bw}" height="{bh:.0f}" fill="{color}" rx="2"><title>{label}: {val:.1f}{unit}</title></rect>')
        svg.append(f'<text x="{pad_l+gi*gw+gw/2:.0f}" y="{h-6}" fill="#8b949e" font-size="10" text-anchor="middle">{label}</text>')
    svg.append('</svg>'); return "\n".join(svg)

def single_bar_svg(labels, values, color, w=760, h=180, unit=""):
    return grouped_bar_svg(labels, [values], [color], w, h, unit)

def line_svg(labels, series_data, colors, names, w=760, h=200):
    all_v=[v for s in series_data for v in s]
    mv=max(all_v) if all_v and max(all_v)>0 else 1
    pad_l,pad_r,pad_t,pad_b=40,10,15,55
    cw=w-pad_l-pad_r; ch=h-pad_t-pad_b; n=len(labels)
    svg=[f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{w}px">',
         f'<rect width="{w}" height="{h}" fill="#161b22" rx="8"/>']
    for p in [.25,.5,.75,1.]:
        y=pad_t+ch*(1-p)
        svg.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w-pad_r}" y2="{y:.0f}" stroke="#30363d" stroke-width="1"/>')
        svg.append(f'<text x="{pad_l-4}" y="{y+4:.0f}" fill="#8b949e" font-size="10" text-anchor="end">{mv*p:.1f}</text>')
    for series,color,name in zip(series_data,colors,names):
        pts=[]
        for i,v in enumerate(series):
            x=pad_l+i*(cw/max(n-1,1)); y=pad_t+ch*(1-v/mv)
            pts.append(f"{x:.0f},{y:.0f}")
        svg.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round"/>')
        for i,(v,pt) in enumerate(zip(series,pts)):
            x,y=pt.split(",")
            svg.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"><title>{labels[i]}: {v}</title></circle>')
    for i,label in enumerate(labels):
        if i%4==0 or i==n-1:
            x=pad_l+i*(cw/max(n-1,1))
            svg.append(f'<text x="{x:.0f}" y="{h-38}" fill="#8b949e" font-size="9" text-anchor="middle">{label}</text>')
    lx=pad_l
    for color,name in zip(colors,names):
        svg.append(f'<rect x="{lx}" y="{h-22}" width="10" height="10" fill="{color}" rx="2"/>')
        svg.append(f'<text x="{lx+13}" y="{h-13}" fill="#c9d1d9" font-size="11">{name}</text>')
        lx+=len(name)*7+28
    svg.append('</svg>'); return "\n".join(svg)

def sparkline(pts, color="#f39c12", w=200, h=55):
    if not pts: return ""
    vals=[p[1] for p in pts]; mn=min(vals); mx=max(vals); rng=mx-mn if mx!=mn else 1
    pad=8
    svg=[f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:{w}px;height:{h}px">']
    coords=[(pad+i*(w-2*pad)/max(len(pts)-1,1), h-pad-(v-mn)/rng*(h-2*pad), v) for i,(_, v) in enumerate(pts)]
    svg.append(f'<polyline points="{" ".join(f"{x:.0f},{y:.0f}" for x,y,_ in coords)}" fill="none" stroke="{color}" stroke-width="2"/>')
    for x,y,v in coords:
        svg.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="{color}"><title>{v}</title></circle>')
    svg.append('</svg>'); return "\n".join(svg)

consistency_chart = line_svg(wk_labels, [tonal_wk,spd_wk,garmin_wk], ["#f39c12","#2ea043","#0a84ff"], ["Tonal","Speediance","Garmin"])
counts_chart = grouped_bar_svg(["Last 90d","Last 180d","All-time"],
    [[t_90["count"],t_180["count"],t_all["count"]],[s_90["count"],s_180["count"],s_all["count"]],[g_90["count"],g_180["count"],g_all["count"]]],
    ["#f39c12","#2ea043","#0a84ff"])
hours_chart = grouped_bar_svg(["Last 90d","Last 180d","All-time"],
    [[t_90["total_hours"],t_180["total_hours"],t_all["total_hours"]],[s_90["total_hours"],s_180["total_hours"],s_all["total_hours"]],[g_90["total_hours"],g_180["total_hours"],g_all["total_hours"]]],
    ["#f39c12","#2ea043","#0a84ff"], unit="h")
strength_spark = sparkline(strength_pts)
spd_vol_labels=list(spd_monthly.keys()); spd_vol_vals=[round(v) for v in spd_monthly.values()]
spd_monthly_chart = single_bar_svg(spd_vol_labels, spd_vol_vals, "#2ea043", unit=" lbs")

garmin_types=sorted(set(r["type"] for r in garmin_records))

color_map={"Tonal":"#f39c12","Speediance":"#2ea043","Garmin Cardio":"#0a84ff"}
def colored(n): return f'<span style="color:{color_map.get(n,chr(35)+"fff")}">{n}</span>'

generated=NOW.strftime("%A, %B %-d, %Y at %-I:%M %p ET")

NAV=[("../hub_index.html","🏠 Hub"),("../strength/index.html","💪 Strength"),
     ("../cardio/index.html","🏃 Cardio"),("../recovery/index.html","🔄 Recovery"),
     ("../sleep_dashboard.html","😴 Sleep"),("index.html","⚖️ Equipment")]
nav_items="".join(f'<a href="{h}" style="color:#8b949e;text-decoration:none;padding:6px 10px;border-radius:6px;white-space:nowrap" onmouseover="this.style.color=\'#f39c12\'" onmouseout="this.style.color=\'#8b949e\'">{l}</a>' for h,l in NAV)
nav=f'<nav style="background:#161b22;border-bottom:1px solid #30363d;padding:8px 16px;display:flex;gap:4px;flex-wrap:wrap;align-items:center"><span style="color:#f39c12;font-weight:700;margin-right:8px">🌸 ARIA</span>{nav_items}</nav>'

def pct_bar(val, mx, color):
    p=min(100,round(val/max(mx,1)*100))
    return f'<div style="background:#21262d;border-radius:4px;height:7px;margin-top:8px"><div style="background:{color};width:{p}%;height:7px;border-radius:4px"></div></div>'

max_count=max(t_all["count"],s_all["count"],g_all["count"],1)

def equip_card(name, color, s_90, s_180, s_all, dist=False):
    vol_label="lbs" if not dist else "mi"
    vol_all=f'{s_all["total_distance"]} mi' if dist else f'{s_all["total_volume"]:,} lbs'
    vol_90 =f'{s_90["total_distance"]} mi'  if dist else f'{s_90["total_volume"]:,} lbs'
    e_all=eff(s_all,dist); e_90=eff(s_90,dist); eu="mi/hr" if dist else "lbs/hr"
    return f'''<div style="background:#161b22;border:1px solid {color}33;border-left:3px solid {color};border-radius:10px;padding:18px;margin-bottom:20px">
  <h2 style="color:{color};margin:0 0 14px 0;font-size:1.2rem">{name}</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px">
    <div style="background:#1c2128;border-radius:8px;padding:12px">
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase">Workouts (all)</div>
      <div style="font-size:24px;font-weight:700;color:{color}">{s_all["count"]}</div>
      <div style="font-size:12px;color:#8b949e">{s_all["wk_per_week"]}/wk avg</div>
    </div>
    <div style="background:#1c2128;border-radius:8px;padding:12px">
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase">Volume (all)</div>
      <div style="font-size:22px;font-weight:700;color:{color}">{vol_all}</div>
      <div style="font-size:12px;color:#8b949e">90d: {vol_90}</div>
    </div>
    <div style="background:#1c2128;border-radius:8px;padding:12px">
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase">Hours (all)</div>
      <div style="font-size:24px;font-weight:700;color:{color}">{s_all["total_hours"]}h</div>
      <div style="font-size:12px;color:#8b949e">Avg: {s_all["avg_min"]} min/session</div>
    </div>
    <div style="background:#1c2128;border-radius:8px;padding:12px">
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase">Efficiency</div>
      <div style="font-size:24px;font-weight:700;color:{color}">{e_all}</div>
      <div style="font-size:12px;color:#8b949e">{eu} (90d: {e_90})</div>
    </div>
  </div>
</div>'''

tonal_total_hrs_all = t_all["total_hours"]+s_all["total_hours"]+g_all["total_hours"]

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Equipment ROI Analysis</title>
<style>
* {{ box-sizing:border-box;margin:0;padding:0 }}
body {{ background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5 }}
.container {{ max-width:900px;margin:0 auto;padding:24px 16px }}
.card {{ background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;margin-bottom:22px }}
.section-title {{ font-size:1.05rem;font-weight:700;color:#e6edf3;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #30363d }}
.grid-3 {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:22px }}
.chart-wrap {{ overflow-x:auto;margin-top:10px }}
</style>
</head>
<body>
{nav}
<div class="container">
  <div style="margin-bottom:26px">
    <h1 style="font-size:1.8rem;font-weight:800;color:#f39c12">⚖️ Equipment ROI Analysis</h1>
    <p style="color:#8b949e;margin-top:6px">Which training method delivers the best results? · Generated {generated}</p>
  </div>

  <!-- Summary Cards -->
  <div class="grid-3">
    <div class="card" style="border-color:#f39c12">
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.05em">Tonal</div>
      <div style="font-size:32px;font-weight:800;color:#f39c12">{t_all["count"]}</div>
      <div style="font-size:12px;color:#8b949e">{t_all["total_volume"]:,} lbs · {t_all["total_hours"]}h</div>
      {pct_bar(t_all["count"],max_count,"#f39c12")}
    </div>
    <div class="card" style="border-color:#2ea043">
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.05em">Speediance</div>
      <div style="font-size:32px;font-weight:800;color:#2ea043">{s_all["count"]}</div>
      <div style="font-size:12px;color:#8b949e">{s_all["total_volume"]:,} lbs · {s_all["total_hours"]}h</div>
      {pct_bar(s_all["count"],max_count,"#2ea043")}
    </div>
    <div class="card" style="border-color:#0a84ff">
      <div style="font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.05em">Garmin Cardio</div>
      <div style="font-size:32px;font-weight:800;color:#0a84ff">{g_all["count"]}</div>
      <div style="font-size:12px;color:#8b949e">{g_all["total_distance"]} mi · {g_all["total_hours"]}h</div>
      {pct_bar(g_all["count"],max_count,"#0a84ff")}
    </div>
  </div>

  <!-- Workout Count Comparison -->
  <div class="card">
    <div class="section-title">📊 Workout Count by Time Window</div>
    <div class="chart-wrap">{counts_chart}</div>
    <div style="display:flex;gap:16px;margin-top:10px;flex-wrap:wrap">
      <span style="font-size:12px"><span style="color:#f39c12">■</span> Tonal</span>
      <span style="font-size:12px"><span style="color:#2ea043">■</span> Speediance</span>
      <span style="font-size:12px"><span style="color:#0a84ff">■</span> Garmin</span>
    </div>
  </div>

  <!-- Weekly Consistency -->
  <div class="card">
    <div class="section-title">📈 Weekly Consistency — Last 26 Weeks</div>
    <div class="chart-wrap">{consistency_chart}</div>
  </div>

  <!-- Time Investment -->
  <div class="card">
    <div class="section-title">⏱️ Time Investment</div>
    <div class="chart-wrap">{hours_chart}</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:14px">
      <div style="background:#1c2128;border-radius:8px;padding:12px">
        <div style="color:#f39c12;font-weight:700">Tonal</div>
        <div style="font-size:13px;color:#8b949e">Avg: {t_all["avg_min"]} min/session</div>
        <div style="font-size:13px;color:#8b949e">Efficiency: {eff(t_all)} lbs/hr</div>
      </div>
      <div style="background:#1c2128;border-radius:8px;padding:12px">
        <div style="color:#2ea043;font-weight:700">Speediance</div>
        <div style="font-size:13px;color:#8b949e">Avg: {s_all["avg_min"]} min/session</div>
        <div style="font-size:13px;color:#8b949e">Efficiency: {eff(s_all)} lbs/hr</div>
      </div>
      <div style="background:#1c2128;border-radius:8px;padding:12px">
        <div style="color:#0a84ff;font-weight:700">Garmin Cardio</div>
        <div style="font-size:13px;color:#8b949e">Avg: {g_all["avg_min"]} min/session</div>
        <div style="font-size:13px;color:#8b949e">Efficiency: {eff(g_all,True)} mi/hr</div>
      </div>
    </div>
  </div>

  <!-- Strength & Volume Progression -->
  <div class="card">
    <div class="section-title">💪 Progression Over Time</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div>
        <div style="color:#f39c12;font-weight:600;margin-bottom:8px;font-size:14px">Tonal — Strength Score</div>
        {strength_spark if strength_spark else '<div style="color:#8b949e;font-size:13px">No strength score data available</div>'}
        {'<div style="font-size:12px;color:#8b949e;margin-top:4px">Latest: '+str(strength_pts[-1][1])+' ('+strength_pts[-1][0]+')</div>' if strength_pts else ''}
      </div>
      <div>
        <div style="color:#2ea043;font-weight:600;margin-bottom:8px;font-size:14px">Speediance — Monthly Volume (lbs)</div>
        <div class="chart-wrap">{spd_monthly_chart}</div>
      </div>
    </div>
  </div>

  <!-- Per-equipment deep dive -->
  <h2 style="color:#8b949e;font-size:1rem;font-weight:600;margin-bottom:14px;text-transform:uppercase;letter-spacing:.05em">📋 Per-Equipment Detail</h2>
  {equip_card("💪 Tonal","#f39c12",t_90,t_180,t_all)}
  {equip_card("⚡ Speediance","#2ea043",s_90,s_180,s_all)}
  {equip_card("🏃 Garmin Cardio","#0a84ff",g_90,g_180,g_all,dist=True)}

  <!-- Verdict -->
  <div class="card" style="border-color:#f39c12">
    <div class="section-title">🏆 The Verdict</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:16px">
      <div style="background:#1c2128;border-radius:8px;padding:14px">
        <div style="display:inline-block;padding:3px 10px;border-radius:20px;background:#f39c1222;color:#f39c12;font-size:12px;font-weight:600;margin-bottom:8px">🔥 Best Consistency</div>
        <div style="font-size:14px">{colored(best_consistency)} logs the most sessions/week — the habit king.</div>
      </div>
      <div style="background:#1c2128;border-radius:8px;padding:14px">
        <div style="display:inline-block;padding:3px 10px;border-radius:20px;background:#2ea04322;color:#2ea043;font-size:12px;font-weight:600;margin-bottom:8px">💪 Best Volume</div>
        <div style="font-size:14px">{colored(best_volume)} moves the most total load — maximum mechanical work.</div>
      </div>
      <div style="background:#1c2128;border-radius:8px;padding:14px">
        <div style="display:inline-block;padding:3px 10px;border-radius:20px;background:#0a84ff22;color:#0a84ff;font-size:12px;font-weight:600;margin-bottom:8px">🎯 Best Variety</div>
        <div style="font-size:14px"><span style="color:#0a84ff">Garmin Cardio</span> covers {len(garmin_types)} activity types: {", ".join(garmin_types)}.</div>
      </div>
    </div>
    <div style="padding:14px;background:#1c2128;border-radius:8px;font-size:14px;color:#8b949e;line-height:1.7">
      <strong style="color:#e6edf3">Summary:</strong> Across all equipment you've logged
      <strong style="color:#f39c12">{t_all["count"]+s_all["count"]+g_all["count"]} total sessions</strong> and
      <strong style="color:#f39c12">{tonal_total_hrs_all:.1f} hours</strong> of training.
      Tonal + Speediance account for {t_all["count"]+s_all["count"]} strength sessions of serious mechanical work.
      Garmin adds the aerobic base with {g_all["count"]} cardio sessions spanning {g_all["total_distance"]} miles.
    </div>
  </div>

  <div style="text-align:center;color:#30363d;font-size:12px;padding-bottom:24px">Generated by ARIA 🌸 · {generated}</div>
</div>
</body>
</html>"""

with open(OUT_FILE,"w") as f: f.write(html)
print(f"SUCCESS: {OUT_FILE}")
