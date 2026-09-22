# 0002 - Continuation splitting with a unified in-page footer

## Status

Accepted

## Context

The book renders each source markdown file as a fixed A4 sheet. Pages whose
content was taller than the printable area collided with the footer: a
coordinate scan of `exports/Cookbook.pdf` found ~19 pages with body text below
the 25 mm design line, the worst 30+ words *under* the green footer line.
Chromium's margin-box footer made two things impossible:

1. It always paints on top of page content, so "footer behind an overlapping
   flowchart" could never work.
2. Its anchor position depends on label height, so long chapter—section names
   subtly shift the footer between pages.

Simply clipping content at the content limit would silently delete cooking
steps; native CSS fragmentation of this flex/grid poster layout is unreliable
(backgrounds do not repeat on continuation fragments, the 12-column recipe grid
breaks unpredictably, break points land mid-line).

## Decision

- **Generator-measured splitting**: render each page in the browser, measure
  real block heights, and rebuild overflowing sources as multiple complete
  sheets broken only at safe boundaries (instruction steps, sidebar sections,
  paragraphs/list items, TOC sections). Continuation sheets repeat just the
  title as an eyebrow strip.
- **Unified in-page footer**: Chromium's header/footer machinery is retired
  (`display_header_footer=False`, zero print margins). Every sheet embeds the
  same absolutely-pinned footer div, layered *behind* content
  (`z-index: -1` inside an isolated stacking context).
- **Giant blocks** too tall for one sheet's content area: vector diagrams
  (mermaid) are **sliced at 100% size** into horizontal bands that continue
  across consecutive sheets - the footer renders behind every band and labels
  stay at full print size. Non-sliceable blocks (rare list/section elements)
  get their own sheet, may overlap the footer band, and are only scaled when
  they cannot physically fit on the paper (floor 55%). Everything is reported.
- **TOC**: tall chapters are chunked at item level so the table simply flows;
  continuation strips name the *chapter* being continued rather than repeating
  "Table of Contents". Page count of the TOC is explicitly irrelevant.

## Amendment (after first printed review)

The originally accepted "scale-to-fit with floor 55%" produced illegible
~6 pt flowchart labels, and whole-chapter TOC sections became artificial
giants. Per review: diagrams slice at full size instead of shrinking, and the
TOC flows at item granularity with chapter-name continuation strips.
- **Global page numbers** stay as a ReportLab overlay applied after merging;
  they intentionally remain on the top layer.

## Consequences

Every sheet carries identical footer geometry regardless of label length;
overflow produces readable continuation sheets instead of collisions; nothing
is ever silently lost - splits, giants and scalings are listed in
`generation_report.md`. Conversion cost grows slightly (a measurement pass per
source page). The old hidden `.footer-container` mechanism is removed.

## Amendment (band placement, seams and bare continuations)

Post-review builds exposed three defect classes in how giant diagrams reach
paper, each fixed without changing the accepted model:

- **Bands are actually placed.** The splitter computed sliced bands, but a
  data-shape mismatch (`run.sliceParts` vs packed `{part}`) left the placement
  path dead: every band sheet stayed empty while the whole graph landed
  unclipped on the last one. Band placement is wired and now exercised on
  every build (flowchart page counts dropped accordingly).
- **No phantom title-only sheets; no false bake failures.** Mermaid fences
  were restored inside markdown `<p>` tags, so Chromium minted stray empty
  paragraphs claiming near-blank pre-diagram sheets; fences are emitted
  unwrapped. Separately, the bake pass raced the template's own mermaid
  auto-render and misreported already-rendered diagrams as failures; bake now
  recognises baked output and skips it.
- **Seam slivers and escaping labels.** A sliced diagram could lose a row
  sliver at a cut, and a label rect could fall outside its band window. Slices
  now guarantee every label maps fully inside exactly one band (printed once,
  never duplicated or clipped), and seam verification additionally runs at
  print level - real PDF ink paths - not only as a DOM audit.
- **Bare diagram-only continuations.** A continuation sheet whose entire
  content is sliced bands (or one giant block) omits the eyebrow title strip -
  repeating a title above pure artwork reads as noise. Sheets carrying flowing
  prose keep the strip; the check runs late in the DOM, so if the straggler
  pass ever moves prose onto a bare sheet, that sheet regains its title.
  Split-debug summaries report `HEADER / strip / BARE` honestly instead of
  inferring. Band windows reserve strip height up front, so re-adding a strip
  on mixed sheets cannot overflow.

## Amendment (content-page tables flow at row boundaries)

The icons-legend page (`_0.1`) exposed a packing gap: a table that did not fit
under its intro text was moved wholesale onto a fresh continuation sheet,
leaving a mostly empty first page and printing a repeated eyebrow title above
an intact table. Tables are now flowing units like list items and TOC
sections:

- **Row-chunking**: on content pages, any top-level table taller than ~420 px
  is rebuilt into row-chunk tables - each repeating the header row - so the
  packer starts it right after its intro text and continues remaining rows
  onto following sheets.
- **Never wholesale-moved**: tables no longer reach the unbreakable-giant
  path; they either fit where the flow places them or continue row-wise under
  the continuation strip, which stays because ordinary content genuinely
  continues there.
- **Compact table styling**: tighter cell padding and line-height on
  content-page tables (book-wide) keeps typical legend tables together with
  their text on one sheet in the first place, making the fallback rare.

