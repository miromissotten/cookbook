"""Radar chart PNG rendering for cookbook graph markers.

Replaces ``==GRAPH_RADARGRAPH_START/END==`` table blocks in markdown with a
rendered radar chart, so a sauce page prints its flavour profile as a picture
- a native ``<img>`` tag Playwright already prints correctly - instead of a
table of numbers. Companion of ``graph_scatterplot`` for the same marker
convention.
"""

import math
import re
from pathlib import Path
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


from config import (
    COLOR_ON_SURFACE,
    COLOR_OUTLINE_VARIANT,
    COLOR_PRIMARY,
    COLOR_SECONDARY_FIXED,
    COLOR_SURFACE_CONTAINER_LOW,
    COLOR_WHITE,
    RADAR_RADIAL_LIMIT,
    RADAR_PRINT_WIDTH_MM,
    RADAR_PRINT_WIDTH_INCHES,
    RADAR_LABEL_FONT_PT,
    RADAR_LINE_WIDTH,
    RADAR_DPI,
)

# Public alias kept so main_generate_cookbook.py can continue importing
# PRINT_WIDTH_MM from this module without knowing about config.py.
PRINT_WIDTH_MM = RADAR_PRINT_WIDTH_MM


_SEPARATOR_RE = re.compile(r'^\|[\s\-:|]+\|$')


def _split_row(line: str):
    """Cells of one pipe-table row, without the outer pipes."""
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def _first_value_row(rows):
    """Values of the first row that is entirely numeric, else None."""
    for row in rows:
        try:
            return [float(cell) for cell in row]
        except ValueError:
            continue
    return None


def _parse_table(table_text: str):
    """Parse a radar table into ``(axis_labels, values)``.

    The block holds one header row naming the axes and one data row of 0-5
    ratings; alignment rows are skipped and further data rows ignored, since a
    chart draws a single sauce. Returns ``(None, None)`` when the block carries
    no usable pair of rows.
    """
    rows = []
    for line in table_text.splitlines():
        line = line.strip()
        if not line.startswith('|') or _SEPARATOR_RE.match(line):
            continue
        rows.append(_split_row(line))

    if len(rows) < 2:
        return None, None

    labels = [label for label in rows[0] if label]
    values = _first_value_row(rows[1:])
    # One value per axis: a table whose columns and numbers disagree is not a
    # chart, and guessing which side is wrong would print a misleading shape.
    if not labels or values is None or len(values) != len(labels):
        return None, None
    return labels, values


def render_radar_png(table_text: str, output_path: str,
                     headers: Optional[List[str]] = None) -> str:
    """Render a radar chart from a markdown pipe-table and return a ``file:///`` URI.

    Args:
        table_text: Raw table text (markdown pipe-table, without the marker lines).
        output_path: Filesystem path to write the PNG into.
        headers: Ignored. The radar table carries its axis names in its first
            row, so unlike the scatterplot it needs no header hints; the
            parameter exists only so the generator can hand every graph
            renderer the same keyword arguments.

    Returns:
        A ``file:///`` URI for the saved PNG.
    """
    labels, values = _parse_table(table_text)
    if not labels:
        raise ValueError("No valid axis/value rows found in radar chart table")

    # Authored ratings above the standard 0-5 scale still print in full instead
    # of running off the rim.
    limit = max(RADAR_RADIAL_LIMIT, math.ceil(max(values)))

    # Close the polygon by repeating the first point, so the outline joins up.
    angles = [2 * math.pi * index / len(labels) for index in range(len(labels))]
    closed_angles = angles + angles[:1]
    closed_values = values + values[:1]

    fig, ax = plt.subplots(figsize=(RADAR_PRINT_WIDTH_INCHES, RADAR_PRINT_WIDTH_INCHES),
                           subplot_kw={'projection': 'polar'})
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, limit)
    ax.set_yticks(range(1, limit + 1))
    ax.set_yticklabels([])  # The rings give scale, not numbers to read off.
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=RADAR_LABEL_FONT_PT, color=COLOR_ON_SURFACE)
    ax.plot(closed_angles, closed_values, color=COLOR_PRIMARY, linewidth=RADAR_LINE_WIDTH)
    ax.fill(closed_angles, closed_values, color=COLOR_SECONDARY_FIXED)
    ax.grid(True, color=COLOR_OUTLINE_VARIANT, alpha=0.6)
    ax.set_facecolor(COLOR_SURFACE_CONTAINER_LOW)
    ax.spines['polar'].set_color(COLOR_OUTLINE_VARIANT)
    fig.patch.set_facecolor(COLOR_WHITE)

    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=RADAR_DPI, bbox_inches='tight',
                facecolor=COLOR_WHITE)
    plt.close(fig)

    return Path(output_path).resolve().as_uri()