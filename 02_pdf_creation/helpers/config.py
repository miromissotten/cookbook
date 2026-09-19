"""
Configuration and constants for the cookbook generator.
"""

from reportlab.lib.units import mm

# Icon paths mapping
ICON_MAPPING = {
    'glutenfree': 'icon_glutenfree.png',
    'lactosefree': 'icon_lactosefree.png',
    'vegan': 'icon_vegan.png',
    'vegetarian': 'icon_vegetarian.png',
    'freezeable': 'icon_freezable.png',
    'love': 'icon_love.png',
    'component': 'icon_component.png',
    'dish': 'icon_dish.png',
    'food_for_dating': 'icon_FoodForDating.png',
    # Difficulty icons
    'icon_difficulty_1.png': 'icon_difficulty_1.png',
    'icon_difficulty_2.png': 'icon_difficulty_2.png',
    'icon_difficulty_3.png': 'icon_difficulty_3.png',
    # People icon
    'people': 'icon_people.svg',
    # Waiting time icon
    'waiting': 'icon_waiting.svg',
}




# Page Numbering Settings (used in CookbookGenerator.add_global_page_numbers)
# These match the footer style and ADR 0016 layout specifications
PAGE_NUMBER_FONT = 'Helvetica-Bold'
PAGE_NUMBER_FONT_SIZE = 8
PAGE_NUMBER_COLOR_RGB = (0.17, 0.20, 0.19)  # #2d3432 equivalent
PAGE_NUMBER_X_POSITION = 195 * mm  # Right edge minus 15mm margin (210mm - 15mm)
PAGE_NUMBER_Y_POSITION = 11 * mm   # 11mm from bottom

# Recipe Parsing Thresholds
VARIANT_LABEL_MAX_WORDS = 8  # Max words for a line to be treated as variant label
