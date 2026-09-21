"""Scatterplot PNG rendering for cookbook graph markers.

Replaces ``==GRAPH_SCATTERPLOT_START/END==`` table blocks in markdown
with rendered scatterplot images so the PDF cookbook ships them as
native ``<img>`` tags Playwright already prints correctly.
"""

import re

from typing import List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path


_COL_STYLE = 1
_COL_X = 2
_COL_Y = 3


def _parse_table(table_text: str):
    """Parse a pipe-table block into ``(headers, rows)``.

    The first pipe-line whose x-column value cannot be parsed as a float is
    treated as the header row. Returns ``([], rows)`` when no header row is
    found so callers can still fall back to default labels safely.
    """
    rows = []
    headers = []
    for line in table_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        if re.search(r'^\|[\s\-:]+\|$', line):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 4:
            continue
        if not headers:
            try:
                float(cells[_COL_X])
            except (ValueError, IndexError):
                headers = cells
                continue
        try:
            style = cells[_COL_STYLE]
            x = float(cells[_COL_X])
            y = float(cells[_COL_Y])
        except (ValueError, IndexError):
            continue
        rows.append((style, x, y))
    return headers, rows


def render_scatterplot_png(table_text: str, output_path: str,
                           headers: Optional[List[str]] = None) -> str:
    """Render a scatterplot from a markdown pipe-table and return a ``file:///`` URI.

    Args:
        table_text: Raw table text (markdown pipe-table, without the marker lines).
        output_path: Filesystem path to write the PNG into.
        headers: Optional column header names; when omitted the headers are
            parsed from the table's first non-data row.

    Returns:
        A ``file:///`` URI for the saved PNG.
    """
    parsed_headers, rows = _parse_table(table_text)
    headers = headers or parsed_headers

    x_label = headers[_COL_X] if len(headers) > _COL_X else "X"
    y_label = headers[_COL_Y] if len(headers) > _COL_Y else "Y"
    chart_title = x_label

    if not rows:
        raise ValueError("No valid data rows found in scatterplot table")

    styles = [r[0] for r in rows]
    xs = [r[1] for r in rows]
    ys = [r[2] for r in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(xs, ys, s=120, alpha=0.75, color="#47664a", edgecolors="#2d3432", linewidths=0.5)

    for i, style in enumerate(styles):
        y_offset = 6 if i % 2 == 0 else -16
        ax.annotate(
            style,
            (xs[i], ys[i]),
            textcoords="offset points",
            xytext=(6, y_offset),
            fontsize=9,
            color="#2d3432",
        )

    ax.set_xlabel(x_label, fontsize=11, color="#2d3432")
    ax.set_ylabel(y_label, fontsize=11, color="#2d3432")
    ax.set_title(chart_title, fontsize=13, fontweight="bold", color="#2d3432")
    ax.grid(True, alpha=0.25, color="#acb4b1")
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f1f4f2")
    for spine in ax.spines.values():
        spine.set_color("#acb4b1")

    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#ffffff")
    plt.close(fig)

    return Path(output_path).resolve().as_uri()
