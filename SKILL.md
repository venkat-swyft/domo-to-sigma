---
name: domo-to-sigma
description: >-
  Convert a Domo dashboard into a Sigma workbook by reconstructing it from a
  Domo dashboard JSON export plus a rendered PDF. Use when the user has a
  Domo dashboard they want to recreate in Sigma — typically because Domo is
  being deprecated and they only have export artifacts left. Discovery via
  JSON parse + agent-driven PDF read, data model creation, workbook layout,
  and structural parity verification — driven by `scripts/*.py`.
user-invocable: true
---

# Domo → Sigma Conversion

Convert a Domo dashboard into a Sigma data model + matching workbook. The Domo side is **forensic** — the source org may be gone; all you typically have is a dashboard JSON export and/or a PDF of how it looked. The Sigma side is live API.

## Two input modes

| Mode | When | Inputs | What the agent does |
|---|---|---|---|
| **PDF-only** | Source Domo is gone or inaccessible; only a rendered PDF survives | `dashboard.pdf` | Reads every page with vision, builds the full conversion plan from visual evidence: chart inventory, layout grid, titles, axis labels, columns/measures, page controls visible in chrome |
| **JSON+PDF** | Source Domo is accessible enough to export the page JSON, OR a prior export was saved | `dashboard.json` + `dashboard.pdf` | Phase 1a script extracts layout, kinds, formats, controls, dynamic titles, datasource refs from JSON; Phase 1b agent fills in only the per-card columns/measures from PDF |

JSON+PDF is the higher-fidelity path — it captures things the PDF can't show (page-level slicers without selected values, format precision, dynamic title templates with date tokens, exact 60-col grid coords). PDF-only works but requires more agent legwork and produces approximate layout positions.

> **For most current Domo→Sigma migrations the source Domo system is no longer live.** The skill defaults to PDF-only. If the user has a JSON export, they pass `--json /path/to/dashboard.json` to enable JSON+PDF mode and the JSON-side phases auto-run.

**Read ALL of the following before replying or taking any action:**
- `refs/chart-type-mapping.md` — Domo `badge_*` chart types → Sigma element `kind` (used in both modes)
- `refs/pdf-extraction-protocol.md` — how the agent reads card-level details from the PDF (the primary phase in PDF-only mode; complements JSON in JSON+PDF mode)
- `refs/domo-json-shape.md` — JSON+PDF mode only: what each Domo JSON field means and which ones we read
- `refs/layout-grid-conversion.md` — JSON+PDF mode only: 60-col Domo → 24-col Sigma grid arithmetic + row-height heuristics

**For canonical Sigma workbook + DM spec shape**, defer to the sibling skills:
- `~/sigma-skills/sigma-workbooks/reference/specification/` — chart kinds, control types, source kinds, formulas, formatting
- `~/sigma-skills/sigma-data-models/reference/` — DM element shape, columns, calc columns, relationships

This skill restates only the **Domo-conversion-specific** patterns; everything else lives in the sibling skills. Read those whenever you need the current Sigma spec surface — when this file disagrees with the sibling refs, the siblings win.

---

## Scripts

The conversion is driven by `scripts/*.py`. Each script encapsulates one phase. You compose them; the agent's role is judgment (chart-kind decisions when the PDF is ambiguous, calc translations, layout sanity) — not orchestration.

| Script | Purpose |
|---|---|
| `scripts/setup.py` | One-time Sigma credential setup |
| `scripts/get-token.sh` | Exchange `SIGMA_CLIENT_ID`/`SIGMA_CLIENT_SECRET` for `SIGMA_API_TOKEN` (~1h TTL) |
| `scripts/scan-dashboard-gaps.py` | **Phase 0a (mandatory):** scan the JSON and emit `gaps-report.md` + `gaps.json`. Inventories every Domo `chartType` and every datasource; classifies each as ✅ auto / ⚠️ hint / ❌ unhandled. Run BEFORE any other phase. |
| `scripts/parse-dashboard-json.py` | **Phase 1a:** parse the JSON into `card-signals.json` (per-card metadata) + `layout.json` (60→24-col layout) + `page-controls.json` (slicers + date filter). Mechanical, no judgment. |
| `scripts/extract-pdf-cards.py` | **Phase 1b helper:** split the dashboard PDF into per-page images so the agent can read each card region with vision. Agent then writes `pdf-extractions.json` (one entry per cardId with visible columns / measures / axis labels). |
| `scripts/resolve-snowflake-tables.py` | **Phase 2:** interactive walk through unique datasources. Per datasource, ask the user for the Snowflake `{schema, table}` and verify via `mcp__sigma-mcp-v2__describe`. Writes `datasource-map.json`. |
| `scripts/build-dm-spec.py` | **Phase 3:** assemble DM spec from `datasource-map.json` + warehouse column metadata. One DM element per unique SF table. |
| `scripts/post-and-readback.py` | **Phase 4 / 5c:** POST a DM or workbook spec, parse YAML response, GET back, emit ID map. Same script for both endpoints; switch with `--type datamodel|workbook`. |
| `scripts/validate-spec.py` | Pre-POST validator. Catches formula prefix mismatches, `kpi`/`pie`/`donut` mistakes, missing `folderId`, color-channel errors. |
| `scripts/build-workbook-spec.py` | **Phase 5a:** merge `card-signals.json` + `pdf-extractions.json` + `dm-ids.json` into a workbook spec. Translates Domo `chartType` → Sigma `kind`, slicers → controls, dateInfo → date-range control, columnFormats → format objects, dynamicTitle → text element. |
| `scripts/build-layout.py` | **Phase 5d:** generate layout XML from `layout.json` + readback IDs. Uses `lib/layout_xml.py` helpers. |
| `scripts/put-layout.py` | **Phase 5e:** apply layout XML to the published workbook (strips read-only fields). |
| `scripts/verify-structural-parity.py` | **Phase 6:** structural-only parity check — chart count, title match, bounding-box position match. Does NOT verify data values (source Domo system is unavailable). |
| `scripts/lib/sigma_api.py` | Shared HTTP helpers + token refresh |
| `scripts/lib/layout_xml.py` | Layout-XML helpers (`gc`, `le`, `page_xml`, `assemble`) |
| `scripts/lib/domo_chart_kinds.py` | The Domo→Sigma chart-type mapping table — single source of truth |

---

## Prerequisites

### Sigma credentials

```bash
python scripts/setup.py
```

Required env vars after setup:
- `SIGMA_BASE_URL` — e.g. `https://aws-api.sigmacomputing.com`
- `SIGMA_CLIENT_ID`
- `SIGMA_CLIENT_SECRET`

Fetch a token at the start of each phase that needs one:

```bash
eval "$(scripts/get-token.sh)"
```

Tokens live ~1 hour. Re-run when a curl returns 401.

### Inputs

Per conversion the agent needs:

1. **`dashboard.json`** — Domo page export (cards, layout, datasource refs). Path provided by the user.
2. **`dashboard.pdf`** — rendered PDF of the dashboard. Path provided by the user.
3. **Snowflake credentials in Sigma** — the connection that holds the tables the dashboard data lives in.

### Snowflake assumption

This skill assumes the data the original Domo dashboard used has already been landed in Snowflake (e.g., Domo DataFlow logic converted to Snowflake SQL views). The skill does NOT migrate data — only the dashboard surface.

---

## Phase 0a — Scan the dashboard JSON for feature gaps (MANDATORY)

Run the gap scanner against the customer's dashboard JSON *before* anything else. It inventories every chart type and every datasource so the agent can set expectations up front.

```bash
python scripts/scan-dashboard-gaps.py /path/to/dashboard.json /tmp/<name>/
# writes /tmp/<name>/gaps-report.md + /tmp/<name>/gaps.json
```

Categories emitted:
- **✅ Auto** — Domo `chartType` maps cleanly to a Sigma `kind`
- **⚠️ Hint** — maps but needs manual touch-up (e.g., heatmap heat-color is UI-only post-publish; trendline-on-KPI needs a separate small line chart)
- **❌ Unhandled** — no native Sigma equivalent (e.g., `badge_sankey`)

Share the markdown report with the customer up front. Save the JSON for downstream scripts.

---

## Phase 1a — Parse the dashboard JSON

```bash
python scripts/parse-dashboard-json.py /path/to/dashboard.json /tmp/<name>/
```

Emits:
- `card-signals.json` — one entry per card with `cardId`, `title`, `titleTemplate` (with `${DATE_RANGE}` tokens parsed), `domoChartType`, `sigmaKind`, `mappingClass` (auto/hint/gap), `datasourceIds`, `columnFormats`, `columnAliases`, `defaultDateGrain`, `dateFilter` (rolling-period or fixed), `dateGrain`, `slicers`
- `layout.json` — one entry per layout slot with `contentKey`, `cardId`, `type` (CARD/SEPARATOR/PAGE_BREAK/HEADER), `domo` (x/y/width/height), `sigmaCols` (`[c0, c1]`), `sigmaRows` (`[r0, r1]`)
- `page-controls.json` — deduplicated page-level slicers across cards, normalized to Sigma `control` shape

These are mechanical — no agent judgment.

---

## Phase 1b — Read the PDF for per-card columns and measures

The dashboard JSON tells you a card is `badge_pie` sourcing the `Projects` datasource — but **not** which column is the dimension or which is the measure. The PDF is the truth source for that.

Workflow:

1. Run the splitter to get one image per PDF page:
   ```bash
   python scripts/extract-pdf-cards.py /path/to/dashboard.pdf /tmp/<name>/pdf-pages/
   ```
2. For each page image, open it with the Read tool (Claude Code reads images natively). For each card position visible on the page, extract:
   - Visible **measure column(s)** — what the chart is measuring (e.g., "Conversion Rate", "Total Leads")
   - Visible **dimension column(s)** — what the chart is grouped by (e.g., "Marketing Source", "Created Date by Week")
   - Visible **axis labels**, **legend values**, **tooltip-style annotations**
   - **Chart shape sanity** — does this look like a bar / pie / line as the JSON's `chartType` said? If mismatched, JSON wins (it's the metadata source); but log the discrepancy.
3. Write findings to `/tmp/<name>/pdf-extractions.json`, one entry per cardId:
   ```json
   {
     "1597313722": {
       "measures": ["Conversion Rate", "Qualified"],
       "dimensions": ["Created Date"],
       "axisLabels": {"x": "Week of Created Date", "y": "Rate"},
       "legend": ["Conversion Rate", "Qualified"],
       "notes": "Two-line trend; both percentages, share y-axis"
     }
   }
   ```

See `refs/pdf-extraction-protocol.md` for the full protocol — what to look for per chart kind, how to match a PDF region to a cardId (by position in layout.json), and when to ask the user instead of guessing.

> **Why this is agent work, not script work:** PDF text extraction can pull column labels but cannot reliably tell which label is a measure vs a dimension vs an axis label. Claude's vision read gets all three right by reading the chart as a whole. Scripts only do the page split.

---

## Phase 2 — Resolve Domo datasources to Snowflake tables

```bash
python scripts/resolve-snowflake-tables.py /tmp/<name>/
```

For each unique `dataSourceId` (with its `dataSourceName` from the JSON), the script:
1. Prompts the user for the Snowflake `{database, schema, table}` path
2. Verifies the table exists via `mcp__sigma-mcp-v2__describe`
3. Records the column list for later DM/spec generation

Writes `/tmp/<name>/datasource-map.json`:

```json
{
  "95545b74-eb2b-41a6-adb8-e3967f376722": {
    "domoName": "Projects",
    "snowflake": {"database": "VAN_WEY", "schema": "MARTS", "table": "MART_PROJECTS"},
    "inodeId": "...",
    "columns": [{"name": "PROJECT_ID", "type": "varchar"}, ...]
  }
}
```

> **Display name ≠ warehouse column name.** A Domo card may reference "Created Date" while the SF column is `CREATED_DATE_TS`. The agent should map PDF-extracted column names to actual SF column names during workbook-spec build (Phase 5a). When the mapping is ambiguous, prompt the user.

---

## Phase 3 — Build the data model spec

One DM element per unique SF table referenced by the dashboard.

```bash
python scripts/build-dm-spec.py /tmp/<name>/
```

Reads `datasource-map.json` and writes `/tmp/<name>/dm-spec.json`. Each element is a `warehouse-table` element with all columns from the SF table included.

If a Domo DataFlow had logic that resulted in a denormalized table in Snowflake (typical for the Swyft pipeline — `MART_*` tables), one DM element is enough. If the user has multiple related SF tables they want joined in Sigma, edit the spec to add `relationships` before posting (see `~/sigma-skills/sigma-data-models/reference/relationships.md`).

Validate before posting:

```bash
python scripts/validate-spec.py --type datamodel /tmp/<name>/dm-spec.json
```

---

## Phase 4 — POST the data model

```bash
eval "$(scripts/get-token.sh)" && \
python scripts/post-and-readback.py --type datamodel \
  --spec /tmp/<name>/dm-spec.json \
  --out /tmp/<name>/dm-ids.json
```

Same semantics as the sibling `tableau-to-sigma` skill: POST → parse YAML → GET back → emit element ID map. The `dm-ids.json` is consumed by the workbook validator in Phase 5b.

---

## Phase 5 — Build the Sigma workbook

### 5a. Assemble the workbook spec

```bash
python scripts/build-workbook-spec.py /tmp/<name>/ \
  --title "<Workbook Title>" \
  --out /tmp/<name>/wb-spec.json
```

Inputs (all read from `/tmp/<name>/`):
- `card-signals.json` — per-card metadata from Phase 1a
- `pdf-extractions.json` — per-card columns from Phase 1b
- `dm-ids.json` — server-assigned DM element IDs from Phase 4
- `datasource-map.json` — Snowflake column metadata

What it auto-handles:
- ✅ Sigma element `kind` from Domo `chartType` (via `lib/domo_chart_kinds.py`)
- ✅ Page-level slicers → `control` elements on a hidden Data page
- ✅ Date filter (rolling period) → `date-range` control with `mode: current` + `unit: day|week|month`
- ✅ Column formats → Sigma `format` objects
- ✅ Column aliases → workbook column `name` overrides
- ✅ Dynamic title with `${DATE_RANGE}` token → `text` element with date-aware body
- ✅ Master table on hidden Data page; all visible cards source from master

What WARN lines mean:
- `'X' has Domo PoP (period-over-period) — added prev-period calc col but verify formula` — KPI cards with PoP get a `Lag()` or date-shifted calc column. Verify against the PDF's PoP value.
- `'X' has Domo heatmap — pivot-table emitted; apply heat formatting post-publish` — Sigma heat-color is UI-only.
- `'X' is badge_sankey — emitted as stacked bar placeholder` — Sigma has no sankey.
- `'X' references column 'Y' not in datasource columns — defaulting to bare ref` — likely a Beast Mode or alias mismatch; surface to the user.

### 5b. Validate

```bash
python scripts/validate-spec.py --type workbook \
  --dm-context /tmp/<name>/dm-ids.json \
  /tmp/<name>/wb-spec.json
```

### 5c. POST + readback

```bash
python scripts/post-and-readback.py --type workbook \
  --spec /tmp/<name>/wb-spec.json \
  --out /tmp/<name>/wb-ids.json
```

### 5d. Build layout XML

```bash
python scripts/build-layout.py /tmp/<name>/
```

Reads `layout.json` + `wb-ids.json`, emits `layout.xml`. SEPARATOR rows → `divider` elements; HEADER rows → `text` elements with `## ` markdown prefix; PAGE_BREAK rows → ignored (web, not print).

### 5e. PUT layout

```bash
python scripts/put-layout.py \
  --workbook <workbookId> \
  --layout /tmp/<name>/layout.xml
```

---

## Phase 6 — Verify structural parity (MANDATORY)

> **No numerical parity is possible** — the source Domo system is gone. This phase verifies *structural* parity only: same number of cards rendered, same titles, same positions, same chart kinds.

```bash
python scripts/verify-structural-parity.py /tmp/<name>/ --workbook <id>
```

Checks (per page):
- ✓ Sigma workbook element count matches Domo card count (excluding hidden master)
- ✓ Each Domo card title appears in a Sigma element title (or text element body, for dynamic-title cards)
- ✓ Each Domo card position (sigmaCols/sigmaRows from layout.json) matches the published Sigma element position (within ±1 col tolerance for grid snapping)
- ✓ Each Domo `chartType` maps to the expected Sigma `kind` on the published element

Output: per-card `PASS` or `MISMATCH`. Exit 0 on full pass, 1 on any mismatch.

For numerical sanity, the agent should screenshot the published Sigma workbook and visually compare to the source PDF — call out any obvious magnitude mismatches (e.g., Sigma shows 200 leads vs PDF showed 2,000) and discuss with the user. Common causes: wrong SF column mapped, wrong aggregation, missed filter from page slicer.

---

## Troubleshooting

| Error / symptom | Cause | Fix |
|---|---|---|
| Gap scanner flags 30%+ of chart types as `unhandled` | Customer has heavy use of badge_sankey / badge_funnel / custom Domo apps | Discuss with customer; some charts may need manual rebuild in Sigma |
| PDF read can't tell measure from dimension on a stacked bar | Stacked bars often have legend = breakdown dim, x-axis = primary dim, value-axis = measure. Read the legend label first | When ambiguous, ask the user |
| Card title in PDF disagrees with `cards[].title` from JSON | Domo's `dynamicTitle` template overrides static title at render time | Trust the `titleTemplate` from `card-signals.json`; the static `title` is often stale |
| Two cards share the same `cardId` in different layout positions | Domo allows the same card embedded multiple times on a page | Build one workbook element per layout-position, all sourcing the same DM columns |
| `Expecting UUID at 0.folderId but instead got: undefined` | `folderId` missing from spec | Find with `GET /v2/files?typeFilters=workbook` → `parentId` |
| `Invalid kind: 'kpi' \| 'pie' \| 'donut'` | Used Sigma example library naming | Must be `kpi-chart` / `pie-chart` / `donut-chart`; the validator catches this |
| `dependency not found: formula reference 'projects/created date'` | Slash or space mismatch in column `name` | Use the actual SF column name (UPPERCASE, no spaces) in the formula prefix |
| Page slicer column doesn't exist on the SF table | Beast Mode column the slicer referenced | Surface to user; either add a Beast Mode-equivalent calc column to the DM, or drop the control |
| Sigma chart renders but numbers are off by 10x | Wrong aggregation — Domo defaults to SUM, Sigma might be COUNT | Recheck the chart's measure aggregation; pull from PDF if visible |
| `429` from Sigma API on rapid POSTs | Rate limit | Wait and retry; consider serializing Phase 5c if doing multiple workbooks |
| Layout PUT rejected, some elements not visible | `elementId=""` in layout XML | Script aborts on this; check `wb-ids.json` for nil IDs |

---

## Why this skill exists

Most Domo→Sigma migrations happen *after* the customer has decided to leave Domo. By then, the most you typically have is a JSON export and screenshots. This skill is forensic by design — it does the most it can with what's preserved, and explicitly punts on what's not.

If your Domo org is still live and you have API access, you can extend Phase 1b to fetch card definitions directly (`/api/content/v1/cards/{id}/definition`) instead of relying on PDF read. That path is not in MVP scope.
