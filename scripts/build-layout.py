#!/usr/bin/env python3
"""Phase 5d — Build layout XML from layout.json + workbook readback IDs.

Reads:
  layout.json   — per-card grid coords (Domo 60-col + Sigma 24-col already computed)
  wb-ids.json   — server-assigned element IDs from POST + readback (post-and-readback.py)

Writes:
  layout.xml    — top-level XML for the workbook spec PUT (apply via put-layout.py)

Layout-item types:
  CARD       -> <LayoutElement> at the computed grid coords
  SEPARATOR  -> <LayoutElement> referencing a divider element
  HEADER     -> <LayoutElement> referencing a text element
  PAGE_BREAK -> dropped (web-only target)
  SPACER     -> dropped (leaves grid range empty)

  python build-layout.py /tmp/<name>/
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from layout_xml import le, page_xml, assemble


SKIP_TYPES = {"PAGE_BREAK", "SPACER"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work_dir", type=Path)
    args = ap.parse_args()

    layout = json.loads((args.work_dir / "layout.json").read_text(encoding="utf-8"))
    wb_ids = json.loads((args.work_dir / "wb-ids.json").read_text(encoding="utf-8"))

    # Map cardId -> sigma element id from readback
    el_by_card_hint = {}
    main_page_id = None
    for page in wb_ids.get("pages") or []:
        if page.get("name", "").lower().startswith("dashboard") and not main_page_id:
            main_page_id = page.get("id")
        for el in page.get("elements") or []:
            # build-workbook-spec uses element id pattern: "el-<slug(cardId)>"
            eid = el.get("id") or ""
            if eid.startswith("el-"):
                el_by_card_hint[eid] = eid  # exact match path

    if not main_page_id:
        # Fall back to the first page
        main_page_id = (wb_ids.get("pages") or [{}])[0].get("id")
        if not main_page_id:
            sys.exit("Could not find a page id in wb-ids.json")

    children = []
    dropped = 0
    for item in layout:
        if item["type"] in SKIP_TYPES:
            dropped += 1
            continue
        card_id = item.get("cardId")
        if not card_id:
            # SEPARATOR or HEADER without a cardId — these need divider/text
            # elements built upstream; skip if we can't resolve
            dropped += 1
            continue
        # Match: build-workbook-spec slugged the cardId. Lookup any element
        # whose id ends with the cardId-as-slug.
        target_id = None
        for eid in el_by_card_hint:
            if str(card_id) in eid:
                target_id = eid
                break
        if not target_id:
            print(f"WARN  no Sigma element id for cardId={card_id} — skipping")
            dropped += 1
            continue
        c0, c1 = item["sigmaCols"]
        r0, r1 = item["sigmaRows"]
        children.append(le(target_id, c0, c1, r0, r1))

    if not children:
        sys.exit("No layout children resolved — check that wb-ids.json has elements")

    xml = assemble(page_xml(main_page_id, *children))
    out_path = args.work_dir / "layout.xml"
    out_path.write_text(xml, encoding="utf-8")
    print(f"OK  {len(children)} layout elements on page {main_page_id} "
          f"({dropped} skipped)")
    print(f"    -> {out_path}")
    print("\nNext: put-layout.py --workbook <workbookId> --layout layout.xml")


if __name__ == "__main__":
    main()
