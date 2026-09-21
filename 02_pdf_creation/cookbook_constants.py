import re
from helpers.graph_radar import PRINT_WIDTH_MM

_WIKI_LINK_RE = re.compile(r'(?<!!)\[\[([^\]|]+(?:\|[^\]]+)?)\]\]')

TOC_PAGE_TITLE = "Table of Contents"
cookbook_folder = "data_modularflavour"

SCATTERPLOT_KIND = 'SCATTERPLOT'
RADAR_KIND = 'RADARGRAPH'
SCATTERPLOT_IMG_STYLE = 'max-width:100%;height:auto'
RADAR_IMG_STYLE = f'width:{PRINT_WIDTH_MM}mm;height:auto'
RADAR_IMG_ALT = 'Radar chart of the flavour profile'

_LOVE_HEART_SIZE_MM = 6
_LOVE_HEART_OPTICAL_OFFSET_PT = 3

_WATERMARK_CSS = """\
.notdone-watermark::after {
    content: "miró not happy yet";
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-45deg);
    color: rgba(220, 38, 38, 0.18);
    font-family: 'Manrope', 'Work Sans', 'Plus Jakarta Sans', Arial, sans-serif;
    font-size: 7rem;
    font-weight: 700;
    white-space: nowrap;
    pointer-events: none;
    z-index: 50;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}"""
