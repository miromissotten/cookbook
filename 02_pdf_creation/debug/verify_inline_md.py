"""Temporary verification: inline markdown in Okonomiyaki instructions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from page_renderer import RecipeParser, RecipeRenderer

md_path = Path(__file__).resolve().parents[2] / "data_modularflavour" / "text" / "_1.4.3. Okonomiyaki.md"
recipe, _ = RecipeParser().parse_recipe_with_diagnostics(md_path.read_text(encoding="utf-8"))
html = RecipeRenderer()._generate_instructions_html(recipe["instructions"])
print("strong layered:", "<strong>layered</strong>" in html)
print("strong mixed:", "<strong>mixed</strong>" in html)
print("em Optional:", "<em>Optional</em>" in html)
print("literal '**' remains:", "**" in html)
print("strong pan 1:", "<strong>pan 1</strong>" in html)
