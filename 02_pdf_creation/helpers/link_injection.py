"""
Measure-then-inject internal navigation links (ADR 0004).

Chromium emits GoTo annotations for ``<a href="#anchor">`` only when the
anchor lives in the same document, and this build converts groups of sheets
into separate group PDFs before merging them with pypdf (twice: merge +
page-number overlay). Relying on Chromium therefore ships dead links for
every cross-group reference. Instead:

1. MEASURE - during each group's existing browser pass we collect, via
   ``page.evaluate`` under print media emulation:
     - every ``a.wiki-link`` client rect (per rendered line),
     - every TOC row carrying ``data-toc-target`` (leader-line start, the
       document-wide right-number rail, text baseline),
     - the first occurrence of every ``id="page-..."`` anchor and its
       physical page index inside the document.
   The caller turns document-local pages into global physical pages using
   the group's start offset.

2. INJECT - after the final merge and page-numbering, proper pypdf GoTo
   link annotations are written onto the merged file, plus ReportLab overlay
    packets that draw TOC solid leaders with printed page numbers (both book
   variants) and green accent underlines (digital variant only). The digital
   variant also stamps a "back to table of contents" GoTo link in the footer
   band of every page from the TOC onwards; the print variant ships without it.

A hard gate fails the run instead of shipping a book with broken navigation:
every measured link must resolve to an existing physical page.
"""

import io
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link
from pypdf.generic import Fit, NumberObject
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from config import (
    PAGE_NUMBER_X_POSITION,
    PAGE_W_PT,
    PAGE_H_PT,
    PX_TO_PT,
    ACCENT_RGB,
    INK_RGB,
    BACK_TO_TOC_LABEL,
    BACK_TO_TOC_FONT,
    BACK_TO_TOC_FONT_SIZE,
    BACK_TO_TOC_BASELINE_MM,
)

# Digital-variant footer link (ADR 0004 amendment): "back to table of
# contents" printed in the footer band's empty right-hand slot, directly
# below the page number (which sits at 11 mm, on the label row above the
# band's green rule). Baseline lives in the ~2 mm gap between that rule
# and the solid green bar at the very bottom edge.
BACK_TO_TOC_LABEL

# Page-container classes used by both sheet templates (see
# html_to_pdf.combine_html_files, which extracts exactly these).
_SHEET_SELECTOR = ".recipe-page, main.a4-page"

_JS_COLLECT_NAV = """
() => {
  const PX2PT = 72 / 96;
  const containers = Array.from(document.querySelectorAll('%(sheet_selector)s'));
  const rects = containers.map(el => el.getBoundingClientRect());

  // Physical page index of a point: sheets stack flush, so the boundary is
  // the next container's top edge. Falls back to the nearest container above.
  const pageIndexFor = (cx, cy) => {
    for (let i = 0; i < rects.length; i++) {
      const bottom = (i + 1 < rects.length)
        ? rects[i + 1].top
        : rects[i].top + Math.max(rects[i].height, 1122.5);
      if (cy >= rects[i].top - 2 && cy < bottom - 2) return i;
    }
    let best = 0;
    for (let i = 0; i < rects.length; i++) { if (rects[i].top <= cy) best = i; }
    return best;
  };

  const rel = (v, base) => (v - base) * PX2PT;

  const links = [];
  document.querySelectorAll('a.wiki-link').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (!href.startsWith('#')) return;
    const target = href.slice(1);
    // DOMRectList is array-like but has no forEach - wrap it.
    Array.from(a.getClientRects()).forEach(r => {
      if (r.width <= 0 || r.height <= 0) return;
      const pi = pageIndexFor(r.left + r.width / 2, r.top + r.height / 2);
      const base = rects[pi] || {left: 0, top: 0};
      links.push({
        target: target,
        page: pi,
        x0: rel(r.left, base.left),
        y0: rel(r.top, base.top),
        x1: rel(r.right, base.left),
        y1: rel(r.bottom, base.top),
      });
    });
  });

  const rows = [];
  document.querySelectorAll('[data-toc-target]').forEach(row => {
    const target = row.getAttribute('data-toc-target');
    if (!target) return;
    const r = row.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    const pi = pageIndexFor(r.left + r.width / 2, r.top + r.height / 2);
    const base = rects[pi] || {left: 0, top: 0};
    const txt = row.querySelector('.toc-entry-text');
    const tr = txt ? txt.getBoundingClientRect() : r;
    const padR = parseFloat(getComputedStyle(row).paddingRight) || 0;
    rows.push({
      target: target,
      page: pi,
      leader_x0: rel(tr.right, base.left) + 4,
      // Own right edge for now; normalised to the shared rail below.
      number_right_x: rel(r.right, base.left) - padR * PX2PT,
      baseline_y: rel(tr.top + tr.height * 0.78, base.top),
    });
  });

  // One alignment rail for the whole document: full-width rows (section and
  // subsection titles, chip items) reach the sheet's text margin, so their
  // right edge defines where EVERY row's page number prints.
  if (rows.length > 0) {
    const railX = Math.max(...rows.map(row => row.number_right_x));
    rows.forEach(row => { row.number_right_x = railX; });
  }

  const anchors = [];
  const seen = Object.create(null);
  document.querySelectorAll('[id^="page-"]').forEach(el => {
    const id = el.id;
    if (seen[id]) return;
    seen[id] = true;
    const r = el.getBoundingClientRect();
    anchors.push({id: id, page: pageIndexFor(r.left + r.width / 2, r.top + r.height / 2)});
  });

  return {links: links, rows: rows, anchors: anchors};
}
""" % {"sheet_selector": _SHEET_SELECTOR}



class LinkInjectionError(RuntimeError):
    """Raised by the injection gate when navigation would ship broken."""


@dataclass
class LinkSpot:
    """One clickable client rect of a wiki link, on a known physical page."""
    target_page_id: str
    global_page: int          # 1-based physical page holding this rect
    x0_pt: float              # page-relative, top-left origin, in points
    y0_pt: float
    x1_pt: float
    y1_pt: float


@dataclass
class TocRowStamp:
    """One TOC row that receives a solid leader line and printed page number."""
    target_page_id: str
    row_global_page: int      # physical page the row itself prints on
    leader_x0_pt: float
    number_right_x_pt: float
    baseline_y_pt: float


@dataclass
class NavigationGeometry:
    """All measured navigation artifacts for one complete book."""
    link_spots: List[LinkSpot] = field(default_factory=list)
    toc_stamps: List[TocRowStamp] = field(default_factory=list)
    # page-id -> global physical page of its first sheet (1-based).
    page_map: Dict[str, int] = field(default_factory=dict)

    def commit_group(self, payload: dict, group_start_page: int) -> None:
        """Fold one group's raw measurement payload into the geometry.

        ``payload`` is what :data:`_JS_COLLECT_NAV` returned for a combined
        document whose first physical page is ``group_start_page``.
        """
        for link in payload.get("links", []):
            self.link_spots.append(LinkSpot(
                target_page_id=link["target"],
                global_page=group_start_page + int(link["page"]),
                x0_pt=float(link["x0"]), y0_pt=float(link["y0"]),
                x1_pt=float(link["x1"]), y1_pt=float(link["y1"]),
            ))
        for row in payload.get("rows", []):
            self.toc_stamps.append(TocRowStamp(
                target_page_id=row["target"],
                row_global_page=group_start_page + int(row["page"]),
                leader_x0_pt=float(row["leader_x0"]),
                number_right_x_pt=float(row["number_right_x"]),
                baseline_y_pt=float(row["baseline_y"]),
            ))
        for anchor in payload.get("anchors", []):
            global_page = group_start_page + int(anchor["page"])
            # First occurrence wins: continuation sheets may repeat ids, and
            # a link must always land on the target's FIRST sheet.
            self.page_map.setdefault(anchor["id"], global_page)


def collect_navigation_geometry(page) -> dict:
    """Measure link/row/anchor geometry on a loaded Playwright page.

    Switches the page to print media first: the templates' screen styles lay
    sheets out in a horizontal flex row (see page_splitter), which would
    corrupt every rectangle. Print media matches what page.pdf() renders.
    """
    page.emulate_media(media="print")
    return page.evaluate(_JS_COLLECT_NAV)


def _overlay_packet(draw_fn: Callable):
    """Render one A4 ReportLab page into an in-memory single-page PDF."""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(PAGE_W_PT, PAGE_H_PT))
    draw_fn(can)
    can.save()
    packet.seek(0)
    return PdfReader(packet).pages[0]



def _draw_toc_stamp(can, stamp: TocRowStamp, page_number: int) -> None:
    """Solid leader plus right-aligned printed page number, footer ink style."""
    label = str(page_number)
    num_width = stringWidth(label, "Helvetica", 9)
    num_x = stamp.number_right_x_pt - 2
    leader_end = num_x - num_width - 3
    baseline_y = PAGE_H_PT - stamp.baseline_y_pt

    can.setFillColorRGB(*INK_RGB)
    can.setFont("Helvetica", 9)
    can.drawRightString(num_x, baseline_y, label)

    if leader_end - stamp.leader_x0_pt >= 8:
        can.setStrokeColorRGB(*INK_RGB)
        can.setLineWidth(0.6)
        can.line(stamp.leader_x0_pt, baseline_y - 1.5, leader_end, baseline_y - 1.5)


def _draw_accent_underline(can, spot: LinkSpot) -> None:
    """Green underline hugging the link rect's lower edge (~1 pt tolerance)."""
    y = PAGE_H_PT - spot.y1_pt - 1.0
    can.setStrokeColorRGB(*ACCENT_RGB)
    can.setLineWidth(0.8)
    can.line(spot.x0_pt + 0.5, y, spot.x1_pt - 0.5, y)


def _draw_back_to_toc(can) -> None:
    """Footer label + accent underline for the digital variant's back link.

    Right-aligned on the page-number rail (195 mm), baseline inside the
    footer band's right-hand slot below the printed page number.
    """
    baseline = BACK_TO_TOC_BASELINE_MM * mm
    can.setFillColorRGB(*ACCENT_RGB)
    can.setFont(BACK_TO_TOC_FONT, BACK_TO_TOC_FONT_SIZE)
    can.drawRightString(PAGE_NUMBER_X_POSITION, baseline, BACK_TO_TOC_LABEL)
    width = stringWidth(BACK_TO_TOC_LABEL, BACK_TO_TOC_FONT,
                        BACK_TO_TOC_FONT_SIZE)
    can.setStrokeColorRGB(*ACCENT_RGB)
    can.setLineWidth(0.6)
    can.line(PAGE_NUMBER_X_POSITION - width, baseline - 1.5,
             PAGE_NUMBER_X_POSITION, baseline - 1.5)


def _back_to_toc_rect() -> tuple:
    """Clickable rect (PDF bottom-origin points) around the footer label."""
    baseline = BACK_TO_TOC_BASELINE_MM * mm
    width = stringWidth(BACK_TO_TOC_LABEL, BACK_TO_TOC_FONT,
                        BACK_TO_TOC_FONT_SIZE)
    x1 = PAGE_NUMBER_X_POSITION + 2
    x0 = x1 - width - 4
    # A little vertical padding so small fingers/cursor slop still hit it.
    return (x0, baseline - 2.5, x1, baseline + BACK_TO_TOC_FONT_SIZE + 1.5)


def inject_navigation(
    input_pdf: str,
    output_pdf: str,
    geometry: NavigationGeometry,
    accent_links: bool,
    back_to_toc_page: Optional[int] = None,
) -> dict:
    """Write ``output_pdf`` with GoTo links (+ overlays) baked in.

    Reads the fully merged, already page-numbered ``input_pdf`` and produces
    one shipped variant. Raises :class:`LinkInjectionError` when any measured
    link or TOC row targets a page that does not exist - the build must fail
    rather than ship broken navigation (same contract as seam checks).

    ``back_to_toc_page`` is the 1-based physical page of the main table of
    contents. When set, every page from there onwards receives a footer
    link back to the TOC (digital variant); the print variant passes None
    and ships without it.

    Returns a summary dict for the generation report.
    """
    reader = PdfReader(input_pdf)
    writer = PdfWriter()
    writer.append(reader)
    total_pages = len(writer.pages)

    def resolved(target: str) -> Optional[int]:
        page_idx = geometry.page_map.get(target)
        if page_idx is None or not 1 <= page_idx <= total_pages:
            return None
        return page_idx - 1  # 0-based for pypdf

    missing: List[str] = []
    overlays: Dict[int, list] = {}

    # Digital-only footer link back to the table of contents: gate first so
    # a digital book can never ship silently without its navigation aid.
    back_to_toc_links = 0
    if accent_links:
        if back_to_toc_page is None or not 1 <= back_to_toc_page <= total_pages:
            raise LinkInjectionError(
                f"back-to-TOC footer link target invalid: {back_to_toc_page!r} "
                f"(book has {total_pages} pages). Refusing to ship a digital "
                "book without working TOC navigation.")
        target_idx = back_to_toc_page - 1
        rect = _back_to_toc_rect()
        # Everything from the TOC's first physical page onwards: the title
        # page and its verso blank stay clean, later TOC pages jumping to
        # the TOC's start is harmless (and useful).
        for source_idx in range(back_to_toc_page, total_pages):
            writer.add_annotation(
                page_number=source_idx,
                annotation=Link(rect=rect, target_page_index=target_idx,
                                fit=Fit(fit_type="/Fit")),
            )
            overlays.setdefault(source_idx, []).append(_draw_back_to_toc)
            back_to_toc_links += 1

    added_links = 0
    for spot in geometry.link_spots:
        target_idx = resolved(spot.target_page_id)
        if target_idx is None:
            missing.append(f"link -> {spot.target_page_id}")
            continue
        source_idx = spot.global_page - 1
        if not 0 <= source_idx < total_pages:
            missing.append(f"link rect on missing page {spot.global_page}")
            continue
        # Flip top-origin page-relative points to PDF's bottom-origin space.
        rect = (spot.x0_pt, PAGE_H_PT - spot.y1_pt,
                spot.x1_pt, PAGE_H_PT - spot.y0_pt)
        writer.add_annotation(
            page_number=source_idx,
            annotation=Link(rect=rect, target_page_index=target_idx,
                            fit=Fit(fit_type="/Fit")),
        )
        added_links += 1
        if accent_links:
            overlays.setdefault(source_idx, []).append(
                lambda can, s=spot: _draw_accent_underline(can, s))

    stamped_rows = 0
    for stamp in geometry.toc_stamps:
        page_number = geometry.page_map.get(stamp.target_page_id)
        if page_number is None:
            missing.append(f"toc row -> {stamp.target_page_id}")
            continue
        row_idx = stamp.row_global_page - 1
        if not 0 <= row_idx < total_pages:
            missing.append(f"toc row on missing page {stamp.row_global_page}")
            continue
        overlays.setdefault(row_idx, []).append(
            lambda can, s=stamp, n=page_number: _draw_toc_stamp(can, s, n))
        stamped_rows += 1

    if missing:
        sample = ", ".join(sorted(set(missing))[:10])
        raise LinkInjectionError(
            f"{len(missing)} navigation element(s) target pages that were "
            f"never laid out (first few: {sample}). Refusing to ship a book "
            f"with broken links.")

    for page_idx, draw_ops in sorted(overlays.items()):
        def draw_all(can, ops=tuple(draw_ops)):
            for op in ops:
                op(can)
        writer.pages[page_idx].merge_page(_overlay_packet(draw_all))

    # pypdf writes Link(target_page_index=...) destinations as bare numbers
    # ("/Dest [7 /Fit]"). The spec wants local destinations to reference the
    # destination PAGE object - several viewers ignore numeric ones. Rewrite
    # every numeric first element into a real page reference.
    for pg in writer.pages:
        for aref in pg.get("/Annots") or []:
            obj = aref.get_object()
            if obj.get("/Subtype") != "/Link":
                continue
            dest = obj.get("/Dest")
            if dest is None or len(dest) == 0:
                continue
            if isinstance(dest[0], NumberObject):
                target_idx = int(dest[0])
                if 0 <= target_idx < len(writer.pages):
                    dest[0] = writer.pages[target_idx].indirect_reference

    with open(output_pdf, "wb") as f:
        writer.write(f)

    return {
        "links_measured": len(geometry.link_spots),
        "links_injected": added_links,
        "toc_rows_stamped": stamped_rows,
        "accent_underlines": len(geometry.link_spots) if accent_links else 0,
        "back_to_toc_links": back_to_toc_links,
        "pages": total_pages,
        "output": os.path.basename(output_pdf),
    }
