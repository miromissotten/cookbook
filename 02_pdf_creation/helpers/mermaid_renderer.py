"""
Mermaid diagram baking for the cookbook build.

Every sheet template renders its own mermaid on load; ``bake_mermaid_in_file``
loads a rendered sheet in the shared browser and freezes each diagram to
static SVG before the layout pass measures it.
"""

from pathlib import Path

# Use nest_asyncio to allow Playwright sync API inside asyncio loop
import nest_asyncio
nest_asyncio.apply()

# Shared browser instance; html_to_pdf owns it and hands it over via set_browser.
_mermaid_browser = None

def get_browser():
    """Get the mermaid browser instance (for sharing with html_to_pdf)."""
    global _mermaid_browser
    return _mermaid_browser

def set_browser(browser):
    """Set the mermaid browser instance from an externally created browser."""
    global _mermaid_browser
    _mermaid_browser = browser

def bake_mermaid_in_file(html_path: str, browser) -> bool:
    """Render <div class="mermaid"> blocks on the loaded file page itself.

    Loads the HTML file in the shared browser and uses the page's own
    mermaid library (templates load lib/mermaid.min.js relative to the file),
    avoiding the giant data:-URL navigation that Chromium aborts. Rewrites the
    file with static SVGs.

    Returns True when every diagram ended up rendered - either baked here or
    already drawn by the template's own startOnLoad auto-render, which races
    (and usually wins) against this pass. Returns False when the page carries
    no mermaid blocks at all. Raises RuntimeError only when unrendered diagram
    source remains after one automatic retry with a fresh page load.
    """
    result = _bake_mermaid_attempt(html_path, browser)
    if result["failed"] > 0 and result["baked"] == 0 and result["already"] == 0:
        # One fresh-load retry absorbs transient render/font races.
        result = _bake_mermaid_attempt(html_path, browser)
    if result["failed"] > 0 and result["baked"] == 0 and result["already"] == 0:
        raise RuntimeError(
            f"{result['failed']} mermaid diagram(s) present but none rendered"
        )
    return bool(result["baked"] > 0 or result["already"] > 0)


def _bake_mermaid_attempt(html_path: str, browser) -> dict:
    """One bake pass over the file; returns {'baked', 'already', 'failed'}."""
    from html_to_pdf import _path_to_uri, PAGE_LOAD_TIMEOUT, wait_for_render_settled

    path = Path(html_path)
    page = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=1)
    try:
        page.goto(_path_to_uri(str(path.resolve())),
                  timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")
        wait_for_render_settled(page)
        if not page.query_selector('div.mermaid'):
            return {"baked": 0, "already": 0, "failed": 0}
        counts = page.evaluate("""
            async () => {
              const counts = {already: 0, baked: 0, failed: 0};
              for (const d of Array.from(document.querySelectorAll('div.mermaid'))) {
                // Mermaid v10 auto-render keeps class="mermaid", empties the
                // text and drops an SVG inside plus data-processed - treat
                // those as done instead of misreporting them as failures.
                if ((d.querySelector && d.querySelector('svg'))
                        || d.hasAttribute('data-processed')) {
                  counts.already += 1;
                  continue;
                }
                const code = (d.textContent || '').trim();
                if (!code) continue;
                try {
                  const id = 'mmd-' + Math.random().toString(36).slice(2);
                  const r = await window.mermaid.render(id, code);
                  d.innerHTML = r.svg;
                  d.classList.remove('mermaid');
                  d.classList.add('mermaid-diagram');
                  counts.baked += 1;
                } catch (err) {
                  counts.failed += 1;
                }
              }
              return counts;
            }
        """)
        counts = dict(counts or {"baked": 0, "already": 0, "failed": 0})
        if counts.get("baked", 0) > 0:
            html = '<!DOCTYPE html>\n' + page.evaluate(
                "() => document.documentElement.outerHTML")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(html)
        return counts
    finally:
        page.close()
