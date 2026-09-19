# 0016 - Tightened uniform page geometry

## Status

Accepted

## Context

The book's sheets carried generous whitespace: recipe pages had 40 mm of
headroom, every page type padded 20 mm right / 30 mm left / 25 mm bottom, and
the footer band opened with a 5 mm blank strip. On a full page that left
~16 mm of air between the lowest text and the footer rule - space a dense
cookbook does not need - and recipe sheets padded differently from content
and TOC sheets. The 30 mm left margin existed to carry a 10 mm binding
allowance on top of the old 20 mm base margin.

## Decision

- **Uniform sheet padding** `25mm 15mm 15mm 25mm` (top/right/bottom/left) on
  every page type - recipe, content and TOC sheets share one rhythm.
- **Gutter preserved**: the left padding is 15 mm base + a 10 mm binding
  allowance, so margins are intentionally asymmetric. Do not "fix" this into
  symmetry - print binding eats the left edge of each sheet.
- **Footer band tightened**: the blank strip above the green rule shrinks
  5 mm → 2 mm; the band's label side padding mirrors the new sheet padding so
  the chapter—section label stays aligned with the text columns.
- **Content limit moves 25 mm → 15 mm** above the sheet's bottom edge
  (still enforced by splitting, never clipping).
- **Page number realignment**: the ReportLab overlay's right edge moves
  180 mm → 195 mm, the new right text edge (210 − 15 mm); the baseline stays
  at 11 mm and the favourite heart keeps its anchor behind the digits
  (ADR 0007).
- The splitter and the TOC leader rail measure the live DOM, so they adapt
  without code changes (ADR 0002's footer mechanism itself is unchanged).

## Consequences

Sheets hold more content: fewer continuation sheets, and the wider/taller
canvas can flip layout elections to the side-by-side recipe layout (ADR 0009).
The text-to-rule gap on a full page drops from ~16 mm to ~6 mm. Chapter
spreads and parity blanks re-paginate; both shipped variants must be rebuilt
and re-reviewed after the change.
