#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TUI JSON viewer - интерактивный просмотрщик JSON/JSONL файлов.

Возможности:
- Ленивая загрузка больших файлов (миллионы объектов)
- Древовидная навигация с разворачиванием/сворачиванием узлов
- Поиск по полям с regex
- Фильтрация отображаемых полей
- Просмотр полных значений длинных полей
- Переход между объектами с сохранением позиции

Управление:
  ↑↓ / j k      - навигация по узлам
  →← / l        - развернуть/свернуть узел
  Enter         - просмотр полного значения (для листовых узлов)
  a / z         - развернуть/свернуть текущий объект
  A / Z         - развернуть/свернуть ВСЕ объекты
  s             - поиск по текущему полю
  F             - глобальный поиск по всем полям с авто-фильтром
  f             - выбор полей для фильтрации
  n / p         - следующий/предыдущий результат поиска
  g             - переход к объекту по номеру
  Home / End    - первый/последний объект
  PgUp / PgDn   - предыдущий/следующий объект (с сохранением позиции)
  q / Esc       - выход
"""

import sys
import json
import os
import curses
import re
from typing import List, Optional, Tuple, Set


class JsonNode:
    """Узел дерева JSON структуры."""

    def __init__(self, key: str, value: any, parent=None, depth: int = 0, index: int = 0):
        self.key = key              # Имя поля или индекс массива
        self.value = value          # Значение узла
        self.parent = parent        # Ссылка на родительский узел
        self.depth = depth          # Глубина вложенности
        self.expanded = False       # Развернут ли узел
        self.children = None        # Дочерние узлы (создаются лениво)
        self.index = index          # Индекс корневого объекта в файле

    def is_leaf(self) -> bool:
        """Проверка: является ли узел листовым (не dict и не list)."""
        return not isinstance(self.value, (dict, list))

    def build_children(self):
        """Ленивое создание дочерних узлов при первом обращении."""
        if self.children is not None:
            return  # Уже созданы

        self.children = []

        if isinstance(self.value, dict):
            # Для словаря создаем узлы для каждого ключа (сортируем для стабильности)
            for k in sorted(self.value.keys()):
                self.children.append(
                    JsonNode(str(k), self.value[k], self, self.depth + 1)
                )
        elif isinstance(self.value, list):
            # Для массива создаем узлы с индексами [0], [1], ...
            for idx, item in enumerate(self.value):
                self.children.append(
                    JsonNode(f"[{idx}]", item, self, self.depth + 1)
                )

    def toggle(self):
        """Переключение состояния развернут/свернут."""
        if self.is_leaf():
            return  # Листовые узлы не разворачиваются

        if not self.expanded:
            self.build_children()  # Создаем детей при первом разворачивании

        self.expanded = not self.expanded

    def get_root_object(self):
        """Получение корневого объекта (depth=0) для текущего узла."""
        node = self
        while node.parent and node.depth > 0:
            node = node.parent
        return node

    def get_relative_path_with_state(self):
        """
        Получение пути от корневого объекта с состоянием expanded.
        Возвращает: [(key, depth, expanded), ...]
        Используется для навигации между объектами с сохранением позиции.
        """
        path = []
        node = self
        root_obj = self.get_root_object()

        while node != root_obj and node.parent:
            path.append((node.key, node.depth, node.expanded))
            node = node.parent

        return list(reversed(path))  # Путь от корня к узлу

    def expand_all(self):
        """Рекурсивное разворачивание всех потомков."""
        if self.is_leaf():
            return

        self.expanded = True
        if not self.children:
            self.build_children()

        for child in self.children:
            child.expand_all()

    def collapse_all(self):
        """Рекурсивное сворачивание всех потомков."""
        self.expanded = False
        if self.children:
            for child in self.children:
                child.collapse_all()

    def collect_leaf_fields(self) -> Set[str]:
        """
        Сбор всех уникальных имен листовых полей в поддереве.
        Исключает индексы массивов (начинающиеся с '[').
        """
        fields = set()

        def walk(node):
            if node.is_leaf():
                if not node.key.startswith('['):
                    fields.add(node.key)
            else:
                if not node.children:
                    node.build_children()
                for child in node.children:
                    walk(child)

        walk(self)
        return fields


class LazyJsonFile:
    """
    Ленивая загрузка JSON объектов из файла.
    Индексирует позиции объектов без загрузки содержимого.
    Использует LRU-кэш для хранения недавно использованных объектов.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._offsets = []      # Позиции начала каждого объекта в файле (в байтах)
        self._count = 0         # Общее количество объектов
        self._cache = {}        # LRU кэш загруженных объектов
        self._cache_size = 200  # Максимальный размер кэша
        self._build_index()

    def _build_index(self):
        """Построение индекса: определение позиций всех объектов в файле."""
        # Пробуем загрузить как одиночный JSON
        try:
            with open(self.filepath, 'rb') as f:
                data = json.load(f)
                self._offsets.append(0)
                self._cache[0] = data
                self._count = 1
                self._is_single = True
                print(f"Одиночный JSON: 1 объект")
                return
        except json.JSONDecodeError:
            pass

        # Если не получилось - обрабатываем как JSONL (по строке на объект)
        self._is_single = False
        with open(self.filepath, 'rb') as f:
            while True:
                pos = f.tell()  # Запоминаем текущую позицию
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    self._offsets.append(pos)
                    self._count += 1

        print(f"JSONL: {self._count} объектов (индексировано)")

    def __len__(self):
        return self._count

    def __getitem__(self, index: int) -> dict:
        """
        Загрузка объекта по индексу (с кэшированием).
        Если объект в кэше - возвращаем из кэша.
        Иначе загружаем из файла и добавляем в кэш.
        """
        if index in self._cache:
            return self._cache[index]

        # Простая стратегия вытеснения: удаляем первый элемент при переполнении
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))

        # Загружаем объект из файла
        with open(self.filepath, 'rb') as f:
            f.seek(self._offsets[index])
            line = f.readline()
            obj = json.loads(line)
            self._cache[index] = obj
            return obj

    def search_by_field(self, field_name: str, pattern_str: str, max_results: int = 1000):
        """
        Поиск по конкретному полю во всех объектах файла.

        Args:
            field_name: Имя поля для поиска
            pattern_str: Шаблон поиска (regex или подстрока)
            max_results: Максимальное количество результатов

        Returns:
            List[(obj_index, path, value, field_name)]
        """
        matches = []

        # Компилируем regex или используем простой поиск подстроки
        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            use_regex = True
        except re.error:
            use_regex = False
            pattern = None

        # Проходим по всем объектам в файле
        for i in range(self._count):
            if len(matches) >= max_results:
                break

            obj = self[i]  # Загружаем объект (с кэшированием)

            # Рекурсивный обход структуры объекта
            def search_recursive(data, path="", parent_key=""):
                nonlocal matches
                if len(matches) >= max_results:
                    return

                if isinstance(data, dict):
                    for key, value in data.items():
                        search_recursive(value, f"{path}.{key}" if path else key, key)
                elif isinstance(data, list):
                    for idx, item in enumerate(data):
                        search_recursive(item, f"{path}[{idx}]", parent_key)
                else:
                    # Листовое значение - проверяем имя поля
                    if parent_key == field_name:
                        val_str = str(data)
                        matched = False

                        if use_regex and pattern:
                            if pattern.search(val_str):
                                matched = True
                        else:
                            if pattern_str.lower() in val_str.lower():
                                matched = True

                        if matched:
                            matches.append((i, path, data, parent_key))

            search_recursive(obj)

        return matches

    def search_all_fields(self, pattern_str: str, max_results: int = 1000):
        """
        Глобальный поиск по ВСЕМ листовым полям.

        Args:
            pattern_str: Шаблон поиска (regex или подстрока)
            max_results: Максимальное количество результатов

        Returns:
            (matches, matched_fields) - результаты и набор имен полей с совпадениями
        """
        matches = []
        matched_fields = set()  # Собираем имена полей, в которых найдены совпадения

        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            use_regex = True
        except re.error:
            use_regex = False
            pattern = None

        for i in range(self._count):
            if len(matches) >= max_results:
                break

            obj = self[i]

            def search_recursive(data, path="", parent_key=""):
                nonlocal matches, matched_fields
                if len(matches) >= max_results:
                    return

                if isinstance(data, dict):
                    for key, value in data.items():
                        search_recursive(value, f"{path}.{key}" if path else key, key)
                elif isinstance(data, list):
                    for idx, item in enumerate(data):
                        search_recursive(item, f"{path}[{idx}]", parent_key)
                else:
                    # Проверяем ВСЕ листовые значения
                    val_str = str(data)
                    matched = False

                    if use_regex and pattern:
                        if pattern.search(val_str):
                            matched = True
                    else:
                        if pattern_str.lower() in val_str.lower():
                            matched = True

                    if matched:
                        matches.append((i, path, data, parent_key))
                        # Добавляем имя поля в список найденных (исключая индексы массивов)
                        if parent_key and not parent_key.startswith('['):
                            matched_fields.add(parent_key)

            search_recursive(obj)

        return matches, matched_fields


def should_show_node(node: 'JsonNode', filter_fields: Set[str]) -> bool:
    """
    Проверка: должен ли узел отображаться при активном фильтре.

    Логика:
    - Если фильтр пуст - показываем всё
    - Листовой узел - показываем если его имя в фильтре
    - Не-листовой узел - показываем если у него есть отфильтрованные потомки
    """
    if not filter_fields:
        return True

    if node.is_leaf():
        return node.key in filter_fields

    # Для не-листовых узлов проверяем наличие отфильтрованных потомков
    def has_filtered_descendants(n):
        if n.is_leaf():
            return n.key in filter_fields
        if not n.children:
            n.build_children()
        for child in n.children:
            if has_filtered_descendants(child):
                return True
        return False

    return has_filtered_descendants(node)


def build_visible_list(root, filter_fields: Set[str] = None) -> List['JsonNode']:
    """
    Построение списка видимых узлов с учетом:
    - Состояния expanded/collapsed
    - Активного фильтра полей

    Возвращает плоский список узлов для отображения.
    """
    visible = []

    def walk(node):
        # Проверяем фильтр
        if filter_fields and not should_show_node(node, filter_fields):
            return

        visible.append(node)

        # Если узел развернут - добавляем его детей
        if node.expanded and node.children:
            for child in node.children:
                walk(child)

    # Обходим все корневые объекты
    if root.children:
        for child in root.children:
            walk(child)

    return visible


def format_node_line(node: 'JsonNode', width: int, total_objects: int) -> str:
    """
    Форматирование строки для отображения узла.

    Формат: <отступ><маркер> [индекс] <ключ>: <значение>
    Обрезка по ширине экрана с добавлением "..." если не помещается.
    """
    indent = "  " * node.depth  # Отступ по глубине вложенности

    # Маркер состояния: "-" развернут, "+" свернут, " " лист
    marker = "-" if node.expanded else "+" if not node.is_leaf() else " "

    # Префикс с индексом для корневых объектов (если их больше одного)
    key_prefix = f"[{node.index}] " if node.depth == 0 and total_objects > 1 else ""

    # Форматирование значения
    if isinstance(node.value, dict):
        val_str = f"{{...}} ({len(node.value)} keys)"
    elif isinstance(node.value, list):
        val_str = f"[...] ({len(node.value)} items)"
    else:
        # Для листовых значений используем repr
        val_str = repr(node.value)

    # Собираем полную строку
    line = f"{indent}{marker} {key_prefix}{node.key}: {val_str}"

    # ОБРЕЗКА по ширине экрана
    available_width = width - 1
    if len(line) > available_width:
        line = line[:available_width - 3] + "..."

    return line


def show_full_value_viewer(stdscr, node: 'JsonNode'):
    """
    Полноэкранный просмотрщик значения узла с прокруткой.

    Управление:
    - ↑↓←→: вертикальная и горизонтальная прокрутка
    - PgUp/PgDn: постраничная прокрутка
    - Home/End: в начало/конец
    - q/Esc: выход
    """
    h, w = stdscr.getmaxyx()

    win = curses.newwin(h, w, 0, 0)
    win.keypad(True)

    # Подготовка текста для отображения
    full_value = str(node.value)
    lines = full_value.split('\n')

    scroll_y = 0  # Вертикальная прокрутка (номер первой видимой строки)
    scroll_x = 0  # Горизонтальная прокрутка (номер первого видимого символа)

    while True:
        win.clear()
        win.box()

        # Заголовок с именем поля
        title = f" Поле: {node.key} (↑↓←→:прокрутка, q/Esc:выход) "
        win.addnstr(0, (w - len(title)) // 2, title[:w-2], w-2, curses.A_BOLD)

        # Информация о значении
        val_type = type(node.value).__name__
        val_len = len(full_value)
        info = f" Тип: {val_type} | Длина: {val_len} символов "
        win.addnstr(1, 2, info[:w-4], w-4)

        # Область для текста (с учетом рамки и заголовков)
        text_h = h - 4
        text_w = w - 4

        # Определяем максимальную ширину строки (для горизонтальной прокрутки)
        max_line_width = max(len(line) for line in lines) if lines else 0

        # Отображаем видимые строки
        for i in range(text_h):
            line_idx = scroll_y + i
            if line_idx >= len(lines):
                break

            line = lines[line_idx]

            # Применяем горизонтальную прокрутку
            if scroll_x < len(line):
                visible_part = line[scroll_x:scroll_x + text_w]
                win.addnstr(i + 2, 2, visible_part, text_w)

        # Статус прокрутки
        status = f"Строка {scroll_y+1}/{len(lines)} | Столбец {scroll_x+1}"
        win.addnstr(h-1, 2, status[:w-4], w-4)

        win.refresh()

        # Обработка клавиш
        ch = win.getch()

        if ch in (ord('q'), ord('Q'), 27):  # q, Q, ESC
            break
        elif ch == curses.KEY_UP:
            scroll_y = max(0, scroll_y - 1)
        elif ch == curses.KEY_DOWN:
            scroll_y = min(max(0, len(lines) - text_h), scroll_y + 1)
        elif ch == curses.KEY_LEFT:
            scroll_x = max(0, scroll_x - 1)
        elif ch == curses.KEY_RIGHT:
            scroll_x = min(max(0, max_line_width - text_w), scroll_x + 1)
        elif ch == curses.KEY_PPAGE:  # Page Up
            scroll_y = max(0, scroll_y - text_h)
        elif ch == curses.KEY_NPAGE:  # Page Down
            scroll_y = min(max(0, len(lines) - text_h), scroll_y + text_h)
        elif ch == curses.KEY_HOME:
            scroll_y = 0
            scroll_x = 0
        elif ch == curses.KEY_END:
            scroll_y = max(0, len(lines) - text_h)


def show_field_selector(stdscr, available_fields: List[str], preselected: Set[str] = None) -> Optional[Set[str]]:
    """
    Диалог выбора полей для фильтрации.

    Управление:
    - ↑↓: навигация по списку
    - Пробел: выбрать/снять выбор с поля
    - Enter: применить выбор
    - Esc: отмена

    Returns:
        Set[str] - выбранные поля, или None если отменено
    """
    h, w = stdscr.getmaxyx()

    # Размеры окна
    win_h = min(len(available_fields) + 4, h - 4)
    win_w = min(60, w - 4)
    win_y = (h - win_h) // 2
    win_x = (w - win_w) // 2

    win = curses.newwin(win_h, win_w, win_y, win_x)
    win.keypad(True)
    win.box()

    # Инициализация состояния
    selected_fields = preselected.copy() if preselected else set()
    cursor_pos = 0          # Позиция курсора в списке
    scroll_offset = 0       # Смещение прокрутки

    while True:
        win.clear()
        win.box()

        # Заголовок
        title = " Выбор полей (пробел=выбрать, Enter=OK, Esc=отмена) "
        win.addnstr(0, (win_w - len(title)) // 2, title, win_w - 2, curses.A_BOLD)

        # Список полей с чекбоксами
        list_h = win_h - 3  # Высота списка (с учетом рамки и строки состояния)
        for i in range(list_h):
            idx = scroll_offset + i
            if idx >= len(available_fields):
                break

            field = available_fields[idx]
            checkbox = "[X]" if field in selected_fields else "[ ]"
            line = f"{checkbox} {field}"

            # Подсвечиваем текущую позицию курсора
            if idx == cursor_pos:
                win.attron(curses.A_REVERSE)
                win.addnstr(i + 1, 2, line[:win_w-4], win_w - 4)
                win.attroff(curses.A_REVERSE)
            else:
                win.addnstr(i + 1, 2, line[:win_w-4], win_w - 4)

        # Строка состояния
        status = f"Выбрано: {len(selected_fields)}/{len(available_fields)}"
        win.addnstr(win_h - 1, 2, status, win_w - 4)

        win.refresh()

        # Обработка клавиш
        ch = win.getch()

        if ch == 27:  # ESC - отмена
            return None
        elif ch in (10, 13):  # Enter - применить
            return selected_fields
        elif ch in (curses.KEY_UP, ord('k')):
            if cursor_pos > 0:
                cursor_pos -= 1
                # Корректируем прокрутку если курсор вышел за пределы видимой области
                if cursor_pos < scroll_offset:
                    scroll_offset = cursor_pos
        elif ch in (curses.KEY_DOWN, ord('j')):
            if cursor_pos < len(available_fields) - 1:
                cursor_pos += 1
                if cursor_pos >= scroll_offset + list_h:
                    scroll_offset = cursor_pos - list_h + 1
        elif ch == ord(' '):  # Пробел - toggle выбор
            field = available_fields[cursor_pos]
            if field in selected_fields:
                selected_fields.remove(field)
            else:
                selected_fields.add(field)


def navigate_by_path_with_state(root_obj, rel_path):
    """
    Навигация к узлу по относительному пути с восстановлением состояния expanded.

    Используется для перехода между объектами с сохранением позиции в дереве.
    Например: при переходе с объекта [0] на объект [1] открывает те же поля.

    Args:
        root_obj: Корневой объект (depth=0)
        rel_path: Путь вида [(key, depth, expanded), ...]

    Returns:
        JsonNode или None если путь не найден
    """
    if not rel_path:
        return root_obj

    current = root_obj

    # Разворачиваем корневой объект если нужно
    if not current.expanded and not current.is_leaf():
        current.expanded = True
        if not current.children:
            current.build_children()

    # Проходим по пути
    for key, target_depth, should_expand in rel_path:
        if not current.children:
            current.build_children()

        if not current.expanded and not current.is_leaf():
            current.expanded = True

        # Ищем дочерний узел с нужным ключом и глубиной
        found = False
        for child in current.children:
            if child.key == key and child.depth == target_depth:
                current = child
                found = True

                # Восстанавливаем состояние expanded
                if not current.is_leaf():
                    if should_expand and not current.expanded:
                        current.expanded = True
                        if not current.children:
                            current.build_children()
                    elif not should_expand and current.expanded:
                        current.expanded = False
                break

        if not found:
            return None  # Путь не найден (структура объектов различается)

    return current


def expand_path_to_node(node):
    """
    Разворачивание всех узлов на пути от корня до указанного узла.
    Используется перед переходом к узлу из результатов поиска.
    """
    path = []
    current = node

    # Собираем путь от узла до корня
    while current.parent:
        path.append(current)
        current = current.parent

    # Разворачиваем в обратном порядке (от корня к узлу)
    for n in reversed(path):
        if n.parent and not n.parent.expanded and not n.parent.is_leaf():
            n.parent.expanded = True
            if not n.parent.children:
                n.parent.build_children()


def find_node_by_path(root_obj, path_str: str):
    """
    Поиск узла по строковому пути вида "field1.field2[0].field3".

    Args:
        root_obj: Корневой объект для поиска
        path_str: Путь к узлу (разделители: точка и квадратные скобки)

    Returns:
        JsonNode или None если не найден
    """
    if not path_str:
        return root_obj

    # Разбираем путь на части
    parts = []
    for part in path_str.split('.'):
        if '[' in part:
            # Обработка массивов: "field[0]" -> ["field", "[0]"]
            key = part.split('[')[0]
            if key:
                parts.append(key)
            idx_part = part.split('[')[1].rstrip(']')
            parts.append(f"[{idx_part}]")
        else:
            parts.append(part)

    # Навигация по пути
    current = root_obj
    if not current.expanded:
        current.toggle()

    for part in parts:
        if not current.children:
            current.build_children()

        if not current.expanded:
            current.expanded = True

        # Ищем дочерний узел с нужным ключом
        found = False
        for child in current.children:
            if child.key == part:
                current = child
                found = True
                break

        if not found:
            return None

    return current


def input_string(stdscr, prompt: str, y: int, x: int, max_len: int = 50) -> Optional[str]:
    """
    Ввод строки с клавиатуры в указанной позиции экрана.

    Returns:
        str - введенная строка, или None если нажат ESC
    """
    curses.echo()           # Включаем отображение вводимых символов
    curses.curs_set(1)      # Показываем курсор

    stdscr.addstr(y, x, prompt)
    stdscr.refresh()

    input_win = curses.newwin(1, max_len, y, x + len(prompt))
    input_win.keypad(True)

    result = ""

    while True:
        ch = input_win.getch()

        if ch in (10, 13):  # Enter - подтверждение
            break
        elif ch == 27:  # ESC - отмена
            result = None
            break
        elif ch in (curses.KEY_BACKSPACE, 127, 8):  # Backspace
            if result:
                result = result[:-1]
                input_win.clear()
                input_win.addstr(0, 0, result)
        elif 32 <= ch <= 126:  # Печатные символы
            if len(result) < max_len:
                result += chr(ch)
                input_win.addstr(0, 0, result)

        input_win.refresh()

    curses.noecho()
    curses.curs_set(0)
    return result


def draw(stdscr, visible_nodes, cursor_idx: int, top_idx: int, 
         total_objects: int, current_obj_idx: int, filename: str, 
         filter_fields: Set[str], status_msg: str = ""):
    """
    Отрисовка главного экрана просмотрщика.

    Args:
        visible_nodes: Список видимых узлов
        cursor_idx: Индекс узла под курсором
        top_idx: Индекс первого отображаемого узла (для прокрутки)
        current_obj_idx: Индекс текущего объекта в файле
        filter_fields: Активные фильтры полей
        status_msg: Сообщение для строки состояния

    Returns:
        int - обновленный top_idx (для прокрутки)
    """
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    list_height = h - 4  # Высота области списка (с учетом заголовка и футера)

    # Автоматическая прокрутка при движении курсора
    if cursor_idx < top_idx:
        top_idx = cursor_idx
    elif cursor_idx >= top_idx + list_height:
        top_idx = cursor_idx - list_height + 1

    # Заголовок с именем файла и индикатором фильтра
    filter_indicator = f" [фильтр: {len(filter_fields)} полей]" if filter_fields else ""
    title = f"Файл: {os.path.basename(filename)} ({total_objects} объектов){filter_indicator}"
    stdscr.addnstr(0, 0, title[:w-1], w-1, curses.A_BOLD)

    # Отрисовка списка узлов
    for i in range(list_height):
        node_idx = top_idx + i
        if node_idx >= len(visible_nodes):
            break

        node = visible_nodes[node_idx]
        line = format_node_line(node, w, total_objects)

        # Подсвечиваем строку под курсором
        if node_idx == cursor_idx:
            stdscr.attron(curses.A_REVERSE)
            stdscr.addnstr(i+1, 0, line, w-1)
            stdscr.attroff(curses.A_REVERSE)
        else:
            stdscr.addnstr(i+1, 0, line, w-1)

    # Строка сообщения (над строкой состояния)
    if status_msg:
        stdscr.addnstr(h-3, 0, status_msg[:w-1], w-1, curses.A_BOLD)

    # Строка состояния с информацией о текущей позиции
    status = f"Текущий: [{current_obj_idx}] | Объектов: {total_objects} | Узлов: {len(visible_nodes)} | {cursor_idx+1}/{len(visible_nodes) or 1}"
    stdscr.addnstr(h-2, 0, status[:w-1], w-1, curses.A_BOLD)

    # Строка управления (подсказка по клавишам)
    controls = "↑↓ →← Enter s:поиск F:глоб.поиск f:фильтр a z A Z g n/p q"
    stdscr.addnstr(h-1, 0, controls[:w-1], w-1, curses.A_BOLD)

    stdscr.refresh()
    return top_idx


def load_object_into_tree(json_file, root, obj_idx, loaded_objects):
    """
    Ленивая загрузка объекта в дерево (если еще не загружен).

    Args:
        json_file: Источник данных (LazyJsonFile)
        root: Корневой узел дерева
        obj_idx: Индекс объекта для загрузки
        loaded_objects: Set индексов уже загруженных объектов

    Returns:
        JsonNode загруженного объекта
    """
    if obj_idx not in loaded_objects and obj_idx < len(json_file):
        obj = json_file[obj_idx]
        node = JsonNode("record", obj, root, 0, obj_idx)
        root.children.append(node)
        loaded_objects.add(obj_idx)
        # Сортируем для сохранения порядка (при разрозненной загрузке)
        root.children.sort(key=lambda n: n.index)
        return node
    else:
        # Объект уже загружен - находим его в дереве
        return next((n for n in root.children if n.index == obj_idx), None)


def ensure_next_objects_loaded(json_file, root, loaded_objects, current_max_idx, batch_size=5):
    """
    Упреждающая загрузка следующих объектов (для плавной прокрутки).
    Загружает batch_size объектов после current_max_idx.
    """
    next_idx = current_max_idx + 1
    for i in range(batch_size):
        if next_idx + i < len(json_file):
            load_object_into_tree(json_file, root, next_idx + i, loaded_objects)


def main(stdscr, json_file: LazyJsonFile, filename: str):
    """
    Главная функция TUI приложения.
    Обрабатывает пользовательский ввод и управляет состоянием.
    """
    curses.curs_set(0)      # Скрываем курсор
    stdscr.keypad(True)     # Включаем обработку специальных клавиш

    if len(json_file) == 0:
        stdscr.addstr(5, 5, "ОШИБКА: Нет JSON объектов!", curses.A_BOLD)
        stdscr.refresh()
        stdscr.getch()
        return

    # Инициализация корневого узла дерева
    root = JsonNode("root", None, depth=-1)
    root.children = []
    loaded_objects = set()  # Множество индексов загруженных объектов

    # Предзагрузка первых объектов для заполнения экрана
    h, w = stdscr.getmaxyx()
    list_height = h - 4
    preload_count = min(max(list_height + 10, 20), len(json_file))

    status_msg = f"Загрузка первых {preload_count} объектов..."
    stdscr.addnstr(h//2, (w - len(status_msg))//2, status_msg, w-1, curses.A_BOLD)
    stdscr.refresh()

    for i in range(preload_count):
        obj = json_file[i]
        node = JsonNode("record", obj, root, 0, i)
        root.children.append(node)
        loaded_objects.add(i)

    # Состояние приложения
    cursor_idx = 0          # Позиция курсора в списке видимых узлов
    top_idx = 0             # Индекс первого отображаемого узла (прокрутка)
    status_msg = ""         # Сообщение для отображения

    search_results = []     # Результаты последнего поиска
    search_idx = -1         # Текущая позиция в результатах поиска
    current_field_name = None  # Имя поля для поиска (по клавише 's')
    filter_fields = set()   # Активные фильтры полей

    # Главный цикл обработки событий
    while True:
        # Обновляем список видимых узлов (с учетом фильтра)
        visible_nodes = build_visible_list(root, filter_fields)
        if cursor_idx >= len(visible_nodes):
            cursor_idx = max(0, len(visible_nodes) - 1)

        # Определяем текущий объект (для отображения в статусе)
        current_obj_idx = 0
        if visible_nodes:
            current_node = visible_nodes[cursor_idx]
            root_obj = current_node.get_root_object()
            current_obj_idx = root_obj.index

        # Отрисовка экрана
        top_idx = draw(stdscr, visible_nodes, cursor_idx, top_idx, 
                      len(json_file), current_obj_idx, filename, filter_fields, status_msg)
        status_msg = ""

        # Ожидание нажатия клавиши
        ch = stdscr.getch()

        # === ОБРАБОТКА КЛАВИШ ===

        if ch in (ord('q'), ord('Q'), 27):  # q, Q, ESC - выход
            break

        elif ch in (curses.KEY_UP, ord('k')):  # Вверх
            cursor_idx = max(0, cursor_idx - 1)

        elif ch in (curses.KEY_DOWN, ord('j')):  # Вниз
            if cursor_idx < len(visible_nodes) - 1:
                cursor_idx += 1

            # Упреждающая загрузка при приближении к концу списка
            if visible_nodes and cursor_idx >= len(visible_nodes) - 5:
                max_loaded = max(loaded_objects) if loaded_objects else -1
                ensure_next_objects_loaded(json_file, root, loaded_objects, max_loaded, 5)

        elif ch in (curses.KEY_RIGHT, ord('l')):  # Вправо - развернуть
            if visible_nodes:
                node = visible_nodes[cursor_idx]
                if not node.is_leaf():
                    node.toggle()

        elif ch in (10, 13):  # Enter - просмотр полного значения или toggle
            if visible_nodes:
                node = visible_nodes[cursor_idx]
                if node.is_leaf():
                    # Для листовых узлов - открываем полноэкранный просмотр
                    show_full_value_viewer(stdscr, node)
                else:
                    # Для не-листовых - переключаем состояние
                    node.toggle()

        elif ch == curses.KEY_LEFT:  # Влево - свернуть или к родителю
            if visible_nodes:
                node = visible_nodes[cursor_idx]
                if node.expanded and node.children:
                    # Если узел развернут - сворачиваем
                    node.toggle()
                elif node.parent and node.parent != root:
                    # Иначе переходим к родительскому узлу
                    parent_idx = next((i for i, n in enumerate(visible_nodes) 
                                     if n is node.parent), 0)
                    cursor_idx = parent_idx

        elif ch == ord('f'):  # f - ручная фильтрация полей
            if root.children:
                first_obj = root.children[0]
                available_fields = sorted(list(first_obj.collect_leaf_fields()))

                if available_fields:
                    # Открываем диалог выбора полей
                    selected = show_field_selector(stdscr, available_fields, filter_fields)
                    if selected is not None:
                        filter_fields = selected
                        if filter_fields:
                            status_msg = f"Фильтр: {len(filter_fields)} полей"
                        else:
                            status_msg = "Фильтр отключен"
                else:
                    status_msg = "Нет доступных полей для фильтрации"

        elif ch == ord('F'):  # F - глобальный поиск с авто-фильтром
            h_local, w_local = stdscr.getmaxyx()
            pattern = input_string(stdscr, "Глобальный поиск (regex): ", h_local-3, 0, 40)

            if pattern:
                status_msg = "Поиск по всем полям..."
                stdscr.addnstr(h_local-3, 0, status_msg, w_local-1, curses.A_BOLD)
                stdscr.refresh()

                # Поиск по всем полям всех объектов
                raw_matches, matched_fields = json_file.search_all_fields(pattern, 1000)

                if raw_matches:
                    search_results = []
                    # Загружаем объекты и находим узлы для результатов
                    for obj_idx, path_str, value, field_name in raw_matches:
                        obj_node = load_object_into_tree(json_file, root, obj_idx, loaded_objects)
                        if obj_node:
                            target_node = find_node_by_path(obj_node, path_str)
                            if target_node:
                                search_results.append(target_node)

                    if search_results:
                        # АВТОМАТИЧЕСКИ применяем фильтр на найденные поля
                        filter_fields = matched_fields

                        # Переходим к первому результату
                        search_idx = 0
                        target_node = search_results[search_idx]
                        expand_path_to_node(target_node)
                        visible_nodes = build_visible_list(root, filter_fields)
                        cursor_idx = visible_nodes.index(target_node)
                        status_msg = f"Найдено {len(search_results)}, фильтр: {len(matched_fields)} полей (1/{len(search_results)})"
                    else:
                        status_msg = f"Не найдено: '{pattern}'"
                        search_results = []
                        search_idx = -1
                else:
                    status_msg = f"Не найдено: '{pattern}'"
                    search_results = []
                    search_idx = -1

        elif ch == ord('a'):  # a - развернуть текущий объект
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                root_obj = current_node.get_root_object()
                root_obj.expand_all()
                status_msg = f"Развернут объект [{root_obj.index}]"

        elif ch == ord('z'):  # z - свернуть текущий объект
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                root_obj = current_node.get_root_object()
                root_obj.collapse_all()
                visible_nodes = build_visible_list(root, filter_fields)
                # Позиционируемся на свернутый объект
                try:
                    cursor_idx = visible_nodes.index(root_obj)
                except ValueError:
                    cursor_idx = next((i for i, n in enumerate(visible_nodes) 
                                     if n.index == root_obj.index and n.depth == 0), 0)
                status_msg = f"Свернут объект [{root_obj.index}]"

        elif ch == ord('A'):  # A - развернуть ВСЕ объекты
            h_local, w_local = stdscr.getmaxyx()
            status_msg = f"Загрузка всех {len(json_file)} объектов..."
            stdscr.addnstr(h_local-3, 0, status_msg, w_local-1, curses.A_BOLD)
            stdscr.refresh()

            # Загружаем все объекты (если еще не загружены)
            for i in range(len(json_file)):
                load_object_into_tree(json_file, root, i, loaded_objects)

            # Разворачиваем все
            for obj_node in root.children:
                obj_node.expand_all()
            status_msg = f"Развернуты ВСЕ {len(json_file)} объектов"

        elif ch == ord('Z'):  # Z - свернуть ВСЕ объекты
            for obj_node in root.children:
                obj_node.collapse_all()
            visible_nodes = build_visible_list(root, filter_fields)
            if visible_nodes:
                cursor_idx = 0
            status_msg = "Свернуты все объекты"

        elif ch == ord('g'):  # g - переход к объекту по номеру
            h_local, w_local = stdscr.getmaxyx()
            obj_num_str = input_string(stdscr, "Объект #: ", h_local-3, 0, 10)
            if obj_num_str and obj_num_str.isdigit():
                obj_num = int(obj_num_str)
                if 0 <= obj_num < len(json_file):
                    target_obj = load_object_into_tree(json_file, root, obj_num, loaded_objects)
                    if target_obj:
                        if not target_obj.expanded:
                            target_obj.toggle()
                        visible_nodes = build_visible_list(root, filter_fields)
                        cursor_idx = visible_nodes.index(target_obj)
                        status_msg = f"Переход к объекту [{obj_num}]"
                else:
                    status_msg = f"Объект [{obj_num}] не существует!"

        elif ch == curses.KEY_END:  # End - к последнему объекту
            last_idx = len(json_file) - 1
            last_obj = load_object_into_tree(json_file, root, last_idx, loaded_objects)
            if last_obj:
                if not last_obj.expanded:
                    last_obj.toggle()
                visible_nodes = build_visible_list(root, filter_fields)
                cursor_idx = visible_nodes.index(last_obj)
                status_msg = f"Переход к последнему объекту [{last_idx}]"

        elif ch == curses.KEY_HOME:  # Home - к первому объекту
            first_obj = load_object_into_tree(json_file, root, 0, loaded_objects)
            if first_obj:
                if not first_obj.expanded:
                    first_obj.toggle()
                visible_nodes = build_visible_list(root, filter_fields)
                cursor_idx = visible_nodes.index(first_obj)
                status_msg = "Переход к первому объекту [0]"

        elif ch == ord('s'):  # s - поиск по текущему полю
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                current_field_name = current_node.key

                h_local, w_local = stdscr.getmaxyx()
                pattern = input_string(stdscr, f"Поиск '{current_field_name}' (regex): ", h_local-3, 0, 40)

                if pattern:
                    status_msg = f"Поиск '{current_field_name}' по всем объектам..."
                    stdscr.addnstr(h_local-3, 0, status_msg, w_local-1, curses.A_BOLD)
                    stdscr.refresh()

                    # Поиск только по указанному полю
                    raw_matches = json_file.search_by_field(current_field_name, pattern, 1000)

                    if raw_matches:
                        search_results = []
                        for obj_idx, path_str, value, field_name in raw_matches:
                            obj_node = load_object_into_tree(json_file, root, obj_idx, loaded_objects)
                            if obj_node:
                                target_node = find_node_by_path(obj_node, path_str)
                                if target_node:
                                    search_results.append(target_node)

                        if search_results:
                            search_idx = 0
                            target_node = search_results[search_idx]
                            expand_path_to_node(target_node)
                            visible_nodes = build_visible_list(root, filter_fields)
                            cursor_idx = visible_nodes.index(target_node)
                            status_msg = f"Найдено {len(search_results)} '{current_field_name}' (1/{len(search_results)})"
                        else:
                            status_msg = f"Не найдено '{current_field_name}': '{pattern}'"
                            search_results = []
                            search_idx = -1
                    else:
                        status_msg = f"Не найдено '{current_field_name}': '{pattern}'"
                        search_results = []
                        search_idx = -1

        elif ch == ord('n'):  # n - следующий результат поиска
            if search_results and search_idx >= 0:
                # Циклический переход к следующему результату
                search_idx = (search_idx + 1) % len(search_results)
                target_node = search_results[search_idx]
                expand_path_to_node(target_node)
                visible_nodes = build_visible_list(root, filter_fields)
                cursor_idx = visible_nodes.index(target_node)
                root_obj = target_node.get_root_object()
                status_msg = f"obj[{root_obj.index}] ({search_idx+1}/{len(search_results)})"
            else:
                status_msg = "Нет результатов поиска. Нажмите 's' или 'F'"

        elif ch == ord('p'):  # p - предыдущий результат поиска
            if search_results and search_idx >= 0:
                # Циклический переход к предыдущему результату
                search_idx = (search_idx - 1) % len(search_results)
                target_node = search_results[search_idx]
                expand_path_to_node(target_node)
                visible_nodes = build_visible_list(root, filter_fields)
                cursor_idx = visible_nodes.index(target_node)
                root_obj = target_node.get_root_object()
                status_msg = f"obj[{root_obj.index}] ({search_idx+1}/{len(search_results)})"
            else:
                status_msg = "Нет результатов поиска. Нажмите 's' или 'F'"

        elif ch == curses.KEY_NPAGE:  # Page Down - следующий объект с сохранением позиции
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                current_obj = current_node.get_root_object()
                current_obj_idx = current_obj.index

                if current_obj_idx < len(json_file) - 1:
                    # Запоминаем относительный путь к текущему узлу
                    rel_path = current_node.get_relative_path_with_state()
                    next_obj_idx = current_obj_idx + 1
                    next_obj = load_object_into_tree(json_file, root, next_obj_idx, loaded_objects)

                    if next_obj:
                        # Пытаемся найти аналогичный узел в следующем объекте
                        target_node = navigate_by_path_with_state(next_obj, rel_path)
                        visible_nodes = build_visible_list(root, filter_fields)
                        if target_node and target_node in visible_nodes:
                            cursor_idx = visible_nodes.index(target_node)
                        else:
                            # Если не нашли - переходим на корень объекта
                            cursor_idx = visible_nodes.index(next_obj)

        elif ch == curses.KEY_PPAGE:  # Page Up - предыдущий объект с сохранением позиции
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                current_obj = current_node.get_root_object()
                current_obj_idx = current_obj.index

                if current_obj_idx > 0:
                    rel_path = current_node.get_relative_path_with_state()
                    prev_obj_idx = current_obj_idx - 1
                    prev_obj = load_object_into_tree(json_file, root, prev_obj_idx, loaded_objects)

                    if prev_obj:
                        target_node = navigate_by_path_with_state(prev_obj, rel_path)
                        visible_nodes = build_visible_list(root, filter_fields)
                        if target_node and target_node in visible_nodes:
                            cursor_idx = visible_nodes.index(target_node)
                        else:
                            cursor_idx = visible_nodes.index(prev_obj)


def run():
    """Точка входа в приложение."""
    if len(sys.argv) < 2:
        print("Использование: python json_tui_viewer.py file.jsonl")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"Файл не найден: {path}")
        sys.exit(1)

    # Инициализация ленивого загрузчика
    json_file = LazyJsonFile(path)
    if len(json_file) == 0:
        print("Не найдено валидных JSON!")
        sys.exit(1)

    # Запуск TUI приложения через curses wrapper
    # (wrapper автоматически восстанавливает терминал при выходе)
    curses.wrapper(main, json_file, path)


if __name__ == "__main__":
    run()
