# 0010 - Two-level ingredient model with options groups

## Status

Accepted

## Context

Most recipes list their ingredients as one flat, continuous list. Two
recipes - Kimbap&Sushi and Bibimbap - are modular by design: a fixed base
(nori sheets plus seasoned rice; rice) plus a menu of alternative toppings
from which the cook picks a few. Both sources announce that menu identically:
a top-level line starting with `...` ("...the rest of the toppings is up to
you, I suggest picking any 4 of the list..."), with the alternatives indented
beneath it, occasionally one level deeper still (sauce suggestions, notes on
individual toppings).

The ingredient parser models exactly two levels: the first line's indent
defines the top level, deeper items become sub-bullets of the current item.
So the options header itself parses as a bold pseudo-ingredient, and any
third-level detail flattens into the second level when printed.

## Decision

- **Two source levels**: Ingredients may nest one level deep. A top-level
  entry is a Base ingredient (always required); indented lines under it are
  its notes or its alternatives. Anything deeper flattens into the second
  level at render time - accepted behaviour, not a bug.
- **Options header**: a top-level Ingredients line starting with `...`
  announces an option group. Wording after the ellipsis stays free, and a
  pick count inside it ("any 4") is prose displayed verbatim, never parsed
  as data - same philosophy as time formulas.
- **Option group**: the indented alternatives below an options header are
  choices, not cumulative requirements.
- **No source migration**: both existing modular recipes already comply;
  no markdown files change.
- **Deferred styling**: today the options header prints bold like a base
  ingredient. Restyling it as a group label is deliberate future work in
  the recipe template, explicitly outside this decision.

## Consequences

Modular recipes print as base-plus-menu instead of a misleading flat
shopping list, and the "pick some" reading survives into the book. Deeply
nested details (Kimbap's sauce links, Bibimbap's spinach notes) surface one
level higher than authored; authors who mind the difference keep such
detail at the second level. The parser, splitter and layout election are
unaffected - options groups flow through band packing like any other list
items. When the deferred restyling lands, only the recipe template changes;
sources and this decision stand unchanged.
