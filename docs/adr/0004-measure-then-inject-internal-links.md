# Measure-then-inject internal links

## Status

Accepted

## Context

Source pages use Obsidian `[[wiki links]]`. The render pipeline already turned them into `<a href="#page-id">` anchors and gave every sheet a matching heading id, but the anchors were dead in the shipped PDF: each group of same-footer sheets converts to its own PDF via Chromium, so an anchor only resolves for targets inside that same document - cross-group references (the majority) printed nothing clickable - and even intra-group GoTo annotations do not reliably survive the two pypdf rewrite passes (group merge + global page-number overlay).

Separately, the table of contents had neither links nor page numbers, although readers of the digital book expect both.

## Decision

- **Measure**: during each group's existing browser conversion pass we run a read-only `page.evaluate` under print media emulation, collecting every `a.wiki-link` client rect, every TOC row marked `data-toc-target`, and the first physical page of every `id="page-..."` anchor. Group start offsets are already tracked by the conversion loop, so document-local pages become global physical pages by construction.
- **Inject**: after the final merge and page-numbering, proper pypdf GoTo annotations are written onto the merged book, and ReportLab overlay packets draw TOC dot-leaders with printed page numbers (both variants) plus green accent underlines (digital variant only). The visual difference between variants therefore costs zero extra browser passes.
- **Two variants ship per build**: `Cookbook_print.pdf` (links invisible but clickable) and `Cookbook_digital.pdf` (accented); the unsuffixed `Cookbook.pdf` is retired.
- **Gate**: every measured link/row must resolve to an existing physical page or the run fails like a seam violation, writing `*_PARTIAL.pdf` instead of shipping broken books.
- Self-links (a page linking to itself) degrade to styled plain text; unresolved references keep degrading to reported plain text (ADR 0001 policy unchanged).

## Considered Options

- Trusting Chromium-emitted annotations and remapping destinations during merge: rejected - cross-group links are never emitted at all, and pypdf destination remapping across two rewrite passes was exactly the silent-failure class ADR 0002 eliminated elsewhere.
- Converting all sheets as one document so native anchors work: rejected - it would abandon group-wise footers and per-group font-subset embedding (large size regression).
- Rendering the digital variant by converting every group twice with styled HTML: rejected - doubles the slowest build stage; overlay-drawn accents achieve the same look from geometry already measured.

## Consequences

One conversion pass still serves both variants; underline position inherits the ~1 pt approximation of drawing at a rect edge rather than true text decoration. The measured page map becomes the project's contract for any future printed navigation aid (e.g. numbered TOC extensions), and injection runs must keep the gate: nothing ships with links that go nowhere.

## Amendment: back-to-TOC footer link (digital variant only)

The digital book additionally carries a small accent-green `back to table of contents` link in the footer band of every page from the main TOC's first physical page onwards: printed right-aligned on the page-number rail, in the band's empty right-hand slot directly below the printed page number, with a thin accent underline marking it clickable. A pypdf GoTo annotation over the label jumps to the TOC's first sheet. The title page and its verso blank stay clean; the print variant ships without any of it (paper has no use for a clickable link, and it would print as stray text).

- The TOC's physical page comes from the already-measured page map via the anchor `page-table-of-contents` (derived with `clean_title_id` from the shared `TOC_PAGE_TITLE` constant); no extra measurement is needed.
- Gate: if the digital variant ships and the TOC page is missing or out of range, the run fails like any other broken-navigation case.
