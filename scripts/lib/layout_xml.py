"""Sigma workbook layout XML helpers.

Sigma uses a 24-col CSS grid. Layout is a single top-level XML string on the
workbook spec — NOT per-page. Each <Page> tag must carry the server-assigned
page ID. Container elements wrap children with <GridContainer>, leaf elements
use <LayoutElement>.

Never hand-write layout XML. Use these helpers.
"""

from __future__ import annotations
from xml.sax.saxutils import quoteattr


def le(eid: str, c0: int, c1: int, r0: int, r1: int) -> str:
    """<LayoutElement>. For plain elements (charts, KPIs, tables, text, dividers)."""
    if not eid:
        raise ValueError("LayoutElement elementId cannot be empty")
    return (
        f'  <LayoutElement elementId={quoteattr(eid)} '
        f'gridColumn="{c0} / {c1}" gridRow="{r0} / {r1}"/>'
    )


def gc(eid: str, c0: int, c1: int, r0: int, r1: int, inner: str) -> str:
    """<GridContainer>. For container elements that wrap child layouts.

    The inner string is the concatenated child XML (each line should be
    already indented by `le()` or a nested `gc()`).
    """
    if not eid:
        raise ValueError("GridContainer elementId cannot be empty")
    return (
        f'<GridContainer elementId={quoteattr(eid)} type="grid" '
        f'gridColumn="{c0} / {c1}" gridRow="{r0} / {r1}" '
        f'gridTemplateColumns="repeat(24, 1fr)" gridTemplateRows="auto">\n'
        f"{inner}\n</GridContainer>"
    )


def page_xml(page_id: str, *children: str) -> str:
    """A <Page> block for one workbook page.

    page_id MUST be the server-assigned page ID from the readback, not a name.
    """
    if not page_id:
        raise ValueError("Page id cannot be empty")
    header = (
        f'<Page type="grid" gridTemplateColumns="repeat(24, 1fr)" '
        f'gridTemplateRows="auto" id={quoteattr(page_id)}>'
    )
    return "\n".join([header, *children, "</Page>"])


def assemble(*pages: str) -> str:
    """Wrap one or more <Page> blocks with the XML prologue."""
    prologue = '<?xml version="1.0" encoding="utf-8"?>'
    return prologue + "\n" + "\n".join(pages)
