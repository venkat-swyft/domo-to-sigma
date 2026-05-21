#!/usr/bin/env python3
"""Phase 3 — Build a Sigma DM spec from the datasource map.

One DM element per unique Snowflake table referenced by the dashboard.
Columns come from a separate `columns.json` file the agent populates by
running `mcp__sigma-mcp-v2__describe` on each table — this script can't
call MCP tools.

Expected inputs in the work dir:
  datasource-map.json   — from Phase 2 (resolve-snowflake-tables.py)
  columns.json          — agent-populated: {<dataSourceId>: [{name, type}, ...]}

Output:
  dm-spec.json — ready to validate-spec + post-and-readback

  python build-dm-spec.py /tmp/<name>/ --name "<Workbook Title>" --folder-id <id>
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


SAFE_ID_RE = re.compile(r"[^A-Za-z0-9]+")


def el_id(prefix: str, value: str) -> str:
    s = SAFE_ID_RE.sub("-", value).strip("-").lower()
    return f"{prefix}-{s}"


def col_id(prefix: str, value: str) -> str:
    return el_id(prefix, value)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work_dir", type=Path)
    ap.add_argument("--name", required=True, help="DM display name")
    ap.add_argument("--folder-id", required=True,
                    help="Sigma folder ID (find via GET /v2/files?typeFilters=workbook -> parentId)")
    ap.add_argument("--schema-version", type=int, default=1)
    args = ap.parse_args()

    ds_map_path = args.work_dir / "datasource-map.json"
    cols_path = args.work_dir / "columns.json"
    if not ds_map_path.exists():
        sys.exit(f"Missing {ds_map_path} — run resolve-snowflake-tables.py first")
    if not cols_path.exists():
        sys.exit(
            f"Missing {cols_path}. Populate it from the agent side:\n"
            "  {<dataSourceId>: [{\"name\": \"COLUMN_NAME\", \"type\": \"varchar\"}, ...]}\n"
            "Use `mcp__sigma-mcp-v2__describe` on each Snowflake table."
        )

    with ds_map_path.open(encoding="utf-8") as f:
        ds_map = json.load(f)
    with cols_path.open(encoding="utf-8") as f:
        columns_by_ds = json.load(f)

    elements = []
    for ds_id, ds in ds_map.items():
        sf = ds.get("snowflake") or {}
        table = sf.get("table")
        if not table:
            print(f"WARN  skipping {ds_id} — no snowflake.table mapped")
            continue
        ds_cols = columns_by_ds.get(ds_id) or []
        if not ds_cols:
            print(f"WARN  skipping {ds_id} ({table}) — no columns in columns.json")
            continue

        name = ds.get("domoName") or table
        eid = el_id("el", name)
        cols = []
        order = []
        for c in ds_cols:
            col_name = c["name"]
            # Strip slashes from display name (would break formula prefix parsing)
            disp_name = col_name.replace("/", "-")
            cid = col_id("c", col_name)
            cols.append({
                "id": cid,
                "name": disp_name,
                "formula": f"[{table}/{col_name}]",
            })
            order.append(cid)

        elements.append({
            "id": eid,
            "kind": "table",
            "name": name,
            "source": {
                "connectionId": sf["connectionId"],
                "kind": "warehouse-table",
                "path": [sf["database"], sf["schema"], table],
            },
            "columns": cols,
            "order": order,
        })

    if not elements:
        sys.exit("No DM elements assembled — check datasource-map.json + columns.json")

    spec = {
        "name": args.name,
        "folderId": args.folder_id,
        "schemaVersion": args.schema_version,
        "pages": [
            {"id": "page-data", "name": "Data", "elements": elements}
        ],
    }

    out_path = args.work_dir / "dm-spec.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    print(f"OK  DM spec with {len(elements)} element(s)")
    print(f"    -> {out_path}")
    print("\nNext: validate-spec.py --type datamodel ; then post-and-readback.py --type datamodel")


if __name__ == "__main__":
    main()
