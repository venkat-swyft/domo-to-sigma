# Domo `chartType` → Sigma `kind` mapping

This file is the human-readable reference. The machine-readable single source of truth is `scripts/lib/domo_chart_kinds.py`. Edit there and keep this file in sync.

## Classification levels

- **✅ auto** — straight 1:1 mapping; parser emits the Sigma kind directly.
- **⚠ hint** — maps to a Sigma kind but with caveats (manual post-publish step, fidelity loss, requires Phase 1b PDF input to disambiguate).
- **❌ gap** — no native Sigma equivalent; agent must surface this to the user and either drop the card or rebuild in Sigma UI.

## Full table

| Domo `chartType` | Sigma `kind` | Class | Notes |
|---|---|---|---|
| `badge_singlevalue` | `kpi-chart` | ✅ | Big-number KPI. |
| `badge_pop_multi_value` | `kpi-chart` | ✅ | KPI with period-over-period delta. Sigma KPI doesn't natively show PoP — emit a calc column `(current - prev) / prev` and bind both to the chart. |
| `badge_pop_trendline` | `kpi-chart` | ⚠ | KPI with embedded sparkline. Sigma KPI has no sparkline. Build a container with the KPI on top + a small `line-chart` below (3-4 rows tall). |
| `badge_two_trendline` | `line-chart` | ✅ | Two-series line. Use `combo-chart` if the two measures have very different scales (one big absolute, one small percent). |
| `badge_pop_vert_multibar` | `bar-chart` | ✅ | Vertical multi-bar where "multi" = period-over-period bars side-by-side. Treat the period (current vs prior) as a breakdown dimension. |
| `badge_vert_stackedbar` | `bar-chart` | ✅ | Set `stacked: true`. |
| `badge_pie` | `pie-chart` | ✅ | |
| `badge_donut` | `donut-chart` | ✅ | Domo's donut variant. Set `holeValue.id` distinct from `value.id` or Sigma silently drops the element. |
| `badge_basic_table` | `table` | ✅ | Flat row-by-row table. Use `pivot-table` if the table has grouping headers visible in the PDF. |
| `badge_heatmap` | `pivot-table` | ⚠ | Pivot with measure values; heat-color formatting is Sigma UI-only. After publish, user opens the element editor and applies a color scale. |
| `badge_map_us_county` | `region-map` | ✅ | Sigma `regionType: "county"`. |
| `badge_map_us_state` | `region-map` | ✅ | Sigma `regionType: "state"`. |
| `badge_map` | `region-map` | ⚠ | Generic map — confirm geo level from the PDF. Could be country, state, county, or ZIP. |
| `badge_xybubble` | `scatter-chart` | ✅ | Use `sizeBy` for bubble size. |
| `badge_scatter` | `scatter-chart` | ✅ | |
| `badge_sankey` | — | ❌ | Sigma has no native sankey. Options: (a) stacked bar showing same-source-to-target ratios; (b) drop the card and recreate in Sigma UI post-publish as a custom chart; (c) skip entirely. Default: emit a `bar-chart` placeholder with a note. |
| `badge_funnel` | — | ❌ | Same situation as sankey. Default: emit a sorted `bar-chart` placeholder. |
| `badge_checkbox_selector` | `control` | ✅ | `controlType: "list"`, `mode: "include"` for IN operators, `mode: "exclude"` for NOT_IN. |
| `badge_segmented` | `control` | ✅ | `controlType: "segmented"` (radio buttons). |
| `Text` | `text` | ✅ | Markdown body. Domo stores HTML in `markup`; we parse it down to `## heading` + paragraphs. |
| `kpiText` | `text` | ✅ | Section-header text card; same as `Text`. |

## When the JSON's `chartType` and the PDF disagree

The Domo `chartType` field is the **metadata source of truth** — the JSON is what the dashboard *was configured as*. The PDF is *what it rendered*. They almost always agree, but if they don't:

- **Trust the JSON.** The PDF rendering can be affected by zoom, data sparseness (a "stacked bar" with one category renders as a single bar), or a partial export.
- **Log the discrepancy.** Note it in `pdf-extractions.json[cardId].notes` so the agent surfaces it during Phase 5a.
- **Re-read the PDF region** if the chart kind looks wildly different (e.g., JSON says `badge_pie` but PDF shows a horizontal bar chart). That's the symptom of a card being replaced in Domo without the JSON being re-exported.

## Domo-specific chart concepts that don't map cleanly

| Concept | Sigma equivalent |
|---|---|
| Goal lines (target value bars) | `referenceMarks` on the chart element |
| Trend arrows ("vs last period" up/down) | Calc column showing % change + format with arrow Unicode chars in display |
| Conditional formatting on tables | Sigma table column formatting w/ `colorRules` (UI-only for some types) |
| Drill paths (clicking a card opens another) | Sigma element-to-element links via element parameter — post-publish UI wiring |
| Subscriptions (email export) | Sigma scheduled exports — set up post-publish |
| Story panels | Sigma `text` elements + dashboard layout |

These are all post-publish manual steps. The skill does NOT attempt to recreate them automatically.
