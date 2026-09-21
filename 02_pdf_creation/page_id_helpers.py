import re


def page_id_for_title(title: str, is_recipe: bool = False) -> str:
    clean_id = str(title).replace(' ', '-').replace('_', '-').lower()
    if not is_recipe:
        clean_id = re.sub(r'[^a-z0-9\-]', '', clean_id)
    return 'page-' + clean_id
