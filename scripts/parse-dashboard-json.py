#!/usr/bin/env python3
"""Phase 1a — Parse a Domo dashboard JSON export into structured signals.

Emits three files into the output dir:
  card-signals.json    — per-card metadata (id, title, sigmaKind, formats, dateFilter, ...)
  layout.json          — per-layout-slot grid coords (Domo 60-col + Sigma 24-col)
  page-controls.json   — deduplicated page-level slicers + the page date filter

Mechanical only — no agent judgment. Consumed by build-workbook-spec.py downstream.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from domo_chart_kinds import lookup as kind_lookup


def _maybe_json(s):
    """Parse a JSON-encoded string field; return {} on failure."""
    if not s:
        return {}
    if isinstance(s, dict):
        return s
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return {}


def _parse_dynamic_title(raw):
    """Domo dynamicTitle is JSON-encoded {text: [{text, type}]}; emit a template string.

    Tokens like DATE_RANGE_FILTER_DATE_TIME_RANGE become ${DATE_RANGE}.
    """
    parsed = _maybe_json(raw)
    parts = []
    for t in parsed.get("text", []):
        ttype = t.get("type", "TEXT")
        if ttype == "TEXT":
            parts.append(t.get("text", ""))
        else:
            # Collapse Domo's verbose tokens to a short readable form
            label = "DATE_RANGE" if "DATE_RANGE" in ttype else ttype
            parts.append(f"${{{label}}}")
    return "".join(parts) if parts else None


def _parse_date_filter(date_info):
    """Convert Domo dateInfo to {column, mode, unit, count} or None."""
    if not date_info:
        return None
    dr = date_info.get("dateRange")
    if not dr:
        return None
    column = dr.get("columnName")
    # The filter shape has two variants depending on Domo version:
    f = dr.get("dateTimeRangeFilter") or dr.get("dateRangeFilter") or {}
    rng = f.get("dateTimeRange") or {}
    range_type = rng.get("dateTimeRangeType")
    if not range_type:
        return None
    if range_type == "ROLLING_PERIOD":
        return {
            "column": column,
            "mode": "rolling",
            "unit": (rng.get("interval") or "").lower() or None,
            "count": rng.get("count"),
            "offset": rng.get("offset", 0),
        }
    if range_type == "INTERVAL_OFFSET":
        # YTD/QTD/MTD-style "this period to date"
        return {
            "column": column,
            "mode": "current",
            "unit": (rng.get("interval") or "").lower() or None,
            "count": rng.get("count"),
        }
    # Unrecognized type — preserve raw for the agent to handle
    return {
        "column": column,
        "mode": "raw",
        "raw": rng,
    }


def _parse_slicers(slicers):
    if not slicers:
        return []
    out = []
    for s in slicers:
        out.append({
            "column": s.get("column") or s.get("name"),
            "type": s.get("type"),
            "displayType": s.get("displayType"),
            "operator": s.get("operator"),
            "values": s.get("values") or [],
            "dataSourceId": s.get("dataSourceId"),
        })
    return out


def parse(dashboard_json: dict) -> dict:
    page = dashboard_json.get("page", {}) or {}
    cards = dashboard_json.get("cards") or []
    page_layout = dashboard_json.get("pageLayoutV4") or {}
    template = (page_layout.get("standard") or {}).get("template") or []
    content_by_key = {
        c["contentKey"]: c for c in (page_layout.get("content") or [])
    }

    # --- Card signals ---
    card_signals = []
    for c in cards:
        meta = c.get("metadata") or {}
        ct = meta.get("chartType") or c.get("type")
        m = kind_lookup(ct)
        formats = _maybe_json(meta.get("columnFormats"))
        aliases = _maybe_json(meta.get("columnAliases"))
        date_filter = _parse_date_filter(c.get("dateInfo"))
        date_grain = ((c.get("dateInfo") or {}).get("dateGrain") or {}).get(
            "dateTimeElement", ""
        ).lower() or None
        card_signals.append({
            "cardId": c.get("id"),
            "title": c.get("title"),
            "titleTemplate": _parse_dynamic_title(meta.get("dynamicTitle")),
            "type": c.get("type"),
            "domoChartType": ct,
            "sigmaKind": m.sigma_kind,
            "mappingClass": m.cls,
            "mappingNote": m.note,
            "datasourceIds": [
                s.get("dataSourceId") for s in (c.get("datasources") or [])
            ],
            "columnFormats": formats,
            "columnAliases": aliases,
            "defaultDateGrain": meta.get("defaultDateGrain"),
            "dateFilter": date_filter,
            "dateGrain": date_grain,
            "slicers": _parse_slicers(c.get("slicers")),
        })

    # --- Layout ---
    layout_items = []
    for item in template:
        ck = item.get("contentKey")
        content = content_by_key.get(ck, {}) or {}
        x = item.get("x", 0)
        y = item.get("y", 0)
        w = item.get("width", 0)
        h = item.get("height", 0)
        # Clamp malformed overflows
        if x + w > 60:
            w = max(0, 60 - x)
        c0 = round(x / 60 * 24) + 1
        c1 = round((x + w) / 60 * 24) + 1
        if c1 <= c0:
            c1 = c0 + 1
        layout_items.append({
            "contentKey": ck,
            "cardId": content.get("cardId"),
            "type": item.get("type", "CARD"),
            "hideTitle": content.get("hideTitle", False),
            "hideSummary": content.get("hideSummary", False),
            "acceptFilters": content.get("acceptFilters", True),
            "acceptDateFilter": content.get("acceptDateFilter", True),
            "acceptSegments": content.get("acceptSegments", True),
            "domo": {"x": x, "y": y, "width": w, "height": h},
            "sigmaCols": [c0, c1],
            "sigmaRows": [y + 1, y + h + 1],
        })

    # --- Page-level controls (dedupe slicers across cards) ---
    seen = set()
    page_slicers = []
    for c in card_signals:
        for s in c["slicers"]:
            key = (s["column"], s["dataSourceId"], s["type"], s["operator"])
            if key in seen:
                continue
            seen.add(key)
            page_slicers.append(s)

    # Mode date filter — the most-common dateFilter wins as the page-level one
    df_counts = {}
    for c in card_signals:
        df = c["dateFilter"]
        if df:
            k = (df.get("column"), df.get("mode"), df.get("unit"), df.get("count"))
            df_counts[k] = df_counts.get(k, 0) + 1
    page_date_filter = None
    if df_counts:
        best = max(df_counts.items(), key=lambda x: x[1])[0]
        page_date_filter = {
            "column": best[0],
            "mode": best[1],
            "unit": best[2],
            "count": best[3],
            "appliesToCards": df_counts[best],
        }

    return {
        "page": {
            "pageId": page.get("pageId"),
            "title": dashboard_json.get("title") or page.get("title"),
            "name": page.get("pageName"),
        },
        "datasources": _unique_datasources(cards),
        "cards": card_signals,
        "layout": layout_items,
        "pageControls": {
            "slicers": page_slicers,
            "dateFilter": page_date_filter,
        },
    }


def _unique_datasources(cards):
    out = {}
    for c in cards:
        for s in c.get("datasources") or []:
            k = s.get("dataSourceId")
            if not k:
                continue
            if k not in out:
                out[k] = {
                    "name": s.get("dataSourceName"),
                    "type": s.get("dataType"),
                    "cards": 0,
                }
            out[k]["cards"] += 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_json", type=Path,
                    help="Path to the Domo dashboard JSON file")
    ap.add_argument("out_dir", type=Path,
                    help="Output directory for the parsed signals")
    args = ap.parse_args()

    if not args.input_json.exists():
        sys.exit(f"input not found: {args.input_json}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with args.input_json.open(encoding="utf-8") as f:
        dashboard = json.load(f)

    parsed = parse(dashboard)

    # Write outputs
    card_signals_path = args.out_dir / "card-signals.json"
    layout_path = args.out_dir / "layout.json"
    controls_path = args.out_dir / "page-controls.json"

    with card_signals_path.open("w", encoding="utf-8") as f:
        json.dump({
            "page": parsed["page"],
            "datasources": parsed["datasources"],
            "cards": parsed["cards"],
        }, f, indent=2)
    with layout_path.open("w", encoding="utf-8") as f:
        json.dump(parsed["layout"], f, indent=2)
    with controls_path.open("w", encoding="utf-8") as f:
        json.dump(parsed["pageControls"], f, indent=2)

    n_cards = len(parsed["cards"])
    n_ds = len(parsed["datasources"])
    n_layout = len(parsed["layout"])
    n_slicers = len(parsed["pageControls"]["slicers"])
    print(f"OK  parsed {n_cards} cards | {n_layout} layout slots | "
          f"{n_ds} datasources | {n_slicers} page-level slicer columns")
    print(f"    -> {card_signals_path}")
    print(f"    -> {layout_path}")
    print(f"    -> {controls_path}")


if __name__ == "__main__":
    main()
