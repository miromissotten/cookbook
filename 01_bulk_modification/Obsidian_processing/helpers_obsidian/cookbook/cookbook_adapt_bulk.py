import os
import re
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill

from .logger import get_logger


def get_referenced_files(pages_index_path):
    referenced_files = set()
    try:
        with open(pages_index_path, 'r', encoding='utf-8') as f:
            content = f.read()
            matches = re.findall(r'\[\[([^\]]+)\]\]', content)
            referenced_files = {f"{os.path.basename(match)}.md" for match in matches}
    except FileNotFoundError:
        get_logger().error(f"Error: Content table not found at {pages_index_path}")
    return referenced_files


def iter_md_files(dir_path, referenced_files):
    for filename in os.listdir(dir_path):
        if filename.endswith(".md") and filename in referenced_files:
            yield filename, os.path.join(dir_path, filename)


def _split_at_header(content, header_string):
    before, rest = content.split(header_string, 1)
    if "###" in rest:
        _, after = rest.split("###", 1)
        after = "###" + after
    else:
        after = ""
    return before.strip(), after.strip()


def remove_empty_subheaders_from_md(md_file_path):
    content = md_file_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    header_indices = [i for i, line in enumerate(lines) if line.startswith('### ')]
    if not header_indices:
        return False

    to_pop = set()
    for idx, header_index in enumerate(header_indices):
        next_header_index = header_indices[idx + 1] if idx + 1 < len(header_indices) else len(lines)
        body = [line for line in lines[header_index + 1:next_header_index] if line.strip()]
        if not body:
            to_pop.add(header_index)

    if to_pop:
        for index in sorted(to_pop, reverse=True):
            lines.pop(index)
        new_content = '\n'.join(lines).strip() + '\n'
        if new_content != content:
            md_file_path.write_text(new_content, encoding='utf-8')
            return True
    return False


def export_subheader_overview(cookbook_path, text_dir_paths, pages_index_path, output_excel_path):
    """
    Creates an Excel overview showing which ### subheaders exist in which files.
    """
    logger = get_logger()
    logger.info(f"--- Generating Subheader Overview ---")

    referenced_files = get_referenced_files(pages_index_path)
    if not referenced_files:
        return

    if not os.path.exists(cookbook_path):
        logger.error(f"Error: Directory not found at {cookbook_path}")
        return

    all_rows = []
    for source_label, text_dir_path in text_dir_paths:
        for filename, file_path in iter_md_files(text_dir_path, referenced_files):
            file_data = {'filename': filename, 'source': source_label}
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                found_headers = False
                for line in lines:
                    if line.startswith("### "):
                        header_name = line.replace("###", "").strip()
                        if header_name:
                            file_data[header_name] = "X"
                            found_headers = True
                if found_headers:
                    logger.info(f"  -> Extracted headers for '{filename}' ({source_label})")
                else:
                    logger.info(f"  -> No ### headers found in '{filename}' ({source_label})")
                all_rows.append(file_data)
            except Exception as e:
                logger.error(f"  -> Error reading '{filename}' ({source_label}): {e}")

    if not all_rows:
        logger.warning("No data found to export.")
        return

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=['filename'], keep='first')
    df = df.sort_values(by='filename', ascending=True)

    non_filename_cols = [c for c in df.columns if c not in ('filename', 'source')]
    df = df[['filename', 'source'] + sorted(non_filename_cols)]
    df = df.fillna('')

    df.to_excel(output_excel_path, index=False)
    logger.info(f"\nSuccessfully created overview: {output_excel_path}")


def export_metadata_to_excel(cookbook_path, text_dir_paths, pages_index_path, output_excel_path, section_title):
    logger = get_logger()
    header_to_find = f"### {section_title}"

    logger.info(f"--- Exporting {section_title} ---")

    referenced_files = get_referenced_files(pages_index_path)
    if not referenced_files:
        return

    if not os.path.exists(cookbook_path):
        logger.error(f"Error: Directory not found at {cookbook_path}")
        return

    all_data = []
    for source_label, text_dir_path in text_dir_paths:
        for filename, file_path in iter_md_files(text_dir_path, referenced_files):
            logger.info(f"Processing file: {filename} ({source_label})")

            item_info = {'filename': filename, 'source': source_label}

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if header_to_find in content:
                try:
                    section_text = content.split(header_to_find)[1].split("###")[0]

                    for line in section_text.strip().split('\n'):
                        line = line.strip()
                        delimiter = ':' if ':' in line else '=' if '=' in line else None
                        if delimiter:
                            parts = line.split(delimiter, 1)
                            key = parts[0].replace('-', '').replace('*', '').strip()
                            value = parts[1].strip()
                            item_info[key] = value
                    logger.info(f"  -> Processed metadata for '{filename}' ({source_label})")
                except IndexError:
                    logger.warning(f"  -> Header found but could not parse content in '{filename}' ({source_label})")
            else:
                logger.info(f"  -> Section '{section_title}' not found in '{filename}' ({source_label}) (leaving blank)")

            all_data.append(item_info)

    if not all_data:
        logger.warning(f"No matching files found in {cookbook_path}.")
        return

    df = pd.DataFrame(all_data)

    if 'filename' in df.columns:
        df = df.sort_values(by='filename', ascending=True)
        cols = ['filename', 'source'] + [c for c in df.columns if c not in ('filename', 'source')]
        df = df[cols]

    df.to_excel(output_excel_path, index=False)

    workbook = load_workbook(output_excel_path)
    worksheet = workbook.active

    dark_blue_fill = PatternFill(start_color="1F1C57", end_color="1F1C57", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")

    worksheet.conditional_formatting.add('A1:XFD1048576',
                                       CellIsRule(operator='equal', formula=['"todo"'], fill=dark_blue_fill))
    worksheet.conditional_formatting.add('A1:XFD1048576',
                                       CellIsRule(operator='equal', formula=['"ongoing"'], fill=yellow_fill))
    worksheet.conditional_formatting.add('A1:XFD1048576',
                                       CellIsRule(operator='equal', formula=['"done"'], fill=green_fill))

    workbook.save(output_excel_path)
    logger.info(f"\nSuccessfully created and formatted: {output_excel_path}")


def update_metadata_from_excel(cookbook_path, text_dir_paths, excel_file_path, section_title):
    """
    Reads an Excel file and updates, adds, or REMOVES a specific Markdown section.
    If all columns (besides filename) are empty, the section is removed.
    """
    logger = get_logger()
    header_string = f"### {section_title}"
    logger.info(f"--- Processing {section_title} from Excel ---")

    dir_map = {label: Path(dir_path) for label, dir_path in text_dir_paths}

    try:
        df = pd.read_excel(excel_file_path).fillna('')
    except Exception as e:
        logger.error(f"Error reading Excel: {e}")
        return

    update_count = 0
    for _, row in df.iterrows():
        filename = row.get('filename')
        if not filename:
            continue

        source = row.get('source', '')
        base_dir = dir_map.get(source)
        if base_dir is None:
            logger.warning(f"Skipping: {filename} (Unknown source '{source}')")
            continue

        md_file_path = base_dir / filename
        if not md_file_path.exists():
            logger.warning(f"Skipping: {filename} (File not found in {source})")
            continue

        try:
            content = md_file_path.read_text(encoding='utf-8')

            metadata_lines = [f"- {k}: {v}" for k, v in row.items()
                              if k not in ('filename', 'source') and str(v).strip() != '']

            if not metadata_lines:
                if header_string in content:
                    logger.info(f"  - Removing empty section '{section_title}' from '{filename}'")
                    before, after = _split_at_header(content, header_string)
                    new_content = f"{before}\n\n{after}" if after else before
                else:
                    continue
            else:
                new_block = f"{header_string}\n" + "\n".join(metadata_lines)

                if header_string in content:
                    before, after = _split_at_header(content, header_string)
                    new_content = f"{before}\n\n{new_block}\n\n{after}" if after else f"{before}\n\n{new_block}"
                else:
                    logger.info(f"  + Section '{section_title}' missing in '{filename}'. Adding to end.")
                    new_content = f"{content.strip()}\n\n{new_block}"

            while "\n\n\n" in new_content:
                new_content = new_content.replace("\n\n\n", "\n\n")

            md_file_path.write_text(new_content.strip() + "\n", encoding='utf-8')
            remove_empty_subheaders_from_md(md_file_path)
            update_count += 1

        except Exception as e:
            logger.error(f"Error processing '{filename}': {e}")

    logger.info(f"Finished. Updated/Modified {update_count} files.")

    try:
        os.remove(excel_file_path)
        logger.info(f"Removed temporary file: {excel_file_path}")
    except OSError:
        pass
