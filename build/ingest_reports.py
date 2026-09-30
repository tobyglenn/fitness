#!/usr/bin/env python3
"""Convert generated morning/nightly/interactive-nightly report HTML into report data JSON.

The report generators still emit full HTML pages (with matplotlib charts
inlined as base64). This step keeps everything a reader sees — metric
cards, coach notes, training plan, nutrition, trend and pattern text —
and drops the baked chart images. Charts are re-drawn in the browser by
report/charts.js from data/daily/*.json.

Usage:
  ingest_reports.py [--delete] FILE.html [FILE.html ...]
  ingest_reports.py [--delete] --scan DIR     # every dated report HTML in DIR

Writes data/reports/<kind>/<YYYY>/<YYYY-MM-DD>.json under the repo root.
With --delete the source HTML is removed after a successful conversion.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from htmldom import Node, parse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "data" / "reports"
# morning_report_<date>.html, nightly_report_<date>.html → kind morning/nightly;
# interactive_nightly_<date>.html (Mac nightly generator) → kind interactive;
# historical_progress_report_<date>.html → kind historical;
# lifting_recovery_report_<date>.html → kind lifting.
NAME_RE = re.compile(
    r"^(?:(morning|nightly)_report|(interactive)_nightly|(historical)_progress_report|(lifting)_recovery_report)"
    r"_(\d{4}-\d{2}-\d{2})\.html$"
)
SCHEMA_VERSION = 1
FALLBACK_TITLES = {
    "morning": "Morning Brief", "nightly": "Nightly Brief",
    "interactive": "Comprehensive Nightly Report", "historical": "Historical Progress Report",
    "lifting": "Lifting & Recovery Report",
}

# Chart heading → renderer id (see report/charts.js).
CHART_IDS = [
    ("recovery trends", "recovery-trends"),
    ("recovery response", "recovery-trends"),
    ("strength benchmark", "strength-benchmark"),
    ("cardio intensity", "cardio-intensity"),
    ("weekly load", "weekly-load"),
    ("fueling vs output", "fueling"),
    ("sleep debt", "sleep-debt"),
    ("recovery debt", "sleep-debt"),
]

TONES = {
    "#32d74b": "green", "#30d158": "green", "#34c759": "green",
    "#ffd60a": "yellow", "#ffcc00": "yellow",
    "#ff453a": "red", "#ff3b30": "red",
    "#0a84ff": "blue", "#007aff": "blue",
    "#ff9f0a": "orange", "#ff9500": "orange",
    "#bf5af2": "purple",
}


# Historical progress report charts cover all history, not a 14-day window.
HISTORICAL_CHART_IDS = [
    ("weight", "hist-weight"),
    ("energy", "hist-energy"),
    ("macro", "hist-macros"),
    ("recovery", "hist-recovery"),
    ("training volume", "hist-volume"),
    ("deload", "hist-volume"),
]


def chart_id(title: str, kind: str = "") -> str | None:
    t = title.lower()
    for key, cid in HISTORICAL_CHART_IDS if kind == "historical" else CHART_IDS:
        if key in t:
            return cid
    return None


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def strip_noise(node: Node, kind: str = "") -> None:
    """Remove scripts and styles; swap inline base64 chart images for slots.

    A baked chart image becomes <div class="chart-slot" data-chart="id">
    when the nearest preceding heading names a known chart, so the
    renderer draws it live; unrecognised images are dropped.
    """
    heading = ""
    for n in list(node.iter()):
        if n.tag in ("h1", "h2", "h3", "h4"):
            heading = clean_text(n.text())
        elif n.tag in ("script", "style"):
            n.remove()
        elif n.tag == "img" and (n.attrs.get("src") or "").startswith("data:"):
            cid = chart_id(" ".join([n.attrs.get("alt", ""), n.attrs.get("title", ""), heading]), kind)
            if cid and n.parent is not None:
                slot = Node("div", {"class": "chart-slot", "data-chart": cid}, n.parent)
                n.parent.children[n.parent.children.index(n)] = slot
                n.parent = None
            else:
                n.remove()


def compact_html(node: Node) -> str:
    html = node.outer_html()
    return re.sub(r">\s+<", "><", re.sub(r"[ \t]*\n\s*", "\n", html)).strip()


def metric_cards(grid: Node) -> list[dict] | None:
    """Structured cards for a metric-grid of 'LABEL<br><span.value>' cards."""
    cards = []
    for card in grid.elements():
        value = card.find("span", "value")
        if not card.has_class("card") or value is None:
            return None
        tip_el = card.find("span", "info-icon")
        label_parts = []
        for c in card.children:
            if isinstance(c, str):
                label_parts.append(c)
            elif c.tag == "br" or c is value:
                break
            elif c is not tip_el:
                label_parts.append(c.text())
        suffix = []
        after = False
        for c in card.children:
            if c is value:
                after = True
            elif after:
                suffix.append(c if isinstance(c, str) else c.text())
        style = (value.attrs.get("style") or "").lower()
        m = re.search(r"color:\s*(#[0-9a-f]{3,8})", style)
        card_out = {"label": clean_text("".join(label_parts)), "value": clean_text(value.text())}
        if m:
            card_out["tone"] = TONES.get(m.group(1), m.group(1))
        if tip_el is not None and tip_el.attrs.get("data-tooltip"):
            card_out["tip"] = tip_el.attrs["data-tooltip"]
        if clean_text("".join(suffix)):
            card_out["sub"] = clean_text("".join(suffix))
        cards.append(card_out)
    return cards or None


def is_cross_link(el: Node) -> bool:
    links = el.find_all("a")
    return (
        el.tag == "div" and not el.classes and len(links) == 1
        and re.search(r"_report_\d{4}-\d{2}-\d{2}\.html", links[0].attrs.get("href", ""))
        and clean_text(el.text()) == clean_text(links[0].text())
    )


def convert(html: str, kind: str, date: str) -> dict:
    root = parse(html)
    body = root.find("body") or root
    title = ""
    metrics = None
    blocks: list[dict] = []
    # Lifting & recovery reports draw their charts with Chart.js from an inline
    # `const data = {...}` script: keep that script (and the Chart.js include)
    # so report.js can run it after rendering. Other scripts are nav helpers.
    scripts: list[dict] = []
    inline_title = False
    for n in root.find_all("script"):
        code = n.text()
        if kind == "lifting" and n.attrs.get("src") and "chart" in n.attrs["src"].lower():
            scripts.append({"scriptSrc": n.attrs["src"]})
        elif kind == "lifting" and ("new Chart" in code or "const data" in code):
            scripts.append({"script": code.strip()})
        n.remove()

    if not any(el.tag == "h1" for el in body.elements()):
        h1 = body.find("h1")  # e.g. interactive nightly wraps everything in a container
        if h1 is not None:
            title = clean_text(h1.text())
            if kind == "lifting":
                inline_title = True  # the heading is part of the report's header block
            else:
                h1.remove()

    for el in body.elements():
        if el.tag in ("nav", "script", "style", "link", "meta", "head"):
            continue
        if el.tag == "h1":
            title = clean_text(el.text())
            continue
        if is_cross_link(el):
            continue  # regenerated by the renderer from the report index
        if el.has_class("chart-box"):
            heading = el.find(("h2", "h3"))
            head_text = clean_text(heading.text()) if heading else ""
            cid = chart_id(head_text, kind)
            if cid and el.find("img"):
                if heading:
                    heading.remove()
                strip_noise(el, kind)
                caption = "".join(compact_html(c) if isinstance(c, Node) else c for c in el.children).strip()
                block = {"chart": cid, "title": head_text}
                if caption:
                    block["caption"] = caption
                blocks.append(block)
                continue
        if metrics is None and (el.has_class("metric-grid") or el.has_class("grid")):
            metrics = metric_cards(el)
            if metrics is not None:
                blocks.append({"metrics": True})
                continue
        strip_noise(el, kind)
        if not clean_text(el.text()) and not el.find(("img", "svg", "canvas")):
            continue
        blocks.append({"html": compact_html(el)})

    blocks += scripts
    return {
        "schema": SCHEMA_VERSION,
        "kind": kind,
        "date": date,
        "title": title or f"{FALLBACK_TITLES.get(kind, kind.title())}: {date}",
        **({"inlineTitle": True} if inline_title else {}),
        "metrics": metrics or [],
        "blocks": blocks,
    }


def out_path(kind: str, date: str) -> Path:
    return REPORTS_DIR / kind / date[:4] / f"{date}.json"


def ingest(path: Path, delete: bool = False) -> Path:
    m = NAME_RE.match(path.name)
    if not m:
        raise ValueError(f"not a dated report file: {path.name}")
    kind, date = m.group(1) or m.group(2) or m.group(3) or m.group(4), m.group(5)
    doc = convert(path.read_text(encoding="utf-8", errors="replace"), kind, date)
    if not doc["blocks"]:
        raise ValueError(f"no content extracted from {path.name}")
    dest = out_path(kind, date)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if delete:
        path.unlink()
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--scan", type=Path, help="convert every dated report HTML in this directory")
    ap.add_argument("--delete", action="store_true", help="remove source HTML after converting")
    args = ap.parse_args()

    files = list(args.files)
    if args.scan:
        files += sorted(p for p in args.scan.glob("*.html") if NAME_RE.match(p.name))
    failures = 0
    for f in files:
        try:
            dest = ingest(f, args.delete)
            print(f"  {f.name} -> {dest.relative_to(ROOT)}")
        except Exception as exc:  # keep going; report at the end
            failures += 1
            print(f"  FAILED {f.name}: {exc}", file=sys.stderr)
    print(f"ingested {len(files) - failures}/{len(files)} report(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
