"""End-to-end smoke for the font-readiness gate + vendored fonts (ADR 0018).

Renders one chapter sub-TOC sheet and one generic content sheet into a
scratch folder outside the repo (ADR 0003), converts them through the real
Playwright path (``_convert_single_to_pdf`` with the font gate) and asserts
the printed PDFs embed the vendored webfonts - never a fallback like
Segoe UI, which caused the chapter 2/3 margin incident.

Usage:
    python 02_pdf_creation/debug/smoke_font_gate.py
"""

import sys
import tempfile
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent.resolve()
_TOOL_ROOT = _SCRIPT_DIR.parent
_REPO_ROOT = _TOOL_ROOT.parent
for _d in (_TOOL_ROOT, _TOOL_ROOT / "helpers"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from html_to_pdf import (  # noqa: E402
    _convert_single_to_pdf,
    close_browser_pool,
)
from page_content import ContentPageRenderer  # noqa: E402
from page_toc import TOCPageRenderer  # noqa: E402
from structure_parser import StructureParser  # noqa: E402


def copy_lib(target: Path) -> None:
    """Copy the tool's lib/ next to the sheets (same contract as the mains)."""
    src = _TOOL_ROOT / "lib"
    dst = target / "lib"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.rglob("*"):
        if f.is_file():
            rel_dst = dst / f.relative_to(src)
            rel_dst.parent.mkdir(parents=True, exist_ok=True)
            rel_dst.write_bytes(f.read_bytes())


def pdf_font_signature(pdf_path: Path) -> tuple:
    """(named fonts with BaseFont, count of Type3 fonts).

    Chromium embeds loaded *webfonts* as unnamed Type3 glyph fonts, while a
    fallback (like the Segoe UI incident) shows up as a named TrueType/CID
    font - hence this signature separates the two.
    """
    from pypdf import PdfReader

    named = set()
    type3_count = 0

    def collect(font_obj) -> None:
        nonlocal type3_count
        try:
            obj = font_obj.get_object()
        except Exception:
            return
        if obj.get("/Subtype") == "/Type3":
            type3_count += 1
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

    for page in PdfReader(str(pdf_path)).pages:
        walk_resources(page.get("/Resources"))
    return named, type3_count


def main() -> int:
    failures = []
    with tempfile.TemporaryDirectory(prefix="cookbook_font_smoke_") as tmp:
        workdir = Path(tmp)
        copy_lib(workdir)

        hier = StructureParser(input_dir=[str(_REPO_ROOT / "data_modularflavour" / "text"),
                                          str(_REPO_ROOT / "data_modularflavour" / "text_notdone")]) \
            .get_structure_hierarchy("_-1.0. cookbook_structure_generated.md")
        ch2 = next(s for s in hier if s["name"].startswith("_2."))
        renderer = TOCPageRenderer()
        toc_html = renderer._generate_chapter_tree_html(ch2, None, 5)
        sub_page = renderer._build_toc_page("_2. Carbohydrates", toc_html)
        (workdir / "ch2_subtoc.html").write_text(sub_page, encoding="utf-8")

        content = ContentPageRenderer().render(
            "_2.1. Rice", "<p>Smoke paragraph for the font gate.</p>")
        (workdir / "content.html").write_text(content, encoding="utf-8")

        for name in ("ch2_subtoc", "content"):
            ok = _convert_single_to_pdf(str(workdir / f"{name}.html"),
                                        str(workdir / f"{name}.pdf"))
            if not ok:
                failures.append(f"{name}: conversion refused (font gate or seam)")
                continue
            named, type3_count = pdf_font_signature(workdir / f"{name}.pdf")
            print(f"{name}: named fonts: {sorted(named)}, "
                  f"Type3 (webfont) fonts: {type3_count}")
            if any(("Segoe" in f) or ("Arial" in f) for f in named):
                failures.append(
                    f"{name}: fallback system font embedded: {sorted(named)}")
            if type3_count == 0:
                failures.append(
                    f"{name}: no Type3 (webfont) embedding found; text was "
                    f"likely rendered in a fallback font")

    close_browser_pool()
    if failures:
        print("SMOKE FAILED:")
        for f in failures:
            print(" -", f)
        return 1
    print("SMOKE OK: vendored fonts used, no fallback, font gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
