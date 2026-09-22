# Tolerant recipe parsing with a generation report

Recipe sources in `data_text/` are hand-written Obsidian notes whose Side-info blocks vary: parenthesised times (`(02h30) + 04h00`), single durations (`00h01`), multiplicative formulas (`(00h20 * x) + 00h05`), literal `???`, missing `group`, `/` as an empty origin. The original parser matched each block with one strict all-or-nothing regex, so a single deviation silently dropped the entire block from the rendered page (e.g. the Ramen page lost its origin). We decided to parse field-by-field, order-independently, rendering whatever parses, displaying time formulas verbatim, and surfacing every gap (missing core fields, non-standard shapes, missing descriptions, absent dietary sections) in a console summary plus a persisted generation report instead of failing the build.

## Considered Options

- Normalising all markdown files to a strict schema: rejected — the data is personal notes; enforcing format discipline on content creation was exactly the regime that produced silent data loss.
- Migrating Side info to YAML frontmatter: rejected for now — large churn across ~110 files and it breaks in-Obsidian readability habits without fixing the silent-failure class by itself.

## Consequences

- Missing information degrades gracefully per element (element omitted, visible amber TODO stub for missing descriptions) instead of vanishing whole blocks.
- Difficulty is never defaulted (no phantom 'easy' icon); unknown values simply show nothing.
- The generation report is the contract that nothing disappears unnoticed: any field label not known to the parser is reported as "unknown" instead of being ignored invisibly.
