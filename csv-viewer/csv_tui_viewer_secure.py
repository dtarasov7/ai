#!/usr/bin/env python3
"""
CSV TUI Viewer - безопасный просмотрщик больших CSV файлов.
Поддерживает ленивую загрузку, поиск, фильтрацию полей.
"""

import curses
import csv
import os
import re
import signal
import sys
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Dict, Set, Any, Tuple


class SecurityError(Exception):
    """Ошибка безопасности."""
    pass


class TimeoutError(Exception):
    """Превышено время выполнения операции."""
    pass


def validate_file_path(filepath: str) -> Path:
    """
    Валидация пути к файлу с проверками безопасности.
    Запрещает чтение псевдо-устройств и опасных путей.
    """
    try:
        path = Path(filepath).resolve()
    except (OSError, RuntimeError) as e:
        raise SecurityError(f"Невалидный путь: {e}")

    if not path.exists():
        raise SecurityError(f"Файл не существует: {path}")

    if not path.is_file():
        raise SecurityError(f"Не является обычным файлом: {path}")

    # Запрет чтения системных псевдо-устройств
    forbidden_prefixes = ('/dev/', '/proc/', '/sys/')
    path_str = str(path)
    for prefix in forbidden_prefixes:
        if path_str.startswith(prefix):
            raise SecurityError(f"Запрещено чтение из {prefix}: {path}")

    return path


def safe_regex_compile(pattern_str: str, timeout: int = 2):
    """
    Безопасная компиляция regex с таймаутом (защита от ReDoS).
    При ошибке или таймауте возвращает None.
    """
    if not pattern_str:
        return None

    def timeout_handler(signum, frame):
        raise TimeoutError("Regex compilation timeout")

    # Таймаут работает только на Unix-системах
    if hasattr(signal, 'SIGALRM'):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)

    try:
        compiled = re.compile(pattern_str, re.IGNORECASE)
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        return compiled
    except (re.error, TimeoutError):
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        return None
    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, old_handler)


def safe_regex_search(pattern, text: str, timeout: int = 2) -> bool:
    """
    Безопасный поиск по regex с таймаутом и обрезкой длинных строк.
    """
    # Обрезаем слишком длинные строки
    max_len = 10000
    if len(text) > max_len:
        text = text[:max_len]

    def timeout_handler(signum, frame):
        raise TimeoutError("Regex search timeout")

    if hasattr(signal, 'SIGALRM'):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)

    try:
        result = pattern.search(text) is not None
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        return result
    except TimeoutError:
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        return False
    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, old_handler)


class LRUCache:
    """LRU кэш для CSV записей."""

    def __init__(self, capacity: int = 200):
        self.capacity = capacity
        self.cache: OrderedDict[int, Dict[str, str]] = OrderedDict()

    def get(self, key: int) -> Optional[Dict[str, str]]:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: int, value: Dict[str, str]):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)


class CsvNode:
    """Узел CSV записи с ленивой загрузкой."""

    def __init__(self, row_number: int, loader):
        self.row_number = row_number
        self.loader = loader
        self._data: Optional[Dict[str, str]] = None

    def get_data(self) -> Dict[str, str]:
        """Получить данные записи (из кэша или загрузить)."""
        if self._data is None:
            self._data = self.loader.load_row(self.row_number)
        return self._data


class CsvLoader:
    """Ленивая загрузка CSV с защитой от CSV Bomb."""

    MAX_FIELD_SIZE = 1024 * 1024  # 1 MB на поле
    MAX_FIELDS = 1000  # Максимум полей

    def __init__(self, filepath: Path, delimiter: str = ',', has_header: bool = True):
        self.filepath = filepath
        self.delimiter = delimiter
        self.has_header = has_header
        self.cache = LRUCache(capacity=200)
        self.headers: List[str] = []
        self.total_rows = 0
        self.rows_loaded = 0
        self._counted = False

        # Устанавливаем лимит размера поля глобально для модуля csv
        csv.field_size_limit(self.MAX_FIELD_SIZE)

        self._load_headers()

    def _normalize_value(self, value: str) -> str:
        """
        Нормализует значение: заменяет переносы строк на пробелы.
        Это нужно для склейки многострочных полей в одну строку.
        """
        # Заменяем все виды переносов строк на пробелы
        value = value.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
        # Убираем множественные пробелы
        value = ' '.join(value.split())
        return value

    def _load_headers(self):
        """Загрузить заголовки CSV или сгенерировать их."""
        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f, delimiter=self.delimiter, quotechar='"')
            try:
                first_row = next(reader)
                if len(first_row) > self.MAX_FIELDS:
                    raise SecurityError(f"Слишком много полей: {len(first_row)} > {self.MAX_FIELDS}")

                if self.has_header:
                    # Нормализуем заголовки (на случай если там переносы строк)
                    self.headers = [self._normalize_value(h) for h in first_row]
                else:
                    # Генерируем имена полей: field1, field2, ...
                    self.headers = [f"field{i+1}" for i in range(len(first_row))]
            except StopIteration:
                self.headers = []

    def load_row(self, row_number: int) -> Dict[str, str]:
        """Загрузить конкретную строку из файла."""
        cached = self.cache.get(row_number)
        if cached is not None:
            return cached

        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f, delimiter=self.delimiter, quotechar='"')

            # Если есть заголовок, пропускаем первую строку
            if self.has_header:
                try:
                    next(reader)
                except StopIteration:
                    return {}

            for idx, row in enumerate(reader):
                if idx == row_number:
                    if len(row) > self.MAX_FIELDS:
                        raise SecurityError(f"Слишком много полей в строке {row_number}")

                    # Дополняем недостающие поля
                    while len(row) < len(self.headers):
                        row.append('')

                    # Нормализуем значения (склеиваем многострочные поля)
                    normalized_row = [self._normalize_value(val) for val in row[:len(self.headers)]]

                    data = dict(zip(self.headers, normalized_row))
                    self.cache.put(row_number, data)
                    return data

        return {}

    def count_rows(self) -> int:
        """Подсчитать общее количество строк."""
        if self._counted:
            return self.total_rows

        with open(self.filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f, delimiter=self.delimiter, quotechar='"')

            # Если есть заголовок, пропускаем его
            if self.has_header:
                try:
                    next(reader)
                except StopIteration:
                    self.total_rows = 0
                    self._counted = True
                    return 0

            count = sum(1 for _ in reader)
            self.total_rows = count
            self._counted = True

        return self.total_rows


class CsvViewer:
    """Главный класс TUI просмотрщика CSV."""

    def __init__(self, stdscr, filepath: Path, delimiter: str, has_header: bool):
        self.stdscr = stdscr
        self.filepath = filepath
        self.loader = CsvLoader(filepath, delimiter, has_header)

        # Режимы отображения
        self.table_mode = True  # True - таблица, False - карточка

        # Данные
        self.nodes: List[CsvNode] = []
        # Используем список вместо set для сохранения порядка полей
        self.filtered_fields: List[str] = list(self.loader.headers)
        self.current_row = 0
        self.current_col = 0  # Для навигации по столбцам в таблице

        # Поиск
        self.search_results: List[int] = []
        self.search_index = -1
        self.search_fields: Set[str] = set()

        # Отображение
        self.top_row = 0
        self.left_col = 0  # Горизонтальный скролл (в символах)
        self.top_field = 0  # Вертикальный скролл для полей в Card режиме
        self.col_widths: Dict[str, int] = {}
        self.manual_col_widths: Dict[str, int] = {}

        # Статус
        self.status_message = ""
        self.filter_active = False

        # Для предотвращения мерцания - кэшируем предыдущее состояние
        self._prev_status_line = ""
        self._needs_redraw = True

        # Инициализация curses
        curses.curs_set(0)
        curses.use_default_colors()

        # Инициализируем цветовые пары
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, -1)  # Зеленый для >

        self.stdscr.keypad(True)
        self.stdscr.timeout(100)

        # Предзагрузка
        self._preload_initial()

    def _preload_initial(self):
        """Предзагрузить начальные записи."""
        height = self.stdscr.getmaxyx()[0]
        initial_load = max(height + 10, 20)
        self._ensure_loaded(initial_load - 1)

    def _ensure_loaded(self, target_row: int):
        """Убедиться, что записи до target_row загружены."""
        while len(self.nodes) <= target_row:
            row_num = len(self.nodes)
            node = CsvNode(row_num, self.loader)

            # Проверяем, есть ли данные
            try:
                data = node.get_data()
                if not data or all(v == '' for v in data.values()):
                    # Пустая строка - конец файла
                    break
            except Exception:
                break

            self.nodes.append(node)
            self.loader.rows_loaded += 1

    def _calculate_col_widths(self):
        """Вычислить ширину столбцов автоматически."""
        max_screen_width = self.stdscr.getmaxyx()[1]
        max_col_width = max_screen_width // 2

        for field in self.filtered_fields:
            if field in self.manual_col_widths:
                continue

            width = len(field) + 2
            # Проверяем несколько видимых записей
            for i in range(self.top_row, min(self.top_row + 10, len(self.nodes))):
                if i < len(self.nodes):
                    data = self.nodes[i].get_data()
                    value = data.get(field, '')
                    width = max(width, len(str(value)) + 2)

            self.col_widths[field] = min(width, max_col_width)

    def run(self):
        """Главный цикл приложения."""
        while True:
            if self._needs_redraw:
                self._draw()
                self._needs_redraw = False

            key = self.stdscr.getch()

            if key == -1:
                continue

            if key in (ord('q'), ord('Q'), 27):  # q, Q, Esc
                # Запрашиваем подтверждение выхода
                if self._confirm_quit():
                    break
                else:
                    self._needs_redraw = True
                    continue

            self._handle_key(key)
            self._needs_redraw = True

    def _confirm_quit(self) -> bool:
        """Подтверждение выхода из приложения."""
        height, width = self.stdscr.getmaxyx()
        prompt = "Really quit? (y/n): "
        y = height - 1

        # Отображаем промпт
        self.stdscr.addstr(y, 0, " " * (width - 1))
        self.stdscr.addstr(y, 0, prompt, curses.A_BOLD)
        self.stdscr.refresh()

        # Ждем ответа
        while True:
            key = self.stdscr.getch()
            if key in (ord('y'), ord('Y')):
                return True
            elif key in (ord('n'), ord('N'), 27):  # n, N, Esc
                return False

    def _draw(self):
        """Отрисовка экрана."""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        # Верхняя строка: статус (обновляем только если изменилась)
        total = len(self.nodes) if len(self.nodes) > 0 else 0
        filter_ind = " [FILTER]" if self.filter_active else ""
        status = f"{self.filepath.name} | Row {self.current_row + 1}/{total}{filter_ind}"

        if status != self._prev_status_line:
            self._prev_status_line = status

        self.stdscr.addstr(0, 0, status[:width-1], curses.A_REVERSE)

        if self.table_mode:
            self._draw_table(height, width)
        else:
            self._draw_card(height, width)

        # Нижние строки: подсказки
        help_line1 = "q:Quit | Tab:Mode | s:Search | F:GlobalSearch | f:Filter | g:Goto"
        help_line2 = "Home/End | PgUp/PgDn | Arrows | Enter:View | w:SetWidth | Shift+Arrows:Scroll"

        if height > 3:
            self.stdscr.addstr(height - 2, 0, help_line1[:width-1])
        if height > 2:
            self.stdscr.addstr(height - 1, 0, help_line2[:width-1])

        # Сообщение статуса
        if self.status_message and height > 4:
            msg_y = height - 3
            self.stdscr.addstr(msg_y, 0, self.status_message[:width-1], curses.A_BOLD)

        self.stdscr.refresh()

    def _draw_table(self, height: int, width: int):
        """Отрисовка таблицы."""
        if not self.filtered_fields:
            self.stdscr.addstr(2, 0, "No fields selected")
            return

        self._calculate_col_widths()

        # Заголовок таблицы
        x = 0
        for idx, field in enumerate(self.filtered_fields):
            col_w = self.manual_col_widths.get(field, self.col_widths.get(field, 15))

            # Применяем горизонтальный скролл
            if x - self.left_col >= 0 and x - self.left_col < width:
                display = field[:col_w].ljust(col_w)
                start_x = max(0, x - self.left_col)
                attr = curses.A_REVERSE | curses.A_BOLD if idx == self.current_col else curses.A_REVERSE
                try:
                    self.stdscr.addstr(1, start_x, display[:width - start_x], attr)
                except curses.error:
                    pass
            x += col_w + 1

        # Строки данных
        visible_height = height - 4
        for row_idx in range(self.top_row, min(self.top_row + visible_height, len(self.nodes))):
            if row_idx >= len(self.nodes):
                break

            y = 2 + (row_idx - self.top_row)
            if y >= height - 2:
                break

            data = self.nodes[row_idx].get_data()
            x = 0
            for idx, field in enumerate(self.filtered_fields):
                col_w = self.manual_col_widths.get(field, self.col_widths.get(field, 15))
                full_value = str(data.get(field, ''))

                # Обрезаем значение и добавляем индикатор если обрезано
                is_truncated = len(full_value) > col_w
                if is_truncated:
                    value = full_value[:col_w-1]
                else:
                    value = full_value.ljust(col_w)

                # Применяем горизонтальный скролл
                if x - self.left_col >= 0 and x - self.left_col < width:
                    start_x = max(0, x - self.left_col)
                    attr = curses.A_REVERSE if row_idx == self.current_row else curses.A_NORMAL

                    try:
                        # Выводим основное значение
                        display_value = value[:width - start_x]
                        self.stdscr.addstr(y, start_x, display_value, attr)

                        # Если обрезано, добавляем зеленый > в конце
                        if is_truncated:
                            # Вычисляем позицию для >
                            value_end_x = start_x + min(len(value), width - start_x - 1)
                            if value_end_x < width - 1:
                                marker_attr = attr | curses.color_pair(1) | curses.A_BOLD
                                self.stdscr.addstr(y, value_end_x, '>', marker_attr)
                    except curses.error:
                        pass

                x += col_w + 1

    def _draw_card(self, height: int, width: int):
        """Отрисовка одной записи (карточка) с вертикальным скроллом."""
        if self.current_row >= len(self.nodes):
            return

        data = self.nodes[self.current_row].get_data()

        # Используем filtered_fields (список) для сохранения порядка
        fields = self.filtered_fields if self.filtered_fields else list(self.loader.headers)

        visible_height = height - 4

        # Индикатор скролла вверх
        if self.top_field > 0:
            try:
                self.stdscr.addstr(2, width - 2, '^', curses.A_BOLD | curses.color_pair(1))
            except curses.error:
                pass

        # Отображаем поля
        y = 2
        for field_idx in range(self.top_field, min(self.top_field + visible_height, len(fields))):
            if y >= height - 2:
                break

            field = fields[field_idx]
            value = data.get(field, '')

            # Обрезаем длинные значения
            max_val_len = width - len(field) - 4
            is_truncated = len(value) > max_val_len
            if is_truncated:
                value = value[:max_val_len]

            line = f"{field}: {value}"
            try:
                self.stdscr.addstr(y, 0, line[:width-1])

                # Добавляем зеленый > если обрезано
                if is_truncated and len(line) < width - 1:
                    marker_attr = curses.color_pair(1) | curses.A_BOLD
                    self.stdscr.addstr(y, min(len(line), width - 2), '>', marker_attr)
            except curses.error:
                pass
            y += 1

        # Индикатор скролла вниз
        if self.top_field + visible_height < len(fields):
            try:
                self.stdscr.addstr(height - 3, width - 2, 'v', curses.A_BOLD | curses.color_pair(1))
            except curses.error:
                pass

    def _handle_key(self, key: int):
        """Обработка нажатий клавиш."""
        height, width = self.stdscr.getmaxyx()

        # Переключение режима (Tab)
        if key == 9:  # Tab
            self.table_mode = not self.table_mode
            self.top_field = 0  # Сбрасываем скролл при переключении
            self.status_message = f"Mode: {'Table' if self.table_mode else 'Card'}"
            return

        # Shift+Up (337) и Shift+Down (336) - скролл полей в Card режиме
        if key == curses.KEY_SR or key == 337:  # Shift+Up
            if not self.table_mode:
                if self.top_field > 0:
                    self.top_field -= 1
        elif key == curses.KEY_SF or key == 336:  # Shift+Down
            if not self.table_mode:
                fields = self.filtered_fields if self.filtered_fields else list(self.loader.headers)
                visible_height = height - 4
                if self.top_field + visible_height < len(fields):
                    self.top_field += 1

        # Обычная навигация
        elif key == curses.KEY_DOWN:
            self._move_row(1)
        elif key == curses.KEY_UP:
            self._move_row(-1)
        elif key == curses.KEY_RIGHT:
            if self.table_mode:
                # Перемещение по столбцам
                old_col = self.current_col
                self.current_col = min(self.current_col + 1, len(self.filtered_fields) - 1)

                # Обновляем горизонтальный скролл
                if self.current_col != old_col:
                    self._adjust_horizontal_scroll(width)
            else:
                # В Card режиме - переход к следующей записи
                self._move_row(1)
        elif key == curses.KEY_LEFT:
            if self.table_mode:
                old_col = self.current_col
                self.current_col = max(0, self.current_col - 1)

                # Обновляем горизонтальный скролл
                if self.current_col != old_col:
                    self._adjust_horizontal_scroll(width)
            else:
                # В Card режиме - переход к предыдущей записи
                self._move_row(-1)
        elif key == curses.KEY_PPAGE:  # PgUp
            if self.table_mode:
                self._move_row(-(height - 4))
            else:
                # Скролл полей на страницу вверх
                visible_height = height - 4
                self.top_field = max(0, self.top_field - visible_height)
        elif key == curses.KEY_NPAGE:  # PgDn
            if self.table_mode:
                self._move_row(height - 4)
            else:
                # Скролл полей на страницу вниз
                fields = self.filtered_fields if self.filtered_fields else list(self.loader.headers)
                visible_height = height - 4
                self.top_field = min(len(fields) - visible_height, self.top_field + visible_height)
                self.top_field = max(0, self.top_field)
        elif key == curses.KEY_HOME:
            if self.table_mode:
                self.current_row = 0
                self.top_row = 0
            else:
                # Скролл полей в начало
                self.top_field = 0
        elif key == curses.KEY_END:
            if self.table_mode:
                # Досчитываем все строки
                total = self.loader.count_rows()
                self._ensure_loaded(total)

                if len(self.nodes) > 0:
                    self.current_row = len(self.nodes) - 1
                    self.top_row = max(0, self.current_row - (height - 4))
            else:
                # Скролл полей в конец
                fields = self.filtered_fields if self.filtered_fields else list(self.loader.headers)
                visible_height = height - 4
                self.top_field = max(0, len(fields) - visible_height)

        # Просмотр полного значения поля
        elif key == 10 or key == curses.KEY_ENTER:
            if self.table_mode:
                self._view_field()

        # Переход по номеру
        elif key == ord('g'):
            self._goto_row()

        # Поиск
        elif key == ord('s'):
            self._search_current_field()
        elif key == ord('F'):
            self._global_search()
        elif key == ord('n'):
            self._next_search_result()
        elif key == ord('p'):
            self._prev_search_result()

        # Фильтрация
        elif key == ord('f'):
            self._filter_dialog()

        # Установка ширины столбца
        elif key == ord('w'):
            self._set_column_width()

        self._adjust_viewport(height)

    def _adjust_horizontal_scroll(self, width: int):
        """Корректировка горизонтального скролла."""
        if not self.filtered_fields:
            return

        # Вычисляем X позицию текущего столбца
        x = 0
        for idx, field in enumerate(self.filtered_fields):
            col_w = self.manual_col_widths.get(field, self.col_widths.get(field, 15))

            if idx == self.current_col:
                # Если столбец за правой границей - скроллим вправо
                if x - self.left_col + col_w > width:
                    self.left_col = x - width + col_w + 10

                # Если столбец за левой границей - скроллим влево
                if x < self.left_col:
                    self.left_col = max(0, x - 10)

                break

            x += col_w + 1

    def _view_field(self):
        """Просмотр полного значения текущего поля."""
        if self.current_row >= len(self.nodes):
            return

        if not self.filtered_fields or self.current_col >= len(self.filtered_fields):
            return

        field = self.filtered_fields[self.current_col]
        data = self.nodes[self.current_row].get_data()
        value = str(data.get(field, ''))

        if not value:
            self.status_message = "Field is empty"
            return

        # Создаем диалоговое окно
        height, width = self.stdscr.getmaxyx()

        # Размеры окна
        win_height = height - 6
        win_width = width - 10
        win_y = 3
        win_x = 5

        # Создаем окно
        win = curses.newwin(win_height, win_width, win_y, win_x)
        win.box()

        # Заголовок
        title = f" {field} "
        win.addstr(0, 2, title[:win_width-4], curses.A_BOLD)

        # Разбиваем значение на строки по ширине окна
        content_width = win_width - 4
        lines = []
        current_line = ""

        for char in value:
            # Пропускаем символы переноса строки - они уже обработаны при загрузке
            if char in ('\r', '\n'):
                continue

            if len(current_line) >= content_width:
                lines.append(current_line)
                current_line = char
            else:
                current_line += char

        if current_line:
            lines.append(current_line)

        # Отображаем строки
        display_height = win_height - 3
        scroll_pos = 0

        while True:
            # Очищаем область содержимого
            for y in range(1, win_height - 1):
                try:
                    win.addstr(y, 1, " " * (win_width - 2))
                except curses.error:
                    pass

            # Выводим строки
            for i in range(display_height):
                line_idx = scroll_pos + i
                if line_idx < len(lines):
                    try:
                        win.addstr(i + 1, 2, lines[line_idx][:content_width])
                    except curses.error:
                        pass

            # Подсказка
            hint = " Press Esc/Enter to close, Up/Down to scroll "
            try:
                win.addstr(win_height - 1, 2, hint[:win_width-4])
            except curses.error:
                pass

            win.refresh()

            key = win.getch()

            if key == 27 or key == 10 or key == curses.KEY_ENTER:  # Esc or Enter
                break
            elif key == curses.KEY_DOWN:
                if scroll_pos + display_height < len(lines):
                    scroll_pos += 1
            elif key == curses.KEY_UP:
                if scroll_pos > 0:
                    scroll_pos -= 1
            elif key == curses.KEY_PPAGE:
                scroll_pos = max(0, scroll_pos - display_height)
            elif key == curses.KEY_NPAGE:
                scroll_pos = min(len(lines) - display_height, scroll_pos + display_height)
                scroll_pos = max(0, scroll_pos)

        # Закрываем окно
        del win
        self.stdscr.touchwin()
        self.stdscr.refresh()

    def _move_row(self, delta: int):
        """Переместить курсор на delta строк."""
        if len(self.nodes) == 0:
            return

        new_row = self.current_row + delta
        new_row = max(0, new_row)

        # Пробуем подгрузить данные, если движемся вперед
        if new_row >= len(self.nodes):
            self._ensure_loaded(new_row)

        # Ограничиваем границами загруженных данных
        max_row = len(self.nodes) - 1
        if max_row >= 0:
            new_row = min(new_row, max_row)
            self.current_row = new_row

    def _adjust_viewport(self, height: int):
        """Корректировка видимой области."""
        if len(self.nodes) == 0:
            return

        visible_height = height - 4

        # Вертикальная прокрутка
        if self.current_row < self.top_row:
            self.top_row = self.current_row
        elif self.current_row >= self.top_row + visible_height:
            self.top_row = self.current_row - visible_height + 1

        # Подгрузка при приближении к концу
        if self.current_row >= len(self.nodes) - 5:
            self._ensure_loaded(self.current_row + 5)

    def _goto_row(self):
        """Диалог перехода к строке."""
        row_str = self._input_string("Go to row: ")
        if row_str and row_str.isdigit():
            target = int(row_str) - 1
            if target >= 0:
                # Пробуем загрузить до нужной строки
                self._ensure_loaded(target)

                max_row = len(self.nodes) - 1
                if max_row >= 0 and target <= max_row:
                    self.current_row = target
                    self.status_message = f"Jumped to row {target + 1}"
                else:
                    self.status_message = f"Row {target + 1} not found (max: {max_row + 1})"

    def _search_current_field(self):
        """Поиск по текущему полю."""
        if not self.filtered_fields:
            self.status_message = "No fields to search"
            return

        if self.table_mode and self.current_col < len(self.filtered_fields):
            field = self.filtered_fields[self.current_col]
        else:
            field = self.filtered_fields[0]

        pattern_str = self._input_string(f"Search in '{field}' (regex): ")
        if not pattern_str:
            return

        pattern = safe_regex_compile(pattern_str)
        use_regex = pattern is not None

        self.search_results = []
        self.search_fields = {field}

        # Загружаем все записи для поиска
        total = self.loader.count_rows()
        self._ensure_loaded(total)

        for idx, node in enumerate(self.nodes):
            data = node.get_data()
            value = str(data.get(field, ''))

            if use_regex:
                if safe_regex_search(pattern, value):
                    self.search_results.append(idx)
            else:
                if pattern_str.lower() in value.lower():
                    self.search_results.append(idx)

        if self.search_results:
            self.search_index = 0
            self.current_row = self.search_results[0]
            self.status_message = f"Found {len(self.search_results)} results. Use n/p to navigate."
        else:
            self.status_message = "No results found"
            self.search_index = -1

    def _global_search(self):
        """Глобальный поиск по всем полям."""
        pattern_str = self._input_string("Global search (regex): ")
        if not pattern_str:
            return

        pattern = safe_regex_compile(pattern_str)
        use_regex = pattern is not None

        self.search_results = []
        self.search_fields = set()

        total = self.loader.count_rows()
        self._ensure_loaded(total)

        for idx, node in enumerate(self.nodes):
            data = node.get_data()
            found_in_fields = set()

            for field, value in data.items():
                value_str = str(value)

                if use_regex:
                    if safe_regex_search(pattern, value_str):
                        found_in_fields.add(field)
                else:
                    if pattern_str.lower() in value_str.lower():
                        found_in_fields.add(field)

            if found_in_fields:
                self.search_results.append(idx)
                self.search_fields.update(found_in_fields)

        if self.search_results:
            # Автоматическая фильтрация - сохраняем порядок полей
            self.filtered_fields = [f for f in self.loader.headers if f in self.search_fields]
            self.filter_active = True

            self.search_index = 0
            self.current_row = self.search_results[0]
            self.status_message = f"Found {len(self.search_results)} results in {len(self.search_fields)} fields"
        else:
            self.status_message = "No results found"
            self.search_index = -1

    def _next_search_result(self):
        """Следующий результат поиска."""
        if not self.search_results:
            self.status_message = "No active search"
            return

        self.search_index = (self.search_index + 1) % len(self.search_results)
        self.current_row = self.search_results[self.search_index]
        self.status_message = f"Result {self.search_index + 1}/{len(self.search_results)}"

    def _prev_search_result(self):
        """Предыдущий результат поиска."""
        if not self.search_results:
            self.status_message = "No active search"
            return

        self.search_index = (self.search_index - 1) % len(self.search_results)
        self.current_row = self.search_results[self.search_index]
        self.status_message = f"Result {self.search_index + 1}/{len(self.search_results)}"

    def _filter_dialog(self):
        """Диалог выбора полей для фильтрации."""
        all_fields = self.loader.headers
        # Используем set для быстрой проверки, но сохраняем порядок через all_fields
        selected = set(self.filtered_fields)

        cursor = 0

        # Кэшируем статусную строку диалога
        dialog_status = "Select fields (Space:toggle, Enter:apply, Esc:cancel, +/-:all/none, *:invert)"

        while True:
            height, width = self.stdscr.getmaxyx()

            # Очищаем только область содержимого, не весь экран
            for y in range(height):
                try:
                    self.stdscr.addstr(y, 0, " " * (width - 1))
                except curses.error:
                    pass

            # Статусная строка - рисуем один раз
            self.stdscr.addstr(0, 0, dialog_status[:width-1], curses.A_REVERSE)

            visible_height = height - 3
            top_offset = max(0, cursor - visible_height + 1)

            for idx in range(top_offset, min(top_offset + visible_height, len(all_fields))):
                field = all_fields[idx]
                check = "[X]" if field in selected else "[ ]"
                line = f"{check} {field}"

                y = 1 + idx - top_offset
                attr = curses.A_REVERSE if idx == cursor else curses.A_NORMAL
                try:
                    self.stdscr.addstr(y, 0, line[:width-1], attr)
                except curses.error:
                    pass

            self.stdscr.refresh()
            key = self.stdscr.getch()

            if key == 27:  # Esc
                break
            elif key == 10 or key == curses.KEY_ENTER:  # Enter
                # Сохраняем порядок полей из all_fields
                if selected:
                    self.filtered_fields = [f for f in all_fields if f in selected]
                else:
                    self.filtered_fields = list(all_fields)
                self.filter_active = len(selected) < len(all_fields)
                self.status_message = f"Filter applied: {len(self.filtered_fields)} fields"
                break
            elif key == ord(' '):
                field = all_fields[cursor]
                if field in selected:
                    selected.remove(field)
                else:
                    selected.add(field)
            elif key == ord('+') or key == 464:  # + на основной и дополнительной клавиатуре
                selected = set(all_fields)
            elif key == ord('-') or key == 465:  # - на основной и дополнительной клавиатуре
                selected = set()
                self.filter_active = False
            elif key == ord('*') or key == 463:  # * (инвертирование)
                # Инвертируем выбор
                selected = set(all_fields) - selected
            elif key == curses.KEY_DOWN:
                cursor = min(cursor + 1, len(all_fields) - 1)
            elif key == curses.KEY_UP:
                cursor = max(0, cursor - 1)

    def _set_column_width(self):
        """Установить ширину текущего столбца."""
        if not self.table_mode or not self.filtered_fields:
            return

        if self.current_col >= len(self.filtered_fields):
            return

        field = self.filtered_fields[self.current_col]

        # Получаем текущую ширину
        current_width = self.manual_col_widths.get(field, self.col_widths.get(field, 15))

        # Максимальная ширина - 2/3 экрана
        height, width = self.stdscr.getmaxyx()
        max_width = (width * 2) // 3

        width_str = self._input_string(f"Width for '{field}' (current: {current_width}, max: {max_width}): ")

        if width_str and width_str.isdigit():
            new_width = int(width_str)
            if new_width > 0:
                # Ограничиваем максимальной шириной
                if new_width > max_width:
                    new_width = max_width
                    self.status_message = f"Width limited to {max_width} (2/3 of screen)"
                else:
                    self.status_message = f"Column '{field}' width set to {new_width}"

                self.manual_col_widths[field] = new_width

    def _input_string(self, prompt: str) -> str:
        """Диалог ввода строки."""
        # Отключаем таймаут для корректного ввода
        self.stdscr.timeout(-1)
        curses.echo()
        curses.curs_set(1)

        height, width = self.stdscr.getmaxyx()
        y = height - 1

        # Очищаем строку ввода
        self.stdscr.addstr(y, 0, " " * (width - 1))
        self.stdscr.addstr(y, 0, prompt[:width-1])
        self.stdscr.refresh()

        try:
            # Используем curses.newwin для создания окна ввода
            input_win = curses.newwin(1, width - len(prompt) - 1, y, len(prompt))
            curses.curs_set(1)

            # Очищаем окно ввода
            input_win.clear()
            input_win.refresh()

            # Читаем строку
            result = input_win.getstr(0, 0, width - len(prompt) - 2).decode('utf-8')
        except KeyboardInterrupt:
            result = ""
        except Exception:
            result = ""
        finally:
            curses.noecho()
            curses.curs_set(0)
            # Возвращаем таймаут
            self.stdscr.timeout(100)

        return result.strip()


def main():
    """Точка входа."""
    if len(sys.argv) < 2:
        print("Usage: python csv_tui_viewer_secure.py <file.csv> [delimiter] [--no-header]")
        print("Example: python csv_tui_viewer_secure.py data.csv")
        print("Example: python csv_tui_viewer_secure.py data.csv ';'")
        print("Example: python csv_tui_viewer_secure.py data.csv ',' --no-header")
        sys.exit(1)

    filepath_str = sys.argv[1]
    delimiter = ','
    has_header = True

    # Парсим аргументы
    for i in range(2, len(sys.argv)):
        arg = sys.argv[i]
        if arg == '--no-header':
            has_header = False
        elif len(arg) == 1 or (len(arg) > 1 and not arg.startswith('-')):
            # Разделитель может быть экранированным, например '\t'
            delimiter = arg.encode().decode('unicode_escape')

    # Валидация пути
    try:
        filepath = validate_file_path(filepath_str)
    except SecurityError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Запуск TUI
    try:
        curses.wrapper(lambda stdscr: CsvViewer(stdscr, filepath, delimiter, has_header).run())
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
