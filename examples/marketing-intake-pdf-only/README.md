# Example — PDF-only mode on the "Marketing & Intake" Domo dashboard

This is a concrete example of what the agent produces in **PDF-only mode** (Phase 1b without a JSON, per `refs/pdf-extraction-protocol.md`).

## Source

The skill was given:
- `Sample-DashboardPDF.pdf` — a 14-page Scribe how-to guide that captures screenshots of the "Marketing & Intake" Domo dashboard as the user clicks through it. The PDF is *not* a direct dashboard export — it's a walkthrough doc.

The user pre-converted the PDF to PNGs (Word "Open PDF" → embedded page images, then exported) and placed them in a folder. Could equally have been done with Win+Shift+S screenshots, `pdftoppm` if Poppler is installed, or any other PDF-to-PNG path.

## What's in this folder

| File | Purpose |
|---|---|
| `page-inventory.json` | Step 1 of the PDF-only protocol — pages walked, sections found, page chrome (filter shelf, dashboard title, save-filters button). |
| `card-signals.json` | Step 2 — per-card extraction. 25 cards across 5 sections with title, chart type, measures, dimensions, formats, sample values from the rendered output. |

## How it was produced

The agent (Claude) read each PNG with the `Read` tool, identified card boundaries, mapped chart shapes to Domo `badge_*` types using `refs/chart-type-mapping.md`, and recorded measures/dimensions visible in axis labels and legends.

## Sanity check against JSON-mode parse

The same dashboard has a JSON export (`Sample-DashboardJSON.json` — 39 cards) and the skill's `parse-dashboard-json.py` Phase 1a parser was run on it during initial design. Key reconciliation points:

| Aspect | JSON parse | PDF read | Notes |
|---|---|---|---|
| Total cards | 39 | 25 | PDF underestimates by ~36%. Misses: Text cards (section headers stored as Domo `type:"Text"` markdown blocks), hidden/duplicate cards, cards on scrolled-off regions the Scribe guide didn't capture. |
| Distinct chart kinds | 15 | 9 | PDF caught the visible variety; missed `badge_pop_trendline`, `badge_checkbox_selector` (filter shelf rendered differently in PDF), `badge_singlevalue` distinct from `badge_pop_multi_value`. |
| Page-level slicers | 6 from JSON | 10 from PDF chrome | PDF caught MORE slicer columns because the JSON's `slicers[]` field only carries those a card has explicitly bound; the dashboard's actual filter shelf shows all available columns. PDF wins here. |
| Datasource count | 2 (Projects, Lead Docket) | 2 (same names inferred) | Tie — both correctly identified the same two datasources. |
| Sankey detection | 1 (`badge_sankey`) | 1 (visual sankey on page 11) | Tie — both flagged the unhandled card. |

## Takeaway

**PDF-only mode loses ~30-40% of cards** (mostly text/section headers and hidden ones) but **catches the visible analytical content** and is often *better* at identifying the page-level filter shelf than the JSON.

When both inputs are available (JSON+PDF mode), the JSON gives the authoritative card list and layout, and the PDF supplies the per-card column/measure detail. They're complementary.

For migrations where the source Domo is gone and only a Scribe-style walkthrough PDF or screenshot collection survives, PDF-only mode is enough to scaffold a Sigma workbook that the user then refines (add missed cards manually, wire up the sankey alternative, etc.).
