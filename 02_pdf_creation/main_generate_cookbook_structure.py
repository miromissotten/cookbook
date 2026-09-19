#!/usr/bin/env python3
"""Generate the cookbook structure file.

Each markdown file is prefixed with an ordered numeric label
(e.g. ``_2.1.3. My Recipe.md``).  The generator emits one entry per file
as a Markdown heading whose depth mirrors the label depth:

| Label depth | Heading   |
|-------------|-----------|
| 1 (``X.``)       | ``##``   |
| 2 (``X.X.``)      | ``###``  |
| 3 (``X.X.X.``)    | ``####`` |
| 4+ (``X.X.X.X.``) | ``#####``|

Status emojis (from ``text_description`` metadata) appear after the wiki
link, e.g. ``#### [[_1.1.1. Ramen]] ✅``.
"""

import re
import sys
from pathlib import Path
from typing import Optional, Sequence, Union

# Make helpers/input_roots importable when this file runs standalone
# (same pattern as the other entry points).
_SCRIPT_DIR = Path(__file__).parent.resolve()
_HELPERS_DIR = _SCRIPT_DIR / "helpers"
for _dir in (_SCRIPT_DIR, _HELPERS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from input_roots import iter_markdown_files, resolve_roots

# A single directory, or an ordered sequence of directories.
PathSpec = Union[str, Path, Sequence[Union[str, Path]]]


class StructureGenerator:
    """Generate _-1.0. cookbook_structure_generated.md.

    Scans markdown files across the ordered input roots (default:
    ``data_modularflavour/text`` plus ``data_modularflavour/text_notdone``,
    ADR 0023) and emits a depth-ordered structure file using Markdown
    headings that mirror the numeric prefix of each file. The first root is
    the primary one — the structure file is written there and it wins
    filename collisions.
    """

    def __init__(self, directory: Optional[PathSpec] = None):
        self.roots = resolve_roots(directory)
        # Primary root: hosts the generated structure file.
        self.directory = self.roots[0]
        self.exclude_patterns = [
            r"^_-",
            r"_structure\.md$",
            r"_content_table.*\.md$",
        ]

    def is_excluded(self, filename: str) -> bool:
        for pattern in self.exclude_patterns:
            if re.search(pattern, filename):
                return True
        return False

    def parse_prefix(self, filename: str):
        """Parse a numbered filename into (numeric_parts, title).

        ``_2.1.1. Ramen_Tare_Shio.md`` -> ((2, 1, 1), "Ramen_Tare_Shio")
        ``_3.1.1.A. Ramen_Tare_Shio.md`` -> ((3, 1, 1, 'A'), "Ramen_Tare_Shio")

        Numeric segments become ``int``; letter segments stay ``str`` so
        mixed tuples like (3, 1, 1, 'A') are preserved.
        """
        stem = Path(filename).stem
        match = re.match(r"^_(\d+(?:\.[\dA-Za-z]+)*)\.?\s*(.+)$", stem)
        if not match:
            return None

        numeric_str = match.group(1)
        title = match.group(2).strip()
        numeric_parts = tuple(
            int(x) if x.isdigit() else x
            for x in numeric_str.split(".")
        )

        return (numeric_parts, title)

    @staticmethod
    def _sort_key(numeric_parts):
        """Convert mixed int/str parts into a comparable sort key.

        Digits sort before letters at each position so that
        ``(3, 1, 1, 0)`` sorts before ``(3, 1, 1, 'A')``.
        """
        return tuple(
            (0, int(x)) if str(x).isdigit() else (1, str(x))
            for x in numeric_parts
        )

    @staticmethod
    def _heading_level(depth: int) -> str:
        """Return the Markdown heading string for a given label depth.

        depth 1 -> ``##``, 2 -> ``###``, 3 -> ``####``, 4 -> ``#####``,
        5+ -> ``######`` (Markdown's maximum).
        """
        num_hashes = min(depth + 1, 6)
        return "#" * num_hashes

    def get_status(self, filename: str) -> str | None:
        """Read text_description status from a markdown file."""
        file_path = self.directory / filename
        if not file_path.exists():
            # The file may live in a secondary input root.
            for root in self.roots[1:]:
                candidate = root / filename
                if candidate.exists():
                    file_path = candidate
                    break
        if not file_path.exists():
            return None

        content = file_path.read_text(encoding="utf-8")
        match = re.search(r"text_description:\s*(\w+)", content)
        if match:
            return match.group(1)
        return None

    def get_status_emoji(self, status: str | None) -> str:
        """Get emoji for status."""
        if status is None:
            return ""
        emojis = {
            "done": "✅",
            "ongoing": "🔄",
            "todo": "❌",
        }
        return emojis.get(status, "")

    def generate_structure_file(self):
        """Generate the structure file content as a Markdown string.

        Scans all markdown files in ``self.directory``, parses their
        numeric prefixes, sorts them in natural book order, and emits
        each as a heading whose depth mirrors the label depth:

        ``depth 1 -> ##``, ``depth 2 -> ###``, ``depth 3 -> ####``,
        ``depth 4+ -> #####``.
        """
        all_files = iter_markdown_files(self.roots)

        entries = []
        seen_prefixes: dict = {}
        for filename in all_files:
            if self.is_excluded(filename):
                continue
            parsed = self.parse_prefix(filename)
            if not parsed:
                continue
            numeric_parts, _title = parsed
            if numeric_parts in seen_prefixes:
                print(f"WARNING: duplicate numeric prefix "
                      f"{'.'.join(str(p) for p in numeric_parts)}: "
                      f"'{filename}' and '{seen_prefixes[numeric_parts]}' "
                      f"- check your input roots")
            seen_prefixes[numeric_parts] = filename
            entries.append({
                "numeric_parts": numeric_parts,
                "filename": filename,
            })

        # Sort by numeric parts (natural book order), tie-break by filename
        entries.sort(
            key=lambda e: (self._sort_key(e["numeric_parts"]), e["filename"])
        )

        output_lines = ["# Book Name: Modular Flavour"]

        for entry in entries:
            filename = entry["filename"]
            file_stem = filename.replace(".md", "")
            depth = len(entry["numeric_parts"])
            heading = self._heading_level(depth)

            status = self.get_status(filename)
            emoji = self.get_status_emoji(status)

            if emoji:
                output_lines.append(f"{heading} [[{file_stem}]] {emoji}")
            else:
                output_lines.append(f"{heading} [[{file_stem}]]")

        return "\n".join(output_lines) + "\n"

    def run(self):
        content = self.generate_structure_file()
        output_path = self.directory / "_-1.0. cookbook_structure_generated.md"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return str(output_path)


if __name__ == "__main__":
    base_dir = Path(__file__).parent.parent / "data_modularflavour"
    generator = StructureGenerator(directory=[
        str(base_dir / "text"),
        str(base_dir / "text_notdone"),
    ])
    output_path = generator.run()
    print(f"Structure file generated: {output_path}")
