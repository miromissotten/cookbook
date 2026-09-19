# Zero-regression refactor notes (2026-09-09)

Scope: readability/maintainability only. **No business logic, layout, template,
CLI, or data change.** The pre-refactor state is commit `a082b85` (HEAD at the
time); every step below is reviewable against it.

## What changed

### 1. Characterization test suite (new `tests/`, stdlib `unittest` only)
No test framework existed. Added fast, browser-free tests that pin current
behavior *before* any refactor, so future edits are reviewable and revertable:

| File | Pins |
|---|---|
| `tests/test_page_toc_helpers.py` (9) | TOC title cleaning, display parts, numbering depth, position-based nesting, depth caps (ADR 0014/0015) |
| `tests/test_recipe_parser.py` (10) | Tolerant multi-shape parsing (ADR 0001/0012): verbatim time formulas, `/` origin omission, bad numeric fields ignored + warned, TODO-stub signal, numbered steps, variant labels, placeholder removal |
| `tests/test_structure_files.py` (7) | Structure generation round-trip (tempfile fixtures only; `data_modularflavour/text/` never touched) |
| `tests/test_report_extraction.py` (2) | Byte-equality of the extracted report helpers vs. the legacy inline methods |

Run: `python -m unittest discover -s tests` (28 tests). `pytest` is not
installed in this environment, hence stdlib `unittest`.

### 2. Import hygiene (behavior-neutral)
- Removed unused imports: `os` (`helpers/config.py`, `helpers/pdf_builder.py`), `Dict, List` (`helpers/page_content.py`).
- Hoisted function-local imports that duplicated module-top imports: `re` (`helpers/html_to_pdf.py`, `main_generate_cookbook_toc_subtoc.py`), `Path` (`html_to_pdf.py`), `base64` (`helpers/mermaid_renderer.py`), `NumberObject` into the existing `pypdf.generic` import (`helpers/link_injection.py`).
- Sorted stdlib import order in `helpers/page_renderer.py` and `helpers/html_to_pdf.py`.

### 3. Report extraction (one verbatim move, guarded by byte-equality test)
- `CookbookGenerator.write_generation_report` orchestration kept; the summary
  counting moved verbatim to `helpers/report_summary.py` (`summarize_diagnostics`)
  and the markdown rendering verbatim to `helpers/generation_report.py`
  (`render_report_markdown`). The old `_render_report_markdown` remains as a
  thin alias for compatibility. `tests/test_report_extraction.py` proves the
  extracted output is byte-identical to the legacy method, including pipe
  escaping and layout-tag exclusion.

## Deliberately NOT touched (regression risk wins)
- **Function-local imports kept where they are semantics, not sloppiness:**
  playwright in `html_to_pdf._get_browser` / `mermaid_renderer` (ImportError →
  friendly `RuntimeError` at call time; hoisting would break module import),
  `page_splitter` in `html_to_pdf` (soft dependency: the seam audit must never
  break conversions, ADR 0002), `pikepdf` in `pdf_builder.merge_pdfs`
  (optional dependency), `html_to_pdf` imports inside
  `mermaid_renderer._bake_mermaid_attempt` (genuine circular import:
  html_to_pdf ↔ mermaid_renderer), `StructureGenerator` lazy imports in both
  entry points, `argparse` in `main()`, conditional `markdown` in the
  TOC-only generator.
- Embedded splitting/measurement/injection JavaScript (`page_splitter.py`,
  `link_injection.py`, `html_to_pdf.py`), all CSS and page-number geometry
  (ADR 0015/0016), Playwright launch flags, pypdf merge + overlay order,
  `template_recipe.html`, public method/CLI signatures, `data_modularflavour/text/`,
  `data_modularflavour/icon/`, `debug/` scripts.
- `01_bulk_modification/` (Streamlit app): only compile-verified; its
  mid-file duplicate imports were left for its owner to avoid cross-cutting churn.

## Notes
- Since ADR 0023 the build reads page sources from the ordered roots
  `data_modularflavour/text` + `data_modularflavour/text_notdone`
  (`helpers/input_roots.py`); the `data_modularflavour/text/` mentions
  below are period records for that single-root era.
- `exports/generation_report.md` differs from HEAD only in nondeterministic
  mermaid element IDs (epoch timestamps) — a real build ran; structure and
  counts are identical. It is a per-run artifact, not a refactor side effect.
- A stale scratch snapshot `.refactor_backup_20260909/` (committed at some
  point; its `main_generate_cookbook.py` predates the ADR-0015 page-number
  config and matches neither HEAD nor the deleted `02_pdf_creation_20260905/`
  copy) was removed. It was tracked in git, so the removal is a reviewable
  working-tree change and the content stays recoverable from history; the
  true pre-refactor state remains commit `a082b85`.
- `docs/CONTEXT.md` is ubiquitous language, not a file map, so the new helper
  modules are documented here instead.
