# 0014 - Main TOC speaks the sub-TOC hierarchy language

## Status

Accepted

## Context

The book has two navigation surfaces: the main TOC (all chapters, one page)
and each chapter's sub-TOC (the deep flavour tree on a chapter's first sheet).
They read as two different visual systems. The main TOC used a flat
three-column editorial grid (20% | 60% | 20%): chapter titles in the left
column, depth-2 subsections shifted one column right, deepest entries omitted.
The chapter sub-TOCs instead render a true nested tree of accent rows: a
chapter is a bar of green, its children hang below it as indented left-accented
rows, deeper levels step down further.

Printed reviews found the main TOC flat: the chapter-to-subsection parent
relationship was legible only as "one column over", never as ancestry, and a
manual grid cannot visually nest without also indenting.

Two machinery contracts constrain any restyle: the link-injection pass
(ADR 0004) stamps printed page numbers and leaders on every row carrying
`data-toc-target`, measured to a document-wide right-edge rail; the splitter
(ADR 0002) chunks tall TOC sections at item level and only breaks pages
between `.toc-section` wrappers.

## Decision

Restyle the main TOC as a hierarchy of accent rows - the sub-TOC's visual
language, not its full depth:

- Every chapter prints as a full-width accent bar, keeping the previous
  chapter-bar visuals (tint, left border, uppercase Manrope 700 title, position
  pill) and the page-number rail at the right edge.
- Depth-2 entries (subsections and chapter-level items) descend beneath their
  chapter as indented rows using the sub-TOC's level-3 styling: soft green
  fill, 3px left border, rounded right corners, Manrope 600.
- Depth scope stays at `TOC_MAX_DEPTH = 2`: the deep tree continues to live on
  the chapter sub-TOCs. The main TOC remains a scan-level map, not a
  duplicate of the chapter pages.
- Every row keeps `data-toc-target` and the `.toc-page-num` span, so ADR 0004
  keeps stamping leaders and numbers with zero measuring changes.
- The three-column grid and its `.toc-col-chapter` / `.toc-col-subchapter`
  spans are removed; the container is renamed `.toc-three-col` ->
  `.toc-main-toc`. The splitter's chunking contract (`.toc-chapter-group
  toc-section` with a `.toc-subsection-list toc-items` wrapper, direct-child
  rows) is untouched.

## Consequences

- The two navigation pages share one hierarchy language: a chapter bar with
  indented children on the main TOC, the same accent stepping on the chapters'
  sub-TOCs.
- Page numbers and leaders keep working exactly as before: the injection pass
  keys off row attributes and the rightmost row edge, both unchanged.
- The splitter logic needed no change; whole chapters still chunk at item
  level with nothing crossing the footer band.
- No sub-TOC styles changed: `.toc-hierarchy` keeps the dark-green level-2
  cards, which would shout if repeated six times on one TOC page.
- Renaming churn was contained: the smoke assertions in `page_toc.py`'s
  `__main__` and the generated debug previews were updated in the same change.
- Deliberately not done: showing depth-3+ entries on the main TOC. If later
  editions want the full tree on page one, this ADR's markup (row-shaped, no
  grid) already supports the extra levels.