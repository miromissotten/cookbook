"""
Generate a PDF containing only the Table of Contents and chapter sub-TOC pages.

This is a specialized entry point that builds a slim PDF with:
1. The main Table of Contents page (hierarchy accent-row layout)
2. Each chapter's sub-TOC page (intro prose + deep flavour-tree layout)

Useful for quickly reviewing the TOC layout without generating the full cookbook.
"""

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter

# Ensure this script's directory and the helpers directory are importable
# so this entry point works regardless of the current working directory.
_SCRIPT_DIR = Path(__file__).parent.resolve()
_HELPERS_DIR = _SCRIPT_DIR / "helpers"
for _dir in (_SCRIPT_DIR, _HELPERS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

# Import modules
from structure_parser import StructureParser
from input_roots import PathSpec, find_file, resolve_roots
from page_toc import TOCPageRenderer
from html_to_pdf import (
    html_to_pdf_combined_with_footer,
    build_footer_template,
    close_browser_pool,
    _get_browser,
)
from mermaid_renderer import bake_mermaid_in_file
from page_splitter import split_page_file


class TOCSubTOCGenerator:
    """Generate a PDF with only the TOC and chapter sub-TOC pages."""

    def __init__(self, input_dir: Optional[PathSpec] = None, temp_dir: Optional[str] = None):
        # Both text folders form one virtual input (ADR 0023); the first
        # root wins filename collisions and hosts the structure file.
        self.input_roots = resolve_roots(input_dir)
        self.input_dir = self.input_roots[0]
        self.exports_dir = Path("exports")

        # Same temp directory strategy as CookbookGenerator: outside the vault
        # by default to avoid cloud-sync reconciliation deleting files mid-build.
        if temp_dir:
            self.temp_dir = Path(temp_dir)
        else:
            self.temp_dir = (Path(tempfile.gettempdir())
                             / f"cookbook_toc_build_{os.getpid()}")

        # Initialize components
        self.structure_parser = StructureParser(input_dir)

    def _regenerate_structure(self):
        """Regenerate the structure file to reflect current markdown state."""
        from main_generate_cookbook_structure import StructureGenerator
        generator = StructureGenerator(directory=list(self.input_roots))
        generator.generate_structure_file()

    def _ensure_temp_dir(self):
        """Create the working folder if it doesn't exist."""
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _clear_temp_dir_contents(self):
        """Remove all files inside the working folder (not the folder itself)."""
        for item in self.temp_dir.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError:
                pass

    def _write_temp_html(self, name: str, html_content: str) -> Path:
        """Write HTML content to a file in the temp directory."""
        self._ensure_temp_dir()
        html_path = self.temp_dir / f"{name}.html"
        html_path.write_text(html_content, encoding="utf-8")
        return html_path

    def read_markdown_file(self, filename: str) -> Optional[str]:
        """Read a markdown file from the input roots (first root wins)."""
        filepath = find_file(self.input_roots, filename)
        if filepath is None:
            return None
        try:
            return filepath.read_text(encoding="utf-8")
        except OSError:
            return None

    def _resolve_wiki_page(self, ref: str) -> Tuple[str, str]:
        """Resolve a wiki-link reference to a page anchor id and display text."""
        clean = ref.replace(' ', '-').replace('_', '-').lower()
        clean = re.sub(r'[^a-z0-9\-]', '', clean)
        return f"page-{clean}", ref

    def generate(self, structure_file: str = None, output_file: str = None):
        """
        Generate the TOC/sub-TOC PDF.

        Args:
            structure_file: Name of the structure file (default: auto-detect)
            output_file: Output PDF path (default: exports/Cookbook_TOC.pdf)
        """
        # Always regenerate the structure file first
        self._regenerate_structure()

        # Auto-detect structure file if not provided
        if structure_file is None:
            generated_candidates = list(self.input_dir.glob("_-*structure*generated*.md"))
            if generated_candidates:
                structure_file = generated_candidates[0].name
            else:
                for f in self.input_dir.glob("_-*.md"):
                    if "structure" in f.stem.lower():
                        structure_file = f.name
                        break

        if structure_file is None:
            raise ValueError("No structure file found")

        # Output path
        if output_file is None:
            output_path = self.exports_dir / "Cookbook_TOC.pdf"
        else:
            output_path = Path(output_file)

        # Ensure exports directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Reset working folder
        self._ensure_temp_dir()
        self._clear_temp_dir_contents()

        print(f"Generating TOC/sub-TOC PDF from: {structure_file}")
        print(f"Output: {output_path}")

        # Parse the structure hierarchy
        hierarchy = self.structure_parser.get_structure_hierarchy(structure_file)
        chapter_subtrees: Dict[str, Dict] = {}
        for section in hierarchy:
            chapter_file = self.structure_parser.resolve_page_file(section.get("name", ""))
            if chapter_file:
                chapter_subtrees[chapter_file] = section

        # Collect HTML files to convert
        html_files: List[Tuple[str, Path]] = []  # (name, html_path)

        # 1. Main TOC page
        print("Generating main TOC page...")
        toc_html = TOCPageRenderer().render(
            "Table of Contents", hierarchy,
            link_resolver=lambda ref: self._resolve_wiki_page(ref)[0])
        toc_path = self._write_temp_html("toc_main", toc_html)
        html_files.append(("toc_main", toc_path))
        print(f"  Main TOC: {toc_path}")

        # 2. Chapter sub-TOC pages
        print("Generating chapter sub-TOC pages...")
        for chapter_file, subtree in chapter_subtrees.items():
            filename = chapter_file
            content = self.read_markdown_file(filename)
            if content is None:
                print(f"  Warning: could not read {filename}, skipping")
                continue

            title = filename.replace('.md', '').replace('_', ' ').title()
            chapter_name = Path(filename).stem

            # Render chapter sub-TOC and intro as separate pages
            prose_html = ""
            if content.strip():
                import markdown as md
                prose_html = md.markdown(content, extensions=['fenced_code', 'tables'])

            chapter_pages = TOCPageRenderer().render_chapter(
                title, subtree, content_html=prose_html,
                link_resolver=lambda ref: self._resolve_wiki_page(ref)[0])

            # Write each page to a separate HTML file
            for i, page_html in enumerate(chapter_pages):
                if len(chapter_pages) > 1:
                    page_name = f"chapter_{chapter_name}_page{i+1}"
                else:
                    page_name = f"chapter_{chapter_name}"
                chapter_path = self._write_temp_html(page_name, page_html)
                html_files.append((page_name, chapter_path))
                if i == 0 and len(chapter_pages) > 1:
                    print(f"  Chapter intro: {chapter_path}")
                else:
                    print(f"  Chapter sub-TOC: {chapter_path}")

        # Copy lib folder for PDF conversion
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
            print(f"Copied lib folder to {lib_dst}")

        # Process each HTML file: bake mermaid, split, convert to PDF
        print("Converting to PDF...")
        pdf_files: List[str] = []

        for name, html_path in html_files:
            print(f"  Processing {name}...")

            # Bake mermaid diagrams if present
            try:
                with open(html_path, 'r', encoding='utf-8') as f:
                    txt = f.read()
                if 'class="mermaid"' in txt:
                    print(f"    Baking mermaid diagrams...")
                    bake_mermaid_in_file(html_path, _get_browser())
            except Exception as exc:
                print(f"    Warning: mermaid bake failed for {name}: {exc}")

            # Split page file (handles overflow)
            try:
                split_page_file(html_path)
            except Exception as exc:
                print(f"    Warning: split failed for {name}: {exc}")

            # Convert to PDF
            try:
                pdf_path = html_path.with_suffix('.pdf')
                footer_html = build_footer_template("", "", start_page=1)
                result = html_to_pdf_combined_with_footer(
                    [str(html_path)],
                    str(pdf_path),
                    footer_html
                )
                if result and pdf_path.exists():
                    pdf_files.append(str(pdf_path))
                    print(f"    Created: {pdf_path}")
                else:
                    print(f"    Warning: PDF not created for {name}")
            except Exception as exc:
                print(f"    Warning: PDF conversion failed for {name}: {exc}")

        # Merge all PDFs into one
        if not pdf_files:
            print("ERROR: no PDF files were generated. Aborting.")
            close_browser_pool()
            sys.exit(1)

        print(f"Merging {len(pdf_files)} PDF(s) into final output...")
        writer = PdfWriter()
        for pdf_file in pdf_files:
            try:
                reader = PdfReader(pdf_file)
                for page in reader.pages:
                    writer.add_page(page)
            except Exception as exc:
                print(f"  Warning: could not read {pdf_file}: {exc}")

        # Write merged PDF
        with open(output_path, 'wb') as f:
            writer.write(f)

        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"\nTOC/sub-TOC PDF generated: {output_path} ({size_mb:.2f} MB)")

        # Cleanup
        close_browser_pool()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a PDF with only the Table of Contents and chapter sub-TOC pages")
    parser.add_argument("--input-dir", default=None,
                        help="Input directory (or comma-separated list of "
                             "directories) with markdown files "
                             "(default: data_modularflavour/text + "
                             "data_modularflavour/text_notdone)")
    parser.add_argument("--structure",
                        help="Structure file name (auto-detect if not provided)")
    parser.add_argument("--output",
                        help="Output PDF path (default: exports/Cookbook_TOC.pdf)")
    parser.add_argument("--temp-dir",
                        help="Working directory for intermediate build files "
                             "(default: system temp, outside any sync root)")

    args = parser.parse_args()

    generator = TOCSubTOCGenerator(input_dir=args.input_dir, temp_dir=args.temp_dir)
    generator.generate(structure_file=args.structure, output_file=args.output)


if __name__ == "__main__":
    main()

