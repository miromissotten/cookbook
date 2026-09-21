import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PDF_ROOT = REPO_ROOT / "02_pdf_creation"
HELPERS_DIR = PDF_ROOT / "helpers"
DEBUG_DIR = PDF_ROOT / "debug"
for _dir in (str(PDF_ROOT), str(HELPERS_DIR), str(DEBUG_DIR)):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
