# 0013 - Chapter sub-TOC intro must be packed, not a flex sibling

## Status

Superseded by 0015 (chapter spread: intro text on the left page, sub-TOC on
the right). The packed-intro placement described below was itself already
replaced by the two-sheet chapter block; 0015 now fixes both the sheet order
(intro first) and the page parity of those sheets.

## Context

Each chapter (0-5) renders a main page: prose intro above a deep sub-TOC of all
pages below it (fan-out by position label, down to `x.x.x.x.x`). The splitter
measures units inside the single `.content-text` container that is the column
model, then rebuilds overflow into continuation sheets (ADR 0002).

In the first version the chapter intro was emitted as a *sibling* of the
`.content-text` div, living in the page's `flex-grow overflow-hidden` wrapper.
The intro was therefore invisible to the packing pass: the splitter only saw
the subsection rows, judged the chapter to "fit" on one sheet, and left the
intro to overflow the flex box. At print time Chromium clipped the wrapper's
content exactly where it ran out of allocated height - on chapter 1 this
dropped every row after `1.3.4 Risotto` (`1.4.x`, `1.5.x`) while the splitter
insisted the page was within budget (a measure-vs-print gap reproduced in
`debug/probe_measure.py`: intro 456 px + tree 641 px + chrome ≈ 1121 px of
content in a ~812 px budget that the splitter never saw).

## Decision

`PageTOC.render_chapter` now passes the chapter prose into
`_generate_chapter_tree_html` as `intro_html`, which is emitted as the **first
child of the `.content-text` container**, before `.toc-chapter-group`. The
packing pass now sees the intro as a unit; chapters whose intro+rows exceed a
sheet split cleanly at safe TOC-section boundaries, and short chapters stay on
one sheet. This restores ADR 0002's contract that "everything that must flow
across sheets lives inside the measured container".

## Consequences

- Chapter 1's `1.4.x`/`1.5.x` rows and every other chapter's deepest rows now
  survive to paper; verified on `exports/Cookbook_digital.pdf` via
  `debug/verify_build_chapter.py` (all five chapters show their tail subsection
  markers, e.g. `1.4`/`1.5`, on the printed page).
- Long chapter pages split over multiple sheets (`debug/probe_measure.py`,
  `debug/repro_convert.py`, and the build report's group sheet counts) instead
  of silently clipping.
- The `.chapter-intro` rule carries the prose into the shared
  `.toc-flavortree content-text` flow, so it inherits the same left padding as
  the TOC spine and the same overflow/continuation behaviour. No splitter logic
  changed; only the template assembly order did.
- `debug/probe_measure.py`, `debug/repro_split.py` and
  `debug/repro_convert.py` document the measure-vs-print regression and the
  reproduction for future layout changes.
