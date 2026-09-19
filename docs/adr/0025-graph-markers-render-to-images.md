# 0025 - Graph markers render to images before layout

## Status

Accepted. Extends the `==GRAPH_<KIND>_START/END==` marker convention to recipe pages.

## Context

Sauce sources author their taste profile as a table of six 0-5 axes inside a
`==GRAPH_RADARGRAPH_START/END==` block, under a `### RadarGraph` heading - the
same marker convention `_1.5. Pizza.md` already uses for its `SCATTERPLOT`
block. Both carry a markdown pipe-table and both need a *picture* on the sheet
rather than a grid of numbers, because the whole point of the chart is to be
read at a glance without cooking the sauce first

The pipeline already had a path for this, and it did not cover the sauces. The
marker replacement lived in `markdown_to_html`, which serves content pages; a
recipe page is built from parsed data (`RecipeParser` -> `RecipeRenderer`) and
its template only ever fills known slots. Nothing parsed `### RadarGraph`, so
every authored radar table was silently discarded - the sources carried data the
book could not print.

Two shapes of the same task would have been needed if each marker kind kept its
own regex, its own working-folder logic and its own failure handling.

## Decision

- **One marker convention, one helper.** `_replace_graph_markers` owns the
  `==GRAPH_<KIND>_START/END==` regex, the working-folder PNG path and the
  warn-and-degrade behaviour; the per-kind entry points differ only by kind,
  renderer, alt text and image style. `SCATTERPLOT` and `RADARGRAPH` are two
  kinds over one implementation.
- **Graphs are rendered to PNG and printed as `<img>`.** Playwright already
  prints images correctly, and an image is a fixed block the splitter measures
  once, unlike an SVG that reflows.
- **A chart that fails to draw never fails the build.** The renderer is called
  inside a `try`, the reason is reported, and the page prints without the
  picture: on a content page the raw marker block stays visible instead of
  being silently dropped, so the fault is discoverable.
- **Presence follows the source.** The parser stores the authored table only
  when the block exists, and the renderer writes the chart's markup only when a
  picture was actually produced - no empty frame, no placeholder (the same rule
  ADR 0006 set for the sauce profile group).
- **The chart is drawn at its printed size.** `graph_radar.PRINT_WIDTH_MM` sizes
  the matplotlib figure and the generator's `<img>`; drawing at 3.4in and
  scaling down by CSS would have shrunk the axis names by half.
- **One parsing rule for the table**: a header row naming the axes plus exactly
  one numeric row. Extra rows are ignored (a chart draws one sauce) and a table
  whose axis and value counts disagree is rejected, because guessing which side
  is wrong would print a misleading shape.
- **The chart prints in the header, under the sauce profile chips** it explains,
  at a small fixed width - the recipe page's main grid keeps its columns.

## Considered Options

- A second marker kind with its own regex and its own failure path: rejected -
  two copies of the same work-folder and degradation logic.
- A mermaid radar diagram instead of matplotlib: rejected - mermaid has no
  radar type, and the book already refuses network calls at print time (ADR
  0018).
- Table of numbers instead of a chart: rejected - the sources ask for a radar
  graph, and reading six numbers per sauce defeats the purpose.
- Building the chart inside `RecipeRenderer`: rejected - the renderer has no
  working folder, and the generator is what owns the build's scratch space.

## Consequences

- A sauce page whose source carries a radar table now prints its taste profile
  as a chart; the sixteen authored sauces gain theirs with no source change.
- `graph_radar` joins `graph_scatterplot` as the second graph renderer; a new
  marker kind is now a renderer plus one call site.
- The recipe template gains a `{radar_block}` slot, which is the only layout
  change: the element sits inside the existing header between the chips and the
  header rule, and the browser-backed layout regressions pass unchanged.
- `RecipeRenderer.render_html` takes an extra optional argument, so every
  existing caller keeps working.
- Renaming `helpers/logging.py` to `helpers/console_logging.py` was required to
  land this: the module shadowed the stdlib `logging` that matplotlib, Pillow
  and reportlab import, which made every test importing the build modules fail
  at import time. The rename is what lets the graph renderers be tested at all.