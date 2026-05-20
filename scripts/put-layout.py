#!/usr/bin/env python3
"""Apply a layout XML to an existing Sigma workbook.

The layout is a single top-level field on the workbook spec — NOT per-page.
This script:
  1. GETs the current workbook spec
  2. Replaces (or sets) the top-level `layout` with our XML
  3. Strips read-only metadata fields the API rejects on PUT
  4. Aborts if any elementId="" appears in the XML
  5. PUTs the full payload back

  python put-layout.py --workbook <workbookId> --layout /tmp/<name>/layout.xml
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from sigma_api import get, put, parse_yaml_or_json


# Server-managed fields that must not appear in a PUT body
READ_ONLY_FIELDS = {
    "workbookId", "dataModelId", "url", "ownerId", "createdBy", "updatedBy",
    "createdAt", "updatedAt", "latestDocumentVersion",
}


def strip_read_only(spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k not in READ_ONLY_FIELDS}


def strip_per_page_layout(spec: dict) -> dict:
    """Per-page `layout` fields are silently ignored — strip them so the top-level
    layout is unambiguous."""
    pages = spec.get("pages") or []
    for page in pages:
        page.pop("layout", None)
    return spec


def assert_no_empty_element_ids(xml: str):
    if re.search(r'elementId=""', xml) or re.search(r"elementId=''", xml):
        sys.exit("layout XML contains elementId=\"\" — refusing to PUT "
                 "(would orphan elements). Check wb-ids.json for nil IDs.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", required=True, help="Sigma workbookId")
    ap.add_argument("--layout", type=Path, required=True, help="Path to layout.xml")
    args = ap.parse_args()

    xml = args.layout.read_text(encoding="utf-8")
    assert_no_empty_element_ids(xml)

    spec_path = f"/v2/workbooks/{args.workbook}/spec"
    print(f"GET  {spec_path} ...")
    status, payload = get(spec_path)
    if status >= 300:
        sys.exit(f"GET failed ({status}):\n"
                 f"{payload.decode('utf-8', errors='replace')[:1000]}")
    spec = parse_yaml_or_json(payload)

    spec["layout"] = xml
    spec = strip_per_page_layout(spec)
    spec = strip_read_only(spec)

    # schemaVersion must be preserved
    if "schemaVersion" not in spec:
        sys.exit("workbook spec missing schemaVersion — won't PUT without it")

    print(f"PUT  {spec_path} ...")
    status, payload = put(spec_path, spec)
    if status >= 300:
        sys.exit(f"PUT failed ({status}):\n"
                 f"{payload.decode('utf-8', errors='replace')[:2000]}")
    print(f"OK  layout applied to workbook {args.workbook}")


if __name__ == "__main__":
    main()
