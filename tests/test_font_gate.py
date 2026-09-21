"""Unit tests for the font-readiness gate (ADR 0018).

The gate guards the print pipeline against the silent Segoe UI fallback
incident: ``document.fonts.status`` cannot detect a failed webfont fetch,
so ``ensure_print_fonts`` probes each required family (and Tailwind)
directly, reloads once on failure and refuses to print on a second
failure. Also pins the vendored-font wiring of the sheet templates.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from html_to_pdf import ensure_print_fonts

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPERS_DIR = REPO_ROOT / "02_pdf_creation" / "helpers"


class _FakePage:
    """Minimal Playwright page double with scripted probe results.

    Each ``evaluate`` call consumes one scripted result; ``reload`` just
    counts, like ``wait_for_function`` (mirroring wait_for_render_settled).
    """

    def __init__(self, probe_results=()):
        self._probe_results = list(probe_results)
        self.reload_count = 0
        self.wait_calls = 0

    def evaluate(self, _js):
        if not self._probe_results:
            raise AssertionError("unexpected extra probe call")
        return self._probe_results.pop(0)

    def reload(self, **_kwargs):
        self.reload_count += 1

    def wait_for_function(self, *_args, **_kwargs):
        self.wait_calls += 1


class _RaisingFirstProbePage(_FakePage):
    """First evaluate raises (JS/runtime hiccup), later ones are scripted."""

    def __init__(self, probe_results):
        super().__init__(probe_results)
        self._first = True

    def evaluate(self, js):
        if self._first:
            self._first = False
            raise RuntimeError("probe boom")
        return super().evaluate(js)


class _ReloadFailsPage(_FakePage):
    def reload(self, **_kwargs):
        self.reload_count += 1
        raise RuntimeError("reload boom")


class _ProbeRaisesAndReloadFailsPage(_FakePage):
    """Probe always raises and the recovery reload fails too."""

    def evaluate(self, _js):
        raise RuntimeError("probe boom")

    def reload(self, **_kwargs):
        self.reload_count += 1
        raise RuntimeError("reload boom")


class EnsurePrintFontsTests(unittest.TestCase):
    def test_fonts_loaded_returns_true_without_reload(self):
        page = _FakePage([[]])
        self.assertTrue(ensure_print_fonts(page))
        self.assertEqual(page.reload_count, 0)
        self.assertEqual(page.wait_calls, 0)

    def test_failed_font_reloads_once_then_succeeds(self):
        page = _FakePage([["600 16px Manrope"], []])
        with patch("builtins.print"):
            self.assertTrue(ensure_print_fonts(page))
        self.assertEqual(page.reload_count, 1)
        # wait_for_render_settled re-runs after the reload (2 probes inside).
        self.assertEqual(page.wait_calls, 2)

    def test_persistent_failure_returns_false_after_single_reload(self):
        page = _FakePage([["tailwind"], ["tailwind"]])
        with patch("builtins.print"):
            self.assertFalse(ensure_print_fonts(page))
        self.assertEqual(page.reload_count, 1)

    def test_probe_error_reloads_and_can_recover(self):
        page = _RaisingFirstProbePage([[]])
        with patch("builtins.print"):
            self.assertTrue(ensure_print_fonts(page))
        self.assertEqual(page.reload_count, 1)

    def test_probe_error_with_failed_reload_returns_false(self):
        page = _ProbeRaisesAndReloadFailsPage()
        with patch("builtins.print"):
            self.assertFalse(ensure_print_fonts(page))
        self.assertEqual(page.reload_count, 1)

    def test_failed_reload_returns_false_immediately(self):
        page = _ReloadFailsPage([["600 16px Manrope"]])
        with patch("builtins.print"):
            self.assertFalse(ensure_print_fonts(page))
        self.assertEqual(page.reload_count, 1)


class TemplateFontWiringTests(unittest.TestCase):
    """Guards the vendored-font regression (CDN fallback).

    These tests inspect production source files for specific strings.
    They are intentionally implementation-sensitive: the alternative
    (rendering a full PDF and inspecting font URLs) would require a
    browser and be orders of magnitude slower. The cost of brittleness
    is low because the vendored-font wiring is stable infrastructure,
    not frequently-changed logic.
    """

    def _sources(self):
        return [
            (HELPERS_DIR / "page_toc.py").read_text(encoding="utf-8"),
            (HELPERS_DIR / "page_content.py").read_text(encoding="utf-8"),
            (HELPERS_DIR / "page_renderer.py").read_text(encoding="utf-8"),
        ]

    def test_sheet_templates_reference_vendored_fonts(self):
        for src in self._sources():
            self.assertIn('href="lib/fonts/fonts.css"', src)

    def test_no_google_fonts_cdn_left_in_sheet_templates(self):
        for src in self._sources():
            self.assertNotIn("fonts.googleapis.com", src)

    def test_vendored_font_css_is_local_only_and_covers_families(self):
        css = (REPO_ROOT / "02_pdf_creation" / "lib" / "fonts" / "fonts.css"
               ).read_text(encoding="utf-8")
        self.assertIn("@font-face", css)
        self.assertNotIn("https://", css)
        for family in ("Manrope", "Work Sans", "Plus Jakarta Sans",
                       "Material Symbols Outlined"):
            self.assertIn(f"font-family: '{family}'", css)


if __name__ == "__main__":
    unittest.main()
