#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TUI JSON viewer - добавлены: A/Z для всех объектов, номер текущего объекта.
Новые клавиши:
  A (Shift+a) - развернуть ВСЕ объекты
  Z (Shift+z) - свернуть ВСЕ объекты
  a - развернуть текущий объект
  z - свернуть текущий объект
"""

import sys
import json
import os
import curses
import re
from typing import List, Optional, Tuple

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

    def get_root_object(self):
        """Возвращает корневой объект (depth=0) для текущего узла."""
        node = self
        while node.parent and node.depth > 0:
            node = node.parent
        return node

    def get_relative_path_with_state(self):
        """Путь от корневого объекта С состоянием expanded: [(key, depth, expanded), ...]"""
        path = []
        node = self
        root_obj = self.get_root_object()
        while node != root_obj and node.parent:
            path.append((node.key, node.depth, node.expanded))
            node = node.parent
        return list(reversed(path))

    def expand_all(self):
        """Развернуть все поддерево."""
        if self.is_leaf():
            return
        self.expanded = True
        if not self.children:
            self.build_children()
        for child in self.children:
            child.expand_all()

    def collapse_all(self):
        """Свернуть все поддерево."""
        self.expanded = False
        if self.children:
            for child in self.children:
                child.collapse_all()

    def find_all_matching_nodes(self, pattern_str: str) -> List['JsonNode']:
        """Находит ВСЕ узлы со значением, соответствующим паттерну."""
        matches = []
        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            use_regex = True
        except re.error:
            use_regex = False
            pattern = None
        
        def search(node):
            if node.is_leaf():
                val_str = str(node.value)
                matched = False
                
                if use_regex and pattern:
                    if pattern.search(val_str):
                        matched = True
                else:
                    if pattern_str.lower() in val_str.lower():
                        matched = True
                
                if matched:
                    matches.append(node)
            
            if not node.is_leaf():
                if not node.children:
                    node.build_children()
                for child in node.children:
                    search(child)
        
        search(self)
        return matches


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


def navigate_by_path_with_state(root_obj: JsonNode, rel_path: List[Tuple[str, int, bool]]) -> Optional['JsonNode']:
    """Разворачивает путь в объекте С СОХРАНЕНИЕМ состояния expanded и возвращает целевой узел."""
    if not rel_path:
        return root_obj
    
    current = root_obj
    
    if not current.expanded and not current.is_leaf():
        current.expanded = True
        if not current.children:
            current.build_children()
    
    for key, target_depth, should_expand in rel_path:
        if not current.children:
            current.build_children()
        
        if not current.expanded and not current.is_leaf():
            current.expanded = True
        
        found = False
        for child in current.children:
            if child.key == key and child.depth == target_depth:
                current = child
                found = True
                
                if not current.is_leaf():
                    if should_expand and not current.expanded:
                        current.expanded = True
                        if not current.children:
                            current.build_children()
                    elif not should_expand and current.expanded:
                        current.expanded = False
                break
        
        if not found:
            return None
    
    return current


def expand_path_to_node(node: JsonNode):
    """Разворачивает весь путь от корня до узла."""
    path = []
    current = node
    while current.parent:
        path.append(current)
        current = current.parent
    
    for n in reversed(path):
        if n.parent and not n.parent.expanded and not n.parent.is_leaf():
            n.parent.expanded = True
            if not n.parent.children:
                n.parent.build_children()


def input_string(stdscr, prompt: str, y: int, x: int, max_len: int = 50) -> Optional[str]:
    """Ввод строки с клавиатуры."""
    curses.echo()
    curses.curs_set(1)
    stdscr.addstr(y, x, prompt)
    stdscr.refresh()
    
    input_win = curses.newwin(1, max_len, y, x + len(prompt))
    input_win.keypad(True)
    
    result = ""
    while True:
        ch = input_win.getch()
        if ch in (10, 13):  # Enter
            break
        elif ch == 27:  # ESC
            result = None
            break
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if result:
                result = result[:-1]
                input_win.clear()
                input_win.addstr(0, 0, result)
        elif 32 <= ch <= 126:
            if len(result) < max_len:
                result += chr(ch)
                input_win.addstr(0, 0, result)
        input_win.refresh()
    
    curses.noecho()
    curses.curs_set(0)
    return result


def draw(stdscr, visible_nodes: List['JsonNode'], cursor_idx: int, top_idx: int, 
         total_objects: int, current_obj_idx: int, filename: str, status_msg: str = ""):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    list_height = h - 4

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

    if status_msg:
        stdscr.addnstr(h-3, 0, status_msg[:w-1], w-1, curses.A_BOLD)
    
    # Статус с номером текущего объекта
    status = f"Текущий: [{current_obj_idx}] | Объектов: {total_objects} | Узлов: {len(visible_nodes)} | {cursor_idx+1}/{len(visible_nodes) or 1}"
    stdscr.addnstr(h-2, 0, status[:w-1], w-1, curses.A_BOLD)
    
    controls = "↑↓ →← a:cur+ z:cur- A:ALL+ Z:ALL- g Home/End s:search n/p q:quit"
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
    status_msg = ""
    
    search_results = []
    search_idx = -1

    while True:
        visible_nodes = build_visible_list(root)
        if cursor_idx >= len(visible_nodes):
            cursor_idx = max(0, len(visible_nodes) - 1)

        # Определяем текущий объект
        current_obj_idx = 0
        if visible_nodes:
            current_node = visible_nodes[cursor_idx]
            root_obj = current_node.get_root_object()
            current_obj_idx = root_obj.index

        top_idx = draw(stdscr, visible_nodes, cursor_idx, top_idx, 
                      len(json_objects), current_obj_idx, filename, status_msg)
        status_msg = ""

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
        elif ch == ord('a'):  # Развернуть ТЕКУЩИЙ объект
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                root_obj = current_node.get_root_object()
                root_obj.expand_all()
                status_msg = f"Развернут объект [{root_obj.index}]"
        elif ch == ord('z'):  # Свернуть ТЕКУЩИЙ объект
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                root_obj = current_node.get_root_object()
                root_obj.collapse_all()
                visible_nodes = build_visible_list(root)
                try:
                    cursor_idx = visible_nodes.index(root_obj)
                except ValueError:
                    cursor_idx = next((i for i, n in enumerate(visible_nodes) 
                                     if n.index == root_obj.index and n.depth == 0), 0)
                status_msg = f"Свернут объект [{root_obj.index}]"
        elif ch == ord('A'):  # Развернуть ВСЕ объекты (Shift+a)
            for obj in root.children:
                obj.expand_all()
            status_msg = f"Развернуты ВСЕ {len(root.children)} объектов"
        elif ch == ord('Z'):  # Свернуть ВСЕ объекты (Shift+z)
            for obj in root.children:
                obj.collapse_all()
            visible_nodes = build_visible_list(root)
            if visible_nodes:
                cursor_idx = 0
            status_msg = f"Свернуты ВСЕ {len(root.children)} объектов"
        elif ch == ord('g'):
            h, w = stdscr.getmaxyx()
            obj_num_str = input_string(stdscr, "Объект #: ", h-3, 0, 10)
            if obj_num_str and obj_num_str.isdigit():
                obj_num = int(obj_num_str)
                if 0 <= obj_num < len(root.children):
                    target_obj = root.children[obj_num]
                    if not target_obj.expanded:
                        target_obj.toggle()
                    visible_nodes = build_visible_list(root)
                    cursor_idx = visible_nodes.index(target_obj)
                    status_msg = f"Переход к объекту [{obj_num}]"
                else:
                    status_msg = f"Объект [{obj_num}] не существует!"
        elif ch == curses.KEY_END:
            last_obj = root.children[-1]
            if not last_obj.expanded:
                last_obj.toggle()
            visible_nodes = build_visible_list(root)
            cursor_idx = visible_nodes.index(last_obj)
            status_msg = f"Переход к последнему объекту [{last_obj.index}]"
        elif ch == curses.KEY_HOME:
            first_obj = root.children[0]
            if not first_obj.expanded:
                first_obj.toggle()
            visible_nodes = build_visible_list(root)
            cursor_idx = visible_nodes.index(first_obj)
            status_msg = "Переход к первому объекту [0]"
        elif ch == ord('s'):
            h, w = stdscr.getmaxyx()
            pattern = input_string(stdscr, "Поиск (regex): ", h-3, 0, 40)
            
            if pattern:
                search_results = []
                for obj in root.children:
                    matches = obj.find_all_matching_nodes(pattern)
                    search_results.extend(matches)
                
                if search_results:
                    search_idx = 0
                    target_node = search_results[search_idx]
                    expand_path_to_node(target_node)
                    visible_nodes = build_visible_list(root)
                    cursor_idx = visible_nodes.index(target_node)
                    root_obj = target_node.get_root_object()
                    status_msg = f"Найдено {len(search_results)} в obj[{root_obj.index}] (1/{len(search_results)})"
                else:
                    status_msg = f"Не найдено: '{pattern}'"
                    search_results = []
                    search_idx = -1
        elif ch == ord('n'):
            if search_results and search_idx >= 0:
                search_idx = (search_idx + 1) % len(search_results)
                target_node = search_results[search_idx]
                expand_path_to_node(target_node)
                visible_nodes = build_visible_list(root)
                cursor_idx = visible_nodes.index(target_node)
                root_obj = target_node.get_root_object()
                status_msg = f"obj[{root_obj.index}] ({search_idx+1}/{len(search_results)})"
            else:
                status_msg = "Нет результатов поиска. Нажмите 's'"
        elif ch == ord('p'):
            if search_results and search_idx >= 0:
                search_idx = (search_idx - 1) % len(search_results)
                target_node = search_results[search_idx]
                expand_path_to_node(target_node)
                visible_nodes = build_visible_list(root)
                cursor_idx = visible_nodes.index(target_node)
                root_obj = target_node.get_root_object()
                status_msg = f"obj[{root_obj.index}] ({search_idx+1}/{len(search_results)})"
            else:
                status_msg = "Нет результатов поиска. Нажмите 's'"
        elif ch == curses.KEY_NPAGE:
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                current_obj = current_node.get_root_object()
                current_obj_idx = current_obj.index
                
                if current_obj_idx < len(root.children) - 1:
                    rel_path = current_node.get_relative_path_with_state()
                    next_obj_idx = current_obj_idx + 1
                    next_obj = root.children[next_obj_idx]
                    target_node = navigate_by_path_with_state(next_obj, rel_path)
                    visible_nodes = build_visible_list(root)
                    if target_node and target_node in visible_nodes:
                        cursor_idx = visible_nodes.index(target_node)
                    else:
                        cursor_idx = visible_nodes.index(next_obj)
        elif ch == curses.KEY_PPAGE:
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                current_obj = current_node.get_root_object()
                current_obj_idx = current_obj.index
                
                if current_obj_idx > 0:
                    rel_path = current_node.get_relative_path_with_state()
                    prev_obj_idx = current_obj_idx - 1
                    prev_obj = root.children[prev_obj_idx]
                    target_node = navigate_by_path_with_state(prev_obj, rel_path)
                    visible_nodes = build_visible_list(root)
                    if target_node and target_node in visible_nodes:
                        cursor_idx = visible_nodes.index(target_node)
                    else:
                        cursor_idx = visible_nodes.index(prev_obj)


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
