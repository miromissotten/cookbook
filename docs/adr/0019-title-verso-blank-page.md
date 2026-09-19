# 0019 - Title verso: a blank page after the title page

## Status

Accepted.

## Context

The book opens on the title page and immediately continues with the main
table of contents. A printed book conventionally gives the title page an
empty verso: the back of the title sheet stays blank, front matter starts
on a fresh page, and the TOC lands on a right-hand page of the spread.

Global page numbers, TOC page references and internal links are all
measured from the final merged PDF (ADR 0004), so the verso must be a real
sheet in the pipeline - it cannot be faked at print time.

## Decision

The build inserts one blank carrier sheet (ADR 0015's `blank_sheet_page()`)
as the second pdf job, between the title page and the main TOC:

- It carries the TOC's footer label (`Table of Contents`) and the standard
  footer band, and receives the global page number 2 - identical to every
  other blank carrier sheet (ADR 0015).
- Because it is a real sheet, the chapter-spread parity pass (ADR 0015)
  counts it; all later page numbers shift by exactly one and every parity
  decision recomputes automatically.

## Consequences

- The shipped book grows by one physical page; every later page number,
  TOC stamp and internal link target shifts by one (the measurement pass
  handles this by construction).
- The blank prints in both shipped variants (print and digital share the
  same paginated base).
- Chapter blocks still satisfy the ADR 0015 spread (intro even / sub-TOC
  odd); `debug/verify_chapter_spread.py` keeps guarding it.
