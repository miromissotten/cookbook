"""Render one chapter's post-split chain for debug (steps 2-6).

Simulates what the build does after the splitter:
  step 2  front matter / parity blank decision (ADR 0015)
  step 3  conversion jobs with real footer bars (build_footer_bar)
  step 4  render_debug_preview output per debug page
"""

import re


def _safe_label(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_-") or "group"


def _chapter_label(job, placed, walk):
    """Return (label, placed) with front matter appended when walk wants it."""
    if not walk(job, placed):
        return (_safe_label(placed), placed)
    return (_safe_label(walk), walk)
