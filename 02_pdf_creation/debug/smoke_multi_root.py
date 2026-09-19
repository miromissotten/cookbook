"""Smoke check: structure merges both text roots (ADR 0023)."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "02_pdf_creation")
sys.path.insert(0, "02_pdf_creation/helpers")

from structure_parser import StructureParser  # noqa: E402

base = Path("data_modularflavour")
parser = StructureParser([str(base / "text"), str(base / "text_notdone")])
files = parser.parse_structure_file("_-1.0. cookbook_structure_generated.md")

counts = Counter()
missing = []
for name in files:
    if (base / "text" / name).exists():
        counts["text"] += 1
    elif (base / "text_notdone" / name).exists():
        counts["text_notdone"] += 1
    else:
        missing.append(name)

print("resolved files:", len(files))
print("per root:", dict(counts))
print("missing:", missing or "none")
assert not missing, missing
print("SMOKE OK")
