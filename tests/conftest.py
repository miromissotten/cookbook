"""Behavioural characterization tests for the cookbook PDF pipeline.

Pure, dependency-free helpers only: no browser, no real data_modularflavour/text,
no writes outside tmp dirs. Run: python -m unittest discover -s tests -v
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PDF_ROOT = REPO_ROOT / "02_pdf_creation"
HELPERS_DIR = PDF_ROOT / "helpers"

for _dir in (str(PDF_ROOT), str(HELPERS_DIR)):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
