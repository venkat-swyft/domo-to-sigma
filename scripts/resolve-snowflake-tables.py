#!/usr/bin/env python3
"""Phase 2 — Interactively resolve Domo datasources to Snowflake tables.

Reads `card-signals.json` (or `gaps.json`) from the working dir, finds every
unique dataSourceId referenced by the dashboard, and for each one prompts the
user for the matching Snowflake {connection, database, schema, table}.

Writes `datasource-map.json`:

  {
    "<dataSourceId>": {
      "domoName": "Projects",
      "snowflake": {
        "connectionId": "<sigma-connection-id>",
        "database": "VAN_WEY",
        "schema": "MARTS",
        "table": "MART_PROJECTS"
      }
    },
    ...
  }

Column-name verification (via mcp__sigma-mcp-v2__describe) is the AGENT'S
follow-up step — this script doesn't call the Sigma API directly because the
MCP tools are session-scoped, not script-scoped.

  python resolve-snowflake-tables.py /tmp/<name>/
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def collect_datasources(work_dir: Path) -> dict:
    """Find unique Domo datasources from card-signals.json or gaps.json."""
    card_path = work_dir / "card-signals.json"
    gaps_path = work_dir / "gaps.json"
    if card_path.exists():
        with card_path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data.get("datasources") or {}
    if gaps_path.exists():
        with gaps_path.open(encoding="utf-8") as f:
            data = json.load(f)
        # gaps.json has a list — convert to dict shape
        out = {}
        for ds in data.get("datasources") or []:
            out[ds["id"]] = {"name": ds.get("name"), "type": ds.get("type"),
                             "cards": ds.get("cards")}
        return out
    sys.exit(f"No card-signals.json or gaps.json in {work_dir} — "
             "run parse-dashboard-json.py or scan-dashboard-gaps.py first")


def prompt(field: str, default: str | None = None) -> str:
    label = f"  {field}"
    if default:
        label += f" [{default}]"
    label += ": "
    v = input(label).strip()
    return v or (default or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work_dir", type=Path)
    args = ap.parse_args()

    datasources = collect_datasources(args.work_dir)
    if not datasources:
        sys.exit("No datasources found in the dashboard")

    out_path = args.work_dir / "datasource-map.json"
    existing = {}
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            existing = json.load(f)

    print(f"Found {len(datasources)} unique Domo datasource(s).\n")
    print("For each, provide the Snowflake mapping. Leave a field blank to keep "
          "the existing value (when re-running).\n")

    mapping = dict(existing)
    for ds_id, ds in datasources.items():
        prev = existing.get(ds_id, {}).get("snowflake") or {}
        print(f"  Datasource: {ds.get('name')}  (id={ds_id}, type={ds.get('type')}, "
              f"used by {ds.get('cards', '?')} cards)")
        conn_id = prompt("Sigma connectionId (UUID)", prev.get("connectionId"))
        database = prompt("Snowflake DATABASE", prev.get("database"))
        schema   = prompt("Snowflake SCHEMA", prev.get("schema"))
        table    = prompt("Snowflake TABLE/VIEW", prev.get("table"))
        if not (conn_id and database and schema and table):
            print("  -- incomplete; skipping this datasource for now\n")
            continue
        mapping[ds_id] = {
            "domoName": ds.get("name"),
            "snowflake": {
                "connectionId": conn_id,
                "database": database,
                "schema": schema,
                "table": table,
            },
        }
        print("  -- saved\n")

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
    print(f"OK  {len([m for m in mapping.values() if m.get('snowflake', {}).get('table')])} "
          f"datasource(s) mapped")
    print(f"    -> {out_path}")
    print("\nNext: verify column names via your Sigma MCP tools, then run "
          "build-dm-spec.py.")


if __name__ == "__main__":
    main()
