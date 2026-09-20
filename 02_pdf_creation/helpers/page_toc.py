"""
Table of Contents HTML Template Generator.

This module provides HTML templates for the table of contents page
in the same style as the recipe template.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import re

# Whole-word tokens dropped from displayed TOC titles (never from the
# source filenames themselves).
_NOISE_TOKENS = {"cookbook"}


def _clean_title(title: str) -> str:
    """Underscores read as spaces; standalone noise tokens dropped."""
    words = [w for w in title.replace("_", " ").split()
             if w.lower() not in _NOISE_TOKENS]
    return " ".join(words)


def display_parts(name: str) -> Tuple[str, str]:
    """Split a raw wiki name into ``(position label, display title)``.

    ``"_2.1.1.A. Ramen_Tare_Shio"`` -> ``("2.1.1.A", "Ramen Tare Shio")``.
    The leading underscore goes away, the position label keeps digits and
    letter suffixes but loses the trailing dot, and remaining underscores
    read as spaces. Names without a recognizable prefix return an empty
    label and the cleaned full name.
    """
    match = re.match(r"^_?(\w[\w.]*)\.\s+(.+)$", name)
    if match:
        return match.group(1).rstrip("."), _clean_title(match.group(2))
    return "", _clean_title(name)


# Deepest numbering level shown in the TOC: 1 -> "x." chapters, 2 -> "x.x."
# subsections (and chapter-level items like "3.1."). Entries numbered deeper
# ("x.x.x." and beyond) are omitted from the table of contents.
TOC_MAX_DEPTH = 2

# Max depth for the full TOC page rendered for the `_Annex.A.` back-matter
# page: effectively unlimited so every page in the book appears somewhere
# in the back matter.
FULL_TOC_MAX_DEPTH = 99


def _numbering_depth(name: str) -> int:
    """Numbering depth of an entry, counted from its position label.

    ``"_2.1.1.A. Ramen_Tare_Shio"`` -> 4, ``"_3.1. Vegan Chashu"`` -> 2.
    Names without a recognizable position label return 0 so they are
    always shown.
    """
    pos_label, _ = display_parts(name)
    return len(pos_label.split(".")) if pos_label else 0


def _entry_name(item: object) -> str:
    """Name of a hierarchy entry, which may be a dict or a plain string."""
    return item.get("name", "Untitled") if isinstance(item, dict) else str(item)


# Deepest numbering level shown in a chapter main page's sub-table of
# contents ("down to x.x.x.x.x"): 5 covers every page nested below a big
# chapter, e.g. "_2.2.4.1. Simple bread" (depth 4), with one level spare.
CHAPTER_TOC_MAX_DEPTH = 5


def clean_title_id(title: str) -> str:
    """Anchor id body for a page title: spaces and underscores read as
    dashes, then non-[a-z0-9-] chars stripped. Shared by the TOC pages and by
    page_content.py's default heading anchor, so wiki links always land on the
    page h1.
    """
    clean = str(title).replace(' ', '-').replace('_', '-').lower()
    return re.sub(r'[^a-z0-9\-]', '', clean)


def nest_entries_by_position(children: List[object]) -> List[Dict]:
    """Nest a flat list of hierarchy entries into a tree by position labels.

    The structure file encodes depth in the position labels themselves
    ("_2.2.4." precedes "_2.2.4.1." in book order), not by indentation. An
    entry becomes a child of the nearest previous entry whose label is
    shallower; label-less entries stay at the top level. Entries may already
    carry a flat child list (parser output: subsections hold their items);
    those lists are nested recursively by the same rules. The input list is
    left untouched - fresh copies carry the new 'children' lists.
    """
    roots: List[Dict] = []
    stack: List[Tuple[int, Dict]] = []
    for entry in children:
        name = _entry_name(entry)
        depth = _numbering_depth(name)
        if isinstance(entry, dict):
            node = dict(entry)
            existing = entry.get("children")
        else:
            node = {"type": "item", "name": name}
            existing = None
        node["children"] = (nest_entries_by_position(existing)
                            if existing else [])
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack and depth > 0:
            stack[-1][1]["children"].append(node)
        else:
            roots.append(node)
        if depth > 0:
            stack.append((depth, node))
    return roots


class TOCPageRenderer:
    """Render table of contents into HTML using the same A4 recipe template style."""

    def __init__(self):
        pass

    def render(self, title: str, sections: List[Dict],
               link_resolver=None) -> str:
        """
        Render a TOC page to HTML.

        Args:
            title: Page title (e.g., "Table of Contents")
            sections: List of section dicts with 'name' and 'items' keys
            link_resolver: Optional callable mapping a ``[[wiki reference]]``
                to a page anchor id; resolvable entries are emitted as
                ``a.wiki-link`` anchors so they flow through the shared
                internal-link mechanism (ADR 0004).

        Returns:
            Complete HTML page
        """
        toc_html = self._generate_toc_html(sections, link_resolver)

        return self._get_html_template().format(
            title=title, toc_content=toc_html,
            clean_title_id=clean_title_id(title))

    def render_full_toc(self, title: str, sections: List[Dict],
                        link_resolver=None) -> str:
        """Render an uncapped TOC page to HTML.

        Like ``render`` but shows every entry regardless of numbering depth,
        using the chapter sub-TOC hierarchy style so deep nesting stays
        legible. Used for the back-matter full TOC rendered for the
        `_Annex.A.` page.
        """
        html_parts = ['<div class="toc-hierarchy content-text">']
        for section in sections:
            section_name = section.get("name", "Untitled")
            if _numbering_depth(section_name) > FULL_TOC_MAX_DEPTH:
                continue
            # Include the section itself so its header renders in the hierarchy
            # at depth 1; nest_entries_by_position handles all descendants.
            nested = nest_entries_by_position([section])
            self._append_hierarchy_rows(html_parts, nested, link_resolver,
                                        FULL_TOC_MAX_DEPTH)
        html_parts.append('</div>')
        toc_html = "\n".join(html_parts)
        return self._get_html_template().format(
            title=title, toc_content=toc_html,
            clean_title_id=clean_title_id(title))

    def render_chapter(self, title: str, subtree: Dict,
                       content_html: str = '', link_resolver=None,
                       max_depth: int = CHAPTER_TOC_MAX_DEPTH) -> List[str]:
        """
        Render a chapter block as separate sheets, text before the sub-TOC
        (ADR 0015):
        Page 1: Chapter Title + Intro prose (only if content_html is non-empty)
        Page 2: Chapter Title + Sub-TOC

        Args:
            title: Page title (also anchors the page id on the h1)
            subtree: The chapter's section dict from the structure hierarchy
            content_html: Optional pre-rendered chapter intro prose
            link_resolver: Same contract as ``render``
            max_depth: Deepest numbering level shown (default 5: x.x.x.x.x)

        Returns:
            List of HTML pages (1 or 2 elements depending on content_html)
        """
        pages: List[str] = []

        # Page 1: Intro prose (only if there's content). The chapter text
        # opens the block so it can start on an even (left) page (ADR 0015).
        if content_html and content_html.strip():
            pages.append(self._build_chapter_intro_page(title, content_html))

        # Page 2: Chapter Title + Sub-TOC (opens the right-hand page)
        toc_html = self._generate_chapter_tree_html(
            subtree, link_resolver, max_depth)
        pages.append(self._build_toc_page(title, toc_html))

        return pages

    def _build_toc_page(self, title: str, toc_html: str) -> str:
        """Build a standalone TOC page with chapter title."""
        return self._get_html_template().format(
            title=title, toc_content=toc_html,
            clean_title_id=clean_title_id(title))

    def _build_chapter_intro_page(self, title: str, content_html: str) -> str:
        """Build a standalone intro prose page.

        The prose lives in a ``.content-text`` container so the splitter
        (ADR 0002) sees every paragraph as a flowable unit and rebuilds an
        overflowing intro onto continuation sheets instead of clipping it
        (ADR 0015). Interpolated directly (no ``str.format``) because
        markdown content may contain braces.
        """
        intro_content = (
            '<div class="chapter-intro-standalone content-text">'
            f'{content_html}</div>'
        )
        return self._get_html_template().format(
            title=title, toc_content=intro_content,
            clean_title_id=clean_title_id(title))

    def _entry_link(self, name: str, link_resolver) -> Tuple[str, Optional[str]]:
        """Return (inner HTML, target page id) for one TOC entry name.

        Resolution always runs on the *raw* name (page ids derive from it),
        while the printed text is the cleaned display form: a small greyed
        position label followed by the display title. Resolvable names
        become wiki-link anchors wrapping both spans (the
        ``.toc-entry-text`` span is what the leader/number measurement keys
        off); unresolvable ones stay plain text.
        """
        pos_label, title = display_parts(name)
        inner = f'<span class="toc-entry-text">{title}</span>'
        if pos_label:
            inner = f'<span class="toc-pos">{pos_label}</span>{inner}'
        if link_resolver is not None:
            page_id = link_resolver(name)
            if page_id:
                return (
                    f'<a class="wiki-link" href="#{page_id}">{inner}</a>',
                    page_id,
                )
        return inner, None

    def _generate_toc_html(self, sections: List[Dict], link_resolver=None,
                           max_depth: int = TOC_MAX_DEPTH) -> str:
        """Generate the main TOC as a hierarchy of accent rows.

        Each chapter prints as a full-width accent bar; its depth-2 entries
        (subsections and chapter-level items) descend beneath it as indented
        accent rows - the same level language the chapter sub-TOCs use, so
        the book's two navigation pages speak one visual hierarchy. Entries
        numbered deeper than ``max_depth`` are omitted.
        """
        html_parts = ['<div class="toc-main-toc content-text">']

        for section in sections:
            section_name = section.get("name", "Untitled")
            children = section.get("children", [])

            if _numbering_depth(section_name) > max_depth:
                continue

            pos_label, _ = display_parts(section_name)
            chapter_key = pos_label.split(".")[0] if pos_label else ""

            html_parts.append(
                f'<div class="toc-chapter-group toc-section" data-chapter="{chapter_key}">')

            sec_inner, sec_target = self._entry_link(section_name, link_resolver)
            tgt = f' data-toc-target="{sec_target}"' if sec_target else ''
            html_parts.append(
                f'<div class="toc-row toc-chapter-header"{tgt}>'
                f'{sec_inner}<span class="toc-page-num"></span></div>')

            if children:
                html_parts.append('<div class="toc-subsection-list toc-items">')
                for child in children:
                    if isinstance(child, dict):
                        child_name = child.get("name", "Untitled")
                    else:
                        child_name = str(child)

                    if _numbering_depth(child_name) > max_depth:
                        continue

                    if isinstance(child, dict) and child.get("type") == "subsection":
                        row_classes = "toc-row toc-subsection-row"
                    else:
                        row_classes = "toc-row toc-item-row"
                    html_parts.append(
                        self._row_html(child_name, row_classes, link_resolver))
                html_parts.append("</div>")

            html_parts.append("</div>")

        html_parts.append("</div>")
        return "\n".join(html_parts)

    def _row_html(self, name: str, row_classes: str, link_resolver) -> str:
        """One main-TOC row: full-width flex bar with cleaned entry text, an
        empty page-number rail, and a ``data-toc-target`` when the entry
        resolves (drives the leader-line / page-number injection, ADR 0004).
        """
        inner, target = self._entry_link(name, link_resolver)
        tgt = f' data-toc-target="{target}"' if target else ''
        return (f'<div class="{row_classes}"{tgt}>'
                f'{inner}<span class="toc-page-num"></span></div>')

    def _generate_chapter_tree_html(self, subtree: Dict, link_resolver,
                                    max_depth: int) -> str:
        """Beautiful hierarchical HTML for one chapter's sub-table of contents.

        Uses a clear visual hierarchy with:
        - Level 2 (subsections): Card-style headers with colored background
        - Level 3 (subsections): Left-accented rows with medium weight
        - Level 4+ (items): Indented with dot leaders
        """
        nested = nest_entries_by_position(subtree.get("children", []))
        html_parts = ['<div class="toc-hierarchy content-text">']
        self._append_hierarchy_rows(html_parts, nested, link_resolver, max_depth)
        html_parts.append('</div>')
        return "\n".join(html_parts)

    def _append_hierarchy_rows(self, html_parts: List[str], entries: List,
                               link_resolver, max_depth: int) -> None:
        """Emit rows for a nested chapter subtree with clear visual hierarchy.

        Level 1 (chapter): Prominent full-width bar
        Level 2 (subsections): Card-style section header
        Level 3 (sub-items): Medium-weight row with left accent
        Level 4+ (deep items): Indented with dot leader
        """
        for entry in entries:
            name = _entry_name(entry)
            depth = _numbering_depth(name)
            if depth > max_depth:
                continue
            inner, target = self._entry_link(name, link_resolver)
            tgt = f' data-toc-target="{target}"' if target else ''

            if depth == 1:
                html_parts.append(
                    f'<div class="toc-level-1 toc-section-header"{tgt}>'
                    f'{inner}</div>')
            elif depth <= 2:
                # Level 2: Card-style section header
                html_parts.append(
                    f'<div class="toc-level-2 toc-section-header"{tgt}>'
                    f'{inner}</div>')
            elif depth == 3:
                # Level 3: Medium-weight row with left accent
                html_parts.append(
                    f'<div class="toc-level-3 toc-subsection-row"{tgt}>'
                    f'{inner}</div>')
            else:
                # Level 4+: Indented with dot leader
                indent_class = f" toc-depth-{min(depth, 5)}"
                html_parts.append(
                    f'<div class="toc-level-4 toc-item-row{indent_class}"{tgt}>'
                    f'{inner}</div>')

            # Recurse into children
            self._append_hierarchy_rows(html_parts, entry.get("children", []),
                                        link_resolver, max_depth)

    def _get_html_head(self) -> str:
        """Shared page-document head: fonts, tailwind config and all sheet
        CSS. Ends inside ``<main>`` so any sheet body can be appended; every
        page type (TOC, chapter intro, parity blank) shares identical
        geometry (ADR 0015)."""
        return """<!DOCTYPE html>
<html class="light" lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>{title}</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="lib/fonts/fonts.css" rel="stylesheet"/>
<script id="tailwind-config">
    tailwind.config = {{
        darkMode: "class",
        theme: {{
            extend: {{
                "colors": {{
                    "surface-container-low": "#f1f4f2",
                    "on-secondary": "#edfee2",
                    "primary": "#47664a",
                    "secondary-fixed-dim": "#c9dabf",
                    "on-surface-variant": "#59615f",
                    "secondary-fixed": "#d7e8cd",
                    "inverse-on-surface": "#9b9d9c",
                    "secondary-container": "#d7e8cd",
                    "surface": "#ffffff",
                    "on-error": "#fff7f6",
                    "on-error-container": "#6e1400",
                    "surface-container-lowest": "#ffffff",
                    "outline": "#757c7a",
                    "background": "#ffffff",
                    "tertiary": "#5a6331",
                    "surface-variant": "#dde4e1",
                    "outline-variant": "#acb4b1",
                    "on-surface": "#2d3432",
                    "surface-container": "#eaefec",
                    "on-primary": "#e9ffe6",
                    "secondary": "#54634e"
                }},
                "fontFamily": {{
                    "headline": ["Manrope", "sans-serif"],
                    "body": ["Work Sans", "sans-serif"],
                    "label": ["Plus Jakarta Sans", "sans-serif"]
                }}
            }}
        }}
    }}
</script>
<style>
    .material-symbols-outlined {{
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    }}
    .recipe-page {{
        width: 210mm;
        height: 297mm;
        padding: 25mm 15mm 15mm 25mm; /* Top 25, Right 15, Bottom 15, Left 25 (= 15 base + 10mm book gutter) */
        box-sizing: border-box;
        background: #ffffff;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        position: relative;
        isolation: isolate;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }}
    @page {{
        size: A4;
        margin: 0;
    }}
    @media print {{
        html, body {{
            margin: 0;
            padding: 0;
            background: white !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }}
        .recipe-page {{
            margin: 0;
            box-shadow: none !important;
            border: none;
            page-break-after: always;
            break-after: page;
            page-break-inside: avoid;
        }}
        /* Multi-sheet documents stack vertically when printed. */
        main {{
            display: block !important;
            padding: 0 !important;
            min-height: 0 !important;
        }}
    }}
    /* ---- MAIN TOC: HIERARCHY ACCENT ROWS ---- */
    .toc-main-toc {{
        padding-left: 5mm;
    }}
    .toc-main-toc .toc-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.3rem 0.75rem;
        min-width: 0;
    }}
    /* Chapter bars: full-width accent bars (visuals unchanged from the
       editorial design; re-scoped to the flex rows). */
    .toc-main-toc .toc-chapter-header {{
        background: rgba(71, 102, 74, 0.08);
        border-left: 3px solid #47664a;
        border-radius: 0 4px 4px 0;
        padding: 0.5rem 0.75rem;
        margin-top: 1.25rem;
        margin-bottom: 0.5rem;
    }}
    .toc-main-toc .toc-chapter-header:first-child {{
        margin-top: 0;
    }}
    .toc-main-toc .toc-chapter-header .toc-entry-text {{
        font-family: 'Manrope', sans-serif;
        font-weight: 700;
        font-size: 1.05rem;
        text-transform: uppercase;
        letter-spacing: 0.02em;
        color: #2d3432;
    }}
    .toc-main-toc .toc-chapter-header .toc-pos {{
        background: rgba(71, 102, 74, 0.12);
        padding: 0.15rem 0.4rem;
        border-radius: 3px;
        color: #47664a;
        font-weight: 600;
    }}
    .toc-main-toc .toc-chapter-group {{
        margin-bottom: 1.5rem;
    }}
    /* Subchapter rows: depth-2 entries descend visibly under the chapter,
       speaking the chapter sub-TOC's level-3 accent language. */
    .toc-main-toc .toc-subsection-row,
    .toc-main-toc .toc-item-row {{
        background: rgba(71, 102, 74, 0.04);
        border-left: 3px solid #47664a;
        border-radius: 0 4px 4px 0;
        margin-left: 1.5rem;
        margin-top: 0.35rem;
        padding: 0.5rem 1rem;
    }}
    .toc-main-toc .toc-subsection-row .toc-entry-text,
    .toc-main-toc .toc-item-row .toc-entry-text {{
        font-family: 'Manrope', sans-serif;
        font-weight: 600;
        font-size: 0.9rem;
        color: #2d3432;
    }}
    .toc-main-toc .toc-subsection-row .toc-pos,
    .toc-main-toc .toc-item-row .toc-pos {{
        color: #47664a;
        font-weight: 600;
        font-size: 0.72rem;
        margin-right: 0.5rem;
    }}
    /* ---- CHAPTER SUB-TOC: CLEAR HIERARCHY ---- */
    .toc-hierarchy {{
        padding-left: 5mm;
    }}
    /* Level 1: Chapter headers - prominent full-width bar */
    .toc-hierarchy .toc-level-1 {{
        background: #47664a;
        color: #ffffff;
        padding: 1rem 1.25rem;
        margin-top: 2rem;
        margin-bottom: 0.75rem;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 2px 8px rgba(71, 102, 74, 0.25);
    }}
    .toc-hierarchy .toc-level-1:first-child {{
        margin-top: 0;
    }}
    .toc-hierarchy .toc-level-1 .toc-entry-text {{
        font-family: 'Manrope', sans-serif;
        font-weight: 700;
        font-size: 1.1rem;
        text-transform: uppercase;
        letter-spacing: 0.02em;
    }}
    .toc-hierarchy .toc-level-1 .toc-pos {{
        background: rgba(255, 255, 255, 0.2);
        padding: 0.15rem 0.4rem;
        border-radius: 3px;
        font-weight: 600;
        font-size: 0.72rem;
    }}
    /* Level 2: Section headers - card style with colored background */
    .toc-hierarchy .toc-level-2 {{
        background: linear-gradient(135deg, #47664a 0%, #3a553d 100%);
        color: #ffffff;
        padding: 0.75rem 1rem;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 2px 8px rgba(71, 102, 74, 0.25);
    }}
    .toc-hierarchy .toc-level-2:first-child {{
        margin-top: 0;
    }}
    .toc-hierarchy .toc-level-2 .toc-entry-text {{
        font-family: 'Manrope', sans-serif;
        font-weight: 700;
        font-size: 1rem;
        color: #ffffff;
    }}
    .toc-hierarchy .toc-level-2 .toc-pos {{
        background: rgba(255, 255, 255, 0.2);
        padding: 0.2rem 0.5rem;
        border-radius: 4px;
        color: #ffffff;
        font-weight: 600;
        font-size: 0.75rem;
        margin-right: 0.5rem;
    }}
    /* Level 3: Subsection rows - left accent with background */
    .toc-hierarchy .toc-level-3 {{
        background: rgba(71, 102, 74, 0.04);
        border-left: 3px solid #47664a;
        padding: 0.5rem 1rem;
        margin-left: 1.5rem;
        margin-top: 0.35rem;
        border-radius: 0 4px 4px 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .toc-hierarchy .toc-level-3 .toc-entry-text {{
        font-family: 'Manrope', sans-serif;
        font-weight: 600;
        font-size: 0.9rem;
        color: #2d3432;
    }}
    .toc-hierarchy .toc-level-3 .toc-pos {{
        color: #47664a;
        font-weight: 600;
        font-size: 0.72rem;
        margin-right: 0.5rem;
    }}
    /* Level 4: Item rows - indented with dot leader */
    .toc-hierarchy .toc-level-4 {{
        padding: 0.35rem 1rem;
        margin-left: 3rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-bottom: 1px dotted rgba(71, 102, 74, 0.15);
    }}
    .toc-hierarchy .toc-level-4 .toc-entry-text {{
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-weight: 400;
        font-size: 0.82rem;
        color: #59615f;
    }}
    .toc-hierarchy .toc-level-4 .toc-pos {{
        color: #9b9d9c;
        font-weight: 500;
        font-size: 0.68rem;
        margin-right: 0.5rem;
    }}
    /* Level 5+: Deeper items - more indented, smaller */
    .toc-hierarchy .toc-level-4.toc-depth-5 {{
        margin-left: 4.5rem;
    }}
    .toc-hierarchy .toc-level-4.toc-depth-5 .toc-entry-text {{
        font-size: 0.78rem;
        color: #757c7a;
    }}
    /* ---- SHARED STYLES ---- */
    .toc-page-num {{
        min-width: 24px;
        text-align: right;
    }}
    .toc-pos {{
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-weight: 500;
        font-size: 0.72rem;
        color: #9b9d9c;
        margin-right: 0.45em;
    }}
    /* ---- CHAPTER INTRO PAGE ---- */
    .chapter-intro-standalone {{
        padding: 0;
        font-family: 'Work Sans', sans-serif;
        font-size: 0.9rem;
        line-height: 1.6;
        color: #59615f;
    }}
    .chapter-intro-standalone p {{
        margin-bottom: 0.75rem;
    }}
    /* Same blockquote treatment as the content pages (page_content.py):
       chapter intros use their own stylesheet, so parity lives here. */
    .chapter-intro-standalone blockquote {{
        margin: 0 0 0.75rem 0;
        padding: 0.2rem 0 0.2rem 0.9rem;
        border-left: 2.5pt solid rgba(71, 102, 74, 0.55);
        font-style: italic;
        color: #59615f;
        break-inside: avoid;
        page-break-inside: avoid;
    }}
    .chapter-intro-standalone blockquote p {{
        margin: 0;
    }}
    /* Fix letter-spacing for h1 headers */
    h1.font-headline {{
        letter-spacing: normal !important;
    }}
</style>
</head>
<body class="font-body text-on-surface print:bg-white">
<main class="py-8 print:py-0 flex justify-center items-center min-h-screen w-full">"""

    def _get_html_template(self) -> str:
        """Assemble the TOC/sub-TOC page template from the shared shell and
        the title + content sheet body (placeholders: title, toc_content,
        clean_title_id)."""
        return (
            self._get_html_head()
            + """
<div class="recipe-page">
    <!-- Header Section -->
    <div class="flex justify-between items-start mb-6">
        <div class="flex-grow">
            <h1 class="font-headline font-extrabold text-[3rem] leading-none tracking-tighter text-on-surface mb-3" id="page-{clean_title_id}">{title}</h1>
                        <svg class="toc-title-underline" viewBox="0 0 1200 24"
                             preserveAspectRatio="none" style="width:100%; height:24px;">
              <line x1="4" y1="14" x2="1196" y2="14"
                    stroke="#47664a" stroke-opacity="0.55"
                    stroke-width="3" stroke-linecap="round"/>
              <line x1="8" y1="17" x2="1192" y2="17"
                    stroke="#47664a" stroke-opacity="0.3"
                    stroke-width="2" stroke-linecap="round"/>
            </svg>
        </div>
    </div>
    <!-- TOC Content -->
    <div class="flex-grow overflow-hidden">
        {toc_content}
    </div>
<div data-page-footer></div>
</div>
"""
            + self._get_html_tail())

    def blank_sheet_page(self) -> str:
        """Render one content-free parity sheet (ADR 0015).

        Shares the shell with every other sheet so geometry, fonts and the
        footer token match exactly, but carries no title, underline or
        content: the injected footer bar and global page number are its
        only print. The empty ``.content-text`` host keeps the splitter's
        container contract intact should the sheet ever be re-measured.
        """
        sheet = """
<div class="recipe-page">
    <div class="flex-grow overflow-hidden">
        <div class="content-text"></div>
    </div>
<div data-page-footer></div>
</div>
"""
        # The head is a .format() template ({{ }} CSS escapes, {title});
        # every other sheet type formats it during assembly. Forgetting
        # this here corrupts the whole combined group when the blank is
        # the first file converted (see combine_html_files: the first
        # file's head styles every page of the group PDF).
        return self._get_html_head().format(title="") + sheet + self._get_html_tail()

    def _get_html_tail(self) -> str:
        """Shared document tail closing ``<main>`` and the document."""
        return """
</main>
</body>
</html>"""


def render_toc_page(title: str, sections: List[Dict]) -> str:
    """Helper function to render a TOC page."""
    renderer = TOCPageRenderer()
    return renderer.render(title, sections)


if __name__ == "__main__":
    # Smoke test using the same hierarchy shape that
    # StructureParser.get_structure_hierarchy() returns.
    sections = [
        {
            "type": "section",
            "name": "Preface",
            "children": [
                {"type": "subsection", "name": "Introduction", "children": []},
            ],
        },
        {
            "type": "section",
            "name": "Architectures",
            "children": [
                {"type": "subsection", "name": "Bowl Systems", "children": []},
                {"type": "subsection", "name": "Noodle Families", "children": []},
                {"type": "item", "name": "Broth Basics"},
            ],
        },
        {
            "type": "section",
            "name": "Level-Up (Sauces)",
            "children": [
                {"type": "subsection", "name": "Chilli Crisp", "children": []},
            ],
        },
    ]
    html = render_toc_page("Table of Contents", sections)
    print(html)

    # Smoke assertions: the main TOC speaks the hierarchy-row design; no
    # three-column grid spans or SVG connectors remain. Inspect only the
    # rendered body markup, since the shared <style> block still references
    # the chapter sub-TOC classes (e.g. .toc-flavortree) for that other page
    # type.
    body_start = html.index('<body')
    body_html = html[body_start:]
    assert 'class="toc-main-toc' in body_html, (
        "main TOC missing .toc-main-toc container")
    assert 'class="toc-flavortree' not in body_html, (
        "main TOC still uses .toc-flavortree class on body elements")
    assert 'toc-connector' not in body_html, (
        "main TOC still emits .toc-connector SVG (removed with the grid)")
    assert 'toc-col-chapter' not in body_html, (
        "main TOC still emits three-column grid spans")
    assert 'toc-col-subchapter' not in body_html, (
        "main TOC still emits three-column grid spans")
    assert 'class="toc-row toc-chapter-header"' in body_html, (
        "main TOC missing chapter header rows")
    assert 'class="toc-row toc-subsection-row"' in body_html, (
        "main TOC missing subsection accent rows")
    print("smoke assertions OK")

    # Chapter main-page preview: intro page + sub-TOC page, written next to
    # this script for quick browser inspection.
    chapter = {
        "type": "section",
        "name": "_1. Architectures",
        "children": [
            {"type": "subsection", "name": "_1.1. Ramen", "children": [
                {"type": "item", "name": "_1.1.0. Ramen flowchart"},
                {"type": "item", "name": "_1.1.1. Ramen"},
            ]},
            {"type": "item", "name": "_3.1. Vegan Chashu"},
        ],
    }
    chapter_pages = TOCPageRenderer().render_chapter(
        "1. Architectures", chapter,
        content_html="<p>Chapter intro prose.</p>")
    preview_path = (Path(__file__).parent.parent / "debug"
                    / "chapter_toc_preview.html")
    preview_path.parent.mkdir(exist_ok=True)
    # Write the sub-TOC page (the block's last page)
    preview_path.write_text(chapter_pages[-1], encoding="utf-8")
    print(f"Chapter sub-TOC preview written to {preview_path}")
    # Write the intro page (pages[0]) if present
    if len(chapter_pages) > 1:
        intro_path = preview_path.with_name("chapter_intro_preview.html")
        intro_path.write_text(chapter_pages[0], encoding="utf-8")
        print(f"Chapter intro preview written to {intro_path}")
