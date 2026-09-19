"""
Main application for generating a PDF cookbook.
This is the entry point that orchestrates the cookbook generation.
Optimized for performance with caching and browser reuse.
"""

import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import markdown
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter

# Ensure this script's directory and the helpers directory are importable
# so this entry point works regardless of the current working directory.
# The script dir is needed to import the sibling main_generate_cookbook_structure.
_SCRIPT_DIR = Path(__file__).parent.resolve()
_HELPERS_DIR = _SCRIPT_DIR / "helpers"
for _dir in (_SCRIPT_DIR, _HELPERS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

# Import modules
from structure_parser import StructureParser
from pdf_builder import PDFBuilder
from page_toc import TOCPageRenderer, display_parts, clean_title_id
from page_content import ContentPageRenderer
from page_splitter import split_page_file
from page_renderer import RecipeParser, RecipeRenderer
from html_to_pdf import (
    html_to_pdf_combined_with_footer,
    build_footer_template,
    close_browser_pool,
    _get_browser,
)
from mermaid_renderer import bake_mermaid_in_file
from graph_scatterplot import render_scatterplot_png
from generation_report import render_report_markdown
from report_summary import summarize_diagnostics
from link_injection import (
    NavigationGeometry,
    LinkInjectionError,
    collect_navigation_geometry,
    inject_navigation,
)
from config import (
    PAGE_NUMBER_FONT,
    PAGE_NUMBER_FONT_SIZE,
    PAGE_NUMBER_COLOR_RGB,
    PAGE_NUMBER_X_POSITION,
    PAGE_NUMBER_Y_POSITION,
)
from input_roots import PathSpec, find_file, resolve_roots
from helpers.logging import progress, info, warn, error, fatal

# [[Page]] or [[Page|shown text]] - Obsidian wiki links in source content.
# The negative lookbehind keeps ![[embed]] out of the page-link pass.
_WIKI_LINK_RE = re.compile(r'(?<!!)\[\[([^\]|]+(?:\|[^\]]+)?)\]\]')

# Display title of the main table of contents: single source of truth for
# the TOC sheet's rendered title, its footer label and (via clean_title_id)
# the anchor id whose measured page the digital variant's "back to table
# of contents" footer link targets (ADR 0004).
TOC_PAGE_TITLE = "Table of Contents"
cookbook_folder = "data_modularflavour"


class CookbookGenerator:
    """Generate a PDF cookbook from markdown files based on structure."""
    
    def __init__(self, input_dir: Optional[PathSpec] = None, temp_dir: Optional[str] = None):
        # Resolve the default input directories relative to this script so the
        # build works regardless of the current working directory. The real
        # data_modularflavour/text and text_notdone folders live one level
        # above the script folder; both are one virtual input (ADR 0023) and
        # the first root wins filename collisions.
        if input_dir is None:
            input_dir = [
                str(_SCRIPT_DIR.parent / cookbook_folder / "text"),
                str(_SCRIPT_DIR.parent / cookbook_folder / "text_notdone"),
            ]
        self.input_roots = resolve_roots(input_dir)
        # Primary root: kept as ``input_dir`` for existing callers/tests.
        self.input_dir = self.input_roots[0]
        self.exports_dir = _SCRIPT_DIR.parent / "exports"
        # All intermediate/temporary artifacts go into a dedicated working
        # folder so only the final PDF ever lands in the exports root.
        #
        # Defaults OUTSIDE the vault (system temp): this project lives in a
        # Google Drive sync root, and Drive's async reconciliation was observed
        # deleting freshly written HTML files from exports/_temp mid-build -
        # that run then silently shipped a partial cookbook of blank pages.
        # Pass --temp-dir to keep working files inside the vault explicitly.
        if temp_dir:
            self.temp_dir = Path(temp_dir)
        else:
            # Unique per process: two overlapping builds (manual rerun while
            # one is in flight, IDE double-fire) must never share - every
            # build WIPES its working folder at startup, which silently
            # destroys the other run's sheets mid-layout (observed 2026-08-25:
            # 98 sheets vanished, caught by the pre-conversion guard).
            self.temp_dir = (Path(tempfile.gettempdir())
                             / f"cookbook_build_{os.getpid()}")
        self._build_lock_path: Optional[Path] = None
        self._sweep_stale_temp_dirs()
        
        # Initialize components
        self.structure_parser = StructureParser(input_dir)
        self.pdf_builder = PDFBuilder()
        self.recipe_parser = RecipeParser()
        self.recipe_renderer = RecipeRenderer()
        
        # Ensure exports directory exists
        self.exports_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        
        # Wiki link reference to page ID mapping
        self.wiki_link_mapping = {}
        # Wiki link reference to actual title mapping (for display text)
        self.wiki_link_titles = {}
        
        # Cache for file contents and parsed recipes to avoid redundant work
        self._file_content_cache: Dict[str, str] = {}
        self._parsed_recipe_cache: Dict[str, Dict] = {}
        # Per-file diagnostics from tolerant recipe parsing, aggregated into
        # the generation report (console + exports/generation_report.md).
        self._parse_diagnostics: Dict[str, List[Tuple[str, str]]] = {}
        # Layout diagnostics from the browser-measured splitting pass
        # (continuation sheets, giant blocks); aggregated into the report.
        self._split_diagnostics: List[Tuple[str, str]] = []
        # Tracks unresolved [[wiki links]] -> source filenames, for the
        # aggregated warning and generation report.
        self.unresolved_wiki_links: Dict[str, set] = defaultdict(set)

        # Measured navigation geometry (ADR 0004): link rects, TOC rows and
        # the page-id -> physical-page map, collected during the group
        # conversion passes and injected into the merged book afterwards.
        self._nav_geometry = NavigationGeometry()
        # Page IDs of loved recipes (love level >= 8): their heart prints
        # behind the page number of the first sheet instead of appearing
        # as an icon in the side icon stack.
        self._loved_page_ids: set = set()
        # Which shipped variants to write: print (invisible links) and/or
        # digital (green-accented links).
        self.variants: Tuple[str, ...] = ("print", "digital")
        # Per-variant injection summaries for the generation report.
        self.link_stats: Dict[str, dict] = {}
        # Groups whose in-browser navigation measurement failed; any nonzero
        # count must fail the build (a link-less book must never ship
        # silently just because measurement broke).
        self._nav_measurement_failures = 0
    
    def add_global_page_numbers(self, pdf_path: str,
                                loved_pages: Optional[set] = None):
        """Overlays global page numbers onto an existing PDF.

        ``loved_pages`` holds zero-based physical page indices of loved
        recipes' first sheets; there the number prints on top of the
        favourite heart.
        """
        print(f"Adding global page numbers to {pdf_path}...")

        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        num_pages = len(reader.pages)
        loved_pages = loved_pages or set()
        
        for i in range(num_pages):
            page = reader.pages[i]
            
            # Create a new PDF in memory for the page number
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=A4)
            
            # Style settings (Match your footer style)
            can.setFont(PAGE_NUMBER_FONT, PAGE_NUMBER_FONT_SIZE)
            can.setFillColorRGB(*PAGE_NUMBER_COLOR_RGB) # #2d3432 equivalent
            
            # Position: right-aligned at 195mm from left - the right text edge
            # (210mm paper - 15mm side margin, ADR 0016) - 11mm from bottom.
            # Note: ReportLab uses points (1/72 inch). 1mm = 2.834 points.
            text = f"{i + 1}"
            if i in loved_pages:
                self._draw_love_heart(can, text)
            can.drawRightString(PAGE_NUMBER_X_POSITION, PAGE_NUMBER_Y_POSITION, text)
            can.save()
            
            # Move to the beginning of the buffer
            packet.seek(0)
            number_pdf = PdfReader(packet)
            number_page = number_pdf.pages[0]
            
            # Merge the page number onto the original page
            try:
                page.merge_page(number_page, expand=True)
            except Exception as e:
                # If merge fails, just add the page as-is (PDF will be generated without numbers)
                warn(f"Could not add page number {i+1}: {e}")
            
            writer.add_page(page)
        
        # Save the result
        with open(pdf_path, "wb") as f:
            writer.write(f)
            
    _LOVE_HEART_SIZE_MM = 6
    # Optical middle of the page-number digits: about half their cap
    # height above the baseline (Helvetica-Bold cap height ~ 0.718 em => ~3 pt).
    _LOVE_HEART_OPTICAL_OFFSET_PT = 3

    @staticmethod
    def _love_heart_path() -> Optional[str]:
        """Locate icon_love.png regardless of the working directory."""
        candidates = [
            Path("data_modularflavour/icon") / "icon_love.png",
            _SCRIPT_DIR.parent / "data_modularflavour" / "icon" / "icon_love.png",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _draw_love_heart(self, can: canvas.Canvas, text: str) -> bool:
        """Draw the favourite heart centred behind the page-number digits.

        Runs before drawRightString so the digits paint on top of the heart.
        Returns True when a heart was actually drawn.
        """
        heart_path = self._love_heart_path()
        if heart_path is None:
            return False
        text_width = can.stringWidth(text, PAGE_NUMBER_FONT,
                                     PAGE_NUMBER_FONT_SIZE)
        centre_x = PAGE_NUMBER_X_POSITION - text_width / 2
        centre_y = PAGE_NUMBER_Y_POSITION + self._LOVE_HEART_OPTICAL_OFFSET_PT
        half = (self._LOVE_HEART_SIZE_MM * mm) / 2
        try:
            can.drawImage(heart_path, centre_x - half, centre_y - half,
                          self._LOVE_HEART_SIZE_MM * mm,
                          self._LOVE_HEART_SIZE_MM * mm,
                          preserveAspectRatio=True, mask='auto')
        except Exception:
            return False
        return True

    def read_markdown_file(self, filename: str) -> str:
        """Read and return the content of a markdown file (with caching)."""
        if filename in self._file_content_cache:
            return self._file_content_cache[filename]
        
        filepath = find_file(self.input_roots, filename)
        if filepath is None:
            content = f"# File not found: {filename}\n\nThe file could not be found."
            self._file_content_cache[filename] = content
            return content
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            self._file_content_cache[filename] = content
            return content
        except FileNotFoundError:
            content = f"# File not found: {filename}\n\nThe file could not be found."
            self._file_content_cache[filename] = content
            return content
        except Exception as e:
            content = f"# Error reading file: {filename}\n\nError: {str(e)}"
            self._file_content_cache[filename] = content
            return content
      
    def is_recipe_file(self, content: str) -> bool:
        """Check if the markdown file is a recipe (has both Instructions and Ingredients)."""
        has_instructions = '### Instructions' in content or '## Instructions' in content
        has_ingredients = '### Ingredients' in content or '## Ingredients' in content
        return has_instructions or has_ingredients

    def _is_notdone_file(self, filename: str) -> bool:
        """Return True when ``filename`` resolves to a non-primary input root."""
        path = find_file(self.input_roots, filename)
        if path is None:
            return False
        for root in self.input_roots[1:]:
            if not root.exists():
                continue
            try:
                if path.is_relative_to(root):
                    return True
            except TypeError:
                continue
        return False

    def _build_file_uri(self, filename: str) -> str:
        """Build a file URI for an asset (image) located in the input directory.

        Assets referenced via ``![[...]]`` embeds can live in different
        locations depending on the page that references them:

        - Recipe/photo assets may live in the markdown input directory (``data_modularflavour/text``).
        - Icon assets live in the dedicated icons directory (``data_modularflavour/icon``).

        The first location where the file actually exists wins; the returned URI
        uses proper percent-encoding (e.g. spaces become ``%20``).
        """
        # Sanitize the referenced filename: strip path separators so we never
        # escape the search roots (Obsidian stores embeds as bare filenames).
        filename = os.path.basename(filename)
        # Ignore Obsidian heading references like "image#section".
        if '#' in filename:
            filename = filename.split('#')[0].strip()

        search_roots = [
            str(self.input_dir),
            # Secondary input roots (e.g. text_notdone) also host page assets.
            *[str(root) for root in self.input_roots[1:]],
            # Script-relative (cwd-independent) first, cwd-relative second.
            str(_SCRIPT_DIR.parent / "data_modularflavour" / "images"),
            str(Path("data_modularflavour") / "images"),
            str(_SCRIPT_DIR.parent / "data_modularflavour" / "icon"),
            str(Path("data_modularflavour") / "icon"),
            ".",
        ]
        for root in search_roots:
            candidate = Path(root) / filename
            try:
                if candidate.is_file():
                    return candidate.resolve().as_uri()
            except OSError:
                continue

        # Fallback: keep the previous absolute-path behavior so nothing breaks
        # if the file is simply not found (broken image icon is shown instead).
        base_path = str(self.input_dir)
        abs_path = os.path.abspath(base_path).replace(os.sep, '/')

        # Windows paths have a drive letter (e.g., G:/path), Unix paths don't
        if ':' in abs_path:
            return f'file:///{abs_path}/{filename}'
        return f'file://{abs_path}/{filename}'
     
    def _convert_wiki_embed_to_img(self, match: re.Match) -> str:
        r"""Convert Obsidian wiki-style embed syntax to HTML img tag.
         
        Handles both ![[image|size]] and ![[image\|size]] formats.
        """
        # The sized pattern carries two groups, the sizeless form only one;
        # match.group(2) raises IndexError when that group does not exist.
        groups = match.groups()
        filename = groups[0].strip()
        size = groups[1].strip() if len(groups) > 1 and groups[1] else None
        file_uri = self._build_file_uri(filename)
        
        if size:
            try:
                width = int(size)
                return f'<img src="{file_uri}" alt="{filename}" width="{width}" />'
            except ValueError:
                return f'<img src="{file_uri}" alt="{filename}" style="width:{size}px" />'
        # No size given: fit the content column so the art can never
        # overflow the sheet's fixed box, which clips (overflow:hidden)
        # instead of reflowing.
        return (f'<img src="{file_uri}" alt="{filename}" '
                f'style="max-width:100%;height:auto" />')

    def _replace_graph_scatterplot_markers(self, text: str) -> str:
        """Replace ==GRAPH_SCATTERPLOT_START/END== blocks with rendered scatterplot images.

        If rendering fails for any reason, the original marker block is left
        in the text so it degrades to visible raw text instead of crashing
        the build.
        """
        def _replace(match: re.Match) -> str:
            table_text = match.group(1).strip()
            try:
                png_path = self.temp_dir / f"scatter_{uuid.uuid4().hex}.png"
                png_uri = render_scatterplot_png(table_text, str(png_path))
                return (
                    f'<img src="{png_uri}" '
                    f'alt="Scatterplot" '
                    f'style="max-width:100%;height:auto" />'
                )
            except Exception as exc:
                warn(f"Could not render scatterplot: {exc}")
                return match.group(0)

        return re.sub(
            r'==GRAPH_SCATTERPLOT_START==\n(.*?)==GRAPH_SCATTERPLOT_END==',
            _replace,
            text,
            flags=re.DOTALL,
        )
    
    def _resolve_wiki_page(self, page_ref: str) -> Tuple[str, Optional[str]]:
        """Resolve a wiki-link page reference to (page_id, display_title).

        Args:
            page_ref: Raw reference from ``[[...]]``, e.g. '03_projects/kookboek/_2.2.1. Rice'.

        Returns:
            A ``(page_id, display_title)`` tuple. ``display_title`` is ``None``
            when the reference could not be resolved to any known page.
        """
        ref = page_ref.strip().lower()
        # Strip vault directory prefixes so refs like
        # '03_projects/kookboek/_2.2.1. Rice' match the registered filenames.
        base = os.path.basename(ref)
        if '#' in base:
            base = base.split('#')[0].strip()      # strip Obsidian section suffix
        base = base.lstrip('_').lstrip('0123456789.- ')
        # Also strip the leading numbers/dots from the full path form.
        stripped = ref.lstrip('_').lstrip('0123456789.- ')

        candidates = [key for key in (ref, base, stripped) if key]
        for key in candidates:
            # 1) Direct mapping / title hit
            if key in self.wiki_link_mapping:
                return self.wiki_link_mapping[key], self.wiki_link_titles.get(key)
            # 2) Via the display-title registry
            if key in self.wiki_link_titles:
                title = self.wiki_link_titles[key]
                pid = self.wiki_link_mapping.get(key) or self.wiki_link_mapping.get(title.lower())
                if pid:
                    return pid, title

        return None, None

    def _render_wiki_link_match(self, match: "re.Match[str]",
                                current_page_id: Optional[str],
                                source_filename: Optional[str] = None) -> str:
        """Convert one ``[[page]]`` / ``[[page|display]]`` match to HTML.

        Resolved targets become anchors. A link pointing at the page it is
        already on degrades to styled, non-clickable text (clicking it is a
        no-op by definition). Unresolved targets degrade to plain text and
        are reported - never a broken anchor.
        """
        content = match.group(1)
        if '|' in content:
            parts = content.split('|')
            page_ref = parts[0].strip()
            display_text = parts[1].strip()
        else:
            page_ref = content.strip()
            display_text = None

        page_id, actual_title = self._resolve_wiki_page(page_ref)

        if page_id is None:
            self.unresolved_wiki_links[page_ref].add(source_filename or "<unknown source>")
            if display_text is None:
                display_text = page_ref.replace('_', ' ').replace('-', ' ').replace('/', ' / ')
            return f'<span class="wiki-link-unresolved">{display_text}</span>'

        if display_text is None:
            display_text = actual_title or page_ref.replace('_', ' ').replace('-', ' ')

        if current_page_id and page_id == current_page_id:
            return f'<span class="wiki-link-self">{display_text}</span>'

        return f'<a href="#{page_id}" class="wiki-link">{display_text}</a>'

    def markdown_to_html(self, markdown_text: str,
                         current_page_id: Optional[str] = None,
                         source_filename: Optional[str] = None) -> str:
        """Convert markdown to HTML.

        ``current_page_id`` is the anchor id of the page being rendered;
        links targeting it are emitted as self-references instead of anchors.
        """
        # Pre-process wiki-style embed syntax ![[filename|size]] to HTML <img> tags
        # Handles both ![[image|size]] and ![[image\|size]] formats (escaped pipe)
        markdown_text = re.sub(
            r'!\[\[([^\]]+?)(?:\\\||\|)([^\]]+?)\]\]',
            self._convert_wiki_embed_to_img,
            markdown_text
        )

        # Sizeless embeds (![[image]]) must be converted here as well, before
        # the wiki-link pass below: _WIKI_LINK_RE would otherwise swallow the
        # inner [[image]] as a page reference and the sheet would print a
        # literal "!image name" instead of the picture.
        markdown_text = re.sub(
            r'!\[\[([^\]]+?)\]\]',
            self._convert_wiki_embed_to_img,
            markdown_text
        )

        # Replace ==GRAPH_SCATTERPLOT_START/END== marker blocks with rendered
        # scatterplot <img> tags BEFORE mermaid extraction / markdown conversion
        # so the img tag survives md.convert() unchanged.
        markdown_text = self._replace_graph_scatterplot_markers(markdown_text)

        # Handle Mermaid diagrams BEFORE markdown conversion.
        # Extract mermaid blocks, replace with safe placeholder text that survives
        # markdown parsing (no HTML entities or special markdown chars), then restore.
        mermaid_blocks = []
        
        def extract_mermaid_block(match):
            diagram_content = match.group(1).strip()
            if not diagram_content:
                return ''
            mermaid_blocks.append(diagram_content)
            return 'X-MRM-' + str(len(mermaid_blocks) - 1) + '-X'
        
        markdown_text = re.sub(
            r'```mermaid\s*\n(.*?)```',
            extract_mermaid_block,
            markdown_text,
            flags=re.DOTALL
        )
        # Pre-process wiki-style links [[page]] / [[page|display]] into
        # internal-link anchors (ADR 0004); self-links degrade to styled text.
        markdown_text = _WIKI_LINK_RE.sub(
            lambda m: self._render_wiki_link_match(
                m, current_page_id, source_filename),
            markdown_text,
        )
        
        md = markdown.Markdown(extensions=['extra', 'codehilite'])
        html = md.convert(markdown_text)
        
        # Restore mermaid placeholders back to <div class="mermaid"> elements
        if mermaid_blocks:
            if 'X-MRM-' in html:
                def restore_mermaid(match):
                    idx_str = match.group(1)
                    try:
                        idx = int(idx_str)
                        if idx < len(mermaid_blocks):
                            return f'<div class="mermaid">{mermaid_blocks[idx]}</div>'
                    except (ValueError, IndexError):
                        pass
                    return match.group(0)

                html = re.sub(
                    r'X-MRM-(\d+)-X',
                    restore_mermaid,
                    html
                )
                # Markdown wrapped the bare placeholder line in a paragraph.
                # A literal <p><div ...></div></p> makes Chromium's parser close
                # the <p> early and mint a stray EMPTY <p> after the diagram -
                # that phantom unit then claims its own near-blank sheet during
                # splitting. Unwrap the paragraph around every diagram div.
                html = re.sub(
                    r'<p>(<div class="mermaid">.*?</div>)</p>',
                    r'\1',
                    html,
                    flags=re.DOTALL
                )

        
        return html
    
    def process_wiki_links_html(self, html_content: str,
                                current_page_id: Optional[str] = None,
                                source_filename: Optional[str] = None) -> str:
        """Convert wiki-style [[page]] and [[page|display]] links to HTML anchors in rendered HTML.

        ``current_page_id`` is the anchor id of the page being rendered;
        links targeting it are emitted as self-references instead of anchors.
        """
        # Also convert Obsidian image embeds (![[image|size]]) to <img> tags here,
        # because the recipe HTML pipeline (unlike markdown_to_html) never sees the
        # raw markdown and would otherwise treat embeds as wiki links.
        html_content = re.sub(
            r'!\[\[([^\]]+?)(?:\\\||\|)([^\]]+?)\]\]',
            self._convert_wiki_embed_to_img,
            html_content,
        )
        html_content = re.sub(
            r'!\[\[([^\]]+?)\]\]',
            lambda m: self._convert_wiki_embed_to_img(m),
            html_content,
        )

        return _WIKI_LINK_RE.sub(
            lambda m: self._render_wiki_link_match(
                m, current_page_id, source_filename),
            html_content,
        )
    
    def register_wiki_link(self, wiki_ref: str, page_id: str):
        """Register a wiki link reference to page ID mapping."""
        # Store both the reference and normalized forms
        self.wiki_link_mapping[wiki_ref.lower()] = page_id
        # Also store without leading numbers/dashes for easier matching
        normalized = wiki_ref.lower().lstrip('0123456789.- ')
        if normalized != wiki_ref.lower():
            self.wiki_link_mapping[normalized] = page_id
    
    def get_or_parse_recipe(self, filename: str, content: str) -> Dict:
        """Get cached recipe or parse and cache it (collecting diagnostics)."""
        if filename in self._parsed_recipe_cache:
            return self._parsed_recipe_cache[filename]

        recipe, diagnostics = self.recipe_parser.parse_recipe_with_diagnostics(content)
        self._parsed_recipe_cache[filename] = recipe
        self._parse_diagnostics[filename] = diagnostics
        return recipe

    def _extract_position_label(self, filename: str) -> str:
        """Extract the numbering label from a filename for title display.

        Examples:
            "_1.1.1. Ramen.md" -> "1.1.1."
            "_2.1.1.A. Ramen_Tare_Shio.md" -> "2.1.1.A."
            "Ramen.md" -> "" (no numbering)

        Args:
            filename: The filename to extract the label from

        Returns:
            The position label with trailing dot, or empty string if none found
        """
        stem = Path(filename).stem
        pos_label, _ = display_parts(stem)
        return f"{pos_label}." if pos_label else ""

    def process_recipe_to_html(self, filename: str, content: str) -> Tuple[str, str]:
        """Process a recipe file and return (html_content, html_filepath).

        Args:
            filename: The filename being processed
            content: File content
        """
        try:
            # Parse recipe (using cache if available)
            recipe = self.get_or_parse_recipe(filename, content)

            # Extract position label from filename for title numbering
            # e.g., "_1.1.1. Ramen.md" -> "1.1.1."
            position_label = self._extract_position_label(filename)

            html_content = self.recipe_renderer.render_html(recipe, position_label)

            # Process wiki links in the rendered HTML. Self-links (the page
            # referencing itself) degrade to styled text, so derive the same
            # page id the renderer puts on the sheet's heading.
            recipe_title = recipe.get('title', '') or 'Untitled Recipe'
            current_page_id = self._page_id_for_title(recipe_title, is_recipe=True)
            html_content = self.process_wiki_links_html(html_content,
                                                        current_page_id=current_page_id,
                                                        source_filename=filename)

            # Loved recipes carry their heart at the page number (see
            # add_global_page_numbers), not in the side icon stack.
            if (recipe.get('love_level') or 0) >= 8:
                self._loved_page_ids.add(current_page_id)
            
            # Save HTML - self-healing if an external tool removed the
            # temp folder between writes (e.g. cloud-sync reconciliation)
            html_path = self._write_temp_html(Path(filename).stem, html_content)

            return html_content, html_path
            
        except Exception as e:
            warn(f"Error processing recipe {filename}: {e}")
            return None, None
    
    def _content_page_title(self, content: str, filename: str) -> str:
        """Display title for a non-recipe page: authored, else filename-derived.

        Sideinfo pages author their heading in a "### Title" section; every
        other content page keeps the filename-derived title. Used by both the
        renderer and the wiki-link pre-scan, so a page's printed heading and
        its links can never disagree.
        """
        page_data = self.recipe_parser.parse_content_page(content)
        if page_data.get('title'):
            return page_data['title']
        return filename.replace('.md', '').replace('_', ' ').title()

    def process_non_recipe_to_html(self, filename: str, content: str, title: str) -> Tuple[str, str]:
        """Process a non-recipe file and return (html_content, html_filepath).

        A sideinfo page (one carrying a "### Text" section) prints only that
        section, opened by its description when it authored one, under its
        authored title plus the filename's position label. A file without a
        "### Text" section keeps rendering its whole content, so pages that
        have not been converted yet lose nothing.

        Args:
            filename: The filename being processed
            content: File content
            title: Page title, used when the file authors none
        """
        try:
            page_data = self.recipe_parser.parse_content_page(content)
            page_title = page_data.get('title') or title

            body_md = content
            if page_data.get('has_text_section'):
                # The description reads as the page's lead sentence: a plain
                # paragraph, blank-line separated from the text body.
                body_md = page_data.get('text') or ''
                if page_data.get('description'):
                    body_md = page_data['description'] + '\n\n' + body_md

            # Links targeting this very page degrade to styled text. The id
            # derives from the authored title alone, never from the printed
            # heading, so it stays independent of the position label and
            # matches the id the wiki-link pre-scan registered.
            current_page_id = self._page_id_for_title(
                page_title, is_recipe=False)
            html_content = self.markdown_to_html(
                body_md, current_page_id=current_page_id,
                source_filename=filename)

            # A sideinfo page prints its authored title with the filename's
            # position label, mirroring the recipe pages ("1.1.1. Ramen").
            display_title = page_title
            if page_data.get('has_text_section'):
                position_label = self._extract_position_label(filename)
                display_title = f"{position_label} {page_title}".strip()

            page_html = ContentPageRenderer().render(
                display_title, html_content, page_id=current_page_id)
            # Save HTML - self-healing if an external tool removed the
            # temp folder between writes (e.g. cloud-sync reconciliation)
            page_path = self._write_temp_html(Path(filename).stem, page_html)

            return page_html, page_path
            
        except Exception as e:
            warn(f"Error processing content {filename}: {e}")
            return None, None
    
    def process_chapter_to_html(self, filename: str, content: str, title: str,
                                subtree: Dict) -> Tuple[List[str], List[str]]:
        """Render a big chapter's block as separate sheets, text first
        (ADR 0015):
        Page 1: Chapter Title + Intro prose (if any)
        Page 2: Chapter Title + Sub-TOC
        
        Args:
            filename: The chapter markdown filename
            content: File content (chapter intro prose)
            title: Page title; anchors the page id exactly like the
                filename-derived title used in the wiki-link pre-scan
            subtree: The chapter's section dict from the structure hierarchy
        """
        try:
            # Links targeting this very page degrade to styled text.
            current_page_id = self._page_id_for_title(title, is_recipe=False)
            prose_html = self.markdown_to_html(
                content, current_page_id=current_page_id,
                source_filename=filename)
            chapter_pages = TOCPageRenderer().render_chapter(
                title, subtree, content_html=prose_html,
                link_resolver=lambda ref: self._resolve_wiki_page(ref)[0])
            
            # Write each page to a separate HTML file
            html_paths = []
            stem = Path(filename).stem
            for i, page_html in enumerate(chapter_pages):
                if len(chapter_pages) > 1:
                    page_stem = f"{stem}_page{i+1}"
                else:
                    page_stem = stem
                page_path = self._write_temp_html(page_stem, page_html)
                html_paths.append(page_path)

            return chapter_pages, html_paths
            
        except Exception as e:
            warn(f"Error processing chapter page {filename}: {e}")
            return [], []
    
    def _page_id_for_title(self, title: str, is_recipe: bool = False) -> str:
        """Build the page anchor ID exactly as the renderers emit it.

        Recipe pages (page_renderer.py) use ``title.replace(' ','-').replace('_','-').lower()``.
        Content pages (page_content.py) additionally strip non-[a-z0-9-] chars.
        Keeping these in sync ensures wiki-link anchors match real page IDs.
        """
        clean_id = str(title).replace(' ', '-').replace('_', '-').lower()
        if not is_recipe:
            clean_id = re.sub(r'[^a-z0-9\-]', '', clean_id)
        return 'page-' + clean_id

    def _register_page_identity(self, title: str, filename_stem: str,
                                is_recipe: bool) -> str:
        """Register all identity variants for a page and return its page_id.

        Both the display title and the filename stem are registered as
        wiki-link keys, plus lowercased title variants (bare stem without
        leading underscore, stem stripped of leading numbering) so
        ``[[...]]`` references resolve regardless of how the author wrote
        them. Behaviour is identical to the previous inline code.
        """
        page_id = self._page_id_for_title(title, is_recipe=is_recipe)
        self.register_wiki_link(title, page_id)
        self.register_wiki_link(filename_stem, page_id)
        self.wiki_link_titles[title.lower()] = title
        self.wiki_link_titles[filename_stem.lower()] = title
        if filename_stem.startswith('_'):
            self.wiki_link_titles[filename_stem[1:].lower()] = title
        normalized_stem = filename_stem.lstrip('_').lstrip('0123456789.- ')
        if normalized_stem and normalized_stem.lower() != filename_stem.lower():
            self.wiki_link_titles[normalized_stem.lower()] = title
        return page_id

    def _pre_scan_wiki_links(self, files_to_process: List[str]):
        """Pre-scan all files to build wiki link mapping before rendering.
        
        This also caches the parsed recipes for later use.
        """
        for filename in files_to_process:
            filepath = find_file(self.input_roots, filename)
            if filepath is None:
                continue
            
            content = self.read_markdown_file(filename)
            filename_stem = Path(filename).stem
            
            if self.is_recipe_file(content):
                # Parse recipe to get title (this caches the recipe)
                recipe = self.get_or_parse_recipe(filename, content)
                # Fall back to the same default the renderer uses so the
                # registered anchor always matches the rendered page ID.
                recipe_title = recipe.get('title', '') or 'Untitled Recipe'
                if recipe_title:
                    # Generate the page ID (same logic as in page_renderer.py)
                    self._register_page_identity(recipe_title, filename_stem,
                                                 is_recipe=True)
            else:
                # For non-recipe content, prefer the page's authored title so
                # its anchor matches the one process_non_recipe_to_html emits.
                title = self._content_page_title(content, filename)
                self._register_page_identity(title, filename_stem,
                                             is_recipe=False)
    
    def _regenerate_structure(self):
        """Regenerate the cookbook structure markdown from the input directory.

        Always runs before a build so the cookbook always reflects the current
        state of the markdown files, even if the standalone structure script
        was not run. Uses the same StructureGenerator as
        main_generate_cookbook_structure.py (single source of truth).
        """
        from main_generate_cookbook_structure import StructureGenerator

        generator = StructureGenerator(directory=list(self.input_roots))
        output_path = generator.run()
        print(f"Regenerated cookbook structure: {output_path}")
        return output_path

    def _ensure_temp_dir(self):
        """Create the temp working folder if an external tool removed it."""
        if not self.temp_dir.exists():
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _sweep_stale_temp_dirs(self):
        """Delete leftover per-run working folders older than 24 hours.

        Per-run folders accumulate when a build crashes hard; without this
        sweep the system temp dir slowly fills with orphaned sheets.
        """
        base = Path(tempfile.gettempdir())
        for d in base.glob("cookbook_build_*"):
            if d == self.temp_dir:
                continue
            try:
                age_h = (time.time() - d.stat().st_mtime) / 3600
                if age_h > 24:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                continue

    def acquire_build_lock(self) -> bool:
        """Claim exclusive rights to run a build; False when one is running.

        The lock file lives next to the output so it is project-global and
        survives across different shells. Locks older than two hours are
        treated as stale leftovers from a crashed build and replaced.
        """
        lock_path = self.exports_dir / ".build.lock"
        try:
            if lock_path.exists():
                age_h = (time.time() - lock_path.stat().st_mtime) / 3600
                if age_h < 2:
                    print(
                        "ERROR: another cookbook build appears to be running "
                        f"(lock: {lock_path}, {age_h * 60:.0f} min old). "
                        "Wait for it to finish; if you are certain none is "
                        "running, delete the lock file and retry."
                    )
                    return False
                warn(f"removing stale build lock ({age_h:.1f} h old) from a crashed run")
                lock_path.unlink()
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self._build_lock_path = lock_path
            return True
        except FileExistsError:
            print(f"ERROR: another cookbook build appears to be running "
                  f"(lock: {lock_path}). If you are certain none is running, "
                  "delete the lock file and retry.")
            return False
        except OSError as exc:
            # Never brick builds over lock hygiene problems.
            warn(f"could not create build lock ({exc}); continuing without one")
            self._build_lock_path = None
            return True

    def release_build_lock(self):
        """Drop the build lock if we still own it."""
        if self._build_lock_path is not None:
            try:
                self._build_lock_path.unlink()
            except OSError:
                pass
            self._build_lock_path = None

    def _clear_temp_dir_contents(self):
        """Remove everything INSIDE the temp folder, keeping the folder itself.

        The folder itself must survive: this vault lives inside a Google
        Drive sync root, and delete+recreate of the folder races Drive's
        async reconciliation, which can delete its freshly recreated
        replacement mid-build (breaking every page write).
        """
        for entry in self.temp_dir.iterdir():
            try:
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink()
            except OSError as exc:
                warn(f"could not clear temp entry {entry}: {exc}")

    def _write_temp_html(self, filename_stem: str, html_content: str) -> str:
        """Write an intermediate HTML file, healing the temp dir once if an
        external tool (e.g. cloud-sync reconciliation) deleted it, and retrying
        transient OS/cloud-sync errors (permission lock, sharing violation) so
        a busy vault can never silently zero out a build.
        """
        html_path = self.temp_dir / f"{filename_stem}.html"
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                self.temp_dir.mkdir(parents=True, exist_ok=True)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                return str(html_path)
            except OSError as exc:
                # First failure: heal + retry once; second failure: report it so
                # the caller prints a visible per-file error instead of silently
                # dropping the page (others propagate to the caller check).
                last_exc = exc
                if attempt == 0:
                    continue
                raise
        raise last_exc  # pragma: no cover - loop always returns or raises above

    def write_generation_report(self):
        """Print the parse-quality summary and write exports/generation_report.md.

        Collects the per-file diagnostics gathered during tolerant recipe
        parsing so missing or non-standard information can never disappear
        silently again.
        """
        report_lines, counts = summarize_diagnostics(
            self._parse_diagnostics,
            self._split_diagnostics,
            self.link_stats,
        )

        report_text = '\n'.join(report_lines)

        print("\n" + report_text + "\n")
        report_path = self.exports_dir / "generation_report.md"
        try:
            md_text = render_report_markdown(
                report_lines, counts, self._split_diagnostics,
                unresolved_wiki_links=self.unresolved_wiki_links,
            )
            if self.link_stats:
                md_text += "\n## Navigation Links (ADR 0004)\n\n"
                for variant, stats in self.link_stats.items():
                    md_text += (
                        f"- **{variant}**: {stats['links_injected']} internal link(s) "
                        f"injected (of {stats['links_measured']} measured), "
                        f"{stats['toc_rows_stamped']} TOC row(s) stamped with page numbers, "
                        f"{stats.get('accent_underlines', 0)} accent underline(s), "
                        f"{stats.get('back_to_toc_links', 0)} back-to-TOC footer link(s)\n"
                    )
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(md_text + '\n')
            print(f"Generation report written to: {report_path}")
        except OSError as exc:
            warn(f"could not write generation report to {report_path}: {exc}")

    def _parity_blank_job(self, blank_no: int, chapter: str,
                          subsection: str) -> Tuple[str, str, str, bool]:
        """Write one blank parity sheet and return it as a pdf job tuple."""
        blank_html = TOCPageRenderer().blank_sheet_page()
        path = self._write_temp_html(f"temp_parity_blank_{blank_no:02d}",
                                     blank_html)
        return (path, chapter, subsection, False)

    def _insert_parity_blanks(self, pdf_jobs: List[Tuple[str, str, str, bool]],
                              chapter_blocks: List[Tuple[str, int, int]]) -> None:
        """Insert blank sheets so chapter blocks open on the correct side of
        a printed spread (ADR 0015).

        Page 1 (title page) is a right-hand page, so even 1-based page numbers
        print on the left. The title-verso blank (ADR 0019) is already part
        of ``pdf_jobs`` and counts here like any other sheet. Walking the
        book in order and counting real sheets per job (post-split, so
        continuation sheets count), each chapter block must satisfy:

        - with intro prose: the intro's first sheet lands on an even page and
          the sub-TOC on an odd page (a blank goes between when the intro
          spans an even number of sheets);
        - without intro prose: the sub-TOC lands on an odd page.

        Blanks join the chapter's (chapter, subsection) footer label, so they
        group and print footers/page numbers exactly like the pages they
        precede.
        """
        if not chapter_blocks:
            return

        parity_diags: List[Tuple[str, str]] = []
        blocks = {start: (label, count)
                  for label, start, count in chapter_blocks}

        def sheet_count(html_file: str) -> int:
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    return f.read().count('<div class="recipe-page')
            except OSError as exc:
                parity_diags.append(
                    ("error", f"parity: cannot read {html_file} ({exc}); "
                              "assuming 1 sheet"))
                return 1

        blank_no = 0
        jobs: List[Tuple[str, str, str, bool]] = []
        # Sheets placed so far; the next sheet lands on page `placed + 1`.
        placed = 0
        idx = 0
        while idx < len(pdf_jobs):
            if idx not in blocks:
                jobs.append(pdf_jobs[idx])
                placed += sheet_count(pdf_jobs[idx][0])
                idx += 1
                continue

            label, count = blocks[idx]
            block_jobs = pdf_jobs[idx:idx + count]
            has_intro = count >= 2
            chapter, subsection = block_jobs[0][1], block_jobs[0][2]

            def add_blank(position: str) -> None:
                nonlocal blank_no, placed
                blank_no += 1
                jobs.append(
                    self._parity_blank_job(blank_no, chapter, subsection))
                # The blank itself occupies the next physical page; the
                # counter must advance or every later parity decision in
                # this walk is computed from a stale count.
                placed += 1
                parity_diags.append(
                    ("info", f"parity: blank inserted {position} "
                             f"({label or 'chapter'}) (page {placed})"))

            if has_intro:
                if placed % 2 == 0:  # next page odd; text must open even
                    add_blank("before intro")
                for job in block_jobs[:-1]:  # intro pages (may span sheets)
                    jobs.append(job)
                    placed += sheet_count(job[0])
                if placed % 2 == 1:  # next page even; sub-TOC must open odd
                    add_blank("between intro and sub-TOC")
            else:
                if placed % 2 == 1:  # next page even; sub-TOC must open odd
                    add_blank("before sub-TOC")

            jobs.append(block_jobs[-1])  # the sub-TOC page
            placed += sheet_count(block_jobs[-1][0])
            idx += count

        if blank_no or parity_diags:
            pdf_jobs[:] = jobs
            self._split_diagnostics.extend(parity_diags)
            print(f"Chapter parity: {blank_no} blank sheet(s) inserted")

    def _cleanup_build_artifacts(self, pdf_jobs, section_pdfs):
        """Remove per-group PDFs and working HTML after shipping or failing."""
        for pdf in section_pdfs:
            try:
                Path(pdf).unlink()
            except Exception:
                pass
        for html_file in self.temp_dir.glob("*.html"):
            try:
                html_file.unlink()
            except Exception as e:
                warn(f"Could not delete {html_file}: {e}")

    @staticmethod
    def _dated_pdf_path(pdf_path: Path) -> Path:
        """Return a yyyyMMdd_HHmm historical sibling path for a PDF."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        return pdf_path.with_name(f"{pdf_path.stem}_{stamp}{pdf_path.suffix}")

    # ------------------------------------------------------------------
    # Build phases (ADR 0005: the entry point orchestrates only).
    # generate() below is an outline of these phases, in execution order.
    # Each phase owns its own sys.exit paths; nothing is reordered.
    # ------------------------------------------------------------------

    def _phase_detect_and_name(self, structure_file: str = None,
                               output_file: str = None):
        """Resolve the structure file and derive every output path."""
        # Auto-detect structure file if not provided (it lives in the
        # primary root).
        if structure_file is None:
            # First pass: look for generated structure file
            generated_candidates = list(self.input_dir.glob("_-*structure*generated*.md"))
            if generated_candidates:
                structure_file = generated_candidates[0].name
            else:
                # Second pass: fall back to any structure file
                for f in self.input_dir.glob("_-*.md"):
                    if "structure" in f.stem.lower():
                        structure_file = f.name
                        break

        if structure_file is None:
            raise ValueError("No structure file found")

        # Output naming (ADR 0004): the --output value is a STEM; each shipped
        # variant gets its own suffixed file. The unsuffixed book is retired -
        # there is no single "the PDF" anymore.
        if output_file is None:
            output_path = self.exports_dir / "cookbook.pdf"
        else:
            output_path = Path(output_file)
        book_stem = (output_path.stem if output_path.suffix.lower() == '.pdf'
                     else output_path.name)
        out_dir = output_path.parent
        variant_paths = {v: out_dir / f"{book_stem}_{v}.pdf"
                         for v in self.variants}
        partial_target = out_dir / f"{book_stem}_PARTIAL.pdf"
        # The merged working book lives in the working folder; only variants
        # ever land in the exports root.
        merged_base = self.temp_dir / f"{book_stem}_base.pdf"
        return structure_file, book_stem, variant_paths, partial_target, \
            merged_base

    def _phase_parse_structure(self, structure_file: str):
        """Parse the ordered file list, wiki links, footers and hierarchy."""
        print(f"Generating cookbook from: {structure_file}")
        print(f"Output: {', '.join(str(p) for p in self.variant_paths.values())}")

        # Parse structure to get ordered list of files
        files_to_process = self.structure_parser.parse_structure_file(structure_file)
        print(f"Found {len(files_to_process)} files to process")

        # Pre-scan: Build wiki link mapping from all files (also caches parsed recipes)
        self._pre_scan_wiki_links(files_to_process)

        # Build file -> (chapter, subsection) mapping for Playwright footers
        file_to_chapter_sub = self.structure_parser.get_file_to_chapter_subsection_mapping(structure_file)

        # Note: init_mermaid_renderer() is not called here - the browser will be
        # created by html_to_pdf.py and shared with mermaid_renderer.py via set_mermaid_browser()

        # Parse the structure hierarchy once: it feeds both the main TOC page
        # and the chapter main pages' deep sub-tables of contents. A chapter
        # subtree is keyed by its real markdown file (resolved "<name>.md").
        hierarchy = self.structure_parser.get_structure_hierarchy(structure_file)
        chapter_subtrees: Dict[str, Dict] = {}
        for section in hierarchy:
            chapter_file = self.structure_parser.resolve_page_file(section.get("name", ""))
            if chapter_file:
                chapter_subtrees[chapter_file] = section
        return files_to_process, file_to_chapter_sub, hierarchy, chapter_subtrees

    def _phase_check_empty_build(self, recipe_htmls, non_recipe_htmls,
                                 files_to_process) -> None:
        """Abort loudly instead of overwriting a good book with an empty stub."""
        if len(recipe_htmls) == 0 and len(non_recipe_htmls) == 0 and len(files_to_process) > 0:
            fatal("no pages were generated although "
                  f"{len(files_to_process)} files were queued. Aborting instead of "
                  "overwriting the previous cookbook with an empty stub PDF.")

    def _phase_generate_html(self, files_to_process, chapter_subtrees):
        """Render every source file into sheet HTML in the working folder."""
        # Generate all HTML files
        print("Generating HTML files...")

        recipe_htmls = {}
        non_recipe_htmls = []

        for filename in files_to_process:
            filepath = find_file(self.input_roots, filename)
            if filepath is None:
                continue

            content = self.read_markdown_file(filename)

            # Big chapters render as main pages: intro page + sub-TOC page
            # (ADR 0015)
            if filename in chapter_subtrees:
                title = filename.replace('.md', '').replace('_', ' ').title()
                _, html_paths = self.process_chapter_to_html(
                    filename, content, title,
                    chapter_subtrees[filename])
                for html_path in html_paths:
                    non_recipe_htmls.append((filename, html_path))
                continue

            if self.is_recipe_file(content):
                html_content, html_path = self.process_recipe_to_html(filename, content)
                if html_content and html_path:
                    recipe_htmls[filename] = html_path
            else:
                title = self._content_page_title(content, filename)
                _, html_path = self.process_non_recipe_to_html(filename, content, title)
                if html_path:
                    non_recipe_htmls.append((filename, html_path))

        print(f"Generated {len(recipe_htmls)} recipe HTMLs and {len(non_recipe_htmls)} content HTMLs")
        return recipe_htmls, non_recipe_htmls

    def _phase_report_unresolved_links(self) -> None:
        """Warn about (or, in strict mode, abort on) unresolved wiki links."""
        # Aggregated report for unresolved wiki links (instead of noisy per-link lines)
        if self.unresolved_wiki_links:
            print(f"\nWARNING: {len(self.unresolved_wiki_links)} unresolved wiki link(s):")
            for ref, source_filenames in self.unresolved_wiki_links.items():
                sources = ", ".join(sorted(source_filenames))
                print(f"  - [[{ref}]] (found in: {sources})")
            print("  These references point to pages that do not exist in the structure;")
            print("  they are rendered as plain text so the PDF has no broken links.\n")
            if getattr(self, "_strict_wiki_links", False):
                print("ERROR: --strict-wiki-links set and unresolved wiki links remain.")
                close_browser_pool()
                return

    def _phase_copy_lib(self) -> None:
        """Copy lib/ next to the sheets so templates resolve relative refs."""
        # Copy lib folder into the temp dir for PDF conversion (mermaid.min.js, etc.).
        # It must sit next to the generated HTML files because the templates
        # reference it via relative paths (lib/mermaid.min.js).
        script_dir = Path(__file__).parent.resolve()
        lib_src = script_dir / "lib"
        lib_dst = self.temp_dir / "lib"
        if lib_src.exists():
            lib_dst.mkdir(parents=True, exist_ok=True)
            for src_file in lib_src.rglob('*'):
                if src_file.is_file():
                    rel = src_file.relative_to(lib_src)
                    dst_file = lib_dst / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
            print(f"Copied {lib_src} to {lib_dst}")

    def _phase_layout_pass(self, pdf_jobs) -> None:
        """Bake mermaid diagrams and browser-split oversized sheets (ADR 0002)."""
        # Browser-measured splitting (ADR 0002): any source whose content
        # exceeds the sheet's content limit is rebuilt into continuation
        # sheets so nothing ever prints across the footer band.
        # Mermaid blocks are baked to static SVGs first: the splitter must
        # measure real diagram geometry (and slice oversized diagrams), not
        # raw source-text heights.
        # Every per-job step carries its own try/except: one unreadable sheet
        # or failed split must not abort the whole layout pass (that used to
        # mask external file deletion as a single "skipped" warning).
        total_jobs = len(pdf_jobs)
        for job_no, (job_file, _chapter, _subsection, _is_notdone) in enumerate(pdf_jobs, start=1):
            job_name = Path(job_file).name
            print(f"[layout {job_no}/{total_jobs}] {job_name}", flush=True)
            try:
                with open(job_file, 'r', encoding='utf-8') as f:
                    txt = f.read()
            except OSError as exc:
                print(f"Warning: cannot read {job_file} for layout pass: {exc}")
                self._split_diagnostics.append(
                    ("error", f"{job_name}: unreadable during layout pass ({exc})"))
                continue
            if 'class="mermaid"' in txt:
                # bake_mermaid_in_file returns False only when the page has no
                # mermaid blocks at all; render failures raise RuntimeError
                # (see mermaid_renderer.bake_mermaid_in_file).
                try:
                    bake_mermaid_in_file(job_file, _get_browser())
                except Exception as exc:
                    print(f"Warning: mermaid bake failed for {job_file}: {exc}")
                    self._split_diagnostics.append(
                        ("error", f"{job_name}: mermaid bake failed ({exc})"))
            try:
                diags = split_page_file(str(job_file))
            except Exception as exc:
                print(f"Warning: split failed for {job_file}: {exc}")
                self._split_diagnostics.append(
                    ("error", f"{job_name}: split failed ({exc})"))
                continue
            if diags:
                self._split_diagnostics.extend(diags)
        if self._split_diagnostics:
            print(f"Layout splitting: {len(self._split_diagnostics)} diagnostic(s)")

    def _phase_assemble_jobs(self, files_to_process, file_to_chapter_sub,
                             hierarchy, chapter_subtrees, recipe_htmls,
                             non_recipe_htmls):
        """Build front matter + per-file pdf jobs and chapter blocks (ADR 0015)."""
        # Build list of (html_file, chapter, subsection, is_notdone) tuples for per-file PDF generation.
        # Each file gets its own Playwright footer so multi-page content still shows the
        # chapter/section/page-number bar on every physical page.
        pdf_jobs: List[Tuple[str, str, str, bool]] = []

        # Title page: no chapter/section
        title_content = "<h2>Modular Flavour</h2>"
        title_html = ContentPageRenderer().render("Modular Flavour", title_content)
        title_html_file = self._write_temp_html('temp_title', title_html)
        pdf_jobs.append((str(title_html_file), '', '', False))

        # Title verso (ADR 0019): one blank carrier sheet right after the
        # title page, so the front matter opens on a fresh page. It joins
        # the TOC's footer label (ADR 0015 rule for blanks) and counts as a
        # real sheet, shifting every later page number by exactly one.
        verso_blank_html = TOCPageRenderer().blank_sheet_page()
        verso_blank_file = self._write_temp_html('temp_title_verso',
                                                  verso_blank_html)
        pdf_jobs.append((str(verso_blank_file), TOC_PAGE_TITLE, '', False))

        # TOC page; every resolvable entry becomes an internal link through
        # the shared wiki-link mechanism (ADR 0004). The hierarchy was parsed
        # above and is shared with the chapter main pages.
        toc_html = TOCPageRenderer().render(
            TOC_PAGE_TITLE, hierarchy,
            link_resolver=lambda ref: self._resolve_wiki_page(ref)[0],
        )
        toc_html_file = self._write_temp_html('temp_toc', toc_html)
        pdf_jobs.append((str(toc_html_file), TOC_PAGE_TITLE, '', False))

        non_recipe_lookup = defaultdict(list)
        for filename, html_path in non_recipe_htmls:
            non_recipe_lookup[filename].append(html_path)

        # Chapter blocks in book order: (chapter label, first job index,
        # page count) - consumed by the parity pass (ADR 0015).
        chapter_blocks: List[Tuple[str, int, int]] = []

        for filename in files_to_process:
            chapter, subsection = file_to_chapter_sub.get(filename, ('', ''))
            if filename in chapter_subtrees and not chapter:
                # Chapter main pages carry their own chapter footer label so
                # the footer bar matches the pages that follow them.
                chapter = display_parts(
                    chapter_subtrees[filename].get("name", ""))[1]
            is_notdone = self._is_notdone_file(filename)
            if chapter and chapter.lower() == 'outro':
                full_toc_html = TOCPageRenderer().render_full_toc(
                    TOC_PAGE_TITLE, hierarchy,
                    link_resolver=lambda ref: self._resolve_wiki_page(ref)[0],
                )
                full_toc_file = self._write_temp_html('temp_full_toc', full_toc_html)
                pdf_jobs.append((str(full_toc_file), TOC_PAGE_TITLE, '', False))
            if filename in recipe_htmls:
                pdf_jobs.append((recipe_htmls[filename], chapter, subsection, is_notdone))
            elif filename in non_recipe_lookup:
                # Add all pages for this filename (intro page + sub-TOC page).
                # Chapter blocks are recorded so the parity pass (ADR 0015)
                # knows where each block starts and how many pages it has.
                if filename in chapter_subtrees:
                    chapter_blocks.append(
                        (chapter, len(pdf_jobs),
                         len(non_recipe_lookup[filename])))
                for html_path in non_recipe_lookup[filename]:
                    pdf_jobs.append((html_path, chapter, subsection, is_notdone))

        return pdf_jobs, chapter_blocks

    def _phase_convert_groups(self, pdf_jobs, partial_target, merged_base):
        """Convert grouped sheets to PDFs; measure navigation; guard failures."""
        # Group consecutive jobs that share the same (chapter, section). Each group
        # becomes one PDF — Chrome only embeds the font subset once per PDF, so
        # grouping collapses ~84 individual PDFs into ~20 and avoids tens of MB of
        # duplicated font data in the final merged file.
        groups: List[Tuple[str, str, List[str]]] = []
        for html_file, chapter, subsection, _is_notdone in pdf_jobs:
            if groups and groups[-1][0] == chapter and groups[-1][1] == subsection:
                groups[-1][2].append(html_file)
            else:
                groups.append((chapter, subsection, [html_file]))

        # External-interference guard: sync engines (this vault can live in a
        # Google Drive sync root) have been observed deleting fresh sheets
        # mid-build. Converting anyway would combine zero-page groups into
        # blank PDFs and silently ship a partial cookbook - stop loudly here.
        missing_jobs = [job for job, _chapter, _subsection, _is_notdone in pdf_jobs
                        if not os.path.exists(job)]
        if missing_jobs:
            print(f"\nERROR: {len(missing_jobs)} generated sheet(s) disappeared "
                  "before PDF conversion:")
            for missing in missing_jobs[:10]:
                print(f"  - {missing}")
            if len(missing_jobs) > 10:
                print(f"  ... and {len(missing_jobs) - 10} more")
            print("An external tool (cloud-sync reconciliation, antivirus, or a")
            print("sync rule) is deleting files from the working directory")
            print("mid-build. Generate with the working dir outside the synced")
            print("tree (the default), or pause syncing while generating.")
            close_browser_pool()
            sys.exit(1)

        print(f"Converting {len(pdf_jobs)} HTML files into {len(groups)} group PDFs...")

        section_pdfs: List[str] = []
        failed_groups: List[str] = []
        global_page_offset = 1

        for idx, (chapter, subsection, files) in enumerate(groups):
            pdf_path = self.temp_dir / f"temp_part_{idx:03d}.pdf"
            label = chapter if chapter else (subsection or "(front matter)")
            if chapter and subsection:
                label = f"{chapter} - {subsection}"
            group_start_page = global_page_offset
            print(f"[pdf {idx + 1}/{len(groups)}] {label} "
                  f"({len(files)} sheet(s))", flush=True)
            footer_html = build_footer_template(chapter, subsection, start_page=global_page_offset)
            measured_batch: List[dict] = []

            def _measure_navigation(page, _batch=measured_batch):
                try:
                    return collect_navigation_geometry(page)
                except Exception:
                    self._nav_measurement_failures += 1
                    raise

            result = html_to_pdf_combined_with_footer(
                files,
                str(pdf_path),
                footer_html,
                temp_html_name=f"temp_combined_{idx:03d}.html",
                measure_cb=_measure_navigation,
                measure_result=measured_batch,
            )
            if result:
                section_pdfs.append(str(pdf_path))
                reader = PdfReader(str(pdf_path))
                num_pages = len(reader.pages)
                # Commit measurements only for groups that actually printed;
                # a failed conversion's geometry would misalign every page.
                for payload in measured_batch:
                    self._nav_geometry.commit_group(payload, group_start_page)
                global_page_offset += num_pages
            else:
                failed_groups.append(f"{chapter} / {subsection}")

        if failed_groups:
            warn(f"{len(failed_groups)} group(s) failed to convert")
            for f in failed_groups:
                print(f"  - {f}")

        if not section_pdfs:
            print("Error: No PDFs were generated")
            close_browser_pool()
            sys.exit(1)

        # Resolve loved recipes to their first physical sheets via the
        # measured ADR 0004 page map; unmeasured ids simply get no heart.
        loved_pages = {self._nav_geometry.page_map[page_id] - 1
                       for page_id in self._loved_page_ids
                       if page_id in self._nav_geometry.page_map}
        if self._loved_page_ids:
            print(f"Loved recipes: heart behind the page number on "
                  f"{len(loved_pages)} sheet(s)")

        # Never overwrite good books with an incomplete build: failed groups
        # mean missing pages, so a partial merge goes to a separate
        # *_PARTIAL.pdf and the run exits non-zero.
        partial_build = bool(failed_groups)
        if partial_build:
            print(f"Merging {len(section_pdfs)} PDFs into {partial_target} "
                  f"(shipped variants stay untouched)...")
            self.pdf_builder.merge_pdfs(section_pdfs, str(partial_target))
            self.add_global_page_numbers(str(partial_target), loved_pages=loved_pages)
            self._cleanup_build_artifacts(pdf_jobs, section_pdfs)
            close_browser_pool()
            print("\nERROR: build incomplete - some groups failed to convert; "
                  "see the warnings above. Fix the cause and regenerate.")
            sys.exit(1)

        print(f"Merging {len(section_pdfs)} PDFs into working copy...")
        self.pdf_builder.merge_pdfs(section_pdfs, str(merged_base))
        self.add_global_page_numbers(str(merged_base), loved_pages=loved_pages)
        return section_pdfs

    def _phase_inject_and_ship(self, pdf_jobs, section_pdfs, merged_base,
                               variant_paths, partial_target, book_stem) -> None:
        """Inject navigation into both variants and ship them (ADR 0004)."""
        # Inject navigation (ADR 0004): GoTo annotations for every measured
        # link plus printed TOC leader lines/page numbers in both variants;
        # green accent underlines only in the digital variant. The digital
        # variant additionally gets a "back to table of contents" footer
        # link on every page from the TOC onwards. A gate violation must
        # never ship a book with broken links.
        injection_error = None
        # The TOC sheet's measured physical page: the digital variant's
        # back-to-TOC footer link targets it (print variant: unused).
        toc_page = self._nav_geometry.page_map.get(
            'page-' + clean_title_id(TOC_PAGE_TITLE))
        try:
            if self._nav_measurement_failures:
                raise LinkInjectionError(
                    f"{self._nav_measurement_failures} group(s) failed "
                    "in-browser navigation measurement; their links would "
                    "silently be missing from the shipped books.")
            for variant in self.variants:
                summary = inject_navigation(
                    input_pdf=str(merged_base),
                    output_pdf=str(variant_paths[variant]),
                    geometry=self._nav_geometry,
                    accent_links=(variant == "digital"),
                    back_to_toc_page=(toc_page if variant == "digital"
                                      else None),
                )
                self.link_stats[variant] = summary
                print(f"[{variant}] injected {summary['links_injected']} internal "
                      f"link(s), stamped {summary['toc_rows_stamped']} TOC row(s), "
                      f"{summary['back_to_toc_links']} back-to-TOC footer link(s) "
                      f"-> {summary['output']}")
        except LinkInjectionError as exc:
            injection_error = str(exc)

        if injection_error:
            for path in variant_paths.values():
                Path(path).unlink(missing_ok=True)
            shutil.copyfile(merged_base, partial_target)
            self._cleanup_build_artifacts(pdf_jobs, section_pdfs)
            close_browser_pool()
            print(f"\nERROR: internal-link gate failed: {injection_error}")
            print(f"A partial book was written to {partial_target}; "
                  "no variant was shipped.")
            sys.exit(1)

        # Retire the legacy unsuffixed artifact so no stale book can
        # masquerade as current after this run.
        legacy_default = self.exports_dir / "Cookbook.pdf"
        if book_stem == "Cookbook" and legacy_default.exists():
            try:
                legacy_default.unlink()
                print(f"Removed legacy unsuffixed book: {legacy_default}")
            except OSError as exc:
                print(f"Warning: could not remove legacy book "
                      f"{legacy_default}: {exc}")

    def _phase_finish(self, pdf_jobs, section_pdfs, variant_paths) -> None:
        """Final report, cleanup, output check and historic digital copy."""
        # Re-render the report so it also carries the navigation stats.
        self.write_generation_report()

        self._cleanup_build_artifacts(pdf_jobs, section_pdfs)

        # Clean up browser pool
        close_browser_pool()

        missing_outputs = [v for v in self.variants if not variant_paths[v].exists()]
        if missing_outputs:
            print(f"Error: output file(s) not created: "
                  f"{', '.join(str(variant_paths[v]) for v in missing_outputs)}")
            sys.exit(1)

        historic_digital_path = None
        if "digital" in self.variants:
            digital_path = variant_paths["digital"]
            historic_digital_path = self._dated_pdf_path(digital_path)
            try:
                shutil.copyfile(digital_path, historic_digital_path)
            except OSError as exc:
                print(f"Error: could not write historic digital cookbook "
                      f"{historic_digital_path}: {exc}")
                sys.exit(1)

        print("\nCookbooks generated:")
        for variant in self.variants:
            path = variant_paths[variant]
            size_mb = path.stat().st_size / 1024 / 1024
            print(f"  [{variant:>7}] {path} ({size_mb:.2f} MB)")
        if historic_digital_path is not None:
            size_mb = historic_digital_path.stat().st_size / 1024 / 1024
            print(f"  [historic] {historic_digital_path} ({size_mb:.2f} MB)")

    _WATERMARK_CSS = """\
.notdone-watermark::after {
    content: "miró not happy yet";
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-45deg);
    color: rgba(220, 38, 38, 0.18);
    font-family: 'Manrope', 'Work Sans', 'Plus Jakarta Sans', Arial, sans-serif;
    font-size: 7rem;
    font-weight: 700;
    white-space: nowrap;
    pointer-events: none;
    z-index: 50;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}"""

    def _inject_notdone_watermark(self, html_path: str) -> None:
        """Add the ``notdone-watermark`` class and CSS to a sheet HTML file."""
        path = Path(html_path)
        if not path.exists():
            return
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        if 'notdone-watermark' in html:
            return
        html = html.replace('<div class="recipe-page"', '<div class="recipe-page notdone-watermark"')
        html = html.replace('</style>', self._WATERMARK_CSS + '\n</style>', 1)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)

    def generate(self, structure_file: str = None, output_file: str = None):
        """
        Generate the complete cookbook PDFs.

        Args:
            structure_file: Name of the structure file (default: auto-detect)
            output_file: Output stem/path; each shipped variant is written as
                ``<stem>_<variant>.pdf`` (default stem: exports/cookbook)
        """
        # Always regenerate the structure file first so auto-detection and the
        # parsed file list reflect the current markdown files.
        self._regenerate_structure()

        # One build at a time: concurrent runs wipe each other's working
        # folders and race for exports/Cookbook.pdf.
        if not self.acquire_build_lock():
            sys.exit(1)

        structure_file, book_stem, variant_paths, partial_target, \
            merged_base = self._phase_detect_and_name(
                structure_file, output_file)
        self.variant_paths = variant_paths

        # Reset the temporary working folder contents so every build starts
        # clean and only the final PDF resides in the exports root afterwards.
        # NOTE: only the CONTENTS are cleared, never the folder itself - when
        # the working folder sits inside a sync root (--temp-dir), delete+
        # recreate races the sync engine's reconciliation, which can delete
        # the freshly recreated folder mid-build (breaking every page write).
        self._ensure_temp_dir()
        self._clear_temp_dir_contents()

        files_to_process, file_to_chapter_sub, hierarchy, chapter_subtrees = \
            self._phase_parse_structure(structure_file)

        recipe_htmls, non_recipe_htmls = self._phase_generate_html(
            files_to_process, chapter_subtrees)

        self._phase_check_empty_build(recipe_htmls, non_recipe_htmls,
                                      files_to_process)

        self._phase_report_unresolved_links()

        self._phase_copy_lib()

        pdf_jobs, chapter_blocks = self._phase_assemble_jobs(
            files_to_process, file_to_chapter_sub, hierarchy, chapter_subtrees,
            recipe_htmls, non_recipe_htmls)

        self._phase_layout_pass(pdf_jobs)

        # Chapter-spread parity (ADR 0015): insert blank carrier sheets so
        # every chapter opens its text on an even (left) page and its
        # sub-TOC on an odd (right) page. Runs after splitting (continuation
        # sheets count as pages) and before the report (insertions logged).
        self._insert_parity_blanks(pdf_jobs, chapter_blocks)

        for job_file, _chapter, _subsection, is_notdone in pdf_jobs:
            if is_notdone:
                self._inject_notdone_watermark(job_file)

        # Persist the aggregated report now that parse and layout diagnostics
        # are both collected (ADR 0002).
        self.write_generation_report()

        section_pdfs = self._phase_convert_groups(pdf_jobs, partial_target,
                                                  merged_base)

        self._phase_inject_and_ship(pdf_jobs, section_pdfs, merged_base,
                                    variant_paths, partial_target, book_stem)

        self._phase_finish(pdf_jobs, section_pdfs, variant_paths)
def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate cookbook PDF")
    parser.add_argument("--input-dir", default=None,
                       help="Input directory (or comma-separated list of "
                            "directories) with markdown files "
                            "(default: <script parent>/data_modularflavour/text "
                            "+ data_modularflavour/text_notdone)")
    parser.add_argument("--structure", 
                       help="Structure file name (auto-detect if not provided)")
    parser.add_argument("--output",
                        help="Output PDF stem or path (default: exports/cookbook -> "
                            "cookbook_print.pdf + cookbook_digital.pdf)")
    parser.add_argument("--strict-wiki-links", action="store_true",
                       help="Exit with an error if any [[wiki links]] cannot be resolved")
    parser.add_argument("--variants", default="print,digital",
                        help="Comma-separated shipped variants (subset of: print,digital). "
                             "print = invisible internal links; digital = green-accented links.")
    parser.add_argument("--temp-dir",
                       help="Working directory for intermediate build files "
                            "(default: system temp, outside any sync root)")

    args = parser.parse_args()

    valid_variants = ("print", "digital")
    requested_variants = tuple(v.strip() for v in args.variants.split(",") if v.strip())
    invalid = [v for v in requested_variants if v not in valid_variants]
    if invalid or not requested_variants:
        parser.error("--variants must be a non-empty comma list drawn from: "
                     f"{', '.join(valid_variants)} (got: {args.variants!r})")

    requested_input_dirs = (
        [d.strip() for d in args.input_dir.split(",") if d.strip()]
        if args.input_dir else None
    )
    generator = CookbookGenerator(input_dir=requested_input_dirs, temp_dir=args.temp_dir)
    generator._strict_wiki_links = args.strict_wiki_links
    generator.variants = requested_variants
    try:
        generator.generate(structure_file=args.structure, output_file=args.output)
    finally:
        generator.release_build_lock()


if __name__ == "__main__":
    main()
