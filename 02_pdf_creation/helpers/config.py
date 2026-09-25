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
    'icon_difficulty_1.png': 'icon_difficulty_1.png',
    'icon_difficulty_2.png': 'icon_difficulty_2.png',
    'icon_difficulty_3.png': 'icon_difficulty_3.png',
    'people': 'icon_people.svg',
    'waiting': 'icon_waiting.svg',
}

# Page Numbering Settings (used in CookbookGenerator.add_global_page_numbers)
PAGE_NUMBER_FONT = 'Helvetica-Bold'
PAGE_NUMBER_FONT_SIZE = 8
PAGE_NUMBER_COLOR_RGB = (0.17, 0.20, 0.19)
PAGE_NUMBER_X_POSITION = 195 * mm
PAGE_NUMBER_Y_POSITION = 11 * mm

# Recipe Parsing Thresholds
VARIANT_LABEL_MAX_WORDS = 8

# ---------------------------------------------------------------------------
# Color Palette
# ---------------------------------------------------------------------------
COLOR_PRIMARY = "#47664a"
COLOR_ON_SURFACE = "#2d3432"
COLOR_SURFACE_CONTAINER_LOW = "#f1f4f2"
COLOR_SECONDARY_FIXED = "#d7e8cd"
COLOR_ON_SURFACE_VARIANT = "#59615f"
COLOR_WHITE = "#ffffff"
COLOR_OUTLINE_VARIANT = "#acb4b1"
COLOR_ON_SECONDARY = "#edfee2"
COLOR_SECONDARY_FIXED_DIM = "#c9dabf"
COLOR_INVERSE_ON_SURFACE = "#9b9d9c"
COLOR_OUTLINE = "#757c7a"
COLOR_SURFACE_VARIANT = "#dde4e1"
COLOR_SURFACE_CONTAINER = "#eaefec"
COLOR_ON_PRIMARY = "#e9ffe6"
COLOR_SECONDARY = "#54634e"
COLOR_TERTIARY = "#5a6331"
COLOR_ON_ERROR = "#fff7f6"
COLOR_ON_ERROR_CONTAINER = "#6e1400"

# RGB tuples (0-1 range) for ReportLab / PIL consumers that need them directly.
# link_injection.py and graph_radar.py accept tuples; provide them alongside
# the hex strings above so RGB consumers never recompute.
def _hex_to_rgb01(hex_color: str) -> tuple:
    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255
    return (r, g, b)


COLOR_PRIMARY_RGB = _hex_to_rgb01(COLOR_PRIMARY)
COLOR_ON_SURFACE_RGB = _hex_to_rgb01(COLOR_ON_SURFACE)

# Aliases kept so link_injection.py can import the names it already uses.
ACCENT_RGB = COLOR_PRIMARY_RGB
INK_RGB = COLOR_ON_SURFACE_RGB

# Mapping of tailwind-config color keys to hex values.
# HTML templates use these as .format() / .replace() placeholders named after
# the constant (e.g. {COLOR_PRIMARY}).
TAILWIND_COLORS = {
    "COLOR_SURFACE_CONTAINER_LOW": COLOR_SURFACE_CONTAINER_LOW,
    "COLOR_ON_SECONDARY": COLOR_ON_SECONDARY,
    "COLOR_PRIMARY": COLOR_PRIMARY,
    "COLOR_SECONDARY_FIXED_DIM": COLOR_SECONDARY_FIXED_DIM,
    "COLOR_ON_SURFACE_VARIANT": COLOR_ON_SURFACE_VARIANT,
    "COLOR_SECONDARY_FIXED": COLOR_SECONDARY_FIXED,
    "COLOR_INVERSE_ON_SURFACE": COLOR_INVERSE_ON_SURFACE,
    "COLOR_SECONDARY_CONTAINER": COLOR_SECONDARY_FIXED,
    "COLOR_SURFACE": COLOR_WHITE,
    "COLOR_WHITE": COLOR_WHITE,
    "COLOR_ON_ERROR": COLOR_ON_ERROR,
    "COLOR_ON_ERROR_CONTAINER": COLOR_ON_ERROR_CONTAINER,
    "COLOR_SURFACE_CONTAINER_LOWEST": COLOR_WHITE,
    "COLOR_OUTLINE": COLOR_OUTLINE,
    "COLOR_BACKGROUND": COLOR_WHITE,
    "COLOR_TERTIARY": COLOR_TERTIARY,
    "COLOR_SURFACE_VARIANT": COLOR_SURFACE_VARIANT,
    "COLOR_OUTLINE_VARIANT": COLOR_OUTLINE_VARIANT,
    "COLOR_ON_SURFACE": COLOR_ON_SURFACE,
    "COLOR_SURFACE_CONTAINER": COLOR_SURFACE_CONTAINER,
    "COLOR_ON_PRIMARY": COLOR_ON_PRIMARY,
    "COLOR_SECONDARY": COLOR_SECONDARY,
}

# ---------------------------------------------------------------------------
# Page Geometry
# ---------------------------------------------------------------------------
A4_WIDTH_MM = 210
A4_HEIGHT_MM = 297
PAGE_PADDING = "25mm 15mm 15mm 25mm"
PAGE_BOX_SHADOW = "0 20px 60px rgba(0,0,0,0.15)"
PAGE_BG = COLOR_WHITE
PAGE_BREAK_AFTER = "always"
PAGE_SIZE = "A4"

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
FONT_HEADLINE = "Manrope"
FONT_BODY = "Work Sans"
FONT_LABEL = "Plus Jakarta Sans"
FONT_FALLBACK = "Arial, sans-serif"

FONT_HEADLINE_STACK = f"'{FONT_HEADLINE}', {FONT_FALLBACK}"
FONT_BODY_STACK = f"'{FONT_BODY}', {FONT_FALLBACK}"
FONT_LABEL_STACK = f"'{FONT_LABEL}', {FONT_FALLBACK}"

# ---------------------------------------------------------------------------
# Hardcoded Paths
# ---------------------------------------------------------------------------
DEFAULT_INPUT_ROOTS = ("data_modularflavour/text", "data_modularflavour/text_notdone")
DEFAULT_OUTPUT_STEM = "cookbook"
TEMP_DIR_PREFIX = "cookbook_build_"
TEMP_HTML_STEM = "temp_combined"
TEMP_HTML_SUFFIX = ".html"
PARTIAL_PDF_SUFFIX = "_PARTIAL"
BASE_PDF_SUFFIX = "_base"
ANNEX_FILENAME = "_Annex.A. Full Table Of Contents.md"
ICON_DIR = "data_modularflavour/icon"

# ---------------------------------------------------------------------------
# ReportLab Constants
# ---------------------------------------------------------------------------
PAGE_W_PT = A4_WIDTH_MM / 25.4 * 72
PAGE_H_PT = A4_HEIGHT_MM / 25.4 * 72
PX_TO_PT = 72.0 / 96.0

# ---------------------------------------------------------------------------
# Mermaid Radar Constants
# ---------------------------------------------------------------------------
RADAR_DPI = 300
RADAR_LABEL_FONT_PT = 8
RADAR_LINE_WIDTH = 1.5
RADAR_RADIAL_LIMIT = 5
RADAR_PRINT_WIDTH_MM = 40
RADAR_PRINT_WIDTH_INCHES = RADAR_PRINT_WIDTH_MM / 25.4

# ---------------------------------------------------------------------------
# Mermaid Scatter Constants
# ---------------------------------------------------------------------------
SCATTER_FIGSIZE = (8, 5)
SCATTER_MARKER_SIZE = 120
SCATTER_ALPHA = 0.75
SCATTER_DPI = 150
SCATTER_LABEL_FONT_SIZE = 9
SCATTER_AXIS_FONT_SIZE = 11
SCATTER_TITLE_FONT_SIZE = 13

# ---------------------------------------------------------------------------
# Chromium Launch Constants
# ---------------------------------------------------------------------------
PAGE_LOAD_TIMEOUT_MS = 120000
RENDER_SETTLED_TIMEOUT_MS = 15000
FORCE_DEVICE_SCALE_FACTOR = 1
VIEWPORT_WIDTH = 794
VIEWPORT_HEIGHT = 1123

# ---------------------------------------------------------------------------
# JS Splitter Constants (interpolated into the page_splitter JS template)
# ---------------------------------------------------------------------------
SPLITTER_EPS = 14.0
SPLITTER_MIN_SCALE = 0.55
SPLITTER_JOIN_FLOOR = 0.80
SPLITTER_TABLE_CHUNK_MAX = 420
SPLITTER_SLIVER_MIN = 80
SPLITTER_TOC_SECTION_HEIGHT_THRESHOLD = 640
SPLITTER_TOC_CHUNK_MAX = 560
SPLITTER_LIST_CHUNK_HEIGHT_THRESHOLD = 380

# ---------------------------------------------------------------------------
# Link Injection Constants
# ---------------------------------------------------------------------------
BACK_TO_TOC_LABEL = "back to table of contents"
BACK_TO_TOC_FONT = "Helvetica"
BACK_TO_TOC_FONT_SIZE = 7
BACK_TO_TOC_BASELINE_MM = 5.8

# ---------------------------------------------------------------------------
# Watermark Constants
# ---------------------------------------------------------------------------
WATERMARK_COLOR_RGBA = "rgba(220, 38, 38, 0.18)"
WATERMARK_FONT_SIZE_REM = 7
WATERMARK_FONT_FAMILY = f"'{FONT_HEADLINE}', '{FONT_BODY}', '{FONT_LABEL}', {FONT_FALLBACK}"

# ---------------------------------------------------------------------------
# Build Lock Constants
# ---------------------------------------------------------------------------
BUILD_LOCK_FILENAME = ".build.lock"
BUILD_LOCK_STALE_HOURS = 2

# ---------------------------------------------------------------------------
# Temp Dir Constants
# ---------------------------------------------------------------------------
STALE_TEMP_DIR_PREFIX = "cookbook_build_"
STALE_TEMP_DIR_AGE_HOURS = 24
TEMP_WRITE_RETRY_COUNT = 2
