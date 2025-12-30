#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TUI JSON viewer - исправлены: поиск только по полю, автозагрузка при скроллинге.
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
        node = self
        while node.parent and node.depth > 0:
            node = node.parent
        return node

    def get_relative_path_with_state(self):
        path = []
        node = self
        root_obj = self.get_root_object()
        while node != root_obj and node.parent:
            path.append((node.key, node.depth, node.expanded))
            node = node.parent
        return list(reversed(path))

    def expand_all(self):
        if self.is_leaf():
            return
        self.expanded = True
        if not self.children:
            self.build_children()
        for child in self.children:
            child.expand_all()

    def collapse_all(self):
        self.expanded = False
        if self.children:
            for child in self.children:
                child.collapse_all()


class LazyJsonFile:
    """Ленивая загрузка JSON объектов."""
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._offsets = []
        self._count = 0
        self._cache = {}
        self._cache_size = 200
        self._build_index()
    
    def _build_index(self):
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
        
        self._is_single = False
        with open(self.filepath, 'rb') as f:
            while True:
                pos = f.tell()
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
        if index in self._cache:
            return self._cache[index]
        
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        
        with open(self.filepath, 'rb') as f:
            f.seek(self._offsets[index])
            line = f.readline()
            obj = json.loads(line)
            self._cache[index] = obj
            return obj
    
    def search_by_field(self, field_name: str, pattern_str: str, max_results: int = 1000):
        """ИСПРАВЛЕНО: поиск ТОЛЬКО по конкретному полю."""
        matches = []
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
            
            # Поиск ТОЛЬКО указанного поля
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
                    # ПРОВЕРКА: совпадает ли имя поля
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
                            matches.append((i, path, data))
            
            search_recursive(obj)
        
        return matches


def build_visible_list(root) -> List['JsonNode']:
    visible = []
    def walk(node):
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


def navigate_by_path_with_state(root_obj, rel_path):
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


def expand_path_to_node(node):
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


def find_node_by_path(root_obj, path_str: str):
    """Находит узел по строковому пути типа 'NotebookApp.password'."""
    if not path_str:
        return root_obj
    
    parts = []
    for part in path_str.split('.'):
        if '[' in part:
            key = part.split('[')[0]
            if key:
                parts.append(key)
            idx_part = part.split('[')[1].rstrip(']')
            parts.append(f"[{idx_part}]")
        else:
            parts.append(part)
    
    current = root_obj
    if not current.expanded:
        current.toggle()
    
    for part in parts:
        if not current.children:
            current.build_children()
        
        if not current.expanded:
            current.expanded = True
        
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
    curses.echo()
    curses.curs_set(1)
    stdscr.addstr(y, x, prompt)
    stdscr.refresh()
    
    input_win = curses.newwin(1, max_len, y, x + len(prompt))
    input_win.keypad(True)
    
    result = ""
    while True:
        ch = input_win.getch()
        if ch in (10, 13):
            break
        elif ch == 27:
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


def draw(stdscr, visible_nodes, cursor_idx: int, top_idx: int, 
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
    
    status = f"Текущий: [{current_obj_idx}] | Объектов: {total_objects} | Узлов: {len(visible_nodes)} | {cursor_idx+1}/{len(visible_nodes) or 1}"
    stdscr.addnstr(h-2, 0, status[:w-1], w-1, curses.A_BOLD)
    
    controls = "↑↓ →← a:cur+ z:cur- A:ALL+ Z:ALL- g Home/End s:search n/p q:quit"
    stdscr.addnstr(h-1, 0, controls[:w-1], w-1, curses.A_BOLD)
    
    stdscr.refresh()
    return top_idx


def load_object_into_tree(json_file, root, obj_idx, loaded_objects):
    """Загружает объект в дерево если еще не загружен."""
    if obj_idx not in loaded_objects and obj_idx < len(json_file):
        obj = json_file[obj_idx]
        node = JsonNode("record", obj, root, 0, obj_idx)
        root.children.append(node)
        loaded_objects.add(obj_idx)
        root.children.sort(key=lambda n: n.index)
        return node
    else:
        return next((n for n in root.children if n.index == obj_idx), None)


def ensure_next_objects_loaded(json_file, root, loaded_objects, current_max_idx, batch_size=5):
    """НОВОЕ: Подгружает следующие объекты если приближаемся к концу."""
    next_idx = current_max_idx + 1
    for i in range(batch_size):
        if next_idx + i < len(json_file):
            load_object_into_tree(json_file, root, next_idx + i, loaded_objects)


def main(stdscr, json_file: LazyJsonFile, filename: str):
    curses.curs_set(0)
    stdscr.keypad(True)

    if len(json_file) == 0:
        stdscr.addstr(5, 5, "ОШИБКА: Нет JSON объектов!", curses.A_BOLD)
        stdscr.refresh()
        stdscr.getch()
        return

    root = JsonNode("root", None, depth=-1)
    root.children = []
    loaded_objects = set()
    
    # Предзагрузка
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

    cursor_idx = 0
    top_idx = 0
    status_msg = ""
    
    search_results = []
    search_idx = -1
    current_field_name = None  # Запоминаем имя поля для поиска

    while True:
        visible_nodes = build_visible_list(root)
        if cursor_idx >= len(visible_nodes):
            cursor_idx = max(0, len(visible_nodes) - 1)

        current_obj_idx = 0
        if visible_nodes:
            current_node = visible_nodes[cursor_idx]
            root_obj = current_node.get_root_object()
            current_obj_idx = root_obj.index

        top_idx = draw(stdscr, visible_nodes, cursor_idx, top_idx, 
                      len(json_file), current_obj_idx, filename, status_msg)
        status_msg = ""

        ch = stdscr.getch()
        
        if ch in (ord('q'), ord('Q'), 27):
            break
        elif ch in (curses.KEY_UP, ord('k')):
            cursor_idx = max(0, cursor_idx - 1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            # ИСПРАВЛЕНО: автозагрузка при движении вниз
            if cursor_idx < len(visible_nodes) - 1:
                cursor_idx += 1
            
            # Проверяем: приближаемся к концу загруженных объектов?
            if visible_nodes and cursor_idx >= len(visible_nodes) - 5:
                # Находим максимальный индекс загруженного объекта
                max_loaded = max(loaded_objects) if loaded_objects else -1
                ensure_next_objects_loaded(json_file, root, loaded_objects, max_loaded, 5)
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
        elif ch == ord('a'):
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                root_obj = current_node.get_root_object()
                root_obj.expand_all()
                status_msg = f"Развернут объект [{root_obj.index}]"
        elif ch == ord('z'):
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
        elif ch == ord('A'):
            h_local, w_local = stdscr.getmaxyx()
            status_msg = f"Загрузка всех {len(json_file)} объектов..."
            stdscr.addnstr(h_local-3, 0, status_msg, w_local-1, curses.A_BOLD)
            stdscr.refresh()
            
            for i in range(len(json_file)):
                load_object_into_tree(json_file, root, i, loaded_objects)
            
            for obj_node in root.children:
                obj_node.expand_all()
            status_msg = f"Развернуты ВСЕ {len(json_file)} объектов"
        elif ch == ord('Z'):
            for obj_node in root.children:
                obj_node.collapse_all()
            visible_nodes = build_visible_list(root)
            if visible_nodes:
                cursor_idx = 0
            status_msg = "Свернуты все объекты"
        elif ch == ord('g'):
            h_local, w_local = stdscr.getmaxyx()
            obj_num_str = input_string(stdscr, "Объект #: ", h_local-3, 0, 10)
            if obj_num_str and obj_num_str.isdigit():
                obj_num = int(obj_num_str)
                if 0 <= obj_num < len(json_file):
                    target_obj = load_object_into_tree(json_file, root, obj_num, loaded_objects)
                    if target_obj:
                        if not target_obj.expanded:
                            target_obj.toggle()
                        visible_nodes = build_visible_list(root)
                        cursor_idx = visible_nodes.index(target_obj)
                        status_msg = f"Переход к объекту [{obj_num}]"
                else:
                    status_msg = f"Объект [{obj_num}] не существует!"
        elif ch == curses.KEY_END:
            last_idx = len(json_file) - 1
            last_obj = load_object_into_tree(json_file, root, last_idx, loaded_objects)
            if last_obj:
                if not last_obj.expanded:
                    last_obj.toggle()
                visible_nodes = build_visible_list(root)
                cursor_idx = visible_nodes.index(last_obj)
                status_msg = f"Переход к последнему объекту [{last_idx}]"
        elif ch == curses.KEY_HOME:
            first_obj = load_object_into_tree(json_file, root, 0, loaded_objects)
            if first_obj:
                if not first_obj.expanded:
                    first_obj.toggle()
                visible_nodes = build_visible_list(root)
                cursor_idx = visible_nodes.index(first_obj)
                status_msg = "Переход к первому объекту [0]"
        elif ch == ord('s'):
            # ИСПРАВЛЕНО: запоминаем имя поля под курсором
            if visible_nodes:
                current_node = visible_nodes[cursor_idx]
                current_field_name = current_node.key
                
                h_local, w_local = stdscr.getmaxyx()
                pattern = input_string(stdscr, f"Поиск '{current_field_name}' (regex): ", h_local-3, 0, 40)
                
                if pattern:
                    status_msg = f"Поиск '{current_field_name}' по всем объектам..."
                    stdscr.addnstr(h_local-3, 0, status_msg, w_local-1, curses.A_BOLD)
                    stdscr.refresh()
                    
                    # ИСПРАВЛЕНО: поиск ТОЛЬКО по указанному полю
                    raw_matches = json_file.search_by_field(current_field_name, pattern, 1000)
                    
                    if raw_matches:
                        search_results = []
                        for obj_idx, path_str, value in raw_matches:
                            obj_node = load_object_into_tree(json_file, root, obj_idx, loaded_objects)
                            if obj_node:
                                target_node = find_node_by_path(obj_node, path_str)
                                if target_node:
                                    search_results.append(target_node)
                        
                        if search_results:
                            search_idx = 0
                            target_node = search_results[search_idx]
                            expand_path_to_node(target_node)
                            visible_nodes = build_visible_list(root)
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
                
                if current_obj_idx < len(json_file) - 1:
                    rel_path = current_node.get_relative_path_with_state()
                    next_obj_idx = current_obj_idx + 1
                    next_obj = load_object_into_tree(json_file, root, next_obj_idx, loaded_objects)
                    if next_obj:
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
                    prev_obj = load_object_into_tree(json_file, root, prev_obj_idx, loaded_objects)
                    if prev_obj:
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

    json_file = LazyJsonFile(path)
    if len(json_file) == 0:
        print("Не найдено валидных JSON!")
        sys.exit(1)

    curses.wrapper(main, json_file, path)


if __name__ == "__main__":
    run()
