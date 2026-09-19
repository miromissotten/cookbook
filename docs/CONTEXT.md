# Modular Flavour (Cookbook)

Glossary for the Modular Flavour cookbook project: hand-written markdown recipe sources in `data_modularflavour/text/` are rendered into an A4 PDF book by the automation pipeline in `02_pdf_creation/`.

## Language

### Pages

**Recipe page**:
A page built from a markdown source that contains Ingredients and/or Instructions; rendered with the dedicated A4 recipe layout.
_Avoid_: dish page

**Content page**:
Any non-recipe page (architectures, flowcharts, lists, structure files); rendered as generic prose - except for a sideinfo page, which prints only its Text section.

**Sideinfo page**:
A content page in the `group: sideinfo` family (reference pages, lists, explainers). It prints its `### Text` section, opened by its `### Description` when one is authored, under its `### Title` value plus the filename's position label ("5.1.1. Miso"). Its `### Side info` and `### Status info` blocks are authoring metadata and never print. A file without a `### Text` section still renders as a plain content page, so a page that has not been converted yet loses nothing.
_Avoid_: info page, side page, reference page

**Text section**:
The `### Text` section of a sideinfo page: the raw markdown printed as that page's body, sub-headings, tables, lists and diagrams included. Its presence is what makes a file a sideinfo page.
_Avoid_: body, content (the whole file is the source; this is the part that prints)

**Group**:
Top classification of a recipe: `dish` (complete dish) or `component` (building block used inside dishes). Drives the dish/component icon: `icon_dish.png` or `icon_component.png`.

**Subgroup**:
Refinement of Group, e.g. `main`, `sauce`, `broth`, `vegetables`.

### Side info fields

**Origin**:
Cuisine or country a recipe comes from (e.g. Japan), shown next to a map pin. `/` or empty means "no origin".
_Avoid_: location, cuisine

**Time formula**:
Active and waiting time, recorded and displayed verbatim, e.g. `(02h30) + 04h00`, `00h01`, `(00h20 * x) + 00h05`. In a formula, `x` means multiply by the number of people.
_Avoid_: prep time, duration

**Work after premade**:
Hands-on work remaining when components were made in advance.

**Servings**:
Base number of people the written quantities are for.

**Possible servings range**:
Reasonable min-max spread for scaling, e.g. `4-8`.

**Carbsource**:
Which ingredient provides the carbohydrates (e.g. noodles, rice, none).

**Freezeable**:
Whether the finished result can be frozen; shown as `icon_freezable.png` in the side icon stack when `yes`, and never as text below the origin.

**Love level**:
Miro's personal 0-10 rating of a recipe. At 8 or higher `icon_love.png` (the Favourite heart) is printed behind the page number of the recipe's first sheet, not in the icon stack.
_Avoid_: importance (that is Status info)

**Food for dating**:
Flag marking recipes suitable to cook on a date; shown as `icon_FoodForDating.png` when set to `True`.

**Difficulty**:
Stated cooking difficulty (`easy`, `medium`, `hard`); rendered as the stepped icons `icon_difficulty_1.png` / `icon_difficulty_2.png` / `icon_difficulty_3.png`, only when actually stated.

**Dietary restrictions**:
Per-flag markers (`glutenfree`, `lactosefree`, `vegan`, `vegetarian`); each renders its icon instead of text when set to `yes`: `icon_glutenfree.png`, `icon_lactosefree.png`, `icon_vegan.png`, `icon_vegetarian.png`.

**Sauce profile**:
The trio `sauce_flavour`, `sauce_consistency`, `sauce_usage` describing sauce characteristics (e.g. creamy · savory / heavy / spread · dip). On sauce pages it characterises the sauce itself; on all other pages it reads as a pairing guide for which sauce works well with the dish/component.
_Avoid_: buttons (chips are static printed labels)

**Sauce profile group**:
Single contained unit presenting a page's sauce profile as one element with the chips inside; labelled "Sauce profile" on sauce pages and "Sauce pairing" everywhere else.

### Ingredients

**Modular recipe**:
A recipe whose ingredients are a fixed base plus an option group from which
the cook picks a few (e.g. Kimbap&Sushi, Bibimbap). Printed with the option
group nested beneath its options header.
_Avoid_: architecture recipe

**Base ingredient**:
A top-level Ingredients entry that is always required for the dish. Indented
lines beneath it are notes about it, printed as sub-bullets.
_Avoid_: main ingredient

**Options header**:
The top-level Ingredients line starting with `...` that announces the option
group of a modular recipe. Wording after the ellipsis is free; any pick count
in it ("any 4") is prose shown verbatim. It is part of the recipe's voice,
not an ingredient.
_Avoid_: topping header, pick list

**Option group**:
The indented alternatives beneath an options header: choices to pick some of,
not cumulative requirements.
_Avoid_: toppings list, sub-ingredients

### Instructions

**Instruction variant**:
A named alternative procedure inside one recipe's Instructions section
(e.g. "lazy version", "impress-your-date version"). Printed as one headed
instruction block per variant: the label is the block's heading, its steps
follow beneath, and in the vertical recipe layout each variant gets a
full-width band of its own with two balanced columns - never mixed with
another variant's steps. Non-versioned recipes keep a single instructions
block; step numbers restart at 1 for each variant.
_Avoid_: version, method

**Heading-separated instructions**:
Instructions authored with subheaders instead of variant labels: the
shallowest heading level inside the section (e.g. `####` per-pizza variants)
opens one headed instruction block each; deeper headings (`##### Ingredients`,
`##### Instructions`) print as inline sub-headings inside their block.
_Avoid_: sub-block per subheading

**Step**:
One top-level action line in an Instructions section, printed with its number
in a green badge.

**Substep**:
An indented line beneath a step that details or conditions it; printed with its
own short green line, trimmed at the bottom, so each substep reads as a
separate point rather than part of one continuous rail. _Avoid_: sub-bullet
(that term belongs to ingredient notes)

### Sheet layout

**Sheet**:
One physical A4 page of the generated book: a fixed 297 mm tall box produced by the HTML templates. The unit the splitter reasons about.
_Avoid_: PDF page (ambiguous with physical pages after splitting)

**Footer band**:
Bottom zone of every sheet: green rule, uppercase chapter—section label, solid green bar. Rendered as part of the sheet itself, layered behind content.
_Avoid_: margin footer

**Gutter**:
The extra 10 mm binding allowance inside the sheet's left padding (left 25 mm vs right 15 mm); the reason sheet margins are intentionally asymmetric.
_Avoid_: spine margin, inner margin

**Content limit**:
The line 15 mm above the sheet's bottom edge; flowing content must never cross it. Enforced by splitting, not clipping.

**Continuation sheet**:
Extra sheet created when one source's content exceeds the content limit. Repeats the title as an eyebrow strip unless the sheet's entire content is diagram bands or another giant block; never repeats side columns like Ingredients.

**Giant block**:
Element too tall for a sheet's content area (typically a mermaid flowchart). Vector diagrams continue across consecutive sheets at full size as horizontal bands; other giants get their own sheet and may overlap the footer band, which paints behind them. Never clipped mid-sheet.

**Band**:
One horizontal slice window of a giant vector diagram: a fixed-height clip window showing a fixed row range of the diagram at 100% size. Bands tile the diagram row-for-row across consecutive sheets; band 0 may share its sheet with the title/intro text, later bands sit on continuation sheets.
_Avoid_: strip (that is the continuation sheet's eyebrow label)

**Scale-to-join**:
The measured election that keeps a content-page diagram on the same sheet as the text above it by mildly shrinking the diagram (never below the readability floor) instead of letting it start the next sheet and strand that text on a short page. When even the floor would not fit, the diagram slices at full size with its first band joining the text. Every election is recorded in the generation report.
_Avoid_: scale-to-fit (the retired whole-page shrink), join window (the leftover space a band may fill, not the election)

**Seam**:
The boundary where consecutive bands must meet: the next band resumes exactly at the row where the previous one stops. Zero lost rows at every seam is verified at split time and gated again at PDF conversion; a violation fails the build instead of shipping.

**Side-by-side recipe layout**:
The classic recipe arrangement: ingredients panel left, instructions column right. Legal only while a recipe's entire content fits one sheet; the moment it does not, the layout election switches the recipe to the vertical recipe layout. It also requires an authored Ingredients section: a recipe without one has no panel to print on the left, so the election never offers this layout.
_Avoid_: two-column layout (ambiguous - both recipe layouts use two columns)

**Vertical recipe layout**:
The arrangement for recipe pages that cannot print side by side: stacked
full-width bands, each across two balanced columns - the ingredient sections
(Ingredients, Hardware, Sauces) first, the instructions directly below. Bands
may share one sheet when space allows, always strictly stacked: no instruction
ever appears beside or above an ingredient. Used whenever one sheet does not
suffice, so ingredients and instructions are never printed side by side on a
multi-sheet recipe. Also used by every recipe that authored no Ingredients
section, even when it fits one sheet: there is no ingredients band at all, so
the instructions print full-width across the page instead of squeezed beside an
empty panel.
_Avoid_: stacked layout, fallback layout

**Ingredients section**:
The recipe's authored `### Ingredients` block, printed as the tinted left panel
of a side-by-side recipe. A recipe that authors no Ingredients section prints
none of it - no panel, no heading, no placeholder line - and its instructions
take the full page width in the vertical recipe layout.
_Avoid_: ingredients panel (that is the printed sidebar), ingredients list

**Layout election**:
The measured choice, made per recipe page, between the two layouts: render side-by-side, measure against the content limit; on overflow rebuild vertically - which may still land on that single sheet. A recipe without an Ingredients section elects vertical either way: side-by-side is never offered because the panel it needs does not exist. Every election is recorded per recipe in the generation report.
_Avoid_: fit test (that is only the measurement half)

### Navigation

**Wiki link**:
A reference written in source markdown as `[[Page]]` or `[[Page|shown text]]`, pointing at another page of the book. A wiki link whose target page does not exist in the book renders as plain text and is reported.
_Avoid_: internal link (that is the printed artifact), hyperlink

**Internal link**:
The clickable hotspot in a generated PDF that jumps to the first sheet of its target page. Present on every linked word and TOC entry in both shipped variants.
_Avoid_: wiki link (that is the source syntax)

**Page ID**:
The stable anchor identity of a page, derived from its title; the rendered sheet carries it and every wiki link targeting the page resolves through it. A heading that prints a position label ("5.1.1. Miso") still anchors the label-free id ("page-miso").

**Self link**:
A wiki link whose target is the page it appears on; rendered as styled, non-clickable text.

**Print version**:
The shipped PDF variant with visually unmarked internal links (`Cookbook_print.pdf`). Links work when clicked but look like normal text.
_Avoid_: clean version

**Digital version**:
The shipped PDF variant whose internal links are additionally underlined in the footer-green accent (`Cookbook_digital.pdf`), and which carries a `back to table of contents` footer link below the page number on every page from the main TOC onwards (ADR 0004 amendment).
_Avoid_: accent version

**Back-to-TOC link**:
The digital variant's small accent-green footer link below the page number, jumping to the main TOC's first sheet. Absent from the print version. _Avoid_: footer link (ambiguous), home link

**Position number**:
The dot-separated book-order label ("1.3.1", letters allowed, e.g. "2.1.1.A") shown small and greyed before a TOC title; mirrors the source filename prefix. _Avoid_: page number (that is the stamped target sheet).

**TOC display title**:
The cleaned title printed in the table of contents: leading underscore stripped, remaining underscores read as spaces, the standalone word "cookbook" dropped. Source filenames themselves never change.

**Main TOC**:
The book's overview table of contents: each chapter as an accent bar with its depth-2 entries (subsections and chapter-level items) descending beneath as indented accent rows. Deeper entries are listed on the chapter pages, not here. _Avoid_: table of contents (ambiguous with the chapter sub-TOC)

**Chapter sub-TOC**:
The deep flavour-tree listing on the sheet(s) directly after a chapter's intro text: every page nested below that chapter, stepped down by depth with gradient cards, accent rows and indented items. Opens on the odd (right-hand) page of the chapter spread. _Avoid_: sub-table of contents (skips the book's numbering language)

**Chapter spread**:
The chapter opening pattern: the chapter's intro text (if any) on the even (left-hand) page and its sub-TOC on the following odd (right-hand) page, enforced by inserting parity blanks where the natural flow would violate it. Chapter links land on the intro page, the block's first sheet. _Avoid_: chapter opener, chapter main pages

### Meta

**Status info**:
Authoring workflow metadata (text/design/sideinfo status, importance_to_miro). Never parsed for the printed book.

**Generation report**:
Per-run summary of everything the tolerant parser noticed (missing fields, odd time formulas, missing descriptions) and of the layout pass (splits, sliced diagrams and their seam checks, giant blocks, bake problems); printed to console and persisted next to the generated book.

### Build machinery

**Bake**:
The layout-pass step that turns embedded diagram source into fixed graphics before sheets are measured, so splitting and printing both see final geometry. Pages without diagrams pass through silently.
_Avoid_: pre-rendering

**Parity blank**:
A content-free sheet the pipeline inserts to keep chapter spreads on the correct page sides; it carries the standard footer band and a printed page number but no content (ADR 0015).

**Group PDF**:
One intermediate PDF holding consecutive pages that share a chapter—section footer label; groups are merged, in book order, into the final file.

**Working folder**:
Scratch location holding a build's intermediate sheets and group PDFs. Never part of the shipped book; defaults to a folder outside any synced tree (ADR 0003).
_Avoid_: exports/_temp (legacy location inside the vault)

**Partial build**:
A run whose group conversion did not complete; written to `Cookbook_PARTIAL.pdf` and reported as a failure instead of overwriting the good book.

**Font-readiness gate**:
Conversion-time check that a sheet's webfonts and Tailwind actually loaded before printing; on failure the sheet is reloaded once, then the group fails into a partial build instead of printing fallback-font pages (ADR 0018).

**Vendored fonts**:
The print families (Manrope, Work Sans, Plus Jakarta Sans, Material Symbols Outlined) stored in `lib/fonts/` and referenced locally by every sheet template, so conversion never fetches fonts from the network (ADR 0018).
