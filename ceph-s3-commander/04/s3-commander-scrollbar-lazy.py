#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Двухпанельный файловый менеджер для S3 Ceph с поддержкой множественных endpoints
"""

import os
import sys
import re
import fnmatch
import urwid
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from datetime import datetime
import tempfile
import shutil
import json
import threading
import time
import platform

__VERSION__ = "1.0.1"
__AUTHOR__ = "Тарасов Дмитрий"


import socket
from urllib.parse import urlparse
import functools
from collections import OrderedDict


def check_s3_endpoint_connectivity(endpoint_url, timeout=2):
    """
    Быстрая проверка доступности S3 endpoint.
    
    Args:
        endpoint_url: URL эндпоинта (например, 'http://10.0.0.1:7480')
        timeout: таймаут подключения в секундах
    
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    try:
        parsed = urlparse(endpoint_url)
        host = parsed.hostname
        port = parsed.port
        
        # Определяем порт по умолчанию
        if port is None:
            port = 443 if parsed.scheme == 'https' else 80
        
        # TCP проверка подключения
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            return (True, None)
        else:
            return (False, f"Cannot connect to {host}:{port}")
            
    except socket.gaierror:
        return (False, f"Cannot resolve hostname: {parsed.hostname}")
    except socket.timeout:
        return (False, f"Connection timeout to {parsed.hostname}:{port}")
    except Exception as e:
        return (False, f"Connection error: {str(e)}")

def get_focus_button(w):
    # Разворачиваем до тела (Pile)
    if isinstance(w, urwid.AttrMap):
        w = w.original_widget        # LineBox
    if isinstance(w, urwid.LineBox):
        w = w.original_widget        # Filler
    if isinstance(w, urwid.Filler):
        w = w.body                   # Pile

    # Если это Pile — пробуем понять, где фокус
    if isinstance(w, urwid.Pile):
        focus_result = w.get_focus()
        # В разных версиях urwid это либо (widget, index), либо просто widget
        if isinstance(focus_result, tuple):
            focused_widget = focus_result[0]
        else:
            focused_widget = focus_result

        # В строке с кнопками у нас Columns
        if isinstance(focused_widget, urwid.Columns):
            col_focus = focused_widget.get_focus()
            # Аналогично: либо (widget, index), либо widget
            if isinstance(col_focus, tuple):
                focus_w = col_focus[0]
            else:
                focus_w = col_focus

            # focus_w обычно AttrMap(button, 'button', focus_map=...)
            if isinstance(focus_w, urwid.AttrMap):
                btn = focus_w.original_widget
            else:
                btn = focus_w
            return btn
    return None

class S3Config:
    """Управление конфигурацией S3 endpoints"""
    
    def __init__(self, config_file='s3_config.json'):
        self.config_file = config_file
        self.endpoints = []
        self.load_config()
    
    def load_config(self):
        """Загрузить конфигурацию из файла"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.endpoints = data.get('endpoints', [])
            except Exception as e:
                print(f"Error loading config: {e}")
                self.create_default_config()
        else:
            self.create_default_config()
    
    def create_default_config(self):
        """Создать конфигурацию по умолчанию"""
        self.endpoints = [
            {
                'name': 'Local Ceph',
                'url': 'http://localhost:7480',
                'access_key': 's3access',
                'secret_key': 's3secret'
            }
        ]
        self.save_config()
    
    def save_config(self):
        """Сохранить конфигурацию в файл"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump({'endpoints': self.endpoints}, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get_endpoints(self):
        """Получить список endpoints"""
        return self.endpoints
    
    def get_endpoint(self, name):
        """Получить endpoint по имени"""
        for ep in self.endpoints:
            if ep['name'] == name:
                return ep
        return None



class LRUCache:
    """Простой LRU кеш для хранения результатов запросов к S3"""
    def __init__(self, maxsize=100):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)

    def invalidate(self, pattern=None):
        """Инвалидация кеша по паттерну"""
        if pattern is None:
            self.cache.clear()
        else:
            keys_to_remove = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self.cache[key]

class S3Manager:
    """Менеджер для работы с S3 Ceph"""
    
    def __init__(self, endpoint_config):
        self.endpoint_name = endpoint_config['name']
        self.endpoint_url = endpoint_config['url']
        self.access_key = endpoint_config['access_key']
        self.secret_key = endpoint_config['secret_key']
        self.is_connected = False
        self.connection_error = None
        
        # Кеш для списков объектов
        self.object_cache = LRUCache(maxsize=100)
        self.bucket_cache = LRUCache(maxsize=10)
        
        # БЫСТРАЯ ПРОВЕРКА: доступен ли endpoint перед созданием клиента
        can_connect, error_msg = check_s3_endpoint_connectivity(self.endpoint_url, timeout=2)
        
        if not can_connect:
            self.s3_client = None
            self.connection_error = error_msg
            return

        try:
            # Настройка коротких таймаутов для boto3
            config = Config(
                connect_timeout=3,
                read_timeout=10,
                retries={'max_attempts': 1}  # Только 1 попытка
            )

            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=config
            )
        except Exception as e:
            self.s3_client = None
            self.connection_error = str(e)

    def list_buckets(self):
        if self.s3_client is None:
            return []
        try:
            response = self.s3_client.list_buckets()
            self.is_connected = True
            return response['Buckets']
        except (ClientError, Exception) as e:
            self.is_connected = False
            self.connection_error = str(e)
            return []

    def create_bucket(self, bucket_name):
        if self.s3_client is None:
            return False
        try:
            self.s3_client.create_bucket(Bucket=bucket_name)
            return True
        except (ClientError, Exception):
            return False

    def delete_bucket(self, bucket_name):
        if self.s3_client is None:
            return False
        try:
            self.s3_client.delete_bucket(Bucket=bucket_name)
            return True
        except (ClientError, Exception):
            return False

    def list_objects(self, bucket_name, prefix=''):
        if self.s3_client is None:
            return [], []
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
            
            folders = []
            files = []
            
            for page in pages:
                if 'CommonPrefixes' in page:
                    for obj in page['CommonPrefixes']:
                        folders.append({'Key': obj['Prefix']})
                
                if 'Contents' in page:
                    for obj in page['Contents']:
                        if not obj['Key'].endswith('/') and obj['Key'] != prefix:
                            files.append(obj)
            
            return folders, files
        except (ClientError, Exception):
            return [], []

    def list_all_objects(self, bucket_name, prefix=''):
        if self.s3_client is None:
            return []
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
            
            objects = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        if obj['Key'] != prefix:
                            objects.append(obj)
            
            return objects
        except (ClientError, Exception):
            return []


    def count_objects(self, bucket_name, prefix=''):
        """Быстрый подсчет количества объектов без загрузки данных

        Args:
            bucket_name: имя бакета
            prefix: префикс для фильтрации

        Returns:
            tuple: (total_objects, total_size) или (None, None) при ошибке
        """
        if self.s3_client is None:
            return None, None

        # Проверяем кеш
        cache_key = f"count:{bucket_name}:{prefix}"
        cached = self.object_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            total_objects = 0
            total_size = 0

            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            for page in pages:
                if 'Contents' in page:
                    total_objects += len(page['Contents'])
                    total_size += sum(obj.get('Size', 0) for obj in page['Contents'])

            result = (total_objects, total_size)
            self.object_cache.put(cache_key, result)
            return result

        except (ClientError, Exception):
            return None, None

    def list_objects_lazy(self, bucket_name, prefix='', page_size=1000):
        """Ленивая загрузка объектов с использованием генератора"""
        if self.s3_client is None:
            yield [], []
            return

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=bucket_name, 
                Prefix=prefix, 
                Delimiter='/',
                PaginationConfig={'PageSize': page_size}
            )

            for page in page_iterator:
                folders = []
                files = []

                if 'CommonPrefixes' in page:
                    for obj in page['CommonPrefixes']:
                        folders.append({'Key': obj['Prefix']})

                if 'Contents' in page:
                    for obj in page['Contents']:
                        if not obj['Key'].endswith('/') and obj['Key'] != prefix:
                            files.append(obj)

                yield folders, files

        except (ClientError, Exception):
            yield [], []

    def invalidate_cache(self, bucket_name=None, prefix=None):
        """Инвалидация кеша после операций изменения"""
        if bucket_name is None:
            self.object_cache.invalidate()
            self.bucket_cache.invalidate()
        else:
            pattern = f"{bucket_name}:"
            if prefix:
                pattern += prefix
            self.object_cache.invalidate(pattern)

    def object_exists(self, bucket_name, key):
        """Проверить существование объекта и вернуть его метаданные"""
        if self.s3_client is None:
            return None
        try:
            response = self.s3_client.head_object(Bucket=bucket_name, Key=key)
            return {
                'Size': response['ContentLength'],
                'LastModified': response['LastModified']
            }
        except:
            return None

    def list_object_versions(self, bucket_name, key):
        """Получить список версий объекта"""
        if self.s3_client is None:
            return []
        try:
            response = self.s3_client.list_object_versions(Bucket=bucket_name, Prefix=key)
            versions = []
            if 'Versions' in response:
                for v in response['Versions']:
                    if v['Key'] == key:
                        versions.append(v)
            return versions
        except (ClientError, Exception):
            return []

    def download_object(self, bucket_name, key, local_path, version_id=None):
        if self.s3_client is None:
            return False
        try:
            extra_args = {}
            if version_id:
                extra_args['VersionId'] = version_id
            self.s3_client.download_file(bucket_name, key, local_path, ExtraArgs=extra_args)
            return True
        except (ClientError, Exception):
            return False

    def upload_file(self, local_path, bucket_name, key):
        if self.s3_client is None:
            return False
        try:
            self.s3_client.upload_file(local_path, bucket_name, key)
            self.invalidate_cache(bucket_name)
            return True
        except (ClientError, Exception):
            return False

    def copy_object(self, source_bucket, source_key, dest_bucket, dest_key, version_id=None):
        if self.s3_client is None:
            return False
        try:
            copy_source = {'Bucket': source_bucket, 'Key': source_key}
            if version_id:
                copy_source['VersionId'] = version_id
            self.s3_client.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key)
            self.invalidate_cache(dest_bucket)
            return True
        except (ClientError, Exception):
            return False

    def delete_object(self, bucket_name, key, version_id=None):
        if self.s3_client is None:
            return False
        try:
            extra_args = {}
            if version_id:
                extra_args['VersionId'] = version_id
            self.s3_client.delete_object(Bucket=bucket_name, Key=key, **extra_args)
            self.invalidate_cache(bucket_name)
            return True
        except (ClientError, Exception):
            return False

    def delete_old_versions(self, bucket_name, key):
        """Удалить все версии кроме последней"""
        if self.s3_client is None:
            return 0
        try:
            versions = self.list_object_versions(bucket_name, key)
            if len(versions) <= 1:
                return 0
            
            versions.sort(key=lambda x: x.get('LastModified', datetime.min), reverse=True)
            
            deleted_count = 0
            for version in versions[1:]:
                if self.delete_object(bucket_name, key, version['VersionId']):
                    deleted_count += 1
            
            return deleted_count
        except (ClientError, Exception):
            return 0

    def enable_versioning(self, bucket_name):
        """Включить версионирование для бакета"""
        if self.s3_client is None:
            return False
        try:
            self.s3_client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )
            return True
        except (ClientError, Exception):
            return False
    
    def disable_versioning(self, bucket_name):
        """Отключить версионирование для бакета (установить в Suspended)"""
        if self.s3_client is None:
            return False
        try:
            self.s3_client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Suspended'}
            )
            return True
        except (ClientError, Exception):
            return False

    def get_versioning_status(self, bucket_name):
        """Получить статус версионирования бакета"""
        if self.s3_client is None:
            return None
        try:
            response = self.s3_client.get_bucket_versioning(Bucket=bucket_name)
            return response.get('Status', 'Disabled')
        except (ClientError, Exception):
            return None

class FileSystemBrowser:
    """Браузер локальной файловой системы"""
    
    def __init__(self):
        self.current_path = os.path.expanduser('~')

    def list_directory(self):
        try:
            items = []
            if self.current_path != '/':
                items.append({'name': '..', 'is_dir': True, 'size': 0, 'mtime': None})
            
            for item in sorted(os.listdir(self.current_path)):
                full_path = os.path.join(self.current_path, item)
                try:
                    stat = os.stat(full_path)
                    is_dir = os.path.isdir(full_path)
                    items.append({
                        'name': item,
                        'is_dir': is_dir,
                        'size': 0 if is_dir else stat.st_size,
                        'mtime': datetime.fromtimestamp(stat.st_mtime)
                    })
                except (PermissionError, OSError):
                    continue
            
            return items
        except (PermissionError, OSError):
            return []

    def list_all_files(self, path):
        all_files = []
        try:
            for root, dirs, files in os.walk(path):
                for file in files:
                    full_path = os.path.join(root, file)
                    try:
                        stat = os.stat(full_path)
                        rel_path = os.path.relpath(full_path, path)
                        all_files.append({
                            'path': full_path,
                            'rel_path': rel_path,
                            'size': stat.st_size
                        })
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass
        return all_files

    def file_exists(self, file_path):
        """Проверить существование файла и вернуть его метаданные"""
        try:
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                return {
                    'size': stat.st_size,
                    'mtime': datetime.fromtimestamp(stat.st_mtime)
                }
        except:
            pass
        return None

    def create_directory(self, dir_name):
        try:
            full_path = os.path.join(self.current_path, dir_name)
            os.makedirs(full_path, exist_ok=False)
            return True
        except OSError:
            return False

def is_binary_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            if b'\x00' in chunk:
                return True
            
            non_printable = sum(1 for byte in chunk if byte < 32 and byte not in (9, 10, 13))
            if len(chunk) > 0 and non_printable / len(chunk) > 0.3:
                return True
            
            return False
    except:
        return True

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f'{size:.1f} {unit}'
        size /= 1024.0
    return f'{size:.1f} PB'



class ScrollBar(urwid.WidgetDecoration):
    """Вертикальный scrollbar для urwid ListBox"""

    def __init__(self, widget):
        """
        Args:
            widget: базовый виджет (обычно ListBox)
        """
        self.__super.__init__(widget)
        self.scrollbar_width = 1

    def render(self, size, focus=False):
        maxcol, maxrow = size

        # Рендерим основной виджет
        canvas = self._original_widget.render((maxcol - self.scrollbar_width, maxrow), focus)

        # Получаем информацию о позиции скролла
        if hasattr(self._original_widget, 'body'):
            # Для ListBox
            middle, top, bottom = self._original_widget.calculate_visible(
                (maxcol - self.scrollbar_width, maxrow), focus
            )

            if middle is None:
                return canvas

            # Получаем общее количество элементов
            try:
                total_rows = len(self._original_widget.body)
            except:
                total_rows = maxrow

            if total_rows == 0:
                return canvas

            # Вычисляем параметры scrollbar
            visible_rows = maxrow

            if total_rows <= visible_rows:
                thumb_height = maxrow
                thumb_top = 0
            else:
                thumb_height = max(1, int(visible_rows * visible_rows / total_rows))

                try:
                    focus_position = self._original_widget.body.focus
                    if focus_position is None:
                        focus_position = 0
                except:
                    focus_position = 0

                scrollable_area = maxrow - thumb_height
                if total_rows > visible_rows:
                    scroll_ratio = focus_position / (total_rows - 1) if total_rows > 1 else 0
                    thumb_top = int(scroll_ratio * scrollable_area)
                else:
                    thumb_top = 0

            # Создаем scrollbar
            scrollbar_canvas = self._create_scrollbar(maxrow, thumb_top, thumb_height)

            # Комбинируем canvas
            combined = urwid.CanvasJoin([
                (canvas, None, False, maxcol - self.scrollbar_width),
                (scrollbar_canvas, None, False, self.scrollbar_width)
            ])

            return combined

        return canvas


    def _create_scrollbar(self, height, thumb_top, thumb_height):
        parts = []
        
        # Верхний трек
        if thumb_top > 0:
            track_top = urwid.SolidCanvas('│', 1, thumb_top)
            track_top = urwid.CompositeCanvas(track_top)
            track_top.fill_attr('scrollbar_track')
            parts.append((track_top, None, False))
        
        # Ползунок
        if thumb_height > 0:
            thumb = urwid.SolidCanvas('█', 1, thumb_height)
            thumb = urwid.CompositeCanvas(thumb)
            thumb.fill_attr('scrollbar_thumb')
            parts.append((thumb, None, False))
        
        # Нижний трек
        track_bottom_height = height - thumb_top - thumb_height
        if track_bottom_height > 0:
            track_bottom = urwid.SolidCanvas('│', 1, track_bottom_height)
            track_bottom = urwid.CompositeCanvas(track_bottom)
            track_bottom.fill_attr('scrollbar_track')
            parts.append((track_bottom, None, False))
    
        return urwid.CanvasCombine(parts)



    def selectable(self):
        return self._original_widget.selectable()

    def keypress(self, size, key):
        maxcol, maxrow = size
        return self._original_widget.keypress((maxcol - self.scrollbar_width, maxrow), key)

    def mouse_event(self, size, event, button, col, row, focus):
        maxcol, maxrow = size
        if col < maxcol - self.scrollbar_width:
            return self._original_widget.mouse_event(
                (maxcol - self.scrollbar_width, maxrow),
                event, button, col, row, focus
            )
        return False

class SelectableText(urwid.Text):
    def __init__(self, text, data, panel):
        super().__init__(text)
        self.data = data
        self.panel = panel
        self.selected = False
    
    def selectable(self):
        return True
    
    def keypress(self, size, key):
        if key == 'enter':
            self.panel.on_item_activated(self.data)
            return None
        elif key == 'insert' and self.data.get('can_select'):
            self.selected = not self.selected
            self.panel.update_item_display(self)
            return 'down'
        elif key == ' ' and self.data.get('can_select'):
            self.selected = not self.selected
            self.panel.update_item_display(self)
            return None
        return key


class FileViewerDialog(urwid.WidgetWrap):
    def __init__(self, title, content, callback):
        self.callback = callback
        
        text_widget = urwid.Text(content)
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker([text_widget]))
        
        close_button = urwid.Button('Close (ESC)')
        urwid.connect_signal(close_button, 'click', self.on_close)
        
        pile = urwid.Pile([
            ('weight', 1, urwid.LineBox(listbox, title)),
            ('pack', urwid.AttrMap(close_button, None, focus_map='selected'))
        ])
        
        super().__init__(urwid.AttrMap(pile, 'dialog'))
    
    def on_close(self, button):
        self.callback()
    
    def keypress(self, size, key):
        if key == 'esc':
            self.callback()
            return None
        return super().keypress(size, key)


class VersionSelectDialog(urwid.WidgetWrap):
    """Диалог выбора версии для просмотра/удаления"""
    def __init__(self, file_data, versions, callback):
        self.file_data = file_data
        self.versions = versions
        self.callback = callback
        self.selected_version = None
        
        # Создаем список версий как radio buttons
        self.radio_group = []
        version_buttons = []
        
        for idx, v in enumerate(versions):
            is_latest = v.get('IsLatest', False)
            latest_mark = "[LATEST] " if is_latest else ""
            size = format_size(v.get('Size', 0))
            mtime = v.get('LastModified', '').strftime('%Y-%m-%d %H:%M:%S') if v.get('LastModified') else ''
            version_id = v.get('VersionId', '')[:12]
            
            label = f"{latest_mark}{version_id}  {size:>10}  {mtime}"
            
            rb = urwid.RadioButton(self.radio_group, label, state=(idx == 0))
            rb.version_data = v
            version_buttons.append(('pack', urwid.AttrMap(rb, None, focus_map='selected')))
        
        # Кнопки управления
        view_button = urwid.Button("[ View ]")
        delete_button = urwid.Button("[ Delete ]")
        cancel_button = urwid.Button("[ Cancel ]")
        
        urwid.connect_signal(view_button, 'click', self.on_view)
        urwid.connect_signal(delete_button, 'click', self.on_delete)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)
        
        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(view_button, 'button', focus_map='buttonfocus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(delete_button, 'button', focus_map='buttonfocus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='buttonfocus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)
        
        # Собираем диалог
        content = [
            ('pack', urwid.Divider()),
            ('pack', urwid.Text(f"Total versions: {len(versions)}")),
            ('pack', urwid.Divider()),
        ]
        content.extend(version_buttons)
        content.extend([
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])
        title = f"Select version: {file_data['name']}"
        pile = urwid.Pile(content)
        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill, title=title)
        
        super().__init__(urwid.AttrMap(linebox, 'dialog'))
    
    def get_selected_version(self):
        """Получить выбранную версию"""
        for rb in self.radio_group:
            if rb.state:
                return rb.version_data
        return None
    
    def on_view(self, button):
        version_data = self.get_selected_version()
        self.callback('view', version_data)
    
    def on_delete(self, button):
        version_data = self.get_selected_version()
        if version_data:
            self.callback('delete', version_data)
    
    def on_cancel(self, button):
        self.callback('cancel', None)

    def keypress(self, size, key):
        if key == 'enter':
            btn = get_focus_button(self._w)
            if btn != None:
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Cancel ]':
                    # Enter на Cancel -> отмена
                    self.on_cancel(None)
                    return None
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Delete ]':
                    # Enter на Delete -> удаление
                    self.on_delete(None)
                    return None
            # Все остальные случаи: Enter -> OK
            self.on_view(None)
            return None
        elif key == 'esc':
            self.on_cancel(None)
            return None
        elif key == 'f8':
            self.on_delete(None)
            return None
        return super().keypress(size, key)


class OverwriteDialog(urwid.WidgetWrap):
    """Диалог подтверждения перезаписи файла"""

    def __init__(self, filename, source_info, dest_info, callback, show_version_options=False):
        self.callback = callback

        title_text = urwid.Text('File already exists!', align='center')
        file_text = urwid.Text(f'File: {filename}')

        src_size = source_info.get("size", 0)
        dst_size = dest_info.get("size", 0)

        src_mtime = source_info.get("mtime")
        dst_mtime = dest_info.get("mtime")

        src_time_str = src_mtime.strftime("%Y-%m-%d %H:%M:%S") if src_mtime else "N/A"
        dst_time_str = dst_mtime.strftime("%Y-%m-%d %H:%M:%S") if dst_mtime else "N/A"

        source_text = urwid.Text( f'Source: {format_size(src_size)} | {src_time_str}' )
        dest_text = urwid.Text( f'Target: {format_size(dst_size)} | {dst_time_str}' )

        buttons_list = []

        overwrite_button = urwid.Button('[ Overwrite ]')
        all_button = urwid.Button('[ All ]')
        urwid.connect_signal(overwrite_button, 'click', lambda b: self.on_choice('overwrite'))
        urwid.connect_signal(all_button, 'click', lambda b: self.on_choice('all'))
        buttons_list.extend([
            ('pack', urwid.AttrMap(overwrite_button, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(all_button, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
        ])

        if show_version_options:
            version_button = urwid.Button('[ New Version ]')
            version_all_button = urwid.Button('[ Version All ]')
            urwid.connect_signal(version_button, 'click', lambda b: self.on_choice('version'))
            urwid.connect_signal(version_all_button, 'click', lambda b: self.on_choice('version_all'))
            buttons_list.extend([
                ('pack', urwid.AttrMap(version_button, 'button', focus_map='button_focus')),
                ('fixed', 1, urwid.Text('')),
                ('pack', urwid.AttrMap(version_all_button, 'button', focus_map='button_focus')),
                ('fixed', 1, urwid.Text('')),
            ])

        skip_button = urwid.Button('[ Skip ]')
        skip_all_button = urwid.Button('[ Skip All ]')
        cancel_button = urwid.Button('[ Cancel ]')
        urwid.connect_signal(skip_button, 'click', lambda b: self.on_choice('skip'))
        urwid.connect_signal(skip_all_button, 'click', lambda b: self.on_choice('skip_all'))
        urwid.connect_signal(cancel_button, 'click', lambda b: self.on_choice('cancel'))
        buttons_list.extend([
            ('pack', urwid.AttrMap(skip_button, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(skip_all_button, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='button_focus')),
        ])

        buttons_list.insert(0, ('weight', 1, urwid.Text('')))
        buttons_list.append(('weight', 1, urwid.Text('')))

        buttons = urwid.Columns(buttons_list, dividechars=0)

        pile = urwid.Pile([
            ('pack', urwid.Divider()),
            ('pack', title_text),
            ('pack', urwid.Divider()),
            ('pack', file_text),
            ('pack', urwid.Divider()),
            ('pack', source_text),
            ('pack', dest_text),
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])
        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill)

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def on_choice(self, choice):
        self.callback(choice)

    def keypress(self, size, key):
        if key == 'esc':
            self.callback('cancel')
            return None
        return super().keypress(size, key)


class ProgressDialog(urwid.WidgetWrap):
    """Диалог прогресса операций в стиле MC"""
    
    def __init__(self, title, callback=None):
        self.callback = callback
        self.title_text = urwid.Text(title, align='center')
        self.progress_text = urwid.Text('', align='left')
        self.file_text = urwid.Text('', align='left')
        self.stats_text = urwid.Text('', align='left')
        self.bytes_text = urwid.Text('', align='left')
        
        self.total_files = 0
        self.processed_files = 0
        self.success_count = 0
        self.fail_count = 0
        self.current_file = ''
        self.total_bytes = 0
        self.processed_bytes = 0
        self.start_time = time.time()
        
        skip_button = urwid.Button('[ Skip ]')
        cancel_button = urwid.Button('[ Cancel ]')
        
        self.cancelled = False
        
        urwid.connect_signal(skip_button, 'click', lambda b: None)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)
        
        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(skip_button, 'button', focus_map='button_focus')),
            ('fixed', 2, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='button_focus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)
        
        pile = urwid.Pile([
            ('pack', urwid.Divider()),
            ('pack', self.title_text),
            ('pack', urwid.Divider()),
            ('pack', self.progress_text),
            ('pack', self.file_text),
            ('pack', urwid.Divider()),
            ('pack', self.stats_text),
            ('pack', self.bytes_text),
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])


        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill)
        
        super().__init__(urwid.AttrMap(linebox, 'dialog'))
    
    def on_cancel(self, button):
        self.cancelled = True
        if self.callback:
            self.callback()
    
    def keypress(self, size, key):
        if key == 'esc':
            self.on_cancel(None)
            return None
        return super().keypress(size, key)
    
    def get_speed_str(self):
        """Получить строку скорости передачи"""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            speed = self.processed_bytes / elapsed
            return f'{format_size(speed)}/s'
        return '0 B/s'
    
    def update(self, current_file='', file_size=0):
        if current_file:
            self.current_file = current_file
            self.processed_files += 1
            self.processed_bytes += file_size
        
        if self.total_files > 0:
            percent = int((self.processed_files / self.total_files) * 100)
            bar_width = 40
            filled = int((self.processed_files / self.total_files) * bar_width)
            bar = '█' * filled + '░' * (bar_width - filled)
            self.progress_text.set_text(f'[{bar}] {percent}%')
        
        if self.current_file:
            display_file = self.current_file
            if len(display_file) > 60:
                display_file = '...' + display_file[-57:]
            self.file_text.set_text(f'File: {display_file}')
        
        self.stats_text.set_text(
            f'Total: {self.total_files} | Processed: {self.processed_files} | '
            f'Success: {self.success_count} | Failed: {self.fail_count}'
        )
        
        if self.total_bytes > 0:
            bytes_percent = int((self.processed_bytes / self.total_bytes) * 100) if self.total_bytes > 0 else 0
            speed_str = self.get_speed_str()
            self.bytes_text.set_text(
                f'Bytes: {format_size(self.processed_bytes)} / {format_size(self.total_bytes)} ({bytes_percent}%) | Speed: {speed_str}'
            )
    
    def set_total(self, total_files, total_bytes=0):
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.start_time = time.time()
        self.update()
    
    def add_success(self):
        self.success_count += 1
        self.update()
    
    def add_failure(self):
        self.fail_count += 1
        self.update()


class SortDialog(urwid.WidgetWrap):
    """Диалог выбора режима сортировки"""
    
    def __init__(self, current_mode, callback):
        self.callback = callback
        self.current_mode = current_mode
        
        title_text = urwid.Text('Sort by:', align='center')
        
        self.radio_group = []
        modes = [
            ('name', 'Name'),
            ('ext', 'Extension'),
            ('size', 'Size'),
            ('time', 'Time')
        ]
        
        radio_buttons = []
        for mode, label in modes:
            rb = urwid.RadioButton(self.radio_group, label, state=(mode == current_mode))
            rb.mode = mode
            radio_buttons.append(urwid.AttrMap(rb, None, focus_map='selected'))
        
        ok_button = urwid.Button('[ OK ]')
        cancel_button = urwid.Button('[ Cancel ]')
        
        urwid.connect_signal(ok_button, 'click', self.on_ok)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)
        
        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(ok_button, 'button', focus_map='button_focus')),
            ('fixed', 2, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='button_focus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)
        
        content = [
            ('pack', urwid.Divider()),
            ('pack', title_text),
            ('pack', urwid.Divider()),
        ]
        content.extend([('pack', rb) for rb in radio_buttons])
        content.extend([
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])
        pile = urwid.Pile(content)

        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill)
        
        super().__init__(urwid.AttrMap(linebox, 'dialog'))
    
    def on_ok(self, button):
        for rb in self.radio_group:
            if rb.state:
                self.callback(True, rb.mode)
                return
        self.callback(False, None)
    
    def on_cancel(self, button):
        self.callback(False, None)
    
    def keypress(self, size, key):
        if key == 'enter':
            self.on_ok(None)
            return None
        elif key == 'esc':
            self.on_cancel(None)
            return None
        return super().keypress(size, key)


class CopyMoveDialog(urwid.WidgetWrap):
    """Диалог копирования/перемещения в стиле MC"""
    
    def __init__(self, title, source_desc, dest_path, callback):
        self.callback = callback
        
        # title_text = urwid.Text(('dialog_title', title), align='center')
        source_text = urwid.Text(source_desc)
        self.dest_edit = urwid.Edit('to: ', dest_path)
        
        ok_button = urwid.Button('[ OK ]')
        cancel_button = urwid.Button('[ Cancel ]')
        
        urwid.connect_signal(ok_button, 'click', self.on_ok)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)
        
        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(ok_button, 'button', focus_map='button_focus')),
            ('fixed', 2, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='button_focus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)
        
        pile = urwid.Pile([
            ('pack', urwid.Divider()),
            # ('pack', title_text),
            # ('pack', urwid.Divider()),
            ('pack', source_text),
            ('pack', urwid.Divider()),
            ('pack', urwid.AttrMap(self.dest_edit, 'edit', focus_map='edit_focus')),
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])

        
        fill = urwid.Filler(pile, valign='top')
        linebox = urwid.LineBox(fill, title=title)
        
        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def keypress(self, size, key):
        if key == 'enter':
            btn = get_focus_button(self._w)
            if btn != None:
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Cancel ]':
                    # Enter на Cancel -> отмена
                    self.on_cancel(None)
                    return None
            # Все остальные случаи: Enter -> OK
            self.on_ok(None)
            return None

        elif key == 'esc':
            self.on_cancel(None)
            return None

        return super().keypress(size, key)

    def on_ok(self, button):
        dest = self.dest_edit.get_edit_text()
        self.callback(True, dest)

    def on_cancel(self, button):
        self.callback(False, None)


class PanelWidget(urwid.WidgetWrap):
    def __init__(self, title, panel_type='fs', s3_config=None, app=None):
        self.title = title
        self.panel_type = panel_type
        self.s3_config = s3_config
        self.s3_manager = None
        self.fs_browser = FileSystemBrowser() if panel_type == 'fs' else None
        self.app = app
        
        self.current_endpoint = None
        self.current_bucket = None
        self.current_prefix = ''
        self.mode = panel_type
        self.sort_mode = 'name'
        
        self.walker = urwid.SimpleFocusListWalker([])
        self.listbox = urwid.ListBox(self.walker)

        # Сохраняем ссылку на виджет текста, чтобы менять его позже
        self.header_text = urwid.Text(title, align='center')
        header_widget = urwid.AttrMap(self.header_text, 'header')
        
        # Путь (FS: /home/user или S3: /ceph/bucket/)
        self.path_text = urwid.Text('')
        path_widget = urwid.AttrMap(self.path_text, 'path')

        # Оборачиваем listbox в ScrollBar
        self.scrollbar = ScrollBar(self.listbox)

        self.linebox = urwid.LineBox(
            urwid.Frame(
                urwid.AttrMap(self.scrollbar, 'body'),
                header=path_widget
            )
        )

        super().__init__(self.linebox)

        
        # Поддержка ленивой загрузки
        self.loading_in_progress = False
        self.loading_thread = None
        self.lazy_generator = None



    def show_sort_dialog(self):
        """Показать диалог выбора сортировки"""
        def callback(confirmed, mode):
            self.app.close_dialog()
            if confirmed and mode:
                self.sort_mode = mode
                self.refresh()
                self.app.show_result(f'Sort by: {mode}')
        
        dialog = SortDialog(self.sort_mode, callback)
        self.app.show_dialog(dialog)

    def sort_items(self, items):
        """Сортировать элементы согласно режиму сортировки"""
        if self.sort_mode == 'name':
            return sorted(items, key=lambda x: x.get('name', x.get('key', '')).lower())
        elif self.sort_mode == 'ext':
            def get_ext(item):
                name = item.get('name', item.get('key', ''))
                if '.' in name:
                    return name.rsplit('.', 1)[1].lower()
                return ''
            return sorted(items, key=get_ext)
        elif self.sort_mode == 'size':
            return sorted(items, key=lambda x: x.get('size', x.get('Size', 0)), reverse=True)
        elif self.sort_mode == 'time':
            return sorted(items, key=lambda x: x.get('mtime', x.get('LastModified', datetime.min)), reverse=True)
        return items

    def is_root_menu(self):
        return self.mode == 'root_menu'

    def is_endpoint_list(self):
        return self.mode == 's3' and self.current_endpoint is None

    def is_bucket_list(self):
        return self.mode == 's3' and self.current_endpoint is not None and self.current_bucket is None

    def is_fs_root(self):
        return self.mode == 'fs' and self.fs_browser.current_path == '/'

    def get_current_path(self):
        """Получить текущий путь для копирования"""
        if self.mode == 's3':
            if self.current_bucket:
                return self.current_prefix if self.current_prefix else ''
            else:
                return ''
        elif self.mode == 'fs':
            return self.fs_browser.current_path
        else:
            return ''

    def update_header(self, info):
        if info:
            self.linebox.set_title(f"{self.title} {info}")
        else:
            self.linebox.set_title(self.title)

    def refresh(self, focus_on=None):
        self.walker.clear()
        
        if self.mode == 'root_menu':
            self._refresh_root_menu()
        elif self.mode == 's3':
            if self.current_endpoint is None:
                self._refresh_endpoints()
            else:
                self._refresh_s3()
        else:
            self._refresh_fs()
        
        if focus_on:
            self.set_focus_on_item(focus_on)

    def set_focus_on_item(self, item_name):
        for idx, widget in enumerate(self.walker):
            w = widget.original_widget
            if isinstance(w, SelectableText):
                data = w.data
                if data.get('name') == item_name or data.get('key', '').rstrip('/').split('/')[-1] == item_name:
                    self.listbox.set_focus(idx)
                    return

    def _refresh_root_menu(self):
        self.update_header('[Root Menu]')
        self.path_text.set_text('Select source type:')
        
        label = '[FS] Local File System'
        data = {'type': 'root_fs', 'can_select': False}
        text = SelectableText(f'  {label}', data, self)
        self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        
        self.walker.append(urwid.Divider())
        
        endpoints = self.s3_config.get_endpoints()
        for ep in endpoints:
            label = f'[S3] {ep["name"]:35} {ep["url"]}'
            data = {'type': 'root_endpoint', 'name': ep['name'], 'config': ep, 'can_select': False}
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

    def view_s3_file_version(self, file_data, version_data=None, close_callback=None):
        """Просмотр S3 файла с указанной версией"""
        version_id = version_data.get('VersionId') if version_data else None
        filename = file_data['name']
        
        if version_id:
            self.app.show_result(f"Downloading {filename} (version {version_id[:8]})...")
        else:
            self.app.show_result(f"Downloading {filename}...")
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmppath = tmp.name
            
            if self.s3_manager.download_object(
                self.current_bucket, 
                file_data['key'], 
                tmppath,
                version_id=version_id ):
                self._view_file(tmppath, filename, close_callback=close_callback)
                try:
                    os.unlink(tmppath)
                except:
                    pass
            else:
                self.app.show_result(f"Failed to download {filename}")

    #def on_view_closed(self, close_callback):
    #    self.app.closedialog() # Закрываем вьювер
    #    if close_callback:
    #        close_callback() # Вызываем возврат в список версий

    def show_version_select_dialog(self, file_data):
        """Показать диалог выбора версии для просмотра"""
        versions = self.s3_manager.list_object_versions(self.current_bucket, file_data['key'])

        if not versions:
            self.app.show_result("No versions found")
            return

        if len(versions) == 1:
            # Только одна версия - просматриваем сразу
            self.view_s3_file_version(file_data, versions[0])
            return

        def callback(action, version_data):
            if action == 'cancel':
                self.app.close_dialog()
                self.refresh()
                return

            if action == 'view' and version_data:
                self.app.close_dialog()
                # self.view_s3_file_version(file_data, version_data)
                self.view_s3_file_version( file_data, version_data,
                    close_callback=lambda: self.show_version_select_dialog(file_data)
                )

            elif action == 'delete' and version_data:
                self.app.close_dialog()

                # Показываем подтверждение удаления
                self.confirm_delete_version(file_data, version_data)
                #    close_callback=lambda: self.show_version_select_dialog(file_data)
                

        dialog = VersionSelectDialog(file_data, versions, callback)
        self.app.show_dialog(dialog, height=('relative', 60))

    def confirm_delete_version(self, file_data, version_data, close_callback=None):
        """Подтверждение удаления конкретной версии"""
        def confirm_callback(confirmed):
            self.app.close_dialog()
            if confirmed:
                # Удаляем версию
                version_id_full = version_data.get('VersionId')
                if self.s3_manager.delete_object(
                    self.current_bucket, 
                    file_data['key'], 
                    version_id=version_id_full
                ):
                    self.app.show_result(f"Version {version_id} deleted successfully")
                    # self.refresh()  # Обновляем список файлов
                else:
                    self.app.show_result(f"Failed to delete version {version_id}")
                self.show_version_select_dialog(file_data)
            else:
                # Возвращаемся к диалогу выбора версии
                self.show_version_select_dialog(file_data)

        version_id = version_data.get('VersionId', '')[:12]
        is_latest = version_data.get('IsLatest', False)
        latest_warn = " [THIS IS THE LATEST VERSION!]" if is_latest else ""
        size = format_size(version_data.get('Size', 0))
        mtime = version_data.get('LastModified', '').strftime('%Y-%m-%d %H:%M:%S') if version_data.get('LastModified') else 'N/A'
        message = f"Delete version of '{file_data['name']}'?{latest_warn}"
        items_info = [
            f"Version ID: {version_id}",
            f"Size: {size}",
            f"Modified: {mtime}"
        ]
        dialog = ConfirmDialog( "Confirm Delete Version", message, items_info, confirm_callback )
        self.app.show_dialog(dialog)

    def _refresh_endpoints(self):
        self.update_header('[S3 Mode - Endpoints]')
        self.path_text.set_text('S3: /')
        
        data = {'type': 'to_root_menu', 'can_select': False}
        text = SelectableText('  [..] Back to root menu', data, self)
        self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        
        endpoints = self.s3_config.get_endpoints()
        
        for ep in endpoints:
            label = f'[ENDPOINT] {ep["name"]:35} {ep["url"]}'
            data = {'type': 'endpoint', 'name': ep['name'], 'config': ep, 'can_select': False}
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

    def _refresh_s3_objects_lazy(self):
        """Ленивая загрузка объектов S3 с постепенным отображением"""
        prefix = self.current_prefix

        # Добавляем индикатор загрузки
        loading_text = SelectableText(' [Loading...]', {'type': 'loading', 'can_select': False}, self)
        self.walker.append(urwid.AttrMap(loading_text, 'info'))

        # Запускаем фоновую загрузку
        if self.loading_thread and self.loading_thread.is_alive():
            return

        self.loading_in_progress = True
        self.loading_thread = threading.Thread(
            target=self._load_s3_objects_background,
            args=(self.current_bucket, prefix),
            daemon=True
        )
        self.loading_thread.start()

    def _load_s3_objects_background(self, bucket_name, prefix):
        """Фоновая загрузка объектов с использованием генератора"""
        try:
            all_folders = []
            all_files = []

            # Используем ленивый генератор
            for folders, files in self.s3_manager.list_objects_lazy(bucket_name, prefix, page_size=1000):
                all_folders.extend(folders)
                all_files.extend(files)

                # После каждой страницы обновляем UI
                # Создаем копии списков для передачи в lambda
                folders_copy = list(all_folders)
                files_copy = list(all_files)
                self.app.loop.set_alarm_in(0, lambda loop, user_data=None: self._update_display_incremental(
                    folders_copy, files_copy
                ))

                # Небольшая пауза для обработки UI
                time.sleep(0.01)

            # Финальное обновление
            self.app.loop.set_alarm_in(0, lambda loop, user_data=None: self._finalize_loading(
                all_folders, all_files
            ))

        except Exception as e:
            error_msg = str(e)
            self.app.loop.set_alarm_in(0, lambda loop, user_data=None: self.app.show_result(
                f"Error loading objects: {error_msg}"
            ))
        finally:
            self.loading_in_progress = False

    def _update_display_incremental(self, folders, files):
        """Инкрементальное обновление отображения по мере загрузки"""
        # Удаляем индикатор загрузки
        for i, widget in enumerate(self.walker):
            w = widget.original_widget
            if isinstance(w, SelectableText) and w.data.get('type') == 'loading':
                del self.walker[i]
                break

        # Создаем элементы для отображения
        items = self._create_display_items(folders, files)

        # Обновляем walker (удаляем старые объекты, добавляем новые)
        # Сохраняем заголовок "[..]"
        keep_count = 0
        for widget in self.walker:
            w = widget.original_widget
            if isinstance(w, SelectableText):
                if w.data.get('type') in ['to_root_menu', 'parent']:
                    keep_count += 1
                else:
                    break

        # Удаляем старые элементы
        del self.walker[keep_count:]

        # Добавляем новые
        for item_widget in items:
            self.walker.append(item_widget)

        # Добавляем индикатор продолжающейся загрузки
        if self.loading_in_progress:
            loading_text = SelectableText(
                f' [Loaded: {len(folders)} folders, {len(files)} files...]',
                {'type': 'loading', 'can_select': False},
                self
            )
            self.walker.append(urwid.AttrMap(loading_text, 'info'))

    def _finalize_loading(self, folders, files):
        """Завершение загрузки и финальное обновление"""
        self.loading_in_progress = False

        # Удаляем индикатор загрузки
        for i in range(len(self.walker) - 1, -1, -1):
            widget = self.walker[i]
            w = widget.original_widget
            if isinstance(w, SelectableText) and w.data.get('type') == 'loading':
                del self.walker[i]

        # Показываем статистику
        self.app.show_result(
            f"Loaded: {len(folders)} folders, {len(files)} files"
        )

    def _create_display_items(self, folders, files):
        """Создать виджеты для отображения папок и файлов"""
        items = []

        # Сортируем если нужно
        combined = []

        for folder in folders:
            key = folder['Key']
            folder_name = key.rstrip('/').split('/')[-1]
            combined.append({
                'type': 'folder',
                'name': folder_name,
                'key': key,
                'size': 0,
                'mtime': None
            })

        for file in files:
            key = file['Key']
            file_name = key.split('/')[-1]
            combined.append({
                'type': 'file',
                'name': file_name,
                'key': key,
                'size': file.get('Size', 0),
                'mtime': file.get('LastModified')
            })

        # Применяем сортировку
        combined = self.sort_items(combined)

        # Создаем виджеты
        for item in combined:
            if item['type'] == 'folder':
                label = f"[DIR]  {item['name']}"
                data = {
                    'type': 'folder',
                    'name': item['name'],
                    'key': item['key'],
                    'can_select': False
                }
            else:
                size_str = format_size(item['size'])
                time_str = item['mtime'].strftime('%Y-%m-%d %H:%M') if item['mtime'] else ''
                label = f"{item['name']:50} {size_str:>10} {time_str}"
                data = {
                    'type': 'file',
                    'name': item['name'],
                    'key': item['key'],
                    'size': item['size'],
                    'mtime': item['mtime'],
                    'can_select': True
                }

            text = SelectableText(f'  {label}', data, self)
            items.append(urwid.AttrMap(text, None, focus_map='selected'))

        return items

        def _refresh_s3(self):
        if self.current_bucket is None:
            self.update_header(f'[S3 Mode - {self.current_endpoint}] Sort: {self.sort_mode}')
            self.path_text.set_text(f'S3: /{self.current_endpoint}/')
            
            data = {'type': 'to_root_menu', 'can_select': False}
            text = SelectableText('  [..] Back to root menu', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            
            buckets = self.s3_manager.list_buckets()
            
            if not buckets and self.s3_manager.connection_error:
                error_msg = f'[ERROR] Connection failed: {self.s3_manager.connection_error[:60]}'
                data = {'type': 'error', 'can_select': False}
                text = SelectableText(f'  {error_msg}', data, self)
                self.walker.append(urwid.AttrMap(text, 'error'))
                self.app.show_result(f'Cannot connect to {self.current_endpoint}: {self.s3_manager.connection_error[:80]}')
                return

            bucket_items = []
            for bucket in buckets:
                # Получаем статус версионирования для каждого бакета
                versioning_status = self.s3_manager.get_versioning_status(bucket['Name'])
                if versioning_status == 'Enabled':
                    versioning_mark = '[V]' 
                elif versioning_status == 'Suspended':
                    versioning_mark = '[S]'
                else:
                    versioning_mark = '   '

                bucket_items.append({
                    'name': bucket['Name'],
                    'type': 'bucket',
                    'CreationDate': bucket.get('CreationDate'),
                    'mtime': bucket.get('CreationDate'),
                    'size': 0,
                    'versioning': versioning_status,
                    'versioning_mark': versioning_mark,
                    'can_select': True
                })
            
            bucket_items = self.sort_items(bucket_items)
            
            for bucket in bucket_items:
                creation_date = bucket.get('CreationDate')
                date_str = creation_date.strftime('%Y-%m-%d %H:%M:%S') if creation_date else ' ' * 19
                
                #label = f'[BUCKET] {bucket["name"]:40} {date_str}'
                label = f'*{bucket["name"]:40} {date_str} {bucket["versioning_mark"]}'
                #label = f'*{bucket["versioning_mark"]} {bucket["name"]:37} {date_str}'

                data = {'type': 'bucket', 'name': bucket['name'], 'can_select': True}
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        else:
            self.update_header(f'[S3 Mode - {self.current_endpoint}] Sort: {self.sort_mode}')

            # Получаем количество объектов
            total_count, total_size = self.s3_manager.count_objects(self.current_bucket, self.current_prefix)
            if total_count is not None:
                count_info = f' [{total_count} objects, {format_size(total_size)}]'
            else:
                count_info = ''

            self.path_text.set_text(f'S3: /{self.current_endpoint}/{self.current_bucket}/{self.current_prefix}{count_info}')
            
            if self.current_prefix:
                data = {'type': 's3_parent', 'can_select': False}
                text = SelectableText('  [..] Parent', data, self)
            else:
                data = {'type': 's3_back', 'can_select': False}
                text = SelectableText('  [..] Back to buckets', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            
            folders, files = self.s3_manager.list_objects(self.current_bucket, self.current_prefix)
            
            if not folders and not files and self.s3_manager.connection_error:
                error_msg = f'[ERROR] Cannot list objects: {self.s3_manager.connection_error[:60]}'
                data = {'type': 'error', 'can_select': False}
                text = SelectableText(f'  {error_msg}', data, self)
                self.walker.append(urwid.AttrMap(text, 'error'))
                return
            
            folder_items = []
            for folder in folders:
                folder_name = folder['Key'][len(self.current_prefix):].rstrip('/')
                folder_items.append({
                    'name': folder_name,
                    'key': folder['Key'],
                    'type': 's3_dir',
                    'size': 0,
                    'mtime': datetime.min,
                    'can_select': True
                })
            
            file_items = []
            for file_obj in files:
                key = file_obj['Key']
                file_name = key[len(self.current_prefix):]
                
                versions = self.s3_manager.list_object_versions(self.current_bucket, key)
                version_info = ''
                if len(versions) > 1:
                    version_info = f' [{len(versions)}]'
                    #version_info = f' [v:{len(versions)}]'
                
                file_items.append({
                    'name': file_name,
                    'key': key,
                    'type': 's3_file',
                    'size': file_obj['Size'],
                    'Size': file_obj['Size'],
                    'mtime': file_obj.get('LastModified', datetime.min),
                    'LastModified': file_obj.get('LastModified'),
                    'version_count': len(versions),
                    'version_info': version_info,
                    'can_select': True
                })
            
            folder_items = self.sort_items(folder_items)
            file_items = self.sort_items(file_items)
            
            for folder_item in folder_items:
                #label = f'[DIR ] {folder_item["name"]:40}  <DIR>           ' + ' ' * 19
                label = f'/{folder_item["name"]:40}                ' + ' ' * 19
                data = {'type': 's3_dir', 'key': folder_item['key'], 'name': folder_item['name'], 'can_select': True}
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            
            for file_item in file_items:
                mtime = file_item['LastModified'].strftime('%Y-%m-%d %H:%M:%S') if file_item.get('LastModified') else ' ' * 19
                size_str = self.format_size(file_item['size'])
                version_str = file_item['version_info']
                #! version_str = file_item['version_count']
                
                #label = f'[FILE] {file_item["name"]:40} {size_str:>10}{version_str:8} {mtime}'
                label = f' {file_item["name"]:40} {size_str:>10}{version_str:4} {mtime}'
                data = {
                    'type': 's3_file',
                    'key': file_item['key'],
                    'name': file_item['name'],
                    'size': file_item['size'],
                    'version_count': file_item['version_count'],
                    'can_select': True
                }
                text = SelectableText(f'  {label}', data, self)
                #self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
                self.walker.append(urwid.AttrMap(text, 'file', focus_map='selected'))

    def _refresh_fs(self):
        self.update_header(f'[FS Mode] Sort: {self.sort_mode}')

        # Подсчитываем количество элементов в текущей директории
        items = self.fs_browser.list_directory()
        dir_count = sum(1 for item in items if item.get('is_dir', False) and item.get('name') != '..')
        file_count = sum(1 for item in items if not item.get('is_dir', False))
        count_info = f' [{dir_count} dirs, {file_count} files]'

        self.path_text.set_text(f'FS: {self.fs_browser.current_path}{count_info}')
        
        if self.is_fs_root():
            data = {'type': 'to_root_menu', 'can_select': False}
            text = SelectableText('  [..] Back to root menu', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        
        items = self.fs_browser.list_directory()
        
        dirs = [item for item in items if item['is_dir'] and item['name'] != '..']
        files = [item for item in items if not item['is_dir']]
        parent = [item for item in items if item['name'] == '..']
        
        dirs = self.sort_items(dirs)
        files = self.sort_items(files)
        
        for item_data in parent:
            label = '/..'
            data = {
                'type': 'fs_dir',
                'name': item_data['name'],
                'size': item_data['size'],
                'can_select': False
            }
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        
        for item_data in dirs:
            mtime = item_data['mtime'].strftime('%Y-%m-%d %H:%M:%S') if item_data['mtime'] else ' ' * 19
            #label = f'[DIR ] {item_data["name"]:40}  <DIR>           {mtime}'
            label = f'/{item_data["name"]:40}            {mtime}'
            data = {
                'type': 'fs_dir',
                'name': item_data['name'],
                'size': item_data['size'],
                'mtime': item_data['mtime'],
                'can_select': True
            }
            text = SelectableText(f'  {label}', data, self)
            #self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            self.walker.append(urwid.AttrMap(text, 'body', focus_map='selected'))
        
        for item_data in files:
            mtime = item_data['mtime'].strftime('%Y-%m-%d %H:%M:%S') if item_data['mtime'] else ' ' * 19
            #label = f'[FILE] {item_data["name"]:40} {self.format_size(item_data["size"]):>10}         {mtime}'
            label = f' {item_data["name"]:40} {self.format_size(item_data["size"]):>10} {mtime}'
            data = {
                'type': 'fs_file',
                'name': item_data['name'],
                'size': item_data['size'],
                'mtime': item_data['mtime'],
                'can_select': True
            }
            text = SelectableText(f'  {label}', data, self)
            #self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            self.walker.append(urwid.AttrMap(text, 'file', focus_map='selected'))

    def format_size(self, size):
        for unit in ['B  ', 'KB ', 'MB ', 'GB ']:
            if size < 1024.0:
                return f'{size:.1f}{unit}'
            size /= 1024.0
        return f'{size:.1f}TB'

    def on_item_activated(self, data):
        item_type = data.get('type')
        
        if item_type == 'to_root_menu':
            self.mode = 'root_menu'
            self.current_endpoint = None
            self.current_bucket = None
            self.current_prefix = ''
            self.s3_manager = None
            self.refresh()
        
        elif item_type == 'root_fs':
            self.mode = 'fs'
            if self.fs_browser is None:
                self.fs_browser = FileSystemBrowser()
            self.refresh()
        
        elif item_type == 'root_endpoint':
            self.mode = 's3'
            self.current_endpoint = data['name']
            endpoint_config = data['config']
            self.s3_manager = S3Manager(endpoint_config)
            self.current_bucket = None
            self.current_prefix = ''
            self.refresh()
        
        elif item_type == 'endpoint':
            self.current_endpoint = data['name']
            endpoint_config = data['config']
            self.s3_manager = S3Manager(endpoint_config)
            self.current_bucket = None
            self.current_prefix = ''
            self.refresh()
        
        elif item_type == 'bucket':
            self.current_bucket = data['name']
            self.current_prefix = ''
            self.refresh()
        
        elif item_type == 's3_back':
            focus_on = self.current_bucket
            self.current_bucket = None
            self.current_prefix = ''
            self.refresh(focus_on=focus_on)
        
        elif item_type == 's3_parent':
            if self.current_prefix:
                parts = self.current_prefix.rstrip('/').split('/')
                focus_on = parts[-1]
                self.current_prefix = '/'.join(parts[:-1]) + '/' if len(parts) > 1 else ''
                self.refresh(focus_on=focus_on)
        
        elif item_type == 's3_dir':
            self.current_prefix = data['key']
            self.refresh()
        
        elif item_type == 's3_file':
            if data.get('version_count', 1) > 1:
                self.show_versions(data)
            else:
                self.view_item()
        
        elif item_type == 'fs_dir':
            if data['name'] == '..':
                focus_on = os.path.basename(self.fs_browser.current_path)
                self.fs_browser.current_path = os.path.dirname(self.fs_browser.current_path)
                self.refresh(focus_on=focus_on)
            else:
                self.fs_browser.current_path = os.path.join(self.fs_browser.current_path, data['name'])
                self.refresh()

    def show_versions(self, file_data):
        versions = self.s3_manager.list_object_versions(self.current_bucket, file_data['key'])
        if not versions:
            self.app.show_result('No versions found')
            return
        
        version_lines = [f"Versions of: {file_data['name']}\n"]
        for idx, v in enumerate(versions):
            is_latest = v.get('IsLatest', False)
            latest_mark = '[LATEST] ' if is_latest else '        '
            size = self.format_size(v.get('Size', 0))
            mtime = v.get('LastModified', '').strftime('%Y-%m-%d %H:%M:%S') if v.get('LastModified') else ''
            version_id = v.get('VersionId', '')[:12]
            version_lines.append(f"{idx+1}. {latest_mark}{version_id} {size:>10} {mtime}")
        
        content = '\n'.join(version_lines)
        content += '\n\nUse F3 to view, F5 to copy, F8 to delete selected version'
        
        viewer = FileViewerDialog(f'Versions: {file_data["name"]}', content, self.app.close_dialog)
        self.app.show_dialog(viewer)

    def select_by_pattern(self, pattern, select=True):
        """Выбрать/снять выбор элементов по glob pattern (только файлы)"""
        try:
            regex_pattern = fnmatch.translate(pattern)
            regex = re.compile(regex_pattern, re.IGNORECASE)
            count = 0
            
            for widget in self.walker:
                w = widget.original_widget
                if isinstance(w, SelectableText) and w.data.get('can_select'):
                    item_type = w.data.get('type')
                    if item_type in ('fs_file', 's3_file'):
                        name = w.data.get('name', '')
                        if regex.match(name):
                            w.selected = select
                            self.update_item_display(w)
                            count += 1
            
            action = 'Selected' if select else 'Unselected'
            self.app.show_result(f'{action} {count} files')
        except re.error:
            self.app.show_result('Invalid pattern')

    def invert_selection(self):
        """Инвертировать выбор (только файлы)"""
        count = 0
        for widget in self.walker:
            w = widget.original_widget
            if isinstance(w, SelectableText) and w.data.get('can_select'):
                item_type = w.data.get('type')
                if item_type in ('fs_file', 's3_file'):
                    w.selected = not w.selected
                    self.update_item_display(w)
                    if w.selected:
                        count += 1
        
        self.app.show_result(f'Selected {count} files')

    def update_item_display(self, text_widget):
        if text_widget.selected:
            text_widget.set_text('* ' + text_widget.get_text()[0][2:])
        else:
            text_widget.set_text('  ' + text_widget.get_text()[0][2:])

    def get_selected_items(self):
        selected = []
        for widget in self.walker:
            w = widget.original_widget
            if isinstance(w, SelectableText) and w.selected:
                selected.append(w.data)
        return selected

    def get_focused_item(self):
        focus_widget, pos = self.listbox.get_focus()
        if focus_widget:
            w = focus_widget.original_widget
            if isinstance(w, SelectableText):
                return w.data
        return None

    def view_item(self):
        focused = self.get_focused_item()
        if not focused:
            return

        item_type = focused['type']

        if item_type == 'fs_file':
            file_path = os.path.join(self.fs_browser.current_path, focused['name'])
            self._view_file(file_path, focused['name'])

        elif item_type == 's3_file':
            # Проверяем количество версий
            if focused.get('version_count', 1) > 1:
                # Показываем диалог выбора версии
                self.show_version_select_dialog(focused)
            else:
                # Просматриваем единственную версию
                self.view_s3_file_version(focused)

        elif item_type in ('fs_dir', 's3_dir', 'bucket'):
            self._calculate_size(focused)

    def _view_file(self, file_path, title, close_callback=None):
        try:
            if is_binary_file(file_path):
                content = f"[Binary file: {title}]\n\nFile size: {os.path.getsize(file_path)} bytes\n\n"
                content += "This is a binary file and cannot be displayed as text."
            else:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read(50000)
                        if len(content) == 50000:
                            content += "\n\n[... File truncated ...]"
                except Exception as e:
                    content = f"Error reading file: {str(e)}"

            def on_viewer_close():
                self.app.close_dialog()  # Закрываем сам вьювер
                if close_callback:
                    close_callback()    # Вызываем возврат (например, в список версий)

            #viewer = FileViewerDialog(f'View: {title}', content, self.app.close_dialog)
            viewer = FileViewerDialog(f'View: {title}', content, on_viewer_close)
            self.app.show_dialog(viewer, height=('relative', 80))

        except Exception as e:
            self.app.show_result(f'Error viewing file: {str(e)}')

    def _calculate_size(self, item):
        """Подсчет размера директории/бакета/псевдодиректории"""
        item_type = item['type']
        
        def calculate_in_thread():
            try:
                total_size = 0
                file_count = 0
                
                if item_type == 'fs_dir':
                    dir_path = os.path.join(self.fs_browser.current_path, item['name'])
                    files = self.fs_browser.list_all_files(dir_path)
                    file_count = len(files)
                    total_size = sum(f['size'] for f in files)
                
                elif item_type == 's3_dir':
                    objects = self.s3_manager.list_all_objects(self.current_bucket, item['key'])
                    file_count = len(objects)
                    total_size = sum(obj.get('Size', 0) for obj in objects)
                
                elif item_type == 'bucket':
                    objects = self.s3_manager.list_all_objects(item['name'], '')
                    file_count = len(objects)
                    total_size = sum(obj.get('Size', 0) for obj in objects)
                
                self.app.loop.draw_screen()
                result_msg = f'Size: {format_size(total_size)} ({file_count} files)'
                
                # Обновляем UI и принудительно рисуем экран
                def update_result(loop, user_data):
                    self.app.show_result(result_msg)
                    self.app.loop.draw_screen()

                self.app.loop.set_alarm_in(0, update_result)

                # ГЛАВНОЕ: Будим основной цикл!
                self.app.wake_up()
            
            except Exception as e:
                def show_error(loop=None, user_data=None):
                    self.app.show_result(f'Error calculating size: {str(e)}')
                    # self.app.loop.draw_screen()

                self.app.loop.set_alarm_in(0, show_error)
                self.app.wake_up() # Будим цикл и при ошибке
        
        self.app.show_result('Calculating size...')
        thread = threading.Thread(target=calculate_in_thread)
        thread.daemon = True
        thread.start()


class InputDialog(urwid.WidgetWrap):
    def __init__(self, title, prompt, callback, default_text=''):
        self.callback = callback
        self.edit = urwid.Edit(prompt, default_text)
        
        ok_button = urwid.Button('[ OK ]')
        cancel_button = urwid.Button('[ Cancel ]')
        
        urwid.connect_signal(ok_button, 'click', self.on_ok)
        urwid.connect_signal(cancel_button, 'click', self.on_cancel)

        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(ok_button, 'button', focus_map='buttonfocus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_button, 'button', focus_map='buttonfocus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)

#        buttons = urwid.Columns([
#            urwid.AttrMap(ok_button, None, focus_map='selected'),
#            urwid.AttrMap(cancel_button, None, focus_map='selected')
#        ], dividechars=2)

        content = [
            ('pack', urwid.Divider()),
            ('pack', self.edit),
        ]

        content.extend([
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])

        pile = urwid.Pile(content)

        fill = urwid.Filler(pile)
        super().__init__(urwid.AttrMap(urwid.LineBox(fill, title=title), 'dialog'))

    def keypress(self, size, key):
        if key == 'enter':
            btn = get_focus_button(self._w)
            if btn != None:
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Cancel ]':
                    # Enter на Cancel -> отмена
                    self.on_cancel(None)
                    return None
            # Все остальные случаи: Enter -> OK
            self.on_ok(None)
            return None
        elif key == 'esc':
            self.on_cancel(None)
            return None
        return super().keypress(size, key)

    def on_ok(self, button):
        text = self.edit.get_edit_text()
        if text.strip():
            self.callback(True, text.strip())

    def on_cancel(self, button):
        self.callback(False, None)


class ConfirmDialog(urwid.WidgetWrap):
    def __init__(self, title, message, items_info, callback):
        self.callback = callback
        
        yes_button = urwid.Button('[ Yes ]')
        no_button = urwid.Button('[ No ]')
        
        urwid.connect_signal(yes_button, 'click', self.on_yes)
        urwid.connect_signal(no_button, 'click', self.on_no)
        
        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(no_button, 'button', focus_map='buttonfocus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(yes_button, 'button', focus_map='buttonfocus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)

        content = [
            ('pack', urwid.Text(message)),
            ('pack', urwid.Divider()),
        ]

        if items_info:
            content.append(('pack', urwid.Text("Items:", align='left')))
            max_display = 10

            for item_info in items_info[:max_display]:
                content.append(('pack', urwid.Text(f"  {item_info}")))

            if len(items_info) > max_display:
                content.append(('pack', urwid.Text(f"  ... and {len(items_info) - max_display} more")))

            content.append(('pack', urwid.Divider()))
        content.extend([
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])

        pile = urwid.Pile(content)

        fill = urwid.Filler(pile, valign='top')
        # super().__init__(urwid.AttrMap(urwid.LineBox(fill), 'dialog'))
        super().__init__(urwid.AttrMap(urwid.LineBox(fill, title=title), 'dialog'))

    def keypress(self, size, key):
        if key == 'enter':
            btn = get_focus_button(self._w)
            if btn != None:
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Yes ]':
                    # Enter на Cancel -> отмена
                    self.on_yes(None)
                    return None
            # Все остальные случаи: Enter -> No
            self.on_no(None)
            return None
        elif key == 'esc':
            self.on_no(None)
            return None
        return super().keypress(size, key)

    def on_yes(self, button):
        self.callback(True)

    def on_no(self, button):
        self.callback(False)


class DualPaneApp:
    def __init__(self, s3_config):
        self.s3_config = s3_config
        
        self.left_panel = PanelWidget('', panel_type='root_menu', s3_config=s3_config, app=self)
        self.right_panel = PanelWidget('', panel_type='root_menu', s3_config=s3_config, app=self)
        
        self.columns = urwid.Columns([
            ('weight', 1, self.left_panel),
            ('weight', 1, self.right_panel)
        ], dividechars=1, focus_column=0)


        self.hotkey_text = urwid.Text(
            'F3:view | F5:copy | F6:move | F7:mkdir | F8:del | F9:del_old_ver | F10:sort | F11:versioning | INS:sel | +:select | -:unsel | *:invert | TAB | q:quit'
        )
        self.result_text = urwid.Text('')
        
        status_content = urwid.Pile([
            ('pack', urwid.AttrMap(self.result_text, 'result')),
            ('pack', urwid.AttrMap(self.hotkey_text, 'status'))
        ])

        self.frame = urwid.Frame(
            urwid.AttrMap(self.columns, 'body'),
            footer=status_content
        )
        
        self.main_widget = self.frame
        
        self.palette = [
            ('header', 'black', 'light cyan', 'bold'),
            ('path', 'white', 'dark cyan'),
            ('mode', 'black', 'light cyan'),
            ('body', 'white', 'dark blue'),
            ('file', 'light gray', 'dark blue'),
            ('selected', 'black', 'light cyan'),
            ('status', 'black', 'light cyan'),
            ('result', 'yellow', 'dark blue'),
            ('dialog', 'black', 'light gray'),
            ('dialog_title', 'black', 'light cyan'),
            ('edit', 'black', 'light cyan'),
            ('edit_focus', 'white', 'dark cyan'),
            ('button', 'black', 'light gray'),
            ('button_focus', 'white', 'dark cyan'),
            ('error', 'light red', 'dark blue'),
        ]
        
        # Переменная для режима "перезаписать все"
        self.overwrite_all = False
        self.version_all = False
        self.skip_all = False
        if platform.system() != 'Windows':
            self.pipe_r, self.pipe_w = os.pipe()
            self.use_pipe = True
        else:
            self.use_pipe = False

    def run(self):
        # Создаем экран с явной поддержкой UTF-8
        screen = urwid.raw_display.Screen()
        screen.set_terminal_properties(colors=256)

        urwid.set_encoding('utf-8')

        self.loop = urwid.MainLoop(
            self.main_widget,
            palette=self.palette,
            unhandled_input=self.handle_input,
            screen=screen
        )
        if self.use_pipe:
            self.loop.watch_file(self.pipe_r, self.loop_wakeup_callback)
        self.loop.run()

    def loop_wakeup_callback(self):
        """Callback для пробуждения event loop через pipe"""
        os.read(self.pipe_r, 1)

    def wake_up(self):
        """Метод для вызова из других потоков"""
        if self.use_pipe:
            os.write(self.pipe_w, b'!')
        else:
            self.loop.set_alarm_in(0, lambda loop, data: None)

    def handle_input(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        elif key == 'tab':
            current_focus = self.columns.focus_position
            self.columns.focus_position = 1 - current_focus
        elif key == 'f3':
            active_panel = self.get_active_panel()
            active_panel.view_item()
        elif key == 'f5':
            self.copy_items()
        elif key == 'f6':
            self.move_items()
        elif key == 'f7':
            self.create_directory()
        elif key == 'f8':
            self.delete_items()
        elif key == 'f9':
            self.delete_old_versions()
        elif key == 'f10':
            active_panel = self.get_active_panel()
            active_panel.show_sort_dialog()
        elif key == 'f11':
            self.toggle_versioning()
        elif key == '+':
            self.select_by_pattern()
        elif key == '-':
            self.unselect_by_pattern()
        elif key == '*':
            active_panel = self.get_active_panel()
            active_panel.invert_selection()

    def select_by_pattern(self):
        def callback(confirmed, pattern):
            self.close_dialog()
            if confirmed:
                active_panel = self.get_active_panel()
                active_panel.select_by_pattern(pattern, select=True)
        
        dialog = InputDialog('Select files by pattern', 'Pattern: ', callback, default_text='*')
        self.show_dialog(dialog)

    def unselect_by_pattern(self):
        def callback(confirmed, pattern):
            self.close_dialog()
            if confirmed:
                active_panel = self.get_active_panel()
                active_panel.select_by_pattern(pattern, select=False)
        
        dialog = InputDialog('Unselect files by pattern', 'Pattern: ', callback, default_text='*')
        self.show_dialog(dialog)

    def delete_old_versions(self):
        active_panel = self.get_active_panel()
        
        if active_panel.mode != 's3' or not active_panel.current_bucket:
            self.show_result('This function works only with S3 objects')
            return
        
        selected_items = active_panel.get_selected_items()
        if not selected_items:
            focused = active_panel.get_focused_item()
            if focused and focused['type'] == 's3_file':
                selected_items = [focused]
        
        if not selected_items:
            self.show_result('No items selected')
            return
        
        versioned_items = []
        for item in selected_items:
            if item['type'] == 's3_file' and item.get('version_count', 1) > 1:
                versioned_items.append(item)
        
        if not versioned_items:
            self.show_result('No versioned files selected')
            return
        
        items_info = [f"{item['name']} ({item['version_count']} versions)" for item in versioned_items]
        
        def callback(confirmed):
            self.close_dialog()
            if confirmed:
                progress = ProgressDialog('Deleting old versions...', callback=self.close_dialog)
                progress.set_total(len(versioned_items))
                self.show_dialog(progress)
                
                def delete_thread():
                    for item in versioned_items:
                        if progress.cancelled:
                            break
                        
                        self.loop.draw_screen()
                        progress.update(item['name'])
                        
                        deleted = active_panel.s3_manager.delete_old_versions(
                            active_panel.current_bucket,
                            item['key']
                        )
                        
                        if deleted > 0:
                            progress.add_success()
                        else:
                            progress.add_failure()
                    
                    time.sleep(0.5)
                    self.loop.draw_screen()
                
                thread = threading.Thread(target=delete_thread)
                thread.daemon = True
                thread.start()
                
                def check_thread():
                    if thread.is_alive():
                        self.loop.set_alarm_in(0.1, lambda *args: check_thread())
                    else:
                        self.close_dialog()
                        active_panel.refresh()
                        self.show_result(f'Deleted old versions: {progress.success_count}, Failed: {progress.fail_count}')
                
                self.loop.set_alarm_in(0.1, lambda *args: check_thread())
        
        message = f'Delete old versions of {len(versioned_items)} file(s)?\nThis will keep only the latest version!'
        dialog = ConfirmDialog('Confirm Delete Old Versions', message, items_info, callback)
        self.show_dialog(dialog)

    # Добавляем аргументы width и height с дефолтными значениями
    def show_dialog(self, dialog, width=('relative', 70), height=('relative', 20)):
        overlay = urwid.Overlay(
            dialog,
            self.frame,
            align='center',
            width=width,
            valign='middle',
            height=height
        )
        self.loop.widget = overlay

    def close_dialog(self):
        self.loop.widget = self.main_widget

    def show_result(self, message):
        self.result_text.set_text(message)

    def get_active_panel(self):
        return self.left_panel if self.columns.focus_position == 0 else self.right_panel

    def get_inactive_panel(self):
        return self.right_panel if self.columns.focus_position == 0 else self.left_panel

    def create_directory(self):
        active_panel = self.get_active_panel()
        
        if active_panel.is_root_menu():
            self.show_result('Select FS or S3 endpoint first')
            return
        
        if active_panel.mode == 's3':
            if active_panel.is_bucket_list():
                def callback(confirmed, bucket_name):
                    self.close_dialog()
                    if confirmed:
                        if active_panel.s3_manager.create_bucket(bucket_name):
                            self.show_result(f'Created bucket: {bucket_name}')
                            active_panel.refresh(focus_on=bucket_name)
                        else:
                            self.show_result(f'Failed to create bucket: {bucket_name}')
                
                dialog = InputDialog('Create New Bucket', 'Bucket name: ', callback)
                self.show_dialog(dialog)
            elif active_panel.is_endpoint_list():
                self.show_result('Cannot create directory at endpoint level')
            else:
                self.show_result('Cannot create directory in S3 (use prefix when copying)')
        else:
            def callback(confirmed, dir_name):
                self.close_dialog()
                if confirmed:
                    if active_panel.fs_browser.create_directory(dir_name):
                        self.show_result(f'Created directory: {dir_name}')
                        active_panel.refresh(focus_on=dir_name)
                    else:
                        self.show_result(f'Failed to create directory: {dir_name}')
            
            dialog = InputDialog('Create New Directory', 'Directory name: ', callback)
            self.show_dialog(dialog)

    def analyze_items(self, items, source_panel):
        analyzed = []
        items_info = []
        total_bytes = 0
        
        for item in items:
            item_type = item['type']
            
            if item_type == 'fs_file':
                analyzed.append({'type': 'fs_file', 'item': item, 'files': [item]})
                #items_info.append(f"[FILE] {item['name']}")
                items_info.append(f" {item['name']}")
                total_bytes += item.get('size', 0)
            
            elif item_type == 'fs_dir':
                dir_path = os.path.join(source_panel.fs_browser.current_path, item['name'])
                all_files = source_panel.fs_browser.list_all_files(dir_path)
                analyzed.append({'type': 'fs_dir', 'item': item, 'files': all_files, 'dir_path': dir_path})
                #items_info.append(f"[DIR ] {item['name']} ({len(all_files)} files)")
                items_info.append(f"/{item['name']} ({len(all_files)} files)")
                total_bytes += sum(f['size'] for f in all_files)
            
            elif item_type == 's3_file':
                analyzed.append({'type': 's3_file', 'item': item, 'files': [item]})
                # items_info.append(f"[FILE] {item['name']}")
                items_info.append(f" {item['name']}")
                total_bytes += item.get('size', 0)
            
            elif item_type == 's3_dir':
                all_objects = source_panel.s3_manager.list_all_objects(source_panel.current_bucket, item['key'])
                analyzed.append({'type': 's3_dir', 'item': item, 'files': all_objects})
                #items_info.append(f"[DIR ] {item['name']} ({len(all_objects)} objects)")
                items_info.append(f"/{item['name']} ({len(all_objects)} objects)")
                total_bytes += sum(obj.get('Size', 0) for obj in all_objects)
            
            elif item_type == 'bucket':
                all_objects = source_panel.s3_manager.list_all_objects(item['name'], '')
                analyzed.append({'type': 'bucket', 'item': item, 'files': all_objects})
                items_info.append(f"*{item['name']} ({len(all_objects)} objects)")
                total_bytes += sum(obj.get('Size', 0) for obj in all_objects)
        
        return analyzed, items_info, total_bytes

    def copy_items(self):
        source_panel = self.get_active_panel()
        dest_panel = self.get_inactive_panel()
        
        if source_panel.is_root_menu() or source_panel.is_endpoint_list():
            self.show_result('Cannot copy from this level')
            return
        
        if dest_panel.is_root_menu() or dest_panel.is_endpoint_list():
            self.show_result('Select destination first')
            return
        
        selected_items = source_panel.get_selected_items()
        if not selected_items:
            focused = source_panel.get_focused_item()
            if focused and focused['type'] in ('fs_file', 's3_file', 'fs_dir', 's3_dir', 'bucket'):
                selected_items = [focused]
        
        if not selected_items:
            self.show_result('No items to copy')
            return
        
        if dest_panel.is_bucket_list():
            has_files = any(item['type'] in ('fs_file', 's3_file') for item in selected_items)
            if has_files:
                self.show_result('Cannot copy files directly to bucket list!')
                return
        
        analyzed, items_info, total_bytes = self.analyze_items(selected_items, source_panel)
        self._show_copy_dialog(analyzed, source_panel, dest_panel, is_move=False, total_bytes=total_bytes)

    def move_items(self):
        source_panel = self.get_active_panel()
        dest_panel = self.get_inactive_panel()
        
        if source_panel.is_root_menu() or source_panel.is_endpoint_list():
            self.show_result('Cannot move from this level')
            return
        
        if dest_panel.is_root_menu() or dest_panel.is_endpoint_list():
            self.show_result('Select destination first')
            return
        
        selected_items = source_panel.get_selected_items()
        if not selected_items:
            focused = source_panel.get_focused_item()
            if focused and focused['type'] in ('fs_file', 's3_file', 'fs_dir', 's3_dir', 'bucket'):
                selected_items = [focused]
        
        if not selected_items:
            self.show_result('No items to move')
            return
        
        if dest_panel.is_bucket_list():
            has_files = any(item['type'] in ('fs_file', 's3_file') for item in selected_items)
            if has_files:
                self.show_result('Cannot move files directly to bucket list!')
                return
        
        analyzed, items_info, total_bytes = self.analyze_items(selected_items, source_panel)
        self._show_copy_dialog(analyzed, source_panel, dest_panel, is_move=True, total_bytes=total_bytes)

    def _show_copy_dialog(self, analyzed, source_panel, dest_panel, is_move=False, total_bytes=0):
        operation = 'Move' if is_move else 'Copy'
        
        if len(analyzed) == 1:
            item = analyzed[0]['item']
            source_desc = f'{operation} "{item["name"]}"'
        else:
            source_desc = f'{operation} {len(analyzed)} items'
        
        if len(analyzed) == 1:
            item = analyzed[0]['item']
            if dest_panel.is_bucket_list():
                dest_path = item['name'].lower().replace('_', '-')
            else:
                dest_base = dest_panel.get_current_path()
                if dest_base:
                    dest_path = dest_base.rstrip('/') + '/' + item['name']
                else:
                    dest_path = item['name']
        else:
            dest_path = dest_panel.get_current_path()
        
        def callback(confirmed, target_name):
            self.close_dialog()
            if not confirmed:
                return
            
            if not target_name:
                target_name = dest_panel.get_current_path()
            
            current_item = source_panel.get_focused_item()
            focus_name = current_item.get('name') if current_item else None
            
            # Сброс флага "перезаписать все"
            self.overwrite_all = False
            self.version_all = False
            self.skip_all = False

            self._do_copy_with_progress(analyzed, source_panel, dest_panel, target_name, focus_name, is_move=is_move, total_bytes=total_bytes)
        
        dialog = CopyMoveDialog(operation, source_desc, dest_path, callback)
        self.show_dialog(dialog)

    def _check_overwrite(self, filename, source_info, dest_info, callback, is_s3_dest=False):
        """Показать диалог подтверждения перезаписи"""
        dialog = OverwriteDialog(filename, source_info, dest_info, callback, show_version_options=is_s3_dest)
        self.show_dialog(dialog)

    def _do_copy_with_progress(self, analyzed, source_panel, dest_panel, target_name, focus_name, is_move=False, total_bytes=0):
        total_files = sum(len(a['files']) for a in analyzed)
        
        operation = 'Moving' if is_move else 'Copying'
        progress = ProgressDialog(f'{operation} files...', callback=self.close_dialog)
        progress.set_total(total_files, total_bytes)
        self.show_dialog(progress)
    
        items_to_delete = []
        user_choice = {'value': None}
        choice_event = threading.Event()
        
        def copy_thread():
            for item_data in analyzed:
                if progress.cancelled:
                    break
                
                item_type = item_data['type']
                item = item_data['item']
                
                # FS файл -> S3
                if item_type == 'fs_file' and dest_panel.mode == 's3' and dest_panel.current_bucket:
                    source_path = os.path.join(source_panel.fs_browser.current_path, item['name'])
                    
                    if len(analyzed) == 1:
                        dest_key = target_name if target_name else item['name']
                    else:
                        if target_name:
                            dest_key = target_name.rstrip('/') + '/' + item['name']
                        else:
                            dest_key = item['name']
                    
                    # Проверка существования
                    if not self.overwrite_all and not self.version_all and not self.skip_all:
                        existing = dest_panel.s3_manager.object_exists(dest_panel.current_bucket, dest_key)
                        if existing:
                            source_info = {
                            }
                            dest_info = {
                                'size': existing.get('Size',0),
                                'mtime': existing.get('LastModified')
                            }
                            
                            def show_overwrite_dialog():
                                def on_choice(choice):
                                    user_choice['value'] = choice
                                    choice_event.set()
                                    self.close_dialog()
                                    self.show_dialog(progress)
                                
                                self._check_overwrite(item['name'], source_info, dest_info, on_choice, is_s3_dest=True)
                            
                            self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                            choice_event.wait()
                            choice_event.clear()
                            
                            if user_choice['value'] == 'cancel':
                                progress.cancelled = True
                                break
                            elif user_choice['value'] == 'all':
                                self.overwrite_all = True
                            elif user_choice['value'] == 'version_all':
                                self.version_all = True
                            elif user_choice['value'] == 'skip':
                                progress.update(item['name'], 0)
                                continue
                            elif user_choice['value'] == 'skip_all':
                                self.skip_all = True
                                progress.update(item['name'], 0)
                                continue
                            elif user_choice['value'] == 'version':
                                pass  # Просто загружаем, S3 создаст версию
                    
                    if self.skip_all:
                        progress.update(item['name'], 0)
                        continue
                    
                    file_size = item.get('size', 0)
                    progress.update(item['name'], file_size)
                    self.loop.draw_screen()
                    
                    if dest_panel.s3_manager.upload_file(source_path, dest_panel.current_bucket, dest_key):
                        progress.add_success()
                        if is_move:
                            items_to_delete.append(item_data)
                    else:
                        progress.add_failure()
                
                # FS директория -> S3
                elif item_type == 'fs_dir' and dest_panel.mode == 's3' and dest_panel.current_bucket:
                    all_success = True
                    for file_info in item_data['files']:
                        if progress.cancelled:
                            break
                        
                        if len(analyzed) == 1:
                            if target_name:
                                dest_key = target_name.rstrip('/') + '/' + file_info['rel_path'].replace(os.sep, '/')
                            else:
                                dest_key = file_info['rel_path'].replace(os.sep, '/')
                        else:
                            if target_name:
                                dest_key = target_name.rstrip('/') + '/' + item['name'] + '/' + file_info['rel_path'].replace(os.sep, '/')
                            else:
                                dest_key = item['name'] + '/' + file_info['rel_path'].replace(os.sep, '/')
                        
                        # Проверка существования для файлов в директории
                        if not self.overwrite_all and not self.version_all and not self.skip_all:
                            existing = dest_panel.s3_manager.object_exists(dest_panel.current_bucket, dest_key)
                            if existing:
                                try:
                                    stat = os.stat(file_info['path'])
                                    source_info = {
                                        'size': stat.st_size,
                                        'mtime': datetime.fromtimestamp(stat.st_mtime)
                                    }
                                    dest_info = {
                                        'size': existing.get('Size',0),
                                        'mtime': existing.get('LastModified')
                                    }
                                    
                                    def show_overwrite_dialog():
                                        def on_choice(choice):
                                            user_choice['value'] = choice
                                            choice_event.set()
                                            self.close_dialog()
                                            self.show_dialog(progress)
                                        
                                        self._check_overwrite(file_info['rel_path'], source_info, dest_info, on_choice, is_s3_dest=True)
                                    
                                    self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                                    choice_event.wait()
                                    choice_event.clear()
                                    
                                    if user_choice['value'] == 'cancel':
                                        progress.cancelled = True
                                        break
                                    elif user_choice['value'] == 'all':
                                        self.overwrite_all = True
                                    elif user_choice['value'] == 'version_all':
                                        self.version_all = True
                                    elif user_choice['value'] == 'skip':
                                        progress.update(file_info['rel_path'], 0)
                                        continue
                                    elif user_choice['value'] == 'skip_all':
                                        self.skip_all = True
                                        progress.update(file_info['rel_path'], 0)
                                        continue
                                except:
                                    pass
                        
                        if self.skip_all:
                            progress.update(file_info['rel_path'], 0)
                            continue
                        
                        file_size = file_info.get('size', 0)
                        progress.update(file_info['rel_path'], file_size)
                        self.loop.draw_screen()
                        
                        if dest_panel.s3_manager.upload_file(file_info['path'], dest_panel.current_bucket, dest_key):
                            progress.add_success()
                        else:
                            progress.add_failure()
                            all_success = False
                    
                    if all_success and is_move:
                        items_to_delete.append(item_data)
                
                # S3 файл -> FS
                elif item_type == 's3_file' and dest_panel.mode == 'fs':
                    if len(analyzed) == 1:
                        if os.path.isabs(target_name):
                            dest_path = target_name
                        else:
                            dest_path = os.path.join(dest_panel.fs_browser.current_path, target_name)
                    else:
                        if target_name:
                            base_dir = os.path.join(dest_panel.fs_browser.current_path, target_name)
                        else:
                            base_dir = dest_panel.fs_browser.current_path
                        os.makedirs(base_dir, exist_ok=True)
                        dest_path = os.path.join(base_dir, item['name'])
                    
                    # Проверка существования
                    if not self.overwrite_all and not self.skip_all:
                        if os.path.exists(dest_path):
                            source_info = {
                                'size': item.get('size',0),
                                'mtime': item.get('mtime')
                                #'size': item['size'],
                                #'mtime': item['mtime']
                            }
                            existing_stat = os.stat(dest_path)
                            dest_info = {
                                'size': existing_stat.st_size,
                                'mtime': datetime.fromtimestamp(existing_stat.st_mtime)
                            }
                            
                            def show_overwrite_dialog():
                                def on_choice(choice):
                                    user_choice['value'] = choice
                                    choice_event.set()
                                    self.close_dialog()
                                    self.show_dialog(progress)
                                
                                self._check_overwrite(item['name'], source_info, dest_info, on_choice, is_s3_dest=False)
                            
                            self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                            choice_event.wait()
                            choice_event.clear()
                            
                            if user_choice['value'] == 'cancel':
                                progress.cancelled = True
                                break
                            elif user_choice['value'] == 'all':
                                self.overwrite_all = True
                            elif user_choice['value'] == 'skip':
                                progress.update(item['name'], 0)
                                continue
                            elif user_choice['value'] == 'skip_all':
                                self.skip_all = True
                                progress.update(item['name'], 0)
                                continue
                    
                    if self.skip_all:
                        progress.update(item['name'], 0)
                        continue
                    
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    
                    file_size = item.get('size', 0)
                    progress.update(item['name'], file_size)
                    self.loop.draw_screen()
                    
                    if source_panel.s3_manager.download_object(source_panel.current_bucket, item['key'], dest_path):
                        progress.add_success()
                        if is_move:
                            items_to_delete.append(item_data)
                    else:
                        progress.add_failure()
                
                # S3 директория -> FS
                elif item_type == 's3_dir' and dest_panel.mode == 'fs':
                    all_success = True
                    for obj in item_data['files']:
                        if progress.cancelled:
                            break
                        
                        rel_key = obj['Key'][len(item['key']):]
                        
                        if len(analyzed) == 1:
                            if target_name:
                                dest_path = os.path.join(dest_panel.fs_browser.current_path, target_name, rel_key.replace('/', os.sep))
                            else:
                                dest_path = os.path.join(dest_panel.fs_browser.current_path, rel_key.replace('/', os.sep))
                        else:
                            if target_name:
                                dest_path = os.path.join(dest_panel.fs_browser.current_path, target_name, item['name'], rel_key.replace('/', os.sep))
                            else:
                                dest_path = os.path.join(dest_panel.fs_browser.current_path, item['name'], rel_key.replace('/', os.sep))
                        
                        # Проверка существования
                        if not self.overwrite_all and not self.skip_all:
                            if os.path.exists(dest_path):
                                source_info = {
                                    'size': obj.get('Size', 0),
                                    'mtime': obj.get('LastModified', datetime.now())
                                }
                                existing_stat = os.stat(dest_path)
                                dest_info = {
                                    'size': existing_stat.st_size,
                                    'mtime': datetime.fromtimestamp(existing_stat.st_mtime)
                                }
                                
                                def show_overwrite_dialog():
                                    def on_choice(choice):
                                        user_choice['value'] = choice
                                        choice_event.set()
                                        self.close_dialog()
                                        self.show_dialog(progress)
                                    
                                    self._check_overwrite(rel_key, source_info, dest_info, on_choice, is_s3_dest=False)
                                
                                self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                                choice_event.wait()
                                choice_event.clear()
                                
                                if user_choice['value'] == 'cancel':
                                    progress.cancelled = True
                                    break
                                elif user_choice['value'] == 'all':
                                    self.overwrite_all = True
                                elif user_choice['value'] == 'skip':
                                    progress.update(rel_key, 0)
                                    continue
                                elif user_choice['value'] == 'skip_all':
                                    self.skip_all = True
                                    progress.update(rel_key, 0)
                                    continue
                        
                        if self.skip_all:
                            progress.update(rel_key, 0)
                            continue
                        
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        
                        file_size = obj.get('Size', 0)
                        progress.update(rel_key, file_size)
                        self.loop.draw_screen()
                        
                        if source_panel.s3_manager.download_object(source_panel.current_bucket, obj['Key'], dest_path):
                            progress.add_success()
                        else:
                            progress.add_failure()
                            all_success = False
                    
                    if all_success and is_move:
                        items_to_delete.append(item_data)
                
                # S3 файл -> S3
                elif item_type == 's3_file' and dest_panel.mode == 's3' and dest_panel.current_bucket:
                    if len(analyzed) == 1:
                        dest_key = target_name if target_name else item['name']
                    else:
                        if target_name:
                            dest_key = target_name.rstrip('/') + '/' + item['name']
                        else:
                            dest_key = item['name']
                    
                    # Проверка существования
                    if not self.overwrite_all and not self.version_all and not self.skip_all:
                        existing = dest_panel.s3_manager.object_exists(dest_panel.current_bucket, dest_key)
                        if existing:
                            source_info = {
                                'size': item.get('size',0),
                                'mtime': item.get('mtime', datetime.now())
                            }
                            dest_info = {
                                'size': existing.get('Size',0),
                                'mtime': existing.get('LastModified')
                            }
                            
                            def show_overwrite_dialog():
                                def on_choice(choice):
                                    user_choice['value'] = choice
                                    choice_event.set()
                                    self.close_dialog()
                                    self.show_dialog(progress)
                                
                                self._check_overwrite(item['name'], source_info, dest_info, on_choice, is_s3_dest=True)
                            
                            self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                            choice_event.wait()
                            choice_event.clear()
                            
                            if user_choice['value'] == 'cancel':
                                progress.cancelled = True
                                break
                            elif user_choice['value'] == 'all':
                                self.overwrite_all = True
                            elif user_choice['value'] == 'version_all':
                                self.version_all = True
                            elif user_choice['value'] == 'skip':
                                progress.update(item['name'], 0)
                                continue
                            elif user_choice['value'] == 'skip_all':
                                self.skip_all = True
                                progress.update(item['name'], 0)
                                continue
                    
                    if self.skip_all:
                        progress.update(item['name'], 0)
                        continue
                    
                    file_size = item.get('size', 0)
                    progress.update(item['name'], file_size)
                    self.loop.draw_screen()
                    
                    if source_panel.s3_manager.copy_object(
                        source_panel.current_bucket, 
                        item['key'], 
                        dest_panel.current_bucket, 
                        dest_key
                    ):
                        progress.add_success()
                        if is_move:
                            items_to_delete.append(item_data)
                    else:
                        progress.add_failure()
                
                # S3 директория -> S3
                elif item_type == 's3_dir' and dest_panel.mode == 's3' and dest_panel.current_bucket:
                    all_success = True
                    for obj in item_data['files']:
                        if progress.cancelled:
                            break
                        
                        rel_key = obj['Key'][len(item['key']):]
                        
                        if len(analyzed) == 1:
                            if target_name:
                                dest_key = target_name.rstrip('/') + '/' + rel_key
                            else:
                                dest_key = rel_key
                        else:
                            if target_name:
                                dest_key = target_name.rstrip('/') + '/' + item['name'] + '/' + rel_key
                            else:
                                dest_key = item['name'] + '/' + rel_key
                        
                        # Проверка существования
                        if not self.overwrite_all and not self.version_all and not self.skip_all:
                            existing = dest_panel.s3_manager.object_exists(dest_panel.current_bucket, dest_key)
                            if existing:
                                source_info = {
                                    'size': obj.get('Size', 0),
                                    'mtime': obj.get('LastModified', datetime.now())
                                }
                                dest_info = {
                                    'size': existing.get('Size',0),
                                    'mtime': existing.get('LastModified')
                                }
                                
                                def show_overwrite_dialog():
                                    def on_choice(choice):
                                        user_choice['value'] = choice
                                        choice_event.set()
                                        self.close_dialog()
                                        self.show_dialog(progress)
                                    
                                    self._check_overwrite(rel_key, source_info, dest_info, on_choice, is_s3_dest=True)
                                
                                self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                                choice_event.wait()
                                choice_event.clear()
                                
                                if user_choice['value'] == 'cancel':
                                    progress.cancelled = True
                                    break
                                elif user_choice['value'] == 'all':
                                    self.overwrite_all = True
                                elif user_choice['value'] == 'version_all':
                                    self.version_all = True
                                elif user_choice['value'] == 'skip':
                                    progress.update(rel_key, 0)
                                    continue
                                elif user_choice['value'] == 'skip_all':
                                    self.skip_all = True
                                    progress.update(rel_key, 0)
                                    continue
                        
                        if self.skip_all:
                            progress.update(rel_key, 0)
                            continue
                        
                        file_size = obj.get('Size', 0)
                        progress.update(rel_key, file_size)
                        self.loop.draw_screen()
                        
                        if source_panel.s3_manager.copy_object(
                            source_panel.current_bucket,
                            obj['Key'],
                            dest_panel.current_bucket,
                            dest_key
                        ):
                            progress.add_success()
                        else:
                            progress.add_failure()
                            all_success = False
                    
                    if all_success and is_move:
                        items_to_delete.append(item_data)
                
                # FS файл -> FS
                elif item_type == 'fs_file' and dest_panel.mode == 'fs':
                    source_path = os.path.join(source_panel.fs_browser.current_path, item['name'])
                    
                    if len(analyzed) == 1:
                        if os.path.isabs(target_name):
                            dest_path = target_name
                        else:
                            dest_path = os.path.join(dest_panel.fs_browser.current_path, target_name)
                    else:
                        if target_name:
                            base_dir = os.path.join(dest_panel.fs_browser.current_path, target_name)
                        else:
                            base_dir = dest_panel.fs_browser.current_path
                        os.makedirs(base_dir, exist_ok=True)
                        dest_path = os.path.join(base_dir, item['name'])
                    
                    # Проверка существования
                    if not self.overwrite_all and not self.skip_all:
                        if os.path.exists(dest_path):
                            source_info = {
                                'size': item.get('size',0),
                                'mtime': item.get('mtime')
                            }
                            existing_stat = os.stat(dest_path)
                            dest_info = {
                                'size': existing_stat.st_size,
                                'mtime': datetime.fromtimestamp(existing_stat.st_mtime)
                            }
                            
                            def show_overwrite_dialog():
                                def on_choice(choice):
                                    user_choice['value'] = choice
                                    choice_event.set()
                                    self.close_dialog()
                                    self.show_dialog(progress)
                                
                                self._check_overwrite(item['name'], source_info, dest_info, on_choice, is_s3_dest=False)
                            
                            self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                            choice_event.wait()
                            choice_event.clear()
                            
                            if user_choice['value'] == 'cancel':
                                progress.cancelled = True
                                break
                            elif user_choice['value'] == 'all':
                                self.overwrite_all = True
                            elif user_choice['value'] == 'skip':
                                progress.update(item['name'], 0)
                                continue
                            elif user_choice['value'] == 'skip_all':
                                self.skip_all = True
                                progress.update(item['name'], 0)
                                continue
                    
                    if self.skip_all:
                        progress.update(item['name'], 0)
                        continue
                    
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    
                    file_size = item.get('size', 0)
                    progress.update(item['name'], file_size)
                    self.loop.draw_screen()
                    
                    try:
                        shutil.copy2(source_path, dest_path)
                        progress.add_success()
                        if is_move:
                            items_to_delete.append(item_data)
                    except (IOError, OSError):
                        progress.add_failure()
                
                # FS директория -> FS
                elif item_type == 'fs_dir' and dest_panel.mode == 'fs':
                    source_dir = os.path.join(source_panel.fs_browser.current_path, item['name'])
                    
                    if len(analyzed) == 1:
                        if target_name:
                            dest_dir = os.path.join(dest_panel.fs_browser.current_path, target_name)
                        else:
                            dest_dir = os.path.join(dest_panel.fs_browser.current_path, item['name'])
                    else:
                        if target_name:
                            dest_dir = os.path.join(dest_panel.fs_browser.current_path, target_name, item['name'])
                        else:
                            dest_dir = os.path.join(dest_panel.fs_browser.current_path, item['name'])
                    
                    all_success = True
                    for file_info in item_data['files']:
                        if progress.cancelled:
                            break
                        
                        dest_path = os.path.join(dest_dir, file_info['rel_path'])
                        
                        # Проверка существования
                        if not self.overwrite_all and not self.skip_all:
                            if os.path.exists(dest_path):
                                try:
                                    stat = os.stat(file_info['path'])
                                    source_info = {
                                        'size': stat.st_size,
                                        'mtime': datetime.fromtimestamp(stat.st_mtime)
                                    }
                                    existing_stat = os.stat(dest_path)
                                    dest_info = {
                                        'size': existing_stat.st_size,
                                        'mtime': datetime.fromtimestamp(existing_stat.st_mtime)
                                    }
                                    
                                    def show_overwrite_dialog():
                                        def on_choice(choice):
                                            user_choice['value'] = choice
                                            choice_event.set()
                                            self.close_dialog()
                                            self.show_dialog(progress)
                                        
                                        self._check_overwrite(file_info['rel_path'], source_info, dest_info, on_choice, is_s3_dest=False)
                                    
                                    self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                                    choice_event.wait()
                                    choice_event.clear()
                                    
                                    if user_choice['value'] == 'cancel':
                                        progress.cancelled = True
                                        break
                                    elif user_choice['value'] == 'all':
                                        self.overwrite_all = True
                                    elif user_choice['value'] == 'skip':
                                        progress.update(file_info['rel_path'], 0)
                                        continue
                                    elif user_choice['value'] == 'skip_all':
                                        self.skip_all = True
                                        progress.update(file_info['rel_path'], 0)
                                        continue
                                except:
                                    pass
                        
                        if self.skip_all:
                            progress.update(file_info['rel_path'], 0)
                            continue
                        
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        
                        file_size = file_info.get('size', 0)
                        progress.update(file_info['rel_path'], file_size)
                        self.loop.draw_screen()
                        
                        try:
                            shutil.copy2(file_info['path'], dest_path)
                            progress.add_success()
                        except (IOError, OSError):
                            progress.add_failure()
                            all_success = False
                    
                    if all_success and is_move:
                        items_to_delete.append(item_data)
                
                # Бакет -> S3
                elif item_type == 'bucket' and dest_panel.mode == 's3' and dest_panel.current_bucket:
                    all_success = True
                    for obj in item_data['files']:
                        if progress.cancelled:
                            break
                        
                        if len(analyzed) == 1:
                            if target_name:
                                dest_key = target_name.rstrip('/') + '/' + obj['Key']
                            else:
                                dest_key = obj['Key']
                        else:
                            if target_name:
                                dest_key = target_name.rstrip('/') + '/' + item['name'] + '/' + obj['Key']
                            else:
                                dest_key = item['name'] + '/' + obj['Key']
                        
                        # Проверка существования
                        if not self.overwrite_all and not self.version_all and not self.skip_all:
                            existing = dest_panel.s3_manager.object_exists(dest_panel.current_bucket, dest_key)
                            if existing:
                                source_info = {
                                    'size': obj.get('Size', 0),
                                    'mtime': obj.get('LastModified', datetime.now())
                                }
                                dest_info = {
                                    'size': existing.get('Size',0),
                                    'mtime': existing.get('LastModified')
                                }
                                
                                def show_overwrite_dialog():
                                    def on_choice(choice):
                                        user_choice['value'] = choice
                                        choice_event.set()
                                        self.close_dialog()
                                        self.show_dialog(progress)
                                    
                                    self._check_overwrite(obj['Key'], source_info, dest_info, on_choice, is_s3_dest=True)
                                
                                self.loop.set_alarm_in(0, lambda *args: show_overwrite_dialog())
                                choice_event.wait()
                                choice_event.clear()
                                
                                if user_choice['value'] == 'cancel':
                                    progress.cancelled = True
                                    break
                                elif user_choice['value'] == 'all':
                                    self.overwrite_all = True
                                elif user_choice['value'] == 'version_all':
                                    self.version_all = True
                                elif user_choice['value'] == 'skip':
                                    progress.update(obj['Key'], 0)
                                    continue
                                elif user_choice['value'] == 'skip_all':
                                    self.skip_all = True
                                    progress.update(obj['Key'], 0)
                                    continue
                        
                        if self.skip_all:
                            progress.update(obj['Key'], 0)
                            continue
                        
                        file_size = obj.get('Size', 0)
                        progress.update(obj['Key'], file_size)
                        self.loop.draw_screen()
                        
                        if source_panel.s3_manager.copy_object(
                            item['name'],
                            obj['Key'],
                            dest_panel.current_bucket,
                            dest_key
                        ):
                            progress.add_success()
                        else:
                            progress.add_failure()
                            all_success = False
                    
                    if all_success and is_move:
                        items_to_delete.append(item_data)
            
            # Удаляем успешно перемещенные элементы
            if is_move:
                for item_data in items_to_delete:
                    item_type = item_data['type']
                    item = item_data['item']
                    
                    if item_type == 'fs_file':
                        try:
                            source_path = os.path.join(source_panel.fs_browser.current_path, item['name'])
                            os.remove(source_path)
                        except OSError:
                            pass
                    
                    elif item_type == 'fs_dir':
                        try:
                            dir_path = os.path.join(source_panel.fs_browser.current_path, item['name'])
                            shutil.rmtree(dir_path)
                        except OSError:
                            pass
                    
                    elif item_type == 's3_file':
                        source_panel.s3_manager.delete_object(source_panel.current_bucket, item['key'])
                    
                    elif item_type == 's3_dir':
                        for obj in item_data['files']:
                            source_panel.s3_manager.delete_object(source_panel.current_bucket, obj['Key'])
                    
                    elif item_type == 'bucket':
                        for obj in item_data['files']:
                            source_panel.s3_manager.delete_object(item['name'], obj['Key'])
                        source_panel.s3_manager.delete_bucket(item['name'])
            
            time.sleep(0.5)
            self.loop.draw_screen()
        
        thread = threading.Thread(target=copy_thread)
        thread.daemon = True
        thread.start()
        
        def check_thread():
            if thread.is_alive():
                self.loop.set_alarm_in(0.1, lambda *args: check_thread())
            else:
                self.close_dialog()
                dest_panel.refresh()
                if focus_name:
                    source_panel.refresh(focus_on=focus_name)
                else:
                    source_panel.refresh()
                
                operation = 'Moved' if is_move else 'Copied'
                speed_str = progress.get_speed_str()
                self.show_result(
                    f'{operation}: {progress.success_count} file(s), Failed: {progress.fail_count} file(s), '
                    f'Total: {format_size(progress.processed_bytes)}, Speed: {speed_str}'
                )
        
        self.loop.set_alarm_in(0.1, lambda *args: check_thread())



    def toggle_versioning(self):
        active_panel = self.get_active_panel()
        
        if active_panel.mode != 's3' or not active_panel.current_bucket:
            self.show_result('This function works only with S3 buckets')
            return
        
        status = active_panel.s3_manager.get_versioning_status(active_panel.current_bucket)
        
        if status == 'Enabled':
            # Версионирование включено - предлагаем отключить
            def callback(confirmed):
                self.close_dialog()
                if confirmed:
                    if active_panel.s3_manager.disable_versioning(active_panel.current_bucket):
                        self.show_result(f'Versioning SUSPENDED for bucket "{active_panel.current_bucket}"')
                        active_panel.refresh()
                    else:
                        self.show_result(f'Failed to suspend versioning')
            
            message = f'Suspend versioning for bucket "{active_panel.current_bucket}"?\n(Existing versions will be preserved)'
            dialog = ConfirmDialog('Suspend Versioning', message, [], callback)
            self.show_dialog(dialog)
        else:
            # Версионирование отключено - предлагаем включить
            def callback(confirmed):
                self.close_dialog()
                if confirmed:
                    if active_panel.s3_manager.enable_versioning(active_panel.current_bucket):
                        self.show_result(f'Versioning ENABLED for bucket "{active_panel.current_bucket}"')
                        active_panel.refresh()
                    else:
                        self.show_result(f'Failed to enable versioning')
            
            current_status = "DISABLED" if status is None or status == 'Disabled' else "SUSPENDED"
            message = f'Enable versioning for bucket "{active_panel.current_bucket}"?\n(Current status: {current_status})'
            dialog = ConfirmDialog('Enable Versioning', message, [], callback)
            self.show_dialog(dialog)
    
    def delete_items(self):
        active_panel = self.get_active_panel()
        
        if active_panel.is_root_menu() or active_panel.is_endpoint_list():
            self.show_result('Cannot delete from this level')
            return
        
        selected_items = active_panel.get_selected_items()
        if not selected_items:
            focused = active_panel.get_focused_item()
            if focused and focused['type'] in ('bucket', 'fs_file', 's3_file', 'fs_dir', 's3_dir'):
                selected_items = [focused]
        
        if not selected_items:
            self.show_result('No items to delete')
            return
        
        analyzed, items_info, total_bytes = self.analyze_items(selected_items, active_panel)
        total_files = sum(len(a['files']) for a in analyzed)
        
        def callback(confirmed):
            self.close_dialog()
            if confirmed:
                current_item = active_panel.get_focused_item()
                focus_name = current_item.get('name') if current_item else None
                
                self._do_delete_with_progress(analyzed, active_panel, focus_name, total_bytes)
        
        message = f'Delete {len(selected_items)} item(s) ({total_files} file(s) total)?\nThis action cannot be undone!'
        dialog = ConfirmDialog('Confirm Delete', message, items_info, callback)
        self.show_dialog(dialog)

    def _do_delete_with_progress(self, analyzed, panel, focus_name, total_bytes):
        total_files = sum(len(a['files']) for a in analyzed)
        
        progress = ProgressDialog('Deleting files...', callback=self.close_dialog)
        progress.set_total(total_files, total_bytes)
        self.show_dialog(progress)
        
        def delete_thread():
            for item_data in analyzed:
                if progress.cancelled:
                    break
                
                item_type = item_data['type']
                item = item_data['item']
                
                if item_type == 'bucket':
                    for obj in item_data['files']:
                        if progress.cancelled:
                            break
                        
                        file_size = obj.get('Size', 0)
                        progress.update(obj['Key'], file_size)
                        self.loop.draw_screen()
                        
                        if panel.s3_manager.delete_object(item['name'], obj['Key']):
                            progress.add_success()
                        else:
                            progress.add_failure()
                    panel.s3_manager.delete_bucket(item['name'])
                
                elif item_type == 's3_file':
                    file_size = item.get('size', 0)
                    progress.update(item['name'], file_size)
                    self.loop.draw_screen()
                    
                    if panel.s3_manager.delete_object(panel.current_bucket, item['key']):
                            progress.add_success()
                    else:
                            progress.add_failure()
                
                elif item_type == 's3_dir':
                    for obj in item_data['files']:
                        if progress.cancelled:
                            break
                        
                        file_size = obj.get('Size', 0)
                        progress.update(obj['Key'], file_size)
                        self.loop.draw_screen()
                        
                        if panel.s3_manager.delete_object(panel.current_bucket, obj['Key']):
                            progress.add_success()
                        else:
                            progress.add_failure()
                
                elif item_type == 'fs_file':
                    try:
                        file_path = os.path.join(panel.fs_browser.current_path, item['name'])
                        
                        file_size = item.get('size', 0)
                        progress.update(item['name'], file_size)
                        self.loop.draw_screen()
                        
                        os.remove(file_path)
                        progress.add_success()
                    except OSError:
                        progress.add_failure()
                
                elif item_type == 'fs_dir':
                    try:
                        dir_path = os.path.join(panel.fs_browser.current_path, item['name'])
                        
                        for file_info in item_data['files']:
                            if progress.cancelled:
                                break
                            
                            file_size = file_info.get('size', 0)
                            progress.update(file_info['rel_path'], file_size)
                            self.loop.draw_screen()
                            
                            shutil.rmtree(dir_path)
                        progress.success_count += len(item_data['files'])
                    except OSError:
                        progress.fail_count += len(item_data['files'])
            
            time.sleep(0.5)
            self.loop.draw_screen()
        
        thread = threading.Thread(target=delete_thread)
        thread.daemon = True
        thread.start()
        
        def check_thread():
            if thread.is_alive():
                self.loop.set_alarm_in(0.1, lambda *args: check_thread())
            else:
                self.close_dialog()
                if focus_name:
                    panel.refresh(focus_on=focus_name)
                else:
                    panel.refresh()
                speed_str = progress.get_speed_str()
                self.show_result(
                    f'Deleted: {progress.success_count} file(s), Failed: {progress.fail_count} file(s), '
                    f'Total: {format_size(progress.processed_bytes)}, Speed: {speed_str}'
                )
        
        self.loop.set_alarm_in(0.1, lambda *args: check_thread())

if __name__ == '__main__':
    s3_config = S3Config('s3_config.json')
    app = DualPaneApp(s3_config)
    app.run()
