"""Convert the repro chapter page to PDF and inspect what actually prints."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))

from html_to_pdf import _convert_single_to_pdf, build_footer_template  # noqa: E402
from pypdf import PdfReader  # noqa: E402

SRC = ROOT / "debug" / "repro_chapter.html"
OUT = ROOT / "debug" / "repro_chapter.pdf"

ok = _convert_single_to_pdf(str(SRC), str(OUT),
                            footer_html=build_footer_template("Architectures", ""))
print("converted:", ok)

r = PdfReader(str(OUT))
print("pdf pages:", len(r.pages))
text = r.pages[0].extract_text() or ""
rows = ["Ramen flowchart", "Carbonara", "Risotto", "Okonomiyaki", "Lasagna",
        "Parmigiana", "Pizza Al Taglio", "Pizza Napoletana"]
for row in rows:
    print(f"  {row!r:30} printed: {row in text}")
