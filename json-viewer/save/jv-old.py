#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простейший TUI JSON viewer на curses.
Совместим с Python 3.6–3.9, использует только стандартную библиотеку.
Управление:
  ↑/↓  - перемещение по списку
  ←    - свернуть текущий узел
  →    - развернуть текущий узел
  Enter - развернуть/свернуть текущий узел
  q    - выход
"""

import sys
import json
import os
import curses

class JsonNode:
    """
    Узел дерева JSON для отображения в TUI.
    """
    def __init__(self, key, value, parent=None, depth=0):
        self.key = key
        self.value = value
        self.parent = parent
        self.depth = depth
        self.expanded = False
        self.children = None  # лениво строим дочерние узлы

    def is_leaf(self):
        return not isinstance(self.value, (dict, list))

    def build_children(self):
        if self.children is not None:
            return
        children = []
        if isinstance(self.value, dict):
            for k in self.value:
                children.append(
                    JsonNode(
                        key=str(k),
                        value=self.value[k],
                        parent=self,
                        depth=self.depth + 1,
                    )
                )
        elif isinstance(self.value, list):
            for idx, item in enumerate(self.value):
                children.append(
                    JsonNode(
                        key=f"[{idx}]",
                        value=item,
                        parent=self,
                        depth=self.depth + 1,
                    )
                )
        self.children = children

    def toggle(self):
        if self.is_leaf():
            return
        if not self.expanded:
            self.build_children()
        self.expanded = not self.expanded


def build_visible_list(root):
    """
    Строит линейный список видимых узлов дерева с учётом expanded.
    """
    visible = []

    def walk(node):
        visible.append(node)
        if node.expanded and node.children:
            for ch in node.children:
                walk(ch)

    walk(root)
    return visible


def format_node_line(node, width):
    """
    Формирование строки для отображения одного узла.
    """
    indent = "  " * node.depth
    # Символ разворачивания/сворачивания
    if node.is_leaf():
        marker = " "
    else:
        marker = "-" if node.expanded else "+"

    # Краткое представление значения
    if isinstance(node.value, dict):
        val_str = f"{{...}} ({len(node.value)} keys)"
    elif isinstance(node.value, list):
        val_str = f"[...] ({len(node.value)} items)"
    else:
        # Ограничиваем длину представления
        val_repr = repr(node.value)
        if len(val_repr) > 40:
            val_repr = val_repr[:37] + "..."
        val_str = val_repr

    line = f"{indent}{marker} {node.key}: {val_str}"
    if len(line) > width:
        line = line[: max(0, width - 1)]
    return line


def draw(stdscr, visible_nodes, cursor_idx, top_idx):
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    # Область для списка (оставим одну строку для статуса)
    list_height = h - 1

    # Корректируем top_idx, чтобы курсор был в видимой области
    if cursor_idx < top_idx:
        top_idx = cursor_idx
    elif cursor_idx >= top_idx + list_height:
        top_idx = cursor_idx - list_height + 1

    # Отрисовка видимых узлов
    for i in range(list_height):
        node_idx = top_idx + i
        if node_idx >= len(visible_nodes):
            break
        node = visible_nodes[node_idx]
        line = format_node_line(node, w)
        if node_idx == cursor_idx:
            # Выделение текущей строки обратным видео
            stdscr.attron(curses.A_REVERSE)
            stdscr.addnstr(i, 0, line, w - 1)
            stdscr.attroff(curses.A_REVERSE)
        else:
            stdscr.addnstr(i, 0, line, w - 1)

    # Строка статуса
    status = "↑/↓: навигация  ←/→/Enter: свернуть/развернуть  q: выход"
    status = status[: max(0, w - 1)]
    stdscr.addnstr(h - 1, 0, status, w - 1, curses.A_BOLD)

    stdscr.refresh()
    return top_idx


def main(stdscr, json_root):
    curses.curs_set(0)
    stdscr.keypad(True)
    curses.use_default_colors()

    root = JsonNode(key="root", value=json_root, depth=0)
    # По умолчанию разворачиваем корень
    if not root.is_leaf():
        root.toggle()

    cursor_idx = 0
    top_idx = 0

    while True:
        visible_nodes = build_visible_list(root)
        if cursor_idx >= len(visible_nodes):
            cursor_idx = max(0, len(visible_nodes) - 1)

        top_idx = draw(stdscr, visible_nodes, cursor_idx, top_idx)

        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break
        elif ch in (curses.KEY_UP, ord("k")):
            if cursor_idx > 0:
                cursor_idx -= 1
        elif ch in (curses.KEY_DOWN, ord("j")):
            if cursor_idx < len(visible_nodes) - 1:
                cursor_idx += 1
        elif ch in (curses.KEY_RIGHT, ord("l"), 10, 13):
            # Развернуть
            node = visible_nodes[cursor_idx]
            if not node.is_leaf() and not node.expanded:
                node.toggle()
        elif ch in (curses.KEY_LEFT, ord("h")):
            # Свернуть или перейти к родителю
            node = visible_nodes[cursor_idx]
            if not node.is_leaf() and node.expanded:
                node.toggle()
            elif node.parent is not None:
                # Перейти к родителю
                parent = node.parent
                # Найти индекс родителя в списке
                visible_nodes = build_visible_list(root)
                for i, n in enumerate(visible_nodes):
                    if n is parent:
                        cursor_idx = i
                        break


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run():
    if len(sys.argv) < 2:
        print("Использование: python json_tui_viewer.py path/to/file.json")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"Файл не найден: {path}")
        sys.exit(1)

    try:
        data = load_json(path)
    except Exception as e:
        print(f"Ошибка чтения/парсинга JSON: {e}")
        sys.exit(1)

    curses.wrapper(main, data)


if __name__ == "__main__":
    run()

