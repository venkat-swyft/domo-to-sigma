# domo-to-sigma

Convert a Domo dashboard into a Sigma workbook by reconstructing it from a Domo dashboard JSON export plus a rendered PDF of the live dashboard. Forensic-reconstruction first — works when the source Domo org is no longer live.

Modeled on [`twells89/sigma-skills-staging/tableau-to-sigma`](https://github.com/twells89/sigma-skills-staging/tree/main/tableau-to-sigma). Sigma-side mechanics (`validate-spec`, `post-and-readback`, layout XML, `put-layout`) follow the same patterns; the Domo side is new.

## What it does

| Input | Output |
|---|---|
| `dashboard.json` (Domo page export) | Card list, layout grid, chart-type mapping, datasources, page-level controls, date filters, formats |
| `dashboard.pdf` (rendered dashboard) | Per-card visible columns, measures, dimension values, axis labels (extracted by the agent via vision) |
| Live Snowflake (`mcp__sigma-mcp-v2`) | Real warehouse column names, DM element creation, parity sanity checks |

| Result |
|---|
| One Sigma data model + one Sigma workbook with cards in the right positions, right kinds, right titles, right controls, right formats |

Numerical parity against the original Domo dashboard is **not** verified — by definition the source Domo system is gone. Sigma reflects live Snowflake data. The skill verifies **structural parity** (chart count / titles / layout positions / kinds) only.

## Scope

- ✅ Card→chart-kind mapping (15 Domo `badge_*` types, see `refs/chart-type-mapping.md`)
- ✅ 60-col Domo grid → 24-col Sigma grid layout
- ✅ Page-level slicers → Sigma `control` elements
- ✅ Rolling-period date filters → Sigma `date-range` controls
- ✅ Column formats (percent / currency / abbreviation / precision)
- ✅ Dynamic title templates with date tokens
- ⚠ Beast Mode formulas — *not* in scope for MVP (Domo card definitions aren't in the dashboard JSON; require API access we don't have)
- ⚠ Heatmap heat-color formatting — pivot-table built, heat formatting applied UI-only
- ❌ Sankey diagrams — Sigma has no native sankey

## Prerequisites

- Sigma OAuth credentials (`SIGMA_CLIENT_ID`, `SIGMA_CLIENT_SECRET`, `SIGMA_BASE_URL`)
- Python 3.10+
- Domo dashboard JSON file + rendered PDF
- Snowflake tables already populated with the data the dashboard used (Domo DataFlow logic converted to Snowflake SQL)

## Quick start

```bash
# One-time
python scripts/setup.py
eval "$(scripts/get-token.sh)"

# Per conversion (interactive)
python scripts/scan-dashboard-gaps.py /path/to/dashboard.json /tmp/<name>/
python scripts/parse-dashboard-json.py /path/to/dashboard.json /tmp/<name>/
# Agent reads the PDF, writes /tmp/<name>/pdf-extractions.json
# Agent resolves datasource→Snowflake table mappings interactively
python scripts/build-dm-spec.py /tmp/<name>/
python scripts/post-and-readback.py --type datamodel --spec /tmp/<name>/dm-spec.json --out /tmp/<name>/dm-ids.json
python scripts/build-workbook-spec.py /tmp/<name>/
python scripts/validate-spec.py --type workbook --dm-context /tmp/<name>/dm-ids.json /tmp/<name>/wb-spec.json
python scripts/post-and-readback.py --type workbook --spec /tmp/<name>/wb-spec.json --out /tmp/<name>/wb-ids.json
python scripts/build-layout.py /tmp/<name>/
python scripts/put-layout.py --workbook <id> --layout /tmp/<name>/layout.xml
python scripts/verify-structural-parity.py /tmp/<name>/
```

Full phase-by-phase recipe is in [`SKILL.md`](SKILL.md).

## Status

Early. Phase 1a (JSON parse) and Phase 0a (gap scan) work end-to-end on one real dashboard (39 cards, 15 chart types). Phases 1b, 2–6 are scaffolded but not yet implemented.
