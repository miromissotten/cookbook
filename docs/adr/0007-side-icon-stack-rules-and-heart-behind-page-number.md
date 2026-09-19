# 0007 - Side icon stack rules and the heart behind the page number

## Status

Accepted

## Context

The vertically stacked side icons on recipe pages had drifted: the difficulty icon printed horizontally squished, the stack as a whole was too small, `freezable` appeared both in the stack and in the list under the origin, the love heart occupied stack space although it is not a cooking trait, and servings were stated apart from the ingredient quantities they qualify. Each was small; together they made the page grammar fuzzy.

## Decision

- **Freezable**: `icon_freezable.png` joins the stack only when `freezable="yes"`; a "no" renders nothing, and the field never appears in the list below the origin.
- **Love level**: the heart leaves the stack entirely; at level 8+ it prints *behind the page number* of the recipe's first sheet, so a loved recipe is read as page-number-on-heart at every reference.
- **Group in words**: `Group: dish` / `Group: component` also appears as text alongside its icon.
- **Icon sizing**: stack icons enlarge; difficulty keeps its aspect ratio (scaled uniformly, never stretched). The group (dish/component), lactose-free and food-for-dating glyphs scale up to a 1.5rem fit box inside the 2rem backdrop so they read bigger while staying contained; the gluten-free ear is tall and narrow, so it takes a 1.75rem fit box, its deepest ink still landing about 2px inside the same rim.
- **Servings**: folded into the ingredients heading as `Ingredients (for x)` instead of a detached line.

## Consequences

The stack now answers exactly one question - intrinsic traits of this recipe at a glance - and nothing else. Affection lives where the eye already goes while navigating: the page number. Aligns the renderer with the `Love level`, `Freezeable` and `Servings` glossary entries; verified in the shipped rebuild of both variants.
