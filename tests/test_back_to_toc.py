"""Behavioural tests for the digital variant's back-to-TOC footer link.

Covers the ADR 0004 amendment: inject_navigation stamps a footer GoTo link
("back to table of contents") on every page from the TOC onwards in the
digital variant only, and gates against a missing/invalid TOC page.

Run: python -m unittest tests.test_back_to_toc -v
"""
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from link_injection import (
    LinkInjectionError,
    NavigationGeometry,
    inject_navigation,
)


def _make_pdf(path: Path, num_pages: int) -> None:
    """Tiny blank A4 PDF with num_pages pages."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=595.28, height=841.89)
    with open(path, "wb") as f:
        writer.write(f)


def _link_annotation_pages(pdf_path: Path):
    """0-based pages carrying /Link annotations -> their dest page indices."""
    hits = {}
    for idx, page in enumerate(PdfReader(str(pdf_path)).pages):
        for aref in page.get("/Annots") or []:
            obj = aref.get_object()
            if obj.get("/Subtype") == "/Link":
                dest = obj.get("/Dest")
                target = dest[0]
                if hasattr(target, "get_object"):
                    target = target
                hits.setdefault(idx, []).append(obj)
    return hits


class BackToTocTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.input_pdf = self.tmp / "base.pdf"
        _make_pdf(self.input_pdf, 5)
        self.geometry = NavigationGeometry()

    def tearDown(self):
        self._tmp.cleanup()

    def test_digital_stamps_footer_link_from_toc_onwards(self):
        out = self.tmp / "digital.pdf"
        summary = inject_navigation(
            str(self.input_pdf), str(out), self.geometry,
            accent_links=True, back_to_toc_page=3)
        self.assertEqual(summary["back_to_toc_links"], 2)  # 0-based pages 3, 4
        hits = _link_annotation_pages(out)
        self.assertEqual(sorted(hits), [3, 4])
        reader = PdfReader(str(out))
        for page_annots in hits.values():
            for obj in page_annots:
                target = obj["/Dest"][0]
                if isinstance(target, (int, float)):
                    target_idx = int(target)
                else:
                    # Indirect reference: resolve to the page's index.
                    target_idx = next(
                        i for i, p in enumerate(reader.pages)
                        if p.indirect_reference.idnum == target.idnum)
                self.assertEqual(target_idx, 2)  # 1-based TOC page 3

    def test_print_variant_gets_no_footer_link(self):
        out = self.tmp / "print.pdf"
        summary = inject_navigation(
            str(self.input_pdf), str(out), self.geometry,
            accent_links=False, back_to_toc_page=None)
        self.assertEqual(summary["back_to_toc_links"], 0)
        self.assertEqual(_link_annotation_pages(out), {})

    def test_digital_without_toc_page_fails_gate(self):
        out = self.tmp / "broken.pdf"
        with self.assertRaises(LinkInjectionError):
            inject_navigation(
                str(self.input_pdf), str(out), self.geometry,
                accent_links=True, back_to_toc_page=None)
        self.assertFalse(out.exists())

    def test_digital_with_out_of_range_toc_page_fails_gate(self):
        out = self.tmp / "broken.pdf"
        with self.assertRaises(LinkInjectionError):
            inject_navigation(
                str(self.input_pdf), str(out), self.geometry,
                accent_links=True, back_to_toc_page=99)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()