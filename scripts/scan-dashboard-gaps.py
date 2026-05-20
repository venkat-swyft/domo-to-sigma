#!/usr/bin/env python3
"""Phase 0a — Scan a Domo dashboard JSON for feature gaps.

Emits gaps-report.md (human-readable summary) and gaps.json (machine).
Run BEFORE Phase 1a to set customer expectations on what will / won't convert cleanly.
"""

from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from domo_chart_kinds import lookup as kind_lookup, MAPPING


CLASS_EMOJI = {"auto": "✅", "hint": "⚠️", "gap": "❌", "unknown": "❓"}
CLASS_LABEL = {"auto": "Auto", "hint": "Hint", "gap": "Gap", "unknown": "Unknown"}


def scan(dashboard: dict) -> dict:
    cards = dashboard.get("cards") or []
    chart_counts = Counter(
        (c.get("metadata") or {}).get("chartType") or c.get("type") or "unknown"
        for c in cards
    )

    by_class = defaultdict(list)
    chart_table = []
    for ct, n in chart_counts.most_common():
        m = kind_lookup(ct)
        chart_table.append({
            "domoChartType": ct,
            "count": n,
            "sigmaKind": m.sigma_kind,
            "class": m.cls,
            "note": m.note,
        })
        by_class[m.cls].append((ct, n, m.sigma_kind, m.note))

    # Datasources
    datasources = {}
    for c in cards:
        for s in c.get("datasources") or []:
            k = s.get("dataSourceId")
            if not k:
                continue
            ds = datasources.setdefault(k, {
                "id": k,
                "name": s.get("dataSourceName"),
                "type": s.get("dataType"),
                "cards": 0,
            })
            ds["cards"] += 1

    return {
        "title": dashboard.get("title") or (dashboard.get("page") or {}).get("title"),
        "pageId": (dashboard.get("page") or {}).get("pageId"),
        "totalCards": len(cards),
        "chartTypeCounts": chart_table,
        "byClass": {
            cls: [{"domoChartType": ct, "count": n, "sigmaKind": sk, "note": note}
                  for ct, n, sk, note in items]
            for cls, items in by_class.items()
        },
        "datasources": list(datasources.values()),
    }


def render_markdown(report: dict) -> str:
    lines = []
    lines.append(f"# Gap report — {report['title'] or '(untitled dashboard)'}")
    lines.append("")
    lines.append(f"- Page ID: `{report['pageId']}`")
    lines.append(f"- Total cards: {report['totalCards']}")
    lines.append(f"- Distinct chart types: {len(report['chartTypeCounts'])}")
    lines.append(f"- Datasources: {len(report['datasources'])}")
    lines.append("")

    lines.append("## Chart-type coverage")
    lines.append("")
    lines.append("| Class | Domo chartType | Count | Sigma kind | Note |")
    lines.append("|---|---|---:|---|---|")
    for row in report["chartTypeCounts"]:
        cls = row["class"]
        sk = row["sigmaKind"] or "—"
        lines.append(
            f"| {CLASS_EMOJI[cls]} {CLASS_LABEL[cls]} | `{row['domoChartType']}` | "
            f"{row['count']} | `{sk}` | {row['note']} |"
        )
    lines.append("")

    by_class = report["byClass"]
    if by_class.get("gap"):
        lines.append("## ❌ Unhandled chart types")
        lines.append("")
        lines.append("These have no native Sigma equivalent. Discuss with the customer:")
        lines.append("")
        for r in by_class["gap"]:
            lines.append(f"- **`{r['domoChartType']}`** × {r['count']} — {r['note']}")
        lines.append("")
    if by_class.get("hint"):
        lines.append("## ⚠️ Maps with caveats")
        lines.append("")
        for r in by_class["hint"]:
            lines.append(
                f"- **`{r['domoChartType']}`** × {r['count']} → `{r['sigmaKind']}` "
                f"— {r['note']}"
            )
        lines.append("")

    lines.append("## Datasources")
    lines.append("")
    lines.append("Each unique Domo dataSourceId becomes one Sigma data-model element.")
    lines.append("You'll be asked to map each to a Snowflake table during Phase 2.")
    lines.append("")
    lines.append("| dataSourceId | Domo name | Type | Cards using |")
    lines.append("|---|---|---|---:|")
    for ds in sorted(report["datasources"], key=lambda d: -d["cards"]):
        lines.append(
            f"| `{ds['id']}` | {ds['name']} | {ds['type']} | {ds['cards']} |"
        )
    lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_json", type=Path)
    ap.add_argument("out_dir", type=Path)
    args = ap.parse_args()

    if not args.input_json.exists():
        sys.exit(f"input not found: {args.input_json}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with args.input_json.open(encoding="utf-8") as f:
        dashboard = json.load(f)

    report = scan(dashboard)
    md = render_markdown(report)

    md_path = args.out_dir / "gaps-report.md"
    json_path = args.out_dir / "gaps.json"
    md_path.write_text(md, encoding="utf-8")
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Print summary to stdout
    by_class = report["byClass"]
    auto = sum(r["count"] for r in by_class.get("auto", []))
    hint = sum(r["count"] for r in by_class.get("hint", []))
    gap = sum(r["count"] for r in by_class.get("gap", []))
    print(f"OK  {report['totalCards']} cards | {auto} auto | {hint} hint | {gap} gap")
    print(f"    -> {md_path}")
    print(f"    -> {json_path}")
    if gap:
        print(f"\n!!  {gap} card(s) use unsupported Domo chart types — review gaps-report.md")


if __name__ == "__main__":
    main()
