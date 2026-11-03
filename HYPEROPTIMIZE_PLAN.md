# Hyper-optimize `tobyglenn/fitness` — Plan

## Goal

Replace the current "commit a 422 KB monolithic HTML per day into a 1.3 GB Pages repo" model with a data-driven, procedurally-generated site. The Pages tree goes from ~1.3 GB → ~500 KB. The repo stores structured JSON per day (~5–10 KB) plus a tiny generator. New morning reports are emitted as JSON and built into HTML by GitHub Pages on every push.

## Why this fixes the immediate break

- GitHub Pages' `Upload artifact` step currently fails because the published tree is **1.3 GB** (over the 1 GB soft limit).
- Real report content per day is ~7.7 KB of text. The rest is inline CSS / JS / SVG / repeated chrome that should be cacheable shared assets.
- 30 days × 10 KB data + 50 KB generator + 50 KB shared assets = **~400 KB** total. Pages will succeed.

## Architecture

```
fitness/
├── data/
│   └── morning/
│       ├── 2026-09-29.json          # ~5–10 KB structured per-day data
│       ├── 2026-09-28.json
│       └── ...                      # one file per report date
├── build/
│   ├── generate.py                  # reads data/morning/*.json → emits out/morning/<date>/index.html
│   ├── templates/
│   │   ├── morning.html             # single template; loads /assets/style.css, /assets/charts.js
│   │   └── index.html               # site root listing all known dates
│   └── assets/
│       ├── style.css                # single shared CSS, ~10 KB
│       └── charts.js                # chart helper, ~5 KB
├── out/                              # gitignored; Pages publishes from this dir
│   ├── index.html
│   └── morning/
│       ├── 2026-09-29/index.html    # generated
│       └── ...
├── .github/workflows/pages.yml      # builds on push to main, deploys out/ to Pages
├── .nojekyll                          # preserve
├── index.json                         # generated list of report dates (built by generate.py)
└── README.md
```

URL contract: `https://tobyglenn.github.io/fitness/morning/2026-09-29/` — preserves the existing mental URL pattern; new structure just moves the dated HTML under `/morning/<date>/`.

## Data schema (`data/morning/<DATE>.json`)

Schema captures every datum currently rendered on the page. All fields are JSON-native (no embedded SVG/HTML).

```json
{
  "schemaVersion": 1,
  "date": "2026-09-29",
  "generatedAt": "2026-09-29T07:30:00-04:00",
  "dataProvenance": {
    "whoop": "whoop_v2_latest.json (cumulative, 7.8 MB)",
    "garmin": "garmin/2026-09-29.json (38 MB dir, daily files since 2016)",
    "eightSleep": "eight_sleep/2026-09-29.json (per-day snapshots)",
    "trainingPlan": "training_plans/2026-09-29_morning.json (4.8 KB)",
    "speediance": "speediance_sync_2026-09.json (4.5 KB)",
    "cronometer": "cronometer_historical.csv"
  },

  "recovery": {
    "whoopPct": 61,
    "garminBodyBattery": 47,
    "garminSleepScore": 0,
    "eightSleepScore": 66,
    "compositePct": 78,
    "sevenDayAvgComposite": 50,
    "trend": "STABLE",
    "avgStress": 39
  },

  "sleep": {
    "deepHours": 1.5,
    "remHours": 2.1,
    "whoopTotalHours": 9.1,
    "garminTotalHours": 7.8,
    "eightSleepTotalHours": 6.6
  },

  "weeklyComparison": {
    "workouts":    {"thisWeek": 1, "lastWeek": 5},
    "runs":        {"thisWeek": 0, "lastWeek": 1},
    "volumeLbs":   {"thisWeek": 35587, "lastWeek": 31413},
    "miles":       {"thisWeek": 0.0, "lastWeek": 1.4},
    "bjj":         {"thisWeek": 0, "lastWeek": 1}
  },

  "todayWorkout": {
    "name": "ARIA !OVERRIDE! Barbell Knee-Safe",
    "planId": "20260917",
    "date": "2026-09-28",
    "durationMin": 46,
    "volumeLbs": 35587,
    "intensityPct": 80,
    "implement": "handles only"
  },

  "previousWorkout": null,

  "todaysPlan": {
    "type": "easy_run",
    "distanceMi": 1.1,
    "intensityZone": "easy aerobic"
  },

  "coachNote": "COACH: TRAIN - SUBMAX. Strong recovery, but injury risk is elevated. Train at 75–85% intensity. Skip PR attempts and limit novel exercises. Focus on: technical work, moderate loads (RPE 7-8).",
  "coachConfidencePct": 84.9,

  "injuryRisk": {
    "status": "ELEVATED",
    "rampPct": -37.8,
    "factors": ["low recovery (49)", "risk elevated due to poor recovery", "low HRV (27.3)"]
  },

  "trends": {
    "sleepVs":   {"deltaPct": 96.8, "direction": "up"},
    "hrvVs":     {"deltaPct": 24.7, "direction": "up"},
    "strainVs":  {"deltaPct": -74.3, "direction": "down"}
  },

  "patterns": [
    "Recovery scores are 14% below the 7-day average.",
    "Sleep consistency has improved over the past 5 days.",
    "Heart rate variability trending upward.",
    "Training load progression is appropriate for current recovery state."
  ],

  "recoveryBrief": "On Tuesday, 2026-09-29: Your readiness indicators show 61% recovery (Whoop)...",
  "narrativeText": "Your readiness indicators show 61% recovery (Whoop), Garmin Sleep Score at 0, Body Battery at 47, and an 8Sleep score of 66. Deep sleep was 1.5h and REM sleep was 2.1h. Total sleep for Whoop was 9.1h, for Garmin was 7.8h, and for 8Sleep was 6.6h. Average stress was 39.",

  "charts": {
    "recoveryTrend":      {"type": "line", "dataUrl": "data:image/png;base64,..."},
    "weeklyLoad":         {"type": "line", "dataUrl": "data:image/png;base64,..."},
    "trainingEffect":     {"type": "scatter", "dataUrl": "data:image/png;base64,..."}
  }
}
```

**Size budget:** ~5 KB text data + up to 3 charts × ~100 KB base64 PNG each ≈ **300 KB worst case**. Well under today's 422 KB monolithic HTML.

**Chart decision:** keep base64-embedded charts in JSON for now (matches today's behavior). Future optimization can move them to external SVGs (smaller, scalable) without breaking the schema.

## Phased implementation

Each phase is independent and shippable. Stop at any phase and the system still works.

### Phase 0 — Foundations (prep)

**0.1 Audit the repo size contributors**

Run:
```bash
cd /home/toby/clawd/docs
git remote -v
du -sh .git .git/lfs data morning_report_*.html website pagefind
find . -name '*.html' | wc -l
```

Expected output:
- `.git/` ~672 MB
- `.git/lfs/` ~161 MB (one 130 MB object)
- `website/` ~23 MB (mirror of tobyonfitnesstech.com)
- `pagefind/` ~12 MB (search index)
- `morning_report_*.html` files in repo root (legacy, ~200+ files)

**0.2 Locate the 130 MB LFS object**

```bash
git lfs ls-files --all
```

Record the pointer hash and what it is (likely a video or audio asset). Decision in Phase 6: keep in LFS (just `.git/lfs/` is ~161 MB on disk, but Pages only uploads the working tree minus LFS pointers — so this won't actually count toward the 1 GB Pages artifact limit), or delete and replace with an external CDN URL.

**0.3 Confirm Pages workflow origin**

Today the repo has no `.github/workflows/*.yml`. Pages must be configured via repo Settings → API → Pages → "GitHub Actions" (UI-managed workflow). The new `.github/workflows/pages.yml` will use `actions/deploy-pages@v4` to publish the `out/` directory.

### Phase 1 — Generator emits JSON sidecar (no behavior change)

**1.1 Add JSON emit function to `generate_morning_report_content.py`**

File: `/home/toby/.openclaw/workspace/scripts/reports/generate_morning_report_content.py`

The function `generate_reports(target_date=None, narrative_text=None)` at line 625 builds the HTML. Add a sibling function that emits the JSON sidecar at the same point:

```python
def emit_morning_json(target_date: str, *, out_path: str = None) -> str:
    """Emit data/morning/<date>.json sidecar from the same data sources as the HTML.

    Returns the absolute path written. Raises MorningReportValidationError on missing
    required data (mirrors HTML path's validation behavior).
    """
    # Reuse existing extract_*() functions to populate each schema section
    payload = {
        "schemaVersion": 1,
        "date": target_date,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataProvenance": {
            "whoop": "whoop_v2_latest.json",
            "garmin": f"garmin/{target_date}.json",
            "eightSleep": f"eight_sleep/{target_date}.json",
            "trainingPlan": f"training_plans/{target_date}_morning.json",
        },
    }

    # Recovery + body battery + sleep scores
    garmin_data = extract_processed_garmin_data(target_date)  # line 268
    whoop_data = _load_json_file(WHOOP_FILE, "WHOOP")["recovery"]["records"]
    whoop_today = next(r for r in whoop_data if str(r["created_at"]).startswith(target_date))
    payload["recovery"] = {
        "whoopPct": whoop_today["score"]["recovery_score"],
        "garminBodyBattery": _safe_metric(garmin_data.get("body_battery", 0)),
        "garminSleepScore": _extract_garmin_sleep_score(garmin_data),
        # ... etc
    }

    # ... populate remaining fields by reusing compute_recovery_aggregates(),
    # extract_whoop_trends(), extract_garmin_trends(), etc.

    out_path = out_path or os.path.join(DATA_DIR, "morning", f"{target_date}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True, default=str)
    return out_path
```

**1.2 Call emit_morning_json from the same orchestrator** that currently calls `generate_reports(...)`. The Mac pipeline's `fitness-report-pipeline morning` cron at 30 7 * * * is the caller. After this change, every morning produces **both** the legacy HTML and the new JSON.

**Verification:**
```bash
ls -la /home/toby/clawd/data/morning/2026-09-29.json
python3 -c "import json; d=json.load(open('/home/toby/clawd/data/morning/2026-09-29.json')); print(d['recovery'])"
```

### Phase 2 — Create new repo layout on a branch

**2.1 Branch off `gh-pages`** in `/home/toby/clawd/docs` (the local fitness repo):

```bash
cd /home/toby/clawd/docs
git checkout -b main-with-generator origin/gh-pages  # or 'main' if it exists
```

**2.2 Add `build/` skeleton:**

```bash
mkdir -p build/templates build/assets data/morning out
touch out/.gitkeep
echo "out/" > .gitignore
echo "build/__pycache__/" >> .gitignore
```

**2.3 Write `build/templates/morning.html`** — a single Jinja-style template (using Python `string.Template` to avoid pip deps on the GitHub Actions runner) that renders one day's report.

**2.4 Write `build/templates/index.html`** — list of all dates with links to `/morning/<date>/`.

**2.5 Write `build/assets/style.css`** — move the inlined CSS from a sample report (`head <style>...</style>` block) into a shared file.

**2.6 Write `build/assets/charts.js`** — minimal chart helper if charts are kept as data URIs (no-op placeholder).

**2.7 Write `build/generate.py`:**

```python
#!/usr/bin/env python3
"""Read data/morning/*.json, emit out/morning/<date>/index.html for each.

Stdlib-only. Deterministic output (no timestamps in rendered HTML).
"""
import json
import os
import sys
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "morning"
OUT_DIR = ROOT / "out" / "morning"
TEMPLATE_DIR = ROOT / "build" / "templates"
ASSET_DIR = ROOT / "build" / "assets"

def render_morning(data: dict) -> str:
    tpl = (TEMPLATE_DIR / "morning.html").read_text()
    return Template(tpl).substitute(
        date=data["date"],
        recovery=data["recovery"],
        sleep=data["sleep"],
        weekly=data["weeklyComparison"],
        today_workout=data.get("todayWorkout") or {},
        coach_note=data.get("coachNote", ""),
        narrative=data.get("narrativeText", ""),
        # ... etc.
    )

def main():
    if not DATA_DIR.exists():
        sys.exit(f"missing {DATA_DIR}")

    dates = sorted(p.stem for p in DATA_DIR.glob("*.json"))
    if not dates:
        sys.exit("no morning data files found")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for date in dates:
        data = json.loads((DATA_DIR / f"{date}.json").read_text())
        html = render_morning(data)
        out = OUT_DIR / date / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"  wrote {out.relative_to(ROOT)} ({len(html):,} bytes)")

    # Copy assets to out/ so Pages serves them
    import shutil
    assets_out = ROOT / "out" / "assets"
    if assets_out.exists():
        shutil.rmtree(assets_out)
    shutil.copytree(ASSET_DIR, assets_out)

    # Index page
    index_tpl = (TEMPLATE_DIR / "index.html").read_text()
    index_html = Template(index_tpl).substitute(dates=dates)
    (ROOT / "out" / "index.html").write_text(index_html)
    print(f"  wrote out/index.html ({len(index_html):,} bytes, {len(dates)} dates)")

if __name__ == "__main__":
    main()
```

**Verification:**
```bash
cd /home/toby/clawd/docs
python3 build/generate.py
ls -la out/morning/2026-09-29/index.html
python3 -c "import os; print(f'out/ size: {sum(os.path.getsize(os.path.join(r,f)) for r,_,fs in os.walk(\"out\") for f in fs):,} bytes')"
```

Expected: total `out/` size ~100 KB (one generated HTML + assets).

### Phase 3 — Backfill historical data

**3.1 Pick scope:** last 30 days (Sep 1 → Sep 29) is enough to cover recent links from morning emails and Telegram messages. Older reports are reachable via Wayback Machine if anyone really needs them.

**3.2 Backfill method A — re-run the generator for each historical date:**

```bash
for d in $(seq -f "%Y-%m-%d" -s " " $(date -d "30 days ago" +%s) $(date +%s)); do
  python3 -c "
import sys; sys.path.insert(0, '/home/toby/.openclaw/workspace/scripts/reports')
from generate_morning_report_content import emit_morning_json
emit_morning_json('$d')
" 2>&1 | tail -1
done
```

Skips days where source data is missing (Garmin / WHOOP / 8Sleep not archived for that day) — those are reported but not fatal.

**3.3 Backfill method B — parse existing HTML reports:**

For dates where source data is gone but the legacy `morning_report_<date>.html` exists, write a one-shot extractor that pulls visible numbers out of the HTML and populates the JSON. Use only for the report body (recovery / sleep / weekly comparison fields); narrative text + patterns stay blank.

**3.4 Validate backfill:**

```bash
ls /home/toby/clawd/docs/data/morning/ | wc -l
du -sh /home/toby/clawd/docs/data/morning/
```

Expected: ~25–30 files, ~250 KB total.

### Phase 4 — Mac deploy script pushes JSON

File: `/Users/tobyglennpeters/clawd/scripts/deploy_to_github_pages.sh` (Mac)

Replace the lines that copy HTML files (lines 35–47 above) with:

```bash
# Copy JSON sidecar instead of HTML
echo "📋 Copying morning JSON sidecar..."
mkdir -p data/morning
if [ -f "$HOME/clawd/data/morning/${DATE}.json" ]; then
    cp -f "$HOME/clawd/data/morning/${DATE}.json" data/morning/
fi
```

`generate.py` runs on Pages Actions, not Mac. Mac is now just a data pipeline (JSON in, JSON pushed).

**Verification:** tomorrow's cron run commits one new JSON file; commit log shows it.

### Phase 5 — Add Pages workflow

File: `/home/toby/clawd/docs/.github/workflows/pages.yml`

```yaml
name: Build and deploy morning reports

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - name: Build site
        run: python3 build/generate.py
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: out/

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Commit and push to `main`. Verify the workflow runs on GitHub.

### Phase 6 — Cleanup legacy content (drop repo size to ~500 KB)

The bloat breakdown:

| Path                  | On-disk size | Pages impact                | Action                               |
|-----------------------|---------------|---------------------------|------------------------------------|
| `.git/`               | 672 MB        | Not published             | Leave (no effect on Pages)         |
| `.git/lfs/`           | 161 MB        | Not published             | Leave (LFS pointers in tree only)  |
| `website/`            | 23 MB         | Yes — published           | **Delete**                         |
| `pagefind/`           | 12 MB         | Yes — published           | **Delete** (only old site uses it) |
| `morning_report_*.html` (root) | ~85 MB | Yes — published       | **Delete** (replaced by `/morning/<date>/`) |
| `strength/`, `cardio/`, `sleep_dashboard.html`, etc. | — | Yes | **Keep** if non-trivial (delete in follow-up) |

**6.1 Delete the dead paths:**

```bash
cd /home/toby/clawd/docs
git rm -rf website/ pagefind/
git rm -f morning_report_*.html
# Keep the date-named files (morning_report_2026-09-29.html) for now —
# they're a useful fallback if Pages build fails on a day. Delete in Phase 7.
```

**6.2 Squash history (optional but recommended):**

The 5,971 files in the repo include all the old legacy dashboards. To drop them entirely and end up with a clean ~500 KB repo:

```bash
cd /home/toby/clawd/docs
git switch --orphan clean-main
git add -A
git commit -m "Initial commit: data-driven morning reports"
git push origin clean-main:main --force
```

The Mac deploy needs to switch its `git clone --branch` from `gh-pages` to `main`. Edit `deploy_to_github_pages.sh` line 30:

```bash
git clone --depth 1 --single-branch --branch main "$REPO_URL" repo || ...
```

**6.3 Decide on the 130 MB LFS object**

After cleaning, `.git/lfs/` doesn't affect Pages (only the working tree does). If audit in Phase 0.2 shows it's something the user actively uses (a video thumbnail, an audio file), keep. Otherwise:

```bash
git lfs untrack "<pattern>"
git rm --cached "<file>"
git commit -m "remove unused LFS object"
```

### Phase 7 — Verify end-to-end

Run all of the following and capture the output:

```bash
# 1. Repo size
cd /home/toby/clawd/docs
echo "repo size:"; du -sh . | awk '{print $1}'
echo "tracked file count:"; git ls-files | wc -l
echo "data/morning size:"; du -sh data/morning/
echo "out/ size (what Pages will publish):"; du -sh out/

# 2. Local Pages test
python3 -m http.server 8000 --directory out &
SERVER_PID=$!
sleep 1
curl -sI http://localhost:8000/morning/2026-09-29/ | head -1
curl -sI http://localhost:8000/ | head -1
kill $SERVER_PID

# 3. Remote Pages check
sleep 30  # wait for Pages Actions to settle
curl -sI https://tobyglenn.github.io/fitness/morning/2026-09-29/ | head -1
curl -sI https://tobyglenn.github.io/fitness/ | head -1

# 4. Check Pages Actions status
gh api repos/tobyglenn/fitness/pages/builds/latest 2>&1 | python3 -m json.tool | head -20
```

All four curls should return HTTP 200.

## Verification checklist (acceptance criteria)

- [ ] `data/morning/2026-09-29.json` exists and parses; contains every field currently rendered on the legacy HTML
- [ ] `build/generate.py` runs successfully against `data/morning/*.json`
- [ ] Generated `out/morning/<date>/index.html` renders correctly when opened in a browser
- [ ] Generated HTML byte count is significantly smaller than today's monolithic HTML
- [ ] `out/` directory total size is under 1 MB
- [ ] GitHub Actions workflow `pages.yml` runs green on push to `main`
- [ ] `https://tobyglenn.github.io/fitness/morning/2026-09-29/` returns HTTP 200
- [ ] `https://tobyglenn.github.io/fitness/` returns HTTP 200 and links to all reports
- [ ] Tomorrow's morning cron run pushes one new JSON file, Pages rebuilds, the new URL is live within ~3 min
- [ ] Repo total size (working tree, excluding `.git/`) is under 1 MB
- [ ] Repo total size on disk (including `.git/`) drops significantly from 1.3 GB

## Risks and rollback

**Risk 1: Generated HTML doesn't render the same as the legacy HTML**
- *Mitigation:* Phase 1 keeps the legacy HTML generator running unchanged. Phase 2 only ADDS a new generator; legacy HTML still deploys. Compare side-by-side before cutting over.
- *Rollback:* revert to legacy HTML deploy; delete the new `data/morning/` and `out/` directories. Legacy `morning_report_<DATE>.html` files remain in repo until Phase 7.

**Risk 2: Backfill loses data for dates where source JSON isn't archived**
- *Mitigation:* method B (parse existing HTML) catches dates where source data is gone. Days with no source data AND no legacy HTML are simply skipped.
- *Rollback:* re-run backfill with a wider date range after restoring source data.

**Risk 3: Pages Actions times out on first build**
- *Mitigation:* the build step is one Python script with no pip installs. Expected runtime < 5 seconds.
- *Rollback:* kill the workflow; the repo Pages config still works (will rebuild on next push).

**Risk 4: Mac deploy script doesn't switch branches cleanly**
- *Mitigation:* Phase 4 changes only the destination branch (gh-pages → main) and what gets copied (HTML → JSON). The clone / commit / push skeleton is the same.
- *Rollback:* revert `deploy_to_github_pages.sh`; Mac pushes HTML again.

**Risk 5: The 130 MB LFS object matters for something**
- *Mitigation:* Phase 0.2 audits it. If in use, keep. If unused, remove.

**Risk 6: Force-push to `main` loses history**
- *Mitigation:* the local clone on DGX retains the full history. The Mac only does `--depth 1` clones. Force-push to `main` does NOT affect the legacy `gh-pages` branch if it's left in place — but Phase 6.2 orphan-commit will collapse `main`'s history. If history preservation matters, skip Phase 6.2 (the repo still shrinks because `website/`, `pagefind/`, and the root-level HTML files are deleted).

## Do not break

- **Mac nightly report pipeline.** Out of scope. The Mac's `fitness-report-pipeline nightly` cron at ~23:30 7 * * * produces a different report (`nightly_report_<DATE>.html` or similar). Leave untouched.
- **Morning emails + Telegram messages.** These embed summary text, not URLs to `morning_report_<DATE>.html`. Should continue to work unchanged.
- **`tobyonfitnesstech.com` homepage.** Served by `tobyglenn/websiteBuilder`, not the fitness repo. Unaffected by this work.
- **`fitness-website-maintenance` skill.** Already documents the `generate_videos_data.mjs` fix. May want to add a reference to this hyperoptimization plan once shipped.

## Estimated sizes (before vs after)

| Path                         | Before       | After        |
|------------------------------|--------------|--------------|
| `out/` (what Pages publishes)| 1.3 GB       | ~500 KB      |
| `data/morning/`              | (none)       | ~250 KB      |
| `build/`                     | (none)       | ~50 KB      |
| Repo total on disk           | 1.3 GB       | ~50 MB (just `.git/` of clean main) |
| Per-day morning payload      | 422 KB HTML  | ~10 KB JSON + ~5 KB built HTML (excluding shared assets) |

## Execution order (one PR per phase)

1. **Phase 1 PR:** emit JSON sidecar. Touches only `generate_morning_report_content.py`.
2. **Phase 2 PR:** add `build/` skeleton to fitness repo on a `feature/generator` branch.
3. **Phase 3 PR:** backfill 30 days of `data/morning/*.json`.
4. **Phase 4 PR:** Mac deploy script change.
6. **Phase 5 PR:** Pages Actions workflow.
6. **Phase 6 PR:** delete `website/`, `pagefind/`, root-level `morning_report_*.html`; force-push clean `main`.
7. **Phase 7:** verification + Telegram announcement.