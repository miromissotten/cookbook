# 0011 - Vertical sheets back-fill: instructions may start below ingredients

## Status

Accepted (amends ADR 0009)

## Context

ADR 0009's vertical recipe layout streams ingredient sections and
instructions as sequential bands, and the planner already continues across
streams mid-sheet. Yet multi-sheet recipes such as Carbonara show a large
void beneath the ingredients band: every unit height was measured in the old
side-by-side geometry (5/12 sidebar, 7/12 article) before the rebuild into
half-width columns, so planned fills drift from reality - ingredients render
shorter than planned - and the verification pass only shifts stragglers
downward, never upward.

## Decision

- **Backfill**: on vertical layouts, once a sheet's ingredient sections
  finish, instruction steps begin directly beneath them in that sheet's
  remaining space, under strict stacking: all ingredient items above any
  instruction step, steps sequential across sheets, and the Instructions
  heading never printed without at least one step beneath it.
- **Measure where you place**: unit heights are probed in the destination
  geometry (half-width band columns) before planning, removing the systematic
  drift instead of compensating for it afterwards.
- **Two-way verification**: the straggler pass gains a symmetric upward pull -
  after overflows settle, leading units of a following sheet move up into
  genuine gaps of the same band; never giants or diagram windows, never past
  the content limit, headings only together with a following unit.
- **Scope**: the recipe vertical path only. Side-by-side single-sheet recipes
  and generic content pages keep today's behaviour; ADR 0009's side-by-side
  ban stands.
- **Reported**: every recipe whose sheets share bands gets one backfill line
  in the generation report.

## Consequences

Multi-sheet recipes print denser: Carbonara-like voids disappear and some
recipes may lose a sheet entirely. Planning trusts probe measurements;
residual error is absorbed by the two-way pass, whose moves are bounded
(few iterations, epsilon-guarded) so packing terminates. Post-move column
balancing is approximate, mirroring the existing down-shift. Reading order
stays strictly top-to-bottom; nothing reintroduces side-by-side.
