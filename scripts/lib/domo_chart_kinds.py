"""Single source of truth for Domo chartType -> Sigma element kind mapping.

When you add a new mapping here, also update refs/chart-type-mapping.md.

Class:
  "auto"     — straight 1:1, no special handling
  "hint"     — maps but needs post-publish UI step or PDF-disambiguation
  "gap"      — no Sigma equivalent; default placeholder + surface to user
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Mapping:
    sigma_kind: str | None
    cls: str  # "auto" | "hint" | "gap"
    note: str = ""


MAPPING: dict[str, Mapping] = {
    # KPIs
    "badge_singlevalue":       Mapping("kpi-chart",    "auto"),
    "badge_pop_multi_value":   Mapping("kpi-chart",    "auto",
                                       "period-over-period via calc col"),
    "badge_pop_trendline":     Mapping("kpi-chart",    "hint",
                                       "KPI+sparkline -> KPI + small line-chart in a container"),

    # Lines
    "badge_two_trendline":     Mapping("line-chart",   "auto",
                                       "two-series line; use combo-chart if mixed scales"),

    # Bars
    "badge_pop_vert_multibar": Mapping("bar-chart",    "auto",
                                       "period is breakdown dimension"),
    "badge_vert_stackedbar":   Mapping("bar-chart",    "auto", "set stacked: true"),

    # Pie / donut
    "badge_pie":               Mapping("pie-chart",    "auto"),
    "badge_donut":             Mapping("donut-chart",  "auto",
                                       "holeValue.id must differ from value.id"),

    # Tables
    "badge_basic_table":       Mapping("table",        "auto"),

    # Heatmap
    "badge_heatmap":           Mapping("pivot-table",  "hint",
                                       "heat color formatting applied UI-only post-publish"),

    # Maps
    "badge_map_us_county":     Mapping("region-map",   "auto", "regionType: county"),
    "badge_map_us_state":      Mapping("region-map",   "auto", "regionType: state"),
    "badge_map":               Mapping("region-map",   "hint",
                                       "confirm geo level from PDF"),

    # Scatter
    "badge_xybubble":          Mapping("scatter-chart", "auto", "size encoded"),
    "badge_scatter":           Mapping("scatter-chart", "auto"),

    # Gaps
    "badge_sankey":            Mapping(None,           "gap",
                                       "no native sankey; emit bar-chart placeholder"),
    "badge_funnel":            Mapping(None,           "gap",
                                       "no native funnel; emit sorted bar-chart placeholder"),

    # Controls
    "badge_checkbox_selector": Mapping("control",      "auto",
                                       "list control; mode include or exclude per operator"),
    "badge_segmented":         Mapping("control",      "auto", "segmented (radio)"),

    # Text
    "Text":                    Mapping("text",         "auto"),
    "kpiText":                 Mapping("text",         "auto"),
}


def lookup(domo_chart_type: str) -> Mapping:
    """Returns a Mapping for the given Domo chartType. Unknown types map to gap."""
    return MAPPING.get(
        domo_chart_type,
        Mapping(None, "gap", f"unknown Domo chartType {domo_chart_type!r}"),
    )
