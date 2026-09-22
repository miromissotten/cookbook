# 0015 - Chapter spread: intro text on the left page, sub-TOC on the right

## Status

Accepted. Supersedes 0013 (whose packed-intro placement was already replaced
by the two-sheet chapter block; this ADR fixes both the order and the page
parity of those sheets).

## Context

Each chapter renders as a block of separate A4 sheets - a title + sub-TOC page
and a title-eyebrow + intro prose page - which the splitter (ADR 0002) rebuilds
into continuation sheets whenever they overflow. Until now the sub-TOC printed
first and the intro second, so the chapter's text always opened on a right-hand
page. For a printed book that is wrong twice over: a reader flipping to a
chapter should land on text, and new sections conventionally open on the
left-hand (even) page of a spread so the sub-TOC faces them from the right.

Global page numbers, TOC page references and internal links are all measured
from the final merged PDF (ADR 0004), so the fix must insert real sheets into
the pipeline before measurement - blanks cannot be faked at print time.

## Decision

Chapter blocks become a *chapter spread*:

1. **Text before sub-TOC**: `render_chapter` emits the intro prose page first
   and the sub-TOC page second. Chapters without intro prose open directly
   with the sub-TOC.
2. **Parity pass**: after the layout pass (so continuation sheets count as
   real pages) the pipeline walks the book, counts sheets per job, and inserts
   blank carrier sheets until every chapter block satisfies: the intro's first
   sheet on an **even** page and the sub-TOC on an **odd** page. When an intro
   spans an even number of sheets, a blank is inserted between intro and
   sub-TOC so the sub-TOC still opens right; for no-prose chapters the blank
   (if needed) goes directly before the sub-TOC.
3. **Blank carrier sheets** are ordinary sheets without content: they carry
   the chapter's footer label, the standard footer band and a printed page
   number, and they ship in both variants (print and digital share the same
   paginated base).
4. **Splitting unchanged**: the intro page keeps its prose in a
   `.content-text` container, so a long intro flows onto continuation sheets
   like any other content page. Parity applies to first sheets only;
   continuations flow freely and are never clipped for pagination.

## Consequences

- Chapter links (main-TOC rows, `[[wiki link]]` anchors) now resolve to the
  chapter's **intro page** - the block's first sheet - instead of the
  sub-TOC; the measured TOC page numbers, leader lines and heart markers
  follow automatically.
- Every chapter block may grow by 0-2 blank sheets, shifting all later page
  numbers. How many blanks actually appear depends on measured sheet counts
  (the main TOC and sub-TOCs split into continuation sheets themselves); the
  generation report lists every insertion under a `parity:` info line.
- Both shipped variants paginate identically because they are built from the
  same merged, parity-corrected base.
- The intro page is now a flowable content page rather than a fixed block;
  its prose styling lives on `.chapter-intro-standalone` (the
  `.content-text` class is used purely as the splitter's container marker).
- `debug/verify_chapter_spread.py` asserts the spread on a shipped PDF
  (intro even / sub-TOC odd per chapter) as a regression guard for future
  layout changes.