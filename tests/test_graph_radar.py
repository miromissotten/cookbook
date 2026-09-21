"""The RadarGraph marker block: chart rendering and how a page picks it up.

A sauce recipe authors its taste profile as a table of six 0-5 axes inside a
``==GRAPH_RADARGRAPH_START/END==`` block (the same marker convention the pizza
scatterplot uses). The block is rendered to a PNG by ``graph_radar`` and printed
under the recipe's sauce profile chips; a page without a block prints no chart.

Run: python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

PDF_ROOT = Path(__file__).resolve().parents[1] / "02_pdf_creation"

from graph_radar import render_radar_png
from main_generate_cookbook import CookbookGenerator
from page_renderer import RecipeParser, RecipeRenderer


# The six taste axes every sauce is rated on, with Hummus's values.
RADAR_TABLE = """| Acid | Richness | Sweet | Umami | Heat | Thickness |
| ---- | -------- | ----- | ----- | ---- | --------- |
| 2    | 4        | 0     | 2     | 0    | 5         |"""

RECIPE_WITH_CHART = """### Title
- title: Hummus

### Side info
- group: component
- subgroup: sauce
- sauce_flavour: creamy · bright · savory
- sauce_consistency: medium
- sauce_usage: dip · drizzle · spread

### Ingredients
- 225 g dried chickpeas

### RadarGraph
==GRAPH_RADARGRAPH_START==

{table}

==GRAPH_RADARGRAPH_END==
""".format(table=RADAR_TABLE)

RECIPE_WITHOUT_CHART = """### Title
- title: Hummus

### Ingredients
- 225 g dried chickpeas
"""


class RadarTableRendering(unittest.TestCase):
    """graph_radar turns one authored table into one PNG."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="radar_test_")
        self.addCleanup(self.tmp.cleanup)
        self.png_path = Path(self.tmp.name) / "radar.png"

    def test_renders_a_png_and_returns_a_file_uri(self):
        uri = render_radar_png(RADAR_TABLE, str(self.png_path))
        self.assertTrue(self.png_path.is_file())
        self.assertGreater(self.png_path.stat().st_size, 0)
        self.assertTrue(uri.startswith("file:///"), uri)
        # Verify it's actually a valid PNG
        with open(self.png_path, "rb") as f:
            header = f.read(8)
        self.assertEqual(header, b"\x89PNG\r\n\x1a\n")

    def test_accepts_the_generators_headers_kwarg(self):
        # _graph_block_to_img passes headers= to every graph renderer; the
        # radar chart ignores it because its axis names live in the table's
        # first row (the scatterplot, by contrast, uses them as labels).
        uri = render_radar_png(RADAR_TABLE, str(self.png_path), headers=None)
        self.assertTrue(self.png_path.is_file())
        self.assertTrue(uri.startswith("file:///"), uri)

    def test_table_without_a_data_row_is_rejected(self):
        header_only = "| Acid | Richness | Sweet | Umami | Heat | Thickness |"
        with self.assertRaises(ValueError):
            render_radar_png(header_only, str(self.png_path))

    def test_axis_and_value_counts_must_agree(self):
        mismatched = ("| Acid | Richness | Sweet | Umami | Heat | Thickness |\n"
                      "| ---- | -------- | ----- | ----- | ---- | --------- |\n"
                      "| 2    | 4        | 0     | 2     |")
        with self.assertRaises(ValueError):
            render_radar_png(mismatched, str(self.png_path))

    def test_rows_beyond_the_first_data_row_are_ignored(self):
        two_sauces = RADAR_TABLE + "\n| 4    | 1        | 3     | 0     | 5    | 1         |"
        uri = render_radar_png(two_sauces, str(self.png_path))
        self.assertTrue(uri.startswith("file:///"), uri)


class RadarBlockParsing(unittest.TestCase):
    """The marker block reaches the recipe as raw table text."""

    def test_parser_lifts_the_marker_block_into_the_recipe(self):
        recipe, diagnostics = RecipeParser().parse_recipe_with_diagnostics(
            RECIPE_WITH_CHART)
        # Only the table travels on: the generator renders it, the parser never
        # needs to know how a chart is drawn.
        self.assertIn("| Acid | Richness | Sweet | Umami | Heat | Thickness |",
                      recipe["radar_graph"])
        self.assertIn("| 2    | 4        | 0     | 2     | 0    | 5",
                      recipe["radar_graph"])
        self.assertNotIn("RADARGRAPH", recipe["radar_graph"])
        # The chart is an optional extra: nothing to report about it.
        self.assertFalse([d for d in diagnostics if "radar" in d[1].lower()],
                         diagnostics)

    def test_page_without_the_block_carries_no_chart(self):
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(
            RECIPE_WITHOUT_CHART)
        self.assertNotIn("radar_graph", recipe)


class RadarChartPlacement(unittest.TestCase):
    """The chart prints under the sauce profile chips, or not at all."""

    def render(self, radar_img_html):
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(RECIPE_WITH_CHART)
        return RecipeRenderer().render_html(recipe, "3.4.2.1.", radar_img_html)

    def test_chart_prints_when_the_generator_produced_one(self):
        html = self.render('<img src="file:///tmp/radar.png" alt="Radar chart" />')
        self.assertIn("data-radar-graph", html)
        self.assertIn("file:///tmp/radar.png", html)
        # Chips first, chart second: the picture explains them.
        self.assertLess(html.index("Sauce profile"), html.index("data-radar-graph"))

    def test_no_chart_and_no_empty_frame_without_one(self):
        html = self.render("")
        self.assertNotIn("data-radar-graph", html)


class RadarGeneratorWiring(unittest.TestCase):
    """CookbookGenerator owns the working folder the PNG lands in."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="radar_wiring_test_")
        self.addCleanup(self.tmp.cleanup)
        self.generator = CookbookGenerator(
            input_dir=[str(PDF_ROOT.parent / "data_modularflavour" / "text")],
            temp_dir=self.tmp.name)

    def test_recipe_chart_is_rendered_into_an_img_tag(self):
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(RECIPE_WITH_CHART)
        img_html = self.generator._radar_graph_html(recipe)
        self.assertIn("width:40mm", img_html)
        self.assertIn("radar_", img_html)

    def test_recipe_without_a_chart_yields_no_img_tag(self):
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(
            RECIPE_WITHOUT_CHART)
        self.assertEqual("", self.generator._radar_graph_html(recipe))

    def test_a_broken_table_warns_and_prints_no_chart(self):
        img_html = self.generator._radar_graph_html(
            {"radar_graph": "not a table at all"})
        self.assertEqual("", img_html)


if __name__ == "__main__":
    unittest.main()