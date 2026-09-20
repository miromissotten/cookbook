"""
Content Page HTML Template Generator.

This module provides HTML templates for non-recipe content pages
(like architecture pages, introductory content, etc.)
in the same style as the recipe template.
"""

from typing import Optional

from page_toc import clean_title_id


class ContentPageRenderer:
    """Render content pages into HTML using the same A4 recipe template style."""
    
    def __init__(self):
        pass
    
    def render(self, title: str, content_html: str,
               page_id: Optional[str] = None) -> str:
        """
        Render a content page to HTML.
        
        Args:
            title: Page title as printed in the heading
            content_html: Pre-rendered HTML content
            page_id: Anchor id for the heading; derived from ``title`` when
                omitted. Callers printing a numbered heading (e.g.
                "5.1.1. Miso") pass the unnumbered page's id, so the anchor
                always matches the wiki-link registry.
            
        Returns:
            Complete HTML page
        """
        # The caller owns page identity: a numbered heading ("5.1.1. Miso")
        # still anchors the unnumbered page id ("page-miso"). Without one the
        # anchor derives from the printed title via the shared rule.
        page_anchor = page_id or ('page-' + clean_title_id(title))
        
        template = self._get_html_template()
        template = template.replace('{title}', title)
        template = template.replace('{page_anchor}', page_anchor)
        template = template.replace('{content}', content_html)
        return template
    
    def _get_html_template(self) -> str:
        """Get the HTML template for content pages."""
        # Using placeholder replacement instead of format() to avoid conflicts with JS curly braces
        template = """<!DOCTYPE html>
<html class="light" lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>{title}</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="lib/fonts/fonts.css" rel="stylesheet"/>
<!-- Mermaid.js for diagrams -->
<script src="lib/mermaid.min.js"></script>
<script id="tailwind-config">
    tailwind.config = {
        darkMode: "class",
        theme: {
            extend: {
                "colors": {
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
                },
                "fontFamily": {
                    "headline": ["Manrope", "sans-serif"],
                    "body": ["Work Sans", "sans-serif"],
                    "label": ["Plus Jakarta Sans", "sans-serif"]
                }
            }
        }
    }
  </script>
<script>
    // Initialize mermaid with startOnLoad to auto-render <div class="mermaid"> elements
    mermaid.initialize({ 
      startOnLoad: true,
      theme: 'default',
      flowchart: { 
        useMaxWidth: true,
        htmlLabels: true,
        curve: 'basis'
      },
      securityLevel: 'loose'
    });
  </script>
<style>
    .material-symbols-outlined {
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    }
    .recipe-page {
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
    }
    @page {
        size: A4;
        margin: 0;
    }
    @media print {
        html, body {
            margin: 0;
            padding: 0;
            background: white !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }
        .recipe-page {
            margin: 0;
            box-shadow: none !important;
            border: none;
            page-break-after: always;
            break-after: page;
            page-break-inside: avoid;
        }
        /* Multi-sheet documents stack vertically when printed. */
        main {
            display: block !important;
            padding: 0 !important;
            min-height: 0 !important;
        }
    }
    .content-text {
        font-family: 'Work Sans', sans-serif;
        font-size: 0.9rem;
        line-height: 1.6;
        color: #2d3432;
    }
    .content-text h1 {
        font-family: 'Manrope', sans-serif;
        font-size: 1.5rem;
        font-weight: 700;
        margin-bottom: 1rem;
        margin-top: 1.5rem;
        color: #2d3432;
        letter-spacing: -0.02em;
    }
    .content-text h2 {
        font-family: 'Manrope', sans-serif;
        font-size: 1.1rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        margin-bottom: 0.75rem;
        margin-top: 1.25rem;
        color: #2d3432;
        border-bottom: 2px solid rgba(71, 102, 74, 0.3);
        padding-bottom: 0.25rem;
    }
    .content-text h3 {
        font-family: 'Manrope', sans-serif;
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        margin-top: 1rem;
        color: #59615f;
    }
    .content-text h4 {
        font-family: 'Manrope', sans-serif;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 0.35rem;
        margin-top: 0.75rem;
        color: #47664a;
        display: inline-block;
        border-bottom: 2px solid rgba(71, 102, 74, 0.4);
        padding-bottom: 0.125rem;
    }
    .content-text p {
        margin-bottom: 0.75rem;
        color: #59615f;
    }
    .content-text ul {
        margin-left: 1.5rem;
        margin-bottom: 0.75rem;
        list-style-type: disc;
        list-style-position: inside;
    }
    .content-text ol {
        margin-left: 1.5rem;
        margin-bottom: 0.75rem;
        list-style-type: decimal;
        list-style-position: inside;
    }
    .content-text li {
        display: list-item;
        margin-bottom: 0.25rem;
        color: #59615f;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.85rem;
    }
    .content-text code {
        background: #f1f4f2;
        padding: 0.125rem 0.25rem;
        border-radius: 0.25rem;
        font-size: 0.85em;
        color: #47664a;
    }
    /* Markdown blockquotes (pull quotes, callouts). Tailwind's preflight
       resets blockquote margins to zero, so an unstyled quote prints as a
       plain paragraph - this rule restores the visual treatment. */
    .content-text blockquote {
        margin: 0 0 0.75rem 0;
        padding: 0.2rem 0 0.2rem 0.9rem;
        border-left: 2.5pt solid rgba(71, 102, 74, 0.55);
        font-style: italic;
        color: #59615f;
        break-inside: avoid;
        page-break-inside: avoid;
    }
    .content-text blockquote p {
        margin: 0;
    }
    .content-text table {
        table-layout: auto;
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
    }
    .content-text table th {
        padding: 0.35rem 0.6rem;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #59615f;
        border-bottom: 0.5pt solid rgba(71, 102, 74, 0.4);
        opacity: 0.8;
        text-align: left;
    }
    .content-text table td {
        padding: 0.3rem 0.6rem;
        border-bottom: 1px solid rgba(116,124,122,0.15);
        font-family: 'Work Sans', sans-serif;
        font-size: 0.75rem;
        line-height: 1.35;
        color: #59615f;
    }
    .content-text table tbody tr:nth-child(even) td {
        background-color: #f1f4f2;
    }
    /* First column cells wrap like every other cell (ADR 0024): forcing
       them onto one line (width:1% + nowrap) pushed wide first columns -
       e.g. 5.2.2's topping names - past the sheet's content width, so
       Chromium print clipped the right-hand columns of the table. */
    .content-text table td:first-child {
        white-space: normal;
        text-align: left;
        vertical-align: middle;
    }
    .content-text table td:first-child img {
        display: block;
        margin: 0 auto;
    }
    .mermaid-diagram {
        margin: 1rem 0;
        padding: 1rem;
        background: #f1f4f2;
        border-radius: 0.5rem;
        overflow-x: auto;
    }
    .mermaid-diagram svg {
        max-width: 100%;
        height: auto;
    }
  </style>
</head>
<body class="font-body text-on-surface print:bg-white">
<main class="py-8 print:py-0 flex justify-center items-center min-h-screen w-full">
<div class="recipe-page">
    <!-- Header Section -->
    <div class="flex justify-between items-start mb-6">
        <div class="flex-grow">
            <h1 class="font-headline font-extrabold text-[3rem] leading-none tracking-tighter text-on-surface mb-3" id="{page_anchor}">{title}</h1>
            <div class="h-[2px] w-full bg-primary/20"></div>
        </div>
    </div>
    <!-- Content Section -->
    <div class="content-text flex-grow overflow-hidden">
        {content}
    </div>
<div data-page-footer></div>
</div>
</main>
</body>
</html>"""
        return template


def render_content_page(title: str, content_html: str) -> str:
    """Helper function to render a content page."""
    renderer = ContentPageRenderer()
    return renderer.render(title, content_html)


if __name__ == "__main__":
    # Test
    html = render_content_page(
        "Test Page",
        "<h2>Test Content</h2><p>This is a test.</p>"
    )
    print(html[:500])