#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TUI JSON viewer с исправленной логикой PgUp/PgDn.
"""

import sys
import json
import os
import curses
from typing import List, Optional

class JsonNode:
    def __init__(self, key: str, value: any, parent=None, depth: int = 0, index: int = 0):
        self.key = key
        self.value = value
        self.parent = parent
        self.depth = depth
        self.expanded = False
        self.children = None
        self.index = index

    def is_leaf(self) -> bool:
        return not isinstance(self.value, (dict, list))

    def build_children(self):
        if self.children is not None:
            return
        self.children = []
        if isinstance(self.value, dict):
            for k in sorted(self.value.keys()):
                self.children.append(
                    JsonNode(str(k), self.value[k], self, self.depth + 1)
                )
        elif isinstance(self.value, list):
            for idx, item in enumerate(self.value):
                self.children.append(
                    JsonNode(f"[{idx}]", item, self, self.depth + 1)
                )

    def toggle(self):
        if self.is_leaf():
            return
        if not self.expanded:
            self.build_children()
        self.expanded = not self.expanded

    def get_relative_path(self):
        """Возвращает путь от корневого объекта: ['key1', 'key2', ...]"""
        path = []
        node = self
        while node.parent and node.parent.key != "root":
            path.append((node.key, node.depth))
            node = node.parent
        return list(reversed(path))


def parse_json_file(path: str) -> List[dict]:
    objects = []
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            objects.append(data)
        print(f"Одиночный JSON: {len(objects)} объект")
        return objects
    except json.JSONDecodeError:
        pass
    
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                objects.append(obj)
            except json.JSONDecodeError:
                continue
    
    print(f"JSONL: {len(objects)} объектов")
    return objects


def build_visible_list(root: JsonNode) -> List['JsonNode']:
    visible = []
    def walk(node: JsonNode):
        visible.append(node)
        if node.expanded and node.children:
            for child in node.children:
                walk(child)
    if root.children:
        for child in root.children:
            walk(child)
    return visible


def format_node_line(node: 'JsonNode', width: int, total_objects: int) -> str:
    indent = "  " * node.depth
    marker = "-" if node.expanded else "+" if not node.is_leaf() else " "
    
    key_prefix = f"[{node.index}] " if node.depth == 0 and total_objects > 1 else ""
    
    if isinstance(node.value, dict):
        val_str = f"{{...}} ({len(node.value)} keys)"
    elif isinstance(node.value, list):
        val_str = f"[...] ({len(node.value)} items)"
    else:
        val_repr = repr(node.value)
        if len(val_repr) > 40:
            val_repr = val_repr[:37] + "..."
        val_str = val_repr

    line = f"{indent}{marker} {key_prefix}{node.key}: {val_str}"
    return line[:width-1]


def find_node_by_relative_path(root: JsonNode, obj_index: int, rel_path: List) -> Optional['JsonNode']:
    """Находит узел по относительному пути в указанном объекте."""
    if obj_index >= len(root.children):
        return None
    obj_node = root.children[obj_index]
    if not rel_path:
        return obj_node
    
    current = obj_node
    for key, depth in rel_path:
        if not current.expanded or not current.children:
            current.toggle()
        for child in current.children:
            if child.key == key and child.depth == depth:
                current = child
                break
        else:
            return None
    return current


def draw(stdscr, visible_nodes: List['JsonNode'], cursor_idx: int, top_idx: int, 
         total_objects: int, filename: str):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    list_height = h - 3

    if cursor_idx < top_idx:
        top_idx = cursor_idx
    elif cursor_idx >= top_idx + list_height:
        top_idx = cursor_idx - list_height + 1

    title = f"Файл: {os.path.basename(filename)} ({total_objects} объектов)"
    stdscr.addnstr(0, 0, title[:w-1], w-1, curses.A_BOLD)
    
    for i in range(list_height):
        node_idx = top_idx + i
        if node_idx >= len(visible_nodes):
            break
        node = visible_nodes[node_idx]
        line = format_node_line(node, w, total_objects)
        
        if node_idx == cursor_idx:
            stdscr.attron(curses.A_REVERSE)
            stdscr.addnstr(i+1, 0, line, w-1)
            stdscr.attroff(curses.A_REVERSE)
        else:
            stdscr.addnstr(i+1, 0, line, w-1)

    status = f"Объектов: {total_objects} | Узлов: {len(visible_nodes)} | {cursor_idx+1}/{len(visible_nodes) or 1}"
    stdscr.addnstr(h-2, 0, status[:w-1], w-1, curses.A_BOLD)
    
    controls = "↑/↓:move  ←:collapse  →/Enter:expand  q:quit  PgUp/Dn:next-obj"
    stdscr.addnstr(h-1, 0, controls[:w-1], w-1, curses.A_BOLD)
    
    stdscr.refresh()
    return top_idx


def main(stdscr, json_objects: List[dict], filename: str):
    curses.curs_set(0)
    stdscr.keypad(True)

    if not json_objects:
        stdscr.addstr(5, 5, "ОШИБКА: Нет JSON объектов!", curses.A_BOLD)
        stdscr.refresh()
        stdscr.getch()
        return

    root = JsonNode("root", None, depth=-1)
    root.children = [JsonNode("record", obj, root, 0, i) 
                     for i, obj in enumerate(json_objects)]
    
    if root.children:
        root.children[0].toggle()

    cursor_idx = 0
    top_idx = 0

    while True:
        visible_nodes = build_visible_list(root)
        if cursor_idx >= len(visible_nodes):
            cursor_idx = max(0, len(visible_nodes) - 1)

        top_idx = draw(stdscr, visible_nodes, cursor_idx, top_idx, 
                      len(json_objects), filename)

        ch = stdscr.getch()
        
        if ch in (ord('q'), ord('Q'), 27):
            break
        elif ch in (curses.KEY_UP, ord('k')):
            cursor_idx = max(0, cursor_idx - 1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            cursor_idx = min(len(visible_nodes) - 1, cursor_idx + 1)
        elif ch in (curses.KEY_RIGHT, ord('l'), 10, 13):
            if visible_nodes:
                visible_nodes[cursor_idx].toggle()
        elif ch == curses.KEY_LEFT:
            if visible_nodes:
                node = visible_nodes[cursor_idx]
                if node.expanded and node.children:
                    node.toggle()
                elif node.parent and node.parent != root:
                    parent_idx = next((i for i, n in enumerate(visible_nodes) 
                                     if n is node.parent), 0)
                    cursor_idx = parent_idx
        elif ch == curses.KEY_PPAGE:  # PgUp - предыдущий объект
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                current_obj_idx = next((n.index for n in visible_nodes 
                                      if n.depth == 0), 0)
                if current_obj_idx > 0:
                    # Сохраняем относительный путь текущего узла
                    rel_path = current_node.get_relative_path()
                    # Переходим к предыдущему объекту
                    new_obj_idx = current_obj_idx - 1
                    new_node = find_node_by_relative_path(root, new_obj_idx, rel_path)
                    if new_node:
                        # Находим индекс нового узла в visible_nodes
                        visible_nodes = build_visible_list(root)
                        new_cursor_idx = next((i for i, n in enumerate(visible_nodes) 
                                             if n is new_node), new_obj_idx)
                        cursor_idx = new_cursor_idx
                    else:
                        # Если путь не найден - просто переходим к объекту
                        root.children[current_obj_idx].expanded = False
                        root.children[new_obj_idx].toggle()
                        cursor_idx = sum(1 for n in build_visible_list(root) 
                                       if n.index == new_obj_idx)
        elif ch == curses.KEY_NPAGE:  # PgDn - следующий объект
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                current_obj_idx = next((n.index for n in visible_nodes 
                                      if n.depth == 0), 0)
                if current_obj_idx < len(root.children) - 1:
                    rel_path = current_node.get_relative_path()
                    new_obj_idx = current_obj_idx + 1
                    new_node = find_node_by_relative_path(root, new_obj_idx, rel_path)
                    if new_node:
                        visible_nodes = build_visible_list(root)
                        new_cursor_idx = next((i for i, n in enumerate(visible_nodes) 
                                             if n is new_node), new_obj_idx)
                        cursor_idx = new_cursor_idx
                    else:
                        root.children[current_obj_idx].expanded = False
                        root.children[new_obj_idx].toggle()
                        cursor_idx = sum(1 for n in build_visible_list(root) 
                                       if n.index == new_obj_idx)


def run():
    if len(sys.argv) < 2:
        print("Использование: python json_tui_viewer.py file.jsonl")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"Файл не найден: {path}")
        sys.exit(1)

    json_objects = parse_json_file(path)
    if not json_objects:
        print("Не найдено валидных JSON!")
        sys.exit(1)

    curses.wrapper(main, json_objects, path)


if __name__ == "__main__":
    run()
