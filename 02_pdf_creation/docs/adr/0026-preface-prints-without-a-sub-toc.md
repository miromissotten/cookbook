# 0026 - The preface prints without a sub-TOC sheet

## Status

Accepted.

## Context

Every chapter renders as a spread (ADR 0015): its intro prose on the even
(left) sheet and its sub-TOC - the deep flavour tree of every page nested
below it - on the odd (right) one. That pays off for the content chapters,
where the sub-TOC is the book's only map of a chapter's interior.

Chapter 0, `_0. cookbook_Preface`, has no interior to map: it carries two
entries (`0.1. Meaning of icons`, `0.2. Hypotheses & Sorries`) that print on
the two pages directly after it, so its sub-TOC sheet restated those pages
instead of helping a reader navigate - and it cost a sheet in the front
matter, where a reader is least willing to spend one.

The parity pass (ADR 0015) could not simply drop a sheet: it inferred a
block's shape from its sheet count alone (`has_intro = count >= 2`), so a
one-sheet text-only chapter was indistinguishable from a chapter that prints
only its sub-TOC.

## Decision

A chapter may print as *text-only*. `page_toc.SUBTOC_LESS_CHAPTERS` lists the
top-level position labels whose block carries no sub-TOC sheet, and
`chapter_prints_subtoc(subtree)` is the single rule the renderer and the
pipeline both ask:

- `render_chapter` returns the prose sheet alone for such a chapter - emitted
  even when the source authored no prose, so the block is never empty and its
  sheet count stays unambiguous;
- `_phase_assemble_jobs` records the shape with each chapter block, so the
  parity pass no longer infers it;
- the parity pass (`_chapter_anchor_sheets`) pins that prose sheet to the even
  (left) page - the side every other chapter's text opens on, so the chapter's
  first entry faces it from the right.

The key is the position label ("0"), never the title: retitling the chapter
cannot silently flip its block shape. Chapters that are not listed behave
exactly as before (text even + sub-TOC odd, or sub-TOC odd alone).

## Consequences

- The front matter loses one sheet, and the pages that follow the preface now
  face its text. The main TOC, its stamped page numbers and every internal
  link re-measure themselves from the merged PDF (ADR 0004), so they follow
  the new pagination automatically.
- `has_intro = count >= 2` is gone: a chapter block now carries its shape
  explicitly, which removes the ambiguity the third shape exposed.
- `debug/verify_chapter_spread.py` asserts one shape per chapter (`text`,
  `spread`, `subtoc`), and the chapter block shapes are pinned by
  `02_pdf_creation/tests/test_page_toc_helpers.py`, which is the deterministic guard for "no
  sub-TOC sheet" (a PDF text extraction cannot tell the two one-sheet kinds
  apart).
- Back-matter blocks stay outside that guard: the parity walk counts one
  sheet fewer than the book prints between the last chapter and the annexes
  (`sheet_count` reads the pre-print HTML, and one of those sheets prints two
  pages), so the Outro's spread lands one page off - its intro prints odd
  where the walk believes it even. That accounting gap is pre-existing and
  independent of this change.
