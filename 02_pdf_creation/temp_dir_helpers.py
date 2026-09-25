import shutil
import tempfile
from pathlib import Path
from typing import Callable, Optional

from config import (
    STALE_TEMP_DIR_PREFIX,
    STALE_TEMP_DIR_AGE_HOURS,
    TEMP_WRITE_RETRY_COUNT,
)


def ensure_temp_dir(temp_dir: Path) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)


def sweep_stale_temp_dirs(temp_dir: Path) -> None:
    import time
    base = Path(tempfile.gettempdir())
    for d in base.glob(f"{STALE_TEMP_DIR_PREFIX}*"):
        if d == temp_dir:
            continue
        try:
            age_h = (time.time() - d.stat().st_mtime) / 3600
            if age_h > STALE_TEMP_DIR_AGE_HOURS:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            continue


def clear_temp_dir_contents(temp_dir: Path, warn: Optional[Callable[[str], None]] = None) -> None:
    for entry in temp_dir.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
        except OSError as exc:
            if warn is not None:
                warn(f"could not clear temp entry {entry}: {exc}")


def write_temp_html(temp_dir: Path, filename_stem: str, html_content: str) -> str:
    html_path = temp_dir / f"{filename_stem}.html"
    last_exc: Optional[Exception] = None
    for attempt in range(TEMP_WRITE_RETRY_COUNT):
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return str(html_path)
        except OSError as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise
    raise last_exc  # pragma: no cover - loop always returns or raises above
