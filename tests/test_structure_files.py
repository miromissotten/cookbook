"""Characterization tests: StructureGenerator + StructureParser.

Covers the structure-file round trip (numbered filename -> markdown ->
ordered filenames + hierarchy) with tmp_path-free fixtures
(tempfile + stdlib unittest, no extra dependencies).

Run: python -m unittest discover -s tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "02_pdf_creation"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "02_pdf_creation" / "helpers"))

from main_generate_cookbook_structure import StructureGenerator
from structure_parser import StructureParser


def _write(directory: Path, name: str, body: str = "text\n") -> None:
    (directory / name).write_text(body, encoding="utf-8")


class TestStructureFiles(unittest.TestCase):
    def test_parse_prefix_reads_numeric_parts_and_title(self):
        generator = StructureGenerator(directory=".")
        self.assertEqual(
            generator.parse_prefix("_2.1.1. Ramen_Tare_Shio.md"),
            ((2, 1, 1), "Ramen_Tare_Shio"))
        self.assertIsNone(generator.parse_prefix("plain.md"))

    def test_is_excluded_skips_generated_and_meta_files(self):
        generator = StructureGenerator(directory=".")
        self.assertTrue(generator.is_excluded("_-1.0. cookbook_structure_generated.md"))
        self.assertTrue(generator.is_excluded("notes_structure.md"))
        self.assertFalse(generator.is_excluded("_2.1. Noodles.md"))

    def test_get_status_and_emoji_read_workflow_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write(tmp_path, "_1. Test.md", "text_description: done\n")
            generator = StructureGenerator(directory=str(tmp_path))
            self.assertEqual(generator.get_status("_1. Test.md"), "done")
            self.assertEqual(generator.get_status_emoji("done"), "✅")
            self.assertIsNone(generator.get_status("missing.md"))
            self.assertEqual(generator.get_status_emoji(None), "")
            self.assertEqual(generator.get_status_emoji("unknown"), "")

    def test_structure_round_trip_preserves_book_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write(tmp_path, "_1. Chapter.md")
            _write(tmp_path, "_1.1. Sub.md")
            _write(tmp_path, "_1.1.1. Item.md")
            generated = tmp_path / "_-1.0. cookbook_structure_generated.md"
            generated.write_text(
                "# Book Name: Modular Flavour\n"
                "## [[_1. Chapter]]\n"
                "### [[_1.1. Sub]]\n"
                "#### [[_1.1.1. Item]]\n",
                encoding="utf-8",
            )
            parser = StructureParser(input_dir=str(tmp_path))
            self.assertEqual(
                parser.parse_structure_file(generated.name),
                ["_1. Chapter.md", "_1.1. Sub.md", "_1.1.1. Item.md"])
            hierarchy = parser.get_structure_hierarchy(generated.name)
            self.assertEqual(hierarchy[0]["name"], "_1. Chapter")
            self.assertEqual(hierarchy[0]["children"][0]["name"], "_1.1. Sub")
            self.assertEqual(hierarchy[0]["children"][0]["children"][0]["name"], "_1.1.1. Item")

    def test_resolve_filename_matches_exact_and_prefixed_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write(tmp_path, "_4.3.1. Chimichurri.md")
            parser = StructureParser(input_dir=str(tmp_path))
            self.assertEqual(
                parser.resolve_page_file("_4.3.1. Chimichurri"),
                "_4.3.1. Chimichurri.md")
            self.assertIsNone(parser.resolve_page_file("missing page"))

    def test_generate_structure_file_lists_sections_and_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write(tmp_path, "_1. Chapter.md")
            _write(tmp_path, "_1.1. Sub.md")
            _write(tmp_path, "_1.1.1. Item.md", "text_description: done\n")
            content = StructureGenerator(directory=str(tmp_path)).generate_structure_file()
            self.assertTrue(content.startswith("# Book Name: Modular Flavour"))
            self.assertIn("## [[_1. Chapter]]", content)
            self.assertIn("### [[_1.1. Sub]]", content)
            self.assertIn("#### [[_1.1.1. Item]]", content)


    def test_parse_prefix_reads_letter_suffixes(self):
        """Letter suffixes like 3.1.1.A should be parsed correctly."""
        generator = StructureGenerator(directory=".")
        self.assertEqual(
            generator.parse_prefix("_3.1.1.A. Item.md"),
            ((3, 1, 1, "A"), "Item"))
        self.assertEqual(
            generator.parse_prefix("_3.1.1.0. Item.md"),
            ((3, 1, 1, 0), "Item"))

    def test_subsection_without_children_is_heading_not_list(self):
        """Subsections without children should be ### headings, not list items."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write(tmp_path, "_1. Chapter.md")
            _write(tmp_path, "_1.1. Sub.md")
            content = StructureGenerator(directory=str(tmp_path)).generate_structure_file()
            self.assertIn("## [[_1. Chapter]]", content)
            self.assertIn("### [[_1.1. Sub]]", content)
            # Should NOT be a list item
            self.assertNotIn("- [[_1.1. Sub]]", content)

    def test_deeply_nested_items_use_correct_heading_levels(self):
        """Items at depth 4+ should use #### and ##### headings."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write(tmp_path, "_1. Chapter.md")
            _write(tmp_path, "_1.1. Sub.md")
            _write(tmp_path, "_1.1.1. Item.md")
            _write(tmp_path, "_1.1.1.1. Deep_Item.md")
            _write(tmp_path, "_1.1.1.1.1. Deeper_Item.md")
            content = StructureGenerator(directory=str(tmp_path)).generate_structure_file()
            self.assertIn("## [[_1. Chapter]]", content)
            self.assertIn("### [[_1.1. Sub]]", content)
            self.assertIn("#### [[_1.1.1. Item]]", content)
            self.assertIn("##### [[_1.1.1.1. Deep_Item]]", content)
            self.assertIn("###### [[_1.1.1.1.1. Deeper_Item]]", content)

    def test_annex_files_appear_at_end_of_structure(self):
        """_Annex.X. files should be included at the end as ## headings."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write(tmp_path, "_1. Chapter.md")
            _write(tmp_path, "_Annex.A. Full Table Of Contents.md")
            _write(tmp_path, "_Annex.B. Outro.md")
            content = StructureGenerator(directory=str(tmp_path)).generate_structure_file()
            lines = content.strip().split("\n")
            self.assertEqual(lines[0], "# Book Name: Modular Flavour")
            self.assertIn("## [[_1. Chapter]]", content)
            self.assertIn("## [[_Annex.A. Full Table Of Contents]]", content)
            self.assertIn("## [[_Annex.B. Outro]]", content)
            annex_a_pos = content.index("## [[_Annex.A. Full Table Of Contents]]")
            annex_b_pos = content.index("## [[_Annex.B. Outro]]")
            chapter_pos = content.index("## [[_1. Chapter]]")
            self.assertLess(chapter_pos, annex_a_pos)
            self.assertLess(annex_a_pos, annex_b_pos)


if __name__ == "__main__":
    unittest.main()
