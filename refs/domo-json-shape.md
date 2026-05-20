# Domo dashboard JSON — what the parser reads

The Domo dashboard JSON is what Domo's "Export Page" feature emits, or what `GET /api/content/v2/pages/{id}` returns. This file documents the fields we read and what we ignore.

## Top-level shape

```json
{
  "id": "794859642",
  "page": { "pageId": ..., "title": ..., "pageName": ..., "owners": [...] },
  "type": "page",
  "title": "Marketing & Intake",
  "sizes": [ {"id": "<cardId>", "size": "" } ],
  "cards": [ ... ],                  // <-- the chart instances
  "collections": [],
  "pageLayoutV4": { ... },           // <-- the layout grid
  "pageAnalyzerSettings": { ... }
}
```

### Fields we READ

- `page.title` / `title` — workbook name
- `page.pageId` — used as a stable identifier
- `cards[]` — every chart on the page (see "Card shape" below)
- `pageLayoutV4.standard.template` — layout for desktop/full size
- `pageLayoutV4.content` — links contentKey to cardId

### Fields we IGNORE

- `sizes[]` — per-card size override; the actual layout is in `pageLayoutV4`
- `collections[]` — Domo's card collection grouping; not relevant to Sigma
- `pageAnalyzerSettings` — Domo-internal
- `pageLayoutV4.compact` — mobile layout; Sigma handles responsive automatically
- `pageLayoutV4.printFriendly` / `hasPageBreaks` — print export config; web-only in Sigma

## Card shape

```json
{
  "id": 1597313722,
  "urn": "1597313722",
  "type": "kpi",                     // <-- "kpi" for chart cards, "Text" for text cards
  "title": "Qualified Leads Trend |",
  "metadata": {
    "chartType": "badge_two_trendline",
    "chartVersion": "12",
    "columnAliases": "{}",           // JSON-encoded string
    "columnFormats": "{...}",        // JSON-encoded string
    "defaultDateGrain": "Week",
    "dynamicTitle": "{...}",         // JSON-encoded structured title
    "SummaryNumberFormat": "{...}",
    "allTime": "{...}",              // date-filter scope
    "calendar": "default"
  },
  "metadataOverrides": {
    "components": [
      { "component": "main", "chartType": "...", "overrides": { ... } }
    ]
  },
  "datasources": [
    { "dataSourceId": "...", "dataSourceName": "Projects", "dataType": "DataFlow" }
  ],
  "slicers": [
    { "type": "string", "column": "...", "operator": "NOT_IN", "values": [...] }
  ],
  "dateInfo": {
    "dateRange": {
      "columnName": "Created Date",
      "dateRangeFilter": {
        "dateTimeRange": {
          "dateTimeRangeType": "ROLLING_PERIOD",
          "interval": "DAY",
          "count": 90
        }
      }
    },
    "dateGrain": { "dateTimeElement": "WEEK", "columnName": "Created Date" }
  },
  "drillPath": { "paths": { ... } },
  "created": 1742596768,
  "ownerId": 455559036,
  "active": true,
  "access": true
}
```

### Card metadata fields we PARSE

| Field | Type | What we do with it |
|---|---|---|
| `id` | int | `cardId` — primary key |
| `title` | string | Static title (often stale; prefer `titleTemplate`) |
| `type` | string | `"kpi"` for charts, `"Text"` for text/markdown blocks |
| `metadata.chartType` | string | Mapped to Sigma `kind` via `lib/domo_chart_kinds.py` |
| `metadata.columnAliases` | JSON string | Parsed into `{originalCol: aliasName}` map |
| `metadata.columnFormats` | JSON string | Parsed into `{col: formatObj}` → Sigma format objects |
| `metadata.defaultDateGrain` | string | "Week"/"Month"/"Quarter"/"Year" — chart-default date bucketing |
| `metadata.dynamicTitle` | JSON string | Parsed: `{text: [{text, type}]}` where `type` is `"TEXT"` or `"DATE_RANGE_FILTER_DATE_TIME_RANGE"`. Emit as template like `"Title \| ${DATE_RANGE}"`. |
| `metadata.markup` / `textHtml` | string (Text cards only) | Parsed HTML → markdown body for Sigma `text` element |
| `datasources[].dataSourceId` | UUID | Mapped to Snowflake table in Phase 2 |
| `datasources[].dataSourceName` | string | Human-readable name shown during Phase 2 prompt |
| `slicers[]` | array | Page-level filter shelf — dedupe across cards, emit as Sigma controls |
| `dateInfo.dateRange.columnName` | string | Date-filter column name (needs SF column name mapping) |
| `dateInfo.dateRange.dateRangeFilter.dateTimeRange` | obj | `{dateTimeRangeType, interval, count}` — `ROLLING_PERIOD` → Sigma date-range mode `"current"` + unit |
| `dateInfo.dateGrain.dateTimeElement` | string | Default grain for the chart's date axis (DateTrunc level) |

### Card metadata fields we IGNORE

| Field | Why |
|---|---|
| `metadata.chartVersion` | Domo internal |
| `metadata.historyId` | Domo internal |
| `metadata.currentLabel` / `currentMethod` | Domo display state |
| `metadata.SummaryNumberFormat` | Card-summary number; Sigma KPI uses element-level format |
| `metadataOverrides` | Chart-style overrides (legend position, gridlines) — UI-only in Sigma; agent applies post-publish if needed |
| `drillPath` | Drill-down config — manual post-publish wiring |
| `subscriptions`, `owners`, `certification` | Permissions/governance metadata |
| `created`, `badgeUpdated`, `creatorId`, `ownerId` | Audit metadata |
| `active`, `access`, `allowTableDrill`, `locked`, `isCurrentUserOwner` | Permission flags |

## Layout shape (`pageLayoutV4`)

```json
{
  "pageLayoutV4": {
    "layoutId": 12345,
    "pageUrn": "794859642",
    "standard": {
      "aspectRatio": "WIDE",
      "width": 60,                    // 60-col grid
      "template": [
        {
          "contentKey": 15,
          "x": 0, "y": 0, "width": 60, "height": 8,
          "type": "CARD",             // or "SEPARATOR", "PAGE_BREAK", "HEADER"
          "virtual": false,
          "children": []
        }
      ]
    },
    "content": [
      {
        "id": 2859,
        "contentKey": 15,
        "cardId": 1971939300,
        "cardUrn": "1971939300",
        "type": "CARD",
        "background": { ... },
        "hideTitle": true,
        "hideSummary": false,
        "hideTimeframe": false,
        "acceptFilters": true,
        "acceptDateFilter": true,
        "acceptSegments": true
      }
    ]
  }
}
```

### Layout fields we READ

| Field | Use |
|---|---|
| `standard.template[].contentKey` | Joins to `content[].contentKey` |
| `standard.template[].x` / `y` / `width` / `height` | Grid position (60-col, row-units) |
| `standard.template[].type` | `CARD` / `SEPARATOR` / `PAGE_BREAK` / `HEADER` |
| `content[].contentKey` → `cardId` | Maps layout slot to a card |
| `content[].hideTitle` / `hideDescription` | If `hideTitle=true`, omit the auto-title text element |
| `content[].acceptFilters` / `acceptDateFilter` / `acceptSegments` | If `false`, this card overrides page-level controls — emit element-level filter instead |

### Layout fields we IGNORE

- `standard.frameMargin` / `framePadding` — Sigma uses fixed container padding
- `standard.aspectRatio` — Sigma is responsive
- `standard.background` — Sigma workbook backgrounds set post-publish
- `content[].backgroundId` / `background` — per-card background color; UI-only in Sigma
- `content[].showMoreContent` / `editInAppViewer` — Domo display flags
- `content[].virtual` / `virtualAppendix` — Domo's virtual-card system (lazy load)

## Layout types beyond CARD

| `type` value | What it is in Domo | Sigma equivalent |
|---|---|---|
| `CARD` | A chart/KPI/table card | Normal Sigma element |
| `SEPARATOR` | Horizontal-rule visual divider between sections | `divider` element |
| `HEADER` | A section heading bar (usually a few rows tall, full-width) | `text` element with `## ` markdown prefix; pull text from a sibling field |
| `PAGE_BREAK` | Visible only when exporting to PDF | Ignored (Sigma is web-first) |
| `SPACER` | Empty space placeholder | Leave the grid range empty |

## Date-filter rolling-period semantics

Domo:
```json
{
  "dateTimeRangeType": "ROLLING_PERIOD",
  "interval": "DAY",
  "count": 90,
  "offset": 0
}
```

→ Sigma date-range control:
```json
{
  "kind": "control",
  "controlType": "date-range",
  "mode": "current",
  "unit": "day",
  "count": 90
}
```

| Domo `interval` | Sigma `unit` |
|---|---|
| `DAY` | `day` |
| `WEEK` | `week` |
| `MONTH` | `month` |
| `QUARTER` | `quarter` |
| `YEAR` | `year` |

`offset: 0` means "ending today". Non-zero offset = lagging window; emit Sigma `mode: "previous"` with the same unit/count.

`dateTimeRangeType: "INTERVAL_OFFSET"` with `count: 0` = "this period to date" (e.g., YTD). Map to Sigma `mode: "current"` + `unit` of the interval, then add an element-level filter `[<col>] <= Today()`.

## Slicer semantics

Each slicer is a page-level filter control. We dedupe by `(column, dataSourceId)` across all cards.

| Domo slicer field | Sigma control mapping |
|---|---|
| `column` | The filter target column (still needs SF column name mapping) |
| `type` | `"string"` → `list` control; `"number"` → `number-range`; `"date"` → `date-range` |
| `displayType` | `"multiple_select"` → `list` w/ multi-select; `"single_select"` → `list` mode single; `"checkbox"` → `list` |
| `operator` | `IN` → `mode: "include"`; `NOT_IN` → `mode: "exclude"`; `BETWEEN` → numeric/date-range |
| `values` | Pre-selected values (often empty if it's just a filter shelf) |
| `dataSourceId` | Which DM element the control filters (one-of, when dashboard mixes datasources) |
