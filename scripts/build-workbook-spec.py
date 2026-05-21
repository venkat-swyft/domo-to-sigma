#!/usr/bin/env python3
"""Phase 5a — Assemble a Sigma workbook spec from Domo signals.

This is the heart of the conversion. Inputs (all from the work dir):
  card-signals.json       — per-card metadata (JSON+PDF mode: from parse-dashboard-json.py;
                            PDF-only mode: agent-built from PDF vision read)
  pdf-extractions.json    — per-card columns/measures from PDF vision (JSON+PDF mode only)
  layout.json             — layout slots (JSON+PDF mode)
  page-controls.json      — page-level slicers + date filter (JSON+PDF mode)
  datasource-map.json     — Snowflake mapping
  dm-ids.json             — server-assigned DM element IDs from Phase 4
  columns.json            — Snowflake columns per datasource (agent-populated)

Output:
  wb-spec.json — ready to validate + POST

  python build-workbook-spec.py /tmp/<name>/ \\
      --title "<Workbook Title>" --folder-id <id> --schema-version 1

Many decisions here are opinionated and benefit from agent review of the
emitted spec before POST. WARN lines flag the assumptions made.
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))


SAFE = re.compile(r"[^A-Za-z0-9]+")


def slug(s: str) -> str:
    return SAFE.sub("-", s or "").strip("-").lower()


def fmt_to_sigma(domo_fmt: dict) -> dict | None:
    """Translate one entry from Domo columnFormats into a Sigma format object."""
    if not domo_fmt:
        return None
    t = (domo_fmt.get("type") or "").lower()
    precision = domo_fmt.get("precision", 0) or 0
    abbr = domo_fmt.get("abbreviate", False)
    if t == "percent":
        # Domo "percentMultiplied: true" matches Sigma's percent format which
        # already multiplies by 100
        return {"kind": "number", "formatString": f",.{precision}%"}
    if t == "currency":
        sym = domo_fmt.get("currencySymbol", "$")
        suffix = "s" if abbr else "f"
        return {
            "kind": "number",
            "formatString": f"{sym},.{precision}{suffix}",
            "currencySymbol": sym,
        }
    if t == "number":
        suffix = "s" if abbr else "f"
        return {"kind": "number", "formatString": f",.{precision}{suffix}"}
    return None


def find_sf_column(name: str, sf_columns: list[dict]) -> dict | None:
    """Match a Domo display column name to a Snowflake column (case-insensitive,
    underscore-vs-space-tolerant)."""
    if not name:
        return None
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    target = norm(name)
    for c in sf_columns:
        if norm(c["name"]) == target:
            return c
    return None


def build_master(ds_id: str, ds_entry: dict, dm_ids: dict,
                 sf_columns: list[dict]) -> dict:
    """Build the master table for one datasource, sourced from the DM element.
    All columns pulled through as passthrough refs."""
    sf = ds_entry["snowflake"]
    domo_name = ds_entry.get("domoName") or sf["table"]
    master_id = f"master-{slug(domo_name)}"
    # Find the DM element ID by name
    dm_element_id = None
    for page in dm_ids.get("pages") or []:
        for el in page.get("elements") or []:
            if el.get("name") == domo_name:
                dm_element_id = el["id"]
                break
    if not dm_element_id:
        sys.exit(f"Could not find DM element named {domo_name!r} in dm-ids.json")

    cols = []
    order = []
    for c in sf_columns:
        cid = f"m-{slug(c['name'])}"
        cols.append({
            "id": cid,
            "name": c["name"].replace("/", "-"),
            "formula": f"[{domo_name}/{c['name'].replace('/', '-')}]",
        })
        order.append(cid)

    return {
        "id": master_id,
        "kind": "table",
        "name": f"Master ({domo_name})",
        "visibleAsSource": False,
        "source": {
            "kind": "data-model",
            "dataModelId": dm_ids["dataModelId"],
            "elementId": dm_element_id,
        },
        "columns": cols,
        "order": order,
    }


def build_control(slicer: dict, ds_id: str, master_name: str,
                  sf_columns: list[dict]) -> dict | None:
    """Translate a Domo slicer into a Sigma list control."""
    col_name = slicer.get("column")
    if not col_name:
        return None
    op = (slicer.get("operator") or "").upper()
    mode = "exclude" if op == "NOT_IN" else "include"
    sf_col = find_sf_column(col_name, sf_columns)
    if not sf_col:
        print(f"WARN  slicer column {col_name!r} not in datasource columns; emitting "
              "with bare reference — verify after POST")
        target_formula = f"[{master_name}/{col_name}]"
    else:
        target_formula = f"[{master_name}/{sf_col['name'].replace('/', '-')}]"
    cid = f"ctl-{slug(ds_id)}-{slug(col_name)}"
    return {
        "id": f"el-{cid}",
        "kind": "control",
        "controlType": "list",
        "controlId": cid,
        "name": col_name,
        "mode": mode,
        "filters": [{
            "source": {"kind": "element", "elementId": "_master_placeholder_"},
            "columnFormula": target_formula,
        }],
    }


def build_date_range_control(date_filter: dict, ds_id: str,
                             master_name: str, sf_columns: list[dict]) -> dict | None:
    if not date_filter:
        return None
    col = date_filter.get("column")
    if not col:
        return None
    mode = date_filter.get("mode", "rolling")
    unit = date_filter.get("unit") or "day"
    count = date_filter.get("count")
    sf_col = find_sf_column(col, sf_columns)
    target_formula = (
        f"[{master_name}/{sf_col['name'].replace('/', '-')}]"
        if sf_col else f"[{master_name}/{col}]"
    )
    cid = f"ctl-{slug(ds_id)}-date"
    spec = {
        "id": f"el-{cid}",
        "kind": "control",
        "controlType": "date-range",
        "controlId": cid,
        "name": col,
        "filters": [{
            "source": {"kind": "element", "elementId": "_master_placeholder_"},
            "columnFormula": target_formula,
        }],
    }
    if mode == "rolling":
        spec["mode"] = "current"
        spec["unit"] = unit
        spec["count"] = count
    elif mode == "current":
        spec["mode"] = "current"
        spec["unit"] = unit
    return spec


def build_chart_for_card(card: dict, extractions: dict, master_id: str,
                        master_name: str, sf_columns: list[dict]) -> dict | None:
    """Translate one card into a Sigma element. Best-effort; flags assumptions."""
    cid = card["cardId"]
    kind = card.get("sigmaKind")
    if not kind:
        print(f"WARN  card {cid} ({card.get('title')!r}): no Sigma kind — skipping. "
              f"({card.get('mappingNote')})")
        return None

    extr = (extractions or {}).get(str(cid), {})
    measures = extr.get("measures") or []
    dims = extr.get("dimensions") or []
    title = card.get("title") or f"Card {cid}"

    el = {
        "id": f"el-{slug(str(cid))}",
        "kind": kind,
        "name": title,
        "source": {"kind": "table", "elementId": master_id},
        "columns": [],
    }

    # Column formats
    formats = card.get("columnFormats") or {}

    def col_formula(col_name: str):
        sf_col = find_sf_column(col_name, sf_columns)
        actual = sf_col["name"].replace("/", "-") if sf_col else col_name
        return f"[{master_name}/{actual}]"

    def add_col(role: str, name: str, formula: str, agg: str | None = None):
        col = {"id": f"c-{slug(str(cid))}-{role}-{slug(name)}", "name": name,
               "formula": formula}
        fmt = fmt_to_sigma(formats.get(name))
        if fmt:
            col["format"] = fmt
        if agg:
            col["aggregate"] = {"function": agg}
        el["columns"].append(col)
        return col["id"]

    if kind == "kpi-chart":
        if not measures:
            print(f"WARN  KPI {title!r} has no measure from PDF extraction; emit empty")
            return el
        # Single big-number KPI uses the first measure
        m = measures[0]
        col_id = add_col("value", m, f"Sum({col_formula(m)})")
        el["value"] = {"id": col_id}

    elif kind in {"bar-chart", "line-chart", "area-chart", "combo-chart"}:
        if not dims:
            print(f"WARN  {kind} {title!r}: no dimension from PDF — emit without xAxis")
        else:
            x_id = add_col("x", dims[0], col_formula(dims[0]))
            el["xAxis"] = {"columnIds": [x_id]}
        if not measures:
            print(f"WARN  {kind} {title!r}: no measure from PDF — emit without yAxis")
        else:
            y_ids = [add_col("y", m, f"Sum({col_formula(m)})") for m in measures]
            el["yAxis"] = {"columnIds": y_ids}

    elif kind in {"pie-chart", "donut-chart"}:
        if not dims or not measures:
            print(f"WARN  {kind} {title!r}: needs both dim+measure from PDF; emit stub")
            return el
        v_id = add_col("value", measures[0], f"Sum({col_formula(measures[0])})")
        c_id = add_col("color", dims[0], col_formula(dims[0]))
        el["value"] = {"id": v_id}
        el["color"] = {"id": c_id}

    elif kind == "scatter-chart":
        if len(measures) >= 2 and dims:
            x_id = add_col("x", measures[0], f"Sum({col_formula(measures[0])})")
            y_id = add_col("y", measures[1], f"Sum({col_formula(measures[1])})")
            d_id = add_col("color", dims[0], col_formula(dims[0]))
            el["xAxis"] = {"columnIds": [x_id]}
            el["yAxis"] = {"columnIds": [y_id]}
            el["color"] = {"id": d_id}
        else:
            print(f"WARN  scatter {title!r}: needs 2 measures + 1 dim; emit stub")

    elif kind == "region-map":
        ct = card.get("domoChartType", "")
        region_type = "county" if "county" in ct else ("state" if "state" in ct else "state")
        if not measures or not dims:
            print(f"WARN  region-map {title!r}: needs dim (geo) + measure; emit stub")
            return el
        v_id = add_col("value", measures[0], f"Sum({col_formula(measures[0])})")
        g_id = add_col("geo", dims[0], col_formula(dims[0]))
        el["regionType"] = region_type
        el["value"] = {"id": v_id}
        el["geo"] = {"id": g_id}

    elif kind == "table":
        for d in dims:
            add_col("dim", d, col_formula(d))
        for m in measures:
            add_col("measure", m, f"Sum({col_formula(m)})")

    elif kind == "pivot-table":
        if not dims:
            print(f"WARN  pivot-table {title!r}: needs row dim; emit stub")
            return el
        r_id = add_col("row", dims[0], col_formula(dims[0]))
        el["rowsBy"] = [{"columnId": r_id}]
        if len(dims) >= 2:
            c_id = add_col("col", dims[1], col_formula(dims[1]))
            el["columnsBy"] = [{"columnId": c_id}]
        for m in measures:
            v_id = add_col("value", m, f"Sum({col_formula(m)})")
            el.setdefault("values", []).append({"columnId": v_id})

    elif kind == "text":
        # Domo text card; body from titleTemplate or title
        body = card.get("titleTemplate") or title
        body_md = body if body.startswith("#") else f"## {body}"
        return {
            "id": f"el-{slug(str(cid))}",
            "kind": "text",
            "body": body_md,
        }

    else:
        print(f"WARN  card {cid} kind={kind}: not specialised; emit minimal")

    return el


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("work_dir", type=Path)
    ap.add_argument("--title", required=True)
    ap.add_argument("--folder-id", required=True)
    ap.add_argument("--schema-version", type=int, default=1)
    args = ap.parse_args()

    wd = args.work_dir
    cs = json.loads((wd / "card-signals.json").read_text(encoding="utf-8"))
    ds_map = json.loads((wd / "datasource-map.json").read_text(encoding="utf-8"))
    dm_ids = json.loads((wd / "dm-ids.json").read_text(encoding="utf-8"))
    columns_by_ds = json.loads((wd / "columns.json").read_text(encoding="utf-8"))
    extractions = {}
    extr_path = wd / "pdf-extractions.json"
    if extr_path.exists():
        extractions = json.loads(extr_path.read_text(encoding="utf-8"))
    page_controls_path = wd / "page-controls.json"
    page_controls = {}
    if page_controls_path.exists():
        page_controls = json.loads(page_controls_path.read_text(encoding="utf-8"))

    # Cards are grouped by their datasource; one master per ds, charts on Main page
    cards_by_ds = {}
    for c in cs["cards"]:
        for ds in (c.get("datasourceIds") or []):
            cards_by_ds.setdefault(ds, []).append(c)

    # Data page: one master table per datasource
    data_elements = []
    main_elements = []
    primary_ds_id = None
    primary_master_id = None
    primary_master_name = None

    for ds_id, ds_cards in cards_by_ds.items():
        ds_entry = ds_map.get(ds_id)
        if not ds_entry or not ds_entry.get("snowflake"):
            print(f"WARN  datasource {ds_id} has no Snowflake mapping; skipping its "
                  f"{len(ds_cards)} card(s)")
            continue
        sf_columns = columns_by_ds.get(ds_id) or []
        master = build_master(ds_id, ds_entry, dm_ids, sf_columns)
        data_elements.append(master)

        # First mapped datasource = primary (controls bind to its master)
        if not primary_ds_id:
            primary_ds_id = ds_id
            primary_master_id = master["id"]
            primary_master_name = master["name"]

        # Build charts
        for card in ds_cards:
            ch = build_chart_for_card(
                card, extractions, master["id"], master["name"], sf_columns,
            )
            if ch:
                main_elements.append(ch)

    # Controls — bind to the primary master
    controls = []
    if primary_master_id and page_controls:
        sf_cols_primary = columns_by_ds.get(primary_ds_id) or []
        for s in page_controls.get("slicers") or []:
            ctl = build_control(s, primary_ds_id, primary_master_name, sf_cols_primary)
            if ctl:
                # Patch placeholder with the actual master id
                for f in ctl["filters"]:
                    f["source"]["elementId"] = primary_master_id
                controls.append(ctl)
        df_ctl = build_date_range_control(
            page_controls.get("dateFilter"), primary_ds_id, primary_master_name,
            sf_cols_primary,
        )
        if df_ctl:
            for f in df_ctl["filters"]:
                f["source"]["elementId"] = primary_master_id
            controls.append(df_ctl)

    main_page = {
        "id": "page-main",
        "name": "Dashboard",
        "elements": controls + main_elements,
    }
    data_page = {
        "id": "page-data",
        "name": "Data",
        "elements": data_elements,
    }

    spec = {
        "name": args.title,
        "folderId": args.folder_id,
        "schemaVersion": args.schema_version,
        "pages": [main_page, data_page],
    }

    out_path = wd / "wb-spec.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    n_cards = len(main_elements)
    n_ctl = len(controls)
    print(f"OK  workbook spec: {n_cards} chart elements, {n_ctl} controls, "
          f"{len(data_elements)} master tables")
    print(f"    -> {out_path}")
    print("\nNext: validate-spec.py --type workbook --dm-context dm-ids.json "
          f"{out_path}")


if __name__ == "__main__":
    main()
