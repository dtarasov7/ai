from __future__ import annotations

import html
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from bs4 import BeautifulSoup
import mistune


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = DIST_DIR / "_epub_build"
OUTPUT_FILE = DIST_DIR / "security-kubernetes-deckhouse-course.epub"
BOOK_TITLE = "Безопасность Kubernetes и Deckhouse Kubernetes Platform"
BOOK_LANGUAGE = "ru"
BOOK_CREATOR = "DKP Course Materials"
BOOK_IDENTIFIER = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://local/c/repos/dkp/security-kubernetes-deckhouse-course"))


EPUB_CSS = """
body {
  margin: 5%;
  font-family: serif;
  line-height: 1.55;
  color: #1f2e28;
}

h1, h2, h3, h4, h5, h6 {
  font-family: sans-serif;
  line-height: 1.2;
}

h1 {
  margin-top: 0;
  font-size: 1.8em;
}

h2 {
  margin-top: 1.7em;
  font-size: 1.35em;
}

h3 {
  margin-top: 1.25em;
  font-size: 1.12em;
}

a {
  color: #165745;
  text-decoration: none;
}

code, pre {
  font-family: monospace;
}

pre {
  white-space: pre-wrap;
  word-break: break-word;
  padding: 0.9em;
  border: 1px solid #d7d7d7;
  background: #f8f8f8;
  border-radius: 0.4em;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
}

th, td {
  border: 1px solid #d7d7d7;
  padding: 0.45em 0.55em;
  vertical-align: top;
  text-align: left;
}

thead th {
  background: #f0f0f0;
}

ul, ol {
  padding-left: 1.3em;
}

li + li {
  margin-top: 0.35em;
}

.hero {
  padding-bottom: 1em;
  margin-bottom: 1.4em;
  border-bottom: 2px solid #d9d9d9;
}

.hero p {
  margin-bottom: 0.6em;
}

.section {
  margin: 1.2em 0 1.4em;
}

.card, .note, .diagram {
  margin: 1em 0;
  padding: 0.9em 1em;
  border: 1px solid #d7d7d7;
  border-radius: 0.4em;
  background: #fbfbfb;
}

.meta, .pill-row {
  margin: 0.8em 0 0;
}

.badge, .pill {
  display: inline-block;
  margin: 0 0.35em 0.35em 0;
  padding: 0.25em 0.6em;
  border: 1px solid #d7d7d7;
  border-radius: 999px;
  background: #f4f4f4;
  font-family: sans-serif;
  font-size: 0.8em;
}

.lead {
  font-size: 1.05em;
}

.button-row, .chapter-nav, .toc {
  display: none;
}
""".strip()


PROGRAM_SECTION_HEADINGS = {
    "Цель курса",
    "Для кого курс",
    "Входные требования",
    "Рекомендуемый формат",
    "Сквозной сценарий курса",
    "Результаты обучения по курсу",
    "Программа по модулям",
    "Цель модуля",
    "Обязательный минимум",
    "Углубление",
    "Практика",
    "Результат на выходе",
    "Итоговая практическая работа",
    "Версия и оговорки",
    "Сопровождающие материалы",
    "Что такое `shop-demo` физически",
}


@dataclass(frozen=True)
class DocSpec:
    source: Path | None
    output_name: str
    title: str
    kind: str
    section_label: str


DOCS: list[DocSpec] = [
    DocSpec(None, "00_title.xhtml", BOOK_TITLE, "generated-title", "Титульный лист"),
    DocSpec(REPO_ROOT / "index.html", "01_preface.xhtml", "О курсе", "html", "Введение"),
    DocSpec(REPO_ROOT / "программа_курса.txt", "02_program.xhtml", "Программа курса", "txt", "Введение"),
    DocSpec(REPO_ROOT / "chapter_1" / "index.html", "03_chapter_1.xhtml", "Глава 1. Основы информационной безопасности в Kubernetes и Deckhouse Kubernetes Platform", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_2" / "index.html", "04_chapter_2.xhtml", "Глава 2. Безопасность пода", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_3" / "index.html", "05_chapter_3.xhtml", "Глава 3. Сетевые политики безопасности. mTLS", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_4" / "index.html", "06_chapter_4.xhtml", "Глава 4. Управление доступом", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_5" / "index.html", "07_chapter_5.xhtml", "Глава 5. Argo CD и operator-argo: контролируемый доступ к приложениям, GitOps и новые риски", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_6" / "index.html", "08_chapter_6.xhtml", "Глава 6. Управление сертификатами и секретами", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_7" / "index.html", "09_chapter_7.xhtml", "Глава 7. Выявление уязвимостей и аудит безопасности", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_8" / "index.html", "10_chapter_8.xhtml", "Глава 8. Мультиарендность и безопасные проектные шаблоны", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_9" / "index.html", "11_chapter_9.xhtml", "Глава 9. Compliance, CIS и DKP CSE", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_10" / "index.html", "12_chapter_10.xhtml", "Глава 10. NeuVector и внешние security-платформы", "html", "Главы"),
    DocSpec(REPO_ROOT / "chapter_11" / "index.html", "13_chapter_11.xhtml", "Глава 11. Модули Deckhouse как часть модели угроз", "html", "Главы"),
    DocSpec(REPO_ROOT / "shop-demo" / "README.md", "13_shop_demo.xhtml", "Приложение A. Учебный стенд shop-demo", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "README.md", "14_labs_overview.xhtml", "Приложение B. Лабораторные работы", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_01_threat_model.md", "11_lab_01.xhtml", "Лабораторная работа 1. Карта угроз и baseline платформы", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_02_pod_security.md", "12_lab_02.xhtml", "Лабораторная работа 2. Pod security и admission baseline", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_03_network_and_mtls.md", "13_lab_03.xhtml", "Лабораторная работа 3. Сетевой baseline и mTLS", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_04_access_model.md", "14_lab_04.xhtml", "Лабораторная работа 4. IAM-модель для shop-demo", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_05_argocd_access.md", "15_lab_05.xhtml", "Лабораторная работа 5. Argo CD как контролируемый доступ к приложениям", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_06_certs_and_secrets.md", "16_lab_06.xhtml", "Лабораторная работа 6. Сертификаты, секреты и delivery patterns", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_07_scanning_and_audit.md", "17_lab_07.xhtml", "Лабораторная работа 7. Scanning, supply chain и triage findings", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_08_multitenancy.md", "18_lab_08.xhtml", "Лабораторная работа 8. Мультиарендность и безопасный проектный шаблон", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_09_compliance_cse.md", "19_lab_09.xhtml", "Лабораторная работа 9. Compliance, CIS и DKP CSE", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_10_neuvector_luntry.md", "20_lab_10.xhtml", "Лабораторная работа 10. NeuVector, Luntry и внешние security-платформы", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "labs" / "lab_11_module_risk_matrix.md", "21_lab_11.xhtml", "Лабораторная работа 11. Модули Deckhouse как часть модели угроз", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "README.md", "21_markmaps_overview.xhtml", "Приложение C. Markmap-карты", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_01_foundations.mm", "18_markmap_01.xhtml", "Карта. Глава 1", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_02_pod_security.mm", "19_markmap_02.xhtml", "Карта. Глава 2", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_03_network_mtls.mm", "20_markmap_03.xhtml", "Карта. Глава 3", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_04_access_management.mm", "21_markmap_04.xhtml", "Карта. Глава 4", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_05_argocd_access.mm", "22_markmap_05.xhtml", "Карта. Глава 5", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_06_certs_and_secrets.mm", "23_markmap_06.xhtml", "Карта. Глава 6", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_07_scanning_and_audit.mm", "24_markmap_07.xhtml", "Карта. Глава 7", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_08_multitenancy.mm", "25_markmap_08.xhtml", "Карта. Глава 8", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_09_compliance_cse.mm", "26_markmap_09.xhtml", "Карта. Глава 9", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_10_neuvector_luntry.mm", "27_markmap_10.xhtml", "Карта. Глава 10", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "markmaps" / "chapter_11_module_risk_matrix.mm", "28_markmap_11.xhtml", "Карта. Глава 11", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "capstone" / "final_assessment_template.md", "28_capstone.xhtml", "Приложение D. Шаблон итоговой проверки", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "capstone" / "reference_argocd_access_solution.md", "29_capstone_argocd_reference.xhtml", "Приложение E. Эталонный пример: Argo CD вместо прямого kubectl", "markdown", "Приложения"),
    DocSpec(REPO_ROOT / "capstone" / "reference_direct_kubectl_solution.md", "30_capstone_direct_kubectl_reference.xhtml", "Приложение F. Эталонный пример: прямой kubectl с компенсирующими мерами", "markdown", "Приложения"),
]


MARKDOWN_RENDERER = mistune.create_markdown(plugins=["table"])


def main() -> None:
    link_map = build_link_map(DOCS)
    prepare_build_dir()
    try:
        write_static_files()
        rendered_docs = [render_document(spec, link_map) for spec in DOCS]
        write_rendered_documents(rendered_docs)
        write_nav(rendered_docs)
        write_ncx(rendered_docs)
        write_package(rendered_docs)
        build_epub_archive()
    finally:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)

    print(f"EPUB created: {OUTPUT_FILE}")


def build_link_map(docs: Iterable[DocSpec]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for doc in docs:
        if doc.source is None:
            continue
        source_relative = doc.source.relative_to(REPO_ROOT).as_posix()
        mapping[source_relative] = doc.output_name
        if doc.source.suffix in {".md", ".mm"}:
            rendered_alias = (Path("rendered") / doc.source.relative_to(REPO_ROOT)).with_suffix(".html")
            mapping[rendered_alias.as_posix()] = doc.output_name
    return mapping


def prepare_build_dir() -> None:
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    (BUILD_DIR / "META-INF").mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "OEBPS" / "text").mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "OEBPS" / "styles").mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)


def write_static_files() -> None:
    (BUILD_DIR / "mimetype").write_text("application/epub+zip", encoding="utf-8")
    (BUILD_DIR / "META-INF" / "container.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""".strip(),
        encoding="utf-8",
    )
    (BUILD_DIR / "OEBPS" / "styles" / "epub.css").write_text(EPUB_CSS, encoding="utf-8")


def render_document(spec: DocSpec, link_map: dict[str, str]) -> dict[str, str]:
    if spec.kind == "generated-title":
        body = render_title_page()
        title = spec.title
    elif spec.kind == "html":
        title, body = render_html_document(spec.source, spec.title, link_map)
    elif spec.kind == "markdown":
        title, body = render_markdown_document(spec.source, spec.title, link_map)
    elif spec.kind == "txt":
        title, body = render_text_document(spec.source, spec.title, link_map)
    else:
        raise ValueError(f"Unsupported document kind: {spec.kind}")

    return {
        "output_name": spec.output_name,
        "title": title,
        "body": wrap_xhtml(title, body),
        "section_label": spec.section_label,
    }


def render_title_page() -> str:
    return f"""
<section class="hero">
  <h1>{html.escape(BOOK_TITLE)}</h1>
  <p>Учебный курс в формате EPUB, собранный из материалов репозитория.</p>
  <div class="meta">
    <span class="badge">11 глав</span>
    <span class="badge">Лабораторные работы</span>
    <span class="badge">Markmap-карты</span>
    <span class="badge">Итоговая проверка</span>
  </div>
</section>
<section class="section">
  <h2>Состав книги</h2>
  <ul>
    <li>введение и программа курса;</li>
    <li>основной текст из 11 глав;</li>
    <li>описание учебного стенда <code>shop-demo</code>;</li>
    <li>листы лабораторных работ;</li>
    <li>mind-map карты тем;</li>
    <li>шаблон итоговой проверки.</li>
  </ul>
</section>
""".strip()


def render_html_document(source: Path, fallback_title: str, link_map: dict[str, str]) -> tuple[str, str]:
    soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html.parser")
    page = soup.select_one("div.page") or soup.body or soup

    for selector in (".toc", ".chapter-nav", ".button-row"):
        for node in page.select(selector):
            node.decompose()

    title = fallback_title
    heading = page.select_one("h1")
    if heading and heading.get_text(strip=True):
        title = heading.get_text(" ", strip=True)

    rewrite_links(page, source, link_map)

    content_parts: list[str] = []
    for child in page.children:
        if getattr(child, "name", None):
            content_parts.append(str(child))

    return title, "\n".join(content_parts)


def render_markdown_document(source: Path, fallback_title: str, link_map: dict[str, str]) -> tuple[str, str]:
    raw = source.read_text(encoding="utf-8")
    title = extract_markdown_title(raw) or fallback_title
    body_html = MARKDOWN_RENDERER(raw)
    soup = BeautifulSoup(body_html, "html.parser")
    rewrite_links(soup, source, link_map)
    return title, str(soup)


def render_text_document(source: Path, fallback_title: str, link_map: dict[str, str]) -> tuple[str, str]:
    raw = source.read_text(encoding="utf-8")
    title, markdown_text = convert_program_text_to_markdown(raw, fallback_title)
    body_html = MARKDOWN_RENDERER(markdown_text)
    soup = BeautifulSoup(body_html, "html.parser")
    rewrite_links(soup, source, link_map)
    return title, str(soup)


def extract_markdown_title(raw: str) -> str | None:
    match = re.search(r"^\s*#\s+(.+?)\s*$", raw, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def convert_program_text_to_markdown(raw: str, fallback_title: str) -> tuple[str, str]:
    lines = raw.splitlines()
    converted: list[str] = []
    title = fallback_title

    for line in lines:
        stripped = line.strip()
        if not stripped:
            converted.append("")
            continue

        if stripped.startswith("Курс: "):
            title = stripped.replace("Курс: ", "", 1).strip()
            converted.append(f"# {title}")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            converted.append(f"## {stripped}")
            continue

        if stripped in PROGRAM_SECTION_HEADINGS:
            converted.append(f"## {stripped}")
            continue

        converted.append(line)

    return title, "\n".join(converted)


def rewrite_links(fragment: BeautifulSoup, source: Path, link_map: dict[str, str]) -> None:
    for anchor in fragment.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        if href.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href):
            continue

        target_path, hash_suffix = split_href(href)
        normalized = normalize_repo_relative(source, target_path)
        if normalized and normalized in link_map:
            anchor["href"] = link_map[normalized] + hash_suffix
        else:
            anchor.unwrap()


def split_href(href: str) -> tuple[str, str]:
    if "#" in href:
        path_part, anchor = href.split("#", 1)
        return path_part, f"#{anchor}"
    return href, ""


def normalize_repo_relative(source: Path, href_path: str) -> str | None:
    try:
        resolved = (source.parent / href_path).resolve()
        relative = resolved.relative_to(REPO_ROOT.resolve())
    except Exception:
        return None
    return relative.as_posix()


def wrap_xhtml(title: str, body_html: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{BOOK_LANGUAGE}" lang="{BOOK_LANGUAGE}">
  <head>
    <meta charset="utf-8"/>
    <title>{escape(title)}</title>
    <link rel="stylesheet" type="text/css" href="../styles/epub.css"/>
  </head>
  <body>
{body_html}
  </body>
</html>
"""


def write_rendered_documents(rendered_docs: list[dict[str, str]]) -> None:
    for doc in rendered_docs:
        target = BUILD_DIR / "OEBPS" / "text" / doc["output_name"]
        target.write_text(doc["body"], encoding="utf-8")


def write_nav(rendered_docs: list[dict[str, str]]) -> None:
    sections = group_docs_by_section(rendered_docs)
    nav_items = []
    for section, docs in sections.items():
        nested = "\n".join(
            f'          <li><a href="text/{escape(doc["output_name"])}">{escape(doc["title"])}</a></li>'
            for doc in docs
        )
        nav_items.append(
            f"""      <li>{escape(section)}
        <ol>
{nested}
        </ol>
      </li>"""
        )

    nav_html = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{BOOK_LANGUAGE}" lang="{BOOK_LANGUAGE}">
  <head>
    <meta charset="utf-8"/>
    <title>Содержание</title>
    <link rel="stylesheet" type="text/css" href="styles/epub.css"/>
  </head>
  <body>
    <nav epub:type="toc" id="toc" xmlns:epub="http://www.idpf.org/2007/ops">
      <h1>Содержание</h1>
      <ol>
{chr(10).join(nav_items)}
      </ol>
    </nav>
  </body>
</html>
"""
    (BUILD_DIR / "OEBPS" / "nav.xhtml").write_text(nav_html, encoding="utf-8")


def write_ncx(rendered_docs: list[dict[str, str]]) -> None:
    nav_points = []
    for index, doc in enumerate(rendered_docs, start=1):
        nav_points.append(
            f"""    <navPoint id="navPoint-{index}" playOrder="{index}">
      <navLabel><text>{escape(doc["title"])}</text></navLabel>
      <content src="text/{escape(doc["output_name"])}"/>
    </navPoint>"""
        )

    ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{BOOK_IDENTIFIER}"/>
  </head>
  <docTitle>
    <text>{escape(BOOK_TITLE)}</text>
  </docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>
"""
    (BUILD_DIR / "OEBPS" / "toc.ncx").write_text(ncx, encoding="utf-8")


def write_package(rendered_docs: list[dict[str, str]]) -> None:
    manifest_items = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="css" href="styles/epub.css" media-type="text/css"/>',
    ]
    spine_items = ['<itemref idref="doc-0"/>']

    for index, doc in enumerate(rendered_docs):
        manifest_items.append(
            f'<item id="doc-{index}" href="text/{escape(doc["output_name"])}" media-type="application/xhtml+xml"/>'
        )
        if index != 0:
            spine_items.append(f'<itemref idref="doc-{index}"/>')

    package_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="bookid" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{escape(BOOK_IDENTIFIER)}</dc:identifier>
    <dc:title>{escape(BOOK_TITLE)}</dc:title>
    <dc:language>{BOOK_LANGUAGE}</dc:language>
    <dc:creator>{escape(BOOK_CREATOR)}</dc:creator>
  </metadata>
  <manifest>
    {"".join(f"{chr(10)}    {item}" for item in manifest_items)}
  </manifest>
  <spine toc="ncx">
    {"".join(f"{chr(10)}    {item}" for item in spine_items)}
  </spine>
</package>
"""
    (BUILD_DIR / "OEBPS" / "package.opf").write_text(package_opf, encoding="utf-8")


def build_epub_archive() -> None:
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    with zipfile.ZipFile(OUTPUT_FILE, "w") as epub:
        epub.write(BUILD_DIR / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted((BUILD_DIR / "META-INF").rglob("*")):
            if path.is_file():
                epub.write(path, path.relative_to(BUILD_DIR).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
        for path in sorted((BUILD_DIR / "OEBPS").rglob("*")):
            if path.is_file():
                epub.write(path, path.relative_to(BUILD_DIR).as_posix(), compress_type=zipfile.ZIP_DEFLATED)


def group_docs_by_section(rendered_docs: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for doc in rendered_docs:
        grouped.setdefault(doc["section_label"], []).append(doc)
    return grouped


if __name__ == "__main__":
    main()
