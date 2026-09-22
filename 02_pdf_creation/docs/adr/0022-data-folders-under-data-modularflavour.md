# 0022 - Data folders live under data_modularflavour

## Status

Accepted.

## Context

The book's four data folders (`data_icons`, `data_externalsources`, `data_images`,
`data_text`) sat at the repository root next to the tooling folders. The `data_`
prefix is redundant inside a folder dedicated to data, and the root placement
stops a future second book module from reusing the same convention without
collisions.

Folder locations are hardcoded in a small, well-defined set of places: the path
constants in `02_pdf_creation/helpers/config.py`, the default `input_dir`
resolved by `CookbookGenerator`/`StructureParser`/`StructureGenerator`, the
asset search roots in `_build_file_uri` and `_get_icon_src`, the debug scripts'
`_REPO_ROOT` derivations, CLI defaults and help texts, one real-data test, and
one absolute path in the `01_bulk_modification` Streamlit config.

## Decision

- The four folders move into `data_modularflavour/` and drop the `data_` prefix:
  `data_text` becomes `data_modularflavour/text`, `data_icons` becomes
  `data_modularflavour/icon`, `data_images` becomes `data_modularflavour/images`
  and `data_externalsources` becomes `data_modularflavour/externalsources`.
- Every literal folder reference in code, CLI defaults, docstrings, comments,
  tests and living docs is updated in the same change. The asset lookup order in
  `_build_file_uri` (input dir, then images, then icons) is preserved.
- Obsidian wikilinks are untouched: they resolve by filename vault-wide (e.g.
  `[[sources_The_Book_of_Ramen.pdf]]`), so moving `data_externalsources` needs
  no markdown edits; the PDF pipeline never resolves those links on disk.
- Icon and image filenames keep their `icon_*` names; structure files unchanged.

## Consequences

- New builds read `data_modularflavour/text` by default; `--input-dir` still
  overrides for one-off builds.
- Machine-specific consumers point at the new location: the
  `01_bulk_modification` config now ends in
  `...kookboek_ModularFlavour\data_modularflavour\text`, and the absolute asset
  URIs in `02_pdf_creation/icons_preview.html` target
  `data_modularflavour/icon/`.
- A future book module gets its own `data_<book>/` sibling without collisions.
- Historical ADRs keep their original `data_*` mentions as period records.
