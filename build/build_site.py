#!/usr/bin/env python3
"""Generate the report shells that GitHub Pages serves.

For every data/reports/<kind>/<yyyy>/<date>.json this writes a ~700-byte
<kind>_report_<date>.html (interactive_nightly_<date>.html for kind interactive) (so every historical URL keeps working) whose
content is rendered in the browser by report/report.js. Also writes:

  data/reports/index.json     dates per kind (drives links and "latest")
  morning_report.html         always shows the newest morning report
  nightly_report.html         always shows the newest nightly report
  interactive_nightly.html    always shows the newest interactive nightly
  historical_progress_report.html  newest historical progress report
  lifting_recovery_report.html     newest lifting & recovery report
  report/index.html           browse every report

Usage: build_site.py [--out DIR]   (default: repo root; CI uses _site/)
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "data" / "reports"
KINDS = ("morning", "nightly", "interactive", "historical", "lifting")
TITLES = {
    "morning": "Morning Brief", "nightly": "Nightly Brief",
    "interactive": "Comprehensive Nightly Report", "historical": "Historical Progress Report",
    "lifting": "Lifting & Recovery Report",
}
PAGE_PREFIX = {
    "interactive": "interactive_nightly_", "historical": "historical_progress_report_",
    "lifting": "lifting_recovery_report_",
}


def page_name(kind: str, date: str) -> str:
    """Published filename; matches the URLs the generators always used."""
    return f"{PAGE_PREFIX.get(kind, kind + '_report_')}{date}.html"

SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="{root}report/{kind}.css">
<link rel="stylesheet" href="{root}report/common.css">
<script src="{root}report/charts.js" defer></script>
<script src="{root}report/report.js" defer></script>
</head>
<body data-kind="{kind}" data-date="{date}" data-root="{root}">
<noscript><p style="margin:40px">This report is rendered from data and needs JavaScript.</p></noscript>
</body>
</html>
"""

BROWSER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>All Reports</title>
<link rel="stylesheet" href="../report/morning.css">
<link rel="stylesheet" href="../report/common.css">
</head>
<body>
<nav id="site-nav" style="background:#1a1a2e;padding:10px 20px;text-align:center;font-size:14px;border-bottom:1px solid #333;display:flex;flex-wrap:wrap;justify-content:center;gap:8px 16px;">
<a href="../" style="color:#a0aec0;text-decoration:none;">🏠 Hub</a>
<a href="../morning_report.html" style="color:#a0aec0;text-decoration:none;">☀️ Latest Morning</a>
<a href="../nightly_report.html" style="color:#a0aec0;text-decoration:none;">🌙 Latest Nightly</a>
</nav>
<h1>All Reports</h1>
<div class="summary-paragraph">{summary}</div>
<div><input class="rb-filter" type="search" placeholder="Filter, e.g. 2026-09" oninput="
  var q=this.value.trim();document.querySelectorAll('.rb-month').forEach(function(m){{m.style.display=m.dataset.m.indexOf(q)===0||!q?'':'none'}});
  document.querySelectorAll('.rb-year').forEach(function(y){{y.style.display=!q||q.indexOf(y.dataset.y)===0||y.dataset.y.indexOf(q)===0?'':'none'}});"></div>
{body}
</body>
</html>
"""


def collect() -> dict[str, list[str]]:
    return {
        kind: sorted(p.stem for p in (REPORTS_DIR / kind).glob("*/*.json"))
        for kind in KINDS
    }


def browser_html(index: dict[str, list[str]]) -> str:
    months: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for kind in ("morning", "nightly"):
        dates = index[kind]
        for d in dates:
            months[d[:7]][d].add(kind)
    parts, year = [], None
    for month in sorted(months, reverse=True):
        if month[:4] != year:
            year = month[:4]
            parts.append(f'<h2 class="rb-year" data-y="{year}">{year}</h2>')
        days = []
        for d in sorted(months[month], reverse=True):
            links = []
            if "morning" in months[month][d]:
                links.append(f'<a href="../morning_report_{d}.html" title="Morning report">☀️ {d[8:]}</a>')
            if "nightly" in months[month][d]:
                links.append(f'<a class="n" href="../nightly_report_{d}.html" title="Nightly report">🌙{"" if links else " " + d[8:]}</a>')
            days.append(f'<span class="rb-day">{"".join(links)}</span>')
        parts.append(f'<div class="rb-month" data-m="{month}"><h3>{month}</h3><div class="rb-days">{"".join(days)}</div></div>')
    m, n = index["morning"], index["nightly"]
    summary = (
        f"{len(m):,} morning reports ({m[0]} → {m[-1]}) and {len(n):,} nightly reports "
        f"({n[0]} → {n[-1]}). ☀️ opens the morning brief, 🌙 the nightly brief."
        if m and n else "No reports yet."
    )
    return BROWSER.format(summary=summary, body="\n".join(parts))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT)
    args = ap.parse_args()
    out = args.out

    index = collect()
    (out / "data" / "reports").mkdir(parents=True, exist_ok=True)
    (out / "data" / "reports" / "index.json").write_text(json.dumps(index, separators=(",", ":")) + "\n")

    count = 0
    for kind in KINDS:
        dates = index[kind]
        for d in dates:
            title = f"{TITLES[kind]}: {d}"
            (out / page_name(kind, d)).write_text(SHELL.format(title=title, kind=kind, date=d, root=""))
            count += 1
        (out / page_name(kind, "latest").replace("_latest", "")).write_text(
            SHELL.format(title=TITLES[kind], kind=kind, date="latest", root=""))
    (out / "report").mkdir(parents=True, exist_ok=True)
    (out / "report" / "index.html").write_text(browser_html(index))
    print(f"wrote {count} report shells, index.json and report/index.html to {out}")


if __name__ == "__main__":
    main()
