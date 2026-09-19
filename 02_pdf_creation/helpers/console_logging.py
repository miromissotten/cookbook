"""Lightweight console logging for the cookbook build.

A single place for severity prefixes and progress formatting so every
status message is greppable and reads the same way. No external logging
dependency is introduced (kept stdlib per the project conventions) and no
behavioral side effect beyond the printed text; the markdown generation
report is rendered separately by ``report_summary`` /
``generation_report`` and is unaffected.

Severity prefixes:
    [INFO]   informational status (progress, milestones, results)
    [WARN]   a non-fatal issue; the build continues
    [ERROR]  a fatal issue; the build aborts
"""
import sys


def progress(message: str) -> None:
    """Print a progress/status line (informational)."""
    print(message)


def info(message: str) -> None:
    """Print a single informational line with a stable prefix."""
    print(f"[INFO] {message}")


def warn(message: str) -> None:
    """Print a warning line with a stable prefix."""
    print(f"[WARN] {message}", file=sys.stderr)


def error(message: str) -> None:
    """Print a fatal-error line with a stable prefix (to stderr)."""
    print(f"[ERROR] {message}", file=sys.stderr)


def fatal(message: str, exit_code: int = 1) -> "SystemExit":
    """Print a fatal error and raise SystemExit so callers can ``sys.exit``.

    Returns the exception so a call site can ``sys.exit(fatal(...))`` without
    changing the exit code contract of the surrounding code.
    """
    error(message)
    raise SystemExit(exit_code)
