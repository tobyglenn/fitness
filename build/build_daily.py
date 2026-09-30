#!/usr/bin/env python3
"""Build data/daily/<YYYY>.json — the per-day metric series behind every chart.

Reads the raw sync data the report generators use (the same fields and
units as generate_morning_report_content.py) and writes one compact,
column-oriented file per year:

  {"fields": ["recovery", "hrv", ...], "days": {"2026-09-24": [40, 27.9, ...]}}

Days are merged into existing year files, so re-running with a partial raw
data directory never erases history. Any value still missing is back-filled
from the metric cards stored in data/reports/morning (what the original
report displayed).

Usage: build_daily.py [--data-dir ~/clawd/data] [--since YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / "data" / "daily"
REPORTS_DIR = ROOT / "data" / "reports"

FIELDS = [
    "recovery",        # WHOOP recovery %
    "hrv",             # WHOOP HRV rMSSD ms
    "rhr",             # WHOOP resting HR
    "strain",          # WHOOP day (cycle) strain
    "kcal_out",        # WHOOP kcal burned + Garmin active calories
    "workout_strain",  # WHOOP workout/activity strain (sum)
    "bjj_strain",      # WHOOP BJJ/grappling strain
    "w_sleep_h",       # WHOOP time in bed
    "w_deep_h",
    "w_rem_h",
    "w_debt_h",        # WHOOP need from sleep debt
    "g_bb",            # Garmin body battery (most recent)
    "g_sleep_score",
    "g_stress",
    "g_sleep_h",
    "g_debt_h",
    "run_mi",          # Garmin running distance
    "aero_te",         # Garmin aerobic training effect (max of the day)
    "anaero_te",
    "e_score",         # Eight Sleep score
    "e_sleep_h",
    "volume_lbs",      # Speediance + Tonal lifting volume
    "kcal_in",         # Cronometer
    "protein_g",
    "carbs_g",
    "fat_g",
    "weight_lbs",      # Cronometer body weight
]

RUN_TYPES = {"running", "treadmill_running", "trail_running", "track_running"}
BJJ_TERMS = ("jiu jitsu", "jiu-jitsu", "bjj", "grappling", "martial arts", "wrestling")


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _utc_date(s: str) -> str | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _local_date(start: str, offset: str | None) -> str | None:
    try:
        utc = datetime.fromisoformat(start.replace("Z", "+00:00"))
        off = str(offset or "+00:00")
        sign = 1 if off.startswith("+") else -1
        h, m = map(int, off[1:].split(":"))
        return (utc + sign * timedelta(hours=h, minutes=m)).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return _utc_date(start)


class Days:
    def __init__(self):
        self.d: dict[str, dict] = defaultdict(dict)

    def set(self, date, field, value, digits=2):
        v = _num(value)
        if date and v is not None:
            self.d[date][field] = round(v, digits)

    def add(self, date, field, value, digits=2):
        v = _num(value)
        if date and v is not None:
            self.d[date][field] = round(self.d[date].get(field, 0) + v, digits)


def load_whoop(data_dir: Path, days: Days) -> None:
    p = data_dir / "whoop_v2_latest.json"
    if not p.exists():
        return
    w = json.loads(p.read_text())
    for r in w.get("recovery", {}).get("records", []):
        if not isinstance(r, dict) or not r.get("created_at"):
            continue
        d, s = _utc_date(r["created_at"]), r.get("score") or {}
        days.set(d, "recovery", s.get("recovery_score"), 0)
        days.set(d, "hrv", s.get("hrv_rmssd_milli"), 1)
        days.set(d, "rhr", s.get("resting_heart_rate"), 0)
    cyc = defaultdict(list)
    for c in w.get("cycle", {}).get("records", []):
        if isinstance(c, dict) and c.get("end"):
            cyc[_utc_date(c["end"])].append(c.get("score") or {})
    for d, scores in cyc.items():
        strains = [x["strain"] for x in scores if _num(x.get("strain")) is not None]
        kj = [x["kilojoule"] for x in scores if _num(x.get("kilojoule")) is not None]
        if strains:
            days.set(d, "strain", sum(strains) / len(strains), 1)
        if kj:
            days.add(d, "kcal_out", sum(kj) / len(kj) / 4.184, 0)
    for wk in w.get("workouts", {}).get("records", []):
        if not isinstance(wk, dict):
            continue
        start = wk.get("start") or wk.get("start_time")
        if not start:
            continue
        d = _local_date(start, wk.get("timezone_offset"))
        strain = (wk.get("score") or {}).get("strain")
        sport = str(wk.get("sport") or wk.get("sport_name") or wk.get("activity_type") or "").lower().replace("-", " ").replace("_", " ")
        days.add(d, "workout_strain", strain, 1)
        if any(t.replace("-", " ") in sport for t in BJJ_TERMS):
            days.add(d, "bjj_strain", strain, 1)
    slp = defaultdict(list)
    for s in w.get("sleep", {}).get("records", []):
        end = isinstance(s, dict) and (s.get("end_time") or s.get("end"))
        if end:
            slp[_utc_date(end)].append(s.get("score") or {})
    for d, scores in slp.items():
        def mean(fn):
            vals = [v for v in (fn(x) for x in scores) if v is not None]
            return sum(vals) / len(vals) if vals else None
        st = lambda x, k: _num((x.get("stage_summary") or {}).get(k))
        days.set(d, "w_sleep_h", mean(lambda x: (st(x, "total_in_bed_time_milli") or 0) / 3.6e6), 2)
        days.set(d, "w_deep_h", mean(lambda x: (st(x, "total_slow_wave_sleep_time_milli") or 0) / 3.6e6), 2)
        days.set(d, "w_rem_h", mean(lambda x: (st(x, "total_rem_sleep_time_milli") or 0) / 3.6e6), 2)
        days.set(d, "w_debt_h", mean(lambda x: (_num((x.get("sleep_needed") or {}).get("need_from_sleep_debt_milli")) or 0) / 3.6e6), 2)


def _garmin_sleep_score(payload: dict):
    cands = [payload.get("sleep"), payload.get("dailySleepDTO"), payload.get("stats"), payload]
    sleep = payload.get("sleep")
    if isinstance(sleep, dict):
        cands += [sleep.get("dailySleepDTO"), sleep.get("dailySleepData")]
    for obj in cands:
        if not isinstance(obj, dict):
            continue
        scores = obj.get("sleepScores") or obj.get("sleep_score") or obj.get("sleepScore")
        if isinstance(scores, dict):
            overall = scores.get("overall") or scores.get("overallScore")
            v = _num(overall.get("value")) if isinstance(overall, dict) else _num(overall)
        else:
            v = _num(scores)
        if v is not None:
            return v
        for key in ("sleepScore", "overallSleepScore"):
            if _num(obj.get(key)) is not None:
                return _num(obj.get(key))
    return None


def load_garmin(data_dir: Path, days: Days, since: str) -> None:
    for f in sorted(glob.glob(str(data_dir / "garmin" / "*.json"))):
        if Path(f).stem < since:
            continue
        try:
            payload = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        s = payload.get("stats") or {}
        d = s.get("calendarDate") or payload.get("date") or Path(f).stem
        slp = (payload.get("sleep") or {}).get("dailySleepDTO") or {}
        need = slp.get("sleepNeed") or {}
        if _num(need.get("actual")) is not None:
            debt_h = (need["actual"] - (need.get("baseline") or 470)) / 60
        else:
            debt_h = (_num((s.get("bodyBatteryDynamicFeedbackEvent") or {}).get("sleepDebtSeconds")) or 0) / 3600
        days.set(d, "g_bb", s.get("bodyBatteryMostRecentValue"), 0)
        days.set(d, "g_sleep_score", _garmin_sleep_score(payload), 0)
        days.set(d, "g_stress", s.get("averageStressLevel"), 0)
        days.set(d, "g_sleep_h", (_num(s.get("sleepingSeconds")) or 0) / 3600 or None, 2)
        days.set(d, "g_debt_h", debt_h, 2)
        days.add(d, "kcal_out", s.get("activeCalories"), 0)
        run_mi, aero, anaero = 0.0, [], []
        for a in payload.get("activities") or []:
            at = a.get("activityType")
            key = at.get("typeKey", "") if isinstance(at, dict) else str(at or "")
            if key in RUN_TYPES:
                run_mi += (_num(a.get("distance")) or 0) * 0.000621371
            if _num(a.get("aerobicTrainingEffect")) is not None:
                aero.append(_num(a["aerobicTrainingEffect"]))
            if _num(a.get("anaerobicTrainingEffect")) is not None:
                anaero.append(_num(a["anaerobicTrainingEffect"]))
        if run_mi:
            days.set(d, "run_mi", run_mi, 2)
        if aero:
            days.set(d, "aero_te", max(aero), 1)
        if anaero:
            days.set(d, "anaero_te", max(anaero), 1)


def load_eight_sleep(data_dir: Path, days: Days) -> None:
    for f in glob.glob(str(data_dir / "eight_sleep" / "*.json")):
        try:
            content = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for e in content if isinstance(content, list) else [content]:
            if not isinstance(e, dict) or not e.get("date"):
                continue
            b = e.get("sleep_breakdown") or {}
            total = e.get("time_slept_hours") or (
                ((b.get("light") or 0) + (b.get("deep") or 0) + (b.get("rem") or 0)) / 3600 if b else None)
            days.set(e["date"], "e_score", e.get("sleep_score") or e.get("score"), 0)
            days.set(e["date"], "e_sleep_h", total, 2)


def load_speediance(data_dir: Path, days: Days) -> None:
    per_day: dict[str, dict] = defaultdict(dict)  # date -> {code: volume}
    for f in glob.glob(str(data_dir / "speediance_sync_*.json")):
        try:
            entries = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for e in entries if isinstance(entries, list) else entries.get("workouts", []):
            d = e.get("date") or str(e.get("finishTime") or "")[:10]
            key = e.get("code") or e.get("trainingId") or e.get("finishTime") or len(per_day[d])
            vol = _num(e.get("totalCapacity", e.get("total_volume_lbs")))
            if d and vol is not None:
                per_day[d][key] = vol
    full = data_dir / "speediance_full_history.json"
    if full.exists():
        for e in json.loads(full.read_text()).get("all_workouts", []):
            d = str(e.get("finishTime") or "")[:10]
            key = e.get("code") or e.get("trainingId") or e.get("finishTime")
            vol = _num(e.get("totalCapacity"))
            if d and vol is not None:
                per_day[d].setdefault(key, vol)
    for d, vols in per_day.items():
        days.set(d, "volume_lbs", sum(vols.values()), 0)


def load_tonal(data_dir: Path, days: Days) -> None:
    """Tonal lifting volume (pre-Speediance history) from the unified timeline."""
    p = data_dir / "unified_training_timeline.json"
    if not p.exists():
        return
    for d, entry in json.loads(p.read_text()).items():
        tonal = (entry or {}).get("tonal") or {}
        days.add(d, "volume_lbs", tonal.get("total_volume_lbs"), 0)


def load_cronometer(data_dir: Path, days: Days) -> None:
    p = data_dir / "cronometer_historical.csv"
    if not p.exists():
        return
    best: dict[str, dict] = {}
    with p.open(newline="") as fh:
        for row in csv.DictReader(fh):
            d = (row.get("Date") or "")[:10]
            if d and (_num(row.get("Energy (kcal)")) or 0) >= (_num((best.get(d) or {}).get("Energy (kcal)")) or 0):
                best[d] = row
    for d, row in best.items():
        days.set(d, "kcal_in", row.get("Energy (kcal)"), 0)
        days.set(d, "protein_g", row.get("Protein (g)"), 0)
        days.set(d, "carbs_g", row.get("Carbs (g)"), 0)
        days.set(d, "fat_g", row.get("Fat (g)"), 0)
        if _num(row.get("Weight (lbs)")):
            days.set(d, "weight_lbs", row.get("Weight (lbs)"), 1)


# Morning report metric-card labels → series fields (fallback only).
CARD_FIELDS = {
    "WHOOP RECOVERY": "recovery", "GARMIN BB": "g_bb", "GARMIN SLEEP SCORE": "g_sleep_score",
    "8SLEEP SCORE": "e_score", "AVG STRESS": "g_stress", "DEEP SLEEP": "w_deep_h",
    "REM SLEEP": "w_rem_h", "WHOOP TOTAL SLEEP": "w_sleep_h", "GARMIN TOTAL SLEEP": "g_sleep_h",
    "8SLEEP TOTAL SLEEP": "e_sleep_h",
}


def backfill_from_reports(days: Days) -> int:
    filled = 0
    for f in glob.glob(str(REPORTS_DIR / "morning" / "*" / "*.json")):
        doc = json.loads(Path(f).read_text())
        for card in doc.get("metrics") or []:
            field = CARD_FIELDS.get(card.get("label", "").upper())
            m = re.match(r"^-?\d+(\.\d+)?", card.get("value", ""))
            if field and m and field not in days.d.get(doc["date"], {}):
                v = float(m.group(0))
                if v:  # the originals print 0 / N/A for missing sources
                    days.set(doc["date"], field, v, 2)
                    filled += 1
    return filled


def write_years(days: Days) -> None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, dict] = defaultdict(dict)
    for d, vals in days.d.items():
        if re.match(r"^\d{4}-\d{2}-\d{2}$", d or ""):
            by_year[d[:4]][d] = vals
    for year, new in sorted(by_year.items()):
        path = DAILY_DIR / f"{year}.json"
        merged: dict[str, dict] = {}
        if path.exists():
            old = json.loads(path.read_text())
            for d, row in old["days"].items():
                merged[d] = {k: v for k, v in zip(old["fields"], row) if v is not None}
        for d, vals in new.items():
            merged.setdefault(d, {}).update(vals)
        out = {
            "fields": FIELDS,
            "days": {
                d: [merged[d].get(k) for k in FIELDS]
                for d in sorted(merged) if any(merged[d].get(k) is not None for k in FIELDS)
            },
        }
        text = json.dumps(out, separators=(",", ":"))
        # one day per line keeps git diffs readable
        text = text.replace('],"', '],\n"').replace('"days":{', '"days":{\n')
        path.write_text(text + "\n")
        print(f"  {path.relative_to(ROOT)}: {len(out['days'])} days")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", Path.home() / "clawd" / "data")))
    ap.add_argument("--since", default="2016-01-01", help="skip Garmin day files before this date")
    args = ap.parse_args()

    days = Days()
    if args.data_dir.exists():
        load_whoop(args.data_dir, days)
        load_garmin(args.data_dir, days, args.since)
        load_eight_sleep(args.data_dir, days)
        load_speediance(args.data_dir, days)
        load_tonal(args.data_dir, days)
        load_cronometer(args.data_dir, days)
    else:
        print(f"raw data dir {args.data_dir} not found; back-filling from reports only")
    print(f"back-filled {backfill_from_reports(days)} value(s) from report metric cards")
    write_years(days)


if __name__ == "__main__":
    main()
