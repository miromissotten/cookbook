"""Characterization tests: TOC helpers in helpers/page_toc.py.

Pins current display/nesting behaviour (02_pdf_creation/docs/CONTEXT.md vocabulary, ADR 0014
depth rules) and the chapter block shapes (ADR 0015 spread, ADR 0026
text-only) so refactors cannot silently change them.

Stdlib unittest style so the suite runs without extra dependencies:
python -m unittest discover -s 02_pdf_creation/tests -v
"""
import unittest
from pathlib import Path

from page_toc import (
    CHAPTER_TOC_MAX_DEPTH,
    SUBTOC_LESS_CHAPTERS,
    TOC_MAX_DEPTH,
    TOCPageRenderer,
    _clean_title,
    _entry_name,
    _numbering_depth,
    chapter_prints_subtoc,
    clean_title_id,
    display_parts,
    nest_entries_by_position,
)


def _sheet_body(html: str) -> str:
    """The sheet's body markup, without the shared ``<style>`` block.

    Every sheet carries the same stylesheet, which references both the
    sub-TOC and the chapter-intro classes, so only the body tells the two
    sheet kinds apart.
    """
    return html[html.index('<body'):]


def _chapter(name: str, children=None) -> dict:
    """A chapter subtree shaped like StructureParser's hierarchy output."""
    return {"type": "section", "name": name, "children": children or []}


class TestPageTocHelpers(unittest.TestCase):
    def test_clean_title_reads_underscores_as_spaces_and_drops_cookbook(self):
        self.assertEqual(_clean_title("Ramen_Tare_Shio"), "Ramen Tare Shio")
        self.assertEqual(_clean_title("My_cookbook_Notes"), "My Notes")
        self.assertEqual(_clean_title("COOKBOOK"), "")

    def test_display_parts_splits_position_label_from_title(self):
        self.assertEqual(
            display_parts("_2.1.1.A. Ramen_Tare_Shio"), ("2.1.1.A", "Ramen Tare Shio"))
        self.assertEqual(
            display_parts("_3.1. Vegan Chashu"), ("3.1", "Vegan Chashu"))

    def test_display_parts_without_prefix_returns_empty_label(self):
        self.assertEqual(display_parts("Just a page"), ("", "Just a page"))

    def test_numbering_depth_counts_position_segments(self):
        self.assertEqual(_numbering_depth("_2.1.1.A. Ramen_Tare_Shio"), 4)
        self.assertEqual(_numbering_depth("_3.1. Vegan Chashu"), 2)
        self.assertEqual(_numbering_depth("Untitled page"), 0)

    def test_entry_name_supports_dicts_and_plain_strings(self):
        self.assertEqual(_entry_name({"name": "Broth"}), "Broth")
        self.assertEqual(_entry_name({"other": "x"}), "Untitled")
        self.assertEqual(_entry_name("Plain"), "Plain")

    def test_clean_title_id_mirrors_content_page_rule(self):
        self.assertEqual(clean_title_id("Ramen Tare_Shio!"), "ramen-tare-shio")
        self.assertEqual(clean_title_id("_2.1. Noodles"), "-21-noodles")

    def test_nest_entries_by_position_builds_depth_tree_without_mutating_input(self):
        flat = [
            {"type": "item", "name": "_2.2. Noodles"},
            {"type": "item", "name": "_2.2.4. Sub group"},
            {"type": "item", "name": "_2.2.4.1. Simple bread"},
            {"type": "item", "name": "_2.3. Other"},
        ]
        nested = nest_entries_by_position(flat)
        self.assertEqual([n["name"] for n in nested], ["_2.2. Noodles", "_2.3. Other"])
        noodles = nested[0]
        self.assertEqual([n["name"] for n in noodles["children"]], ["_2.2.4. Sub group"])
        self.assertEqual(
            [n["name"] for n in noodles["children"][0]["children"]],
            ["_2.2.4.1. Simple bread"])
        # Input list keeps its original flat child lists.
        self.assertEqual(flat[0].get("children", []), [])
        for entry in nested[1:]:
            self.assertEqual(entry["children"], [])

    def test_nest_entries_keeps_labelless_entries_at_top_level(self):
        nested = nest_entries_by_position([
            {"type": "item", "name": "_2.2. Noodles"},
            {"type": "item", "name": "Loose page"},
        ])
        self.assertEqual([n["name"] for n in nested], ["_2.2. Noodles", "Loose page"])

    def test_depth_caps_documented_in_code(self):
        self.assertEqual(TOC_MAX_DEPTH, 2)
        self.assertEqual(CHAPTER_TOC_MAX_DEPTH, 5)

    def test_chapter_prints_subtoc_keys_off_the_position_label(self):
        """Only the front-matter preface skips its sub-TOC sheet (ADR 0026).

        The policy keys on the top-level position label, so retitling the
        chapter cannot flip its block shape, and the annex chapters keep
        printing their sub-TOC like any other chapter.
        """
        self.assertEqual(SUBTOC_LESS_CHAPTERS, {"0"})
        self.assertFalse(chapter_prints_subtoc(_chapter("_0. cookbook_Preface")))
        self.assertFalse(chapter_prints_subtoc(_chapter("_0. Foreword")))
        self.assertTrue(chapter_prints_subtoc(_chapter("_1. Architectural Recipes")))
        self.assertTrue(chapter_prints_subtoc(_chapter("_Annex.B. Outro")))
        self.assertTrue(chapter_prints_subtoc(_chapter("Loose page")))

    def test_render_chapter_prints_one_text_sheet_for_the_preface(self):
        """ADR 0026: the preface block is its prose sheet alone, so the pages
        printed after it face the text instead of a sub-TOC."""
        pages = TOCPageRenderer().render_chapter(
            "0. Cookbook Preface",
            _chapter("_0. cookbook_Preface", [
                {"type": "subsection", "name": "_0.1. Meaning of icons"},
                {"type": "subsection", "name": "_0.2. Hypotheses & Sorries"},
            ]),
            content_html="<p>Preface prose.</p>")
        self.assertEqual(len(pages), 1)
        body = _sheet_body(pages[0])
        self.assertEqual(pages[0].count('<div class="recipe-page"'), 1)
        self.assertIn("chapter-intro-standalone", body)
        self.assertIn("Preface prose.", body)
        self.assertNotIn("toc-hierarchy", body)

    def test_render_chapter_preface_sheet_survives_without_prose(self):
        """A text-only chapter must never lose its block: the prose sheet
        prints (title only) even when the source authored no text."""
        pages = TOCPageRenderer().render_chapter(
            "0. Cookbook Preface", _chapter("_0. cookbook_Preface"),
            content_html="")
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].count('<div class="recipe-page"'), 1)
        self.assertIn("0. Cookbook Preface", _sheet_body(pages[0]))

    def test_render_chapter_orders_text_before_sub_toc(self):
        """ADR 0015: chapter text opens the block, the sub-TOC follows."""
        pages = TOCPageRenderer().render_chapter(
            "1. Architectural Recipes",
            _chapter("_1. Architectural Recipes", [
                {"type": "subsection", "name": "_1.1. Noodle bowls"},
            ]),
            content_html="<p>Chapter prose.</p>")
        self.assertEqual(len(pages), 2)
        intro, subtoc = _sheet_body(pages[0]), _sheet_body(pages[1])
        self.assertIn("chapter-intro-standalone", intro)
        self.assertNotIn("toc-hierarchy", intro)
        self.assertIn("toc-hierarchy", subtoc)
        self.assertNotIn("chapter-intro-standalone", subtoc)

    def test_render_chapter_without_prose_prints_the_sub_toc_alone(self):
        pages = TOCPageRenderer().render_chapter(
            "1. Architectural Recipes",
            _chapter("_1. Architectural Recipes", [
                {"type": "subsection", "name": "_1.1. Noodle bowls"},
            ]),
            content_html="")
        self.assertEqual(len(pages), 1)
        self.assertIn("toc-hierarchy", _sheet_body(pages[0]))

    def test_blank_sheet_page_formats_the_shared_head_template(self):
        """Parity blanks must unescape the .format() head ({{ }} CSS braces,
        {title}) like every other sheet type.

        Regression: an unformatted blank head poisoned the whole combined
        group PDF when the blank converted first (ADR 0015 parity pass);
        Chromium then threw "Unexpected token '{'" and printed unstyled,
        margin-less pages for chapters 2/3.
        """
        html = TOCPageRenderer().blank_sheet_page()
        self.assertNotIn("{{", html, "head still holds escaped .format() CSS")
        self.assertNotIn("}}", html, "head still holds escaped .format() CSS")
        self.assertNotIn("{title}", html, "head still holds the {title} slot")
        # The unescaped sheet shell survives intact.
        self.assertEqual(html.count('<div class="recipe-page"'), 1,
                         "blank must hold exactly one sheet")
        self.assertIn("data-page-footer", html,
                      "blank missing the footer token")

    def test_blank_sheet_page_head_carries_real_css(self):
        """After formatting, the blank's <head> unescapes to parseable CSS
        (single braces) so a blank-first combined group stays styled."""
        html = TOCPageRenderer().blank_sheet_page()
        self.assertIn(".recipe-page {", html)
        self.assertIn(".toc-hierarchy {", html)


if __name__ == "__main__":
    unittest.main()
