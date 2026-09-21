import os
from pathlib import Path

from helpers.console_logging import warn


def acquire_build_lock(exports_dir: Path) -> tuple:
    import time
    lock_path = exports_dir / ".build.lock"
    try:
        if lock_path.exists():
            age_h = (time.time() - lock_path.stat().st_mtime) / 3600
            if age_h < 2:
                print(
                    "ERROR: another cookbook build appears to be running "
                    f"(lock: {lock_path}, {age_h * 60:.0f} min old). "
                    "Wait for it to finish; if you are certain none is "
                    "running, delete the lock file and retry."
                )
                return False, None
            warn(f"removing stale build lock ({age_h:.1f} h old) from a crashed run")
            lock_path.unlink()
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True, lock_path
    except FileExistsError:
        print(f"ERROR: another cookbook build appears to be running "
              f"(lock: {lock_path}). If you are certain none is running, "
              "delete the lock file and retry.")
        return False, None
    except OSError as exc:
        warn(f"could not create build lock ({exc}); continuing without one")
        return True, None


def release_build_lock(build_lock_path: Path) -> None:
    if build_lock_path is not None:
        try:
            build_lock_path.unlink()
        except OSError:
            pass
