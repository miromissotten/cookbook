"""
Structure parser for dynamically parsing cookbook structure files.
Extracts file references and resolves them to actual filenames in the directory.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from input_roots import iter_markdown_files, resolve_roots

# A single directory, or an ordered sequence of directories.
PathSpec = Union[str, Path, Sequence[Union[str, Path]]]


class StructureParser:
    """Parse structure files and resolve filenames dynamically.

    Filenames resolve against an ordered list of input roots: by default
    ``data_modularflavour/text`` then ``data_modularflavour/text_notdone``
    (ADR 0023). The first root is the primary one — it hosts the structure
    file and wins filename collisions.
    """

    def __init__(self, input_dir: Optional[PathSpec] = None):
        self.roots = resolve_roots(input_dir)
        # Primary root: hosts the structure file; kept as ``input_dir`` so
        # existing callers and tests keep working.
        self.input_dir = self.roots[0]

    
    def parse_structure_file(self, structure_filename: str) -> List[str]:
        """
        Parse the structure file and return ordered list of filenames.
        
        Args:
            structure_filename: Name of the structure file (e.g., '_-1.0. cookbook_structure_generated.md')
            
        Returns:
            List of filenames to process, in order
        """
        structure_path = self.input_dir / structure_filename
        
        with open(structure_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract all [[wiki-style links]]
        pattern = r'\[\[([^\]]+)\]\]'
        matches = re.findall(pattern, content)
        
        files_to_process = []
        for match in matches:
            # Handle section references like [[filename#section]]
            if '#' in match:
                filename = match.split('#')[0].strip()
            else:
                filename = match.strip()
            
            # Resolve to actual filename
            resolved = self._resolve_filename(filename)
            if resolved and resolved not in files_to_process:
                files_to_process.append(resolved)
        
        return files_to_process
    
    def _resolve_filename(self, name: str) -> Optional[str]:
        """
        Dynamically resolve a filename from structure file to actual file.
        
        Tries multiple strategies:
        1. Exact match with .md extension
        2. Files starting with the name prefix
        3. Fuzzy matching
        
        Args:
            name: Name from structure file (e.g., '_4.3.1. Chimichurri')
            
        Returns:
            Resolved filename with .md extension, or None if not found
        """
        # Each strategy walks the ordered roots; within one strategy the
        # first root that matches wins (text beats text_notdone).
        # Strategy 1: Exact match
        exact = f"{name}.md"
        for root in self.roots:
            if (root / exact).exists():
                return exact

        # Strategy 2: Match by prefix (for numbered files like _4.3.1.)
        # Find files that start with the name pattern
        prefix = name.split('.')[0] if '.' in name else name

        # For structure references like _4.3.1. Chimichurri,
        # try to find matching files
        for root in self.roots:
            candidates = list(root.glob(f"{prefix}*.md"))
            for candidate in candidates:
                # Check if the name is a prefix of the candidate (ignoring extensions)
                stem = candidate.stem
                if stem.startswith(name) or name.startswith(stem):
                    return candidate.name

        # Strategy 3: Look for files with similar structure
        # Extract the numeric/underscore prefix
        if '.' in name:
            parts = name.split('.')
            if len(parts) >= 2:
                # Try to find files with same numeric prefix
                prefix_match = parts[0]
                for root in self.roots:
                    for candidate in root.glob(f"{prefix_match}*.md"):
                        if name.lower() in candidate.stem.lower():
                            return candidate.name

        # Strategy 4: Case-insensitive search
        name_lower = name.lower()
        for root in self.roots:
            for md_file in root.glob("*.md"):
                if md_file.stem.lower().replace('_', '').replace('-', '') == name_lower.replace('_', '').replace('-', ''):
                    return md_file.name

        return None

    def resolve_page_file(self, name: str) -> Optional[str]:
        """Public wrapper around ``_resolve_filename`` for callers that map
        structure entries (e.g. chapter headers) back to real files."""
        return self._resolve_filename(name)
    
    def get_structure_hierarchy(self, structure_filename: str) -> List[Dict]:
        """
        Parse structure file and return hierarchical data for TOC.
        
        Args:
            structure_filename: Name of the structure file
            
        Returns:
            List of sections with their children
        """
        structure_path = self.input_dir / structure_filename
        
        with open(structure_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        hierarchy = []
        current_section = None
        
        for line in lines:
            line = line.rstrip()
            if not line:
                continue
            
            # Main section: ## [[name]]
            if re.match(r'^##\s*\[\[', line):
                match = re.search(r'\[\[(.+?)\]\]', line)
                if match:
                    section_name = match.group(1)
                    current_section = {
                        'type': 'section',
                        'name': section_name,
                        'children': []
                    }
                    hierarchy.append(current_section)
            
            # Subsection: ### [[name]]
            elif re.match(r'^###\s*\[\[', line):
                match = re.search(r'\[\[(.+?)\]\]', line)
                if match and current_section:
                    subsection_name = match.group(1)
                    subsection = {
                        'type': 'subsection',
                        'name': subsection_name,
                        'children': []
                    }
                    current_section['children'].append(subsection)
            
            # Item: #### [[name]], ##### [[name]], ###### [[name]], or - [[name]]
            elif re.match(r'^(?:#{4,6}|-)\s*\[\[', line):
                match = re.search(r'\[\[(.+?)\]\]', line)
                if match:
                    item_name = match.group(1)
                    # Remove section reference if present
                    if '#' in item_name:
                        item_name = item_name.split('#')[0].strip()
                    
                    # Determine heading level from the line
                    heading_match = re.match(r'^(#+)\s*\[\[', line)
                    heading_level = len(heading_match.group(1)) if heading_match else 4
                    
                    item = {
                        'type': 'item',
                        'name': item_name,
                        'heading_level': heading_level
                    }
                    
                    # Add to current section or subsection
                    if current_section:
                        # Items belong to the most recent subsection; only
                        # items listed before any ### stay section-level.
                        if (current_section['children'] and
                                current_section['children'][-1]['type'] == 'subsection'):
                            target_list = current_section['children'][-1]['children']
                            # Check if we should nest under the last item
                            if (target_list and
                                    target_list[-1]['type'] == 'item' and
                                    heading_level > target_list[-1].get('heading_level', 4)):
                                # Nest under the last item
                                target_list[-1].setdefault('children', []).append(item)
                            else:
                                target_list.append(item)
                        else:
                            # No subsection open yet: add directly to section
                            current_section['children'].append(item)
        
        return hierarchy
    
    def get_file_to_chapter_subsection_mapping(self, structure_filename: str) -> Dict[str, Tuple[str, str]]:
        """Return filename -> (chapter, section) where section may be empty.

        Chapter comes from `## [[name]]` headers. Section comes from either
        `### [[name]]` headers or — when the current item is indented under
        another list item — the closest less-indented list item above it.
        """
        structure_path = self.input_dir / structure_filename

        with open(structure_path, 'r', encoding='utf-8') as f:
            content = f.read()

        def clean_section_name(name: str) -> str:
            return re.sub(r'^_?[\d][\w.]*\s*', '', name).strip()

        def indent_width(raw_line: str) -> int:
            # Treat a tab as one level; count leading spaces in groups of 2 or 4.
            width = 0
            for ch in raw_line:
                if ch == '\t':
                    width += 4
                elif ch == ' ':
                    width += 1
                else:
                    break
            return width

        mapping: Dict[str, Tuple[str, str]] = {}
        current_chapter = ''
        current_subsection_header = ''  # from ### [[name]]
        # Stack of (indent, display_name) for the most recent list items at each depth
        item_stack: List[Tuple[int, str]] = []

        for raw_line in content.split('\n'):
            line = raw_line.rstrip()
            if not line:
                continue

            main_match = re.match(r'^##\s*\[\[([^\]]+)\]\]', line)
            if main_match:
                current_chapter = clean_section_name(main_match.group(1))
                current_subsection_header = ''
                item_stack = []
                continue

            sub_match = re.match(r'^###\s*\[\[([^\]]+)\]\]', line)
            if sub_match:
                current_subsection_header = clean_section_name(sub_match.group(1))
                item_stack = []
                continue

            item_match = re.match(r'^\s*(?:#{4,6}|-)\s*\[\[([^\]]+)\]\]', line)
            if item_match:
                indent = indent_width(raw_line)
                name = item_match.group(1).split('#')[0].strip()
                display_name = clean_section_name(name)

                # Pop stack entries that are >= this indent — they are no longer ancestors
                while item_stack and item_stack[-1][0] >= indent:
                    item_stack.pop()

                # Section for this item = nearest ancestor list item, else the ### header
                if item_stack:
                    section = item_stack[-1][1]
                else:
                    section = current_subsection_header

                resolved = self._resolve_filename(name)
                if resolved:
                    mapping[resolved] = (current_chapter, section)

                # Push this item so its indented children can pick it up as their section
                item_stack.append((indent, display_name))

        return mapping

    def get_all_markdown_files(self) -> List[str]:
        """
        Get all markdown files across the input roots (first root wins on
        duplicate filenames).

        Returns:
            List of all .md filenames
        """
        return iter_markdown_files(self.roots)
    
def main():
    """Test the structure parser."""
    parser = StructureParser("data_modularflavour/text")
    
    print("Testing StructureParser...")
    print(f"\nAll markdown files in directory:")
    files = parser.get_all_markdown_files()
    for f in sorted(files)[:10]:
        print(f"  - {f}")
    print(f"  ... ({len(files)} total)")
    
    print(f"\nParsing structure file:")
    try:
        files = parser.parse_structure_file("_-1.0. cookbook_structure_generated.md")
        print(f"  Found {len(files)} files to process")
        for f in files[:5]:
            print(f"    - {f}")
        print(f"    ...")
    except Exception as e:
        print(f"  Error: {e}")
    
    print(f"\nGetting hierarchy:")
    try:
        hierarchy = parser.get_structure_hierarchy("_-1.0. cookbook_structure_generated.md")
        print(f"  Found {len(hierarchy)} sections")
        for section in hierarchy[:3]:
            print(f"    - {section['name']} ({len(section['children'])} children)")
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    main()
