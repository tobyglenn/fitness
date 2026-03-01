#!/usr/bin/env python3
"""Day Detail Page Generator - ~/clawd/docs/day/index.html"""
import json, glob, csv, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
DATA_BASE = "/Users/tobyglennpeters/clawd/data"
OUT_DIR = "/Users/tobyglennpeters/clawd/docs/day"
OUT_FILE = os.path.join(OUT_DIR, "index.html")
os.makedirs(OUT_DIR, exist_ok=True)

# Load unified timeline
print("Loading unified timeline...")
with open(f"{DATA_BASE}/unified_training_timeline.json") as f:
    unified = json.load(f)

# Load WHOOP
print("Loading WHOOP...")
whoop_by_date = {}
whoop_path = "/Users/tobyglennpeters/.openclaw/workspace/scripts/data/whoop_v2_latest.json"
if os.path.exists(whoop_path):
    with open(whoop_path) as f:
        whoop_raw = json.load(f)
    for rec in whoop_raw.get("recovery", {}).get("records", []):
        score_data = rec.get("score", {})
        created = rec.get("created_at", "")
        if created:
            d = created[:10]
            whoop_by_date[d] = {
                "recovery_score": score_data.get("recovery_score"),
                "hrv_rmssd": score_data.get("hrv_rmssd_milli"),
                "resting_hr": score_data.get("resting_heart_rate"),
            }
for date_str, entry in unified.items():
    w = entry.get("whoop")
    if w and w.get("recovery_score") is not None and date_str not in whoop_by_date:
        whoop_by_date[date_str] = {
            "recovery_score": w.get("recovery_score"),
            "hrv_rmssd": w.get("hrv_rmssd"),
            "resting_hr": w.get("resting_hr"),
        }

# Load 8Sleep
print("Loading 8Sleep...")
eight_by_date = {}
for sf in glob.glob(f"{DATA_BASE}/eight_sleep/*.json"):
    try:
        with open(sf) as f:
            s = json.load(f)
        date_str = s.get("date", os.path.basename(sf).replace(".json",""))
        breakdown = s.get("sleep_breakdown", {})
        eight_by_date[date_str] = {
            "sleep_score": s.get("sleep_score"),
            "time_slept_hours": s.get("time_slept_hours"),
            "time_in_bed_hours": s.get("time_in_bed_hours"),
            "deep_hours": breakdown.get("deep"),
            "rem_hours": breakdown.get("rem"),
            "light_hours": breakdown.get("light"),
            "awake_hours": breakdown.get("awake"),
            "heart_rate_avg": s.get("heart_rate", {}).get("average") if isinstance(s.get("heart_rate"), dict) else None,
        }
    except Exception:
        pass

# Load Garmin
print("Loading Garmin...")
garmin_by_date = {}
with open(f"{DATA_BASE}/garmin_all_activities.json") as f:
    garmin_raw = json.load(f)
for act in garmin_raw.get("activities", []):
    start = act.get("startTimeLocal", act.get("date", ""))
    if not start:
        continue
    date_str = start[:10]
    dist_miles = act.get("distance_miles")
    if dist_miles is None and act.get("distance"):
        dist_miles = round(act["distance"] / 1609.344, 2)
    dur_min = act.get("duration_min")
    if dur_min is None and act.get("duration"):
        dur_min = round(act["duration"] / 60, 1)
    entry = {
        "activityType": act.get("activityType", ""),
        "activityName": act.get("activityName", ""),
        "distance_miles": dist_miles,
        "duration_min": dur_min,
        "averageHR": act.get("averageHR"),
        "maxHR": act.get("maxHR"),
        "elevationGain": act.get("elevationGain"),
        "avgPace": round(dur_min / dist_miles, 2) if (dist_miles and dist_miles > 0 and dur_min) else None,
    }
    garmin_by_date.setdefault(date_str, []).append(entry)

# Load Tonal
print("Loading Tonal...")
tonal_by_date = {}
tonal_files = sorted(glob.glob(f"{DATA_BASE}/tonal/tonal_workouts_*.json"))
if tonal_files:
    with open(tonal_files[-1]) as f:
        tonal_raw = json.load(f)
    for workout in tonal_raw.get("workouts", []):
        begin_utc = workout.get("beginTime", "")
        if not begin_utc:
            continue
        try:
            dt_utc = datetime.fromisoformat(begin_utc.replace("Z", "+00:00"))
            dt_et = dt_utc.astimezone(EASTERN)
            date_str = dt_et.strftime("%Y-%m-%d")
        except Exception:
            continue
        content = workout.get("contentCard") or {}
        workout_name = content.get("title") or content.get("name") or workout.get("workoutType", "Tonal Workout")
        dur_min = round(workout.get("totalDuration", 0) / 60)
        total_vol = workout.get("totalVolume", 0)
        exercises = {}
        for sa in workout.get("workoutSetActivity", []):
            mid = sa.get("movementId", "")
            if not mid:
                continue
            avg_w = sa.get("avgWeight") or sa.get("baseWeight") or 0
            reps = sa.get("reps") or sa.get("repCount") or sa.get("prescribedReps") or 0
            vol = sa.get("volume") or 0
            if mid not in exercises:
                exercises[mid] = {"name": mid[:20], "sets": 0, "reps": reps,
                                   "weight_lbs": round(float(avg_w), 1) if avg_w else 0, "volume": 0}
            exercises[mid]["sets"] += 1
            exercises[mid]["volume"] += vol
        tonal_by_date.setdefault(date_str, []).append({
            "workout_name": workout_name,
            "begin_time": dt_et.strftime("%I:%M %p"),
            "duration_min": dur_min,
            "total_volume_lbs": total_vol,
            "total_sets": workout.get("totalSets", 0),
            "total_reps": workout.get("totalReps", 0),
            "exercises": list(exercises.values())[:20],
        })

# Load Cronometer
print("Loading Cronometer...")
crono_by_date = {}
crono_path = f"{DATA_BASE}/cronometer_historical.csv"
if os.path.exists(crono_path):
    try:
        with open(crono_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_str = (row.get("Date") or row.get("date",""))[:10]
                if not date_str:
                    continue
                try:
                    crono_by_date[date_str] = {
                        "calories": float(row.get("Energy (kcal)", row.get("Calories",0)) or 0),
                        "protein": float(row.get("Protein (g)", row.get("Protein",0)) or 0),
                        "carbs": float(row.get("Carbohydrates (g)", row.get("Carbs",0)) or 0),
                        "fat": float(row.get("Fat (g)", row.get("Fat",0)) or 0),
                    }
                except Exception:
                    pass
    except Exception as e:
        print(f"Cronometer warning: {e}")

# Assemble
print("Assembling dataset...")
all_dates = (set(unified.keys()) | set(whoop_by_date.keys()) |
             set(eight_by_date.keys()) | set(garmin_by_date.keys()) | set(tonal_by_date.keys()))
day_data = {d: {"date": d, "whoop": whoop_by_date.get(d), "eight_sleep": eight_by_date.get(d),
                "garmin": garmin_by_date.get(d), "tonal": tonal_by_date.get(d),
                "nutrition": crono_by_date.get(d)} for d in sorted(all_dates)}
print(f"Total days: {len(day_data)}")
data_json = json.dumps(day_data, ensure_ascii=True)

# HTML template parts (split around data injection point)
HTML_BEFORE = open("/Users/tobyglennpeters/clawd/docs/scripts/_day_detail_before.html").read()
HTML_AFTER = open("/Users/tobyglennpeters/clawd/docs/scripts/_day_detail_after.html").read()

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write(HTML_BEFORE)
    f.write(data_json)
    f.write(HTML_AFTER)

size = os.path.getsize(OUT_FILE)
print(f"Written: {OUT_FILE} ({size:,} bytes)")
if size < 3072:
    print("ERROR: File too small", file=sys.stderr)
    sys.exit(1)
print("SUCCESS")
