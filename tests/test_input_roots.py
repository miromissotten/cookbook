"""Multi-root input resolution (ADR 0023): text + text_notdone as one source.

Pins the ordered-roots contract of helpers/input_roots.py and its
consumers (StructureParser, StructureGenerator, CookbookGenerator).
All fixtures live in temp dirs; no real data folder is touched.

Run: python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

from input_roots import find_file, iter_markdown_files, resolve_roots
from main_generate_cookbook import CookbookGenerator
from main_generate_cookbook_structure import StructureGenerator
from structure_parser import StructureParser


def _write(directory: Path, filename: str, content: str = "x\n") -> None:
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestResolveRoots(unittest.TestCase):
    def test_none_uses_both_default_roots_in_order(self):
        roots = resolve_roots(None)
        self.assertEqual([r.name for r in roots],
                         ["text", "text_notdone"])

    def test_single_dir_spec_becomes_one_root(self):
        roots = resolve_roots("some/dir")
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0], Path("some/dir"))

    def test_duplicates_are_deduplicated_in_order(self):
        roots = resolve_roots(["a", "b", "a", Path("b")])
        self.assertEqual([str(r) for r in roots], ["a", "b"])

    def test_empty_spec_raises(self):
        with self.assertRaises(ValueError):
            resolve_roots([])


class TestFindAndIterate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root_a = base / "a"
        self.root_b = base / "b"
        self.root_a.mkdir()
        self.root_b.mkdir()

    def test_find_file_first_root_wins(self):
        _write(self.root_a, "shared.md", "from a")
        _write(self.root_b, "shared.md", "from b")
        found = find_file([self.root_a, self.root_b], "shared.md")
        self.assertEqual(found, self.root_a / "shared.md")

    def test_find_file_falls_back_to_second_root(self):
        _write(self.root_b, "only_b.md")
        found = find_file([self.root_a, self.root_b], "only_b.md")
        self.assertEqual(found, self.root_b / "only_b.md")

    def test_find_file_missing_returns_none(self):
        self.assertIsNone(find_file([self.root_a, self.root_b], "nope.md"))

    def test_iter_markdown_files_unions_and_dedupes(self):
        _write(self.root_a, "_1. A.md")
        _write(self.root_b, "_2. B.md")
        _write(self.root_b, "_1. A.md")  # shadowed by root_a's copy
        files = iter_markdown_files([self.root_a, self.root_b])
        self.assertEqual(files.count("_1. A.md"), 1)
        self.assertIn("_1. A.md", files)
        self.assertIn("_2. B.md", files)
        self.assertEqual(files[0], "_1. A.md")
        self.assertEqual(files[1], "_2. B.md")


class TestStructureParserMultiRoot(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root_a = base / "text"
        self.root_b = base / "text_notdone"
        self.root_a.mkdir()
        self.root_b.mkdir()
        _write(self.root_a, "_1. Chapter.md")
        _write(self.root_b, "_2. Notdone.md")
        _write(self.root_a, "_-1.0. cookbook_structure_generated.md",
               "## [[_1. Chapter]]\n### [[_2. Notdone]]\n")

    def test_parser_resolves_files_in_second_root(self):
        parser = StructureParser([str(self.root_a), str(self.root_b)])
        self.assertEqual(parser.input_dir, self.root_a)
        self.assertEqual(parser._resolve_filename("_2. Notdone"),
                         "_2. Notdone.md")
        self.assertEqual(parser.get_all_markdown_files(),
                         ["_-1.0. cookbook_structure_generated.md",
                          "_1. Chapter.md", "_2. Notdone.md"])

    def test_parser_collision_prefers_first_root(self):
        _write(self.root_b, "_1. Chapter.md")
        parser = StructureParser([str(self.root_a), str(self.root_b)])
        found = find_file(parser.roots, "_1. Chapter.md")
        self.assertEqual(found, self.root_a / "_1. Chapter.md")


class TestStructureGeneratorMultiRoot(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root_a = base / "text"
        self.root_b = base / "text_notdone"
        self.root_a.mkdir()
        self.root_b.mkdir()

    def test_merges_and_sorts_across_roots(self):
        _write(self.root_a, "_2. Later.md", "text_description: done\n")
        _write(self.root_b, "_1. Early.md", "text_description: todo\n")
        generator = StructureGenerator(
            directory=[str(self.root_a), str(self.root_b)])
        content = generator.generate_structure_file()
        self.assertIn("## [[_1. Early]] ❌", content)
        self.assertIn("## [[_2. Later]] ✅", content)
        # Early (from the second root) must sort before Later.
        self.assertLess(content.index("[[_1. Early]]"),
                        content.index("[[_2. Later]]"))

    def test_structure_file_is_written_to_primary_root(self):
        _write(self.root_b, "_1. Only.md")
        generator = StructureGenerator(
            directory=[str(self.root_a), str(self.root_b)])
        output = generator.run()
        self.assertEqual(Path(output).parent, self.root_a)
        self.assertTrue((self.root_a /
                         "_-1.0. cookbook_structure_generated.md").exists())


class TestCookbookGeneratorMultiRoot(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root_a = base / "text"
        self.root_b = base / "text_notdone"
        self.root_a.mkdir()
        self.root_b.mkdir()
        _write(self.root_a, "_1. Finished.md", "# Finished\n")
        _write(self.root_b, "_2. Draft.md", "# Draft\n")

    def _generator(self) -> CookbookGenerator:
        return CookbookGenerator(
            input_dir=[str(self.root_a), str(self.root_b)],
            temp_dir=str(self.root_a / "_tmp_build"))

    def test_reads_files_from_both_roots(self):
        gen = self._generator()
        self.assertIn("# Finished", gen.read_markdown_file("_1. Finished.md"))
        self.assertIn("# Draft", gen.read_markdown_file("_2. Draft.md"))
        self.assertTrue(gen.read_markdown_file("_9. Missing.md")
                        .startswith("# File not found"))

    def test_roots_attribute_keeps_order(self):
        gen = self._generator()
        self.assertEqual([r.name for r in gen.input_roots],
                         ["text", "text_notdone"])
        self.assertEqual(gen.input_dir, self.root_a)


if __name__ == "__main__":
    unittest.main()

