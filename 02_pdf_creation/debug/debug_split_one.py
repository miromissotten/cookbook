"""
[DEBUG TOOL] Render, bake and split a single markdown page in isolation,
then summarise every produced sheet (text volume, SVG/giant presence).

Runs one file through the same pipeline steps as the full build
(render -> mermaid bake -> browser-measured split) without generating the
whole book, giving a seconds-fast feedback loop for splitter work.

Usage:
    python 02_pdf_creation/debug/debug_split_one.py "_1.1.0. Ramen flowchart.md"

Sheets are written to <system temp>/cookbook_split_debug/.
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

from main_generate_cookbook import CookbookGenerator
from mermaid_renderer import bake_mermaid_in_file
from page_splitter import split_page_file
from html_to_pdf import _get_browser, _path_to_uri

_LIB_FILES = ("mermaid.min.js", "tailwind.min.js")


def summarise(html_path: str) -> None:
    """Load the split document and print one diagnostic line per sheet."""
    browser = _get_browser()
    page = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=1)
    page.emulate_media(media="print")
    try:
        page.goto(_path_to_uri(str(Path(html_path).resolve())),
                  timeout=60000, wait_until="networkidle")
        # networkidle can fire while the document is still streaming in from
        # file:// - wait for parsing to finish before counting sheets.
        try:
            page.wait_for_function(
                "() => document.readyState !== 'loading'", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(300)
        rows = page.evaluate("""
            () => Array.from(document.querySelectorAll('.recipe-page, .a4-page')).map(sh => {
              const strip = sh.querySelector('.cont-strip');
              const header = sh.querySelector('h1');
              return {
                label: ((header || strip || {}).textContent || '').trim(),
                hasHeader: !!header,
                hasStrip: !!strip,
                textLen: (sh.innerText || '').trim().length,
                giants: sh.querySelectorAll('[data-giant]').length,
                svgs: sh.querySelectorAll('svg').length,
                children: sh.children.length
              };
            })
        """)
        if not rows:
            # Diagnostic fallback: why did the sheet selector match nothing?
            info = page.evaluate("""
                () => ({
                  readyState: document.readyState,
                  bodyChildren: document.body ? document.body.children.length : -1,
                  mainChildren: document.querySelector('main')
                    ? document.querySelector('main').children.length : -1,
                  firstClasses: document.body
                    ? Array.from(document.body.querySelectorAll('*'))
                        .slice(0, 12).map(n => n.tagName + '.' + n.className)
                    : [],
                  recipePages: document.querySelectorAll('.recipe-page').length,
                  title: document.title
                })
            """)
            print(f"[summarise] FALLBACK INFO: {info}")

    finally:
        page.close()

    print(f"--- {Path(html_path).name}: {len(rows)} sheet(s) ---")
    for i, r in enumerate(rows):
        origin = ('HEADER' if r['hasHeader']
                  else ('strip ' if r['hasStrip'] else 'BARE   '))
        flag = ''
        if r['hasHeader'] and r['svgs'] == 0 and r['giants'] == 0 and r['textLen'] < 150:
            flag = '   <-- TITLE-ONLY SHEET'
        elif not r['hasHeader'] and r['svgs'] == 0 and r['giants'] == 0 and r['textLen'] < 60:
            flag = '   <-- STRIP-ONLY SHEET'
        print(f"sheet {i + 1}: [{origin}] textLen={r['textLen']:5d} giants={r['giants']} "
              f"svgs={r['svgs']} children={r['children']} label={r['label'][:40]!r}{flag}")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python 02_pdf_creation/debug/debug_split_one.py \"<md filename>\"")
    md_name = sys.argv[1]

    debug_dir = Path(os.environ.get("TEMP", "/tmp")) / "cookbook_split_debug"
    data_base = _REPO_ROOT / "data_modularflavour"
    gen = CookbookGenerator(input_dir=[str(data_base / "text"),
                                       str(data_base / "text_notdone")],
                            temp_dir=str(debug_dir))
    content = gen.read_markdown_file(md_name)
    if content.startswith("# File not found"):
        sys.exit(f"markdown not found in data_modularflavour/text[/text_notdone]: {md_name}")

    title = Path(md_name).stem.replace('_', ' ').title()
    _html, html_path = gen.process_non_recipe_to_html(
        md_name, content, title)
    if not html_path:
        sys.exit("render failed")

    # Copy the JS libs next to the sheet so template script tags resolve.
    lib_src = _TOOL_ROOT / "lib"
    if lib_src.exists():
        lib_dst = debug_dir / "lib"
        lib_dst.mkdir(parents=True, exist_ok=True)
        for name in _LIB_FILES:
            src = lib_src / name
            if src.exists():
                shutil.copy2(src, lib_dst / name)
        # Vendored print fonts (ADR 0018): sheets reference lib/fonts/fonts.css.
        fonts_src = lib_src / "fonts"
        if fonts_src.exists():
            fonts_dst = lib_dst / "fonts"
            fonts_dst.mkdir(parents=True, exist_ok=True)
            for f in fonts_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, fonts_dst / f.name)

    browser = _get_browser()
    with open(html_path, 'r', encoding='utf-8') as fh:
        txt = fh.read()
    if 'class="mermaid"' in txt:
        try:
            baked = bake_mermaid_in_file(html_path, browser)
            print(f"bake: {'ok' if baked else 'no mermaid divs found'}")
        except Exception as exc:
            print(f"bake FAILED: {exc}")
    else:
        print("bake: skipped (no mermaid blocks)")

    diags = split_page_file(html_path)
    print("split diagnostics:", diags or "(fits on one sheet)")
    summarise(html_path)


if __name__ == "__main__":
    main()
