# 0018 - Vendored print fonts and a font-readiness gate

## Status

Accepted

## Context

Every sheet template fetched its webfonts from
`fonts.googleapis.com` at conversion time. `document.fonts.status` - the
pipeline's only readiness signal - reports `loaded` even when a font fetch
*failed*: a face whose load failed is in `error` state, not pending. In one
build the fetch failed transiently for the pages of chapters 2 and 3, so
those sheets were printed with Chromium's fallback font (Segoe UI, embedded
as `/CAAAAA+SegoeUI` at 16.0 pt with content reaching x=583.3 pt) while
healthy pages embedded the webfonts (unnamed Type3 fonts at 14.4 pt,
content reaching x=548.3 pt). The result was visibly different text
formatting and margins for entire chapters, with no warning anywhere in
the run. The fallback was nondeterministic (any page of any run is
exposed) and chapter 4's sub-TOC continuation even mixed both fonts on one
sheet.

## Decision

- **Vendor the fonts**: the exact stack the sheets use (Manrope 200-800,
  Work Sans 300-500, Plus Jakarta Sans 400-600, Material Symbols Outlined
  variable) is fetched once from the css2 API into `lib/fonts/` with a
  rewritten local `fonts.css` and the licenses alongside. Sheet templates
  reference `lib/fonts/fonts.css` relatively - the same mechanism as
  `lib/mermaid.min.js` - so both entry points' existing recursive
  `lib/` copy into the working folder carries the fonts next to the
  sheets. Conversion no longer touches the network for fonts.
- **Font-readiness gate**: before printing, `_convert_single_to_pdf` runs
  `ensure_print_fonts`, which force-loads every declared face, requires
  all four families to be declared (catches a missing `fonts.css`),
  fails on any face in `error` state, and requires the Tailwind CDN
  object. On failure the page reloads once; a second failure refuses the
  conversion, routing the group to `Cookbook_PARTIAL.pdf` with a non-zero
  exit - the same contract as the seam gate (ADR 0002) and the link gate
  (ADR 0004). The gate runs before the navigation measurement pass so the
  measured geometry always belongs to the fonts that are printed.
- Tailwind stays on its CDN for now (`lib/tailwind.min.js` exists for a
  future swap); the gate still verifies its presence because a Tailwind
  failure would deform layout far worse than a font failure.

## Consequences

- Chapter-to-chapter typography is deterministic; the network can no
  longer change the book's look between runs.
- A genuinely offline machine now fails loudly into a partial build
  (fonts are local, but Tailwind is not) instead of shipping a deformed
  book - consistent with the pipeline's refuse-to-ship philosophy.
- `lib/fonts/` adds ~52 small woff2 files to the repo; the OFL/Apache
  licenses sit next to them.
- Font changes are now explicit repo changes: updating a family or weight
  means re-vendoring `lib/fonts/` (and the templates' tailwind font
  config) together.
