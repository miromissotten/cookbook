"""Measure the chapter page under splitter conditions, then print it.

If the measured geometry says 'fits' but the printed PDF clips rows, the
discrepancy is inside the same page session - this probe isolates it.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))

from html_to_pdf import _get_browser, _path_to_uri, wait_for_render_settled  # noqa: E402
from pypdf import PdfReader  # noqa: E402

SRC = ROOT / "debug" / "repro_chapter.html"
PDF = ROOT / "debug" / "repro_probe.pdf"

PROBE = r"""
() => {
  const sheet = document.querySelector('.recipe-page');
  const scs = getComputedStyle(sheet);
  const mainEl = sheet.closest('main');
  if (mainEl) { mainEl.style.display='block'; mainEl.style.padding='0';
                mainEl.style.minHeight='0'; }
  const tree = document.querySelector('.toc-flavortree');
  const intro = document.querySelector('.chapter-intro');
  const rows = [...document.querySelectorAll('[data-toc-target]')];
  const wrap = tree.parentElement;
  let header = null;
  for (const c of sheet.children) {
    if (c.querySelector && c.querySelector('h1')) { header = c; break; }
  }
  const headerH = header
    ? header.getBoundingClientRect().height +
      (parseFloat(getComputedStyle(header).marginBottom) || 0) : 0;
  return {
    fonts: document.fonts.status,
    sheetClientH: sheet.clientHeight,
    padTop: parseFloat(scs.paddingTop),
    padBot: parseFloat(scs.paddingBottom),
    headerH: headerH,
    introH: intro ? Math.round(intro.getBoundingClientRect().height) : null,
    treeScrollH: tree.scrollHeight,
    treeClientH: tree.clientHeight,
    wrapClientH: wrap.clientHeight,
    wrapScrollH: wrap.scrollHeight,
    row0H: rows.length ? Math.round(rows[0].getBoundingClientRect().height) : null,
    rowCount: rows.length,
    contentSpan: rows.length
      ? Math.round(rows[rows.length-1].getBoundingClientRect().bottom
                   - intro.getBoundingClientRect().top) : null,
  };
}
"""

browser = _get_browser()
page = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=1)
page.emulate_media(media="print")
page.goto(_path_to_uri(str(SRC.resolve())), timeout=60000, wait_until="networkidle")
wait_for_render_settled(page)
page.wait_for_timeout(150)
print("A (splitter conditions):")
print(json.dumps(page.evaluate(PROBE), indent=1))
page.wait_for_timeout(3000)
print("B (after +3s):")
print(json.dumps(page.evaluate(PROBE), indent=1))
page.pdf(path=str(PDF), width='210mm', height='297mm', print_background=True,
         margin={'top': '0mm', 'bottom': '0mm', 'left': '0mm', 'right': '0mm'})
page.close()

r = PdfReader(str(PDF))
text = (r.pages[0].extract_text() or "").replace(" ", "").lower()
print("pdf pages:", len(r.pages))
for needle in ("ramenflowchart", "risotto", "okonomiyaki", "lasagna",
               "pizzanapoletana"):
    print(f"  printed {needle!r}:", needle in text)
