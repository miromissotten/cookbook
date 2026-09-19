"""Verify the chapter spread parity (ADR 0015) on a shipped cookbook PDF.

For every chapter: the intro prose page must sit on an even physical page
(left-hand when printed) and the sub-TOC page on an odd page (right-hand).
Chapters without intro prose must open with their sub-TOC on an odd page.

Usage: python debug/verify_chapter_spread.py [path-to-pdf]
       (default: exports/Cookbook_digital.pdf)
"""
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]

# chapter title prefix -> has intro prose?
CHAPTERS = {
    '0. Cookbook Preface': True,
    '1. Architectural Recipes': True,
    '2. Carbohydrates': True,
    '3. Binding Agents': True,
    '4. Component Lab': True,
    '5. Annex Things': False,
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


def main() -> int:
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / 'exports' / 'Cookbook_digital.pdf')
    if not pdf_path.exists():
        print(f'ERROR: {pdf_path} not found (build the book first)')
        return 2

    texts = [norm(p.extract_text() or '') for p in PdfReader(str(pdf_path)).pages]
    failures = []

    for prefix, has_intro in CHAPTERS.items():
        # Chapter's own sheets: [intro?] sub-TOC, continuations.
        hits = title_hits(prefix, texts)
        if not hits:
            failures.append(f'{prefix}: title not found in {pdf_path.name}')
            continue
        first, second = hits[0], (hits[1] if len(hits) > 1 else None)
        if has_intro:
            if first % 2:
                failures.append(f'{prefix}: intro on p{first}, expected even')
            if second is None:
                failures.append(f'{prefix}: no sub-TOC page after intro')
            elif second % 2 == 0:
                failures.append(f'{prefix}: sub-TOC on p{second}, expected odd')
            else:
                print(f'OK {prefix}: intro p{first} (even), sub-TOC p{second} (odd)')
        else:
            if first % 2 == 0:
                failures.append(f'{prefix}: sub-TOC on p{first}, expected odd')
            else:
                print(f'OK {prefix}: sub-TOC p{first} (odd), no intro')

    if failures:
        for line in failures:
            print(f'FAIL {line}')
        return 1
    print(f'Chapter spread parity holds ({pdf_path.name})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
