# 0012 - Tolerant multi-shape instructions: every line prints

## Status

Accepted

## Context

Recipe Instructions were parsed by recognising "- " bullets only. Risotto -
numbered steps under two labels ("lazy version:", "impress-your-date
version:") - collapsed to a single glued pseudo-step starting with an
indented note; Red Wine Sauce parsed to zero steps and printed "No
instructions listed"; Hummus lost most of its steps; Aglio e Olio's three
version labels vanished into neighbouring text. The generation report could
not see any of it: absorbed or dropped lines left no trace, so the bug
survived multiple print runs silently.

Rewriting the sources into bullet lists was rejected: the numbered, labelled
shape is how recipes are naturally authored here, ten-plus pages already use
it, and ADR 0001 commits parsing to tolerance instead of authoring
discipline. The generic markdown library was rejected because recipe pages
render through the structured A4 template (numbered circles, ingredients
sidebar), not generic HTML flow.

## Decision

The Instructions section follows an absorb-all contract: every non-empty
source line maps to a block that prints.

- **Steps**: "- " bullets and "N." / "N)" markers alike; indentation beneath
  a step makes sub-notes, exactly as before.
- **Instruction variants** (CONTEXT.md): short non-sentence label lines (at
  most eight words, colon optional, no terminal punctuation) open a headed
  **instruction block**: every following step/sub-note belongs to that block
  until the next variant starts a new one, so a whole variant travels
  atomically through continuation splitting. Side-by-side recipes stack the
  headed blocks inside the instructions column; vertical layouts give each
  block its own full-width band across two balanced columns (ADR 0009).
  Step numbering restarts at 1 after each variant and after each verbatim
  sub-heading.
- **Sub-headings**: heading lines print verbatim. The shallowest heading
  level inside the section opens a headed instruction block; deeper levels
  stay inline inside that block, so Pizza Al Taglio's `####` per-pizza
  variants each own one block and their `##### Ingredients` /
  `##### Instructions` print as inline sub-headings within it instead of
  opening blocks of their own (which overwrote the variant name with
  "Ingredients" before any content arrived, losing it entirely).
- **Prose lead-ins**: every remaining line prints as a paragraph (Aglio e
  Olio's intro, Cacio e Pepe's preamble).
- **Empty placeholders**: a bare "-" carries nothing printable; it is dropped
  and reported as a warning, keeping even that removal non-silent.
- **Preamble**: content before the first variant/sub-heading prints in its
  own full-width intro band above the first block. Invariant: every
  instruction element belongs to exactly one stream - the
  ``data-instruction-intro`` marker marks the preamble and nothing else
  (instruction tables style themselves via a presentation class). Registering
  an element in two streams does not duplicate it: materialisation moves DOM
  nodes (appendChild, not clone), so the extra stream silently relocates it
  onto a later sheet, printing it after the steps that precede it.

Diagnostics ride the existing tolerant-parsing report path (ADR 0001). The
splitter additionally audits every rebuilt page: a planned instruction unit
that never printed, or instruction units printing out of source-stream
order, is reported as a ``warn`` line.

## Consequences

Risotto, Red Wine Sauce, Hummus, Pizza Al Taglio and friends regain their
full instruction text without touching a single source file; misparses can
no longer vanish unnoticed, because unknown shapes still print (as prose)
and placeholder drops are warned. The eight-word label heuristic becomes a
documented convention: sentence-like lines stay prose, short names open
headed blocks. The splitter builds one stream per instruction block, so a
version can never be split mid-way across a column balance nor share a
column pair with a neighbouring version; only a block taller than an entire
column spills onward, via the existing continuation machinery. The preamble
never shares a version's two-column band: it prints full width above the
first block - the Aglio e Olio preamble once printed mid-recipe on the
continuation sheet because a leftover duplicate stream registration moved it
there (placement appends, it does not clone).
