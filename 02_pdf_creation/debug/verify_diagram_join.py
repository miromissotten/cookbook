"""
[DEBUG TOOL] Regression guard for ADR 0017: every content-page diagram must
start on the same sheet as the text above it.

Runs every markdown source that embeds a ```mermaid fence through the same
pipeline steps as the full build (render -> mermaid bake -> browser-measured
split) and asserts the splitter never produces the stranded-intro pattern:
a title-only sheet (heading plus at most a couple of sentences, no diagram)
followed by the sheet carrying that diagram.

Usage:
    python 02_pdf_creation/debug/verify_diagram_join.py [md filename ...]

Without arguments every data_modularflavour/text/*.md source with a mermaid fence is
checked. Exits non-zero when a stranded intro is found.
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

# A sheet counts as a "stranded intro" when it carries the page header, no
# diagram (neither raw svg nor a giant/band/join-scaled block) and almost no
# text beyond the title and a sentence or two - and the NEXT sheet of the
# same source carries the diagram. Footer band + page number inflate
# innerText slightly, hence the 260-char allowance.
_STRANDED_TEXT_MAX = 260

_SHEET_ROWS_JS = """
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
"""

def sheet_rows(html_path: str, browser):
    """Load a split document in print media and return one row per sheet."""
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
        return page.evaluate(_SHEET_ROWS_JS)
    finally:
        page.close()


def find_violations(rows):
    """Return human-readable stranded-intro violations for one source."""
    violations = []
    for i in range(len(rows) - 1):
        cur, nxt = rows[i], rows[i + 1]
        if (cur["hasHeader"] and cur["svgs"] == 0 and cur["giants"] == 0
                and cur["textLen"] < _STRANDED_TEXT_MAX and nxt["svgs"] > 0):
            violations.append(
                f"sheet {i + 1} is a stranded intro (textLen={cur['textLen']}, "
                f"label={cur['label'][:40]!r}) with its diagram on sheet {i + 2}")
    return violations


def verify_source(md_name: str, gen: CookbookGenerator, debug_dir: Path,
                  browser) -> list:
    """Run one source through render -> bake -> split; return violations."""
    content = gen.read_markdown_file(md_name)
    if content.startswith("# File not found"):
        return [f"markdown not found in data_modularflavour/text[/text_notdone]: {md_name}"]

    title = Path(md_name).stem.replace("_", " ").title()
    _html, html_path = gen.process_non_recipe_to_html(
        md_name, content, title)
    if not html_path:
        return ["render failed"]

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

    with open(html_path, "r", encoding="utf-8") as fh:
        txt = fh.read()
    if 'class="mermaid"' in txt:
        try:
            bake_mermaid_in_file(html_path, browser)
        except Exception as exc:
            return [f"mermaid bake failed: {exc}"]

    split_page_file(html_path)
    return find_violations(sheet_rows(html_path, browser))


def main():
    data_base = _REPO_ROOT / "data_modularflavour"
    input_roots = [str(data_base / "text"), str(data_base / "text_notdone")]
    args = sys.argv[1:]
    if args:
        sources = args
    else:
        sources = sorted(
            name
            for root in input_roots
            for p in Path(root).glob("*.md")
            if "```mermaid" in p.read_text(encoding="utf-8",
                                           errors="replace")
            for name in (p.name,)
        )
    if not sources:
        print("no markdown sources with mermaid fences found")
        return

    debug_dir = Path(os.environ.get("TEMP", "/tmp")) / "cookbook_join_verify"
    gen = CookbookGenerator(input_dir=input_roots, temp_dir=str(debug_dir))
    browser = _get_browser()

    failures = []
    for md_name in sources:
        violations = verify_source(md_name, gen, debug_dir, browser)
        status = "FAIL" if violations else "ok"
        print(f"[{status}] {md_name}")
        for v in violations:
            print(f"    - {v}")
        failures.extend(f"{md_name}: {v}" for v in violations)

    if failures:
        print(f"\nADR 0017 VIOLATIONS: {len(failures)} "
              f"stranded intro(s) found")
        sys.exit(1)
    print("\nADR 0017 check passed: every diagram starts on its text's sheet")


if __name__ == "__main__":
    main()

