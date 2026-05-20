#!/usr/bin/env python3
"""Pre-POST validator for Sigma DM or workbook specs.

Catches issues that the API would reject (and a few it silently accepts).

Exit 0 = clean. Exit 1 = errors printed to stdout.

  python validate-spec.py --type datamodel /tmp/<name>/dm-spec.json
  python validate-spec.py --type workbook --dm-context /tmp/<name>/dm-ids.json /tmp/<name>/wb-spec.json
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


# Chart kinds that frequently get wrong (common Sigma example library typos)
INVALID_KINDS = {"kpi", "pie", "donut"}

# Valid Sigma kinds we currently target
VALID_KINDS = {
    "table", "pivot-table", "bar-chart", "line-chart", "area-chart",
    "combo-chart", "scatter-chart", "kpi-chart", "pie-chart", "donut-chart",
    "region-map", "point-map", "control", "text", "image", "container", "divider",
}

# Valid control types
VALID_CONTROL_TYPES = {
    "list", "date-range", "text", "text-area", "segmented",
    "number", "number-range", "slider", "range-slider", "top-n",
}


def fail(errors, msg):
    errors.append(msg)


def validate_columns(element, errors, ctx):
    """Common column shape: id + name + formula; name has no slashes."""
    cols = element.get("columns") or []
    seen = set()
    for c in cols:
        cid = c.get("id")
        name = c.get("name")
        formula = c.get("formula")
        if not cid:
            fail(errors, f"{ctx}: column missing id")
        elif cid in seen:
            fail(errors, f"{ctx}: duplicate column id {cid!r}")
        else:
            seen.add(cid)
        if not name:
            fail(errors, f"{ctx}: column {cid!r} missing name")
        elif "/" in name:
            fail(errors, f"{ctx}: column name {name!r} contains '/' — rename "
                         f"(slashes break formula prefix parsing)")
        if not formula:
            fail(errors, f"{ctx}: column {cid!r} missing formula")
    return [c["id"] for c in cols if c.get("id")]


def validate_dm(spec, errors):
    if not spec.get("name"):
        fail(errors, "datamodel: top-level 'name' is required")
    if not spec.get("folderId"):
        fail(errors, "datamodel: 'folderId' is required — find via "
                     "GET /v2/files?typeFilters=workbook -> parentId")
    pages = spec.get("pages") or []
    if not pages:
        fail(errors, "datamodel: at least one page with elements is required")

    element_ids = set()
    for pi, page in enumerate(pages):
        for ei, el in enumerate(page.get("elements") or []):
            ctx = f"datamodel pages[{pi}].elements[{ei}] id={el.get('id')!r}"
            eid = el.get("id")
            if not eid:
                fail(errors, f"{ctx}: element missing id")
            elif eid in element_ids:
                fail(errors, f"{ctx}: duplicate element id {eid!r}")
            else:
                element_ids.add(eid)
            kind = el.get("kind")
            if kind != "table":
                fail(errors, f"{ctx}: DM element kind must be 'table' (got {kind!r})")
            src = el.get("source") or {}
            src_kind = src.get("kind")
            if src_kind not in {"warehouse-table", "sql"}:
                fail(errors, f"{ctx}: source.kind must be 'warehouse-table' or 'sql' "
                             f"(got {src_kind!r})")
            if src_kind == "warehouse-table":
                if not src.get("path"):
                    fail(errors, f"{ctx}: warehouse-table source missing 'path' array")
                if not src.get("connectionId"):
                    fail(errors, f"{ctx}: source missing 'connectionId'")
            if src_kind == "sql":
                if not src.get("statement"):
                    fail(errors, f"{ctx}: sql source missing 'statement' "
                                 "(use field name 'statement', NOT 'sql')")
            col_ids = validate_columns(el, errors, ctx)
            order = el.get("order") or []
            for oid in order:
                if oid not in col_ids:
                    fail(errors, f"{ctx}: order[] references unknown column id {oid!r}")


def validate_workbook(spec, errors, dm_context=None):
    if not spec.get("name"):
        fail(errors, "workbook: top-level 'name' is required")
    if not spec.get("folderId"):
        fail(errors, "workbook: 'folderId' is required")
    pages = spec.get("pages") or []
    if not pages:
        fail(errors, "workbook: at least one page is required")

    # Build the set of DM element names available for cross-source refs
    dm_element_names = set()
    if dm_context:
        for page in dm_context.get("pages") or []:
            for el in page.get("elements") or []:
                if el.get("name"):
                    dm_element_names.add(el["name"])

    page_ids = set()
    for pi, page in enumerate(pages):
        pid = page.get("id")
        if not pid:
            fail(errors, f"workbook pages[{pi}]: missing id")
        elif pid in page_ids:
            fail(errors, f"workbook pages[{pi}]: duplicate page id {pid!r}")
        else:
            page_ids.add(pid)

        for ei, el in enumerate(page.get("elements") or []):
            ctx = f"workbook pages[{pi}].elements[{ei}] id={el.get('id')!r}"
            kind = el.get("kind")
            if kind in INVALID_KINDS:
                fail(errors, f"{ctx}: invalid kind {kind!r} — use "
                             f"{kind!r}-chart instead (kpi-chart / pie-chart / donut-chart)")
            elif kind not in VALID_KINDS:
                fail(errors, f"{ctx}: unknown kind {kind!r} (valid: {sorted(VALID_KINDS)})")
            if kind == "control":
                ctype = el.get("controlType")
                if ctype not in VALID_CONTROL_TYPES:
                    fail(errors, f"{ctx}: controlType {ctype!r} not in {sorted(VALID_CONTROL_TYPES)}")
            if kind in {"bar-chart", "line-chart", "area-chart", "combo-chart", "scatter-chart"}:
                if "yAxis" not in el:
                    fail(errors, f"{ctx}: {kind} requires a yAxis field")
            if kind in {"pie-chart", "donut-chart"}:
                if not el.get("value") or not el.get("color"):
                    fail(errors, f"{ctx}: {kind} requires both 'value' and 'color' fields")
                if kind == "donut-chart":
                    v_id = (el.get("value") or {}).get("id")
                    h_id = (el.get("holeValue") or {}).get("id")
                    if h_id and h_id == v_id:
                        fail(errors, f"{ctx}: donut holeValue.id == value.id — "
                                     "Sigma silently drops the element")
            validate_columns(el, errors, ctx)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--type", choices=["datamodel", "workbook"], required=True)
    ap.add_argument("--dm-context", type=Path, default=None,
                    help="Path to dm-ids.json from a prior DM POST (workbook mode only)")
    ap.add_argument("spec", type=Path)
    args = ap.parse_args()

    with args.spec.open(encoding="utf-8") as f:
        spec = json.load(f)
    dm_context = None
    if args.dm_context:
        with args.dm_context.open(encoding="utf-8") as f:
            dm_context = json.load(f)

    errors = []
    if args.type == "datamodel":
        validate_dm(spec, errors)
    else:
        validate_workbook(spec, errors, dm_context=dm_context)

    if errors:
        print(f"FAIL  {len(errors)} validation error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"OK  {args.spec} validates as {args.type}")


if __name__ == "__main__":
    main()
