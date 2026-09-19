"""
[DEBUG TOOL] Render, bake and split a single RECIPE markdown page in isolation,
then report every produced sheet's band/column text order and save screenshots.

Companion to debug_split_one.py (content pages): recipes must go through
process_recipe_to_html so the sheet carries the real aside/article structure
the splitter's recipe branch measures - a content-page render would split as
kind=content and prove nothing about ingredient/hardware bands.

Usage:
    python 02_pdf_creation/debug/debug_split_recipe.py "_1.2.2. Bibimbap.md"

Sheets and screenshots are written to <system temp>/cookbook_split_debug/.
"""

import os
import shutil
import sys
from pathlib import Path

# This tool lives in 02_pdf_creation/debug/: derive the tool root (the folder
# holding main_generate_cookbook.py, helpers/ and lib/) and the repo root
# (holding data_modularflavour/text/) from the script location so it runs regardless of CWD.
_SCRIPT_DIR = Path(__file__).parent.resolve()   # .../02_pdf_creation/debug
_TOOL_ROOT = _SCRIPT_DIR.parent                 # .../02_pdf_creation
_REPO_ROOT = _TOOL_ROOT.parent                  # repo root: data_modularflavour/text/, exports/
for _d in (_TOOL_ROOT, _TOOL_ROOT / "helpers"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from main_generate_cookbook import CookbookGenerator  # noqa: E402
from page_splitter import split_page_file  # noqa: E402
from html_to_pdf import _get_browser, _path_to_uri  # noqa: E402

_LIB_FILES = ("mermaid.min.js", "tailwind.min.js")

# Per sheet: every band's head label and, per column, the placed units in
# order. Reading order is left column then right column, so the unit lists
# show whether a section (e.g. Hardware) stayed whole and in source order.
_COLUMNS_JS = """
() => Array.from(document.querySelectorAll('.recipe-page')).map(sh => ({
  bands: Array.from(sh.querySelectorAll('[data-band]')).map(band => ({
    key: band.getAttribute('data-band'),
    head: (band.querySelector('[data-band-head] h2') || {}).textContent || null,
    cols: Array.from(band.querySelectorAll('[data-vcol]')).map(col => ({
      col: col.getAttribute('data-vcol'),
      units: Array.from(col.querySelectorAll('[data-vunit]')).map(n =>
        (n.tagName === 'H2' ? 'H2: ' : '')
        + (n.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 44))
    }))
  }))
}))
"""


def copy_libs(debug_dir: Path) -> None:
    """Copy the JS libs and vendored fonts next to the sheets (ADR 0018)."""
    lib_src = _TOOL_ROOT / "lib"
    if not lib_src.exists():
        return
    lib_dst = debug_dir / "lib"
    lib_dst.mkdir(parents=True, exist_ok=True)
    for name in _LIB_FILES:
        src = lib_src / name
        if src.exists():
            shutil.copy2(src, lib_dst / name)
    fonts_src = lib_src / "fonts"
    if fonts_src.exists():
        fonts_dst = lib_dst / "fonts"
        fonts_dst.mkdir(parents=True, exist_ok=True)
        for f in fonts_src.iterdir():
            if f.is_file():
                shutil.copy2(f, fonts_dst / f.name)


def report_and_screenshot(html_path: str, debug_dir: Path) -> None:
    browser = _get_browser()
    page = browser.new_page(viewport={"width": 794, "height": 1123},
                            device_scale_factor=1)
    page.emulate_media(media="print")
    try:
        page.goto(_path_to_uri(str(Path(html_path).resolve())),
                  timeout=60000, wait_until="networkidle")
        try:
            page.wait_for_function(
                "() => document.readyState !== 'loading'", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(300)
        sheets = page.evaluate(_COLUMNS_JS)
        count = page.locator('.recipe-page').count()
        for i in range(count):
            out = debug_dir / f"sheet_{i + 1}.png"
            page.locator('.recipe-page').nth(i).screenshot(path=str(out))
    finally:
        page.close()

    for i, sheet in enumerate(sheets):
        print(f"--- sheet {i + 1}: {len(sheet['bands'])} band(s) ---")
        for band in sheet['bands']:
            head = f"head={band['head']!r}" if band['head'] else "head=none"
            print(f"  band {band['key']} ({head})")
            for col in band['cols']:
                print(f"    col {col['col']}:")
                for u in col['units']:
                    print(f"      {u}")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python 02_pdf_creation/debug/debug_split_recipe.py "
                 "\"<recipe md filename>\"")
    md_name = sys.argv[1]

    debug_dir = Path(os.environ.get("TEMP", "/tmp")) / "cookbook_split_debug"
    data_base = _REPO_ROOT / "data_modularflavour"
    gen = CookbookGenerator(input_dir=[str(data_base / "text"),
                                       str(data_base / "text_notdone")],
                            temp_dir=str(debug_dir))
    content = gen.read_markdown_file(md_name)
    if content.startswith("# File not found"):
        sys.exit(f"markdown not found in data_modularflavour/text[/text_notdone]: {md_name}")

    _html, html_path = gen.process_recipe_to_html(md_name, content)
    if not html_path:
        sys.exit("render failed")

    copy_libs(debug_dir)

    diags = split_page_file(html_path)
    print("split diagnostics:")
    for d in diags or ["(fits on one sheet)"]:
        print(f"  {d}")
    report_and_screenshot(html_path, debug_dir)
    print(f"sheets + screenshots in: {debug_dir}")


if __name__ == "__main__":
    main()
