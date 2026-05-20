#!/usr/bin/env python3
"""POST a DM or workbook spec, then GET back to capture server-assigned IDs.

The Sigma spec endpoints return YAML by default. POST gives you a workbookId or
dataModelId but NOT element IDs — those come from a follow-up GET.

This script does both and emits a clean JSON ID map.

  python post-and-readback.py --type datamodel \\
    --spec /tmp/<name>/dm-spec.json --out /tmp/<name>/dm-ids.json
  python post-and-readback.py --type workbook \\
    --spec /tmp/<name>/wb-spec.json --out /tmp/<name>/wb-ids.json
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from sigma_api import post, get, parse_yaml_or_json


SPEC_ENDPOINT = {
    "datamodel": "/v2/dataModels/spec",
    "workbook":  "/v2/workbooks/spec",
}

GET_BY_ID = {
    "datamodel": lambda i: f"/v2/dataModels/{i}/spec",
    "workbook":  lambda i: f"/v2/workbooks/{i}/spec",
}

RESPONSE_ID_KEY = {
    "datamodel": "dataModelId",
    "workbook":  "workbookId",
}


def extract_ids(spec):
    """Walk a (YAML/JSON-parsed) spec and emit {pages: [{id, name, elements: [...]}]}."""
    pages = []
    for page in spec.get("pages") or []:
        pages.append({
            "id": page.get("id"),
            "name": page.get("name"),
            "elements": [
                {"id": el.get("id"), "kind": el.get("kind"), "name": el.get("name")}
                for el in (page.get("elements") or [])
            ],
        })
    return pages


def check_for_error_columns(spec):
    """Universal column-type guard. Any column whose 'type' resolved to 'error' on
    GET means the formula failed to compile silently — abort.
    """
    bad = []
    for page in spec.get("pages") or []:
        for el in page.get("elements") or []:
            for col in el.get("columns") or []:
                t = col.get("type")
                if t == "error":
                    bad.append({
                        "element": el.get("name"),
                        "column": col.get("name"),
                        "formula": col.get("formula"),
                    })
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--type", choices=["datamodel", "workbook"], required=True)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    with args.spec.open(encoding="utf-8") as f:
        body = json.load(f)

    # POST
    endpoint = SPEC_ENDPOINT[args.type]
    print(f"POST {endpoint} ...")
    status, payload = post(endpoint, body)
    if status >= 300:
        sys.exit(f"POST failed ({status}):\n{payload.decode('utf-8', errors='replace')[:2000]}")
    posted = parse_yaml_or_json(payload)
    obj_id = posted.get(RESPONSE_ID_KEY[args.type])
    if not obj_id:
        sys.exit(f"POST response missing {RESPONSE_ID_KEY[args.type]}: "
                 f"{json.dumps(posted)[:500]}")
    print(f"  -> {RESPONSE_ID_KEY[args.type]} = {obj_id}")

    # GET back for element IDs
    get_path = GET_BY_ID[args.type](obj_id)
    print(f"GET  {get_path} ...")
    status, payload = get(get_path)
    if status >= 300:
        sys.exit(f"GET back failed ({status})")
    readback = parse_yaml_or_json(payload)

    # Column-type guard
    bad = check_for_error_columns(readback)
    if bad:
        print(f"\n!! {len(bad)} column(s) resolved to type 'error' on readback:")
        for b in bad:
            print(f"   - {b['element']} / {b['column']}: {b['formula']!r}")
        print("\nThese failed silently at POST time (formula compile error). Fix and re-POST.")
        sys.exit(2)

    # Emit ID map
    out_obj = {
        RESPONSE_ID_KEY[args.type]: obj_id,
        "pages": extract_ids(readback),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(out_obj, f, indent=2)
    n_el = sum(len(p["elements"]) for p in out_obj["pages"])
    print(f"OK  {len(out_obj['pages'])} pages | {n_el} elements")
    print(f"    -> {args.out}")


if __name__ == "__main__":
    main()
