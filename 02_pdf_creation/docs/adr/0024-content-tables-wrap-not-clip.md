# 0024 - Content tables wrap their cells and never clip at the sheet edge

## Status

Accepted.

## Context

Content-page markdown tables are printed with the `.content-text table` styles in
`helpers/page_content.py`. That block pinned the first column with
`width: 1%` + `white-space: nowrap` - a pattern meant for short quantity-like
first columns (the "Meaning of icons" table). On tables whose first column
carries long labels, the nowrap forced the whole column - and therefore the
table - far past the sheet's content width (170 mm):

- `_5.2.2. list_Ramen Toppings.md` (8 columns) laid out at ~930 px inside a
  ~643 px content box. Chromium print has no horizontal continuation, and
  `.recipe-page` clips overflow, so the right-hand columns were silently cut
  off mid-header ("Savoury" printed as `s a v o`, "Crunchy" disappeared).
- The browser splitter (ADR 0002) only reflows *vertical* overflow; a
  horizontally overflowing table was invisible to it.

## Decision

- **Every table cell may wrap.** The first column loses `width: 1%` and
  `white-space: nowrap`; it behaves like any other column under the browser's
  auto table layout. Long first-column labels (topping names, dish names)
  word-wrap onto extra lines instead of widening the table. `text-align`
  moves from centered to left for readability of wrapped labels; images in
  the first column stay centered through the existing
  `td:first-child img { margin: 0 auto }` rule.
- **Headers are not given `white-space: nowrap`.** A single-word header
  ("Fermented") can never wrap anyway - its word width is the column's
  minimum - so 5.2.2's header row always prints on one line. Multi-word
  headers keep today's behaviour: they wrap only when the column physically
  cannot fit on one line (e.g. "Stabilisation method" on the Italian
  Emulsions table), which keeps every content table inside the printable
  width without any scale-to-fit machinery.
- The now-redundant `td:last-child { width: auto }` rule is removed.

## Consequences

- 5.2.2 prints all eight columns; its rows grow (table ~460 px -> ~719 px),
  which the splitter's existing row-chunking (header repeated per chunk)
  absorbs across its two sheets.
- Tables that already fit (Meaning of icons, Flour, Furikake, Potatoes) lay
  out pixel-identical; the Italian Emulsions table keeps its wrapped headers
  and gains only a slightly different first-column width share.
- The first column's alignment changes from centered to left on tables whose
  labels wrap. Revert `text-align` to `center` in one line if a future design
  pass prefers centered labels.
- The rejected alternative - `th { white-space: nowrap }` plus a splitter
  fit-to-width scale pass - would guarantee one-line headers everywhere but
  needs browser-measured scaling machinery for tables whose one-line headers
  exceed the sheet (Emulsions today: +13.7 px). Revisit if the author wants
  strict one-line headers for multi-word headers.
