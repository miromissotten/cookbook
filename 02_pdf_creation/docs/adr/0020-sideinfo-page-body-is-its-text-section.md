# 0020 - A sideinfo page's body is its Text section

## Status

Accepted.

## Context

Sideinfo pages (the `- group: sideinfo` content page family, e.g. `_5.1.1. Miso.md`,
`_5.1.8. Furikake.md`, `_5.2.2. list_Ramen Toppings.md`) are hand-written
markdown structured as a stack of `###` sections: `### Title`, an optional
`### Description`, `### Text`, `### Side info` and `### Status info`. Section
order is arbitrary - `### Text` precedes `### Title` in some files, `### Description`
is last in others.

The pipeline's content-page path (`process_non_recipe_to_html`) passed the
**entire file** through `markdown_to_html`, so the printed pages showed the
authoring scaffolding itself: literal `### Side info` / `- group: sideinfo` /
`### Status info` lines appeared as prose beside the actual content, plus
authoring notes such as `==TO REREAD AND REWRITE==`. The heading was
filename-derived (`5.2.2. List Ramen Toppings`), which disagreed with the
authored title (`Toppings for Ramen`) that the author wrote for the reader.

## Decision

- **`### Text` is the page body.** A file that has a `### Text` section prints
  that section's raw markdown, and nothing else from the file. Sub-headings
  (`####`, `#####`), tables, bullet lists and mermaid fences inside it are
  preserved and rendered by the existing `markdown_to_html` pass.
- **`### Description` prints above it.** When authored, its value is prepended
  as a plain opening paragraph (blank-line separated), so the description reads
  as the page's lead sentence.
- **`### Title` is the heading**, printed with the filename's position label:
  `_5.1.1. Miso.md` + `- title: Miso` prints `5.1.1. Miso`, mirroring the recipe
  pages' `1.1.1. Ramen`.
- **Everything else never prints.** `### Side info`, `### Status info` and any
  stray authoring note stay out of the book, including on files that still lack
  a `### Text` section (they keep today's behaviour until the author adds one).
- **Detection signal is the `### Text` section itself**, not `- group: sideinfo`:
  strictly additive, so a content page that has not been converted yet cannot
  silently lose its prose (see `_3.4. Distinct Sauces.md`).
- **The page id derives from the authored title alone** (`page-miso`), never
  from the printed heading, so it stays independent of the position label. The
  wiki-link pre-scan resolves content pages through the same helper, keeping
  both ends of every `[[...]]` link consistent.

## Consequences

- The 12 sideinfo pages print only what they authored for the reader; the
  metadata stack disappears from the book.
- Content page ids for sideinfo pages change from filename-derived
  (`page-5-1-1--miso`) to title-derived (`page-miso`). Registration and
  rendering derive from one shared helper, so links cannot drift; the files
  live in chapter 5 and nothing else hard-codes these ids.
- The chapter sub-TOC entry text stays filename-derived (`5.2.2. List Ramen
  Toppings`), so a sideinfo page whose authored title differs may read
  differently in the sub-TOC than on its own sheet. A separate decision.
- `RecipeParser.parse_content_page` shares the description/continuation-line
  helper with the recipe parser, so both paths read a multi-line `- description:`
  identically.