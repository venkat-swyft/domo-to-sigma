# Domo 60-col → Sigma 24-col grid conversion

Domo uses a **60-column** grid; Sigma uses a **24-column** grid. Both are top-left origin with row-major coordinates.

## Column arithmetic

```python
c0 = round(x / 60 * 24) + 1                  # Sigma cols are 1-indexed, span notation is [c0, c1)
c1 = round((x + width) / 60 * 24) + 1
```

Sigma layout XML uses span notation `gridColumn="c0 / c1"` where `c1` is **exclusive** (e.g., `1 / 7` means cols 1–6, i.e., 6 cols wide). Same as CSS grid.

### Common conversions

| Domo `x` / `width` | Domo cols (of 60) | Sigma `c0 / c1` | Sigma cols wide |
|---|---|---|---|
| `x=0, w=60` | 0–60 (full) | `1 / 25` | 24 |
| `x=0, w=30` | 0–30 (half) | `1 / 13` | 12 |
| `x=30, w=30` | 30–60 (half) | `13 / 25` | 12 |
| `x=0, w=20` | 0–20 (1/3) | `1 / 9` | 8 |
| `x=20, w=20` | 20–40 (1/3) | `9 / 17` | 8 |
| `x=40, w=20` | 40–60 (1/3) | `17 / 25` | 8 |
| `x=0, w=15` | 0–15 (1/4) | `1 / 7` | 6 |
| `x=0, w=12` | 0–12 (1/5) | `1 / 6` | 5 |
| `x=12, w=12` | 12–24 (1/5) | `6 / 11` | 5 |
| `x=24, w=12` | 24–36 (1/5) | `11 / 15` | 4 |
| `x=36, w=12` | 36–48 (1/5) | `15 / 20` | 5 |
| `x=48, w=12` | 48–60 (1/5) | `20 / 25` | 5 |

### Why a row of 5 equal cards becomes 5+5+4+5+5

24 doesn't divide evenly by 5. The arithmetic snaps each card to the nearest whole column, producing one 4-col card among the four 5-col cards. This is visually fine but the asymmetry is real. If the customer's eye notices it, you can manually balance with `4 / 9` (5 wide), `9 / 14` (5 wide), `14 / 19` (5 wide), `19 / 24` (5 wide), `24 / 25` (1 wide spacer) — but this is fiddly and rarely necessary.

## Row arithmetic

Domo uses **integer row units** with no fixed scale — each `y` and `height` is just a number that establishes ordering and proportions. Sigma rows are auto-sized to content (`gridTemplateRows="auto"`).

**Default: preserve Domo `y` and `height` as Sigma `r0` and `r1`.**

```python
r0 = domo_y + 1
r1 = domo_y + domo_height + 1
```

This works because Sigma's auto-sized rows respect the requested row span: if you say `gridRow="9 / 23"` (14 rows tall), Sigma will allocate roughly that proportion of the canvas height.

### Empirical row-height ranges in Domo

From inspecting real dashboards:

| Domo `height` | Domo card type (typical) |
|---|---|
| 3 | SEPARATOR (thin divider) |
| 5 | HEADER (section heading bar) |
| 8 | Top hero text block / page title row |
| 9 | KPI tile (one-row stat card) |
| 11 | Half-height secondary KPI row |
| 14 | Medium chart (bar chart with N categories) |
| 22–23 | Tall hero chart (trendline, large pie, table) |

When you convert to Sigma:
- KPIs at `height=9` are fine at Sigma `r0/r1` of 9 rows
- Charts at `height=14` and above need ≥12 Sigma rows to render the chart and its axis labels (Sigma's default chart elements compress badly under 10 rows)
- If a Domo card is `height=9` but is a chart (not a KPI), bump to ≥12 in Sigma — the original Domo card was probably cramped too

## Layout edge cases

### Separators

Domo `SEPARATOR` cards are full-width thin horizontal-rule elements between sections. In Sigma, emit a `divider` element with the same row span:

```xml
<LayoutElement elementId="div-1" gridColumn="1 / 25" gridRow="34 / 37"/>
```

### Headers

Domo `HEADER` rows are full-width banner-style section titles. The Domo JSON doesn't always carry the header text — sometimes it's in a sibling Text card directly above. In Sigma, emit a `text` element with markdown `## Heading` and the same span.

### Page breaks

Domo `PAGE_BREAK` rows exist for PDF export pagination. Sigma is web-only, so **ignore PAGE_BREAK** entirely — drop the layout slot. Subsequent cards collapse upward into the row the page break was occupying.

### Spacers

Domo `SPACER` rows are intentional empty space. In Sigma, leave the grid range empty — don't emit anything. The subsequent card's `r0` will start where the spacer ended, and Sigma will leave the space blank.

### Overflowing cards

A Domo card with `x + width > 60` is malformed but does occur in old dashboards. Clamp:
```python
domo_width = min(domo_width, 60 - domo_x)
```

A Domo card with `height = 0` is a zero-height placeholder. Skip it.

## Multi-page dashboards

If the source dashboard has multiple pages (Domo's "Page Tabs"), each tab is a separate top-level `pageLayoutV4` in the export. Today this skill processes ONE page per invocation — re-run for each tab.

The Sigma workbook can hold multiple pages; the agent stitches them together in Phase 5d by emitting one `<Page>` block per source dashboard tab, all inside a single top-level layout XML.

## When the Sigma rendering looks wrong after PUT

Common causes and fixes:

| Symptom | Cause | Fix |
|---|---|---|
| All elements stacked in a vertical strip | Layout XML wasn't applied | Re-run `put-layout.py` |
| Some elements correct, others overlapping | Multiple Sigma elements with the same `gridColumn` and `gridRow` | Check `layout.json` for two cards with identical `sigmaCols`+`sigmaRows`; one of them probably has `x=0, w=0` or similar zero-area bug — drop it |
| KPI names truncated inside container | Inner `gridRow` smaller than container's outer span (Sigma's `gridTemplateRows="auto"` does NOT expand) | Match the inner KPI row span to the container's outer row span |
| Empty containers visible | Used `<LayoutElement>` for an element that wraps children | Use `<GridContainer>` from `lib/layout_xml.py` `gc()` helper |
| Cards in wrong order | Layout XML emitted in a different order than the visual layout suggests | Sigma respects the `gridRow` start values — if two elements have the same `r0`, ties break on `c0`. Visual order ≠ XML order. Trust the grid coords, not the file ordering. |
