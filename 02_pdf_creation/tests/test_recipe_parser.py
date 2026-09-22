"""Characterization tests: tolerant RecipeParser behaviour.

Pins the absorb-all contract from ADR 0001/0012 using small inline
markdown fixtures (no data_modularflavour/text dependency, no browser needed).

Note: several tests assert on HTML structure (tag counts, class names).
These are implementation-sensitive but guard specific layout regressions:
the Aglio e Olio double-stream bug and the instruction-intro marker bug.
Removing them would allow those regressions to pass silently.

Stdlib unittest style: python -m unittest discover -s 02_pdf_creation/tests -v
"""
import unittest
from pathlib import Path

from page_renderer import RecipeParser


MINIMAL_RECIPE = """### Title
- title: Ramen Tare Shio

### Side info
- group: component
- subgroup: sauce
- freezeable: yes
- origin: Japan
- love level: 9
- carbsource: none
- recipe for how many people: serves 4
- time formula active + waiting: 00h20 + 00h05
- for how many p possible reasonably: 2-6
- work after premade: 00h05
- Food for dating: True
- difficulty: easy
- sauce_flavour: savory
- sauce_consistency: light
- sauce_usage: dip

### Dietary Restrictions
- Lactosefree: yes
- Vegetarian: yes
- Vegan: possible
- Glutenfree: no

### Ingredients
- 100g salt
  - use sea salt
- 50ml mirin

### Instructions
- Warm the pan
- Add salt
"""


class TestRecipeParser(unittest.TestCase):
    def test_parse_minimal_recipe_keeps_all_fields(self):
        recipe, diagnostics = RecipeParser().parse_recipe_with_diagnostics(MINIMAL_RECIPE)
        self.assertEqual(recipe["title"], "Ramen Tare Shio")
        self.assertEqual(recipe["group"], "component")
        self.assertEqual(recipe["origin"], "Japan")
        self.assertEqual(recipe["love_level"], 9.0)
        self.assertEqual(recipe["servings"], 4)
        self.assertEqual(recipe["time_formula"], "00h20 + 00h05")
        self.assertTrue(recipe["food_for_dating"])
        self.assertEqual(recipe["glutenfree"], "no")
        self.assertEqual(
            recipe["ingredients"][0],
            {"main": "100g salt", "sub": ["use sea salt"], "indent": 0})
        self.assertEqual(
            [b["kind"] for b in recipe["instructions"]], ["step", "step"])
        self.assertIn(("todo", "no description -> TODO stub rendered"), diagnostics)

    def test_missing_side_info_only_warns_for_that_block(self):
        recipe, diagnostics = RecipeParser().parse_recipe_with_diagnostics(
            "### Title\n- title: Lonely\n"
        )
        self.assertEqual(recipe["title"], "Lonely")
        self.assertIn("warn", [level for level, _ in diagnostics])
        self.assertTrue(any("Side info" in message for _, message in diagnostics))

    def test_slash_origin_is_omitted_but_other_fields_survive(self):
        content = MINIMAL_RECIPE.replace("- origin: Japan", "- origin: /")
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(content)
        self.assertNotIn("origin", recipe)
        self.assertEqual(recipe["group"], "component")

    def test_non_standard_time_formula_is_kept_verbatim_and_reported(self):
        content = MINIMAL_RECIPE.replace("00h20 + 00h05", "(02h30) + 04h00")
        recipe, diagnostics = RecipeParser().parse_recipe_with_diagnostics(content)
        self.assertEqual(recipe["time_formula"], "(02h30) + 04h00")
        self.assertTrue(any(
            level == "info" and "time formula" in message
            for level, message in diagnostics
        ))

    def test_bad_love_level_and_servings_are_ignored_with_warnings(self):
        content = MINIMAL_RECIPE.replace("love level: 9", "love level: lots")
        content = content.replace("serves 4", "serves many")
        recipe, diagnostics = RecipeParser().parse_recipe_with_diagnostics(content)
        self.assertNotIn("love_level", recipe)
        self.assertNotIn("servings", recipe)
        self.assertTrue(any("love level" in message for _, message in diagnostics))
        self.assertTrue(any("servings" in message for _, message in diagnostics))

    def test_missing_description_renders_todo_stub_signal(self):
        content = MINIMAL_RECIPE.replace(
            "### Ingredients", "### Description\n- description: test\n\n### Ingredients")
        _, clean = RecipeParser().parse_recipe_with_diagnostics(content)
        self.assertFalse(any(level == "todo" for level, _ in clean))

        _, diagnostics = RecipeParser().parse_recipe_with_diagnostics(MINIMAL_RECIPE)
        self.assertIn(("todo", "no description -> TODO stub rendered"), diagnostics)

    def test_numbered_steps_and_variant_labels_are_absorbed(self):
        content = (
            MINIMAL_RECIPE.split("### Instructions")[0]
            + "### Instructions\nHiroshima Style\n1. First step\n2) Second step\n"
        )
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(content)
        kinds = [b["kind"] for b in recipe["instructions"]]
        self.assertIn("variant", kinds)
        self.assertEqual(kinds.count("step"), 2)

    def test_bare_placeholder_step_is_dropped_and_warned(self):
        content = MINIMAL_RECIPE + "-\n"
        recipe, diagnostics = RecipeParser().parse_recipe_with_diagnostics(content)
        self.assertTrue(
            all(b.get("step") != "-" for b in recipe.get("instructions", [])))
        self.assertTrue(any("placeholder" in message for _, message in diagnostics))

    def test_unknown_side_info_fields_are_ignored_but_reported(self):
        content = MINIMAL_RECIPE.replace(
            "- difficulty: easy", "- difficulty: easy\n- made_up: x")
        recipe, diagnostics = RecipeParser().parse_recipe_with_diagnostics(content)
        self.assertNotIn("made_up", recipe)
        self.assertTrue(any("unknown side-info" in message for _, message in diagnostics))

    def test_parse_recipe_discards_diagnostics_but_keeps_data(self):
        recipe = RecipeParser().parse_recipe(MINIMAL_RECIPE)
        self.assertEqual(recipe["title"], "Ramen Tare Shio")

    def test_instruction_table_block_is_parsed_as_table_kind(self):
        content = (
            MINIMAL_RECIPE.split("### Instructions")[0]
            + "### Instructions\n"
            + "| Type | Notes |\n"
            + "| ---- | ----- |\n"
            + "| A    | note  |\n"
            + "- Next step\n"
        )
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(content)
        kinds = [b.get("kind") for b in recipe["instructions"]]
        self.assertIn("table", kinds)
        table_block = next(b for b in recipe["instructions"] if b.get("kind") == "table")
        self.assertIn("| Type | Notes |", table_block.get("lines", []))

    def test_instruction_table_is_rendered_as_html_table(self):
        from page_renderer import RecipeRenderer
        blocks = [
            {"kind": "table", "lines": [
                "| Type | Notes |",
                "| ---- | ----- |",
                "| A    | note  |",
            ]}
        ]
        html = RecipeRenderer()._render_instruction_core(blocks)
        self.assertIn("<table>", html)
        self.assertNotIn("|", html)
        # Presentation-only class: the data-instruction-intro MARKER is
        # reserved for the preamble (one marker = one splitter stream), so a
        # table can never open a second intro stream next to its wrapper's.
        self.assertIn('instruction-intro-table', html)
        self.assertNotIn('data-instruction-intro', html)

    def test_instruction_step_renders_inline_markdown(self):
        from page_renderer import RecipeRenderer
        blocks = [
            {"kind": "step",
             "step": "Hiroshima style is **layered** (noodles, cabbage).",
             "subs": ["*Optional*: add pork."]},
        ]
        html = RecipeRenderer()._render_instruction_core(blocks)
        self.assertIn("<strong>layered</strong>", html)
        self.assertIn("<em>Optional</em>", html)
        self.assertNotIn("**", html)
        self.assertNotIn("*Optional*", html)

    def test_instruction_prose_renders_inline_markdown(self):
        from page_renderer import RecipeRenderer
        blocks = [{"kind": "prose", "text": "Osaka style is **mixed**."}]
        html = RecipeRenderer()._render_instruction_core(blocks)
        self.assertIn("<strong>mixed</strong>", html)
        self.assertNotIn("**", html)

    def test_instruction_step_without_markdown_stays_plain(self):
        from page_renderer import RecipeRenderer
        blocks = [{"kind": "step", "step": "Fry the garlic", "subs": []}]
        html = RecipeRenderer()._render_instruction_core(blocks)
        self.assertIn("<p>Fry the garlic</p>", html)

    def test_heading_preamble_is_one_intro_div_before_first_section(self):
        from page_renderer import RecipeRenderer
        instructions = [
            {"kind": "prose", "text": "Preamble prose comes first."},
            {"kind": "heading", "text": "ORIGINAL AGLIO E OLIO:"},
            {"kind": "step", "step": "Fry the garlic", "subs": []},
        ]
        html = RecipeRenderer()._generate_instructions_html(instructions)
        self.assertEqual(html.count("data-instruction-intro"), 1)
        self.assertIn('<div data-instruction-intro>', html)
        self.assertNotIn('data-instruction-block data-instruction-intro', html)
        self.assertLess(html.index("data-instruction-intro"),
                        html.index("ORIGINAL AGLIO E OLIO:"))

    def test_variant_preamble_is_intro_div_not_intro_section(self):
        from page_renderer import RecipeRenderer
        instructions = [
            {"kind": "prose", "text": "Preamble prose comes first."},
            {"kind": "variant", "label": "CHEATED AGLIO E OLIO"},
            {"kind": "step", "step": "Fry the garlic", "subs": []},
        ]
        html = RecipeRenderer()._generate_instructions_html(instructions)
        self.assertEqual(html.count("data-instruction-intro"), 1)
        # The headless preamble is a plain intro div, never a section carrying
        # both markers: a double stream registration relocates it onto a later
        # sheet (the Aglio e Olio bug).
        self.assertIn('<div data-instruction-intro>', html)
        self.assertNotIn('data-instruction-block data-instruction-intro', html)

    def test_variant_preamble_with_table_keeps_single_intro_marker(self):
        from page_renderer import RecipeRenderer
        instructions = [
            {"kind": "prose", "text": "Preamble prose."},
            {"kind": "table", "lines": [
                "| Type | Notes |",
                "| ---- | ----- |",
                "| A    | note  |",
            ]},
            {"kind": "variant", "label": "ROASTING&FRYING"},
            {"kind": "step", "step": "Roast the potatoes", "subs": []},
        ]
        html = RecipeRenderer()._generate_instructions_html(instructions)
        self.assertEqual(html.count("data-instruction-intro"), 1)
        self.assertIn('instruction-intro-table', html)


    def test_heading_levels_are_recorded_in_blocks(self):
        content = MINIMAL_RECIPE + (
            "#### Variant one\n"
            "##### Ingredients\n"
            "- salt\n"
            "##### Instructions\n"
            "1. pour it\n")
        recipe, _ = RecipeParser().parse_recipe_with_diagnostics(content)
        heading_levels = [b["level"] for b in recipe["instructions"]
                          if b["kind"] == "heading"]
        self.assertEqual(heading_levels, [4, 5, 5])

    def test_level5_headings_nest_inside_level4_blocks(self):
        """Pizza Al Taglio shape: each `####` variant owns one instruction
        block; `#####` sub-headings stay inline instead of splitting it."""
        from page_renderer import RecipeRenderer
        instructions = [
            {"kind": "heading", "level": 4, "text": "Bianca: Patate e Rosmarino"},
            {"kind": "heading", "level": 5, "text": "Ingredients"},
            {"kind": "step", "step": "extra virgin olive oil", "subs": []},
            {"kind": "heading", "level": 5, "text": "Instructions"},
            {"kind": "step", "step": "slice potatoes very thinly", "subs": []},
            {"kind": "heading", "level": 4, "text": "Rosso: Margherita"},
            {"kind": "heading", "level": 5, "text": "Ingredients"},
            {"kind": "step", "step": "Tomato sauce", "subs": []},
            {"kind": "heading", "level": 5, "text": "Instructions"},
            {"kind": "step", "step": "add tomato sauce.", "subs": []},
        ]
        html = RecipeRenderer()._generate_instructions_html(instructions)
        # One block per `####` variant, labelled by the variant name - not one
        # per `#####`, which overwrote the variant name with "Ingredients".
        self.assertEqual(html.count("data-instruction-block"), 2)
        head_labels = [seg[1:seg.index("<")]
                       for seg in html.split('<h3 class="section-heading"')[1:]]
        self.assertEqual(head_labels,
                         ["Bianca: Patate e Rosmarino", "Rosso: Margherita"])
        # `#####` labels print inline (h4), never as a block head of their own.
        self.assertEqual(html.count("<h4"), 4)
        # Source order survives: each variant's ingredients precede its steps.
        self.assertLess(html.index("Bianca"), html.index("extra virgin olive oil"))
        self.assertLess(html.index("extra virgin olive oil"),
                        html.index("slice potatoes"))
        self.assertLess(html.index("slice potatoes"),
                        html.index("Rosso: Margherita"))

    def test_inline_level5_heading_restarts_step_numbering(self):
        from page_renderer import RecipeRenderer
        blocks = [
            {"kind": "step", "step": "first action", "subs": []},
            {"kind": "heading", "level": 5, "text": "Instructions"},
            {"kind": "step", "step": "second action", "subs": []},
        ]
        html = RecipeRenderer()._render_instruction_core(blocks)
        # Both post-heading steps print badge "1": numbering restarts at every
        # sub-heading, so a variant's Ingredients and Instructions lists both
        # count from 1.
        self.assertEqual(html.count(">1</span>"), 2)
        self.assertIn("<h4", html)

    def test_level_less_heading_still_opens_a_block(self):
        """Legacy heading dicts without a level keep opening blocks."""
        from page_renderer import RecipeRenderer
        instructions = [
            {"kind": "heading", "text": "ORIGINAL AGLIO E OLIO:"},
            {"kind": "step", "step": "Fry the garlic", "subs": []},
        ]
        html = RecipeRenderer()._generate_instructions_html(instructions)
        self.assertEqual(html.count("data-instruction-block"), 1)
        self.assertIn("ORIGINAL AGLIO E OLIO:", html)


if __name__ == "__main__":
    unittest.main()
