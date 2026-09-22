"""Run debug_split_recipe.py on the given recipe file and write its stdout
to a temp file we can read back. Avoids %TEMP% redirection quirks in the
PowerShell runner."""
import runpy, sys, tempfile, os

recipe = sys.argv[1]
tmp = os.path.join(tempfile.gettempdir(), "r2.txt")
with open(tmp, "w", encoding="utf-8") as fh:
    sys.stdout = fh
    runpy.run_path("debug/debug_split_recipe.py")
    sys.stdout = sys.__stdout__
print("wrote", tmp)
