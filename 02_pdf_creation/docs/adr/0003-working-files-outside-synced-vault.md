# 0003 - Build working files live outside the synced vault

## Status

Accepted

## Context

The vault lives inside a Google Drive sync root (`My Drive/.../kookboek_ModularFlavour`).
The build writes ~107 intermediate HTML sheets plus group PDFs into a working
folder before anything is printed. Sync engines reconcile asynchronously, and
twice this collided head-on with a running build:

1. **Folder-level race** (fixed earlier): deleting and recreating the working
   folder raced Drive's reconciliation, which deleted the freshly recreated
   folder mid-build, breaking every page write. The fix - clearing only the
   *contents* of `exports/_temp` - is why the code refuses to delete the
   folder itself to this day.
2. **File-level wave**: one build lost 105 of 107 freshly written sheets mid-run.
   The layout pass aborted at the first missing file (one try wrapped the whole
   pass), conversion then combined zero-page groups into *blank* PDFs that
   counted as success, and the run silently shipped a partial cookbook
   (title page + blanks) with exit code 0. A later instrumented reproduction
   with a directory watcher caught the same actor deleting two copied JS libs;
   no pipeline code deletes source sheets between writing and converting.

## Decision

- **Working files default outside any synced tree**: intermediate artifacts go
  to `<system temp>/cookbook_build`. Only the final PDF (and the human-read
  generation report) land in the vault's `exports/`.
- **Escape hatch**: `--temp-dir` opts back into an in-vault working folder for
  debugging - paired with the watcher tool when sync interference is suspected.
- **Fail loudly instead of shipping blanks**:
  - the layout pass survives per-file failures (per-job try/except) and logs
    each one;
  - before conversion, every queued sheet must exist or the build stops with
    an explicit "sheets disappeared before conversion" error;
  - a group whose inputs all vanished converts to nothing (never a blank PDF);
  - failed groups produce `Cookbook_PARTIAL.pdf` and a non-zero exit -
    `Cookbook.pdf` is only ever replaced by a complete book.

## Consequences

Sync reconciliation can no longer corrupt the book; at worst it cannot find
the working folder's contents mid-build, which nothing depends on anymore.
Debugging layout issues uses `--temp-dir` (plus the tools collected under
`02_pdf_creation/debug/`: `debug_split_one.py` / `debug_watch_temp.py`)
rather than peeking into `exports/_temp`, which is no longer written. Builds
leave no churn in the vault for the sync engine to react to, which also
removes the trigger for the reconciliation waves.

## Amendment (same day): concurrent builds

The first validation run under this policy still lost 98 sheets - because two
builds overlapped (a leftover background run plus a manual rerun) and both
shared `%TEMP%/cookbook_build`, which each build *wipes at startup*. The
pre-conversion guard caught it loudly, proving its worth, but the race needed
closing:

- working folders are now **per process** (`cookbook_build_<pid>`), swept of
  siblings older than 24 h;
- an **exclusive build lock** (`exports/.build.lock`) rejects a second build
  while one runs; locks older than 2 h are treated as crash leftovers.

