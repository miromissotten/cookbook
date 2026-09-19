import streamlit as st
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import PATH_OBSIDIAN_PROJECTS_COOKBOOK, PATH_OBSIDIAN_PROJECTS_COOKBOOK_TEXT_DIR, PATH_OBSIDIAN_PROJECTS_COOKBOOK_TEXT_NOTDONE_DIR
from Obsidian_processing.helpers_obsidian.cookbook.page_obsidian_cookbook_editing import obsidian_cookbook

st.set_page_config(layout="wide", page_title="Obsidian - Cookbook", page_icon="📖")

with st.spinner("Loading cookbook editor..."):
    obsidian_cookbook(PATH_OBSIDIAN_PROJECTS_COOKBOOK, PATH_OBSIDIAN_PROJECTS_COOKBOOK_TEXT_DIR, PATH_OBSIDIAN_PROJECTS_COOKBOOK_TEXT_NOTDONE_DIR)
