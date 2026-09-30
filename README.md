# fitness

Toby's fitness dashboard, served by GitHub Pages at <https://tobyglenn.github.io/fitness/>.

## Reports are data, not pages

Every dated report is stored as JSON and rendered in the browser; nothing
per-date is committed as HTML. The old baked pages (charts inlined as base64)
took ~1.3 GB; the same reports are now ~36 MB of data.

| Report | URL | Data |
|---|---|---|
| Morning brief (2021-10 →) | `morning_report_<date>.html` | `data/reports/morning/` |
| Nightly brief (2021-10 →) | `nightly_report_<date>.html` | `data/reports/nightly/` |
| Comprehensive (interactive) nightly | `interactive_nightly_<date>.html` | `data/reports/interactive/` |
| Historical progress (2026-02 →) | `historical_progress_report_<date>.html` | `data/reports/historical/` |

```
data/reports/<kind>/<yyyy>/<date>.json   report content: metric cards, coach notes,
                                         training plan, nutrition, trends, patterns,
                                         and which charts to draw
data/daily/<yyyy>.json                   one row per day of every metric the charts use
                                         (WHOOP, Garmin, Eight Sleep, Speediance/Tonal,
                                         Cronometer), 2016 → today
report/report.js                         builds a report page from the two files above
report/charts.js                         draws the charts (SVG, no dependencies)
report/<kind>.css                        the original report styles, verbatim
```

URLs are unchanged, and `morning_report.html`, `nightly_report.html`,
`interactive_nightly.html` and `historical_progress_report.html` show the
latest of each. Those are ~700-byte shells generated at deploy time by
`build/build_site.py`, along with `report/index.html` (browse every report)
and `data/reports/index.json`.

`lifting_recovery_report_<date>.html` stays committed as HTML: each page is
~30 KB and already draws its charts with Chart.js from inline data.

## Daily flow

1. The pipeline's generators write their dated report HTML into the checkout
   as before (gitignored).
2. `build/ingest_reports.py --scan .` converts them to `data/reports/…json`.
3. `build/build_daily.py --data-dir ~/clawd/data` refreshes `data/daily/`.
4. Commit + push to `main`; `.github/workflows/pages.yml` builds the shells
   and publishes the site as a single orphan commit on `gh-pages` (Pages
   source), so that branch never accumulates history.

Build scripts are stdlib-only Python 3.9+.

Preview locally:

```sh
rsync -a --exclude .git ./ /tmp/site-preview/
python3 build/build_site.py --out /tmp/site-preview
cd /tmp/site-preview && python3 -m http.server 8000
```
