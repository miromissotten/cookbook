from pathlib import Path


def inject_notdone_watermark(html_path: str, watermark_css: str) -> None:
    path = Path(html_path)
    if not path.exists():
        return
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    if 'notdone-watermark' in html:
        return
    html = html.replace('<div class="recipe-page"', '<div class="recipe-page notdone-watermark"')
    html = html.replace('</style>', watermark_css + '\n</style>', 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
