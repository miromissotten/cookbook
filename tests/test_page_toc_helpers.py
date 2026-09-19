"""Characterization tests: TOC title helpers in helpers/page_toc.py.

Pins current display/nesting behaviour (docs/CONTEXT.md vocabulary,
ADR 0014/0015 depth rules) so refactors cannot silently change it.

Stdlib unittest style so the suite runs without extra dependencies:
python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "02_pdf_creation" / "helpers"))

from page_toc import (
    CHAPTER_TOC_MAX_DEPTH,
    TOC_MAX_DEPTH,
    TOCPageRenderer,
    _clean_title,
    _entry_name,
    _numbering_depth,
    clean_title_id,
    display_parts,
    nest_entries_by_position,
)


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
