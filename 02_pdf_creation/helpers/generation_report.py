"""Generation-report rendering for the cookbook build.

Verbatim extraction of ``CookbookGenerator._render_report_markdown``:
same inputs, same Markdown bytes. Kept separate so the 1500-line
entry point stays focused on orchestration.
"""
from typing import Dict, List, Optional, Set, Tuple


# Layout-diagnostic tags live in their own report section and must not
# repeat inside the parse-diagnostics table.
_LAYOUT_TAGS = (
    "split", "sliced", "giant", "scaled", "join-scaled",
    "side-by-side", "vertical", "backfill",
)


def render_report_markdown(report_lines, counts, split_diags,
                            unresolved_wiki_links: Optional[Dict[str, Set[str]]] = None) -> str:
    """Render the generation diagnostics as GitHub-Flavoured Markdown.

    ``counts`` is the dict produced by :func:`report_summary.summarize_diagnostics`
    (warn_count/todo_count/clean_count/total_files/split_count/giant_count/
    sliced_count/join_scaled_count/side_by_side_count/vertical_count). The parse
    diagnostics are still carried as the flat ``report_lines`` text emitted by
    that same summarizer, so the Markdown table is regenerated from the same
    strings it always was (and the fixture is byte-identical).
    """
    warn_count = counts["warn_count"]
    todo_count = counts["todo_count"]
    clean_count = counts["clean_count"]
    total_files = counts["total_files"]
    split_count = counts["split_count"]
    giant_count = counts["giant_count"]
    sliced_count = counts["sliced_count"]
    join_scaled_count = counts["join_scaled_count"]
    side_by_side_count = counts["side_by_side_count"]
    vertical_count = counts["vertical_count"]
    md = []
    md.append("# Generation Report")
    md.append("")
    md.append(f"**{total_files} recipe files scanned**  ")
    md.append(f"{warn_count} warnings | {todo_count} todos | {clean_count} clean")
    md.append("")
    md.append("## Parse Diagnostics")
    md.append("")
    md.append("| Level | File | Message |")
    md.append("|-------|------|---------|")
    for line in report_lines[1:]:
        if line.startswith("Summary:") or line.startswith("Layout:"):
            continue
        if line.startswith("["):
            bracket_end = line.index("]")
            tag = line[1:bracket_end]
            if tag in _LAYOUT_TAGS:
                continue
            remainder = line[bracket_end+1:].strip()
            if " - " in remainder:
                sub_parts = remainder.split(" - ", 1)
                fname = sub_parts[0]
                msg = sub_parts[1] if len(sub_parts) > 1 else ""
            else:
                fname = ""
                msg = remainder
            fname = fname.replace("|", "\\|")
            msg = msg.replace("|", "\\|")
            md.append(f"| {tag} | {fname} | {msg} |")
        else:
            esc_line = line.replace("|", "\\|")
            md.append(f"| | | {esc_line} |")
    md.append("")
    md.append("## Layout Analysis (ADR 0002)")
    md.append("")
    for level, message in split_diags:
        md.append(f"- **{level}**: {message}")
    md.append("")
    md.append("### Summary")
    md.append("")
    md.append(f"- {split_count} source page(s) split into continuation sheets")
    md.append(f"- {giant_count} giant/scaled block(s)")
    md.append(f"- {sliced_count} diagram(s) sliced at full size")
    md.append(f"- {join_scaled_count} diagram(s) scaled to join their text (ADR 0017)")
    md.append(f"- {side_by_side_count} side-by-side layout election(s)")
    md.append(f"- {vertical_count} vertical layout election(s)")
    md.append("")
    if unresolved_wiki_links:
        md.append("## Unresolved Wiki Links")
        md.append("")
        for reference, source_filenames in unresolved_wiki_links.items():
            sources = ", ".join(sorted(source_filenames))
            md.append(f"- `[[{reference}]]` found in: {sources}")
        md.append("")
    return "\n".join(md)
