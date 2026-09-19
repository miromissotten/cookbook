# 0006 - Sauce profile as one grouped element

## Status

Accepted

## Context

Recipe pages rendered `sauce_flavour`, `sauce_consistency` and `sauce_usage` as three loose chips in a flex row under the description. Because they looked like any other metadata, they read as three unrelated facts; the point of the trio - telling you what kind of sauce works with the dish - was invisible. They also appeared identically on clearly non-sauce pages (Hamburgers, Kumpir), amplifying the noise.

## Decision

- **One contained unit**: the three chips are wrapped in a single pill-style container, visually declaring "these belong together".
- **Context-dependent label**: the container is labelled `Sauce profile` on sauce-subgroup pages and `Sauce pairing` on every other page - on a dish it advises, on a sauce it describes.
- **Static printed labels**: chips are never interactive controls; this is a print-first book.
- **Presence follows the source**: the group renders when at least one of the three fields exists; individual chips appear only for present fields, and values print verbatim (including oddities like `thin (brine)`). No fields means no group.

Implementation lives centrally in the renderer's chip generation, so both recipe and content paths share it.

## Considered Options

- Interactive hover tooltips explaining each chip: rejected - the artefact is a printed book.
- A separate always-visible legend row: rejected - it decouples the explanation from the values and adds standing clutter.

## Consequences

Matches the `Sauce profile group` glossary entry in CONTEXT.md. Verified against a live build (Kumpir and Ramen Eggs render `Sauce pairing`, Aioli renders `Sauce profile`). Future sauce-related presentation extends the one wrapper instead of growing new loose rows.
