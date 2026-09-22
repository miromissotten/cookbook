# 0005 - Two entry points over a helpers package

## Status

Accepted

## Context

`automation/` (now `02_pdf_creation/`) had grown flat: twelve importable library modules sat beside the two runnable scripts, mixed with ad-hoc debug and one-off tools (`find_wiki.py`, leftover test scripts). Nothing told a future reader which files you *run* and which exist to be *imported*, and every new experiment deposited more debris at the root.

## Decision

- **Exactly two entry points** remain at the pipeline root: `main_generate_cookbook.py` (builds the book) and `main_generate_cookbook_structure.py` (regenerates the structure markdown). Everything else importable lives in `helpers/`.
- Entry points bootstrap `sys.path` themselves so they work regardless of the current working directory.
- The build embeds structure regeneration by importing the *same* `StructureGenerator` from the sibling script - a single source of truth, making the standalone structure run optional.
- One-off tools are deleted rather than accumulated; debugging needs are served by the dedicated `debug_split_one.py` / `debug_watch_temp.py` pair under `02_pdf_creation/debug/`, not by root litter.

## Consequences

"What do I run?" is answerable by listing one directory level. Library imports have a stable home (`helpers.*`), debug tooling has a sanctioned place, and the root cannot silently re-accumulate scripts. Renaming or moving internals now only ever touches `helpers/`.
