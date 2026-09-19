# 0017 - Diagram joins its intro text: scale-to-join with slice fallback

## Status

Accepted. Narrows ADR 0002's giant placement for content-page diagrams; the
band/seam machinery and the full-size slicing rule are unchanged.

## Context

The splitter's two diagram paths behaved inconsistently about where a
flowchart starts relative to its intro text. Diagrams taller than a fresh
sheet slice into full-size bands whose first band joins the text sheet
(ADR 0002) - the Italian Emulsions flowchart (3.3.0) opens directly under its
sentence. A diagram that fits a fresh sheet whole, however, packs as an
ordinary flowing unit: the printed book showed the compact Italian Emulsion
Dishes flowchart (1.3.0) starting one page after its intro sentence,
stranding that sentence on a ~90% empty sheet. Whether a flowchart started
below its text was an accident of diagram height.

Slicing cannot fix the compact case: a diagram that nearly fits under its
text would slice into one large band plus a near-blank sliver sheet.

## Decision

- **Scale-to-join**: when the packer's sheet scan breaks at a sliceable
  diagram (an SVG-bearing unit) that fits a fresh sheet whole, and text was
  already packed on the current sheet, the diagram joins that sheet, scaled
  down just enough to fit the leftover space - never below the 0.80
  readability floor (the retired whole-page scale-to-fit used 0.55; vector
  labels stay sharp under a transform scale).
- **Slice fallback**: when even the floor would not fit (text nearly fills
  the sheet) and the leftover is at least a sliver band (80 px), the diagram
  slices at full size with band 0 joining the text - making "the diagram
  starts immediately below its text" unconditional for content pages.
- **Deferred joins are reported**: only a genuinely full sheet (leftover
  under a sliver band) still lets the diagram start the next sheet, and the
  generation report says so.
- **Scope**: content pages' sliceable SVG diagrams. Recipe-page wide blocks
  (ADR 0009) and non-sliceable images keep today's behaviour.
- Join-scaled diagrams are pinned like giants (`data-giant`): the straggler
  verification pass never pulls them onto another sheet.
- Every election is recorded: `join-scaled` lines plus a summary counter in
  the generation report; `debug/verify_diagram_join.py` asserts on a build
  that no stranded intro remains.

## Consequences

The 1.3.0 flowchart prints on one sheet with its diagram mildly scaled below
the sentence; 3.3.0, Ramen and Korean Rice flowcharts are unaffected (their
diagrams are taller than a sheet and keep full-size band slicing). Diagrams
never strand their intro text on a short sheet; the packer's behaviour no
longer depends on an accident of diagram height. A diagram may print up to
20% smaller than a sliced alternative would - accepted because the shrink is
bounded, vector-sharp, and buys a sheet without a near-blank tail.
