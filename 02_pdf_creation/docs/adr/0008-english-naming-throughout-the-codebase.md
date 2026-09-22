# 0008 - English naming throughout the codebase

## Status

Accepted

## Context

Dutch `kookboek` and English `cookbook` were used interchangeably - module and script filenames (`main_generate_kookboek.py`, `kookboek_adapt_bulk.py`), identifiers (`obsidian_kookboek()`, `PATH_OBSIDIAN_PROJECTS_KOOKBOEK`), generated artifact names (`_-1.0. kookboek_structure_generated.md`, `kookboek_content_table*.md`), temp-dir prefixes and docs prose. Searching the project required remembering both spellings, and generated names were hardcoded in several generators, so drift was constant.

## Decision

- **`cookbook` / `Cookbook` / `COOKBOOK` everywhere**: filenames, Python identifiers, generated artifact names (renamed together with the generator defaults that emit them), working-folder prefixes (`cookbook_build_<pid>`, `cookbook_split_debug`) and documentation prose.
- **Preserved exceptions**, agreed explicitly:
  - the vault folder name `kookboek_ModularFlavour` itself - renaming it would break the open workspace, trigger a full Google Drive re-sync and invalidate hardcoded absolute paths;
  - legacy `[[03_projects/kookboek/...]]` wiki links pointing at locations outside this project;
  - archived binaries (`00_archive/layout_testing/kookboek.pptx`) and historical entries in `generation_report.md`, which is overwritten on every build anyway.

## Consequences

A case-insensitive search for `kookboek` returns only the whitelisted literals. Generated filenames and the code that writes/parses them changed in lockstep, so builds stay coherent. Git history (initialized for the rename) separates the mechanical rename from functional changes.
