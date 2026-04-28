from __future__ import annotations

import html
import uuid

import build_epub


REPO_ROOT = build_epub.REPO_ROOT


def render_teacher_title_page() -> str:
    return f"""
<section class="hero">
  <h1>{html.escape(build_epub.BOOK_TITLE)}</h1>
  <p>Версия для преподавателя: ключи к самопроверке, ориентиры решений лабораторных работ и эталон итоговой практической работы.</p>
  <div class="meta">
    <span class="badge">Ответы</span>
    <span class="badge">Решения лабораторных</span>
    <span class="badge">Итоговая работа</span>
    <span class="badge">Критерии проверки</span>
  </div>
</section>
<section class="section">
  <h2>Состав книги</h2>
  <ul>
    <li>методика использования преподавательской версии;</li>
    <li>ответы на вопросы для самопроверки;</li>
    <li>решения и допустимые варианты для лабораторных работ;</li>
    <li>эталон итоговой практической работы и шкала проверки.</li>
  </ul>
</section>
""".strip()


def main() -> None:
    build_epub.BUILD_DIR = build_epub.DIST_DIR / "_teacher_epub_build"
    build_epub.OUTPUT_FILE = build_epub.DIST_DIR / "security-kubernetes-deckhouse-course-teacher.epub"
    build_epub.BOOK_TITLE = "Безопасность Kubernetes и Deckhouse Kubernetes Platform. Версия для преподавателя"
    build_epub.BOOK_CREATOR = "DKP Course Materials"
    build_epub.BOOK_IDENTIFIER = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "https://local/c/repos/dkp/security-kubernetes-deckhouse-course-teacher",
        )
    )
    build_epub.DOCS = [
        build_epub.DocSpec(None, "00_title.xhtml", build_epub.BOOK_TITLE, "generated-title", "Титульный лист"),
        build_epub.DocSpec(REPO_ROOT / "teacher" / "index.html", "01_teacher_index.xhtml", "О преподавательской версии", "html", "Введение"),
        build_epub.DocSpec(REPO_ROOT / "teacher" / "README.md", "02_teacher_method.xhtml", "Методика преподавателя", "markdown", "Введение"),
        build_epub.DocSpec(REPO_ROOT / "teacher" / "self_check_answers.md", "03_self_check_answers.xhtml", "Ответы на вопросы для самопроверки", "markdown", "Ключи"),
        build_epub.DocSpec(REPO_ROOT / "teacher" / "lab_solutions.md", "04_lab_solutions.xhtml", "Решения лабораторных работ", "markdown", "Ключи"),
        build_epub.DocSpec(REPO_ROOT / "teacher" / "final_practical_work.md", "05_final_practical_work.xhtml", "Итоговая практическая работа", "markdown", "Итоговая проверка"),
    ]
    build_epub.render_title_page = render_teacher_title_page
    build_epub.main()


if __name__ == "__main__":
    main()
