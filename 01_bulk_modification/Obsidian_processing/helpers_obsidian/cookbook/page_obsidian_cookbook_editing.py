import os
from pathlib import Path

import streamlit as st

from .cookbook_adapt_bulk import export_metadata_to_excel, update_metadata_from_excel, export_subheader_overview, rename_markdown_subheader


def obsidian_cookbook(cookbook_path: Path, text_dir_path: Path, text_notdone_dir_path: Path):
    st.warning("⚠️ You're adapting actual markdown files. Please take care.")

    file_map = {
        "sideinfo": "recipes_overview_subheaders_sideinfo.xlsx",
        "statusinfo": "recipes_overview_subheaders_statusinfo.xlsx",
        "description": "recipes_overview_subheaders_description.xlsx",
        "title": "recipes_overview_subheaders_title.xlsx",
        "sources": "recipes_overview_subheaders_sources.xlsx",
        "subheaders": "recipes_overview_subheaders.xlsx",
        "dietaryrestrictions": "recipes_overview_subheaders_dietaryrestrictions.xlsx",
        "structure_generated": "_-1.0. cookbook_structure_generated.md",
    }

    paths = {k: cookbook_path / v for k, v in file_map.items() if k != "structure_generated"}
    pages_index_path = text_dir_path / file_map["structure_generated"]

    text_dir_pairs = [
        ("text", text_dir_path),
        ("text_notdone", text_notdone_dir_path),
    ]

    subheader_sections = [
        {"label": "Side info", "path": paths["sideinfo"], "id": "side"},
        {"label": "Status info", "path": paths["statusinfo"], "id": "status"},
        {"label": "Description", "path": paths["description"], "id": "description"},
        {"label": "Title", "path": paths["title"], "id": "title"},
        {"label": "Sources", "path": paths["sources"], "id": "sources"},
        {"label": "Dietary Restrictions", "path": paths["dietaryrestrictions"], "id": "dietaryrestrictions"},
    ]

    st.subheader("Cookbook path")
    if st.button(f"📁 cookbook_path: {cookbook_path}", key="open_cookbook_path"):
        with st.spinner(f"opening: {cookbook_path} ..."):
            os.startfile(cookbook_path)
            st.success(f"✅ {cookbook_path.name} opened")

    st.subheader("Rename subheaders")
    col1, col2, col3 = st.columns([1, 1, 1])
    i_naming = [col1.text_input("Old subheader title"), col2.text_input("New subheader title")]
    if col3.button("Rename subheaders"):
        try:
            for source_label, dir_path in text_dir_pairs:
                rename_markdown_subheader(
                    cookbook_path=cookbook_path,
                    text_dir_path=dir_path,
                    pages_index_path=pages_index_path,
                    old_title=i_naming[0],
                    new_title=i_naming[1],
                )
            st.success("✅ Subheaders renamed successfully!")
        except Exception as e:
            st.error(f"Failed to rename subheaders: {e}")

    st.subheader("Subheader overview")
    col1, col2, col3 = st.columns([1, 1, 1])
    subheaders_path = paths["subheaders"]

    if col1.button("Export subheader overview"):
        try:
            export_subheader_overview(
                cookbook_path=cookbook_path,
                text_dir_paths=text_dir_pairs,
                pages_index_path=pages_index_path,
                output_excel_path=subheaders_path,
            )
            st.success("✅ Subheader overview exported successfully!")
        except Exception as e:
            st.error(f"Failed to export subheader overview: {e}")
        st.rerun()

    if os.path.exists(subheaders_path):
        with col2:
            if st.button(f"📄 subheader overview", key="open_subheaders"):
                with st.spinner(f"opening: {subheaders_path} ..."):
                    os.startfile(subheaders_path)
                    st.success(f"✅ {subheaders_path.name} opened")
        if col3.button("❌ Delete subheader overview file"):
            try:
                os.remove(subheaders_path)
                st.success("🗑️ Subheader overview file deleted.")
            except Exception as e:
                st.error(f"Failed to delete file: {e}")
            st.rerun()

    st.subheader("Complete subheaders in bulk")
    st.warning("these sections depend on the info present in the generated book structure (page index). please reload if unsure if it's the latest version.")
    for section in subheader_sections:
        label = section["label"]
        excel_path = section["path"]
        sec_id = section["id"]

        st.markdown(f"##### {label}")
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button(f"🧮 Create Excel - from markdown files '{label}'", key=f"export_{sec_id}"):
                try:
                    with st.spinner(f"Creating/updating Excel for {label}..."):
                        export_metadata_to_excel(cookbook_path, text_dir_pairs, pages_index_path, excel_path, label)
                    st.success(f"✅ {label} Overview Excel created/updated successfully!")
                except Exception as e:
                    st.error(f"Failed to create Excel for {label}: {e}")
                st.rerun()
        if os.path.exists(excel_path):
            with col2:
                if st.button(f"📄 {label}", key=f"open_{sec_id}"):
                    with st.spinner(f"opening: {excel_path} ..."):
                        os.startfile(excel_path)
                        st.success(f"✅ {excel_path.name} opened")
            if col3.button(f"✍️ Updating Markdown files - from '{label} Overview Excel'", key=f"update_{sec_id}"):
                if not excel_path.exists():
                    st.error(f"File not found: {excel_path.name}. Please create it first.")
                else:
                    try:
                        with st.spinner(f"Updating Markdown files from {label}..."):
                            update_metadata_from_excel(cookbook_path, text_dir_pairs, excel_path, label)
                        st.success(f"✅ Markdown files updated from {label} Excel successfully!")
                    except Exception as e:
                        st.error(f"Failed to update markdown from {label} Excel: {e}")
                    st.rerun()
