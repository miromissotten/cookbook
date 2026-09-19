"""
PDF Builder module for generating cookbook PDFs.
Handles the merge step: each group's sheets are printed by Chromium (html_to_pdf)
and stitched into the book's merged base here.
"""

from pathlib import Path
from typing import List

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter


class PDFBuilder:
    """Build PDF documents for cookbook content."""

    def merge_pdfs(self, pdf_files: List[str], output_file: str) -> str:
        """Merge multiple PDFs into one; recompress with pikepdf when available."""
        writer = PdfWriter()

        for pdf_file in pdf_files:
            if Path(pdf_file).exists():
                reader = PdfReader(pdf_file)
                for page in reader.pages:
                    writer.add_page(page)

        with open(output_file, 'wb') as f:
            writer.write(f)

        # PyPDF2's merge preserves every embedded font stream as-is. Re-saving with
        # pikepdf roughly halves the file by recompressing flate streams and reusing
        # identical indirect objects across pages.
        try:
            import pikepdf
            src = pikepdf.open(output_file, allow_overwriting_input=True)
            src.save(
                output_file,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                recompress_flate=True,
            )
            src.close()
        except ImportError:
            pass
        except Exception as e:
            print(f"Warning: pikepdf recompression skipped: {e}")

        return output_file
