"""Regression tests for Obsidian image embeds (![[...]]) in both pipelines.

A sizeless embed on a *content* page used to survive into _WIKI_LINK_RE,
which read the inner [[image]] as a page reference and printed a literal
"!image name" instead of the picture. The sizeless form additionally
raised IndexError in _convert_wiki_embed_to_img, which read group 2
unconditionally while that pattern only has one group.

Run: python -m unittest discover -s 02_pdf_creation/tests -v
"""
import tempfile
import unittest
from pathlib import Path

from main_generate_cookbook import CookbookGenerator, _WIKI_LINK_RE


class TestWikiEmbedConversion(unittest.TestCase):
    """Embeds must become <img> tags, never unresolved page links."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        # A real file on disk, so _build_file_uri resolves it instead of
        # taking the not-found fallback branch.
        (self.tmp_path / "decomposed_ramen.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        (self.tmp_path / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        self.gen = CookbookGenerator(input_dir=str(self.tmp_path))

    def test_sizeless_embed_on_content_page_becomes_img(self):
        html = self.gen.markdown_to_html("![[decomposed_ramen.png]]")
        self.assertIn("<img", html)
        self.assertIn("decomposed_ramen.png", html)
        self.assertNotIn("wiki-link-unresolved", html)

    def test_sizeless_embed_resolves_to_a_real_asset_uri(self):
        html = self.gen.markdown_to_html("![[decomposed_ramen.png]]")
        self.assertIn("decomposed_ramen.png\"", html)
        self.assertIn("file:///", html)

    def test_sizeless_embed_fits_the_content_column(self):
        html = self.gen.markdown_to_html("![[decomposed_ramen.png]]")
        self.assertIn("max-width:100%", html)

    def test_sized_embed_keeps_its_numeric_width(self):
        html = self.gen.markdown_to_html("![[decomposed_ramen.png|300]]")
        self.assertIn('width="300"', html)
        self.assertNotIn("wiki-link-unresolved", html)

    def test_sized_embed_keeps_its_css_width(self):
        html = self.gen.markdown_to_html("![[diagram.svg|45%]]")
        self.assertIn("width:45%", html)

    def test_escaped_pipe_embed_still_converts(self):
        html = self.gen.markdown_to_html("![[decomposed_ramen.png\\|250]]")
        self.assertIn('width="250"', html)

    def test_rendered_html_pipeline_handles_sizeless_embed(self):
        """The recipe path converts embeds after rendering; it must not
        raise IndexError on a one-group match."""
        html = self.gen.process_wiki_links_html("![[decomposed_ramen.png]]")
        self.assertIn("<img", html)
        self.assertNotIn("wiki-link-unresolved", html)

    def test_embed_does_not_pollute_the_unresolved_report(self):
        self.gen.markdown_to_html("![[decomposed_ramen.png]]")
        self.assertEqual(dict(self.gen.unresolved_wiki_links), {})

    def test_real_page_link_still_resolves(self):
        self.gen.register_wiki_link("Bibimbap", "bibimbap-page")
        html = self.gen.markdown_to_html("[[Bibimbap]]")
        self.assertIn('href="#bibimbap-page"', html)
        self.assertNotIn("wiki-link-unresolved", html)

    def test_page_link_regex_ignores_embeds(self):
        self.assertIsNone(_WIKI_LINK_RE.search("![[decomposed_ramen.png]]"))
        self.assertIsNotNone(_WIKI_LINK_RE.search("[[Page]]"))


if __name__ == "__main__":
    unittest.main()