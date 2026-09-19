"""Ordered multi-root markdown input for the cookbook build.

The vault splits finished and work-in-progress page sources across two
sibling folders (``data_modularflavour/text`` and
``data_modularflavour/text_notdone``). The split is purely an authoring
aid: the build must treat both folders as one virtual input directory
(ADR 0023).

Root order is precedence: ``text`` comes first, so a file present in both
folders resolves to the finished copy and shadowing is reported instead of
staying silent.
"""

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

# A single directory, or an ordered sequence of directories.
PathSpec = Union[str, Path, Sequence[Union[str, Path]]]

# Default search order: finished sources win over work-in-progress ones.
DEFAULT_INPUT_DIRS: Sequence[str] = (
    "data_modularflavour/text",
    "data_modularflavour/text_notdone",
)


def resolve_roots(spec: Optional[PathSpec] = None) -> List[Path]:
    """Normalize a directory spec into an ordered, de-duplicated root list.

    Args:
        spec: ``None`` (use ``DEFAULT_INPUT_DIRS``), a single directory, or
            an ordered sequence of directories.

    Returns:
        Ordered root list. Non-existent roots are kept so a folder that is
        temporarily empty or renamed never silently changes resolution
        semantics; individual lookups simply skip missing roots.
    """
    if spec is None:
        paths: List[Path] = [Path(p) for p in DEFAULT_INPUT_DIRS]
    elif isinstance(spec, (str, Path)):
        paths = [Path(spec)]
    else:
        paths = [Path(p) for p in spec]

    if not paths:
        raise ValueError("input spec resolved to an empty root list")

    roots: List[Path] = []
    seen = set()
    for path in paths:
        try:
            key = str(Path(path).resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        roots.append(Path(path))
    return roots


def find_file(roots: Sequence[Path], filename: str) -> Optional[Path]:
    """Return the first existing ``root / filename`` (root order = precedence)."""
    for root in roots:
        candidate = root / filename
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def iter_markdown_files(roots: Sequence[Path]) -> List[str]:
    """Union of ``*.md`` basenames across roots, sorted; first root wins.

    A filename that exists in several roots is de-duplicated (the earliest
    root's copy is used) and reported once, so shadowing never happens
    silently.
    """
    winner: Dict[str, Path] = {}
    shadowed: List[str] = []
    for root in roots:
        try:
            entries = list(root.glob("*.md"))
        except OSError:
            continue
        for entry in entries:
            if entry.name in winner:
                if entry.name not in shadowed:
                    shadowed.append(entry.name)
            else:
                winner[entry.name] = root

    if shadowed:
        print(f"WARNING: {len(shadowed)} markdown filename(s) exist in "
              f"several input roots; the first root's copy wins: "
              f"{', '.join(sorted(shadowed))}")

    return sorted(winner)
