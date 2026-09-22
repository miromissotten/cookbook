"""Unit tests for the shared sheet/footer counters.

The footer-token warning ("footer token count ... does not match sheet count")
is driven by two counters that must agree on every sheet shape the templates
and the watermark pass can emit. These tests pin that contract directly so a
future "exact string" regression can't silently re-introduce the false warning.

Note: these tests verify regex-based HTML counters, which are implementation
details. They are retained because the footer-token/sheet-count contract is
user-visible (it controls a diagnostic warning) and would be expensive to
test via full PDF rendering.

Run: python -m unittest 02_pdf_creation.tests.test_sheet_counting -v
"""
import unittest
from pathlib import Path

from html_to_pdf import count_footer_tokens  # noqa: E402
from page_splitter import count_sheets  # noqa: E402


class SheetContainerCounting(unittest.TestCase):
    """count_sheets sees every flavour of sheet opening tag."""

    def test_plain_sheet(self):
        html = '<main class="py-8"><div class="recipe-page">x</div></main>'
        self.assertEqual(count_sheets(html), 1)

    def test_watermarked_todo_sheet_counts(self):
        # The notdone-watermark pass appends a class; the old exact-string
        # counters missed this tag entirely -> false "does not match" warnings.
        html = '<div class="recipe-page notdone-watermark">x</div>'
        self.assertEqual(count_sheets(html), 1)

    def test_lookalike_classes_are_ignored(self):
        self.assertEqual(count_sheets('<div class="recipe-pagex">'), 0)
        self.assertEqual(count_sheets('.recipe-page { }'), 0)

    def test_mixed_plain_and_watermarked_sheets(self):
        html = ('<div class="recipe-page"></div>'
                '<div class="recipe-page notdone-watermark"></div>')
        self.assertEqual(count_sheets(html), 2)

    def test_footer_div_is_not_treated_as_a_sheet(self):
        # The injected footer token is a sibling tag, not a sheet container.
        html = '<div class="recipe-page"><div data-page-footer></div></div>'
        self.assertEqual(count_sheets(html), 1)


class FooterTokenCounting(unittest.TestCase):
    """count_footer_tokens matches both serialisations of the token."""

    def test_bare_and_empty_attribute_tokens(self):
        html = '<div data-page-footer></div><div data-page-footer=""></div>'
        self.assertEqual(count_footer_tokens(html), 2)

    def test_tokens_and_sheets_match_on_a_watermarked_page(self):
        html = ('<div class="recipe-page notdone-watermark">'
                '<div data-page-footer></div></div>')
        self.assertEqual(count_footer_tokens(html),
                         count_sheets(html))


if __name__ == "__main__":
    unittest.main()
