"""
[DEBUG TOOL] Throwaway diagnostic for the "vanishing sheets" bug.

Polls one or more directories and logs every file created/deleted/rewritten
between snapshots, with timestamps. Read-only: it never touches the watched
files. Run it alongside a cookbook build to prove whether an external process
(cloud-sync reconciliation, antivirus) deletes intermediate files mid-build:

    python 02_pdf_creation/debug/debug_watch_temp.py exports/_temp --stop-after 600
    # in a second terminal (run from the repository root):
    python 02_pdf_creation/main_generate_cookbook.py --temp-dir exports/_temp

Omit --stop-after to watch until Ctrl+C.
"""

import argparse
import time
from pathlib import Path


def snapshot(dirs):
    """Return {path: size} for every file under the watched directories.

    Files that are locked or vanish mid-poll (Chromium holds write handles,
    sync engines delete) are simply skipped: a watcher must never die because
    of what it observes.
    """
    state = {}
    for d in dirs:
        root = Path(d)
        if root.exists():
            try:
                entries = list(root.rglob("*"))
            except OSError:
                continue
            for f in entries:
                try:
                    if f.is_file():
                        state[str(f)] = f.stat().st_size
                except OSError:
                    pass
    return state


def main():
    parser = argparse.ArgumentParser(
        description="Watch directories and log file create/delete/rewrite events.")
    parser.add_argument("dirs", nargs="+", help="Directories to watch")
    parser.add_argument("--interval", type=float, default=0.5,
                        help="Poll interval in seconds (default: 0.5)")
    parser.add_argument("--stop-after", type=float, default=None,
                        help="Stop watching after N seconds (default: run until Ctrl+C)")
    args = parser.parse_args()

    print(f"[watch] polling {args.dirs} every {args.interval}s", flush=True)
    previous = snapshot(args.dirs)
    print(f"[watch] initial snapshot: {len(previous)} file(s)", flush=True)
    started = time.monotonic()

    try:
        while True:
            time.sleep(args.interval)
            current = snapshot(args.dirs)
            for name in sorted(set(previous) - set(current)):
                print(f"[watch] DELETED  {name}", flush=True)
            for name in sorted(set(current) - set(previous)):
                print(f"[watch] CREATED  {name} ({current[name]} bytes)", flush=True)
            for name in sorted(set(current) & set(previous)):
                if current[name] != previous[name]:
                    print(f"[watch] REWRITTEN {name} "
                          f"({previous[name]} -> {current[name]} bytes)", flush=True)
            previous = current
            if args.stop_after is not None and time.monotonic() - started >= args.stop_after:
                break
    except KeyboardInterrupt:
        pass
    finally:
        print(f"[watch] done after {time.monotonic() - started:.1f}s; "
              f"final count: {len(previous)} file(s)", flush=True)


if __name__ == "__main__":
    main()
