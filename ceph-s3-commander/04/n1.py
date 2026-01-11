Я добавлю к коду функциональность кеширования списков файлов и ленивой загрузки. Вот обновленная версия с этими улучшениями:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Двухпанельный файловый менеджер для S3 Ceph с поддержкой множественных endpoints
Версия с кешированием и ленивой загрузкой
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
from collections import OrderedDict
import hashlib

__VERSION__ = "1.1.0"
__AUTHOR__ = "Тарасов Дмитрий"


import socket
from urllib.parse import urlparse

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


class LRUCache:
    """LRU кеш для хранения списков файлов"""
    
    def __init__(self, max_size=100):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
    
    def get(self, key):
        """Получить значение из кеша"""
        if key in self.cache:
            self.hits += 1
            # Перемещаем в конец (последний использованный)
            self.cache.move_to_end(key)
            return self.cache[key]
        self.misses += 1
        return None
    
    def put(self, key, value):
        """Сохранить значение в кеш"""
        if key in self.cache:
            # Обновляем существующее значение
            self.cache.move_to_end(key)
        else:
            # Добавляем новое значение
            if len(self.cache) >= self.max_size:
                # Удаляем самый старый элемент
                self.cache.popitem(last=False)
        self.cache[key] = value
    
    def invalidate(self, pattern=None):
        """Инвалидировать кеш (полностью или по шаблону)"""
        if pattern is None:
            self.cache.clear()
        else:
            keys_to_remove = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self.cache[key]
    
    def get_stats(self):
        """Получить статистику кеша"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            'size': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate
        }


class LazyLoadingList:
    """Список с ленивой загрузкой элементов"""
    
    def __init__(self, loader_func, page_size=100):
        self.loader_func = loader_func
        self.page_size = page_size
        self.items = []
        self.total_items = None
        self.loaded_pages = set()
        self.is_fully_loaded = False
        self.lock = threading.Lock()
    
    def load_page(self, page_num):
        """Загрузить страницу данных"""
        with self.lock:
            if page_num in self.loaded_pages or self.is_fully_loaded:
                return
            
            start = page_num * self.page_size
            end = start + self.page_size
            
            new_items = self.loader_func(start, end)
            
            if not new_items:
                self.is_fully_loaded = True
                return
            
            # Расширяем список если нужно
            if len(self.items) < end:
                self.items.extend([None] * (end - len(self.items)))
            
            # Заполняем загруженными элементами
            for i, item in enumerate(new_items):
                self.items[start + i] = item
            
            self.loaded_pages.add(page_num)
            
            if len(new_items) < self.page_size:
                self.is_fully_loaded = True
                # Обрезаем список до реального размера
                self.items = [item for item in self.items if item is not None]
    
    def get_item(self, index):
        """Получить элемент по индексу (с автозагрузкой при необходимости)"""
        page_num = index // self.page_size
        
        if page_num not in self.loaded_pages:
            self.load_page(page_num)
        
        if index < len(self.items):
            return self.items[index]
        return None
    
    def get_slice(self, start, end):
        """Получить срез элементов"""
        start_page = start // self.page_size
        end_page = end // self.page_size
        
        for page in range(start_page, end_page + 1):
            if page not in self.loaded_pages:
                self.load_page(page)
        
        return self.items[start:end]
    
    def __len__(self):
        if self.is_fully_loaded:
            return len([item for item in self.items if item is not None])
        # Оценочное значение до полной загрузки
        return len(self.loaded_pages) * self.page_size
    
    def __iter__(self):
        # Загружаем все данные для итерации
        page = 0
        while not self.is_fully_loaded:
            self.load_page(page)
            page += 1
        
        return iter([item for item in self.items if item is not None])


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


class S3Manager:
    """Менеджер для работы с S3 Ceph с кешированием"""
    
    def __init__(self, endpoint_config):
        self.endpoint_name = endpoint_config['name']
        self.endpoint_url = endpoint_config['url']
        self.access_key = endpoint_config['access_key']
        self.secret_key = endpoint_config['secret_key']
        self.is_connected = False
        self.connection_error = None
        
        # Кеш для списков
        self.cache = LRUCache(max_size=50)
        
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
    
    def _get_cache_key(self, operation, *args):
        """Генерация ключа кеша"""
        key_parts = [self.endpoint_name, operation] + [str(arg) for arg in args]
        key_str = ":".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def list_buckets(self, use_cache=True):
        """Получить список бакетов с кешированием"""
        cache_key = self._get_cache_key('list_buckets')
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
        if self.s3_client is None:
            return []
        try:
            response = self.s3_client.list_buckets()
            self.is_connected = True
            buckets = response['Buckets']
            
            if use_cache:
                self.cache.put(cache_key, buckets)
            
            return buckets
        except (ClientError, Exception) as e:
            self.is_connected = False
            self.connection_error = str(e)
            return []

    def create_bucket(self, bucket_name):
        if self.s3_client is None:
            return False
        try:
            self.s3_client.create_bucket(Bucket=bucket_name)
            # Инвалидируем кеш списка бакетов
            self.cache.invalidate('list_buckets')
            return True
        except (ClientError, Exception):
            return False

    def delete_bucket(self, bucket_name):
        if self.s3_client is None:
            return False
        try:
            self.s3_client.delete_bucket(Bucket=bucket_name)
            # Инвалидируем кеш
            self.cache.invalidate('list_buckets')
            self.cache.invalidate(bucket_name)
            return True
        except (ClientError, Exception):
            return False

    def list_objects(self, bucket_name, prefix='', use_cache=True):
        """Получить список объектов с кешированием"""
        cache_key = self._get_cache_key('list_objects', bucket_name, prefix)
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
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
            
            result = (folders, files)
            
            if use_cache:
                self.cache.put(cache_key, result)
            
            return result
        except (ClientError, Exception):
            return [], []
    
    def list_objects_lazy(self, bucket_name, prefix='', page_size=100):
        """Ленивая загрузка объектов"""
        if self.s3_client is None:
            return LazyLoadingList(lambda s, e: [], page_size)
        
        def loader(start, end):
            try:
                paginator = self.s3_client.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(
                    Bucket=bucket_name,
                    Prefix=prefix,
                    PaginationConfig={
                        'PageSize': page_size,
                        'StartingToken': None
                    }
                )
                
                items = []
                count = 0
                
                for page in page_iterator:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            if obj['Key'] != prefix and not obj['Key'].endswith('/'):
                                if count >= start:
                                    items.append(obj)
                                    if len(items) >= (end - start):
                                        return items
                                count += 1
                
                return items
            except (ClientError, Exception):
                return []
        
        return LazyLoadingList(loader, page_size)

    def list_all_objects(self, bucket_name, prefix='', use_cache=True):
        """Получить все объекты с кешированием"""
        cache_key = self._get_cache_key('list_all_objects', bucket_name, prefix)
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
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
            
            if use_cache:
                self.cache.put(cache_key, objects)
            
            return objects
        except (ClientError, Exception):
            return []

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

    def list_object_versions(self, bucket_name, key, use_cache=True):
        """Получить список версий объекта с кешированием"""
        cache_key = self._get_cache_key('list_versions', bucket_name, key)
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
        if self.s3_client is None:
            return []
        try:
            response = self.s3_client.list_object_versions(Bucket=bucket_name, Prefix=key)
            versions = []
            if 'Versions' in response:
                for v in response['Versions']:
                    if v['Key'] == key:
                        versions.append(v)
            
            if use_cache:
                self.cache.put(cache_key, versions)
            
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
            # Инвалидируем кеш для этого пути
            prefix = '/'.join(key.split('/')[:-1])
            self.cache.invalidate(f'{bucket_name}:{prefix}')
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
            # Инвалидируем кеш
            prefix = '/'.join(dest_key.split('/')[:-1])
            self.cache.invalidate(f'{dest_bucket}:{prefix}')
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
            # Инвалидируем кеш
            prefix = '/'.join(key.split('/')[:-1])
            self.cache.invalidate(f'{bucket_name}:{prefix}')
            self.cache.invalidate(f'list_versions:{bucket_name}:{key}')
            return True
        except (ClientError, Exception):
            return False

    def delete_old_versions(self, bucket_name, key):
        """Удалить все версии кроме последней"""
        if self.s3_client is None:
            return 0
        try:
            versions = self.list_object_versions(bucket_name, key, use_cache=False)
            if len(versions) <= 1:
                return 0
            
            versions.sort(key=lambda x: x.get('LastModified', datetime.min), reverse=True)
            
            deleted_count = 0
            for version in versions[1:]:
                if self.delete_object(bucket_name, key, version['VersionId']):
                    deleted_count += 1
            
            # Инвалидируем кеш версий
            self.cache.invalidate(f'list_versions:{bucket_name}:{key}')
            
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
            # Инвалидируем кеш бакета
            self.cache.invalidate(f'versioning:{bucket_name}')
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
            # Инвалидируем кеш
            self.cache.invalidate(f'versioning:{bucket_name}')
            return True
        except (ClientError, Exception):
            return False

    def get_versioning_status(self, bucket_name, use_cache=True):
        """Получить статус версионирования бакета"""
        cache_key = self._get_cache_key('versioning', bucket_name)
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
        if self.s3_client is None:
            return None
        try:
            response = self.s3_client.get_bucket_versioning(Bucket=bucket_name)
            status = response.get('Status', 'Disabled')
            
            if use_cache:
                self.cache.put(cache_key, status)
            
            return status
        except (ClientError, Exception):
            return None
    
    def get_cache_stats(self):
        """Получить статистику кеша"""
        return self.cache.get_stats()
    
    def clear_cache(self):
        """Очистить весь кеш"""
        self.cache.invalidate()


class FileSystemBrowser:
    """Браузер локальной файловой системы с кешированием"""
    
    def __init__(self):
        self.current_path = os.path.expanduser('~')
        self.cache = LRUCache(max_size=50)

    def list_directory(self, use_cache=True):
        """Получить список директории с кешированием"""
        cache_key = f'fs:{self.current_path}'
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
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
            
            if use_cache:
                self.cache.put(cache_key, items)
            
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
            # Инвалидируем кеш
            cache_key = f'fs:{self.current_path}'
            self.cache.invalidate()
            return True
        except OSError:
            return False
    
    def get_cache_stats(self):
        """Получить статистику кеша"""
        return self.cache.get_stats()
    
    def clear_cache(self):
        """Очистить кеш"""
        self.cache.invalidate()

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
                    self.on_cancel(None)
                    return None
                if isinstance(btn, urwid.Button) and btn.get_label() == '[ Delete ]':
                    self.on_delete(None)
                    return None
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
                    self.on_cancel(None)
                    return None
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



