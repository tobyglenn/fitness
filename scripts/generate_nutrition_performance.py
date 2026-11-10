#!/usr/bin/env python3
"""
Nutrition-Performance Bridge Generator
"""

import json, csv, os, math, glob, zoneinfo
from datetime import datetime
from pathlib import Path
from collections import defaultdict

BASE = Path('/Users/tobyglennpeters/clawd')
DATA = BASE / 'data'
OUT_DIR = BASE / 'docs' / 'nutrition_performance'
OUT_FILE = OUT_DIR / 'index.html'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 1. Cronometer ────────────────────────────────────────────────────────────
nutrition = {}
cron_path = DATA / 'cronometer_historical.csv'
if cron_path.exists():
    with open(cron_path) as f:
        for row in csv.DictReader(f):
            d = row.get('Date','').strip()
            if not d: continue
            try:
                nutrition[d] = {
                    'calories': float(row.get('Energy (kcal)',0) or 0),
                    'protein_g': float(row.get('Protein (g)',0) or 0),
                    'carbs_g': float(row.get('Carbs (g)',0) or 0),
                    'fat_g': float(row.get('Fat (g)',0) or 0),
                }
            except: pass

# ── 2. Tonal ─────────────────────────────────────────────────────────────────
tonal_by_date = {}
tz_ny = zoneinfo.ZoneInfo('America/New_York')
for tf in sorted(glob.glob(str(DATA / 'tonal' / 'tonal_workouts_*.json'))):
    with open(tf) as f:
        td = json.load(f)
    for w in td.get('workouts', []):
        begin = w.get('beginTime',''); vol = w.get('totalVolume',0) or 0
        if not begin: continue
        try:
            if begin.endswith('Z'): begin = begin[:-1]+'+00:00'
            dt_ny = datetime.fromisoformat(begin).astimezone(tz_ny)
            d = dt_ny.strftime('%Y-%m-%d')
            tonal_by_date[d] = tonal_by_date.get(d,0) + vol
        except: pass

# ── 3. WHOOP ─────────────────────────────────────────────────────────────────
whoop_by_date = {}
wp = DATA / 'whoop_v2_latest.json'
if wp.exists():
    wdata = json.load(open(wp))
    for rec in wdata.get('recovery',{}).get('records',[]):
        so = rec.get('score',{}) or {}
        score = so.get('recovery_score'); created = rec.get('created_at','')
        if score is None or not created: continue
        try:
            dt_ny = datetime.fromisoformat(created.replace('Z','+00:00')).astimezone(tz_ny)
            whoop_by_date[dt_ny.strftime('%Y-%m-%d')] = float(score)
        except: pass

# ── 4. 8Sleep ─────────────────────────────────────────────────────────────────
sleep_by_date = {}
eight_hist = DATA / 'eight_sleep_historical.csv'
if eight_hist.exists():
    try:
        for rec in json.load(open(eight_hist)):
            d = rec.get('date',''); score = rec.get('sleep_score') or rec.get('score')
            if d and score is not None: sleep_by_date[d] = float(score)
    except: pass
eight_dir = DATA / 'eight_sleep'
if eight_dir.exists():
    for jf in sorted(eight_dir.glob('*.json'))[-90:]:
        try:
            rec = json.load(open(jf))
            d = rec.get('date') or jf.stem
            score = rec.get('sleep_score') or rec.get('score')
            if d and score is not None and d not in sleep_by_date:
                sleep_by_date[d] = float(score)
        except: pass

# ── 5. Build records ──────────────────────────────────────────────────────────
all_dates = sorted(set(list(nutrition.keys()) + list(tonal_by_date.keys())))
records = []
for d in all_dates:
    nut = nutrition.get(d,{})
    records.append({'date':d,
        'calories': nut.get('calories',0), 'protein_g': nut.get('protein_g',0),
        'carbs_g': nut.get('carbs_g',0),  'fat_g': nut.get('fat_g',0),
        'tonal_volume': tonal_by_date.get(d,0),
        'whoop_recovery': whoop_by_date.get(d),
        'sleep_score': sleep_by_date.get(d)})

# ── 6. Analytics ──────────────────────────────────────────────────────────────
def pearson(xs, ys):
    n = len(xs)
    if n < 3: return 0
    mx = sum(xs)/n; my = sum(ys)/n
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx = math.sqrt(sum((x-mx)**2 for x in xs))
    dy = math.sqrt(sum((y-my)**2 for y in ys))
    return num/(dx*dy) if dx and dy else 0

scatter_pts = [{'date':records[i]['date'],'protein':records[i]['protein_g'],'volume':records[i+1]['tonal_volume']}
               for i in range(len(records)-1) if records[i]['protein_g']>0 and records[i+1]['tonal_volume']>0]

corr_prot_vol = pearson([p['protein'] for p in scatter_pts],[p['volume'] for p in scatter_pts]) if len(scatter_pts)>=3 else 0

carb_pairs = [(records[i]['carbs_g'], records[i+1]['tonal_volume'])
              for i in range(len(records)-1) if records[i]['carbs_g']>0 and records[i+1]['tonal_volume']>0]
corr_carb_vol = pearson([x for x,_ in carb_pairs],[y for _,y in carb_pairs]) if len(carb_pairs)>=3 else 0

sleep_pairs = [(records[i]['sleep_score'], records[i+1]['tonal_volume'])
               for i in range(len(records)-1) if records[i]['sleep_score'] is not None and records[i+1]['tonal_volume']>0]
corr_sleep_vol = pearson([x for x,_ in sleep_pairs],[y for _,y in sleep_pairs]) if len(sleep_pairs)>=3 else 0

prot_vals = [r['protein_g'] for r in records if r['protein_g']>0]
cal_vals  = [r['calories']  for r in records if r['calories']>0]
avg_protein  = sum(prot_vals)/len(prot_vals) if prot_vals else 0
avg_calories = sum(cal_vals)/len(cal_vals)   if cal_vals  else 0

HIGH_THRESH = 150
high_days = [r for r in records if r['protein_g']>HIGH_THRESH]
reg_days  = [r for r in records if 0<r['protein_g']<=HIGH_THRESH]
date_to_idx = {r['date']:i for i,r in enumerate(records)}
def avg_next_vol(day_list):
    vols = [records[date_to_idx[r['date']]+1]['tonal_volume']
            for r in day_list
            if date_to_idx.get(r['date'],-1)+1 < len(records) and
               records[date_to_idx[r['date']]+1]['tonal_volume']>0]
    return sum(vols)/len(vols) if vols else 0
high_avg_vol = avg_next_vol(high_days)
reg_avg_vol  = avg_next_vol(reg_days)
vol_delta_pct = (high_avg_vol-reg_avg_vol)/reg_avg_vol*100 if reg_avg_vol else 0

def corr_label(r):
    r=abs(r)
    if r>0.7: return 'Strong'
    if r>0.4: return 'Moderate'
    if r>0.2: return 'Weak'
    return 'Minimal'
def corr_color(r):
    r=abs(r)
    if r>0.7: return '#2ea043'
    if r>0.4: return '#f39c12'
    return '#8b949e'

# ── SVG: Scatter ──────────────────────────────────────────────────────────────
def build_scatter(pts):
    if not pts: return '<p style="color:#8b949e;text-align:center;padding:40px">No paired data</p>'
    W,H=800,400; ML,MR,MT,MB=60,30,30,50
    xs=[p['protein'] for p in pts]; ys=[p['volume'] for p in pts]
    xlo=max(0,min(xs)-max(xs)*0.1); xhi=max(xs)*1.1
    ymax=max(ys)*1.15
    def sx(v): return ML+(v-xlo)/(xhi-xlo)*(W-ML-MR)
    def sy(v): return MT+(1-v/ymax)*(H-MT-MB)
    n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
    denom=sum((x-mx)**2 for x in xs)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/denom if denom else 0
    intercept=my-slope*mx
    t1,t2=xlo,xhi
    circles=''.join(f'<circle cx="{sx(p["protein"]):.1f}" cy="{sy(p["volume"]):.1f}" r="6" fill="#f39c12" fill-opacity="0.75" stroke="#f39c12"><title>{p["date"]}: {p["protein"]:.0f}g → {p["volume"]:.0f} lbs</title></circle>' for p in pts)
    xticks=''.join(f'<line x1="{sx(v):.1f}" y1="{H-MB}" x2="{sx(v):.1f}" y2="{H-MB+5}" stroke="#333"/><text x="{sx(v):.1f}" y="{H-MB+18}" fill="#555" font-size="11" text-anchor="middle">{v:.0f}</text>' for v in [xlo+i*(xhi-xlo)/5 for i in range(6)])
    step_y=max(1,int(ymax/5/500)*500) or max(1,int(ymax/5))
    yticks=''.join(f'<line x1="{ML}" y1="{sy(v):.1f}" x2="{ML-5}" y2="{sy(v):.1f}" stroke="#333"/><text x="{ML-8}" y="{sy(v)+4:.1f}" fill="#555" font-size="10" text-anchor="end">{v//1000:.0f}k</text>' for v in range(0,int(ymax)+1,step_y))
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;display:block;margin:0 auto"><rect width="{W}" height="{H}" fill="#0d1117" rx="8"/><line x1="{ML}" y1="{MT}" x2="{ML}" y2="{H-MB}" stroke="#21262d"/><line x1="{ML}" y1="{H-MB}" x2="{W-MR}" y2="{H-MB}" stroke="#21262d"/><line x1="{sx(t1):.1f}" y1="{sy(slope*t1+intercept):.1f}" x2="{sx(t2):.1f}" y2="{sy(slope*t2+intercept):.1f}" stroke="#0a84ff" stroke-width="2" stroke-dasharray="5,4" opacity="0.9"/>{circles}{xticks}{yticks}<text x="{W//2}" y="{H-3}" fill="#555" font-size="12" text-anchor="middle">Protein Intake (g)</text><text x="14" y="{H//2}" fill="#555" font-size="12" text-anchor="middle" transform="rotate(-90,14,{H//2})">Next-Day Volume (lbs)</text></svg>'

# ── SVG: Macro Bars ───────────────────────────────────────────────────────────
def build_macro_bars(recs):
    last30=[r for r in recs if r['calories']>0][-30:]
    if not last30: return '<p style="color:#8b949e;padding:40px">No data</p>'
    W=800; ML,MR,MT,MB=100,20,20,35; BH=13; GAP=4
    max_cal=max((r['protein_g']*4+r['carbs_g']*4+r['fat_g']*9) for r in last30); avail=W-ML-MR
    bars=''
    for i,r in enumerate(last30):
        y=MT+i*(BH+GAP)
        total=r['protein_g']*4+r['carbs_g']*4+r['fat_g']*9
        if not total: continue
        s=avail/max_cal
        pw=r['protein_g']*4*s; cw=r['carbs_g']*4*s; fw=r['fat_g']*9*s
        dot=f'<circle cx="{ML-14}" cy="{y+BH/2:.1f}" r="4" fill="#2ea043"/>' if r['tonal_volume']>0 else ''
        bars+=f'{dot}<rect x="{ML}" y="{y}" width="{pw:.1f}" height="{BH}" fill="#f39c12"><title>{r["date"]}: {r["protein_g"]:.0f}g protein</title></rect><rect x="{ML+pw:.1f}" y="{y}" width="{cw:.1f}" height="{BH}" fill="#0a84ff"><title>{r["date"]}: {r["carbs_g"]:.0f}g carbs</title></rect><rect x="{ML+pw+cw:.1f}" y="{y}" width="{fw:.1f}" height="{BH}" fill="#2ea043"><title>{r["date"]}: {r["fat_g"]:.0f}g fat</title></rect><text x="{ML-18}" y="{y+BH-2}" fill="#555" font-size="9" text-anchor="end">{r["date"][5:]}</text>'
    n=len(last30); H=MT+n*(BH+GAP)+MB+10
    leg=f'<rect x="{ML}" y="{H-22}" width="10" height="10" fill="#f39c12"/><text x="{ML+14}" y="{H-13}" fill="#aaa" font-size="11">Protein</text><rect x="{ML+72}" y="{H-22}" width="10" height="10" fill="#0a84ff"/><text x="{ML+86}" y="{H-13}" fill="#aaa" font-size="11">Carbs</text><rect x="{ML+135}" y="{H-22}" width="10" height="10" fill="#2ea043"/><text x="{ML+149}" y="{H-13}" fill="#aaa" font-size="11">Fat</text><circle cx="{ML+205}" cy="{H-17}" r="4" fill="#2ea043"/><text x="{ML+213}" y="{H-13}" fill="#aaa" font-size="11">Training day</text>'
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;display:block;margin:0 auto"><rect width="{W}" height="{H}" fill="#0d1117" rx="8"/>{bars}{leg}</svg>'

# ── SVG: Recovery Chain ───────────────────────────────────────────────────────
def build_recovery_chain(recs):
    last90=recs[-90:]; W,H=800,350; ML,MR,MT,MB=55,30,30,45
    def norm(v,lo,hi): return (v-lo)/(hi-lo)*100 if hi!=lo else 50
    sleep_raw=[(i,r['sleep_score']) for i,r in enumerate(last90) if r['sleep_score'] is not None]
    whoop_raw=[(i,r['whoop_recovery']) for i,r in enumerate(last90) if r['whoop_recovery'] is not None]
    prot_raw =[(i,r['protein_g']) for i,r in enumerate(last90) if r['protein_g']>0]
    def line_path(raw,lo,hi,color):
        if not raw: return ''
        n=max(1,len(last90)-1)
        pts=[(ML+i/n*(W-ML-MR), MT+(1-norm(v,lo,hi)/100)*(H-MT-MB)) for i,v in raw]
        d='M '+' L '.join(f'{x:.1f},{y:.1f}' for x,y in pts)
        lx,ly=pts[-1]; lv=raw[-1][1]
        return f'<path d="{d}" stroke="{color}" stroke-width="2" fill="none" opacity="0.9"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{color}"/><text x="{lx+5:.1f}" y="{ly+4:.1f}" fill="{color}" font-size="10">{lv:.0f}</text>'
    s_lo,s_hi=(min(v for _,v in sleep_raw),max(v for _,v in sleep_raw)) if sleep_raw else (0,100)
    w_lo,w_hi=(min(v for _,v in whoop_raw),max(v for _,v in whoop_raw)) if whoop_raw else (0,100)
    p_lo,p_hi=(min(v for _,v in prot_raw),max(v for _,v in prot_raw)) if prot_raw else (0,300)
    yticks=''.join(f'<line x1="{ML}" y1="{MT+(1-v/100)*(H-MT-MB):.1f}" x2="{ML-5}" y2="{MT+(1-v/100)*(H-MT-MB):.1f}" stroke="#333"/><text x="{ML-8}" y="{MT+(1-v/100)*(H-MT-MB)+4:.1f}" fill="#555" font-size="10" text-anchor="end">{v}</text>' for v in [0,25,50,75,100])
    xlabels=''.join(f'<text x="{ML+i/max(1,len(last90)-1)*(W-ML-MR):.1f}" y="{H-MB+14}" fill="#555" font-size="10" text-anchor="middle">{r["date"][5:]}</text>' for i,r in enumerate(last90) if i%15==0)
    legend=f'<line x1="{ML}" y1="{H-14}" x2="{ML+20}" y2="{H-14}" stroke="#0a84ff" stroke-width="2"/><text x="{ML+24}" y="{H-10}" fill="#aaa" font-size="11">Sleep Score</text><line x1="{ML+105}" y1="{H-14}" x2="{ML+125}" y2="{H-14}" stroke="#f85149" stroke-width="2"/><text x="{ML+129}" y="{H-10}" fill="#aaa" font-size="11">WHOOP Recovery</text><line x1="{ML+240}" y1="{H-14}" x2="{ML+260}" y2="{H-14}" stroke="#f39c12" stroke-width="2"/><text x="{ML+264}" y="{H-10}" fill="#aaa" font-size="11">Protein (normalized)</text>'
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;display:block;margin:0 auto"><rect width="{W}" height="{H}" fill="#0d1117" rx="8"/><line x1="{ML}" y1="{MT}" x2="{ML}" y2="{H-MB}" stroke="#21262d"/><line x1="{ML}" y1="{H-MB}" x2="{W-MR}" y2="{H-MB}" stroke="#21262d"/>{yticks}{xlabels}{line_path(sleep_raw,s_lo,s_hi,"#0a84ff")}{line_path(whoop_raw,w_lo,w_hi,"#f85149")}{line_path(prot_raw,p_lo,p_hi,"#f39c12")}{legend}</svg>'

# ── SVG: Heatmap ──────────────────────────────────────────────────────────────
def build_heatmap(recs):
    nut_recs=[r for r in recs if r['protein_g']>0][-42:]
    if not nut_recs: return '<p style="color:#8b949e">No data</p>'
    max_p=max(r['protein_g'] for r in nut_recs)
    CELL=38; GAP=4; W=7*(CELL+GAP)+70; days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    weeks=defaultdict(dict)
    for r in nut_recs:
        dt=datetime.strptime(r['date'],'%Y-%m-%d')
        weeks[dt.isocalendar()[:2]][dt.weekday()]=r
    sw=sorted(weeks.keys())[-6:]
    rows=''
    for wi,wk in enumerate(sw):
        y0=wi*(CELL+GAP)+25
        rows+=f'<text x="0" y="{y0+CELL//2+5}" fill="#555" font-size="11">W{wk[1]}</text>'
        for dow in range(7):
            x=50+dow*(CELL+GAP); r=weeks[wk].get(dow)
            if r:
                pct=r['protein_g']/max_p
                rc=int(0x16+pct*(0xf3-0x16)); gc=int(0x1b+pct*(0x9c-0x1b)); bc=int(0x22+pct*(0x12-0x22))
                color=f'#{rc:02x}{gc:02x}{bc:02x}'
                dot=f'<circle cx="{x+CELL-6}" cy="{y0+6}" r="3" fill="#2ea043"/>' if r['tonal_volume']>0 else ''
                rows+=f'<rect x="{x}" y="{y0}" width="{CELL}" height="{CELL}" rx="4" fill="{color}"><title>{r["date"]}: {r["protein_g"]:.0f}g</title></rect><text x="{x+CELL//2}" y="{y0+CELL//2+5}" fill="{"#000" if pct>0.65 else "#ccc"}" font-size="10" text-anchor="middle">{r["protein_g"]:.0f}</text>{dot}'
            else:
                rows+=f'<rect x="{x}" y="{y0}" width="{CELL}" height="{CELL}" rx="4" fill="#161b22"/>'
    H=len(sw)*(CELL+GAP)+50
    hdrs=''.join(f'<text x="{50+i*(CELL+GAP)+CELL//2}" y="16" fill="#555" font-size="11" text-anchor="middle">{d}</text>' for i,d in enumerate(days))
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px;display:block;margin:0 auto"><rect width="{W}" height="{H}" fill="#0d1117" rx="8"/>{hdrs}{rows}</svg>'

# ── Assemble HTML ─────────────────────────────────────────────────────────────
scatter_svg        = build_scatter(scatter_pts)
macro_bars_svg     = build_macro_bars(records)
recovery_chain_svg = build_recovery_chain(records)
heatmap_svg        = build_heatmap(records)

def corr_bar(r):
    pct=abs(r)*100; color=corr_color(r); sign='+' if r>=0 else '−'
    return f'<div style="display:flex;align-items:center;gap:12px"><div style="flex:1;background:#21262d;border-radius:4px;height:8px"><div style="width:{pct:.1f}%;background:{color};height:8px;border-radius:4px"></div></div><span style="color:{color};font-weight:600;min-width:70px">{sign}{abs(r):.2f} ({corr_label(r)})</span></div>'

NAV = [('🏠 Home','../index.html'),('📅 Calendars','../calendars/'),('💪 Strength','../strength/'),('🏃 Cardio','../cardio/'),('💤 Recovery','../recovery/'),('🥗 Nutrition','../nutrition/'),('🔗 Nutrition Bridge','../nutrition_performance/')]
nav_html='\n'.join(f'<a href="{u}">{l}</a>' for l,u in NAV)
generated_at=datetime.now().strftime('%Y-%m-%d %H:%M')

html=f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Nutrition ↔ Performance Bridge</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh}}
nav{{background:#161b22;border-bottom:1px solid #21262d;padding:12px 24px;display:flex;gap:20px;flex-wrap:wrap;align-items:center;position:sticky;top:0;z-index:100}}
nav a{{color:#8b949e;text-decoration:none;font-size:13px;transition:color .2s}}
nav a:hover,nav a:last-child{{color:#f39c12}}
.container{{max-width:1100px;margin:0 auto;padding:32px 20px}}
.hero{{text-align:center;margin-bottom:40px}}
.hero h1{{font-size:2.2rem;font-weight:700;color:#f39c12;margin-bottom:8px}}
.hero p{{color:#8b949e;font-size:1rem}}
.stats-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:36px}}
.stat-card{{background:#161b22;border:1px solid #21262d;border-radius:12px;padding:20px;text-align:center}}
.stat-val{{font-size:2rem;font-weight:700;color:#f39c12}}
.stat-lbl{{color:#8b949e;font-size:.85rem;margin-top:4px}}
.section{{background:#161b22;border:1px solid #21262d;border-radius:12px;padding:24px;margin-bottom:28px}}
.section h2{{font-size:1.1rem;font-weight:600;color:#e6edf3;margin-bottom:16px;border-left:3px solid #f39c12;padding-left:10px}}
.corr-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
.corr-item{{background:#0d1117;border-radius:8px;padding:14px}}
.corr-item label{{display:block;color:#8b949e;font-size:.8rem;margin-bottom:8px}}
.impact-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
.impact-card{{background:#0d1117;border-radius:10px;padding:20px;text-align:center;border:1px solid #21262d}}
.impact-card .val{{font-size:1.8rem;font-weight:700;color:#f39c12}}
.impact-card .sub{{color:#8b949e;font-size:.8rem;margin-top:4px}}
.delta{{font-size:1rem;font-weight:600;padding:5px 12px;border-radius:20px;display:inline-block;margin-top:10px}}
.pos{{background:rgba(46,160,67,.2);color:#2ea043}}.neg{{background:rgba(248,81,73,.2);color:#f85149}}
footer{{text-align:center;color:#30363d;font-size:.75rem;padding:32px 0}}
</style>
</head>
<body>
<nav>{nav_html}</nav>
<div class="container">
  <div class="hero">
    <h1>🥗 Nutrition ↔ Performance Bridge</h1>
    <p>How your macros fuel (or limit) your training output — correlations across protein, carbs, sleep &amp; Tonal volume</p>
  </div>

  <div class="stats-row">
    <div class="stat-card"><div class="stat-val">{avg_protein:.0f}g</div><div class="stat-lbl">Avg Daily Protein</div></div>
    <div class="stat-card"><div class="stat-val">{avg_calories:.0f}</div><div class="stat-lbl">Avg Daily Calories</div></div>
    <div class="stat-card"><div class="stat-val" style="color:{corr_color(corr_prot_vol)}">{corr_prot_vol:+.2f}</div><div class="stat-lbl">Protein → Volume Correlation</div></div>
    <div class="stat-card"><div class="stat-val">{len(records)}</div><div class="stat-lbl">Days with Data</div></div>
  </div>

  <div class="section">
    <h2>A. Protein Intake → Next-Day Tonal Volume</h2>
    <p style="color:#8b949e;font-size:.85rem;margin-bottom:16px">{len(scatter_pts)} paired data points. Dashed blue = trend line.</p>
    {scatter_svg}
  </div>

  <div class="section">
    <h2>Correlation Coefficients</h2>
    <div class="corr-row">
      <div class="corr-item"><label>Protein (g) → Next-Day Volume (lbs)</label>{corr_bar(corr_prot_vol)}</div>
      <div class="corr-item"><label>Carbs (g) → Next-Day Volume (lbs)</label>{corr_bar(corr_carb_vol)}</div>
      <div class="corr-item"><label>Sleep Score → Next-Day Volume (lbs)</label>{corr_bar(corr_sleep_vol)}</div>
    </div>
  </div>

  <div class="section">
    <h2>B. Macro Breakdown + Training Days (Last 30)</h2>
    <p style="color:#8b949e;font-size:.85rem;margin-bottom:16px">Green dot = training day. Bars show protein / carbs / fat caloric split.</p>
    {macro_bars_svg}
  </div>

  <div class="section">
    <h2>C. Recovery Chain (Last 90 Days)</h2>
    <p style="color:#8b949e;font-size:.85rem;margin-bottom:16px">All metrics normalized to 0–100 scale for comparison.</p>
    {recovery_chain_svg}
  </div>

  <div class="section">
    <h2>D. High-Protein Days Impact (threshold: {HIGH_THRESH}g)</h2>
    <div class="impact-cards">
      <div class="impact-card">
        <div class="val">{len(high_days)}</div><div class="sub">High-Protein Days (&gt;{HIGH_THRESH}g)</div>
        <div style="color:#8b949e;font-size:.85rem;margin-top:8px">Avg next-day volume: <strong style="color:#f39c12">{high_avg_vol:,.0f} lbs</strong></div>
      </div>
      <div class="impact-card">
        <div class="val">{len(reg_days)}</div><div class="sub">Regular Days (≤{HIGH_THRESH}g)</div>
        <div style="color:#8b949e;font-size:.85rem;margin-top:8px">Avg next-day volume: <strong style="color:#8b949e">{reg_avg_vol:,.0f} lbs</strong></div>
      </div>
      <div class="impact-card">
        <div class="val">{'↑' if vol_delta_pct>=0 else '↓'}{abs(vol_delta_pct):.1f}%</div>
        <div class="sub">Volume Delta</div>
        <div class="delta {'pos' if vol_delta_pct>=0 else 'neg'}">High-protein days {'boost' if vol_delta_pct>=0 else 'reduce'} output by {abs(vol_delta_pct):.1f}%</div>
      </div>
    </div>
  </div>

  <div class="section">
    <h2>E. Weekly Protein Heatmap</h2>
    <p style="color:#8b949e;font-size:.85rem;margin-bottom:16px">Cell brightness = protein intake (g). Green dot = training day.</p>
    {heatmap_svg}
  </div>
</div>
<footer>Generated {generated_at} · Nutrition ↔ Performance Bridge</footer>
</body>
</html>'''

with open(OUT_FILE,'w') as f:
    f.write(html)

sz = OUT_FILE.stat().st_size
print(f'Generated: {OUT_FILE}')
print(f'Size: {sz:,} bytes')
print(f'Records: {len(records)} days, {len(scatter_pts)} scatter points')
print(f'Corr prot→vol: {corr_prot_vol:.3f}')
