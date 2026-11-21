#!/usr/bin/env python3
"""Deep Sleep Optimization Dashboard generator."""
import json, os, glob, csv
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

EIGHT_SLEEP_DIR = os.path.expanduser("~/clawd/data/eight_sleep")
WHOOP_FILE = os.path.expanduser("~/.openclaw/workspace/scripts/data/whoop_v2_latest.json")
TONAL_FILE = os.path.expanduser("~/clawd/data/tonal/tonal_full_history.json")
CRONOMETER_FILE = os.path.expanduser("~/clawd/data/cronometer/dailysummary.csv")
OUTPUT_FILE = os.path.expanduser("~/clawd/docs/recovery/deep_sleep_focus/index.html")
ET = ZoneInfo("America/New_York")

def parse_8sleep_record(d):
    """Parse a single 8Sleep record dict, handling both old and new formats."""
    sb = d.get("sleep_breakdown", {})
    # New format: hours already
    deep = sb.get("deep", 0) or 0
    total = d.get("time_slept_hours", 0) or 0
    score = d.get("sleep_score", d.get("score", 0)) or 0
    # If deep looks like seconds (> 100), convert
    if deep > 24:
        deep = deep / 3600
    # If total is 0, maybe compute from breakdown
    if total == 0 and sb:
        raw = sum(sb.get(k, 0) or 0 for k in ["deep", "light", "rem"])
        if raw > 100:
            total = raw / 3600
        else:
            total = raw
    bed_temp = d.get("bed_temp_f", 0) or 0
    sleep_start_str = d.get("sleep_start", d.get("presence_start", "")) or ""
    bed_hour = None
    if sleep_start_str:
        try:
            dt_utc = datetime.fromisoformat(sleep_start_str.replace("Z", "+00:00"))
            dt_et = dt_utc.astimezone(ET)
            bed_hour = dt_et.hour + dt_et.minute / 60.0
        except Exception:
            pass
    return {"deep": deep, "total": total, "score": score, "bed_temp": bed_temp, "bed_hour": bed_hour}

# Load 8Sleep last 90 days
all_files = sorted(glob.glob(os.path.join(EIGHT_SLEEP_DIR, "*.json")))
cutoff = datetime.now() - timedelta(days=90)
sleep_records = []
for fpath in all_files:
    fname = os.path.basename(fpath).replace(".json", "")
    try:
        rec_date = datetime.strptime(fname, "%Y-%m-%d")
    except ValueError:
        continue
    if rec_date < cutoff:
        continue
    with open(fpath) as f:
        raw = json.load(f)
    # Handle list or dict
    recs = raw if isinstance(raw, list) else [raw]
    # Pick the left-side record or first
    rec = next((r for r in recs if isinstance(r, dict) and r.get("side") == "left"), recs[0] if recs and isinstance(recs[0], dict) else None)
    if rec is None:
        continue
    parsed = parse_8sleep_record(rec)
    sleep_records.append({
        "date": fname,
        "date_dt": rec_date,
        "dow": rec_date.strftime("%a"),
        **parsed,
    })

sleep_records.sort(key=lambda x: x["date"])

# Load WHOOP
whoop_by_date = {}
try:
    with open(WHOOP_FILE) as f:
        wd = json.load(f)
    for rec in wd.get("recovery", {}).get("records", []):
        created = rec.get("created_at", "")
        score_d = rec.get("score", {})
        hrv = score_d.get("hrv_rmssd_milli")
        if created and hrv:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(ET)
                whoop_by_date[dt.strftime("%Y-%m-%d")] = {
                    "hrv": hrv,
                    "rhr": score_d.get("resting_heart_rate"),
                    "recovery_score": score_d.get("recovery_score"),
                }
            except Exception:
                pass
except Exception:
    pass

# Load Tonal
tonal_by_date = {}
try:
    with open(TONAL_FILE) as f:
        tonal_data = json.load(f)
    for w in tonal_data:
        bt = w.get("beginTime", "")
        if not bt:
            continue
        try:
            dt_et = datetime.fromisoformat(bt.replace("Z", "+00:00")).astimezone(ET)
            dk = dt_et.strftime("%Y-%m-%d")
            if dk not in tonal_by_date:
                tonal_by_date[dk] = {"count": 0, "volume": 0}
            tonal_by_date[dk]["count"] += 1
            tonal_by_date[dk]["volume"] += w.get("totalVolume", 0) or 0
        except Exception:
            pass
except Exception:
    pass

# Load Cronometer
cron_by_date = {}
try:
    with open(CRONOMETER_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dk = row.get("Date", "").strip()
            if not dk:
                continue
            def sf(v):
                try: return float(v) if v else 0.0
                except: return 0.0
            cron_by_date[dk] = {"calories": sf(row.get("Energy (kcal)", 0)), "protein": sf(row.get("Protein (g)", 0))}
except Exception:
    pass

# Compute stats
valid = [r for r in sleep_records if r["deep"] > 0 and r["total"] > 0]
print(f"Valid records: {len(valid)}")
if not valid:
    print("ERROR: No valid deep sleep records found")
    exit(1)

avg_deep = sum(r["deep"] for r in valid) / len(valid)
avg_ratio = sum(r["deep"] / r["total"] for r in valid if r["total"] > 0) / len(valid)
early = valid[:max(1, len(valid)//3)]
late = valid[-max(1, len(valid)//3):]
avg_early = sum(r["deep"] for r in early) / len(early)
avg_late = sum(r["deep"] for r in late) / len(late)
trend_pct = ((avg_late - avg_early) / avg_early * 100) if avg_early > 0 else 0
trend_arrow = "↑" if trend_pct > 2 else ("↓" if trend_pct < -2 else "→")

dow_sums = {}
dow_counts = {}
for r in valid:
    dow_sums[r["dow"]] = dow_sums.get(r["dow"], 0) + r["deep"]
    dow_counts[r["dow"]] = dow_counts.get(r["dow"], 0) + 1
dow_avgs = {d: dow_sums[d]/dow_counts[d] for d in dow_sums}
best_dow = max(dow_avgs, key=dow_avgs.get) if dow_avgs else "N/A"

def pearson(xs, ys):
    n = len(xs)
    if n < 3: return 0.0
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = sum((x-mx)**2 for x in xs)**0.5
    dy = sum((y-my)**2 for y in ys)**0.5
    return num/(dx*dy) if dx and dy else 0.0

deep_vals = [r["deep"] for r in valid]
workout_flag = [1.0 if r["date"] in tonal_by_date else 0.0 for r in valid]
rest_flag = [0.0 if r["date"] in tonal_by_date else 1.0 for r in valid]
bed_temps = [r["bed_temp"] for r in valid]
hrv_paired, deep_hrv = [], []
prot_paired, deep_prot = [], []
bedh_paired, deep_bedh = [], []
for r in valid:
    if r["date"] in whoop_by_date and whoop_by_date[r["date"]]["hrv"]:
        hrv_paired.append(whoop_by_date[r["date"]]["hrv"])
        deep_hrv.append(r["deep"])
    prev = (r["date_dt"] - timedelta(days=1)).strftime("%Y-%m-%d")
    if prev in cron_by_date and cron_by_date[prev]["protein"] > 0:
        prot_paired.append(cron_by_date[prev]["protein"])
        deep_prot.append(r["deep"])
    if r["bed_hour"] is not None:
        bedh_paired.append(r["bed_hour"])
        deep_bedh.append(r["deep"])

factors = [
    ("Workout Day", pearson(workout_flag, deep_vals)),
    ("Rest Day", pearson(rest_flag, deep_vals)),
    ("Bed Temperature", pearson(bed_temps, deep_vals) if any(t > 0 for t in bed_temps) else 0.0),
    ("HRV (WHOOP)", pearson(hrv_paired, deep_hrv) if len(hrv_paired) >= 3 else 0.0),
    ("Prior-Day Protein", pearson(prot_paired, deep_prot) if len(prot_paired) >= 3 else 0.0),
    ("Earlier Bedtime", -pearson(bedh_paired, deep_bedh) if len(bedh_paired) >= 3 else 0.0),
]
factors.sort(key=lambda x: abs(x[1]), reverse=True)
top_factor = factors[0][0]

def rolling_avg(data, window=7):
    result = []
    for i in range(len(data)):
        chunk = data[max(0,i-window+1):i+1]
        result.append(sum(chunk)/len(chunk) if chunk else None)
    return result

trend_dates = [r["date"] for r in valid]
trend_deep = [r["deep"] for r in valid]
trend_roll = rolling_avg(trend_deep)

days_order = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
dow_data = {d: [] for d in days_order}
for r in valid:
    if r["dow"] in dow_data: dow_data[r["dow"]].append(r["deep"])
dow_avgs_ordered = [sum(dow_data[d])/len(dow_data[d]) if dow_data[d] else 0 for d in days_order]

# Insights
insights = []
if hrv_paired and abs(factors[3][1]) > 0.05:
    corr = factors[3][1]
    dir_ = "higher" if corr > 0 else "lower"
    insights.append(("📈", f"{dir_.capitalize()} HRV correlates with {'more' if corr>0 else 'less'} deep sleep (r={corr:.2f}). Monitor HRV to gauge sleep readiness.", 72))
bt_corr = factors[2][1]
if any(t > 0 for t in bed_temps) and abs(bt_corr) > 0.03:
    avg_bt = sum(t for t in bed_temps if t>0)/sum(1 for t in bed_temps if t>0)
    insights.append(("🌡️", f"Bed temp correlates {'positively' if bt_corr>0 else 'negatively'} with deep sleep (r={bt_corr:.2f}). Your avg: {avg_bt:.1f}°F.", 65))
if trend_pct > 2:
    insights.append(("✨", f"Deep sleep trending up {trend_pct:.1f}% — great momentum, keep your current habits!", 80))
elif trend_pct < -2:
    insights.append(("⚠️", f"Deep sleep down {abs(trend_pct):.1f}% this period. Check if sleep timing or stress changed recently.", 75))
if best_dow in dow_avgs:
    insights.append(("📅", f"{best_dow} is your best deep sleep day (avg {dow_avgs[best_dow]:.2f}h). Plan recovery around this.", 60))
wk_corr = factors[0][1]
if abs(wk_corr) > 0.03:
    insights.append(("🏋️", f"{'Workout' if wk_corr>0 else 'Rest'} days correlate with more deep sleep (r={wk_corr:.2f}). Timing matters.", 58))
insights = insights[:3]
while len(insights) < 3:
    insights.append(("💤", "Consistent bedtimes signal your body to initiate deep sleep earlier in the night.", 55))

recs = [
    "🕙 Fix your bedtime ±30 min — circadian consistency is the #1 predictor of deep sleep.",
    f"🌡️ Try {'warmer' if bt_corr>0 else 'cooler'} bed temperature — your correlation suggests it helps.",
    "🏋️ Finish workouts 3+ hours before bed to allow core temp to drop (needed for deep sleep).",
    "🥩 Eat your largest protein meal at lunch — late digestion can suppress deep sleep.",
    "📵 No screens or bright lights 45 min pre-bed — melatonin suppression delays deep onset.",
    "🧘 10 min of yoga nidra or 4-7-8 breathing before bed increases slow-wave sleep time.",
]

# SVGs
def make_trend_svg(dates, deeps, rolls):
    W, H, PL, PR, PT, PB = 900, 280, 50, 20, 20, 40
    n = len(deeps)
    if n == 0: return "<svg><text x='10' y='20' fill='white'>No data</text></svg>"
    max_val = max(max(deeps), 2.0)
    def px(i): return PL + (i/max(n-1,1))*(W-PL-PR)
    def py(v): return H - PB - (v/max_val)*(H-PT-PB)
    lines = []
    for gv in [0.5,1.0,1.5,2.0,2.5]:
        if gv > max_val*1.05: continue
        gy=py(gv); lines.append(f'<line x1="{PL}" y1="{gy:.1f}" x2="{W-PR}" y2="{gy:.1f}" stroke="#30363d" stroke-width="1"/>')
        lines.append(f'<text x="{PL-5}" y="{gy+4:.1f}" fill="#8b949e" font-size="10" text-anchor="end">{gv:.1f}</text>')
    step=max(1,n//6)
    for i in range(0,n,step):
        lines.append(f'<text x="{px(i):.1f}" y="{H-5}" fill="#8b949e" font-size="9" text-anchor="middle">{dates[i][-5:]}</text>')
    pts=" ".join(f"{px(i):.1f},{py(deeps[i]):.1f}" for i in range(n))
    lines.append(f'<polyline points="{pts}" fill="none" stroke="#f39c12" stroke-width="1.5" opacity="0.7"/>')
    for i in range(n): lines.append(f'<circle cx="{px(i):.1f}" cy="{py(deeps[i]):.1f}" r="2" fill="#f39c12" opacity="0.6"/>')
    rpts=" ".join(f"{px(i):.1f},{py(rv):.1f}" for i,rv in enumerate(rolls) if rv)
    if rpts: lines.append(f'<polyline points="{rpts}" fill="none" stroke="#0a84ff" stroke-width="2.5"/>')
    lines.append('<rect x="60" y="8" width="12" height="3" fill="#f39c12" rx="1"/><text x="76" y="15" fill="#8b949e" font-size="10">Daily</text>')
    lines.append('<rect x="110" y="8" width="12" height="3" fill="#0a84ff" rx="1"/><text x="126" y="15" fill="#8b949e" font-size="10">7-Day Avg</text>')
    return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;">\n' + "\n".join(lines) + "\n</svg>"

def make_corr_svg(factors_list):
    W, H, BAR_H = 420, 240, 22
    PL, PR, PT = 145, 60, 20
    max_abs = max(abs(v) for _,v in factors_list) if factors_list else 1
    max_abs = max(max_abs, 0.01)
    usable = W-PL-PR
    mid_x = PL+usable*0.5
    lines = [f'<line x1="{mid_x:.1f}" y1="{PT}" x2="{mid_x:.1f}" y2="{PT+len(factors_list)*(BAR_H+8)}" stroke="#30363d" stroke-width="1"/>']
    for i,(name,val) in enumerate(factors_list):
        y=PT+i*(BAR_H+8); bw=abs(val)/max_abs*usable*0.45
        color="#2ea043" if val>=0 else "#f85149"
        xs=mid_x if val>=0 else mid_x-bw
        lines.append(f'<rect x="{xs:.1f}" y="{y}" width="{max(bw,1):.1f}" height="{BAR_H}" fill="{color}" rx="3" opacity="0.85"/>')
        lines.append(f'<text x="{PL-8}" y="{y+BAR_H//2+4}" fill="#e6edf3" font-size="11" text-anchor="end">{name}</text>')
        tx=mid_x+bw+4 if val>=0 else mid_x-bw-4; anc="start" if val>=0 else "end"
        sign="+" if val>=0 else ""
        lines.append(f'<text x="{tx:.1f}" y="{y+BAR_H//2+4}" fill="#8b949e" font-size="10" text-anchor="{anc}">{sign}{val:.2f}</text>')
    return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;">\n' + "\n".join(lines) + "\n</svg>"

def make_dow_svg(days, avgs):
    W, H, PL, PB, PT, PR = 380, 200, 40, 30, 20, 20
    n=len(days); cw=(W-PL-PR)/n; bw=cw-6
    max_val=max(avgs) if max(avgs)>0 else 1
    lines=[]
    for gv in [0.5,1.0,1.5,2.0]:
        if gv>max_val*1.1: continue
        gy=H-PB-(gv/max_val)*(H-PT-PB)
        lines.append(f'<line x1="{PL}" y1="{gy:.1f}" x2="{W-PR}" y2="{gy:.1f}" stroke="#30363d" stroke-width="1"/>')
        lines.append(f'<text x="{PL-5}" y="{gy+4:.1f}" fill="#8b949e" font-size="9" text-anchor="end">{gv:.1f}</text>')
    best=max(avgs) if avgs else 0
    for i,(day,avg) in enumerate(zip(days,avgs)):
        x=PL+i*cw+3; bh=max((avg/max_val)*(H-PT-PB),1); y=H-PB-bh
        color="#f39c12" if avg==best and avg>0 else "#2ea043"
        lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{color}" rx="3" opacity="0.85"/>')
        lines.append(f'<text x="{x+bw/2:.1f}" y="{H-10}" fill="#8b949e" font-size="10" text-anchor="middle">{day}</text>')
        if avg>0: lines.append(f'<text x="{x+bw/2:.1f}" y="{y-4:.1f}" fill="#e6edf3" font-size="9" text-anchor="middle">{avg:.1f}</text>')
    return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;">\n' + "\n".join(lines) + "\n</svg>"

def make_hrv_scatter(hrv_list, deep_list):
    W,H,PL,PR,PT,PB=380,240,50,20,20,40
    if not hrv_list:
        return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"><text x="20" y="60" fill="#8b949e" font-size="13">Insufficient HRV data (need WHOOP sync).</text></svg>'
    minh,maxh=min(hrv_list),max(hrv_list); maxd=max(deep_list)*1.1 if deep_list else 1
    maxh=max(maxh,minh+0.1); maxd=max(maxd,0.5)
    def px(v): return PL+(v-minh)/(maxh-minh)*(W-PL-PR)
    def py(v): return H-PB-(v/maxd)*(H-PT-PB)
    lines=[]
    for gv in [0.5,1.0,1.5,2.0,2.5]:
        if gv>maxd: continue
        gy=py(gv); lines.append(f'<line x1="{PL}" y1="{gy:.1f}" x2="{W-PR}" y2="{gy:.1f}" stroke="#30363d" stroke-width="1"/>')
        lines.append(f'<text x="{PL-5}" y="{gy+4:.1f}" fill="#8b949e" font-size="9" text-anchor="end">{gv:.1f}</text>')
    lines.append(f'<text x="{(W+PL-PR)//2}" y="{H-5}" fill="#8b949e" font-size="10" text-anchor="middle">HRV (ms)</text>')
    for hrv,deep in zip(hrv_list,deep_list):
        lines.append(f'<circle cx="{px(hrv):.1f}" cy="{py(deep):.1f}" r="5" fill="#0a84ff" opacity="0.75"/>')
    return f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;">\n' + "\n".join(lines) + "\n</svg>"

trend_svg = make_trend_svg(trend_dates, trend_deep, trend_roll)
corr_svg = make_corr_svg(factors)
dow_svg = make_dow_svg(days_order, dow_avgs_ordered)
hrv_svg = make_hrv_scatter(hrv_paired, deep_hrv)
trend_color = "#2ea043" if trend_pct>2 else ("#f85149" if trend_pct<-2 else "#f39c12")

def insight_block(icon, text, conf):
    p = min(conf,100)
    return f'''<div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:12px;display:flex;align-items:flex-start;gap:12px;">
      <span style="font-size:22px;flex-shrink:0;">{icon}</span>
      <div style="flex:1;">
        <div style="font-size:14px;color:#c9d1d9;">{text}</div>
        <div style="margin-top:8px;display:flex;align-items:center;gap:8px;">
          <div style="width:80px;height:4px;background:#30363d;border-radius:2px;overflow:hidden;">
            <div style="width:{p}%;height:100%;background:#f39c12;border-radius:2px;"></div>
          </div>
          <span style="font-size:11px;color:#8b949e;">Confidence: {conf}%</span>
        </div>
      </div>
    </div>'''

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>🧠 Deep Sleep Optimization</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5;}}
nav{{background:#161b22;border-bottom:1px solid #30363d;padding:12px 24px;display:flex;gap:20px;flex-wrap:wrap;align-items:center;}}
nav a{{color:#8b949e;text-decoration:none;font-size:13px;padding:4px 0;}}
nav a:hover,nav a.active{{color:#f39c12;font-weight:600;}}
.container{{max-width:1100px;margin:0 auto;padding:24px 16px;}}
h1{{font-size:28px;font-weight:700;margin-bottom:6px;}}
.subtitle{{color:#8b949e;font-size:14px;margin-bottom:28px;}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:28px;}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px;}}
.card-label{{color:#8b949e;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;}}
.card-value{{font-size:30px;font-weight:700;color:#f39c12;}}
.card-sub{{font-size:13px;color:#8b949e;margin-top:4px;}}
.section{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;margin-bottom:24px;}}
.section-title{{font-size:16px;font-weight:600;margin-bottom:16px;}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px;}}
@media(max-width:700px){{.two-col{{grid-template-columns:1fr;}}}}
ul.recs{{list-style:none;}}
ul.recs li{{padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:8px;margin-bottom:10px;font-size:14px;color:#c9d1d9;}}
.footer{{text-align:center;padding:24px 0;font-size:12px;color:#8b949e;}}
.footer a{{color:#f39c12;text-decoration:none;}}
</style>
</head>
<body>
<nav>
  <a href="/index.html">🏠 Hub</a>
  <a href="/calendars/">📅 Calendars</a>
  <a href="/strength/">💪 Strength</a>
  <a href="/cardio/">🏃 Cardio</a>
  <a href="/recovery/" class="active">🫀 Recovery</a>
  <a href="/nutrition/">🥗 Nutrition</a>
  <a href="/sleep_dashboard.html">😴 Sleep</a>
  <a href="/sleep_stage_performance/">🌙 Stages</a>
</nav>
<div class="container">
  <h1>🧠 Deep Sleep Optimization</h1>
  <p class="subtitle">90-day analysis · {len(valid)} nights · Generated {datetime.now(ET).strftime('%b %d, %Y %I:%M %p ET')}</p>

  <div class="cards">
    <div class="card">
      <div class="card-label">Avg Deep Sleep</div>
      <div class="card-value">{avg_deep:.2f}h</div>
      <div class="card-sub">{avg_ratio*100:.0f}% of total sleep</div>
    </div>
    <div class="card">
      <div class="card-label">90-Day Trend</div>
      <div class="card-value" style="color:{trend_color};">{trend_arrow} {abs(trend_pct):.1f}%</div>
      <div class="card-sub">Early vs. late period avg</div>
    </div>
    <div class="card">
      <div class="card-label">Best Day of Week</div>
      <div class="card-value" style="font-size:24px;">{best_dow}</div>
      <div class="card-sub">Avg {dow_avgs.get(best_dow,0):.2f}h deep</div>
    </div>
    <div class="card">
      <div class="card-label">Top Factor</div>
      <div class="card-value" style="font-size:17px;line-height:1.3;">{top_factor}</div>
      <div class="card-sub">r = {factors[0][1]:.2f}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📈 Deep Sleep — 90-Day Trend</div>
    {trend_svg}
    <div style="font-size:12px;color:#8b949e;margin-top:8px;">🟡 Daily · 🔵 7-Day Rolling Average</div>
  </div>

  <div class="two-col">
    <div class="section">
      <div class="section-title">🔗 Factor Correlations</div>
      <p style="font-size:12px;color:#8b949e;margin-bottom:12px;">🟢 Positive correlation · 🔴 Negative correlation</p>
      {corr_svg}
    </div>
    <div class="section">
      <div class="section-title">📅 Deep Sleep by Day of Week</div>
      <p style="font-size:12px;color:#8b949e;margin-bottom:12px;">🟡 Best day · 🟢 Other days</p>
      {dow_svg}
    </div>
  </div>

  <div class="section">
    <div class="section-title">❤️ HRV vs Deep Sleep</div>
    <p style="font-size:12px;color:#8b949e;margin-bottom:12px;">{len(hrv_paired)} paired nights · WHOOP HRV (x-axis) vs deep sleep hours (y-axis)</p>
    {hrv_svg}
  </div>

  <div class="section">
    <div class="section-title">💡 Key Insights</div>
    {"".join(insight_block(i,t,c) for i,t,c in insights)}
  </div>

  <div class="section">
    <div class="section-title">🎯 Recommendations</div>
    <ul class="recs">{"".join(f"<li>{r}</li>" for r in recs)}</ul>
  </div>

  <div class="footer">
    <a href="/sleep_dashboard.html">← Sleep Dashboard</a> &nbsp;·&nbsp;
    <a href="/recovery/">Recovery Hub</a> &nbsp;·&nbsp;
    <a href="/sleep_stage_performance/">Sleep Stages</a>
  </div>
</div>
</body>
</html>"""

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w") as f:
    f.write(html)
size_kb = os.path.getsize(OUTPUT_FILE)/1024
print(f"SUCCESS: {OUTPUT_FILE}")
print(f"File size: {size_kb:.1f} KB")
