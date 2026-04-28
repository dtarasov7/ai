from __future__ import annotations

import html
import json
import os
import re
import shutil
from pathlib import Path

from bs4 import BeautifulSoup
import mistune


REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERED_DIR = REPO_ROOT / "rendered"
MARKDOWN_RENDERER = mistune.create_markdown(plugins=["table"])


SOURCE_DIRS = [
    REPO_ROOT / "labs",
    REPO_ROOT / "markmaps",
    REPO_ROOT / "capstone",
    REPO_ROOT / "teacher",
    REPO_ROOT / "shop-demo",
]


def main() -> None:
    shutil.rmtree(RENDERED_DIR, ignore_errors=True)
    RENDERED_DIR.mkdir(parents=True, exist_ok=True)

    sources = collect_sources()
    for source in sources:
        render_source(source)

    print(f"Rendered local HTML files: {len(sources)}")
    print(f"Output directory: {RENDERED_DIR}")


def collect_sources() -> list[Path]:
    sources: list[Path] = []
    for directory in SOURCE_DIRS:
        if not directory.exists():
            continue
        for extension in ("*.md", "*.mm"):
            sources.extend(path for path in directory.rglob(extension) if path.is_file())
    return sorted(sources)


def render_source(source: Path) -> None:
    relative = source.relative_to(REPO_ROOT)
    target = (RENDERED_DIR / relative).with_suffix(".html")
    target.parent.mkdir(parents=True, exist_ok=True)

    raw = source.read_text(encoding="utf-8")
    if source.suffix == ".mm":
        content = render_markmap_page(source, target, raw)
    else:
        content = render_markdown_page(source, target, raw)
    target.write_text(content, encoding="utf-8", newline="\n")


def render_markdown_page(source: Path, target: Path, raw: str) -> str:
    title = extract_title(raw) or source.name
    body_html = MARKDOWN_RENDERER(raw)
    soup = BeautifulSoup(body_html, "html.parser")
    rewrite_links(soup, source, target)

    return wrap_page(
        title=title,
        target=target,
        body=f"""
<main class="markdown-body">
{soup}
</main>
""".strip(),
        raw_link=relative_href(target, source),
    )


def render_markmap_page(source: Path, target: Path, raw: str) -> str:
    title = extract_title(raw) or source.name
    raw_json = json.dumps(raw, ensure_ascii=False)
    d3_script = html.escape(relative_href(target, REPO_ROOT / "js" / "d3.min.js"))
    markmap_view_script = html.escape(relative_href(target, REPO_ROOT / "js" / "markmap-view.js"))
    markmap_lib_script = html.escape(relative_href(target, REPO_ROOT / "js" / "markmap-lib.js"))
    course_viewer_script = html.escape(relative_href(target, REPO_ROOT / "js" / "markmap-course-viewer.js"))

    body = f"""
<main class="markmap-page">
  <div class="markmap-toolbar">
    <div>
      <h2>{html.escape(title)}</h2>
      <p>Карта построена из файла <code>{html.escape(source.relative_to(REPO_ROOT).as_posix())}</code>.</p>
    </div>
    <div class="markmap-actions">
      <div class="markmap-status">
        <span id="fold-status">Все уровни раскрыты. 2-5 задают видимую глубину, 0 раскрывает всё</span>
        <span id="presentation-status">Презентация выключена. M включает, N/P листают ветки</span>
      </div>
      <button id="zoom-in" type="button">+</button>
      <button id="zoom-out" type="button">-</button>
      <button id="fit-button" type="button">Вписать</button>
      <button id="presentation-toggle" type="button">Презентация</button>
      <button id="settings-toggle" type="button">Настройки</button>
      <a href="{html.escape(relative_href(target, source))}">Открыть raw</a>
    </div>
  </div>
  <svg id="markmap-svg"></svg>
  <div class="settings-panel" id="settings-panel">
    <div class="settings-header">
      <span>Настройки Markmap</span>
      <button class="close-settings" id="close-settings" type="button">&times;</button>
    </div>
    <div class="settings-content">
      <div class="setting-group">
        <div class="setting-label">
          <span>Длительность анимации</span>
          <span class="setting-value" id="duration-value">0</span>
        </div>
        <input type="range" class="setting-slider" id="duration-slider" min="0" max="2000" value="0" step="100">
      </div>
      <div class="setting-group">
        <div class="setting-label">
          <span>Ширина переноса</span>
          <span class="setting-value" id="wrapWidth-value">28</span>
        </div>
        <input type="range" class="setting-slider" id="wrapWidth-slider" min="4" max="150" value="28" step="1">
      </div>
      <div class="setting-group">
        <div class="setting-label">
          <span>Минимальная высота узла</span>
          <span class="setting-value" id="nodeMinHeight-value">20</span>
        </div>
        <input type="range" class="setting-slider" id="nodeMinHeight-slider" min="5" max="100" value="20" step="5">
      </div>
      <div class="setting-group">
        <div class="setting-label">
          <span>Вертикальный отступ</span>
          <span class="setting-value" id="spacingVertical-value">10</span>
        </div>
        <input type="range" class="setting-slider" id="spacingVertical-slider" min="0" max="100" value="10" step="5">
      </div>
      <div class="setting-group">
        <div class="setting-label">
          <span>Горизонтальный отступ</span>
          <span class="setting-value" id="spacingHorizontal-value">70</span>
        </div>
        <input type="range" class="setting-slider" id="spacingHorizontal-slider" min="20" max="500" value="70" step="10">
      </div>
      <button class="reset-button" id="reset-settings" type="button">Сбросить настройки</button>
    </div>
  </div>
</main>
<script src="{d3_script}"></script>
<script src="{markmap_view_script}"></script>
<script src="{markmap_lib_script}"></script>
<script>
  window.courseMarkmapSource = {raw_json};
  const source = window.courseMarkmapSource;

  function showFallback(message) {{
    const svg = document.getElementById('markmap-svg');
    svg.outerHTML = '<div class="viewer-error">' + message + '</div>';
  }}

  if (false) window.addEventListener('load', () => {{
    try {{
      if (!window.markmap || !window.markmap.Transformer || !window.markmap.Markmap) {{
        showFallback('Не удалось загрузить markmap-библиотеки. Проверьте доступ к CDN или откройте исходный текст карты ниже.');
        return;
      }}

      const transformer = new window.markmap.Transformer();
      const {{ root }} = transformer.transform(source);
      const svg = document.getElementById('markmap-svg');
      const instance = window.markmap.Markmap.create(svg, {{
        duration: 0,
        autoFit: true,
        spacingHorizontal: 80,
        spacingVertical: 8,
      }}, root);

      document.getElementById('fit-button').addEventListener('click', () => instance.fit());
      setTimeout(() => instance.fit(), 50);
    }} catch (error) {{
      showFallback('Ошибка построения карты: ' + error.message);
    }}
  }});
</script>
<script src="{course_viewer_script}"></script>
""".strip()

    return wrap_page(title=title, target=target, body=body, raw_link=relative_href(target, source), is_markmap=True)


def wrap_page(title: str, target: Path, body: str, raw_link: str, is_markmap: bool = False) -> str:
    stylesheet = relative_href(target, REPO_ROOT / "styles.css")
    index_link = relative_href(target, REPO_ROOT / "index.html")
    page_class = "viewer-page markmap-viewer-page" if is_markmap else "viewer-page"

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="{html.escape(stylesheet)}">
  <style>
    body {{
      background: #f6f8f5;
    }}
    .viewer-page {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px;
    }}
    .markmap-viewer-page {{
      width: 100%;
      max-width: none;
      margin: 0;
      padding: 12px 18px 18px;
    }}
    .viewer-topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 18px;
      padding: 12px 0;
    }}
    .viewer-topbar a,
    .markmap-actions a,
    .markmap-actions button {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 12px;
      border: 0;
      border-radius: 6px;
      background: #fff;
      color: #165745;
      text-decoration: none;
      font: inherit;
      cursor: pointer;
    }}
    .markdown-body {{
      background: #fff;
      border: 1px solid rgba(31, 46, 40, 0.14);
      border-radius: 8px;
      padding: 28px;
      line-height: 1.6;
    }}
    .markdown-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 18px 0;
    }}
    .markdown-body th,
    .markdown-body td {{
      border: 1px solid rgba(31, 46, 40, 0.2);
      padding: 8px 10px;
      vertical-align: top;
    }}
    .markdown-body pre {{
      overflow-x: auto;
      padding: 16px;
      border-radius: 8px;
      background: #f1f3f2;
      color: #1f2e28;
    }}
    .markdown-body pre code {{
      color: inherit;
    }}
    .markmap-page {{
      min-height: calc(100vh - 80px);
      background: #fff;
      padding: 0;
    }}
    .markmap-toolbar {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 12px;
      padding-bottom: 12px;
    }}
    .markmap-toolbar h2 {{
      margin: 0 0 6px;
    }}
    .markmap-toolbar p {{
      margin: 0;
      color: #5c6b63;
    }}
    .markmap-actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
      align-items: center;
      max-width: 680px;
    }}
    .markmap-status {{
      flex: 1 1 100%;
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 260px;
      color: #5c6b63;
      font-size: 12px;
      line-height: 1.35;
      text-align: right;
    }}
    #zoom-in,
    #zoom-out {{
      width: 34px;
      justify-content: center;
      padding: 0;
    }}
    #markmap-svg {{
      width: 100%;
      height: calc(100vh - 160px);
      min-height: 680px;
    }}
    .settings-panel {{
      position: fixed;
      top: 0;
      right: -360px;
      z-index: 20;
      width: 340px;
      max-width: calc(100vw - 28px);
      height: 100vh;
      background: #fff;
      box-shadow: -8px 0 24px rgba(31, 46, 40, 0.12);
      transition: right 0.2s ease;
      overflow-y: auto;
    }}
    .settings-panel.active {{
      right: 0;
    }}
    .settings-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 16px 18px;
      font-weight: 700;
    }}
    .settings-content {{
      padding: 18px;
    }}
    .setting-group {{
      margin-bottom: 18px;
    }}
    .setting-label {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
      color: #24352e;
      font-size: 14px;
      font-weight: 600;
    }}
    .setting-value {{
      color: #165745;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .setting-slider {{
      width: 100%;
    }}
    .close-settings {{
      width: 34px;
      height: 34px;
      padding: 0;
      border: 0;
      border-radius: 6px;
      background: #fff;
      color: #165745;
      cursor: pointer;
      font-size: 22px;
      line-height: 1;
    }}
    .reset-button {{
      width: 100%;
      min-height: 38px;
      border: 0;
      border-radius: 6px;
      background: #fff;
      color: #165745;
      cursor: pointer;
      font: inherit;
    }}
    .viewer-error {{
      margin: 24px 0;
      padding: 18px;
      border-left: 4px solid #b3261e;
      background: #fff1f1;
      color: #77120c;
    }}
    @media (max-width: 760px) {{
      .viewer-page {{
        padding: 14px;
      }}
      .markmap-viewer-page {{
        padding: 8px;
      }}
      .viewer-topbar,
      .markmap-toolbar {{
        flex-direction: column;
        align-items: stretch;
      }}
      .markdown-body {{
        padding: 18px;
      }}
      #markmap-svg {{
        height: calc(100vh - 220px);
        min-height: 480px;
      }}
    }}
  </style>
</head>
<body>
  <div class="{page_class}">
    <nav class="viewer-topbar">
      <a href="{html.escape(index_link)}">К основному курсу</a>
      <a href="{html.escape(raw_link)}">Открыть исходный файл</a>
    </nav>
{body}
  </div>
</body>
</html>
"""


def rewrite_links(soup: BeautifulSoup, source: Path, target: Path) -> None:
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith("#") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href):
            continue

        path_part, hash_part = split_href(href)
        linked_source = (source.parent / path_part).resolve()
        try:
            linked_source.relative_to(REPO_ROOT.resolve())
        except ValueError:
            continue

        if linked_source.suffix in {".md", ".mm"}:
            linked_target = (RENDERED_DIR / linked_source.relative_to(REPO_ROOT)).with_suffix(".html")
            anchor["href"] = relative_href(target, linked_target) + hash_part


def split_href(href: str) -> tuple[str, str]:
    if "#" not in href:
        return href, ""
    path, hash_value = href.split("#", 1)
    return path, f"#{hash_value}"


def extract_title(raw: str) -> str | None:
    match = re.search(r"^\s*#\s+(.+?)\s*$", raw, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def relative_href(from_file: Path, to_file: Path) -> str:
    return Path(os.path.relpath(to_file.resolve(), start=from_file.parent.resolve())).as_posix()


if __name__ == "__main__":
    main()
