import os
from pathlib import Path


def build_file_uri(filename: str, input_dir: str, input_roots, script_dir: Path) -> str:
    filename = os.path.basename(filename)
    if '#' in filename:
        filename = filename.split('#')[0].strip()

    search_roots = [
        str(input_dir),
        *[str(root) for root in input_roots[1:]],
        str(script_dir.parent / "data_modularflavour" / "images"),
        str(Path("data_modularflavour") / "images"),
        str(script_dir.parent / "data_modularflavour" / "icon"),
        str(Path("data_modularflavour") / "icon"),
        ".",
    ]
    for root in search_roots:
        candidate = Path(root) / filename
        try:
            if candidate.is_file():
                return candidate.resolve().as_uri()
        except OSError:
            continue

    base_path = str(input_dir)
    abs_path = os.path.abspath(base_path).replace(os.sep, '/')

    if ':' in abs_path:
        return f'file:///{abs_path}/{filename}'
    return f'file://{abs_path}/{filename}'
