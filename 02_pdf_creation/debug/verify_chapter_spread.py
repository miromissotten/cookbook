"""Verify the chapter spread parity (ADR 0015/0026) on a shipped cookbook PDF.

Per block shape:

- ``spread``: the intro prose sheet opens on an even physical page (left-hand
  when printed) and the sub-TOC sheet on the following odd page (right-hand);
- ``subtoc``: the chapter authored no prose, so its sub-TOC sheet opens on an
  odd page;
- ``text``: the chapter prints no sub-TOC sheet at all (ADR 0026), so its
  prose sheet opens on an even page - the pages that follow it face that
  sheet.

Usage: python debug/verify_chapter_spread.py [path-to-pdf]
       (default: exports/Cookbook_digital.pdf)
"""
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]

# Chapter title prefix -> expected block shape (ADR 0015/0026): 'spread'
# (intro prose even, sub-TOC odd), 'subtoc' (sub-TOC only, odd) or 'text'
# (no sub-TOC sheet, prose even). Back-matter blocks stay out of this map:
# Annex.A's full-TOC sheets already print one page more than the parity walk
# counts, which shifts the Outro's spread by one page (tracked separately).
# Chapter 5's source authors no prose yet (`_5. Curiosity Corner.md` is a
# blank file), so it prints its sub-TOC alone; switch it to 'spread' once
# that chapter gets its intro text.
CHAPTERS = {
    '0. Cookbook Preface': 'text',
    '1. Architectural Recipes': 'spread',
    '2. Carbohydrates': 'spread',
    '3. Binding Agents': 'spread',
    '4. Component Lab': 'spread',
    '5. Curiosity Corner': 'subtoc',
}


def norm(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


def title_hits(prefix: str, texts: list) -> list:
    """Pages whose extracted text STARTS with footer label + chapter title.

    The chapter's own sheets open with the footer chapter label followed by
    the h1 title, so the title sits within the first ~120 characters of the
    extracted text. Mid-page prose mentions of the chapter name are ignored.
    """
    hits = []
    for i, t in enumerate(texts):
        pos = t.find(prefix)
        if pos != -1 and pos <= 120:
            hits.append(i + 1)
    return hits


def check_shape(prefix: str, shape: str, hits: list) -> list:
    """Parity failures for one chapter's measured sheet positions.

    ``hits`` are 1-based physical pages whose text opens with the chapter
    title, in book order: a spread contributes its text sheet and then its
    sub-TOC sheet, a text-only chapter only its text sheet.
    """
    first = hits[0]
    if shape == 'text':
        if first % 2 == 0:
            return []
        return [f'{prefix}: text sheet on p{first}, expected even']
    if shape == 'subtoc':
        if first % 2:
            return []
        return [f'{prefix}: sub-TOC on p{first}, expected odd']

    failures = []
    if first % 2:
        failures.append(f'{prefix}: intro on p{first}, expected even')
    if len(hits) < 2:
        failures.append(f'{prefix}: no sub-TOC page after intro')
    elif hits[1] % 2 == 0:
        failures.append(f'{prefix}: sub-TOC on p{hits[1]}, expected odd')
    return failures


def main() -> int:
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / 'exports' / 'Cookbook_digital.pdf')
    if not pdf_path.exists():
        print(f'ERROR: {pdf_path} not found (build the book first)')
        return 2

    texts = [norm(p.extract_text() or '') for p in PdfReader(str(pdf_path)).pages]
    failures = []

    for prefix, shape in CHAPTERS.items():
        # Chapter's own sheets: [intro?] sub-TOC, or the text sheet alone.
        hits = title_hits(prefix, texts)
        if not hits:
            failures.append(f'{prefix}: title not found in {pdf_path.name}')
            continue
        chapter_failures = check_shape(prefix, shape, hits)
        failures.extend(chapter_failures)
        if not chapter_failures:
            print(f'OK {prefix} [{shape}]: sheets on '
                  + ', '.join(f'p{p}' for p in hits[:2]))

    if failures:
        for line in failures:
            print(f'FAIL {line}')
        return 1
    print(f'Chapter spread parity holds ({pdf_path.name})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
