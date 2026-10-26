"""
Reporting tools — generate PPTX summaries from PLM/MES analysis data.
"""

import os
import tempfile
from datetime import datetime
from typing import Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt, Emu

# ── Autodesk brand palette ─────────────────────────────────────────────────
_BLACK    = RGBColor(0x00, 0x00, 0x00)
_WHITE    = RGBColor(0xFF, 0xFF, 0xFF)
_ADSK_BLU = RGBColor(0x00, 0x6E, 0xFF)   # Autodesk blue
_DARK     = RGBColor(0x1A, 0x1A, 0x2E)   # near-black for headers
_LIGHT    = RGBColor(0xF4, 0xF6, 0xF9)   # slide background
_GREEN    = RGBColor(0x00, 0x87, 0x5A)
_AMBER    = RGBColor(0xFF, 0x8C, 0x00)
_RED      = RGBColor(0xCC, 0x22, 0x22)
_GREY     = RGBColor(0x8A, 0x8A, 0x8A)

_RISK_COLOR = {"HIGH": _RED, "MEDIUM": _AMBER, "LOW": _GREEN}

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


# ── Helpers ────────────────────────────────────────────────────────────────

def _plm_url(tenant: str, ws_id: int, dms_id: int) -> str:
    tenant_upper = tenant.upper()
    urn = f"urn%60adsk,plm%60tenant,workspace,item%60{tenant_upper},{ws_id},{dms_id}"
    return (f"https://{tenant}.autodeskplm360.net/plm/workspaces/{ws_id}"
            f"/items/itemDetails?view=full&tab=details&mode=view&itemId={urn}")


def _ops_order_url(order_id) -> str:
    return f"https://fusionoperations.autodesk.com/admin/productionorders/{order_id}"


def _blank_slide(prs: Presentation) -> object:
    """Add a slide using the blank layout."""
    blank = prs.slide_layouts[6]
    return prs.slides.add_slide(blank)


def _bg(slide, color: RGBColor = _LIGHT) -> None:
    from pptx.oxml.ns import qn
    from lxml import etree
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def _box(slide, left, top, width, height,
         bg: Optional[RGBColor] = None,
         line: Optional[RGBColor] = None,
         line_w: int = 0) -> object:
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height
    )
    shape.line.fill.background() if line is None else None
    if bg:
        shape.fill.solid()
        shape.fill.fore_color.rgb = bg
    else:
        shape.fill.background()
    if line:
        shape.line.color.rgb = line
        shape.line.width = line_w or Pt(1)
    else:
        shape.line.fill.background()
    return shape


def _label(slide, text: str, left, top, width, height,
           size: int = 11, bold: bool = False, color: RGBColor = _BLACK,
           align=PP_ALIGN.LEFT, wrap: bool = True) -> object:
    txb = slide.shapes.add_textbox(left, top, width, height)
    txb.word_wrap = wrap
    tf = txb.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return txb


def _linked_label(slide, text: str, url: str, left, top, width, height,
                  size: int = 11, bold: bool = False,
                  color: RGBColor = _ADSK_BLU) -> object:
    txb = slide.shapes.add_textbox(left, top, width, height)
    txb.word_wrap = True
    tf = txb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.underline = True
    # Attach hyperlink
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.oxml.ns import qn
    from lxml import etree
    rPr = run._r.get_or_add_rPr()
    hlinkClick = etree.SubElement(rPr, qn("a:hlinkClick"))
    rId = slide.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hlinkClick.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", rId)
    return txb


def _header_bar(slide, title: str, subtitle: str = "") -> None:
    _box(slide, 0, 0, SLIDE_W, Inches(1.1), bg=_DARK)
    _label(slide, title, Inches(0.35), Inches(0.12), Inches(10), Inches(0.55),
           size=22, bold=True, color=_WHITE)
    if subtitle:
        _label(slide, subtitle, Inches(0.35), Inches(0.62), Inches(12), Inches(0.38),
               size=12, color=RGBColor(0xCC, 0xDD, 0xFF))


def _risk_badge(slide, risk: str, left, top) -> None:
    color = _RISK_COLOR.get(risk, _GREY)
    _box(slide, left, top, Inches(1.1), Inches(0.33), bg=color)
    _label(slide, risk, left, top, Inches(1.1), Inches(0.33),
           size=10, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)


def _divider(slide, top, color: RGBColor = _ADSK_BLU) -> None:
    _box(slide, Inches(0.35), top, Inches(12.6), Pt(2), bg=color)


# ── Slide builders ─────────────────────────────────────────────────────────

def _slide_title(prs, data: dict) -> None:
    slide = _blank_slide(prs)
    # Dark full-bleed background
    _bg(slide, _DARK)
    # Blue accent bar at bottom
    _box(slide, 0, Inches(6.6), SLIDE_W, Inches(0.9), bg=_ADSK_BLU)

    _label(slide, "Change Impact Analysis",
           Inches(0.6), Inches(1.4), Inches(12), Inches(0.9),
           size=36, bold=True, color=_WHITE)

    co = data["co"]
    _label(slide, co["title"],
           Inches(0.6), Inches(2.4), Inches(12), Inches(0.65),
           size=24, color=RGBColor(0xAA, 0xCC, 0xFF))

    date_str = datetime.now().strftime("%B %d, %Y")
    _label(slide, f"Generated: {date_str}",
           Inches(0.6), Inches(3.15), Inches(6), Inches(0.4),
           size=13, color=_GREY)

    state = co.get("current_state", "")
    _label(slide, f"CO State: {state}",
           Inches(0.6), Inches(3.6), Inches(6), Inches(0.4),
           size=13, color=RGBColor(0xCC, 0xDD, 0xFF))

    # Urgency badge bottom-left
    urgency = data.get("urgency", "UNKNOWN")
    urg_color = {"CRITICAL": _RED, "HIGH": _AMBER, "MEDIUM": _GREEN}.get(urgency, _GREY)
    _box(slide, Inches(0.6), Inches(6.7), Inches(2.2), Inches(0.38), bg=urg_color)
    _label(slide, f"URGENCY: {urgency}",
           Inches(0.6), Inches(6.7), Inches(2.2), Inches(0.38),
           size=12, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)

    tenant = data["tenant"]
    _linked_label(slide, "Open in Fusion Manage",
                  _plm_url(tenant, co["ws_id"], co["co_id"]),
                  Inches(9.5), Inches(6.72), Inches(3.2), Inches(0.35),
                  size=11, color=_WHITE)


def _slide_co_summary(prs, data: dict) -> None:
    slide = _blank_slide(prs)
    _bg(slide, _LIGHT)
    _header_bar(slide, "Change Order Summary", "CO details and affected items")

    co      = data["co"]
    tenant  = data["tenant"]
    affected = data["affected_items"]

    # CO detail box
    _box(slide, Inches(0.35), Inches(1.25), Inches(5.8), Inches(5.9),
         bg=_WHITE, line=RGBColor(0xDD, 0xDD, 0xDD))
    _label(slide, "CHANGE ORDER", Inches(0.5), Inches(1.35), Inches(5.5), Inches(0.3),
           size=9, bold=True, color=_ADSK_BLU)
    _linked_label(slide, co["title"],
                  _plm_url(tenant, co["ws_id"], co["co_id"]),
                  Inches(0.5), Inches(1.65), Inches(5.5), Inches(0.5),
                  size=14, bold=True)

    rows = [
        ("Workflow State", co.get("current_state", "—")),
        ("Workspace ID",   str(co["ws_id"])),
        ("DMS ID",         str(co["co_id"])),
        ("Affected Items", str(len(affected))),
    ]
    y = Inches(2.25)
    for label, val in rows:
        _label(slide, label, Inches(0.5), y, Inches(2.2), Inches(0.35),
               size=10, color=_GREY)
        _label(slide, val, Inches(2.75), y, Inches(3.2), Inches(0.35),
               size=10, bold=True)
        y += Inches(0.38)

    # Affected items panel
    _box(slide, Inches(6.35), Inches(1.25), Inches(6.6), Inches(5.9),
         bg=_WHITE, line=RGBColor(0xDD, 0xDD, 0xDD))
    _label(slide, "AFFECTED ITEMS", Inches(6.5), Inches(1.35), Inches(6.3), Inches(0.3),
           size=9, bold=True, color=_ADSK_BLU)

    y = Inches(1.72)
    for ai in affected:
        _linked_label(slide, f"[{ai['dms_id']}]  {ai['title']}",
                      _plm_url(tenant, ai["ws_id"], ai["dms_id"]),
                      Inches(6.5), y, Inches(6.3), Inches(0.38), size=11, bold=True)
        y += Inches(0.38)
        details = [
            f"Transition: {ai.get('transition', '—')}",
            f"Release: '{ai.get('from_rel', '')}' -> '{ai.get('to_rel', '')}'",
            f"Effectivity: {ai.get('effectivity', '—')}",
        ]
        for d in details:
            _label(slide, d, Inches(6.65), y, Inches(6.1), Inches(0.28), size=9, color=_GREY)
            y += Inches(0.28)
        _divider(slide, y + Inches(0.04), RGBColor(0xEE, 0xEE, 0xEE))
        y += Inches(0.18)


def _slide_item_sourcing(prs, data: dict) -> None:
    slide = _blank_slide(prs)
    _bg(slide, _LIGHT)
    _header_bar(slide, "Affected Item & Sourcing", "Procurement type, AML suppliers, and lead times")

    tenant = data["tenant"]
    for ai in data["affected_items"]:
        sourcing = ai.get("sourcing", {})
        lt_days  = (sourcing.get("default_lead_time_days")
                    or sourcing.get("min_lead_time_days"))

        # Item info panel
        _box(slide, Inches(0.35), Inches(1.25), Inches(5.8), Inches(5.9),
             bg=_WHITE, line=RGBColor(0xDD, 0xDD, 0xDD))
        _label(slide, "ITEM DETAIL", Inches(0.5), Inches(1.35), Inches(5.5), Inches(0.28),
               size=9, bold=True, color=_ADSK_BLU)
        _linked_label(slide, ai["title"],
                      _plm_url(tenant, ai["ws_id"], ai["dms_id"]),
                      Inches(0.5), Inches(1.65), Inches(5.5), Inches(0.45),
                      size=13, bold=True)

        item_rows = [
            ("DMS ID",        str(ai["dms_id"])),
            ("PLM Lifecycle", ai.get("plm_lifecycle", "—")),
            ("PDM Status",    f"{ai.get('pdm_status', '—')} Rev {ai.get('pdm_revision', '—')}"),
            ("Procurement",   ai.get("procurement", "—")),
            ("Material",      ai.get("material", "—")),
            ("Dimensions",    ai.get("dimensions", "—")),
            ("Mass",          f"{ai.get('mass_kg', '—')} kg"),
        ]
        y = Inches(2.2)
        for lbl, val in item_rows:
            _label(slide, lbl, Inches(0.5), y, Inches(2.1), Inches(0.3), size=9, color=_GREY)
            _label(slide, val, Inches(2.65), y, Inches(3.3), Inches(0.3), size=9, bold=True)
            y += Inches(0.31)

        _label(slide, "WHERE USED", Inches(0.5), y + Inches(0.1), Inches(5.5), Inches(0.28),
               size=9, bold=True, color=_ADSK_BLU)
        y += Inches(0.42)
        for wu in ai.get("where_used", []):
            rel = f"  Rev {wu['release']}" if wu.get("release") else ""
            _linked_label(slide,
                          f"[{wu['dms_id']}]  {wu['title']}  ({wu['lifecycle']}{rel})",
                          _plm_url(tenant, 57, wu["dms_id"]),
                          Inches(0.5), y, Inches(5.5), Inches(0.32), size=9)
            y += Inches(0.32)

        # Supplier & quotes panel
        _box(slide, Inches(6.35), Inches(1.25), Inches(6.6), Inches(5.9),
             bg=_WHITE, line=RGBColor(0xDD, 0xDD, 0xDD))
        _label(slide, "APPROVED SUPPLIERS & QUOTES (AML)",
               Inches(6.5), Inches(1.35), Inches(6.3), Inches(0.28),
               size=9, bold=True, color=_ADSK_BLU)

        y2 = Inches(1.72)
        for sup in sourcing.get("suppliers", []):
            _label(slide, sup["supplier_name"],
                   Inches(6.5), y2, Inches(6.3), Inches(0.32),
                   size=11, bold=True)
            y2 += Inches(0.3)
            _label(slide, f"Part#: {sup['supplier_part_number']}   "
                          f"Mfr: {sup['manufacturer']} {sup['manufacturer_part_number']}",
                   Inches(6.65), y2, Inches(6.1), Inches(0.27), size=9, color=_GREY)
            y2 += Inches(0.28)
            for q in sup.get("quotes", []):
                def_str = " [DEFAULT]" if q["is_default"] else ""
                _label(slide, f"Quote{def_str}:",
                       Inches(6.65), y2, Inches(1.4), Inches(0.27),
                       size=9, bold=q["is_default"], color=_DARK)
                _label(slide, f"Lead time: {q['lead_time_days']}d  |  "
                              f"${q['unit_price']}/unit  |  "
                              f"qty {q['min_qty']}-{q['max_qty']}",
                       Inches(8.1), y2, Inches(4.6), Inches(0.27),
                       size=9, bold=q["is_default"])
                y2 += Inches(0.27)
            y2 += Inches(0.1)

        # Lead time summary badge
        lt_str = f"{lt_days} days" if lt_days else "NOT SPECIFIED"
        lt_color = _GREEN if lt_days else _RED
        _box(slide, Inches(6.5), y2 + Inches(0.1), Inches(5.8), Inches(0.42), bg=lt_color)
        _label(slide, f"Lead Time (default quote): {lt_str}",
               Inches(6.5), y2 + Inches(0.1), Inches(5.8), Inches(0.42),
               size=11, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)


def _slide_production_impact(prs, data: dict) -> None:
    slide = _blank_slide(prs)
    _bg(slide, _LIGHT)
    _header_bar(slide, "Production Order Impact", "Direct matches and BOM-component ancestry")

    at_risk = data["at_risk"]
    tenant  = data["tenant"]

    # Risk summary boxes
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in at_risk:
        counts[r["risk"]] = counts.get(r["risk"], 0) + 1

    x = Inches(0.35)
    for level in ("HIGH", "MEDIUM", "LOW"):
        _box(slide, x, Inches(1.25), Inches(2.8), Inches(1.1),
             bg=_RISK_COLOR[level])
        _label(slide, str(counts[level]),
               x, Inches(1.3), Inches(2.8), Inches(0.65),
               size=32, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)
        _label(slide, level,
               x, Inches(1.88), Inches(2.8), Inches(0.35),
               size=11, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)
        x += Inches(3.0)

    total_box_x = Inches(9.35)
    _box(slide, total_box_x, Inches(1.25), Inches(3.6), Inches(1.1),
         bg=_DARK)
    _label(slide, str(len(at_risk)),
           total_box_x, Inches(1.3), Inches(3.6), Inches(0.65),
           size=32, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)
    _label(slide, "TOTAL AT-RISK ORDERS",
           total_box_x, Inches(1.88), Inches(3.6), Inches(0.35),
           size=10, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)

    if not at_risk:
        _label(slide, "No production orders at risk.",
               Inches(0.35), Inches(2.65), Inches(12.6), Inches(0.5),
               size=14, color=_GREY, align=PP_ALIGN.CENTER)
        return

    # Table header
    col_x  = [Inches(0.35), Inches(1.55), Inches(3.35), Inches(5.5),
               Inches(7.2),  Inches(9.1),  Inches(10.8), Inches(11.9)]
    col_w  = [Inches(1.15),  Inches(1.75), Inches(2.1),  Inches(1.65),
               Inches(1.85),  Inches(1.65), Inches(1.1),  Inches(1.35)]
    headers = ["Risk", "Order", "Match Type", "Part Code",
               "Assembly", "Status", "% Done", "Due (days)"]

    _box(slide, Inches(0.35), Inches(2.55), Inches(12.6), Inches(0.38), bg=_DARK)
    for i, h in enumerate(headers):
        _label(slide, h, col_x[i], Inches(2.57), col_w[i], Inches(0.35),
               size=9, bold=True, color=_WHITE)

    y = Inches(2.93)
    for idx, r in enumerate(at_risk):
        row_bg = _WHITE if idx % 2 == 0 else RGBColor(0xF0, 0xF4, 0xFF)
        _box(slide, Inches(0.35), y, Inches(12.6), Inches(0.42), bg=row_bg)

        _risk_badge(slide, r["risk"], col_x[0], y + Inches(0.045))

        if r.get("order_id"):
            _linked_label(slide, r["order_code"], _ops_order_url(r["order_id"]),
                          col_x[1], y, col_w[1], Inches(0.42), size=9, bold=True)
        else:
            _label(slide, r["order_code"], col_x[1], y, col_w[1], Inches(0.42), size=9, bold=True)
        _label(slide, r["match_type"], col_x[2], y, col_w[2], Inches(0.42), size=9)
        _linked_label(slide, r["part"],
                      _plm_url(tenant, 57, int(r["part"])),
                      col_x[3], y, col_w[3], Inches(0.42), size=9)
        parent_txt = r.get("parent") or "—"
        if r.get("parent"):
            _linked_label(slide, parent_txt,
                          _plm_url(tenant, 57, int(r["parent"])),
                          col_x[4], y, col_w[4], Inches(0.42), size=9)
        else:
            _label(slide, parent_txt, col_x[4], y, col_w[4], Inches(0.42), size=9)
        _label(slide, r.get("status", "—"), col_x[5], y, col_w[5], Inches(0.42), size=9)
        _label(slide, f"{r.get('pct', 0)}%", col_x[6], y, col_w[6], Inches(0.42), size=9)
        days = r.get("days_until_due")
        _label(slide, f"{days}d" if days is not None else "—",
               col_x[7], y, col_w[7], Inches(0.42), size=9, bold=True,
               color=_RED if days is not None and days <= 7 else _BLACK)
        y += Inches(0.42)


def _slide_timeline(prs, data: dict) -> None:
    slide = _blank_slide(prs)
    _bg(slide, _LIGHT)
    _header_bar(slide, "Lead Time vs. Order Timeline",
                "Can the ECO be implemented before the order is due?")

    at_risk = data["at_risk"]
    if not at_risk:
        _label(slide, "No production orders to assess.",
               Inches(0.5), Inches(3.0), Inches(12), Inches(0.5),
               size=14, color=_GREY, align=PP_ALIGN.CENTER)
        return

    for ai in data["affected_items"]:
        sourcing  = ai.get("sourcing", {})
        lt_days   = (sourcing.get("default_lead_time_days")
                     or sourcing.get("min_lead_time_days"))
        my_orders = [r for r in at_risk if r["part"] == ai["ops_code"]]
        if not my_orders:
            continue

        min_days = min(
            r["days_until_due"] for r in my_orders if r["days_until_due"] is not None
        )

        # Timeline bar
        bar_left  = Inches(0.5)
        bar_top   = Inches(2.0)
        bar_w     = Inches(12.0)
        bar_h     = Inches(0.55)
        max_days  = max(lt_days or 30, min_days, 30) + 5

        _box(slide, bar_left, bar_top, bar_w, bar_h,
             bg=RGBColor(0xE0, 0xE0, 0xE0))

        # Lead time zone (red)
        lt_frac = min((lt_days or 0) / max_days, 1.0)
        lt_px   = int(bar_w * lt_frac)
        _box(slide, bar_left, bar_top, Emu(lt_px), bar_h,
             bg=RGBColor(0xFF, 0xCC, 0xCC))

        # Due-date marker
        due_frac = min(min_days / max_days, 1.0)
        due_x    = bar_left + Emu(int(bar_w * due_frac))
        _box(slide, due_x - Inches(0.03), bar_top - Inches(0.1),
             Inches(0.06), bar_h + Inches(0.2), bg=_AMBER)
        _label(slide, f"Order Due\n{min_days}d",
               due_x - Inches(0.6), bar_top + bar_h + Inches(0.05),
               Inches(1.2), Inches(0.45), size=9, bold=True,
               color=_AMBER, align=PP_ALIGN.CENTER)

        # Lead time label
        if lt_days:
            lt_x = bar_left + Emu(int(bar_w * lt_frac))
            _box(slide, lt_x - Inches(0.03), bar_top - Inches(0.1),
                 Inches(0.06), bar_h + Inches(0.2), bg=_RED)
            _label(slide, f"Lead Time\n{lt_days}d",
                   lt_x - Inches(0.6), bar_top - Inches(0.6),
                   Inches(1.2), Inches(0.45), size=9, bold=True,
                   color=_RED, align=PP_ALIGN.CENTER)

        # Today label
        _label(slide, "Today", bar_left - Inches(0.05), bar_top + bar_h + Inches(0.05),
               Inches(0.7), Inches(0.3), size=9, color=_DARK)
        _label(slide, f"+{max_days}d",
               bar_left + bar_w - Inches(0.4), bar_top + bar_h + Inches(0.05),
               Inches(0.5), Inches(0.3), size=9, color=_GREY)

        # Verdict
        can_do = lt_days is not None and min_days > lt_days
        verdict_color = _GREEN if can_do else _RED
        verdict_text  = (
            f"Change IS achievable: {min_days}d remaining > {lt_days}d lead time  "
            f"(slack: {min_days - lt_days}d)"
            if can_do else
            f"CANNOT implement before due date: "
            f"{min_days}d remaining  <  {lt_days or '?'}d lead time"
            + (f"  (shortfall: {lt_days - min_days}d)" if lt_days else "")
        )
        _box(slide, Inches(0.5), Inches(3.1), Inches(12.0), Inches(0.55),
             bg=verdict_color)
        _label(slide, verdict_text, Inches(0.6), Inches(3.1), Inches(11.8), Inches(0.55),
               size=11, bold=True, color=_WHITE)

        # Per-order detail
        y = Inches(3.95)
        _label(slide, "ORDER DETAILS", Inches(0.5), y, Inches(12), Inches(0.28),
               size=9, bold=True, color=_ADSK_BLU)
        y += Inches(0.35)
        for r in my_orders:
            days_left = r.get("days_until_due")
            shortfall = (lt_days - days_left) if (lt_days and days_left is not None) else None
            line = (f"Order {r['order_code']}  |  due in {days_left}d"
                    + (f"  via assembly {r['parent']}" if r["parent"] else "")
                    + (f"  |  shortfall: {shortfall}d" if shortfall and shortfall > 0 else "")
                    + (f"  |  slack: {-shortfall}d" if shortfall and shortfall < 0 else ""))
            _label(slide, line, Inches(0.65), y, Inches(11.8), Inches(0.32),
                   size=10, color=_DARK)
            y += Inches(0.35)


def _slide_recommendations(prs, data: dict) -> None:
    slide = _blank_slide(prs)
    _bg(slide, _LIGHT)
    _header_bar(slide, "Recommendations & Next Actions", "")

    at_risk  = data["at_risk"]
    affected = data["affected_items"]
    urgency  = data.get("urgency", "UNKNOWN")

    # Urgency banner
    urg_color = {"CRITICAL": _RED, "HIGH": _AMBER, "MEDIUM": _GREEN}.get(urgency, _GREY)
    _box(slide, Inches(0.35), Inches(1.25), Inches(12.6), Inches(0.55), bg=urg_color)
    _label(slide, f"URGENCY: {urgency}",
           Inches(0.35), Inches(1.25), Inches(12.6), Inches(0.55),
           size=14, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)

    recs = []
    for ai in affected:
        sourcing  = ai.get("sourcing", {})
        lt_days   = (sourcing.get("default_lead_time_days")
                     or sourcing.get("min_lead_time_days"))
        my_orders = [r for r in at_risk if r["part"] == ai["ops_code"]]
        if not my_orders:
            recs.append(("INFO", "No active production orders reference this part. "
                         "Safe to advance the CO workflow."))
        else:
            min_days = min(
                r["days_until_due"] for r in my_orders if r["days_until_due"] is not None
            )
            suppliers = ", ".join(
                s["supplier_name"] for s in sourcing.get("suppliers", [])
                if s["supplier_name"]
            ) or "supplier"
            order_codes = ", ".join(r["order_code"] for r in my_orders)
            if lt_days and min_days <= lt_days:
                recs += [
                    ("STOP",
                     f"Do NOT apply ECO to order(s) {order_codes} — only {min_days}d remain, "
                     f"lead time is {lt_days}d."),
                    ("ACTION",
                     f"Contact {suppliers} immediately to check expedite feasibility."),
                    ("ACTION",
                     f"If expedite is not possible: ship existing pre-change stock for "
                     f"order(s) {order_codes}. Set ECO effectivity to the next order."),
                    ("ACTION",
                     f"Hold or coordinate delivery dates with customer if the order is held."),
                ]
            elif lt_days:
                slack = min_days - lt_days
                recs += [
                    ("GO",
                     f"Change is achievable — {min_days}d remaining > {lt_days}d lead time "
                     f"(slack: {slack}d)."),
                    ("ACTION", f"Place order with {suppliers} immediately to protect the buffer."),
                ]
        if not sourcing.get("has_quotes") or lt_days is None:
            recs.append(("DATA GAP",
                         f"Lead time is not set in PLM for part {ai['dms_id']}. "
                         "Enter lead time from supplier quote to enable automated risk scoring."))

    # Second supplier gap
    for ai in affected:
        for sup in ai.get("sourcing", {}).get("suppliers", []):
            if not sup.get("quotes"):
                recs.append(("DATA GAP",
                             f"Supplier '{sup['supplier_name']}' has no quotes on file. "
                             "Request a quote to qualify as a fallback source."))

    icon_color = {"STOP": _RED, "ACTION": _ADSK_BLU,
                  "GO": _GREEN, "DATA GAP": _AMBER, "INFO": _GREY}
    y = Inches(2.0)
    for icon, text in recs:
        color = icon_color.get(icon, _GREY)
        _box(slide, Inches(0.35), y, Inches(1.1), Inches(0.38), bg=color)
        _label(slide, icon, Inches(0.35), y, Inches(1.1), Inches(0.38),
               size=9, bold=True, color=_WHITE, align=PP_ALIGN.CENTER)
        _label(slide, text, Inches(1.55), y, Inches(11.4), Inches(0.4),
               size=10, color=_DARK)
        y += Inches(0.5)

    # Quick links — at-risk production orders in Fusion Operations
    if at_risk:
        _divider(slide, y + Inches(0.1))
        y += Inches(0.25)
        _label(slide, "AT-RISK ORDERS IN FUSION OPERATIONS",
               Inches(0.35), y, Inches(12.6), Inches(0.28),
               size=9, bold=True, color=_ADSK_BLU)
        y += Inches(0.33)
        seen_ids: set = set()
        for r in at_risk:
            oid = r.get("order_id")
            if not oid or oid in seen_ids:
                continue
            seen_ids.add(oid)
            parent_note = f"  (assembly {r['parent']})" if r.get("parent") else ""
            label_text  = (f"{r['order_code']}{parent_note}  "
                           f"|  {r.get('status', '')}  "
                           f"|  due {r.get('due', '').split('T')[0]}")
            _linked_label(slide, label_text, _ops_order_url(oid),
                          Inches(0.5), y, Inches(12.4), Inches(0.32), size=10)
            y += Inches(0.35)


# ── Public API ─────────────────────────────────────────────────────────────

def build_cia_pptx(
    tenant: str,
    co: dict,
    affected_items: list[dict],
    at_risk: list[dict],
    output_path: Optional[str] = None,
) -> str:
    """
    Generate a Change Impact Analysis PPTX.

    Args:
        tenant:         PLM tenant hostname prefix (e.g. 'mycompany')
        co:             dict with keys: title, current_state, co_id, ws_id
        affected_items: list of affected item dicts (from get_eco_details + get_item_sourcing)
                        each must have: dms_id, ws_id, title, transition, from_rel, to_rel,
                        effectivity, ops_code, procurement, material, dimensions, mass_kg,
                        pdm_status, pdm_revision, plm_lifecycle, where_used[], sourcing{}
        at_risk:        list of at-risk order dicts (from get_active_orders_at_risk)
                        each must have: part, parent, order_code, risk, match_type,
                        status, active, pct, due, days_until_due
        output_path:    file path for the .pptx (defaults to temp file)

    Returns:
        Absolute path to the generated .pptx file.
    """
    # Determine urgency
    lt_days = None
    for ai in affected_items:
        s = ai.get("sourcing", {})
        lt_days = s.get("default_lead_time_days") or s.get("min_lead_time_days") or lt_days

    min_days_until_due = None
    for r in at_risk:
        d = r.get("days_until_due")
        if d is not None:
            min_days_until_due = d if min_days_until_due is None else min(min_days_until_due, d)

    if min_days_until_due is not None and lt_days:
        if min_days_until_due <= lt_days:
            urgency = "CRITICAL" if min_days_until_due <= 7 else "HIGH"
        else:
            urgency = "MEDIUM"
    elif at_risk:
        urgency = "UNKNOWN"
    else:
        urgency = "LOW"

    data = {
        "tenant":       tenant,
        "co":           co,
        "affected_items": affected_items,
        "at_risk":      at_risk,
        "urgency":      urgency,
    }

    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H

    _slide_title(prs, data)
    _slide_co_summary(prs, data)
    _slide_item_sourcing(prs, data)
    _slide_production_impact(prs, data)
    _slide_timeline(prs, data)
    _slide_recommendations(prs, data)

    if not output_path:
        fd, output_path = tempfile.mkstemp(suffix=".pptx", prefix="cia_")
        os.close(fd)

    prs.save(output_path)
    return os.path.abspath(output_path)


async def generate_cia_pptx(
    tenant: str,
    co: dict,
    affected_items: list[dict],
    at_risk: list[dict],
    output_path: Optional[str] = None,
) -> dict:
    """
    Async wrapper for the MCP tool — generates the PPTX and returns the file path.
    """
    path = build_cia_pptx(tenant, co, affected_items, at_risk, output_path)
    return {"success": True, "file_path": path}
