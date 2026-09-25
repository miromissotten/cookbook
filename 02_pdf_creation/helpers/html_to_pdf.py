"""
HTML to PDF converter for recipe files.
Converts an HTML recipe file to PDF using the A4 template.
Uses Playwright for reliable HTML to PDF conversion with browser reuse for performance.
"""

import html
import os
import re
from html.parser import HTMLParser
from pathlib import Path

# Use nest_asyncio to allow Playwright sync API inside asyncio loop
import nest_asyncio
nest_asyncio.apply()

from config import (
    PAGE_LOAD_TIMEOUT_MS,
    PAGE_W_PT,
    PAGE_H_PT,
    PX_TO_PT,
    A4_WIDTH_MM,
    A4_HEIGHT_MM,
    PAGE_BOX_SHADOW,
    PAGE_BG,
    PAGE_SIZE,
    PAGE_BREAK_AFTER,
    RENDER_SETTLED_TIMEOUT_MS,
    FORCE_DEVICE_SCALE_FACTOR,
    VIEWPORT_WIDTH,
    VIEWPORT_HEIGHT,
    COLOR_PRIMARY,
    COLOR_ON_SURFACE,
    COLOR_ON_SURFACE_VARIANT,
    COLOR_PRIMARY_RGB,
)

from typing import List, Optional

# Import mermaid renderer functions at module level to avoid import issues in async contexts
from mermaid_renderer import get_browser as get_mermaid_browser, set_browser as set_mermaid_browser

# Global browser instance for reuse
_browser = None
_playwright = None

def _get_browser():
    """Get or create a reusable browser instance."""
    global _browser, _playwright
    
    if _browser is not None:
        return _browser
    
    # First, check if mermaid_renderer already has a browser we can share
    mermaid_browser = get_mermaid_browser()
    if mermaid_browser is not None:
        _browser = mermaid_browser
        return _browser
    
    try:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
        # Force device scale factor to 1 to avoid Windows DPI scaling shrinking PDF content.
        _browser = _playwright.chromium.launch(args=[f'--force-device-scale-factor={FORCE_DEVICE_SCALE_FACTOR}'])
        # Share this browser with mermaid_renderer so both use the same instance
        set_mermaid_browser(_browser)
        return _browser
    except Exception as e:
        raise RuntimeError(
            f"Cannot initialize Playwright. Original error: {e}"
        )


def _close_browser():
    """Close the global browser instance."""
    global _browser, _playwright
    
    if _browser is not None:
        _browser.close()
        _browser = None
    # The shared-browser handoff must not outlive the browser it points at,
    # or the next _get_browser() hands back the closed instance (seen when
    # one test class closed the browser and a later class asked for it).
    set_mermaid_browser(None)
    if _playwright is not None:
        _playwright.stop()
        _playwright = None

PAGE_LOAD_TIMEOUT = PAGE_LOAD_TIMEOUT_MS

# Marker element embedded in every sheet template; replaced with the real
# in-page footer right before conversion. Must be a plain element (not a
# comment) so it survives the HTMLParser-based combiner. Chromium's serializer
# rewrites the bare attribute to data-page-footer="", so match both shapes.
_PAGE_FOOTER_RE = re.compile(
    r'<div\s+data-page-footer(?:\s*=\s*"[^"]*")?\s*/?>')


def count_footer_tokens(html_text: str) -> int:
    """Number of page-footer tokens (bare or `="") in ``html_text``."""
    return len(_PAGE_FOOTER_RE.findall(html_text))


def _path_to_uri(path_str: str) -> str:
    """Properly encoded file:/// URI for a Windows path (spaces, '&', ...)."""
    return Path(path_str).resolve().as_uri()


def wait_for_render_settled(page) -> None:
    """Wait until webfonts and any client-side mermaid rendering have settled."""
    try:
        page.wait_for_function("() => document.fonts.status === 'loaded'", timeout=RENDER_SETTLED_TIMEOUT_MS)
    except Exception:
        pass
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('.mermaid').length === 0 || "
            "document.querySelectorAll('.mermaid svg').length > 0",
            timeout=RENDER_SETTLED_TIMEOUT_MS
        )
    except Exception:
        pass


# Probe executed in the page (ADR 0018). document.fonts.status cannot detect
# failed webfont fetches - a face whose load failed is in 'error' state, not
# pending, so status reports 'loaded' while Chromium prints a fallback font.
# Font faces also only load lazily when the page uses them, so per-weight
# check() calls false-negative on unused weights. The probe therefore
# force-loads every declared face (local files: cheap), requires all four
# families to be declared (catches fonts.css not loading at all), fails on
# any face in 'error' state, and checks the Tailwind CDN object.
_FONT_PROBE_JS = """async () => {
    const required = ['Manrope', 'Work Sans', 'Plus Jakarta Sans',
                      'Material Symbols Outlined'];
    const faces = [...document.fonts];
    await Promise.all(faces.map((f) => f.load().catch(() => {})));
    const declared = new Set(
        faces.map((f) => f.family.replace(/["']/g, '')));
    const missing = required.filter((fam) => !declared.has(fam));
    for (const f of faces) {
        const fam = f.family.replace(/["']/g, '');
        if (f.status === 'error' && !missing.includes(fam)) {
            missing.push(fam);
        }
    }
    if (typeof tailwind === 'undefined') { missing.push('tailwind'); }
    return missing;
}"""


def ensure_print_fonts(page) -> bool:
    """Return True when the sheets' webfonts and Tailwind actually loaded.

    Reloads the page once when the probe finds missing assets; a second
    failure (or a probe/reload error) returns False so the caller refuses
    to print fallback-font pages instead of shipping deformed sheets
    (ADR 0018).
    """
    missing = None
    for attempt in range(2):
        try:
            missing = page.evaluate(_FONT_PROBE_JS)
        except Exception as exc:
            print(f"Warning: font readiness probe failed ({exc})")
            missing = ["probe-error"]
        if not missing:
            return True
        if attempt == 0:
            try:
                page.reload(wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
                wait_for_render_settled(page)
            except Exception as exc:
                print(f"Warning: font reload failed ({exc})")
                return False
    print("Warning: print fonts not settled after one reload, missing: "
          + ", ".join(str(m) for m in missing))
    return False


def inject_page_footer(html_text: str, footer_html: str) -> str:
    """Bake the group's footer into every sheet carrying the footer token."""
    if not footer_html:
        return html_text
    return _PAGE_FOOTER_RE.sub(lambda _m: footer_html, html_text)

def _convert_single_to_pdf(input_file: str, output_file: str, footer_html: Optional[str] = None, retry_count: int = 0,
                           measure_cb=None, measure_result=None) -> bool:
    """Convert one HTML file to PDF.

    When ``measure_cb`` is given (with ``measure_result`` as its output
    list), the loaded page is handed to it for read-only geometry collection
    (ADR 0004) right before printing. Measurement failures never fail the
    conversion itself - the injection gate catches missing data later.
    """
    if not os.path.exists(input_file):
        print(f"Error: File not found: {input_file}")
        return False
    
    page = None
    load_path = input_file
    footer_tmp = None
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            text = f.read()
        token_count = count_footer_tokens(text)
        # Local import: page_splitter imports this module at load time, so
        # a module-level import here would be circular (same pattern as the
        # seam-audit import further down).
        from page_splitter import count_sheets
        sheet_count = count_sheets(text)
        if token_count != sheet_count:
            print(f"Warning: footer token count ({token_count}) does not match "
                  f".recipe-page count ({sheet_count}) in {os.path.basename(input_file)}")
        # In-page footers live inside the sheet markup behind a token; bake the
        # group's footer into a temp copy so the original stays reusable.
        if footer_html:
            injected = inject_page_footer(text, footer_html)
            if injected != text:
                footer_tmp = input_file + '.footertmp.html'
                with open(footer_tmp, 'w', encoding='utf-8') as f:
                    f.write(injected)
                load_path = footer_tmp
        
        browser = _get_browser()
        page = browser.new_page(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}, device_scale_factor=FORCE_DEVICE_SCALE_FACTOR)

        # Convert the absolute path to a proper encoded URI (handles spaces and special chars)
        input_path_obj = Path(input_file).resolve()
        
        # Build file URI with proper handling of special characters
        # Replace problematic characters that break file:// URIs on Windows
        path_str = str(input_path_obj)
        # Replace & with %26, # with %23, etc.
        path_str = path_str.replace('&', '%26').replace('#', '%23').replace('?', '%3F')
        input_uri = f"file:///{path_str}"
        
        # Also encode the parent directory for base tag
        parent_path_str = str(input_path_obj.parent)
        parent_path_str = parent_path_str.replace('&', '%26').replace('#', '%23').replace('?', '%3F')
        input_dir_uri = f"file:///{parent_path_str}"

        # Load the HTML file using the proper URI with increased timeout
        page.goto(_path_to_uri(load_path), timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")
        
        wait_for_render_settled(page)

        # Font-readiness gate (ADR 0018): document.fonts.status cannot see a
        # failed webfont fetch, which silently printed sheets in a fallback
        # font with different metrics (chapter 2/3 margins incident). Reload
        # once; refuse the sheet if the required families and Tailwind are
        # still unavailable - the caller routes the group to
        # Cookbook_PARTIAL.pdf and the run exits non-zero.
        if not ensure_print_fonts(page):
            print(f"Error: required webfonts unavailable for "
                  f"{os.path.basename(input_file)}; refusing to print "
                  f"fallback-font pages")
            page.close()
            page = None
            return False

        # Seam integrity gate (ADR 0002): a sliced diagram whose bands do
        # not meet row-for-row would silently lose a sliver of the diagram
        # in print. Refuse the conversion; the caller routes the group to
        # Cookbook_PARTIAL.pdf and the run exits non-zero.
        try:
            from page_splitter import audit_page_seams
            seam_violations = audit_page_seams(page)
        except Exception as exc:  # the audit must never break conversions
            print(f"Warning: seam audit skipped ({exc})")
            seam_violations = []
        if seam_violations:
            for violation in seam_violations:
                print(f"SEAM VIOLATION in {os.path.basename(input_file)}: "
                      f"{violation}")
            page.close()
            page = None
            return False

        # Navigation-geometry measurement (ADR 0004): read-only pass over the
        # settled, print-media layout before the PDF is printed.
        if measure_cb is not None and measure_result is not None:
            try:
                measure_result.append(measure_cb(page))
            except Exception as exc:
                print(f"Warning: navigation measurement failed on "
                      f"{os.path.basename(input_file)}: {exc}")

        # Footer is part of the sheet markup (pinned, behind content); the
        # physical page box is exactly A4 with zero print margins.
        page.pdf(
            path=output_file,
            width=f'{A4_WIDTH_MM}mm',
            height=f'{A4_HEIGHT_MM}mm',
            print_background=True,
            display_header_footer=False,
            margin={'top': '0mm', 'bottom': '0mm', 'left': '0mm', 'right': '0mm'}
        )
        
        page.close()
        page = None
        return True

    except Exception as e:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        
        # Retry once for timeout errors
        if retry_count == 0 and ("Timeout" in str(e) or "timeout" in str(e)):
            print(f"Retrying {input_file} after timeout...")
            return _convert_single_to_pdf(input_file, output_file, footer_html, retry_count=1,
                                          measure_cb=measure_cb, measure_result=measure_result)
        
        print(f"Error converting {input_file}: {e}")
        return False
    finally:
        if footer_tmp and os.path.exists(footer_tmp):
            try:
                os.remove(footer_tmp)
            except Exception:
                pass


def _merge_head_markup(heads: List[str]) -> str:
    """Union of several sheets' <head> inner markup into one shared head.

    The first clean head donates everything; every other clean head
    contributes only the <style>/<link> elements the base does not already
    carry (whitespace-normalized dedupe), inserted before the closing
    </head>. Scripts are deliberately not merged: the page templates share
    an identical script head (verified: tailwind CDN, lib/mermaid.min.js,
    tailwind-config, inline init are byte-equal across page types), so the
    base's copy must not run twice. Returns '' for an empty list.
    """
    if not heads:
        return ''
    base = heads[0]
    element_re = re.compile(r'<style\b.*?</style>|<link\b[^>]*>', re.S | re.I)

    def elements(text: str) -> List[str]:
        return [re.sub(r'\s+', ' ', m).strip() for m in element_re.findall(text)]

    seen: set[str] = set(elements(base))
    extras: List[str] = []
    for other in heads[1:]:
        for el in elements(other):
            if el not in seen:
                seen.add(el)
                extras.append(el)
    if not extras:
        return base
    idx = base.rfind('</head>')
    if idx == -1:
        return base + '\n' + '\n'.join(extras)
    return base[:idx] + '\n' + '\n'.join(extras) + '\n' + base[idx:]


def combine_html_files(html_files: List[str], output_file: str = None) -> str:
    """
    Combine multiple HTML files into a single HTML document.
    
    Each HTML file is expected to have an <main class="a4-page"> element.
    These elements are extracted and combined with CSS page breaks.
    
    Args:
        html_files: List of HTML file paths to combine
        output_file: Optional path to save the combined HTML file
        
    Returns:
        Path to the combined HTML file (or memory string if output_file is None)
    """
    class A4PageExtractor(HTMLParser):
        """Extract page content from HTML.

        Recognises two page-container patterns:
        - <main class="...a4-page...">  (old recipe template)
        - <div  class="...recipe-page...">  (new botanical template)
        """

        # (tag, class-substring) pairs that mark a page container
        PAGE_PATTERNS = [('main', 'a4-page'), ('div', 'recipe-page')]

        def __init__(self):
            super().__init__()
            self.in_page = False
            self.page_tag = None      # tag name that opened the current page
            self.in_head = False
            self.in_footer = False
            self.depth = 0
            self.a4_content = []
            self.head_content = []

        def _match_page_container(self, tag, attrs):
            """Return True if (tag, attrs) matches any PAGE_PATTERN."""
            for page_tag, page_class in self.PAGE_PATTERNS:
                if tag == page_tag:
                    for attr_name, attr_val in attrs:
                        if attr_name == 'class' and page_class in (attr_val or ''):
                            return True
            return False

        def handle_starttag(self, tag, attrs):
            if self.in_footer:
                return
            if tag == 'footer' and self.in_page:
                self.in_footer = True
                return

            if self.in_page:
                self.depth += 1
                attrs_str = ' '.join([f'{k}="{v}"' for k, v in attrs])
                self.a4_content.append(f'<{tag} {attrs_str}>')
            elif self._match_page_container(tag, attrs):
                self.in_page = True
                self.page_tag = tag
                self.depth = 1
                attrs_str = ' '.join([f'{k}="{v}"' for k, v in attrs])
                self.a4_content.append(f'<{tag} {attrs_str}>')
            elif tag == 'head':
                self.in_head = True
            elif self.in_head:
                attrs_str = ' '.join([f'{k}="{v}"' for k, v in attrs])
                self.head_content.append(f'<{tag} {attrs_str}>')

        def handle_endtag(self, tag):
            if self.in_footer:
                if tag == 'footer':
                    self.in_footer = False
                return

            if self.in_page:
                if tag == self.page_tag and self.depth == 1:
                    self.a4_content.append(f'</{tag}>')
                    self.in_page = False
                    self.page_tag = None
                else:
                    self.depth -= 1
                    self.a4_content.append(f'</{tag}>')
            elif tag == 'head':
                self.in_head = False
            elif self.in_head:
                self.head_content.append(f'</{tag}>')

        def handle_data(self, data):
            if self.in_footer:
                return
            if self.in_page:
                self.a4_content.append(data)
            elif self.in_head:
                self.head_content.append(data)
    
    all_pages_html = []
    final_heads: List[str] = []

    for html_file in html_files:
        if not os.path.exists(html_file):
            print(f"Warning: File not found: {html_file}")
            continue

        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        parser = A4PageExtractor()
        parser.feed(html_content)

        all_pages_html.append(''.join(parser.a4_content))

        # Collect head content from every file whose <head> is final markup
        # (CSS, JS, etc.). A sheet whose head is still an escaped .format()
        # template (literal {{ }} pairs, a stray {title}) would poison the
        # CSS and the tailwind-config JS of the whole combined document;
        # such heads are skipped entirely.
        #
        # Heads are NOT uniform across a group, so the first one must not
        # simply donate the shared head: content sheets (chapter intros,
        # sub-TOCs, flowcharts) carry the Tailwind/content stylesheet while
        # recipe sheets carry the recipe stylesheet (.section-heading,
        # .recipe-page, ...). Donating only the first head stripped the
        # recipe CSS from every group opened by a content sheet, printing
        # its recipe headings as unstyled 16px h2s. _merge_head_markup
        # unions all clean heads instead, so a combined group is styled
        # for every page type it contains.
        if "{{" not in ''.join(parser.head_content):
            final_heads.append(''.join(parser.head_content))

    combined_head_markup = _merge_head_markup(final_heads)
    # Build combined HTML document
    combined_html = '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
    combined_html += '<meta charset="utf-8"/>\n'
    combined_html += '<meta content="width=device-width, initial-scale=1.0" name="viewport"/>\n'
    combined_html += '<title>Combined Cookbook</title>\n'
    combined_html += combined_head_markup
    combined_html += '<style>\n'
    combined_html += f'html, body {{ margin: 0; padding: 0; }}\n'
    combined_html += f'body {{ display: block; background: {PAGE_BG}; width: {A4_WIDTH_MM}mm; max-width: {A4_WIDTH_MM}mm; overflow-x: hidden; }}\n'
    combined_html += f'@page {{ size: {PAGE_SIZE}; margin: 0; }}\n'
    combined_html += f'.a4-page, .recipe-page {{ width: {A4_WIDTH_MM}mm !important; max-width: {A4_WIDTH_MM}mm !important; box-sizing: border-box; }}\n'
    combined_html += f'.a4-page, .recipe-page {{ height: {A4_HEIGHT_MM}mm !important; position: relative !important; isolation: isolate !important; overflow: hidden !important; }}\n'
    combined_html += f'.a4-page, .recipe-page {{ {PAGE_BREAK_AFTER}-after: {PAGE_BREAK_AFTER}; }}\n'
    combined_html += f'.a4-page:last-child, .recipe-page:last-child {{ {PAGE_BREAK_AFTER}-after: auto; }}\n'
    # Break long unbreakable words inside page titles so they wrap instead of overflowing.
    combined_html += '.recipe-page h1, .a4-page h1 { overflow-wrap: anywhere; word-break: break-word; }\n'
    combined_html += 'main { display: contents; }\n'
    combined_html += '</style>\n'
    combined_html += '</head>\n<body>\n'
    combined_html += '\n'.join(all_pages_html)
    combined_html += '\n</body>\n</html>'
    
    # Save to file if output_file provided
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(combined_html)
        return output_file
    
    return combined_html


def build_inpage_footer(chapter: str = '', section: str = '', start_page: int = 1) -> str:
    """In-sheet footer: green rule, chapter—section label, green bar.

    Rendered inside each sheet, absolutely pinned to the bottom edge and
    layered behind content (z-index -1 inside the sheet's isolated stacking
    context), so giant blocks may overlap it without covering it up. Geometry
    is fixed regardless of label length, which keeps the footer visually
    consistent across every sheet of the book.

    ``start_page`` is accepted for backwards compatibility with the old
    Chromium margin-footer API and is intentionally ignored.
    """
    chapter_safe = html.escape(chapter or '')
    section_safe = html.escape(section or '')
    if chapter_safe and section_safe:
        left_text = f"{chapter_safe} &mdash; {section_safe}"
    else:
        left_text = chapter_safe or section_safe or ''

    # Same visuals as the old Chromium margin-box footer: 2mm whitespace,
    # 1.5pt green rule with the uppercase label, 2mm solid green bar.
    # Side padding mirrors the sheet's padding (ADR 0016) so the label
    # stays aligned with the text columns.
    return (
        '<div class="page-footer" '
        'style="position:absolute;left:0;right:0;bottom:0;z-index:-1;'
        '-webkit-print-color-adjust:exact;print-color-adjust:exact;width:100%;'
        "font-family:'Plus Jakarta Sans',Manrope,Arial,sans-serif;"
        'color:{COLOR_ON_SURFACE_VARIANT};margin:0;padding:0;box-sizing:border-box;">'
        '<div style="width:100%;height:2mm;"></div>'
        '<div style="width:100%;display:flex;justify-content:space-between;align-items:center;'
        'padding:2mm 15mm 2mm 25mm;border-top:1.5pt solid {COLOR_PRIMARY};opacity:0.4;box-sizing:border-box;">'
        '<span style="font-size:8pt;font-weight:500;letter-spacing:0.18em;text-transform:uppercase;'
        f'color:{COLOR_ON_SURFACE_VARIANT};">{left_text}</span>'
        '<span style="font-size:8pt;font-weight:700;letter-spacing:0.12em;color:{COLOR_ON_SURFACE};"></span>'
        '</div>'
        '<div style="width:100%;height:2mm;background-color:{COLOR_PRIMARY};opacity:0.8;"></div>'
        '</div>'
    )


# Backwards-compatible alias: existing callers import build_footer_template.
build_footer_template = build_inpage_footer


def html_to_pdf_combined_with_footer(input_files: List[str], output_file: str, footer_html: str,
                                     temp_html_name: str = 'temp_combined.html',
                                     measure_cb=None, measure_result=None) -> Optional[str]:
    """Combine multiple HTML files into one PDF with a shared footer.

    Used to merge adjacent pages that share the same (chapter, section) into a
    single PDF so Chrome only embeds one font subset across the group.

    ``measure_cb``/``measure_result`` forward the ADR 0004 navigation
    measurement hook to the underlying conversion.
    """
    if not input_files:
        return None

    # Skip groups whose inputs all vanished (e.g. deleted mid-build by a sync
    # engine): combining them yields a zero-page document that still prints a
    # blank PDF and would count as "success", silently shipping a partial book.
    existing_files = [f for f in input_files if os.path.exists(f)]
    if not existing_files:
        print("Error: no input files exist; skipping group conversion")
        return None

    if len(existing_files) == 1:
        ok = _convert_single_to_pdf(existing_files[0], output_file, footer_html=footer_html,
                                    measure_cb=measure_cb, measure_result=measure_result)
        return output_file if ok else None

    temp_combined_html = os.path.join(
        os.path.dirname(output_file) if output_file else '.', temp_html_name
    )
    combine_html_files(existing_files, temp_combined_html)
    success = _convert_single_to_pdf(temp_combined_html, output_file, footer_html=footer_html,
                                     measure_cb=measure_cb, measure_result=measure_result)

    if os.path.exists(temp_combined_html):
        try:
            os.remove(temp_combined_html)
        except Exception:
            pass

    return output_file if success else None


def close_browser_pool():
    """Close the browser pool. Call this when done to clean up resources."""
    _close_browser()
