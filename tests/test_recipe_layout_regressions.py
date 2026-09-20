"""Browser regressions for content-height sidebars and atomic variant moves."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "02_pdf_creation"
for directory in (TOOL, TOOL / "helpers", TOOL / "debug"):
    sys.path.insert(0, str(directory))

from debug_split_recipe import copy_libs
from main_generate_cookbook import CookbookGenerator
from html_to_pdf import _get_browser, _close_browser, wait_for_render_settled
from page_splitter import split_page_file


class RecipeLayoutRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="recipe_layout_test_")
        cls.directory = Path(cls.temp.name)
        cls.generator = CookbookGenerator(
            input_dir=[str(ROOT / "data_modularflavour" / "text"),
                       str(ROOT / "data_modularflavour" / "text_notdone")],
            temp_dir=str(cls.directory))
        copy_libs(cls.directory)

    @classmethod
    def tearDownClass(cls):
        _close_browser()
        cls.temp.cleanup()

    def render(self, filename):
        content = self.generator.read_markdown_file(filename)
        self.assertFalse(content.startswith("# File not found"))
        _, path = self.generator.process_recipe_to_html(filename, content)
        self.assertTrue(path)
        diagnostics = split_page_file(path) or []
        self.assertFalse([d for d in diagnostics if d[0] in ("warn", "error")],
                         diagnostics)
        self.last_diagnostics = diagnostics
        page = _get_browser().new_page(viewport={"width": 794, "height": 1123})
        self.addCleanup(page.close)
        page.emulate_media(media="print")
        page.goto(Path(path).resolve().as_uri(), wait_until="networkidle")
        wait_for_render_settled(page)
        return page

    def assert_sidebar_matches_longer_column(self, page):
        geometry = page.evaluate("""() => {
            const aside = document.querySelector('aside');
            const article = aside.parentElement.querySelector('article');
            const bottom = el => el.getBoundingClientRect().bottom;
            const actual = bottom(aside);
            aside.style.alignSelf = article.style.alignSelf = 'start';
            const expected = Math.max(bottom(aside), bottom(article));
            aside.style.removeProperty('align-self');
            article.style.removeProperty('align-self');
            return {actual, expected};
        }""")
        self.assertAlmostEqual(geometry["actual"], geometry["expected"], delta=1)
        return geometry

    def test_lasagna_background_ends_at_longer_column(self):
        page = self.render("_1.4.2. Lasagna.md")
        self.assertEqual(page.locator('.recipe-page').count(), 1)
        fixed = self.assert_sidebar_matches_longer_column(page)
        # Reproduce the old bug without changing the source template.
        old_bottom = page.evaluate("""() => {
            const aside = document.querySelector('aside');
            aside.parentElement.style.alignContent = 'normal';
            const bottom = aside.getBoundingClientRect().bottom;
            aside.parentElement.style.alignContent = 'start';
            return bottom;
        }""")
        self.assertGreater(old_bottom, fixed["expected"] + 20)
        # Exercise the opposite imbalance: ingredients longer than instructions.
        page.evaluate("""() => {
            const aside = document.querySelector('aside');
            const article = aside.parentElement.querySelector('article');
            article.replaceChildren(document.createTextNode('Short instructions'));
        }""")
        self.assert_sidebar_matches_longer_column(page)

    def test_pizza_variants_keep_columns_without_clipping(self):
        page = self.render("_1.5.1. Pizza Al Taglio.md")
        self.assertEqual(page.locator('.recipe-page').count(), 3)
        variants = page.evaluate("""() =>
            Array.from(document.querySelectorAll('[data-band]'))
            .filter(b => /^ins:\\d+$/.test(b.dataset.band)
                         && b.querySelector('[data-vunit]'))
            .map(b => ({key: b.dataset.band,
                left: b.querySelector('[data-vcol="L"]').textContent,
                right: b.querySelector('[data-vcol="R"]').textContent}))
        """)
        self.assertEqual([v["key"] for v in variants],
                         [f"ins:{i}" for i in range(6)])
        for variant in variants:
            with self.subTest(variant=variant["key"]):
                self.assertIn("Ingredients", variant["left"])
                self.assertNotIn("Instructions", variant["left"])
                self.assertIn("Instructions", variant["right"])

    def test_risotto_still_fits_two_sheets_without_warnings(self):
        page = self.render("_1.3.4. Risotto.md")
        self.assertEqual(page.locator('.recipe-page').count(), 2)

    OVERFLOW_STEPS = "\n".join(
        f"{i}. Simmer the synthetic step for a while and stir it thoroughly "
        "so the instruction column grows well past a single printed sheet."
        for i in range(1, 61))

    def test_recipe_without_ingredients_prints_vertical_fullwidth(self):
        """No `### Ingredients` section -> no Ingredients section printed and
        the vertical layout elected (never the side-by-side split)."""
        page = self.render("_3.1.1. Ramen_Bouillon.md")
        self.assertEqual(page.locator('.recipe-page').count(), 1)
        shape = page.evaluate("""() => {
            const article = document.querySelector(
                'article[data-purpose=recipe-instructions]');
            return {
                asideCount: document.querySelectorAll('aside').length,
                articleClass: article ? article.className : null,
                verticalMarker: article ?
                    article.hasAttribute('data-vertical-recipe') : false,
                ingredientsHeadings: Array.from(
                    document.querySelectorAll('h2, h3'))
                    .map(h => h.textContent.trim())
                    .filter(t => t.startsWith('Ingredients')).length,
                noIngredientsStub: document.body.textContent
                    .includes('No ingredients listed'),
                ingredientBands:
                    document.querySelectorAll('[data-band="ingredients"]').length
            };
        }""")
        self.assertEqual(shape["asideCount"], 0)
        self.assertIn("col-span-12", shape["articleClass"])
        self.assertNotIn("col-span-7", shape["articleClass"])
        self.assertTrue(shape["verticalMarker"])
        self.assertEqual(shape["ingredientsHeadings"], 0)
        self.assertFalse(shape["noIngredientsStub"])
        self.assertEqual(shape["ingredientBands"], 0)
        self.assertIn(("vertical",
                       "_3.1.1. Ramen_Bouillon.html: "
                       "vertical layout elected (1 sheet)"),
                      self.last_diagnostics)

    def test_oversized_recipe_without_ingredients_rebuilds_vertical_bands(self):
        """A long no-ingredients recipe overflows into the vertical band
        rebuild without an ingredients band ever being created."""
        content = (
            "### Title\n- title: Synthetic Overflow\n\n"
            "### Instructions\n" + self.OVERFLOW_STEPS + "\n")
        _, path = self.generator.process_recipe_to_html(
            "_ZZ. Synthetic Overflow.md", content)
        self.assertTrue(path)
        diagnostics = split_page_file(path) or []
        self.assertFalse([d for d in diagnostics if d[0] in ("warn", "error")],
                         diagnostics)
        self.assertTrue(any(d[0] == "vertical" for d in diagnostics),
                        diagnostics)
        page = _get_browser().new_page(viewport={"width": 794, "height": 1123})
        self.addCleanup(page.close)
        page.emulate_media(media="print")
        page.goto(Path(path).resolve().as_uri(), wait_until="networkidle")
        wait_for_render_settled(page)
        shape = page.evaluate("""() => ({
            sheets: document.querySelectorAll('.recipe-page').length,
            asides: document.querySelectorAll('aside').length,
            ingredientBands:
                document.querySelectorAll('[data-band="ingredients"]').length,
            instructionBands: Array.from(
                document.querySelectorAll('[data-band="instructions"]'))
                .filter(b => b.querySelector('[data-vunit]')).length,
            verticalLayouts:
                document.querySelectorAll('[data-layout="vertical"]').length
        })""")
        self.assertGreaterEqual(shape["sheets"], 2)
        self.assertEqual(shape["asides"], 0)
        self.assertEqual(shape["ingredientBands"], 0)
        self.assertGreaterEqual(shape["instructionBands"], 1)
        self.assertEqual(shape["verticalLayouts"], shape["sheets"])


class ContentTableLayoutRegressions(unittest.TestCase):
    """Content-page tables wrap instead of clipping at the sheet's right
    edge (ADR 0024): a wide first column (5.2.2's topping names) used to
    force the whole table past the printable width, and Chromium print
    silently dropped the right-hand columns."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="content_table_test_")
        cls.directory = Path(cls.temp.name)
        cls.generator = CookbookGenerator(
            input_dir=[str(ROOT / "data_modularflavour" / "text"),
                       str(ROOT / "data_modularflavour" / "text_notdone")],
            temp_dir=str(cls.directory))
        copy_libs(cls.directory)

    @classmethod
    def tearDownClass(cls):
        _close_browser()
        cls.temp.cleanup()

    def render_content(self, filename):
        content = self.generator.read_markdown_file(filename)
        self.assertFalse(content.startswith("# File not found"))
        _, path = self.generator.process_non_recipe_to_html(
            filename, content, "TEST")
        self.assertTrue(path)
        diagnostics = split_page_file(path) or []
        self.assertFalse([d for d in diagnostics if d[0] in ("warn", "error")],
                         diagnostics)
        page = _get_browser().new_page(viewport={"width": 794, "height": 1123})
        self.addCleanup(page.close)
        page.emulate_media(media="print")
        page.goto(Path(path).resolve().as_uri(), wait_until="networkidle")
        wait_for_render_settled(page)
        return page

    @staticmethod
    def measure_tables(page):
        return page.evaluate("""() => {
            const tables = [];
            document.querySelectorAll('.recipe-page').forEach(sheet => {
                const host = sheet.querySelector('.content-text');
                if (!host) return;
                host.querySelectorAll('table').forEach(t => {
                    const lines = th => {
                        const r = document.createRange();
                        r.selectNodeContents(th);
                        return new Set([...r.getClientRects()]
                            .map(x => Math.round(x.top))).size;
                    };
                    tables.push({
                        width: t.getBoundingClientRect().width,
                        container: host.clientWidth,
                        thLines: [...t.querySelectorAll('th')].map(lines),
                        columns: t.querySelectorAll('th').length
                    });
                });
            });
            return {sheets: document.querySelectorAll('.recipe-page').length,
                    tables: tables};
        }""")

    def test_ramen_toppings_table_wraps_within_the_sheet(self):
        page = self.render_content("_5.2.2. Categorisation_Toppings.md")
        shape = self.measure_tables(page)
        self.assertGreaterEqual(shape["sheets"], 1)
        self.assertTrue(shape["tables"], "toppings table missing")
        for table in shape["tables"]:
            with self.subTest(columns=table["columns"]):
                # The toppings matrix has 8 columns; every repeated header
                # (split row-chunks) must carry all of them.
                self.assertEqual(table["columns"], 8)
                # Nothing may stick out past the sheet's content width -
                # that is exactly what print clips off.
                self.assertLessEqual(table["width"], table["container"] + 1)
                # Single-word headers can never wrap; assert it so a future
                # CSS change cannot break the one-line header guarantee.
                self.assertEqual(table["thLines"], [1] * 8)

    def test_emulsions_table_never_clips(self):
        page = self.render_content("_3.3. Italian Emulsions.md")
        shape = self.measure_tables(page)
        self.assertTrue(shape["tables"], "emulsions table missing")
        for table in shape["tables"]:
            with self.subTest(columns=table["columns"]):
                self.assertLessEqual(table["width"], table["container"] + 1)


if __name__ == "__main__":
    unittest.main()
