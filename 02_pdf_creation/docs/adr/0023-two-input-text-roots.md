# 0023 - Two input text roots: text and text_notdone

## Status

Accepted.

## Context

Page sources were split by the author into `data_modularflavour/text`
(finished) and `data_modularflavour/text_notdone` (work in progress). The
split is an authoring aid only: the published cookbook must contain both.
The build pipeline, however, discovered files from a single directory, so
after the split every `text_notdone` file silently dropped out of the
book and wiki links pointing at them became unresolved.

The per-recipe `text_description` metadata (the ✅/🔄/❌ status emojis in
the structure file) is independent of folder membership - both folders
contain a mix of statuses - so the folders must never be treated as a
status signal.

## Decision

- The build treats the two folders as one ordered, virtual input:
  `data_modularflavour/text` first, then `data_modularflavour/text_notdone`.
  Root order is precedence: a filename present in both folders resolves to
  the first root's copy, and shadowing is reported with a warning instead
  of happening silently.
- A single helper (`02_pdf_creation/helpers/input_roots.py`) owns root
  resolution, file lookup and markdown enumeration. The parser,
  structure generator, main generator, TOC tool and debug scripts all
  consume it; no component globs a single folder for page sources anymore.
- The structure file stays in the primary root (`text`) so Obsidian and
  structure auto-detection keep working unchanged.
- The merged file list is sorted by each file's numeric prefix, which is
  one global sequence across both folders, so book order is correct
  without any per-folder rules.
- `--input-dir` still overrides for one-off builds and now accepts a
  comma-separated list of directories.

## Consequences

- New builds include all pages from both folders by default; there is no
  "finished recipes only" build.
- Adding a third authoring folder later is a one-line change in
  `input_roots.DEFAULT_INPUT_DIRS` (plus `helpers/config.py`).
- Duplicate numeric prefixes across roots are warned about during
  structure generation instead of producing unpredictable ordering.
- Folder membership carries no meaning for status emojis; updating
  `text_description` metadata remains the way to change the ✅/🔄/❌ marks.
