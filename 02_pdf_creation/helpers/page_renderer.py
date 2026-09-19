"""
Page renderer for converting recipe markdown files to HTML using the A4 template.
"""

import html
import markdown
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import ICON_MAPPING, VARIANT_LABEL_MAX_WORDS


class RecipeParser:
    """Parse recipe markdown files into structured data.

    Tolerant, order-independent parsing: every known field is matched
    individually by its own label, so a missing or oddly formatted line only
    omits that single element instead of dropping the whole block.
    """

    # Every label recognised inside a "### Side info" block.
    SIDE_INFO_LABELS = (
        'group', 'subgroup', 'freezeable', 'origin', 'love level',
        'carbsource', 'recipe for how many people',
        'time formula active + waiting', 'for how many p possible reasonably',
        'work after premade', 'Food for dating', 'difficulty',
        'sauce_flavour', 'sauce_consistency', 'sauce_usage',
    )
    # Side info labels whose absence is reported as a warning.
    CORE_SIDE_INFO_LABELS = (
        'group', 'subgroup', 'freezeable', 'origin', 'love level',
        'carbsource', 'recipe for how many people',
        'time formula active + waiting', 'for how many p possible reasonably',
        'work after premade', 'Food for dating', 'difficulty',
    )
    # Dietary restriction lines; tri-state yes/possible/no per line.
    DIETARY_FIELDS = ('Lactosefree', 'Vegetarian', 'Vegan', 'Glutenfree')
    # Canonical shape of the time formula (bare durations only); anything
    # else still renders, verbatim, and is reported as info.
    TIME_FORMULA_STANDARD_RE = re.compile(
        r'^\d{2}h\d{2}(?:\s*\+\s*\d{2}h\d{2})?$'
    )
    # A numbered instruction step ("1." / "1)") inside "### Instructions";
    # treated exactly like a "- " bullet (ADR 0012).
    NUMBERED_STEP_RE = re.compile(r'^(\d+)[.)][ \t]*(\S.*)$')
    # A short non-sentence line is an Instruction variant label
    # ("lazy version:", "Hiroshima Style"); longer or sentence-shaped
    # lines are prose lead-ins. Threshold lives in config so the parser
    # and any future callers share one source of truth.
    VARIANT_LABEL_MAX_WORDS = VARIANT_LABEL_MAX_WORDS
    
    def __init__(self):
        pass
    
    def parse_recipe(self, content: str) -> Dict:
        """Parse recipe content into structured data (diagnostics discarded)."""
        recipe, _diagnostics = self.parse_recipe_with_diagnostics(content)
        return recipe

    def parse_recipe_with_diagnostics(self, content: str) -> Tuple[Dict, List[Tuple[str, str]]]:
        """Parse recipe content into structured data plus parse diagnostics.

        Parsing is tolerant and order-independent: every known field is matched
        individually by its own label, so one missing or oddly formatted line
        only omits that single element instead of silently dropping the whole
        block. Diagnostics are (level, message) tuples with level one of
        'warn' (missing core data), 'todo' (missing description) or 'info'
        (non-standard shapes, ignored extras).
        """
        recipe: Dict = {}
        diagnostics: List[Tuple[str, str]] = []

        # Parse title
        title_match = re.search(r'^### Title\s*\n- title:\s*(.+)\s*$', content, re.MULTILINE)
        if title_match:
            recipe['title'] = title_match.group(1).strip()

        self._parse_side_info(content, recipe, diagnostics)
        self._parse_dietary_restrictions(content, recipe, diagnostics)
        self._parse_description(content, recipe, diagnostics)

        # Parse ingredients - handle nested structure based on indentation
        ingredients_section = re.search(r'^### Ingredients\s*\n(.*?)(?=^### |\Z)', content, re.MULTILINE | re.DOTALL)
        if ingredients_section:
            ingredients_text = ingredients_section.group(1)
            recipe['ingredients'] = self._parse_list_with_indentation(ingredients_text)
        
        # Parse hardware
        hardware_section = re.search(r'^### Hardware\s*\n(.*?)(?=^### |\Z)', content, re.MULTILINE | re.DOTALL)
        if hardware_section:
            hardware_text = hardware_section.group(1)
            recipe['hardware'] = self._parse_list_with_indentation(hardware_text)
        
        # Parse instructions
        instructions_section = re.search(r'^### Instructions\s*\n(.*?)(?=^### |\Z)', content, re.MULTILINE | re.DOTALL)
        if instructions_section:
            instructions_text = instructions_section.group(1)
            recipe['instructions'] = self._parse_instructions_with_indentation(
                instructions_text, diagnostics)
        
        # Parse sauces (if present)
        sauces_section = re.search(r'^### Sauces\s*\n(.*?)(?=^### |\Z)', content, re.MULTILINE | re.DOTALL)
        if sauces_section:
            sauces_text = sauces_section.group(1)
            recipe['sauces'] = self._parse_list_with_indentation(sauces_text)
        
        return recipe, diagnostics

    def _section_body(self, content: str, heading: str):
        """Return the raw text under a "### heading" until the next heading."""
        match = re.search(
            rf'^{re.escape(heading)}\s*\n(.*?)(?=^### |\Z)',
            content, re.MULTILINE | re.DOTALL
        )
        return match.group(1) if match else None

    def _labelled_value(self, block: str, label: str):
        """Return the value of "- label: value" inside block, or None."""
        match = re.search(rf'^-\s*{re.escape(label)}\s*:\s*(.*)$', block, re.MULTILINE)
        return match.group(1).strip() if match else None

    def _value_with_continuation(self, block: str, label: str) -> Optional[str]:
        """Value of "- label: value" plus plain lines continuing underneath.

        A blank line, another "- field:" bullet or a heading ends the value;
        the collected lines join with single spaces.
        """
        match = re.search(rf'^-\s*{re.escape(label)}\s*:\s*(.*)$', block, re.MULTILINE)
        if not match:
            return None

        parts = [match.group(1).strip()]
        # "match.end()" sits on the value line's newline, so its first split
        # element is the empty string; skipping it is what allows a
        # continuation line to be read at all. (Without this the loop broke on
        # that empty element and only ever kept the value's first line.)
        for line in block[match.end():].split('\n')[1:]:
            stripped = line.strip()
            if not stripped or stripped.startswith('- ') or stripped.startswith('#'):
                break
            parts.append(stripped)
        return ' '.join(part for part in parts if part)

    def parse_content_page(self, content: str) -> Dict:
        """Parse a sideinfo-style content page's structured sections.

        Content pages keep their printed body in a "### Text" section, with an
        optional "### Description" above it and their heading in "### Title";
        "### Side info" / "### Status info" are authoring metadata that never
        reach the page. The presence of "### Text" is the signal that a file is
        such a page - one without it keeps rendering its whole content, so a
        file that has not been converted yet cannot silently lose its prose.

        Returns:
            title: authored "- title:" value, else None
            description: authored "- description:" value, else None
            text: raw markdown body of "### Text", else None
            has_text_section: True when "### Text" is present
        """
        text_body = self._section_body(content, '### Text')
        if text_body is None:
            return {
                'title': None,
                'description': None,
                'text': None,
                'has_text_section': False,
            }

        title_block = self._section_body(content, '### Title') or ''
        description_block = self._section_body(content, '### Description') or ''
        return {
            'title': self._labelled_value(title_block, 'title'),
            'description': self._value_with_continuation(
                description_block, 'description'),
            'text': text_body,
            'has_text_section': True,
        }

    def _parse_side_info(self, content: str, recipe: Dict, diagnostics: List[Tuple[str, str]]) -> None:
        """Parse Side info field-by-field; report gaps instead of failing."""
        block = self._section_body(content, '### Side info')
        if block is None:
            diagnostics.append(('warn', 'no ### Side info section'))
            return

        values = {}
        for label in self.SIDE_INFO_LABELS:
            values[label] = self._labelled_value(block, label)

        # Labels present in the file but unknown to us (typos, future fields).
        present_labels = {
            m.group(1).strip()
            for m in re.finditer(r'^-\s*([^:\n]+):', block, re.MULTILINE)
        }
        unknown = sorted(present_labels - set(self.SIDE_INFO_LABELS))
        if unknown:
            diagnostics.append(('info', 'unknown side-info field(s) ignored: ' + ', '.join(unknown)))

        missing_core = [label for label in self.CORE_SIDE_INFO_LABELS if not values[label]]
        if missing_core:
            diagnostics.append(('warn', 'missing side-info fields: ' + ', '.join(missing_core)))

        # Plain string fields: present -> kept, absent -> simply omitted.
        simple_fields = [
            ('group', 'group'),
            ('subgroup', 'subgroup'),
            ('freezeable', 'freezeable'),
            ('carbsource', 'carbsource'),
            ('difficulty', 'difficulty'),
            ('work_after_premade', 'work after premade'),
            ('servings_range', 'for how many p possible reasonably'),
            ('sauce_flavour', 'sauce_flavour'),
            ('sauce_consistency', 'sauce_consistency'),
            ('sauce_usage', 'sauce_usage'),
        ]
        for key, label in simple_fields:
            if values[label]:
                recipe[key] = values[label]

        # Origin "/" or empty means "no origin": omit entirely.
        origin = values['origin']
        if origin and origin != '/':
            recipe['origin'] = origin

        if values['love level']:
            try:
                recipe['love_level'] = float(values['love level'])
            except ValueError:
                diagnostics.append(('warn', f'non-numeric love level "{values["love level"]}" (ignored)'))

        if values['recipe for how many people']:
            number_match = re.search(r'\d+', values['recipe for how many people'])
            if number_match:
                recipe['servings'] = int(number_match.group(0))
            else:
                diagnostics.append(('warn', f'non-numeric servings "{values["recipe for how many people"]}" (ignored)'))

        # Time formula is stored verbatim; odd shapes stay visible on the page.
        if values['time formula active + waiting']:
            raw_time = values['time formula active + waiting']
            recipe['time_formula'] = raw_time
            if not self.TIME_FORMULA_STANDARD_RE.match(raw_time):
                diagnostics.append(('info', f'non-standard time formula "{raw_time}" (shown verbatim)'))

        if values['Food for dating']:
            dating_value = values['Food for dating'].strip().lower()
            if dating_value == 'true':
                recipe['food_for_dating'] = True
            elif dating_value in ('false', 'no'):
                recipe['food_for_dating'] = False
            else:
                diagnostics.append(('warn', f'unrecognised Food for dating value "{values["Food for dating"]}" (ignored)'))

    def _parse_dietary_restrictions(self, content: str, recipe: Dict, diagnostics: List[Tuple[str, str]]) -> None:
        """Parse Dietary Restrictions line-by-line (tri-state preserved)."""
        block = self._section_body(content, '### Dietary Restrictions')
        if block is None:
            diagnostics.append(('info', 'no ### Dietary Restrictions section'))
            return

        missing_lines = []
        for field in self.DIETARY_FIELDS:
            value = self._labelled_value(block, field)
            if value:
                recipe[field.lower()] = value
            else:
                missing_lines.append(field)
        if missing_lines:
            diagnostics.append(('info', 'Dietary Restrictions lines absent: ' + ', '.join(missing_lines)))

    def _parse_description(self, content: str, recipe: Dict, diagnostics: List[Tuple[str, str]]) -> None:
        """Parse the description; supports continuation lines below it."""
        description = self._value_with_continuation(content, 'description')
        if description is None:
            diagnostics.append(('todo', 'no description -> TODO stub rendered'))
            return
        recipe['description'] = description

    def _parse_list_with_indentation(self, text: str) -> List[Dict]:
        """Parse list with proper indentation handling for nested items."""
        lines = text.split('\n')
        items = []
        
        # Track current item and its base indentation
        current_item = None
        base_indent = None
        
        for line in lines:
            if not line.strip():
                continue
            
            # Get leading whitespace count
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            
            # Skip lines that don't start with - (these are likely continuations)
            if not stripped.startswith('- '):
                # Continuation of previous item
                if current_item:
                    current_item['main'] += ' ' + stripped
                continue
            
            # This is a new item (starts with -)
            item_text = stripped[2:]  # Remove "- " prefix
            
            if base_indent is None:
                # First item - set base indent
                base_indent = indent
                current_item = {'main': item_text, 'sub': [], 'indent': indent}
                items.append(current_item)
            elif indent == base_indent:
                # Same level as first item - new main item
                current_item = {'main': item_text, 'sub': [], 'indent': indent}
                items.append(current_item)
            elif indent > base_indent:
                # Indented more than base - it's a sub-item
                if current_item:
                    current_item['sub'].append(item_text)
            else:
                # Less indented than base - new main item
                current_item = {'main': item_text, 'sub': [], 'indent': indent}
                items.append(current_item)
        
        return items
    
    def _looks_like_variant_label(self, text: str) -> bool:
        """Short non-sentence lines name Instruction variants; colon optional."""
        cleaned = text.strip().rstrip(':').strip()
        if not cleaned or cleaned[-1] in '.!?':
            return False
        return len(cleaned.split()) <= self.VARIANT_LABEL_MAX_WORDS

    def _parse_instructions_with_indentation(
            self, text: str, diagnostics: List[Tuple[str, str]]) -> List[Dict]:
        """Parse instructions into ordered, individually printable blocks.

        Absorb-all contract (ADR 0012): every non-empty source line maps to a
        block that prints. Steps are "- " bullets or "N."/"N)" markers, with
        indentation beneath a step making sub-notes. Remaining lines become
        variant labels (short non-sentences), verbatim sub-headings ("####"
        style) or prose paragraphs. Only a bare "-" placeholder is dropped,
        and that removal is reported as a warning.
        """
        blocks: List[Dict] = []
        base_indent = None
        current_step = None
        current_subs: List[str] = []
        table_buffer: List[str] = []

        def flush_step() -> None:
            nonlocal current_step, current_subs
            if current_step is not None:
                blocks.append({'kind': 'step', 'step': current_step, 'subs': current_subs})
            current_step = None
            current_subs = []

        def flush_table() -> None:
            nonlocal table_buffer
            if table_buffer:
                blocks.append({'kind': 'table', 'lines': table_buffer})
                table_buffer = []

        for line in text.split('\n'):
            if not line.strip():
                flush_table()
                continue

            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            content = stripped.rstrip()

            if content == '-':
                diagnostics.append(('warn', 'empty instruction placeholder removed'))
                continue

            if table_buffer is not None:
                if content.startswith('|'):
                    table_buffer.append(content)
                    continue
                else:
                    flush_table()

            bullet_match = content.startswith('- ')
            number_match = None if bullet_match else self.NUMBERED_STEP_RE.match(content)

            if bullet_match:
                item_text = content[2:].strip()
            elif number_match:
                item_text = number_match.group(2).strip()
            else:
                item_text = None

            if item_text is not None:
                if base_indent is None:
                    base_indent = indent
                    flush_step()
                    current_step = item_text
                elif indent > base_indent and current_step is not None:
                    # Sub-note of the step being built.
                    current_subs.append(item_text)
                else:
                    # Same level or shallower: a new step.
                    flush_step()
                    current_step = item_text
                continue

            # Non-marker line: flush the open step, then classify visibly.
            flush_step()
            if content.startswith('#'):
                level = len(content) - len(content.lstrip('#'))
                blocks.append({'kind': 'heading', 'level': level,
                               'text': content.lstrip('#').strip()})
            elif content.startswith('|'):
                table_buffer.append(content)
            elif self._looks_like_variant_label(content):
                blocks.append({'kind': 'variant', 'label': content.rstrip(':').strip()})
            else:
                blocks.append({'kind': 'prose', 'text': content})

        flush_table()
        flush_step()
        return blocks


class RecipeRenderer:
    """Render recipe data into HTML using the A4 template."""
    
    def __init__(self):
        self.icon_mapping = ICON_MAPPING
        self.difficulty_icons = {
            'easy': ['icon_difficulty_1.png'],
            'medium': ['icon_difficulty_2.png'],
            'hard': ['icon_difficulty_3.png'],
        }
    
    def render_html(self, recipe: Dict, position_label: str = '') -> str:
        """Render recipe data into HTML string.

        Args:
            recipe: Parsed recipe dictionary
            position_label: Numbering label to display before the title (e.g., "1.1.1.")
        """
        # Generate icon HTML
        icons_html = self._generate_icons_html(recipe)
        
        # Generate sauces HTML (only if sauces data exists)
        sauces_html = self._generate_sauces_html(recipe.get('sauces', []))
        
        # Generate hardware HTML
        hardware_html = self._generate_hardware_html(recipe.get('hardware', []))
        
        # The tinted ingredients sidebar is written only when the recipe
        # actually authored an Ingredients section. Without one nothing of it
        # is written (no heading, no placeholder text) and the page always
        # prints in the vertical layout - full-width instructions instead of
        # sitting beside an empty panel. The splitter recognises these pages
        # by the data-vertical-recipe marker on the article.
        has_ingredients = bool(recipe.get('ingredients'))
        if has_ingredients:
            sidebar_block = self._build_ingredients_sidebar(
                recipe, hardware_html, sauces_html)
            instructions_html = self._generate_instructions_html(
                recipe.get('instructions', []), full_width=False)
        else:
            sidebar_block = self._build_fullwidth_extras(
                hardware_html, sauces_html)
            instructions_html = self._generate_instructions_html(
                recipe.get('instructions', []), full_width=True)
        
        # Generate side info HTML
        side_info_html = self._generate_side_info_html(recipe)

        # Origin pin row (empty string -> nothing rendered at all)
        origin_html = self._generate_origin_html(recipe)

        # Description quote block or visible TODO stub
        description_html = self._generate_description_html(recipe)

        # Sauce profile group (only when at least one profile field exists)
        profile_chips_html = self._generate_sauce_profile_group_html(recipe)

        # Generate HTML template
        html_template = self._get_html_template()

        # Replace placeholders - create a clean title for ID
        clean_title = recipe.get('title', 'Untitled Recipe').replace(' ', '-').replace('_', '-').lower()

        # Prepend position label to title for display (e.g., "1.1.1. Ramen")
        display_title = f"{position_label} {recipe.get('title', 'Untitled Recipe')}" if position_label else recipe.get('title', 'Untitled Recipe')

        html_content = html_template.format(
            title=display_title,
            clean_title_id=clean_title,
            origin_block=origin_html,
            description_block=description_html,
            profile_chips=profile_chips_html,
            icons=icons_html,
            sidebar_block=sidebar_block,
            instructions=instructions_html,
            side_info=side_info_html
        )
        
        return html_content
    
    def _generate_icons_html(self, recipe: Dict) -> str:
        """Generate HTML for dietary and status icons."""
        icons = []
        
        # Group icon (component vs dish)
        group = recipe.get('group', '').lower()
        if group == 'component':
            icons.append(self._icon_html('component', 'Component recipe', large=True))
        elif group == 'dish':
            icons.append(self._icon_html('dish', 'Complete dish', large=True))
        
        # Dietary icons
        if recipe.get('vegan', 'no').lower() == 'yes':
            icons.append(self._icon_html('vegan', 'Vegan', large=True))
        elif recipe.get('vegan', 'no').lower() == 'possible':
            icons.append(self._icon_html('vegan', 'Vegan (possible)', is_possible=True, large=True))
        
        if recipe.get('vegetarian', 'no').lower() == 'yes':
            icons.append(self._icon_html('vegetarian', 'Vegetarian', large=True))
        elif recipe.get('vegetarian', 'no').lower() == 'possible':
            icons.append(self._icon_html('vegetarian', 'Vegetarian (possible)', is_possible=True, large=True))
        
        if recipe.get('lactosefree', 'no').lower() == 'yes':
            icons.append(self._icon_html('lactosefree', 'Lactose-free', large=True))
        elif recipe.get('lactosefree', 'no').lower() == 'possible':
            icons.append(self._icon_html('lactosefree', 'Lactose-free (possible)', is_possible=True, large=True))
        
        if recipe.get('glutenfree', 'no').lower() == 'yes':
            icons.append(self._icon_html('glutenfree', 'Gluten-free', taller=True))
        elif recipe.get('glutenfree', 'no').lower() == 'possible':
            icons.append(self._icon_html('glutenfree', 'Gluten-free (possible)',
                                         is_possible=True, taller=True))
        
        # Difficulty icon
        # Difficulty icon - only when a difficulty is actually stated;
        # never default to easy when the information is missing.
        difficulty = recipe.get('difficulty')
        if difficulty:
            difficulty_icons = self.difficulty_icons.get(difficulty.lower())
            if difficulty_icons:
                for icon in difficulty_icons:
                    icons.append(self._icon_html(
                        icon, f'Difficulty: {difficulty.capitalize()}', wide=True))
        
        # Food for dating icon
        if recipe.get('food_for_dating', False):
            icons.append(self._icon_html('food_for_dating', 'Food for dating', large=True))
        
        # Freezable icon - shown only when explicitly yes; never repeated as
        # text in the side-info row below the origin.
        if str(recipe.get('freezeable', '')).strip().lower() == 'yes':
            icons.append(self._icon_html('freezeable', 'Freezeable'))
        
        return ''.join(icons)
    
    def _icon_html(self, icon_type: str, title: str, is_possible: bool = False,
                   wide: bool = False, large: bool = False,
                   taller: bool = False) -> str:
        """Generate HTML for one icon inside its round backdrop.

        All size variants preserve the aspect ratio:
        - default: glyphs keep a fixed 1rem height inside the 2rem backdrop;
        - ``wide=True`` fits extra-wide artwork (the 132x45 difficulty
          strips) within the backdrop footprint;
        - ``large=True`` scales key glyphs up to a 1.5rem fit box so they
          fill more of the backdrop while staying contained inside it;
        - ``taller=True`` gives the tall, narrow glyphs (the gluten-free ear)
          the full circle height: a 1.75rem fit box whose deepest ink still
          lands ~2px inside the 2rem rim.
        """
        # Known icon keys are mapped; anything else is already a filename.
        icon_name = self.icon_mapping.get(icon_type, icon_type)
        
        # Try to load icon as file path for PDF compatibility
        icon_src = self._get_icon_src(icon_name)
        
        # Wide glyphs fit the 2rem backdrop width (~11 px tall for the
        # 132x45 difficulty strips); regular glyphs keep a fixed height;
        # large glyphs scale up to a 1.5rem fit box, the tall gluten-free
        # ear to 1.75rem - both still inside the 2rem backdrop.
        # max-w-none stops the flex parent from clamping the width, which
        # is what squashed wide images horizontally before.
        if wide:
            size_class = "w-auto h-auto max-w-[2rem] max-h-[1rem]"
        elif taller:
            size_class = "w-auto h-auto max-w-[1.75rem] max-h-[1.75rem]"
        elif large:
            size_class = "w-auto h-auto max-w-6 max-h-6"
        else:
            size_class = "h-4 w-auto max-w-none"
        css_class = f"{size_class} grayscale opacity-50" if is_possible else size_class
        
        return (f'<div class="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center" title="{title}">\n'
                f'  <img src="{icon_src}" alt="{title}" class="{css_class}" />\n'
                f'</div>\n')
    
    def _get_icon_src(self, icon_name: str) -> str:
        """Get icon as file path or data URI for PDF compatibility."""
        # Try to find the icon file
        search_paths = [
            Path("data_modularflavour/icon") / icon_name,
            Path(icon_name),
        ]
        
        for icon_path in search_paths:
            if icon_path.exists():
                # Use absolute path with file:// for Playwright
                try:
                    abs_path = icon_path.resolve()
                    return abs_path.as_uri()
                except Exception:
                    pass
        # Fallback to original filename
        return icon_name
    
    def _build_ingredients_sidebar(self, recipe: Dict, hardware_html: str,
                                   sauces_html: str) -> str:
        """Build the tinted left column: Ingredients, Hardware, Sauces.

        Emitted only for recipes that authored an Ingredients section; the
        side-by-side layout election depends on this panel existing.
        """
        # Servings ride in the Ingredients heading ("Ingredients (for 4)");
        # without a parseable value the heading stays plain.
        servings = recipe.get('servings')
        ingredients_suffix = f' (for {servings})' if servings else ''
        ingredients_html = self._generate_ingredients_html(
            recipe.get('ingredients', []))
        return (
            '<!-- Left Column: Ingredients & Sauces -->\n'
            '<aside class="col-span-5 bg-surface-container-low p-3 rounded '
            'border border-outline-variant/20" '
            'data-purpose="ingredients-sidebar">\n'
            '<!-- Ingredients Section -->\n'
            '<section class="mb-3 avoid-break">\n'
            f'<h2 class="section-heading">Ingredients{ingredients_suffix}</h2>\n'
            f'{ingredients_html}\n'
            '</section>\n'
            '    <!-- Hardware Section -->\n'
            f'{hardware_html}\n'
            f'{sauces_html}\n'
            '</aside>')

    def _build_fullwidth_extras(self, hardware_html: str,
                                sauces_html: str) -> str:
        """Build the (rare) no-ingredients page's full-width extras.

        A recipe without an Ingredients section prints no Ingredients section
        at all; Hardware or Sauces data, if ever authored, still prints - as a
        full-width block above the instructions instead of a sidebar panel.
        """
        extras = (hardware_html or '') + (sauces_html or '')
        if not extras:
            return ''
        return ('<div class="col-span-12">\n' + extras + '\n</div>')

    def _generate_ingredients_html(self, ingredients: List) -> str:
        """Generate HTML for ingredients list with nested sub-items."""
        # Nothing is written for a recipe without ingredients: the whole
        # Ingredients section is omitted rather than printing a placeholder.
        # The sidebar itself is only built when ingredients exist (see
        # render_html), so an empty list here means no markup at all.
        if not ingredients:
            return ''

        items = []
        for ing in ingredients:
            if isinstance(ing, dict):
                html = f'<li class="text-xs text-on-surface-variant"><span class="font-medium">{ing["main"]}</span>'
                if ing['sub']:
                    html += '<ul class="ml-4 mt-1 space-y-0.5">'
                    for sub in ing['sub']:
                        # No literal bullet: .ingredient-list li::before already
                        # draws one for every li, and a typed character here
                        # printed a second bullet next to it (Bibimbap's option
                        # group showed "••").
                        html += f'<li class="text-xs text-on-surface-variant italic">{sub}</li>'
                    html += '</ul>'
                html += '</li>'
                items.append(html)
            else:
                items.append(f'<li class="text-xs text-on-surface-variant">{ing}</li>')

        return f'<ul class="ingredient-list space-y-1">\n' + ''.join(items) + '</ul>'
    
    def _generate_sauces_html(self, sauces: List = None) -> str:
        """Generate HTML for sauces - only shown if sauce data exists."""
        if not sauces:
            return ''  # Don't show sauces section at all if no data
        
        items = []
        for sauce in sauces:
            if isinstance(sauce, dict):
                html = f'<li class="text-xs text-on-surface-variant"><span class="font-medium">{sauce["main"]}</span>'
                if sauce['sub']:
                    html += '<ul class="ml-4 mt-1 space-y-0.5">'
                    for sub in sauce['sub']:
                        # No literal bullet - CSS owns the marker (see
                        # _generate_ingredients_html).
                        html += f'<li class="text-xs text-on-surface-variant italic">{sub}</li>'
                    html += '</ul>'
                html += '</li>'
                items.append(html)
            else:
                items.append(f'<li class="text-xs text-slate-700">{sauce}</li>')
        
        # Include the full section wrapper when there's sauce data
        sauces_section = f'''<!-- Sauces Section -->
<section class="mb-3 avoid-break">
<h2 class="section-heading">Sauces</h2>
<ul class="ingredient-list space-y-1">
{''.join(items)}</ul>
</section>'''
        return sauces_section
    
    def _generate_hardware_html(self, hardware: List) -> str:
        """Generate HTML for hardware list with nested sub-items."""
        if not hardware:
            return ''

        items = []
        for hw in hardware:
            if isinstance(hw, dict):
                html = f'<li class="text-xs text-on-surface-variant"><span class="font-medium">{hw["main"]}</span>'
                if hw['sub']:
                    html += '<ul class="ml-4 mt-1 space-y-0.5">'
                    for sub in hw['sub']:
                        # No literal bullet - CSS owns the marker (see
                        # _generate_ingredients_html).
                        html += f'<li class="text-xs text-on-surface-variant italic">{sub}</li>'
                    html += '</ul>'
                html += '</li>'
                items.append(html)
            else:
                items.append(f'<li class="text-xs text-on-surface-variant">{hw}</li>')

        return f'''<!-- Hardware Section -->
<section class="mb-3 avoid-break">
<h2 class="section-heading">Hardware</h2>
<ul class="ingredient-list space-y-1">
{''.join(items)}</ul>
</section>'''

    def _cap_instruction_label(self, text: str) -> str:
        """Uppercase only the leading letter of an Instruction version label,
        preserving the author's own casing for the rest ('lazy version' ->
        'Lazy version', 'impress-your-date version' stays hyphenated)."""
        t = text.strip()
        return t[:1].upper() + t[1:] if t else t

    def _inline_md(self, text: str) -> str:
        """Convert a single line of inline markdown (**bold**, *italic*) to HTML.

        Step text is spliced into existing <p>/<li> wrappers, so the
        block-level <p>...</p> the markdown library emits for a lone
        paragraph is unwrapped, leaving only inline markup.
        """
        if not text:
            return text
        converted = markdown.markdown(text, extensions=['extra']).strip()
        if converted.startswith('<p>') and converted.endswith('</p>'):
            converted = converted[3:-4]
        return converted

    def _render_instruction_core(self, blocks: List) -> str:
        """Render a list of parsed instruction blocks as numbered steps (with
        sub-notes), prose paragraphs and verbatim sub-headings. Step numbering
        restarts at 1 after every verbatim sub-heading."""
        parts: List[str] = []
        step_number = 0
        for instr in blocks:
            kind = instr.get('kind', 'step') if isinstance(instr, dict) else 'step'

            if kind == 'heading':
                step_number = 0  # each verbatim section counts from 1
                level = instr.get('level')
                # A deeper level (`#####` nested in a `####` variant block)
                # prints as a small inline label so the hierarchy inside one
                # block stays visible; block-opening headings and legacy
                # level-less blocks keep the established sub-heading style.
                if isinstance(level, int) and level > 4:
                    parts.append(
                        '<div class="avoid-break mb-1 mt-2">'
                        '<h4 class="font-label font-bold uppercase '
                        'tracking-wider text-on-surface text-[0.72rem] '
                        f'leading-snug">{instr["text"]}</h4>'
                        '</div>')
                else:
                    parts.append(
                        '<div class="avoid-break mb-2 mt-3">'
                        '<h3 class="font-headline font-bold text-on-surface '
                        f'text-[0.95rem] leading-snug">{instr["text"]}</h3>'
                        '</div>')
                continue
            if kind == 'table':
                md = '\n'.join(instr.get('lines', []))
                table_html = markdown.markdown(md, extensions=['extra'])
                # Presentation-only class, not the intro marker: the marker is
                # reserved for the preamble wrapper (one marker = one splitter
                # stream). A marked table nested in the intro wrapper opened a
                # second intro stream next to its wrapper's.
                parts.append(
                    '<div class="instruction-intro-table avoid-break mb-2">'
                    f'{table_html}'
                    '</div>')
                continue
            if kind == 'prose':
                parts.append(
                    '<div class="avoid-break mb-2">'
                    '<p class="text-[0.78rem] text-on-surface-variant '
                    f'leading-relaxed font-body">{self._inline_md(instr["text"])}</p>'
                    '</div>')
                continue

            # A step.
            step_number += 1
            step_html = f'<div class="flex gap-3 mb-2 avoid-break">\n'
            step_html += f'  <span class="flex-shrink-0 w-5 h-5 rounded-full bg-secondary-fixed-dim text-on-surface flex items-center justify-center font-bold text-[0.65rem] font-label">{step_number}</span>\n'
            step_html += f'  <div class="text-[0.78rem] text-on-surface-variant leading-relaxed font-body">\n'
            step_html += f'    <p>{self._inline_md(instr["step"])}</p>\n'
            if instr.get('subs'):
                step_html += f'    <ul class="ml-4 mt-1 space-y-0.5 substep-list">\n'
                for sub in instr['subs']:
                    step_html += f'      <li class="substep text-[0.72rem] text-on-surface-variant">{self._inline_md(sub)}</li>\n'
                step_html += f'    </ul>\n'
            step_html += f'  </div>\n'
            step_html += f'</div>'
            parts.append(step_html)

        return ''.join(parts)

    def _generate_instructions_html(self, instructions: List,
                                    full_width: bool = False) -> str:
        """Generate HTML for the recipe's instruction area.

        Non-versioned recipes keep the classic single Instructions block.
        Versioned recipes (with "variant" labels, ADR 0012) get one headed
        block per version: each version prints as its own <section> with a
        proper section-heading and a clean separation from the others, so the
        splitter can place every version in its own vertical band.

        Recipes without an Ingredients section always print the vertical
        layout: ``full_width=True`` widens the article to all 12 grid columns
        and adds the ``data-vertical-recipe`` marker the splitter keys on to
        elect vertical instead of side-by-side.
        """
        article_open = (
            '<article class="col-span-12" data-vertical-recipe '
            'data-purpose="recipe-instructions">\n' if full_width else
            '<article class="col-span-7" '
            'data-purpose="recipe-instructions">\n')
        if not instructions:
            return (
                article_open
                + '<h2 class="section-heading">Instructions</h2>\n'
                '<div class="space-y-2 mt-2">\n'
                '<p class="text-xs text-on-surface-variant italic">No instructions listed</p>\n'
                '</div>\n'
                '</article>')

        has_variants = any(
            isinstance(i, dict) and i.get('kind') == 'variant' for i in instructions)

        has_headings = any(
            isinstance(i, dict) and i.get('kind') == 'heading' for i in instructions)

        if not has_variants and not has_headings:
            # Legacy single-block output (non-versioned recipes without
            # subheaders: Carbonara, Hummus). Untouched visually.
            body = self._render_instruction_core(instructions)
            return (
                article_open
                + '<h2 class="section-heading">Instructions</h2>\n'
                '<div class="space-y-2 mt-2">\n' + body + '\n</div>\n'
                '</article>')

        if not has_variants:
            # Heading-separated sections (no variants, but headings present).
            # The shallowest heading level found (a `####` among `####` and
            # `#####`) opens its own <section data-instruction-block>; deeper
            # headings stay inside that block as inline sub-headings (Pizza Al
            # Taglio: `##### Ingredients`/`##### Instructions` belong to their
            # `####` variant's block instead of splitting it in two, which
            # overwrote the variant name with "Ingredients" before any content
            # arrived). Headings without a recorded level (legacy fixtures,
            # hand-built dicts) keep opening blocks. The pre-heading intro
            # (if any) is rendered as <div data-instruction-intro> outside
            # the two-column band attribute so the splitter gives it full width.
            block_levels = [
                i['level'] for i in instructions
                if isinstance(i, dict) and i.get('kind') == 'heading'
                and isinstance(i.get('level'), int)]
            block_level = min(block_levels) if block_levels else None

            def opens_block(instr) -> bool:
                if not isinstance(instr, dict) or instr.get('kind') != 'heading':
                    return False
                level = instr.get('level')
                return block_level is None or level is None or level <= block_level

            sections: List[Dict] = []
            cur_label = None
            cur_blocks: List[Dict] = []
            for instr in instructions:
                if opens_block(instr):
                    if cur_blocks:
                        sections.append({'label': cur_label, 'blocks': cur_blocks})
                    cur_blocks = []
                    cur_label = instr['text']
                else:
                    cur_blocks.append(instr)
            if cur_blocks:
                sections.append({'label': cur_label, 'blocks': cur_blocks})

            intro_html = ''
            headed_sections = sections
            if sections and sections[0]['label'] is None:
                intro_blocks = sections[0]['blocks']
                if intro_blocks:
                    intro_html = (
                        '<div data-instruction-intro>'
                        '<div class="space-y-2">\n'
                        + self._render_instruction_core(intro_blocks)
                        + '</div>\n'
                        '</div>')
                headed_sections = sections[1:]

            sections_html: List[str] = []
            for sec in headed_sections:
                head = ''
                if sec['label']:
                    head = (
                        '<div class="instruction-block-head">\n'
                        f'<h3 class="section-heading">{html.escape(sec["label"])}</h3>\n'
                        '</div>\n')
                sections_html.append(
                    '<section class="instruction-block" data-instruction-block>\n'
                    + head
                    + '<div class="space-y-2">\n'
                    + self._render_instruction_core(sec['blocks'])
                    + '</div>\n'
                    + '</section>')

            body = '\n'.join(sections_html)
            return (
                article_open
                + '<h2 class="section-heading">Instructions</h2>\n'
                '<div class="space-y-2 mt-2">\n'
                + intro_html + ('\n' if intro_html and body else '') + body + '\n'
                '</div>\n'
                '</article>')

        # Versioned: split the block stream into sections. A "variant" line
        # opens a new headed section; anything before the first variant becomes
        # a headless intro block (e.g. Aglio's preamble).
        sections: List[Dict] = []
        cur_label = None
        cur_blocks: List[Dict] = []
        for instr in instructions:
            if isinstance(instr, dict) and instr.get('kind') == 'variant':
                if cur_blocks:
                    sections.append({'label': cur_label, 'blocks': cur_blocks})
                cur_blocks = []
                cur_label = self._cap_instruction_label(instr['label'])
            else:
                cur_blocks.append(instr)
        if cur_blocks:
            sections.append({'label': cur_label, 'blocks': cur_blocks})

        sections_html: List[str] = []
        for sec in sections:
            if not sec['label']:
                # Headless preamble: a plain intro div, exactly like the
                # heading path's shape. It must NOT also be an instruction
                # block - the intro marker marks the preamble and nothing else
                # (one marker = one splitter stream; a section carrying both
                # markers registered the preamble twice and relocated it onto
                # a later sheet, printing it after the steps that precede it).
                sections_html.append(
                    '<div data-instruction-intro>'
                    '<div class="space-y-2">\n'
                    + self._render_instruction_core(sec['blocks'])
                    + '</div>\n'
                    '</div>')
                continue
            head = (
                '<div class="instruction-block-head">\n'
                f'<h3 class="section-heading">{html.escape(sec["label"])}</h3>\n'
                '</div>\n')
            sections_html.append(
                '<section class="instruction-block" data-instruction-block>\n'
                + head
                + '<div class="space-y-2">\n'
                + self._render_instruction_core(sec['blocks'])
                + '</div>\n'
                '</section>')

        body = '\n'.join(sections_html)
        return (
            article_open
            + '<div class="space-y-2 mt-2">\n' + body + '\n</div>\n'
            '</article>')
    
    def _generate_origin_html(self, recipe: Dict) -> str:
        """Generate the origin pin row; omitted entirely when origin is absent."""
        origin = recipe.get('origin')
        if not origin:
            return ''
        return (
            '<div class="flex items-center gap-2 text-[0.7rem] font-label text-on-surface-variant mt-1 mb-2">\n'
            '<span class="flex items-center gap-1">\n'
            '<svg class="w-3 h-3" fill="none" stroke="currentColor" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">\n'
            '<path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path>\n'
            '<path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path>\n'
            f'</svg>\n{origin}\n</span>\n</div>'
        )

    def _generate_description_html(self, recipe: Dict) -> str:
        """Generate the description quote block, or a visible TODO stub.

        The block is unlabelled: the italic quote styling already marks it as
        the page's lead sentence, so no "Description:" prefix is printed
        (mirroring how a sideinfo page opens with its description, ADR 0020).
        """
        description = recipe.get('description')
        if description:
            return (
                '<p class="text-[0.75rem] leading-relaxed text-on-surface-variant italic '
                'border-l-4 border-secondary-fixed-dim pl-3 py-1 font-body">\n'
                f'{description}\n'
                '</p>'
            )
        return (
            '<p class="text-[0.75rem] leading-relaxed border-l-4 border-amber-500 '
            'bg-amber-50 pl-3 py-1 font-body text-amber-800">\n'
            '<span class="font-label font-bold uppercase tracking-widest">TODO</span>'
            ' &mdash; add a description\n'
            '</p>'
        )

    def _generate_sauce_profile_group_html(self, recipe: Dict) -> str:
        """Generate the sauce profile group: one nested-pill container holding
        the profile chips, labelled per page type (see CONTEXT.md)."""
        profile_fields = [
            ('sauce_flavour', 'Flavour'),
            ('sauce_consistency', 'Consistency'),
            ('sauce_usage', 'Usage'),
        ]
        chips = []
        for key, label in profile_fields:
            value = recipe.get(key)
            if value:
                chips.append(
                    '<span class="inline-flex items-center rounded-full bg-secondary-fixed '
                    f'px-2 py-0.5 text-[0.65rem] font-label text-on-surface'
                    f'"><strong class="font-semibold">{label}:</strong>&nbsp;{value}</span>'
                )
        if not chips:
            return ''
        label_html = (
            f'<span class="font-label font-bold uppercase tracking-widest '
            f'text-[0.65rem] text-on-surface-variant">{self._sauce_profile_label(recipe)}</span>'
        )
        return (
            '<div class="inline-flex flex-wrap items-center gap-1.5 mt-1 mb-1 '
            'rounded-full border border-outline-variant/40 bg-surface-container px-3 py-1">'
            + label_html + ''.join(chips) + '</div>'
        )

    @staticmethod
    def _sauce_profile_label(recipe: Dict) -> str:
        """'Sauce profile' on sauce pages; 'Sauce pairing' everywhere else."""
        if str(recipe.get('subgroup', '')).strip().lower() == 'sauce':
            return 'Sauce profile'
        return 'Sauce pairing'

    def _generate_side_info_html(self, recipe: Dict) -> str:
        """Generate HTML for side info."""
        info_items = []
        
        group = recipe.get('group', '').lower()
        if group and group not in ('component', 'dish'):
            info_items.append(f'<span><strong>Group:</strong> {recipe.get("group")}</span>')
        if recipe.get('subgroup'):
            info_items.append(f'<span><strong>Subgroup:</strong> {recipe.get("subgroup")}</span>')
        if recipe.get('carbsource'):
            info_items.append(f'<span><strong>Carbs:</strong> {recipe.get("carbsource")}</span>')
        # Time formula is displayed verbatim, exactly as written in the source
        # (e.g. "(02h30) + 04h00", "00h01", "(00h20 * x) + 00h05").
        if recipe.get('time_formula'):
            info_items.append(f'<span><strong>Time:</strong> {recipe["time_formula"]}</span>')
        if recipe.get('servings_range'):
            info_items.append(f'<span><strong>Range:</strong> {recipe.get("servings_range")} people</span>')
        if recipe.get('work_after_premade'):
            info_items.append(f'<span><strong>Premade:</strong> {recipe.get("work_after_premade")}</span>')
        
        if info_items:
            return f'<div class="flex flex-wrap gap-2 text-[0.7rem] text-on-surface-variant font-label mb-2">{" ".join(info_items)}</div>'
        return ''
    
    def _get_html_template(self) -> str:
        """Get the HTML template for rendering."""
        return """<!DOCTYPE html>
<html class="light" lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Recipe: {title}</title>
 <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
 <link href="lib/fonts/fonts.css" rel="stylesheet"/>
<script id="tailwind-config">
    tailwind.config = {{
        darkMode: "class",
        theme: {{
            extend: {{
                "colors": {{
                    "surface-container-low": "#f1f4f2",
                    "on-secondary": "#edfee2",
                    "primary": "#47664a",
                    "secondary-fixed-dim": "#c9dabf",
                    "on-surface-variant": "#59615f",
                    "secondary-fixed": "#d7e8cd",
                    "inverse-on-surface": "#9b9d9c",
                    "secondary-container": "#d7e8cd",
                    "surface": "#ffffff",
                    "on-error": "#fff7f6",
                    "on-error-container": "#6e1400",
                    "surface-container-lowest": "#ffffff",
                    "outline": "#757c7a",
                    "background": "#ffffff",
                    "tertiary": "#5a6331",
                    "surface-variant": "#dde4e1",
                    "outline-variant": "#acb4b1",
                    "on-surface": "#2d3432",
                    "surface-container": "#eaefec",
                    "on-primary": "#e9ffe6",
                    "secondary": "#54634e"
                }},
                "fontFamily": {{
                    "headline": ["Manrope", "sans-serif"],
                    "body": ["Work Sans", "sans-serif"],
                    "label": ["Plus Jakarta Sans", "sans-serif"]
                }}
            }}
        }}
    }}
</script>
<style>
    .material-symbols-outlined {{
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    }}
    .recipe-page {{
        width: 210mm;
        height: 297mm;
        padding: 25mm 15mm 15mm 25mm; /* Top 25, Right 15, Bottom 15, Left 25 (= 15 base + 10mm book gutter) */
        box-sizing: border-box;
        background: #ffffff;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        position: relative;
        isolation: isolate;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }}
    @page {{
        size: A4;
        margin: 0;
    }}
    @media print {{
        html, body {{
            margin: 0;
            padding: 0;
            background: white !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }}
        .recipe-page {{
            margin: 0;
            box-shadow: none !important;
            border: none;
            page-break-after: always;
            break-after: page;
            page-break-inside: avoid;
        }}
        /* Multi-sheet documents stack vertically when printed. */
        main {{
            display: block !important;
            padding: 0 !important;
            min-height: 0 !important;
        }}
    }}
    .section-heading {{
        font-family: 'Manrope', sans-serif;
        font-weight: 700;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        color: #2d3432;
        border-bottom: 2px solid rgba(71, 102, 74, 0.3);
        display: inline-block;
        margin-bottom: 0.5rem;
        padding-bottom: 0.15rem;
    }}
    .ingredient-list li {{
        position: relative;
        padding-left: 1.2rem;
        margin-bottom: 0.15rem;
        font-size: 0.8rem;
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: #59615f;
    }}
    .ingredient-list li::before {{
        content: '•';
        position: absolute;
        left: 0;
        color: #47664a;
        font-weight: bold;
    }}
    .avoid-break {{
        page-break-inside: avoid;
        break-inside: avoid;
    }}
    .instruction-block {{
        background: rgba(71, 102, 74, 0.04);
        border-radius: 0.375rem;
        padding: 0.75rem;
        margin-bottom: 0.75rem;
    }}
    .instruction-block .instruction-block-head {{
        margin-bottom: 0.5rem;
    }}
    /* Substep marker: each substep gets its own short green line, top-aligned
       and trimmed at the bottom (ADR-free visual tweak, see CONTEXT.md
       "Substep"), so consecutive substeps read as separate points instead of
       one continuous rail. padding-left mirrors the old pl-2 exactly, so
       splitter measurements are unchanged. */
    .substep {{
        position: relative;
        padding-left: 0.5rem;
    }}
    .substep::before {{
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0.4rem;
        border-left: 2px solid #c9dabf; /* secondary-fixed-dim */
    }}
    .mermaid-diagram {{
        margin: 1rem 0;
        padding: 1rem;
        background: #f1f4f2;
        border-radius: 0.5rem;
        overflow-x: auto;
        break-inside: avoid;
    }}
    .mermaid-diagram svg {{
        max-width: 100%;
        height: auto;
    }}
    .content-text table,
    .instruction-intro-table table {{
        table-layout: auto;
        width: 100%;
        border-collapse: collapse;
        font-size: 0.75rem;
        color: #59615f;
        margin-top: 0.5rem;
        margin-bottom: 0.75rem;
        break-inside: avoid;
    }}
    .instruction-intro-table table th {{
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #59615f;
        border-bottom: 1pt solid #47664a;
        opacity: 0.8;
        text-align: left;
        padding: 0.35rem 0.6rem;
    }}
    .instruction-intro-table table td {{
        padding: 0.3rem 0.6rem;
        border-bottom: 1px solid rgba(116,124,122,0.15);
        font-family: 'Work Sans', sans-serif;
        font-size: 0.75rem;
        line-height: 1.35;
        color: #59615f;
    }}
    .instruction-intro-table table tbody tr:nth-child(even) td {{
        background-color: #f1f4f2;
    }}
    .instruction-intro-table table td:first-child {{
        width: 1%;
        white-space: nowrap;
        text-align: center;
        vertical-align: middle;
    }}
    .instruction-intro-table table td:first-child img {{
        display: block;
        margin: 0 auto;
    }}
    .instruction-intro-table table td:last-child {{
        width: auto;
    }}
</style>
<!-- Mermaid.js for diagrams -->
<script src="lib/mermaid.min.js"></script>
<script>
    mermaid.initialize({{
        startOnLoad: true,
        theme: 'default',
        flowchart: {{
            useMaxWidth: true,
            htmlLabels: true,
            curve: 'basis'
        }},
        securityLevel: 'loose'
    }});
</script>
</head>
<body class="font-body text-on-surface print:bg-white">
<main class="py-8 print:py-0 flex justify-center items-center min-h-screen w-full">
<div class="recipe-page">
<!-- Header Section -->
<div class="flex justify-between items-start mb-4">
<div class="flex-grow">
<h1 class="font-headline font-extrabold text-[2.8rem] leading-none tracking-tighter text-on-surface mb-1" id="page-{clean_title_id}">{title}</h1>
{origin_block}
{side_info}
{description_block}
{profile_chips}
<div class="h-[1px] w-full bg-primary/20 mt-2"></div>
</div>
<!-- Icon Box -->
<div class="flex flex-col gap-1 bg-surface-container p-2 rounded border border-outline-variant/30 shadow-sm ml-4 flex-shrink-0">
{icons}
</div>
</div>
<!-- Main Recipe Grid -->
<div class="grid grid-cols-12 gap-3 flex-grow overflow-hidden" style="page-break-before: avoid; break-before: avoid; align-content: start;">
{sidebar_block}
<!-- Right Column: Instructions -->
<!-- Right Column Instructions: the full <article> is emitted by _generate_instructions_html -->
{instructions}
</div>
<div data-page-footer></div>
</div>
</main>
</body></html>"""
