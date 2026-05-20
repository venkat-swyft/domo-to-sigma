# PDF extraction protocol

This file is the runbook for the agent's PDF-read phase. It applies in both modes:
- **PDF-only mode** — the agent extracts *everything* from the PDF (layout, kinds, titles, columns/measures, controls).
- **JSON+PDF mode** — the agent extracts only the per-card column/measure details that the JSON doesn't carry (Phase 1b).

## Why the agent does this, not a script

Programmatic PDF text extraction (`pdfminer`, `pdfplumber`, OCR) returns text fragments without spatial structure. It can pull "Total Leads", "742", "Marketing Source", "Conversion Rate" off a page — but it can't tell you which of those is a card title, which is a measure label, which is a dimension label, and which is a tooltip annotation. Claude's vision read gets all of those right by seeing the chart as a whole.

Scripts only do the **page split** (extracting PDF pages as PNG images). The reading is yours.

## Tooling — page split

The skill ships `scripts/extract-pdf-cards.py`. On most platforms it uses `pdftoppm` under the hood:

```bash
python scripts/extract-pdf-cards.py /path/to/dashboard.pdf /tmp/<name>/pdf-pages/
```

If `pdftoppm` isn't installed:
- **macOS**: `brew install poppler`
- **Debian/Ubuntu**: `apt install poppler-utils`
- **Windows**: install Poppler for Windows and add to PATH, or use WSL

Fallback when `pdftoppm` is unavailable: ask the user to export the PDF as one PNG per page from any PDF reader, drop them in `/tmp/<name>/pdf-pages/`, named `page-001.png`, `page-002.png`, etc.

## PDF-only mode — full extraction protocol

For each PDF page, open the image with the Read tool and produce structured findings.

### Step 1 — Inventory pass (one pass over all pages)

Build `/tmp/<name>/page-inventory.json`:

```json
[
  {
    "pageNumber": 1,
    "approximateCardCount": 11,
    "topElement": "Page title 'Marketing & Intake' + date range filter (rolling 90 days)",
    "leftToRightTopRow": ["Total Leads", "Qualified Leads", "Sign Ups", "Referred Out", "Withdrawn"],
    "rowBreakdown": "5 KPIs top, 5 rate KPIs second row, separator, 4 stat KPIs left side + 2 tall charts right",
    "hasFilterShelf": true,
    "filterColumnsVisible": ["Marketing Source", "Case Source"]
  }
]
```

This pass orients you. Don't try to extract every detail yet.

### Step 2 — Per-card extraction (per page)

For each card visible on a page, produce a record in `/tmp/<name>/card-signals.json`:

```json
{
  "cards": [
    {
      "cardId": "p1-c01",                          // synthetic ID: page-cardposition
      "page": 1,
      "position": {"row": 1, "col": 1, "rowSpan": 1, "colSpan": 1, "of": [5, 1]},
      "title": "Total Leads | Apr-Jun 2025",
      "domoChartType": "badge_pop_multi_value",    // your best guess from visual evidence
      "sigmaKind": "kpi-chart",                    // via refs/chart-type-mapping.md
      "measures": ["Total Leads"],                 // what the chart MEASURES
      "dimensions": [],                            // what it's GROUPED BY (empty for KPIs)
      "axisLabels": {},                            // {x: ..., y: ...} for charts; empty for KPIs
      "legend": [],                                // list of legend values for multi-series
      "valueDisplayed": "742",                     // the big number for KPIs (cross-reference later)
      "popDisplayed": "+12% vs prior period",      // period-over-period text, if shown
      "format": "integer",                         // "integer" / "percent" / "currency" / "decimal-2"
      "notes": "Small green up-arrow next to PoP. No data label on bars."
    }
  ]
}
```

**Position grid:** the simplest approach is a per-page row/col grid. Look at the page and count the rows of cards and the columns within each row.

- `position.row` = which row top-to-bottom (1-indexed)
- `position.col` = which column left-to-right within that row (1-indexed)
- `position.rowSpan` / `colSpan` = if a card spans multiple rows or columns
- `position.of` = `[totalColsInRow, totalRowsOnPage]` so you can compute proportional widths later

The build-workbook-spec script translates these row/col positions into Sigma 24-col grid coordinates using the proportions implied by `of`.

### Step 3 — Page-level chrome

For each page, separately extract:

```json
{
  "pageChrome": {
    "page": 1,
    "title": "Marketing & Intake",                          // the dashboard's name
    "dateRangeShown": "Apr 1, 2025 - Jun 30, 2025",         // visible in the PDF chrome (if any)
    "dateRangeInferred": "rolling 90 days ending today",    // best-effort interpretation
    "filterShelf": [
      {"column": "Marketing Source", "displayType": "multi-select", "valuesSelected": ["Google Ads", "Facebook"]},
      {"column": "Case Source",      "displayType": "multi-select", "valuesSelected": []}
    ],
    "drillIndicators": []                                   // text like "Click for details" or breadcrumb trails
  }
}
```

The filter shelf in PDF-only mode is **best-effort**. Often the PDF only shows filter labels with no selected values. Document what you see; flag uncertainty in `notes`.

### Step 4 — Cross-page consistency check

After all pages are read, scan the assembled `card-signals.json` for inconsistencies:

- Same metric appearing on multiple pages? Verify the values agree (or note if one is a different time window).
- Two cards with the same `title` but different measures? Likely a copy-paste error or a legitimate "by source A" vs "by source B" — confirm visually.
- A filter shelf column that doesn't appear on any datasource you'll map in Phase 2? Surface to user.

### Step 5 — Sanity discussion with user

Before Phase 2 (Snowflake table resolution), summarize for the user:

> "PDF read complete. Inventory:
> - **42 cards** across **3 pages**
> - **18 KPI big-numbers**, **8 trend lines**, **6 bar charts**, **4 tables**, **3 pie/donuts**, **2 maps**, **1 heatmap**
> - **2 datasource candidates** referenced visually: `Projects` (most KPIs) and `Lead Docket` (lead-focused cards)
> - **Filter shelf** has 5 columns: Marketing Source, Case Source, Status, Case Categorization, Initial Assessment
> - **Date range**: rolling 90 days on most cards, full-year on 3 cards
>
> Anything I'm missing or misread?"

User confirms or corrects. You update the JSON files. Then proceed to Phase 2.

## JSON+PDF mode — targeted extraction (Phase 1b)

When the JSON has already been parsed in Phase 1a, you have:
- All cards, kinds, layout positions, titles, formats, controls, date filters — done
- You DON'T have: which column is the measure, which is the dimension, what aggregation

For each card in `card-signals.json` (from Phase 1a), open the PDF page that contains it (use the layout position to find the page) and extract only:

```json
{
  "1597313722": {
    "measures": ["Conversion Rate", "Qualified"],
    "dimensions": ["Created Date"],
    "axisLabels": {"x": "Week", "y": "Rate"},
    "legend": ["Conversion Rate", "Qualified"],
    "notes": "Two-line trend. Both lines share the same y-axis (percentages). Created Date binned to week."
  }
}
```

Save to `/tmp/<name>/pdf-extractions.json` keyed by `cardId`. The build-workbook-spec script merges this with `card-signals.json`.

## How to identify chart kind from the rendered chart

| Visual feature | Likely chart kind |
|---|---|
| Single huge number, possibly with a small ↑/↓ delta | `kpi-chart` (badge_pop_multi_value or badge_singlevalue) |
| Single number + a tiny line behind it | `kpi-chart` with sparkline (badge_pop_trendline) |
| Big number split into two side-by-side numbers | `kpi-chart` (badge_pop_multi_value) — current and prior period |
| Vertical bars, single series | `bar-chart` |
| Vertical bars, side-by-side colored | `bar-chart` w/ breakdown dimension |
| Vertical bars stacked | `bar-chart` w/ `stacked: true` |
| Horizontal bars | `bar-chart` w/ `orientation: "horizontal"` (UI-only post-publish) |
| One line | `line-chart` single-series |
| Two or more lines, similar scale | `line-chart` multi-series |
| Bar + line overlaid | `combo-chart` |
| Circle divided into slices | `pie-chart` |
| Circle with hole | `donut-chart` |
| Grid of cells with color intensity | `pivot-table` w/ heat formatting (badge_heatmap) — Sigma heat format applied UI-only |
| US map with regions colored | `region-map` w/ regionType state or county |
| Map with dots/circles | `point-map` |
| Cloud of dots/circles on x,y axes | `scatter-chart` |
| Cloud of sized bubbles | `scatter-chart` w/ size encoding |
| Flow lines from N sources to M targets | `badge_sankey` ❌ no Sigma equivalent — emit `bar-chart` placeholder |
| Diminishing funnel shape | `badge_funnel` ❌ — emit sorted `bar-chart` placeholder |
| Headers row + data rows | `table` |
| Headers row + sub-grouped rows | `pivot-table` |

## How to identify measure vs dimension on a chart

| Hint | Conclusion |
|---|---|
| The label is on the **y-axis** of a vertical bar/line chart | Probably the **measure** |
| The label is on the **x-axis** of a vertical bar/line chart | Probably the **dimension** |
| The label is in the **legend** with multiple values | The **breakdown dimension** (or, for multi-series, the *measures themselves* — see below) |
| The label is on a **slice** of a pie chart | The **dimension value** |
| The legend says "Conversion Rate" and "Qualified" on a two-line chart | Both are **measures** (multi-measure pattern — color encodes which measure) |
| The label appears in a column header of a table | A **column** — could be either; check if the values are numeric (measure) or categorical (dimension) |
| The label has a "Sum of" / "Avg of" / "Count of" prefix | The **measure** (with aggregation hint) |
| The label has a **trailing**/leading time fragment ("Week of", "Q1 2024") | The **date dimension**, binned |

When ambiguous, ask the user. Better to ask than to fabricate a column mapping.

## When PDF text is not selectable (image-only PDFs)

Some Domo PDF exports are flat images, not text-layered PDFs. Vision read still works (Claude reads images), but:
- Numbers can blur at low DPI — flag values that look indistinct
- Long labels may be truncated with "..." — work with the prefix; ask the user for the full label
- Small-font axis tick labels may be unreadable below ~10pt — note as `axisLabels: {"x": "unreadable"}` and flag

Ask the user to re-export the PDF at higher DPI (Domo allows 150/200/300 DPI exports) if vision read is failing on many cards.

## Common pitfalls

| Pitfall | Avoidance |
|---|---|
| Conflating multiple cards on one page into one extraction | Always identify cards by visual boundary (border, background color change, whitespace gap) |
| Reading the previous-period value as the current value | PoP cards show two numbers side-by-side — the LARGER text or LEFT number is current; verify from layout direction |
| Treating a chart title as a measure label | Card titles are usually larger font, often at the top — measure labels are smaller, near the axis or value |
| Mis-counting cards per row when a card spans multiple columns | A wider card with no neighbor to its right is a *full-row* card — its `colSpan` equals the row's total cols |
| Recording axis tick labels as "dimension values" | The dimension is the *column*; the tick labels are the *values within that column*. Record the column name, not the value list. |
| Forgetting to record formats | If the value shows "$1,234" the format is `currency`; "12.5%" → `percent`; "1.2K" → `integer` with abbreviation |
