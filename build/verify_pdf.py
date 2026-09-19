"""Verify the rebuilt PDF contains the units that were previously clipped/lost.

Scan is in-memory: text is extracted once into a list, then searched.
Run after a build: python build/verify_pdf.py
"""
import fitz, glob, sys

FILES = sorted(glob.glob("exports/cookbook_digital.pdf"))
if not FILES:
    print("No cookbook_digital.pdf found in exports/"); sys.exit(2)
PDF = FILES[0]

targets = [
    ("Risotto-impress-kettle",    "start to boil a kettle"),
    ("Risotto-impress-onion",     "put the onion in a pan"),
    ("Risotto-impress-preamble",  "simple weekday version"),
    ("Carbonara-step1-parallel",  "step 1 of things in parallel"),
    ("Carbonara-solidified-eggs", "solidified eggs"),
    ("Pizza-taglio-bread",        "pizza al taglio bread"),
    ("Pizza-taglio-peppers1",     "Roast peppers until skins blacken"),
    ("Bibimbap-step7",            "serve with sesame"),
    ("Okonomiyaki-sauce",         "Okonomi sauce"),
    ("Aglio-original-step8",      "parsley to finish"),
    ("Aglio-cheat-step6",         "serve with black pepper"),
    ("Hummus-step1",              "Combine the chickpeas"),
    ("Hummus-step9",              "Store leftovers in the refrigerator"),
]

def clean(s):
    return s.replace("\u00a0", " ")

d = fitz.open(PDF)
pages = [clean(d[i].get_text()) for i in range(d.page_count)]
print(f"pages: {d.page_count}  file: {PDF}")
print("-" * 72)
ok = True
for name, w in targets:
    found = [i + 1 for i, t in enumerate(pages) if w in t]
    if not found:
        ok = False
        print(f"FAIL  {name:28s} \"{w[:46]}\" -> NOT FOUND")
    else:
        print(f"ok    {name:28s} \"{w[:46]}\" -> pages {found}")
print("-" * 72)
if ok:
    print("ALL TARGETS PRESENT")
    d.close()
    sys.exit(0)
d.close()
sys.exit(1)

