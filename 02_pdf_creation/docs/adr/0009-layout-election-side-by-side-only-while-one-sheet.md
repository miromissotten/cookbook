# 0009 - Layout election: side-by-side only while a recipe fits one sheet

## Status

Accepted

## Context

Every recipe page rendered with one fixed template: a 12-column grid with the
ingredients sidebar left (span 5) and instructions right (span 7). The ADR 0002
splitter treated those as two independent columns, so an overflowing recipe
kept the side-by-side arrangement on every continuation sheet: ingredients kept
living left, instructions right, page after page. Cooking from such a spread
means constant horizontal scanning across two parallel streams whose reading
order competes, and the narrow sidebar forces very long ingredient lists into a
tall sliver while instructions race past them.

## Decision

- **Layout election**: render the page side-by-side and measure it against the
  content limit (the existing browser-measured pass). Fits one sheet -> ship
  side-by-side, unchanged. Overflows -> rebuild the page as the **vertical
  recipe layout**: an ingredients band across two balanced columns first,
  further such bands for the instructions directly below - one per
  instruction variant where the recipe names them (ADR 0012). The election is
  recorded per recipe in `generation_report.md`. The vertical rebuild is
  allowed to rescue a recipe onto a single sheet - stacking two half-width
  bands can be shorter than one tall ingredients column.
- **Never side by side beyond one sheet**: once a recipe needs more than one
  sheet, ingredients and instructions are never printed side by side again.
- **Balanced halves, per sheet**: each sheet takes a greedy run of units that
  fits its budget, then distributes exactly that run over its two columns
  minimising the taller column (soft penalty when a section heading would
  strand at a column bottom). Step numbers carry the reading order, so
  balancing never confuses instruction sequence. One exception: a variant
  block whose sub-labels pair `Ingredients` -> `Instructions` (Pizza Al
  Taglio's `#####` headings) splits at that boundary - ingredients fill the
  left column, instructions the right - instead of height balancing, which
  would interleave the two. Pure step continuations of such a block (a sheet
  that starts past the boundary) balance normally.
- **Band membership**: the ingredients band streams Ingredients at list-item
  granularity (including its oversized-section continuation chunks, whose
  cloned headings repeat the band label and are suppressed inline); Hardware
  and Sauces stay WHOLE sections - their few items are meaningless detached
  from their short heading, and item-level streaming let the balanced columns
  / verification passes tear them apart and print the pieces at mismatched
  heights (Bibimbap's hardware split). An ingredients-band continuation sheet
  carrying only such whole sections prints headless: the sections carry their
  own h2. Each instructions band streams the whole steps of one instruction
  block.
  Header zone (title, origin, side info, description, profile chips, icon
  stack) is untouched and full-width in both layouts.
- **Wide blocks**: mermaid diagrams and oversized images break out and span
  both instruction columns at 100% size, reusing the existing slicing /
  band / seam machinery (ADR 0002); squeezing them into a half-width column
  would resurrect the illegibility the scale-to-floor amendment removed.
- **Continuations**: eyebrow title strip as today; a band's section heading
  repeats on every sheet where that band's items appear. The ingredients band
  keeps the tinted panel look, spanning both columns.

## Consequences

Multi-sheet recipes read top-to-bottom instead of left-right across competing
columns, and tall ingredient lists use the full text measure. The splitter's
recipe branch grows a second packing model (sequential balanced bands beside
the content/TOC column packer); the old aside-chunking path became dead code
and was removed. Election lines ("side-by-side"/"vertical") join the layout
summary of the generation report. Column balancing relies on numbered step
badges for cross-column reading order; un-numbered prose steps would lose
strict sequence guidance.

## Amendment (recipes authoring no Ingredients section)

The election assumed every recipe page has a sidebar to print on the left.
Recipes that author Instructions but no `### Ingredients` section broke that
assumption: their sidebar was rendered empty (a tinted panel carrying only a
"No ingredients listed" placeholder) and, because the page still fitted one
sheet, the election kept the side-by-side arrangement - instructions squeezed
into a 7-column sliver beside a panel with nothing in it.

- **No Ingredients section, no sidebar**: a recipe authoring no Ingredients
  section renders no `<aside>` at all - no panel, no heading, no placeholder
  line. Hardware/Sauces data, if ever authored, prints as a full-width block
  instead.
- **Vertical by construction**: the article carries a `data-vertical-recipe`
  marker and spans all 12 grid columns. The splitter recognises the marker,
  counts such a page as a recipe page without a sidebar, and never offers the
  side-by-side layout: fitting pages elect vertical without a rebuild; on
  overflow they rebuild through the ordinary vertical band machinery with no
  ingredients stream and no ingredients band.
- **Election reporting**: a fitting no-ingredients page reports a `vertical`
  election in `generation_report.md` exactly like a rebuilt one, so the report
  never claims a side-by-side layout that was not printed.
- The marker keys on the rendered attribute, not on re-parsing the markdown:
  the election stays a single measured pass over the page as printed.
