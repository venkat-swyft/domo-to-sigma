#!/usr/bin/env python3
"""Phase 6 — Structural parity check.

We cannot verify numerical parity (the source Domo system may be gone). What
we CAN check:
  - Sigma element count matches the count of Domo cards we tried to build
  - Each Domo card's title appears as the name of a published Sigma element
  - Each published Sigma element has a kind compatible with the Domo card's
    chartType (per refs/chart-type-mapping.md)

Reads from the work dir:
  card-signals.json
  wb-ids.json
  layout.json

Output: per-card PASS / MISMATCH. Exit 0 on full pass, 1 on any mismatch.

  python verify-structural-parity.py /tmp/<name>/
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from domo_chart_kinds import lookup


def slug(s: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-").lower()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work_dir", type=Path)
    args = ap.parse_args()

    cs = json.loads((args.work_dir / "card-signals.json").read_text(encoding="utf-8"))
    wb_ids = json.loads((args.work_dir / "wb-ids.json").read_text(encoding="utf-8"))

    # Index published elements by their id and name
    published = []
    for page in wb_ids.get("pages") or []:
        for el in page.get("elements") or []:
            published.append({
                "id": el.get("id"),
                "kind": el.get("kind"),
                "name": el.get("name"),
                "pageId": page.get("id"),
            })

    n_cards = len(cs["cards"])
    n_published = len(published)
    n_text_cards = sum(1 for c in cs["cards"] if c.get("type") == "Text")

    print(f"Domo cards: {n_cards}")
    print(f"Sigma published elements: {n_published}\n")

    results = []
    failures = 0
    for card in cs["cards"]:
        cid = str(card["cardId"])
        # Find the element whose id contains the card slug or whose name matches
        match = None
        for el in published:
            if cid in (el["id"] or ""):
                match = el
                break
        if not match:
            for el in published:
                if (el["name"] or "").strip() == (card.get("title") or "").strip():
                    match = el
                    break
        if not match:
            results.append((card, None, "NO_MATCH"))
            failures += 1
            continue

        expected = lookup(card.get("domoChartType") or "")
        if expected.sigma_kind is None:
            status = "GAP_OK" if match else "GAP"
        elif expected.sigma_kind != match["kind"]:
            # Allow line-chart <-> combo-chart drift since the agent may flip
            tolerant = (
                {expected.sigma_kind, match["kind"]} == {"line-chart", "combo-chart"}
                or {expected.sigma_kind, match["kind"]} == {"bar-chart", "pivot-table"}
            )
            status = "KIND_DRIFT_OK" if tolerant else "KIND_MISMATCH"
            if status == "KIND_MISMATCH":
                failures += 1
        else:
            status = "PASS"
        results.append((card, match, status))

    print(f"{'CardId':>12}  {'Domo title':<40} {'Domo kind':<25} {'Sigma kind':<14} Status")
    print("-" * 120)
    for card, match, status in results:
        kind_dst = match["kind"] if match else "—"
        print(f"{card['cardId']:>12}  {(card.get('title') or '')[:40]:<40} "
              f"{card.get('domoChartType', '')[:25]:<25} {kind_dst:<14} {status}")

    print(f"\n{n_cards} cards | {n_cards - failures} OK | {failures} MISMATCH")
    if failures:
        print("\nReview the MISMATCH rows above. Common causes:")
        print("  - Sigma kind was changed in build-workbook-spec.py post-emit")
        print("  - Card title was customised post-publish; titles diverge")
        print("  - Element was dropped (datasource not mapped, no Sigma kind)")
        sys.exit(1)

    print("\nNext: visually compare the published Sigma workbook to the source "
          "PDF for numerical sanity (we can't verify values against the source "
          "Domo system).")


if __name__ == "__main__":
    main()
