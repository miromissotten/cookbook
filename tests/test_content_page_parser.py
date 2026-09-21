"""Characterization tests for sideinfo content pages' "### Text" body.

A sideinfo page carries its printed body in a `### Text` section, an optional
`### Description` above it and its heading in `### Title`; every other section
(`### Side info`, `### Status info`) is authoring metadata that must never
reach the page. A file without a `### Text` section keeps rendering its whole
content, so the pipeline stays backward compatible.

Run: python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

from main_generate_cookbook import CookbookGenerator
from page_renderer import RecipeParser


SIDEINFO_PAGE = """### Description
- description: Miso = fermented soybean paste. The main ingredients are soybeans, salt and koji.

### Text
- Shiro Miso (white): mildest, sweetest, lowest salt

### Side info
- group: sideinfo
- subgroup: sideinfo

### Status info
- text_description: done
- design: todo
- sideinfo: done

### Title
- title: Miso
"""

METADATA_ONLY_PAGE = """### Side info
- group: sideinfo
- subgroup: list

### Status info
- text_description: todo
- design: todo
- sideinfo: todo
"""


class ContentPageParsing(unittest.TestCase):
    """RecipeParser.parse_content_page extraction rules."""

    def test_extracts_title_description_and_text(self):
        page = RecipeParser().parse_content_page(SIDEINFO_PAGE)
        self.assertTrue(page["has_text_section"])
        self.assertEqual(page["title"], "Miso")
        self.assertEqual(
            page["description"],
            "Miso = fermented soybean paste. The main ingredients are soybeans, "
            "salt and koji.")
        self.assertEqual(
            page["text"].strip(),
            "- Shiro Miso (white): mildest, sweetest, lowest salt")

    def test_text_without_description_leaves_description_none(self):
        page = RecipeParser().parse_content_page(
            "### Text\nstill to write\n\n### Title\n- title: Nori\n")
        self.assertTrue(page["has_text_section"])
        self.assertEqual(page["title"], "Nori")
        self.assertIsNone(page["description"])
        self.assertEqual(page["text"].strip(), "still to write")

    def test_text_section_is_found_before_the_title_section(self):
        """Section order is arbitrary: Kansui authors Text first."""
        page = RecipeParser().parse_content_page(
            "### Text\nkansui raises the pH of noodle dough.\n\n"
            "### Title\n- title: Kansui\n")
        self.assertTrue(page["has_text_section"])
        self.assertEqual(page["title"], "Kansui")
        self.assertIn("pH of noodle dough", page["text"])

    def test_no_text_section_reports_no_text_body(self):
        page = RecipeParser().parse_content_page(METADATA_ONLY_PAGE)
        self.assertFalse(page["has_text_section"])
        self.assertIsNone(page["text"])
        self.assertIsNone(page["title"])
        self.assertIsNone(page["description"])

    def test_missing_title_leaves_title_none(self):
        page = RecipeParser().parse_content_page("### Text\nJust prose.\n")
        self.assertTrue(page["has_text_section"])
        self.assertIsNone(page["title"])
        self.assertEqual(page["text"].strip(), "Just prose.")

    def test_text_section_preserves_subheadings_tables_and_fences(self):
        page = RecipeParser().parse_content_page(
            "### Text\nIntro.\n\n#### A short history\n\n"
            "| Type | Use |\n|---|---|\n| T45 | Cakes |\n\n"
            "```mermaid\nflowchart LR\n    A --> B\n```\n\n"
            "### Title\n- title: Flour\n")
        text = page["text"]
        self.assertIn("#### A short history", text)
        self.assertIn("| T45 | Cakes |", text)
        self.assertIn("```mermaid", text)

    def test_description_wiki_link_is_kept_verbatim(self):
        page = RecipeParser().parse_content_page(
            "### Description\n- description: As [[_1.1.1. Ramen|ramen]] toppings.\n\n"
            "### Text\n| Topping |\n|---|\n")
        self.assertEqual(page["description"], "As [[_1.1.1. Ramen|ramen]] toppings.")

    def test_multi_line_description_joins_continuation_lines(self):
        page = RecipeParser().parse_content_page(
            "### Description\n- description: First line\ncontinued here\n\n"
            "### Text\nBody.\n")
        self.assertEqual(page["description"], "First line continued here")

    def test_recipe_parser_reads_the_same_multi_line_description(self):
        """The shared helper must not change recipe parsing behaviour."""
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(
            "### Description\n- description: First line\ncontinued here\n\n"
            "### Ingredients\n- 100g salt\n")
        self.assertEqual(recipe["description"], "First line continued here")


class ContentPageRendering(unittest.TestCase):
    """process_non_recipe_to_html prints the Text section, nothing else."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.gen = CookbookGenerator(input_dir=str(self.tmp_path))

    def write_page(self, filename, content):
        (self.tmp_path / filename).write_text(content, encoding="utf-8")
        return content

    def render(self, filename, content, title):
        page_html, html_path = self.gen.process_non_recipe_to_html(
            filename, content, title)
        self.assertTrue(html_path)
        return page_html

    def test_sideinfo_page_prints_text_with_position_label_and_title(self):
        content = self.write_page("_5.1.1. Miso.md", SIDEINFO_PAGE)
        page_html = self.render("_5.1.1. Miso.md", content, "5.1.1. Miso")
        self.assertIn(">5.1.1. Miso</h1>", page_html)
        self.assertIn('id="page-miso"', page_html)
        self.assertIn("Shiro Miso (white)", page_html)

    def test_sideinfo_page_hides_its_metadata_sections(self):
        content = self.write_page("_5.1.1. Miso.md", SIDEINFO_PAGE)
        page_html = self.render("_5.1.1. Miso.md", content, "5.1.1. Miso")
        for hidden in ("### Side info", "group: sideinfo", "### Status info",
                       "text_description", "### Text", "### Title"):
            self.assertNotIn(hidden, page_html)

    def test_description_prints_above_the_text(self):
        content = self.write_page("_5.1.1. Miso.md", SIDEINFO_PAGE)
        page_html = self.render("_5.1.1. Miso.md", content, "5.1.1. Miso")
        self.assertLess(page_html.index("fermented soybean paste"),
                        page_html.index("Shiro Miso (white)"))

    def test_page_id_is_registered_under_title_and_filename_stem(self):
        content = self.write_page("_5.1.1. Miso.md", SIDEINFO_PAGE)
        self.gen._pre_scan_wiki_links(["_5.1.1. Miso.md"])
        self.assertEqual(self.gen.wiki_link_mapping["miso"], "page-miso")
        self.assertEqual(self.gen.wiki_link_mapping["_5.1.1. miso"], "page-miso")
        html = self.gen.markdown_to_html("[[Miso]] and [[_5.1.1. Miso]]")
        self.assertEqual(html.count('href="#page-miso"'), 2)
        self.assertNotIn("wiki-link-unresolved", html)

    def test_self_link_degrades_to_plain_text(self):
        content = ("### Text\nSee [[Miso]] for the whole picture.\n\n"
                   "### Title\n- title: Miso\n")
        self.write_page("_5.1.1. Miso.md", content)
        self.gen._pre_scan_wiki_links(["_5.1.1. Miso.md"])
        page_html = self.render("_5.1.1. Miso.md", content, "5.1.1. Miso")
        self.assertNotIn('href="#page-miso"', page_html)
        self.assertIn('class="wiki-link-self"', page_html)

    def test_mermaid_inside_text_still_becomes_a_diagram(self):
        content = ("### Text\n\n```mermaid\nflowchart LR\n"
                   "    S[Soybeans] --> M[Miso]\n```\n\n"
                   "### Title\n- title: Soy beans - Derivatives\n")
        self.write_page("_5.1.4. Soy Beans - derivatives.md", content)
        page_html = self.render("_5.1.4. Soy Beans - derivatives.md", content,
                                "5.1.4. Soy Beans - Derivatives")
        self.assertIn('<div class="mermaid">', page_html)
        self.assertIn(">5.1.4. Soy beans - Derivatives</h1>", page_html)

    def test_file_without_text_section_renders_whole_content(self):
        content = "Rough concept prose.\n\n### Side info\n- group: sideinfo\n"
        page_html = self.render("_3.4. Distinct Sauces.md", content,
                                "3.4. Distinct Sauces")
        self.assertIn("Rough concept prose.", page_html)
        self.assertIn("group: sideinfo", page_html)
        self.assertIn(">3.4. Distinct Sauces</h1>", page_html)

    def test_blockquote_renders_as_a_styled_quote(self):
        # _1.1. Noodle bowls prints a pull quote; the Flour sideinfo page
        # uses the same syntax for a callout. The HTML must keep its
        # <blockquote> and the template must style it, or Tailwind's
        # preflight makes the quote print as a plain paragraph.
        content = ("### Text\n\nThe saying goes:\n\n"
                   "> A good ramen doesn't need toppings.\n\n"
                   "### Title\n- title: Noodle bowls\n")
        self.write_page("_1.1. Noodle bowls.md", content)
        page_html = self.render("_1.1. Noodle bowls.md", content,
                                "1.1. Noodle Bowls")
        self.assertIn("<blockquote>", page_html)
        self.assertIn("good ramen doesn", page_html)
        self.assertIn(".content-text blockquote", page_html)


class ContentPageTitles(unittest.TestCase):
    """_content_page_title feeds both the wiki pre-scan and the renderer."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.gen = CookbookGenerator(input_dir=self._tmp.name)

    def test_authored_title_wins_over_the_filename(self):
        self.assertEqual(
            self.gen._content_page_title(
                SIDEINFO_PAGE, "_5.2.2. list_Ramen Toppings.md"),
            "Miso")

    def test_filename_derived_title_is_the_fallback(self):
        # The leading "_" keeps reading as a space, exactly as the previous
        # inline derivation did - hence the strip() in the expectation.
        self.assertEqual(
            self.gen._content_page_title(
                METADATA_ONLY_PAGE, "_5.2.3. other lists.md").strip(),
            "5.2.3. Other Lists")

    def test_unreadable_file_falls_back_without_raising(self):
        self.assertEqual(
            self.gen._content_page_title(
                "# File not found: _x.md\n\nThe file could not be found.",
                "_x.md").strip(),
            "X")


if __name__ == "__main__":
    unittest.main()
