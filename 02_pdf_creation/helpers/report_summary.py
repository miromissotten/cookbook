"""Generation-report aggregation for the cookbook build.

Verbatim extraction of the counting logic previously inline in
``CookbookGenerator.write_generation_report``: same inputs, same
report lines and counts. Kept in this module (next to
``render_report_markdown``) so the entry point orchestrates only.
"""
from typing import Dict, List, Tuple


def summarize_diagnostics(parse_diagnostics: Dict,
                          split_diagnostics: List[Tuple[str, str]],
                          link_stats: Dict) -> Tuple[List[str], Dict]:
    """Aggregate raw diagnostics into report lines plus summary counts."""
    severity_order = {'warn': 0, 'todo': 1, 'info': 2}
    entries = []
    warn_count = 0
    todo_count = 0
    for filename, file_diagnostics in parse_diagnostics.items():
        for level, message in file_diagnostics:
            entries.append((severity_order.get(level, 3), level, filename, message))
            if level == 'warn':
                warn_count += 1
            elif level == 'todo':
                todo_count += 1
    entries.sort(key=lambda entry: (entry[0], entry[2]))

    split_diags = list(split_diagnostics or [])
    split_count = sum(1 for level, _msg in split_diags if level == 'split')
    giant_count = sum(1 for level, _msg in split_diags if level in ('giant', 'scaled'))
    sliced_count = sum(1 for level, _msg in split_diags if level == 'sliced')
    join_scaled_count = sum(
        1 for level, _msg in split_diags if level == 'join-scaled')
    side_by_side_count = sum(
        1 for level, _msg in split_diags if level == 'side-by-side')
    vertical_count = sum(
        1 for level, _msg in split_diags if level == 'vertical')

    total_files = len(parse_diagnostics)
    files_with_issues = {
        filename
        for filename, file_diagnostics in parse_diagnostics.items()
        if file_diagnostics
    }
    clean_count = total_files - len(files_with_issues)

    report_lines = [f"Generation report - {total_files} recipe files scanned"]
    for _severity, level, filename, message in entries:
        report_lines.append(f"[{level}] {filename} - {message}")
    report_lines.append(
        f"Summary: {total_files} recipe files | {warn_count} warnings | "
        f"{todo_count} todos | {clean_count} clean"
    )
    for level, message in split_diags:
        report_lines.append(f"[{level}] {message}")
    report_lines.append(
        f"Layout: {split_count} source page(s) split into continuation sheets | "
        f"{giant_count} giant/scaled block(s) | "
        f"{sliced_count} diagram(s) sliced at full size | "
        f"{join_scaled_count} join-scaled diagram(s) (ADR 0017) | "
        f"{side_by_side_count} side-by-side election(s) | "
        f"{vertical_count} vertical election(s) (ADR 0009)"
    )
    if link_stats:
        for variant, stats in link_stats.items():
            report_lines.append(
                f"Links [{variant}]: {stats['links_injected']} injected "
                f"(of {stats['links_measured']} measured) | "
                f"{stats['toc_rows_stamped']} TOC rows stamped | "
                f"{stats.get('accent_underlines', 0)} accent underline(s) | "
                f"{stats.get('back_to_toc_links', 0)} back-to-TOC link(s)"
            )

    counts = {
        'warn_count': warn_count,
        'todo_count': todo_count,
        'clean_count': clean_count,
        'total_files': total_files,
        'split_count': split_count,
        'giant_count': giant_count,
        'sliced_count': sliced_count,
        'join_scaled_count': join_scaled_count,
        'side_by_side_count': side_by_side_count,
        'vertical_count': vertical_count,
    }
    return report_lines, counts
