# 0021 - The description prints unlabelled

## Status

Accepted.

## Context

Recipe pages render the authored `- description:` as a quote block: italic
`text-on-surface-variant` prose with a `border-secondary-fixed-dim` left rule
(`_generate_description_html`). The styling already marks the paragraph as the
page's lead sentence, yet the block opened with a bold `Description:` prefix,
and the amber "missing description" stub repeated the same label before its
`TODO`.

Nothing read that label: no test asserts it, and the parser's diagnostics
(`no description -> TODO stub rendered`) and the sideinfo path never depended
on it. Sideinfo pages already open with the description as a plain, unlabelled
paragraph (ADR 0020), so the label made the two page families inconsistent and
printed a word the styling already says.

## Decision

- **The description quote block carries no label.** The authored value prints
  on its own inside the styled `<p>`; the italic quote formatting is what
  identifies it.
- **The missing-description stub carries no label either.** It reads
  `TODO — add a description` inside the amber box, which stays as the
  authoring-workflow marker.
- **The value is still inserted raw**, as before, so the wiki-link injection
  pass keeps resolving `[[...]]` targets in descriptions.

## Consequences

- Every recipe page's description is one label shorter, matching how a
  sideinfo page opens with its description.
- Removing the label may shorten the header when text wraps; existing
  browser-backed layout regressions pass with the change.
- `02_pdf_creation/icons_preview.html` mirrors the recipe header and was
  updated with the same change.
