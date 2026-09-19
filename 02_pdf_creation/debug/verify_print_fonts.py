"""Post-build font audit (ADR 0018): fail when the shipped book embeds
fallback fonts.

The conversion-time gate (``ensure_print_fonts``) refuses fallback-font
sheets during the build; this auditor is the artifact-level backstop. It
scans the final merged PDFs page by page and exits non-zero when any page
embeds a font from a known fallback family.

Signatures (see debug/smoke_font_gate.py): loaded *webfonts* embed as
unnamed Type3 glyph fonts; a fallback (the chapter 2/3 Segoe incident)
shows up as a named TrueType/CID font. The page-number overlay's
/Helvetica* fonts carry no fallback family name and are ignored naturally.

Usage:
    python 02_pdf_creation/debug/verify_print_fonts.py [pdf ...]

Without arguments it audits both shipped variants.
"""

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent.resolve()
_REPO_ROOT = _SCRIPT_DIR.parent.parent

FALLBACK_MARKERS = ("Segoe", "Arial", "Times", "Calibri", "Courier")

DEFAULT_PDFS = (
    _REPO_ROOT / "exports" / "Cookbook_print.pdf",
    _REPO_ROOT / "exports" / "Cookbook_digital.pdf",
)


def _walk_page_fonts(page, named: set, type3: list) -> None:
    """Collect named fonts and count Type3 fonts on one page, including
    Type0 descendants and fonts nested in Form XObjects."""
    def collect(font_obj) -> None:
        try:
            obj = font_obj.get_object()
        except Exception:
            return
        if obj.get("/Subtype") == "/Type3":
            type3.append(obj)
            return
        bf = obj.get("/BaseFont")
        if bf:
            named.add(str(bf))
        descendants = obj.get("/DescendantFonts")
        if descendants:
            for sub in descendants.get_object():
                sbf = sub.get_object().get("/BaseFont")
                if sbf:
                    named.add(str(sbf))

    def walk_resources(res) -> None:
        if res is None:
            return
        res = res.get_object()
        fonts = res.get("/Font")
        if fonts:
            fonts = fonts.get_object()
            for key in fonts:
                collect(fonts[key])
        xobjs = res.get("/XObject")
        if xobjs:
            for key in xobjs.get_object():
                xo = xobjs.get_object()[key].get_object()
                if xo.get("/Subtype") == "/Form":
                    walk_resources(xo.get("/Resources"))

    walk_resources(page.get("/Resources"))


def audit_pdf(pdf_path: Path):
    """Return (bad_pages, type3_pages) for one PDF.

    bad_pages: list of (page_number, sorted fallback font names).
    type3_pages: number of pages that embed webfont (Type3) text.
    """
    from pypdf import PdfReader

    bad_pages = []
    type3_pages = 0
    for page_no, page in enumerate(PdfReader(str(pdf_path)).pages, start=1):
        named = set()
        type3 = []
        _walk_page_fonts(page, named, type3)
        if type3:
            type3_pages += 1
        bad = sorted(
            f for f in named
            if any(marker in f for marker in FALLBACK_MARKERS))
        if bad:
            bad_pages.append((page_no, bad))
    return bad_pages, type3_pages


def main(argv) -> int:
    pdfs = [Path(p) for p in argv[1:]] or list(DEFAULT_PDFS)
    total_bad_pages = 0
    for pdf in pdfs:
        if not pdf.exists():
            print(f"FAIL: {pdf} does not exist")
            total_bad_pages += 1
            continue
        bad_pages, type3_pages = audit_pdf(pdf)
        print(f"{pdf.name}: {len(bad_pages)} page(s) with fallback fonts, "
              f"{type3_pages} page(s) with webfont (Type3) text")
        for page_no, fonts in bad_pages[:20]:
            print(f"  p{page_no}: {', '.join(fonts)}")
        if len(bad_pages) > 20:
            print(f"  ... and {len(bad_pages) - 20} more pages")
        total_bad_pages += len(bad_pages)
    if total_bad_pages:
        print("FAIL: fallback fonts are embedded in the shipped book; "
              "rebuild after checking the conversion gate output.")
        return 1
    print("OK: no fallback fonts embedded; body text uses the vendored "
          "webfonts.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
