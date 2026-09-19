"""Reproduce the splitter's decision on a chapter main page.

Builds the _1. Architectures page exactly like the build pipeline does,
writes it to debug/repro_chapter.html, runs split_page_file() on it, and
inspects the resulting sheets (page count, row survival, measured heights).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))

from structure_parser import StructureParser  # noqa: E402
from page_toc import TOCPageRenderer, clean_title_id  # noqa: E402
from page_splitter import split_page_file  # noqa: E402

DATA_DIR = ROOT.parent / "data_modularflavour" / "text"
OUT = ROOT / "debug" / "repro_chapter.html"

parser = StructureParser(str(DATA_DIR))
hierarchy = parser.get_structure_hierarchy("_-1.0. cookbook_structure_generated.md")
chapter = next(s for s in hierarchy if s['name'] == "_1. Architectures")

# Mock resolver over real filenames (same rule as the wiki-link pre-scan).
titles = {md.stem.lower(): md.stem.replace('_', ' ').title()
          for md in DATA_DIR.glob("*.md")}


def resolver(ref):
    ref = ref.strip().lower()
    base = ref.lstrip('_').lstrip('0123456789.- ')
    for key in (ref, base):
        if key in titles:
            body = clean_title_id(titles[key])
            return 'page-' + body if body else None
    return None


prose = (DATA_DIR / "_1. Architectures.md").read_text(encoding="utf-8")
# minimal markdown->html for the repro (paragraphs only)
prose_html = "".join(f"<p>{p.strip()}</p>"
                     for p in prose.split("\n\n") if p.strip())

title = "_1. Architectures".replace('_', ' ').title()
pages = TOCPageRenderer().render_chapter(
    title, chapter, content_html=prose_html, link_resolver=resolver)
# pages[0] = intro page (if present), pages[-1] = sub-TOC page (ADR 0015)
html = pages[-1] if pages else ""
OUT.write_text(html, encoding="utf-8")
print(f"wrote {OUT} ({len(html)} bytes)")
print("rows in source:", html.count('data-toc-target'))

result = split_page_file(str(OUT))
print("split result:", result)

out = OUT.read_text(encoding="utf-8")
sheets = out.count('class="recipe-page"')
print("recipe-page sheets after split:", sheets)
rows = re.findall(r'data-toc-target="([^"]+)"', out)
print("rows after split:", len(rows))
# Write intro page if present (pages[0] under the ADR 0015 order)
if len(pages) > 1:
    intro_out = OUT.with_name("repro_chapter_intro.html")
    intro_out.write_text(pages[0], encoding="utf-8")
    print(f"wrote intro page {intro_out}")
print("first row:", rows[0] if rows else None,
      "| last row:", rows[-1] if rows else None)
missing = [n for n in ("_1.4.6. Udon", "_1.5.2. Pizza Napoletana")
           if not any(n[1:] in r for r in rows)]
print("expected deep rows missing:", missing or "none")
