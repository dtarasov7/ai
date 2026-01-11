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
import base64
from botocore.exceptions import ClientError
from botocore.config import Config
from datetime import datetime
import tempfile
import shutil
import json
import threading
import time
import platform

import argparse
import getpass
import requests  # Для Vault (нужен pip install requests, обычно есть везде)
# Для шифрования (нужен pip install cryptography)
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
import socket
from urllib.parse import urlparse
import functools
from collections import OrderedDict


__VERSION__ = "1.2.0"
__AUTHOR__ = "Тарасов Дмитрий"

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
        w = w.original_widget  # LineBox
    if isinstance(w, urwid.LineBox):
        w = w.original_widget  # Filler
    if isinstance(w, urwid.Filler):
        w = w.body  # Pile

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
    """
    Управление конфигурацией S3 endpoints.
    Поддерживает 3 режима:
    1. Plaintext JSON (файл)
    2. Encrypted (файл + пароль)
    3. HashiCorp Vault (API)
    """
    def __init__(self, args):
        self.endpoints = []
        self.args = args
        self.load_config()

    def _exit_error(self, message):
        """Вывод ошибки и завершение программы"""
        print(f"\nCRITICAL ERROR: {message}")
        sys.exit(1)

    def load_config(self):
        """Маршрутизация загрузки в зависимости от аргументов"""
        if self.args.vault_url:
            self._load_from_vault()
        elif self.args.encrypted_config:
            self._load_from_encrypted_file()
        else:
            self._load_from_plain_file()

    # --- РЕЖИМ 1: Обычный файл ---
    def _load_from_plain_file(self):
        config_file = self.args.config
        if not os.path.exists(config_file):
            self._exit_error(f"Config file '{config_file}' not found.\n"
                             "Run with default settings or create config file manually.")
        
        try:
            with open(config_file, 'r') as f:
                data = json.load(f)
                self.endpoints = data.get('endpoints', [])
        except json.JSONDecodeError as e:
            self._exit_error(f"Syntax error in '{config_file}': {e}")
        except Exception as e:
            self._exit_error(f"Cannot read config '{config_file}': {e}")

        if not self.endpoints:
            self._exit_error("Config file is empty or has no 'endpoints' list.")

    # --- РЕЖИМ 2: Зашифрованный файл ---
    def _load_from_encrypted_file(self):
        if not HAS_CRYPTO:
            self._exit_error("Module 'cryptography' is missing. Install it: pip install cryptography")
            
        enc_file = self.args.encrypted_config
        if not os.path.exists(enc_file):
            self._exit_error(f"Encrypted config '{enc_file}' not found.")

        try:
            # Читаем ВСЕ байты
            with open(enc_file, 'rb') as f:
                file_content = f.read()
            
            if len(file_content) < 40: # 16 (salt) + ~20 (min fernet overhead)
                self._exit_error("Encrypted file is too short/corrupted.")
                
            salt = file_content[:16]
            encrypted_data = file_content[16:]
            
            # ВАЖНО: getpass может вернуть строку с пробелами в конце на некоторых терминалах
            print(f"Reading encrypted config: {enc_file}")
            password = getpass.getpass("Enter decryption password: ")
            
            # Убираем пробельные символы только если это случайно попавший \r или \n, 
            # но для безопасности пароля лучше брать как есть.
            # Если вы создавали пароль с пробелом в конце - он важен!
            
            # Генерируем ключ (параметры ДОЛЖНЫ совпадать с encryptor.py)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend() 
                # backend default is OK
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))
            
            f = Fernet(key)
            
            # Пытаемся расшифровать
            try:
                decrypted_data = f.decrypt(encrypted_data)
            except Exception:
                # Fernet кидает InvalidToken если пароль не подошел
                self._exit_error("Decryption failed! Invalid password or corrupted file.")
            
            # Декодируем JSON
            try:
                json_str = decrypted_data.decode('utf-8')
                data = json.loads(json_str)
                self.endpoints = data.get('endpoints', [])
            except json.JSONDecodeError:
                self._exit_error("Decrypted data is not valid JSON. Check source file integrity.")
                
        except Exception as e:
            # Ловим любые другие неожиданные ошибки
            self._exit_error(f"Unexpected error during decryption: {str(e)}")

    # --- РЕЖИМ 3: HashiCorp Vault ---
    def _load_from_vault(self):
        vault_url = self.args.vault_url.rstrip('/')
        vault_path = self.args.vault_path
        vault_user = self.args.vault_user

        if not vault_user:
            print(f"Connecting to Vault: {vault_url}")
            vault_user = input("Vault Username: ").strip()

        vault_pass = self.args.vault_pass
        if not vault_pass:
            vault_pass = getpass.getpass("Vault Password: ")

        try:
            # 1. Авторизация (Userpass auth method)
            login_url = f"{vault_url}/v1/auth/userpass/login/{vault_user}"
            resp = requests.post(login_url, json={"password": vault_pass}, timeout=5)

            if resp.status_code != 200:
                self._exit_error(f"Vault login failed: {resp.text}")
                
            client_token = resp.json()['auth']['client_token']
            
            # 2. Чтение секрета
            # Поддержка KV Version 2 (путь должен содержать /data/ или мы сами его добавим?)
            # Для простоты считаем, что пользователь дает полный путь к API, 
            # но часто в KV v2 путь 'secret/myconf' превращается в 'secret/data/myconf'
            
            read_url = f"{vault_url}/v1/{vault_path}"
            headers = {"X-Vault-Token": client_token}
            
            resp = requests.get(read_url, headers=headers, timeout=5)
            
            if resp.status_code != 200:
                self._exit_error(f"Cannot read secret '{vault_path}': {resp.status_code} {resp.text}")
            
            json_resp = resp.json()
            
            # Пытаемся достать данные.
            # KV v2: data -> data -> key
            # KV v1: data -> key
            
            payload = {}
            if 'data' in json_resp:
                inner = json_resp['data']
                if 'data' in inner and isinstance(inner['data'], dict):
                    payload = inner['data'] # KV v2 structure
                else:
                    payload = inner # KV v1 structure
            else:
                self._exit_error("Vault response format not recognized (no 'data' field).")
                
            # Ищем ключ 's3_config_json' или парсим весь payload если это уже структура
            if 'endpoints' in payload:
                # Структура лежит прямо в секрете
                self.endpoints = payload['endpoints']
            elif 'content' in payload:
                 # Структура лежит в поле 'content' строкой или объектом
                 content = payload['content']
                 if isinstance(content, str):
                     self.endpoints = json.loads(content).get('endpoints', [])
                 else:
                     self.endpoints = content.get('endpoints', [])
            else:
                # Последний шанс - может весь payload и есть конфиг?
                self.endpoints = payload.get('endpoints', [])
                
            if not self.endpoints:
                 self._exit_error(f"Secret '{vault_path}' read, but no 'endpoints' found inside.")

        except requests.exceptions.RequestException as e:
            self._exit_error(f"Network error connecting to Vault: {e}")
        except Exception as e:
            self._exit_error(f"Vault error: {e}")

    def save_config(self):
        """Сохранение отключено в безопасных режимах"""
        if self.args.vault_url or self.args.encrypted_config:
            # В защищенных режимах мы не сохраняем конфиг обратно на диск в plain text
            return
        
        # Логика для plain text (если нужно)
        pass 

    def get_endpoints(self):
        return self.endpoints

    def get_endpoint(self, name):
        for ep in self.endpoints:
            if ep['name'] == name:
                return ep
        return None



class LRUCache:
    """Простой LRU кеш для хранения результатов запросов к S3"""

    def __init__(self, maxsize=1000):
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
        self.versioning_status_cache = {}
        self.s3_needs_refresh = True

        # Кеш для списков объектов
        self.object_cache = LRUCache(maxsize=1000)
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

    def on_panel_focus(self):
        """Вызывается при фокусе на панели"""
        if self.s3_needs_refresh:
            self.s3_needs_refresh = False
            self.refresh()

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

    def list_objects_lazy(self, bucket_name, prefix='', page_size=1000, use_versioning=False):
        """Ленивая загрузка объектов. Если use_versioning=True, использует list_object_versions"""
        if self.s3_client is None:
            yield [], []
            return

        try:
            if not use_versioning:
                # СТАНДАРТНЫЙ РЕЖИМ (быстрый, без версий)
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
                                # Для совместимости ставим 1 версию
                                obj['version_count'] = 1
                                files.append(obj)
                    yield folders, files

            else:
                # РЕЖИМ С ПОДСЧЕТОМ ВЕРСИЙ (медленнее, агрегация данных)
                paginator = self.s3_client.get_paginator('list_object_versions')
                page_iterator = paginator.paginate(
                    Bucket=bucket_name,
                    Prefix=prefix,
                    Delimiter='/',
                    PaginationConfig={'PageSize': page_size}
                )

                for page in page_iterator:
                    folders = []
                    # Словарь для агрегации версий по ключу файла
                    # Key -> {ObjDict, count}
                    files_map = OrderedDict()

                    if 'CommonPrefixes' in page:
                        for obj in page['CommonPrefixes']:
                            folders.append({'Key': obj['Prefix']})

                    # Обрабатываем версии (Versions)
                    if 'Versions' in page:
                        for v in page['Versions']:
                            key = v['Key']
                            if key == prefix or key.endswith('/'):
                                continue

                            if key not in files_map:
                                # Сохраняем первую встреченную версию как "основную" для отображения
                                # (S3 обычно отдает последнюю версию первой, если она есть)
                                files_map[key] = v.copy()
                                files_map[key]['version_count'] = 0

                            files_map[key]['version_count'] += 1

                            # Если текущая версия помечена как Latest, обновляем метаданные,
                            # чтобы отображать актуальный размер и дату
                            if v.get('IsLatest'):
                                files_map[key].update(v)

                    # Превращаем карту обратно в список файлов
                    files = list(files_map.values())
                    yield folders, files

        except (ClientError, Exception):
            yield [], []

    def invalidate_cache(self, bucket_name=None, prefix=None):
        """Инвалидация кеша после операций изменения"""
        if bucket_name is None:
            self.object_cache.invalidate()
            self.bucket_cache.invalidate()
            self.versioning_status_cache.clear()  # Очистить кеш версионирования
        else:
            pattern = f"{bucket_name}:"
            if prefix:
                pattern += prefix
            self.object_cache.invalidate(pattern)
            # При изменениях в бакете - сбросить его статус версионирования
            if bucket_name in self.versioning_status_cache:
                del self.versioning_status_cache[bucket_name]

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

        versioning_status = self.get_versioning_status_cached(bucket_name)

        # Если версионирование никогда не включалось - не запрашиваем
        if versioning_status is None or versioning_status == 'Disabled':
            return []

        try:
            response = self.s3_client.list_object_versions(Bucket=bucket_name, Prefix=key)
            versions = []
            if 'Versions' in response:
                for v in response['Versions']:
                    if v['Key'] == key:
                        versions.append(v)
            return versions
        except (ClientError, Exception) as e:
            self.connection_error = f"list version error: {str(e)}"
            return []

    def download_object(self, bucket_name, key, local_path, version_id=None, callback=None):
        if self.s3_client is None:
            return False
        try:
            extra_args = {}
            if version_id:
                extra_args['VersionId'] = version_id
            self.s3_client.download_file(bucket_name, key, local_path, ExtraArgs=extra_args, Callback=callback)
            return True
        except (ClientError, Exception) as e:
            self.connection_error = f"Download error: {str(e)}"
            return False

    # ОБНОВЛЕНИЕ S3 только при изменениях
    def mark_s3_for_refresh(self):
        """Отметить что S3 нужно обновить"""
        self.s3_needs_refresh = True

    def upload_file(self, local_path, bucket_name, key):
        if self.s3_client is None:
            return False
        try:
            self.s3_client.upload_file(local_path, bucket_name, key)
            self.invalidate_cache(bucket_name)
            self.mark_s3_for_refresh()
            return True
        except (ClientError, Exception) as e:
            self.connection_error = f"Upload error: {str(e)}"
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
            self.mark_s3_for_refresh()
            return True
        except (ClientError, Exception) as e:
            self.connection_error = f"Copy error: {str(e)}"
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
            self.mark_s3_for_refresh()
            return True
        except (ClientError, Exception) as e:
            self.connection_error = f"Delete error: {str(e)}"
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

            self.mark_s3_for_refresh()
            return deleted_count
        except (ClientError, Exception) as e:
            self.connection_error = f"Delete old version error: {str(e)}"
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
        except (ClientError, Exception) as e:
            self.connection_error = f"Enable Versioning error: {str(e)}"
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
        except (ClientError, Exception) as e:
            self.connection_error = f"Disable Vesrsioning error: {str(e)}"
            return False

    def get_versioning_status_cached(self, bucket_name):
        """Получить статус версионирования с кешированием"""
        if bucket_name not in self.versioning_status_cache:
            # Запрашиваем только один раз
            self.versioning_status_cache[bucket_name] = self.get_versioning_status(bucket_name)
        return self.versioning_status_cache[bucket_name]

    def get_versioning_status(self, bucket_name):
        """Получить статус версионирования бакета"""
        if self.s3_client is None:
            return None
        try:
            response = self.s3_client.get_bucket_versioning(Bucket=bucket_name)
            return response.get('Status', 'Disabled')
        except (ClientError, Exception) as e:
            self.connection_error = f"Get Ver Satus error: {str(e)}"
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
        # self.__super.__init__(widget)
        super().__init__(widget)
        self.scrollbar_width = 1

    def render(self, size, focus=False):
        maxcol, maxrow = size

        # Вычисляем размер для основного виджета
        content_width = maxcol - self.scrollbar_width
        if content_width < 1:
            content_width = 1

        # Рендерим основной виджет с правильным размером
        canvas = self._original_widget.render((content_width, maxrow), focus)

        # Получаем информацию о позиции скролла
        if hasattr(self._original_widget, 'body'):
            # Для ListBox
            try:
                middle, top, bottom = self._original_widget.calculate_visible(
                    (content_width, maxrow), focus
                )
            except:
                # Если calculate_visible не работает, возвращаем canvas без scrollbar
                return canvas

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

            # Комбинируем canvas - ВАЖНО: правильный размер
            # Используем CanvasJoin но убеждаемся что общая ширина = maxcol
            combined = urwid.CanvasJoin([
                (canvas, None, False, content_width),
                (scrollbar_canvas, None, False, self.scrollbar_width)
            ])

            return combined

        return canvas

    def _create_scrollbar(self, height, thumb_top, thumb_height):
        """Создать canvas для scrollbar"""
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

        # Нижний трек
        track_bottom_height = height - thumb_top - thumb_height
        if track_bottom_height > 0:
            track_bottom = urwid.SolidCanvas('│', 1, track_bottom_height)
            track_bottom = urwid.CompositeCanvas(track_bottom)
            track_bottom.fill_attr('scrollbar_track')
            parts.append((track_bottom, None, False))

        if not parts:
            # Если нет частей, создаем пустой canvas
            return urwid.SolidCanvas(' ', 1, height)

        return urwid.CanvasCombine(parts)

    def selectable(self):
        return self._original_widget.selectable()

    def keypress(self, size, key):
        maxcol, maxrow = size
        content_width = maxcol - self.scrollbar_width
        if content_width < 1:
            content_width = 1
        return self._original_widget.keypress((content_width, maxrow), key)

    def mouse_event(self, size, event, button, col, row, focus):
        maxcol, maxrow = size
        content_width = maxcol - self.scrollbar_width
        if content_width < 1:
            content_width = 1

        if col < content_width:
            return self._original_widget.mouse_event(
                (content_width, maxrow), event, button, col, row, focus
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
    """Диалог выбора версии файла для просмотра или действий"""

    def __init__(self, file_data, versions, callback):
        self.callback = callback
        self.versions = versions
        self.file_data = file_data

        # Группа радиокнопок
        self.radio_group = []
        version_items = []

        for idx, v in enumerate(versions):
            is_latest = v.get('IsLatest', False)
            latest_mark = "[LATEST] " if is_latest else "         "

            size = format_size(v.get('Size', 0))
            mtime = v.get('LastModified').strftime('%Y-%m-%d %H:%M:%S') if v.get('LastModified') else 'N/A'
            version_id = v.get('VersionId', '')[:12]

            # label = f"{latest_mark}{version_id}  {size:>10}  {mtime}"
            # Используем моноширинный шрифт для таблицы
            label = f"{latest_mark} {version_id:<12} {size:>10} {mtime}"

            # Первая версия выбрана по умолчанию
            rb = urwid.RadioButton(self.radio_group, label, state=(idx == 0))
            rb.version_data = v  # Сохраняем данные версии прямо в объект кнопки

            # Оборачиваем в AttrMap для подсветки
            version_items.append(urwid.AttrMap(rb, None, focus_map='selected'))

        # Список версий в ListBox
        self.listbox = urwid.ListBox(urwid.SimpleFocusListWalker(version_items))

        # Кнопки действий
        view_btn = urwid.Button('[ View ]')
        del_btn = urwid.Button('[ Delete ]')
        copy_btn = urwid.Button('[ Copy ]')
        move_btn = urwid.Button('[ Move ]')
        cancel_btn = urwid.Button('[ Cancel ]')

        # Обработчик нажатия на кнопки действий
        def on_action(action):
            # Ищем выбранную радиокнопку
            for rb in self.radio_group:
                if rb.state:
                    # Нашли — вызываем и сразу выходим из функции
                    return self.callback(action, rb.version_data)

            # Если цикл закончился и ничего не нашли — отмена
            self.callback('cancel', None)

        # Привязываем сигналы
        urwid.connect_signal(view_btn, 'click', lambda b: on_action('view'))
        urwid.connect_signal(del_btn, 'click', lambda b: on_action('delete'))
        urwid.connect_signal(copy_btn, 'click', lambda b: on_action('copy'))
        urwid.connect_signal(move_btn, 'click', lambda b: on_action('move'))
        urwid.connect_signal(cancel_btn, 'click', lambda b: self.callback('cancel', None))

        # Компоновка кнопок
        buttons_col = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(view_btn, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(copy_btn, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(move_btn, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(del_btn, 'button', focus_map='button_focus')),
            ('fixed', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(cancel_btn, 'button', focus_map='button_focus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)

        pile = urwid.Pile([
            ('pack', urwid.Divider()),
            ('weight', 1, self.listbox),
            ('pack', urwid.Divider()),
            ('pack', buttons_col),
            ('pack', urwid.Divider()),
        ])

        fill = urwid.Filler(pile, valign='top', height=('relative', 100))

        title = f"Select version for '{file_data['name']}'"
        linebox = urwid.LineBox(fill, title=title)

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def keypress(self, size, key):
        if key == 'esc':
            self.callback('cancel', None)
            return None
        # Enter по умолчанию делает View для выбранной версии
        for rb in self.radio_group:
            if rb.state:
                if key == 'enter':
                    btn = get_focus_button(self._w)
                    if btn is not None:
                        if isinstance(btn, urwid.Button) and btn.get_label() == '[ Cancel ]':
                            # Enter на Cancel -> отмена
                            self.callback('cancel', None)
                            return None
                        if isinstance(btn, urwid.Button) and btn.get_label() == '[ Delete ]':
                            self.callback('delete', rb.version_data)
                            return None
                        if isinstance(btn, urwid.Button) and btn.get_label() == '[ Move ]':
                            self.callback('move', rb.version_data)
                            return None
                        if isinstance(btn, urwid.Button) and btn.get_label() == '[ Copy ]':
                            self.callback('copy', rb.version_data)
                            return None
                    self.callback('view', rb.version_data)
                    return None
                if key == 'f3':
                    self.callback('view', rb.version_data)
                    return None
                if key == 'f5':
                    self.callback('copy', rb.version_data)
                    return None
                if key == 'f6':
                    self.callback('move', rb.version_data)
                    return None
                if key == 'f8':
                    self.callback('delete', rb.version_data)
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

        source_text = urwid.Text(f'Source: {format_size(src_size)} | {src_time_str}')
        dest_text = urwid.Text(f'Target: {format_size(dst_size)} | {dst_time_str}')

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

    def __init__(self, current_mode, current_reverse, callback):
        self.callback = callback
        self.current_mode = current_mode
        self.current_reverse = current_reverse

        # Убираем title_text из контента, он будет в рамке
        # title_text = urwid.Text('Sort by:', align='center')

        self.radio_group = []
        modes = [
            ('none', 'Unsorted'),
            ('name', 'Name'),
            ('ext', 'Extension'),
            ('size', 'Size'),
            ('time', 'Time')
        ]

        radio_buttons = []
        for mode, label in modes:
            is_selected = (mode == current_mode)
            rb = urwid.RadioButton(self.radio_group, label, state=is_selected)
            rb.mode = mode
            radio_buttons.append(urwid.AttrMap(rb, None, focus_map='selected'))

        self.reverse_checkbox = urwid.CheckBox("Reverse order", state=current_reverse)

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
            # ('pack', title_text), # Удалено
            # ('pack', urwid.Divider()), # Удалено
        ]

        content.extend([('pack', rb) for rb in radio_buttons])

        content.extend([
            ('pack', urwid.Divider()),
            ('pack', urwid.AttrMap(self.reverse_checkbox, None, focus_map='selected')),
            ('pack', urwid.Divider()),
            ('pack', buttons),
            ('pack', urwid.Divider()),
        ])

        pile = urwid.Pile(content)
        fill = urwid.Filler(pile, valign='top')

        # FIX: Заголовок перенесен в title рамки
        linebox = urwid.LineBox(fill, title="Sort by")

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def on_ok(self, button):
        reverse = self.reverse_checkbox.get_state()
        for rb in self.radio_group:
            if rb.state:
                self.callback(True, rb.mode, reverse)
                return
        self.callback(False, None, False)

    def on_cancel(self, button):
        self.callback(False, None, False)

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
            if btn is not None:
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

        # Настройки сортировки
        self.sort_mode = 'name' if panel_type == 'fs' else 'none'
        self.sort_reverse = False

        self.walker = urwid.SimpleFocusListWalker([])

        # Поддержка ленивой загрузки
        self.loading_in_progress = False
        self.loading_thread = None
        self.lazy_generator = None
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

        self.refresh()

    def show_item_info(self):
        """Показать информацию о текущем элементе (F4)"""
        item = self.get_focused_item()
        if not item:
            return

        info = OrderedDict()
        title = "Info"

        try:
            if self.mode == 'fs':
                path = item.get('path')  # Если есть полный путь
                if not path:
                    # Пытаемся восстановить путь
                    name = item['name']
                    if name == '..': return
                    path = os.path.join(self.fs_browser.current_path, name)

                title = f"File Info: {item['name']}"
                info = self._get_fs_info(path)

            elif self.mode == 's3':
                itype = item.get('type')

                if itype == 'bucket':
                    title = f"Bucket Info: {item['name']}"
                    info = self._get_s3_bucket_info(item['name'])

                elif itype in ['s3_file', 's3_dir']:
                    # Для файлов и папок
                    key = item['key']
                    name = item['name']
                    title = f"Object Info: {name}"
                    info = self._get_s3_object_info(self.current_bucket, key, itype)

        except Exception as e:
            self.app.show_result(f"Error getting info: {e}")
            return

        if info:
            dialog = FileInfoDialog(title, info, self.app.close_dialog)
            self.app.show_dialog(dialog, width=('relative', 60), height=('relative', 70))

    def _get_fs_info(self, path):
        """Сбор информации о локальном файле"""
        import stat, pwd, grp
        info = OrderedDict()

        try:
            st = os.stat(path)

            info['Name'] = os.path.basename(path)
            info['Path'] = path
            info['Size'] = format_size(st.st_size) + f" ({st.st_size} bytes)"

            # Тип файла
            if stat.S_ISDIR(st.st_mode):
                type_str = "Directory"
            elif stat.S_ISLNK(st.st_mode):
                type_str = "Symlink"
            elif stat.S_ISREG(st.st_mode):
                type_str = "Regular File"
            else:
                type_str = "Other"
            info['Type'] = type_str

            # Права доступа
            info['Mode'] = stat.filemode(st.st_mode)
            info['Octal'] = oct(st.st_mode)[-3:]

            # Владелец/Группа
            try:
                owner = pwd.getpwuid(st.st_uid).pw_name
            except:
                owner = str(st.st_uid)

            try:
                group = grp.getgrgid(st.st_gid).gr_name
            except:
                group = str(st.st_gid)

            info['Owner'] = f"{owner} ({st.st_uid})"
            info['Group'] = f"{group} ({st.st_gid})"

            # Временные метки
            info['Access'] = datetime.fromtimestamp(st.st_atime).strftime('%Y-%m-%d %H:%M:%S')
            info['Modify'] = datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            info['Change'] = datetime.fromtimestamp(st.st_ctime).strftime('%Y-%m-%d %H:%M:%S')

            # Техническая инфа
            info['Device'] = st.st_dev
            info['Inode'] = st.st_ino
            info['Links'] = st.st_nlink

        except Exception as e:
            info['Error'] = str(e)

        return info

    def _get_s3_bucket_info(self, bucket_name):
        """Полная информация о бакете"""
        info = OrderedDict()
        info['Name'] = bucket_name

        client = self.s3_manager.s3_client

        try:
            # 1. Region
            try:
                loc = client.get_bucket_location(Bucket=bucket_name)
                region = loc.get('LocationConstraint')
                info['Region'] = region if region else 'us-east-1'
            except:
                info['Region'] = 'Unknown'

            # 2. Versioning
            try:
                ver = client.get_bucket_versioning(Bucket=bucket_name)
                info['Versioning'] = ver.get('Status', 'Disabled')
                if 'MFADelete' in ver:
                    info['MFA Delete'] = ver['MFADelete']
            except:
                pass

            # 3. Encryption (Default)
            try:
                enc = client.get_bucket_encryption(Bucket=bucket_name)
                rules = enc.get('ServerSideEncryptionConfiguration', {}).get('Rules', [])
                if rules:
                    algo = rules[0].get('ApplyServerSideEncryptionByDefault', {}).get('SSEAlgorithm', 'None')
                    info['Default Enc'] = algo
            except:
                info['Default Enc'] = 'None'

            # 4. Lifecycle Configuration
            try:
                lc = client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
                rules = lc.get('Rules', [])
                info['Lifecycle'] = f"{len(rules)} rule(s) configured"
            except ClientError as e:
                # Часто возвращает ошибку, если правил нет
                if "NoSuchLifecycleConfiguration" in str(e):
                    info['Lifecycle'] = "None"
                else:
                    info['Lifecycle'] = "Error/None"

            # 5. CORS
            try:
                cors = client.get_bucket_cors(Bucket=bucket_name)
                info['CORS'] = "Configured"
            except:
                info['CORS'] = "None"

            # 6. ACL / Owner
            try:
                acl = client.get_bucket_acl(Bucket=bucket_name)
                owner = acl.get('Owner', {})
                info['--- Access ---'] = ''
                info['Owner'] = owner.get('DisplayName', owner.get('ID', 'N/A'))
            except:
                pass

            # 7. Usage / Quotas (Специфично для Ceph, часто недоступно через стандартный API)
            # Для Ceph можно попробовать получить через GetBucketAccelerateConfiguration или другие хаки, 
            # но надежнее просто проверить доступность.

            # Payer
            try:
                pay = client.get_bucket_request_payment(Bucket=bucket_name)
                info['Payer'] = pay.get('Payer', 'BucketOwner')
            except:
                pass

        except Exception as e:
            info['Error'] = str(e)

        return info

    def _get_s3_object_info(self, bucket, key, itype):
        """Полная информация об объекте S3"""
        info = OrderedDict()
        info['Name'] = key.split('/')[-1]
        info['Bucket'] = bucket
        info['Key'] = key
        info['S3 URI'] = f"s3://{bucket}/{key}"

        if itype == 's3_dir':
            info['Type'] = "Folder (Prefix)"
            return info

        try:
            client = self.s3_manager.s3_client
            obj = client.head_object(Bucket=bucket, Key=key)

            # --- Основные свойства ---
            info['Size'] = format_size(obj.get('ContentLength', 0)) + f" ({obj.get('ContentLength', 0)})"
            info['Last Mod'] = obj.get('LastModified').strftime('%Y-%m-%d %H:%M:%S')
            info['MIME Type'] = obj.get('ContentType', 'N/A')
            info['Storage'] = obj.get('StorageClass', 'STANDARD')
            info['ETag'] = obj.get('ETag', '').replace('"', '')

            # --- Web Headers ---
            web_headers = {}
            if 'CacheControl' in obj:
                web_headers['Cache-Control'] = obj['CacheControl']
            if 'ContentEncoding' in obj:
                web_headers['Content-Encoding'] = obj['ContentEncoding']
            if 'ContentDisposition' in obj:
                web_headers['Disposition'] = obj['ContentDisposition']
            if 'WebsiteRedirectLocation' in obj:
                web_headers['Redirect'] = obj['WebsiteRedirectLocation']

            if web_headers:
                info['--- Web Headers ---'] = ''
                for k, v in web_headers.items():
                    info[k] = v

            # --- Data Management (Lifecycle, Replication, Restore) ---
            lifecycle_info = {}
            # if 'Expiration' in obj: lifecycle_info['Expiration'] = obj['Expiration']
            if 'Expiration' in obj:
                lifecycle_info['Expiration'] = obj['Expiration']
            else:
                # FIX: Если заголовка нет, проверим правила вручную (для информирования)
                try:
                    lc = client.get_bucket_lifecycle_configuration(Bucket=bucket)
                    matched_rules = []
                    for rule in lc.get('Rules', []):
                        if rule.get('Status') == 'Enabled':
                            prefix = rule.get('Filter', {}).get('Prefix', rule.get('Prefix', ''))
                            # Проверяем совпадение префикса
                            if key.startswith(prefix):
                                rule_id = rule.get('ID', 'Unknown')
                                # Можно добавить детали (Days=30 и т.д.), но ID достаточно для подсказки
                                matched_rules.append(f"'{rule_id}'")

                    if matched_rules:
                        lifecycle_info['Potential Rule'] = f"{', '.join(matched_rules)} (Pending application)"
                except:
                    pass  # Правил нет или нет прав

            if 'ReplicationStatus' in obj:
                lifecycle_info['Replication'] = obj['ReplicationStatus']
            if 'Restore' in obj:
                lifecycle_info['Restore'] = obj['Restore']

            if lifecycle_info:
                info['--- Lifecycle ---'] = ''
                for k, v in lifecycle_info.items():
                    info[k] = v

            # --- Object Lock & Security ---
            security_info = {}
            if 'ObjectLockMode' in obj:
                security_info['Lock Mode'] = obj['ObjectLockMode']
            if 'ObjectLockRetainUntilDate' in obj:
                security_info['Retain Until'] = str(obj['ObjectLockRetainUntilDate'])
            if 'ObjectLockLegalHoldStatus' in obj:
                security_info['Legal Hold'] = obj['ObjectLockLegalHoldStatus']
            if 'ServerSideEncryption' in obj:
                security_info['Encryption'] = obj['ServerSideEncryption']
            if 'SSEKMSKeyId' in obj:
                security_info['KMS Key ID'] = obj['SSEKMSKeyId']

            if security_info:
                info['--- Security ---'] = ''
                for k, v in security_info.items():
                    info[k] = v

            # --- Metadata ---
            if 'Metadata' in obj and obj['Metadata']:
                info['--- Metadata ---'] = ''
                for k, v in obj['Metadata'].items():
                    info[f"Meta-{k}"] = v

            # --- Tags ---
            try:
                tags_resp = client.get_object_tagging(Bucket=bucket, Key=key)
                tags = tags_resp.get('TagSet', [])
                if tags:
                    info['--- Tags ---'] = ''
                    for tag in tags:
                        info[f"Tag: {tag['Key']}"] = tag['Value']
            except ClientError:
                pass

                # --- ACL ---
            try:
                acl = client.get_object_acl(Bucket=bucket, Key=key)
                owner = acl.get('Owner', {})
                info['--- Permissions ---'] = ''
                info['Owner'] = f"{owner.get('DisplayName', 'N/A')} ({owner.get('ID', 'N/A')})"

                # Краткая сводка прав
                grants = []
                for g in acl.get('Grants', []):
                    perm = g.get('Permission')
                    grantee = g.get('Grantee', {})
                    if grantee.get('Type') == 'Group':
                        who = grantee.get('URI', '').split('/')[-1]
                    else:
                        who = grantee.get('DisplayName', 'ID=' + grantee.get('ID', '')[:4])
                    grants.append(f"{who}:{perm}")

                if grants:
                    info['ACL'] = ", ".join(grants[:3])  # Показываем первые 3 компактно
            except:
                pass

            # --- Versions ---
            try:
                versions = client.list_object_versions(Bucket=bucket, Prefix=key)
                if 'Versions' in versions:
                    obj_versions = [v for v in versions['Versions'] if v['Key'] == key]
                    if len(obj_versions) > 0:
                        info['--- Versions ---'] = ''
                        info['Count'] = len(obj_versions)
                        for i, v in enumerate(obj_versions[:5]):
                            vid = v.get('VersionId', 'null')[:8]
                            is_cur = " *" if v.get('IsLatest') else ""
                            date = v.get('LastModified').strftime('%m-%d %H:%M')
                            size = format_size(v.get('Size', 0))
                            info[f"v{i + 1}"] = f"{vid:<8} {date} {size}{is_cur}"
            except:
                pass

            # --- Presigned URL ---
            try:
                url = client.generate_presigned_url('get_object', Params={'Bucket': bucket, 'Key': key}, ExpiresIn=3600)
                info['URL_FULL'] = url  # Ключ для FileInfoDialog
            except:
                pass

        except Exception as e:
            info['Error'] = str(e)

        return info

    def copy_version(self, file_data, version_data, move=False):
        """Копировать или переместить конкретную версию файла"""

        target_panel = self.app.get_inactive_panel()

        # Подготовка фейкового элемента для копирования
        item_to_copy = file_data.copy()
        item_to_copy['VersionId'] = version_data['VersionId']
        item_to_copy['Size'] = version_data['Size']

        items = [item_to_copy]

        operation = 'move' if move else 'copy'
        title = "Move Version" if move else "Copy Version"

        if target_panel.mode == 'fs':
            base_path = target_panel.fs_browser.current_path
            # Добавляем имя файла к пути назначения
            dest_path = os.path.join(base_path, file_data['name'])
            dest_desc = f"FS: {dest_path}"  # Это просто описание, можно оставить

            # А вот в диалог передаем именно путь для редактирования
            edit_path = dest_path
        elif target_panel.mode == 's3':
            if not target_panel.current_bucket:
                self.app.show_result("Target panel is not in a bucket")
                return

            prefix = target_panel.current_prefix if target_panel.current_prefix else ''
            # Формируем путь S3: bucket/prefix/filename
            # Но обычно S3Commander показывает просто prefix/filename или bucket/prefix/filename
            # в зависимости от того, как работает _do_copy

            # Если _do_copy ожидает локальный путь или ключ S3?
            # В _show_copy_dialog: dest_path = item['name'] (если внутри бакета)

            # Если мы внутри бакета целевой панели:
            if target_panel.current_bucket:
                # Имя файла + префикс
                edit_path = prefix + file_data['name']
                dest_desc = f"S3: {target_panel.current_bucket}/{edit_path}"
            else:
                # Копирование в список бакетов? (вряд ли для файла)
                edit_path = file_data['name']
                dest_desc = f"S3: {edit_path}"

        else:
            self.app.show_result("Invalid target")
            return

        def on_confirm(confirmed, target_path_from_dialog):  # target_path приходит из диалога!
            self.app.close_dialog()
            if confirmed:
                # Нам нужно подготовить структуру 'analyzed', которую ждет _do_copy_with_progress
                # Так как у нас всего один файл (версия), мы можем собрать его вручную,
                # чтобы не вызывать analyze_items (хотя можно и его).

                # Создаем структуру, идентичную той, что делает analyze_items
                analyzed_item = {
                    'type': file_data['type'],  # 's3_file'
                    'item': item_to_copy,  # Наш объект с VersionId
                    'files': [item_to_copy]  # Список файлов (он сам)
                }
                analyzed = [analyzed_item]

                total_bytes = item_to_copy['Size']

                # Сброс флагов (как в _show_copy_dialog)
                self.app.overwrite_all = False
                self.app.version_all = False
                self.app.skip_all = False

                # Вызываем существующий метод запуска копирования
                # target_path_from_dialog - это то, что юзер ввел/подтвердил в диалоге (папка назначения)
                self.app._do_copy_with_progress(
                    analyzed,
                    self,  # source_panel
                    target_panel,
                    target_path_from_dialog,
                    item_to_copy['name'],  # focus_name
                    is_move=move,
                    total_bytes=total_bytes
                )

        from_desc = f"{file_data['name']} (ver: {version_data['VersionId'][:8]})"
        # Передаем edit_path вместо dest_desc в поле ввода
        dialog = CopyMoveDialog(title, from_desc, edit_path, on_confirm)
        # dialog = CopyMoveDialog(title, from_desc, dest_desc, on_confirm)
        self.app.show_dialog(dialog)

    def show_sort_dialog(self):
        """Показать диалог выбора сортировки"""

        def callback(confirmed, mode, reverse):
            self.app.close_dialog()
            if confirmed and mode:
                self.sort_mode = mode
                self.sort_reverse = reverse  # Сохраняем выбор

                # Для S3: пересортировываем только если данные уже загружены
                if self.mode == 's3' and not self.loading_in_progress:
                    self._resort_current_view()
                else:
                    self.refresh()

                rev_mark = " (Rev)" if reverse else ""
                self.app.show_result(f'Sort by: {mode}{rev_mark}')

                if self.mode == 's3':
                    self.update_header(f'[S3 Mode - {self.current_endpoint}] Sort: {self.sort_mode}{rev_mark}')

        # Передаем текущий режим и флаг reverse
        dialog = SortDialog(self.sort_mode, self.sort_reverse, callback)
        self.app.show_dialog(dialog)

    def _resort_current_view(self):
        """Пересортировать текущий вид без перезагрузки из сети"""
        folders = []
        files = []

        # 1. Извлекаем данные из текущих виджетов walker
        for widget in self.walker:
            w = widget.original_widget if isinstance(widget, urwid.AttrMap) else widget
            if isinstance(w, SelectableText):
                data = w.data
                dtype = data.get('type')

                # FIX: Используем новые типы 's3_dir' и 's3_file'
                if dtype == 's3_dir':
                    folders.append({'Key': data['key']})
                elif dtype == 's3_file':
                    # Восстанавливаем структуру, которую ожидает _create_display_items
                    files.append({
                        'Key': data['key'],
                        'Size': data.get('size', 0),
                        'LastModified': data.get('mtime'),
                        'version_count': data.get('version_count', 1)  # Сохраняем кол-во версий
                    })

        # 2. Очищаем walker, оставляя только навигацию
        keep_count = 0
        keep_types = ['to_root_menu', 'parent', 's3_parent', 's3_back']

        for widget in self.walker:
            w = widget.original_widget if isinstance(widget, urwid.AttrMap) else widget
            if isinstance(w, SelectableText):
                if w.data.get('type') in keep_types:
                    keep_count += 1
                else:
                    break

        del self.walker[keep_count:]

        # 3. Пересоздаем виджеты с учетом новой сортировки
        # self.sort_mode уже был обновлен диалогом перед вызовом этого метода
        items = self._create_display_items(folders, files, do_sort=True)

        for item in items:
            self.walker.append(item)

        # 4. Обновляем экран
        if self.app and hasattr(self.app, 'loop') and self.app.loop:
            self.app.loop.draw_screen()

    # ОБНОВЛЕНИЕ S3 только при изменениях
    def mark_s3_for_refresh(self):
        """Отметить что S3 нужно обновить"""
        self.s3_needs_refresh = True

    def sort_items(self, items):
        """Сортировать элементы с учетом флага Reverse"""

        def get_type_priority(item):
            t = item.get('type', '')
            if t in ['folder', 's3_dir', 'fs_dir', 'parent', 's3_parent']:
                return 0
            return 1

        # Получаем списки
        dirs = [x for x in items if get_type_priority(x) == 0]
        files = [x for x in items if get_type_priority(x) == 1]

        # Функция-ключ для сортировки файлов
        key_func = None
        reverse_files = self.sort_reverse

        if self.sort_mode == 'name':
            key_func = lambda x: x.get('name', x.get('key', '')).lower()
            # Для имени reverse работает "как ожидается" (Z-A)

        elif self.sort_mode == 'ext':
            def get_ext(item):
                name = item.get('name', item.get('key', ''))
                if '.' in name:
                    return name.rsplit('.', 1)[1].lower()
                return ''

            key_func = get_ext

        elif self.sort_mode == 'size':
            key_func = lambda x: x.get('size', x.get('Size', 0))
            # По умолчанию (reverse=False) size сортирует по убыванию (большие сверху)? 
            # Обычно в файл-менеджерах size asc = маленькие сверху.
            # Давайте сделаем стандартно: False = asc (0..9), True = desc (9..0)
            # НО выше в коде было files.sort(..., reverse=True) для size.
            # Значит, если sort_reverse включен, мы должны делать reverse=False.
            reverse_files = not self.sort_reverse  # Инвертируем логику для size/time

        elif self.sort_mode == 'time':
            key_func = lambda x: x.get('mtime', x.get('LastModified', datetime.min)) or datetime.min
            # Аналогично size: по умолчанию новые сверху (desc), reverse -> старые сверху (asc)
            reverse_files = not self.sort_reverse

        # Сортируем папки (всегда по имени)
        # Папки тоже можно реверсировать, если пользователь выбрал Reverse
        dirs.sort(key=lambda x: x.get('name', '').lower(), reverse=self.sort_reverse)

        if key_func:
            files.sort(key=key_func, reverse=reverse_files)

        # Для 'none' возвращаем как есть
        if self.sort_mode == 'none':
            return items

        return dirs + files

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
                    version_id=version_id):
                self._view_file(tmppath, filename, close_callback=close_callback)
                try:
                    os.unlink(tmppath)
                except:
                    pass
            else:
                self.app.show_result(f"Failed to download {filename}")

    def show_version_select_dialog(self, file_data):
        """Показать диалог выбора версии"""
        # Загружаем версии
        versions = self.s3_manager.list_object_versions(self.current_bucket, file_data['key'])

        if not versions:
            self.app.show_result("No versions found")
            return

        def callback(action, version_data):
            if action == 'cancel':
                self.app.close_dialog()
                return

            if action == 'view' and version_data:
                self.app.close_dialog()
                self.view_s3_file_version(
                    file_data,
                    version_data,
                    close_callback=lambda: self.show_version_select_dialog(file_data)
                )

            elif action == 'delete' and version_data:
                self.app.close_dialog()
                self.confirm_delete_version(file_data, version_data)

            elif action == 'copy' and version_data:
                self.app.close_dialog()
                self.copy_version(file_data, version_data, move=False)

            elif action == 'move' and version_data:
                self.app.close_dialog()
                self.copy_version(file_data, version_data, move=True)

        dialog = VersionSelectDialog(file_data, versions, callback)
        self.app.show_dialog(dialog, height=('relative', 70))

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
        mtime = version_data.get('LastModified', '').strftime('%Y-%m-%d %H:%M:%S') if version_data.get(
            'LastModified') else 'N/A'
        message = f"Delete version of '{file_data['name']}'?{latest_warn}"
        items_info = [
            f"Version ID: {version_id}",
            f"Size: {size}",
            f"Modified: {mtime}"
        ]
        dialog = ConfirmDialog("Confirm Delete Version", message, items_info, confirm_callback)
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
        # loading_text = SelectableText(' [Loading...]', {'type': 'loading', 'can_select': False}, self)
        # self.walker.append(urwid.AttrMap(loading_text, 'info'))

        # ВАЖНО: Принудительная перерисовка
        if hasattr(self.app, 'loop') and self.app.loop:
            self.app.loop.draw_screen()

        # Запускаем фоновую загрузку
        if self.loading_thread and self.loading_thread.is_alive():
            return

        self.loading_in_progress = True
        self.loading_thread = threading.Thread(
            target=self.load_s3_objects_background,
            args=(self.current_bucket, prefix),
            daemon=True
        )
        self.loading_thread.start()

    def load_s3_objects_background(self, bucket_name, prefix):
        """Фоновая загрузка объектов с обновлением статусной строки"""
        try:
            # Сразу показываем статус
            self.app.loop.set_alarm_in(0, lambda l, u: self.app.show_result("Loading..."))
            self.app.wakeup()

            use_versioning = False
            if self.s3_manager:
                status = self.s3_manager.get_versioning_status_cached(bucket_name)
                use_versioning = status in ['Enabled', 'Suspended']

            all_folders = []
            all_files = []

            for folders, files in self.s3_manager.list_objects_lazy(bucket_name, prefix, page_size=1000,
                                                                    use_versioning=use_versioning):
                all_folders.extend(folders)
                all_files.extend(files)

                current_folders = list(all_folders)
                current_files = list(all_files)

                # Обновляем список файлов
                self.app.loop.set_alarm_in(0, lambda l, u: self._update_display_incremental(current_folders,
                                                                                            current_files))

                # Обновляем статусную строку: Желтый на синем (стиль 'result' в DualPaneApp)
                count_msg = f"Loading... {len(all_folders) + len(all_files)} items"
                self.app.loop.set_alarm_in(0, lambda l, u, msg=count_msg: self.app.show_result(msg))

                self.app.wakeup()

            # Финальное обновление
            self.app.loop.set_alarm_in(0, lambda l, u: self._finalize_loading(all_folders, all_files))
            self.app.wakeup()

        except Exception as e:
            error_msg = str(e)
            self.app.loop.set_alarm_in(0, lambda l, u, err=error_msg:
            self.app.show_result(f"Error loading objects: {err}", is_error=True))
            self.app.wakeup()
        finally:
            self.loading_in_progress = False

    def _update_display_incremental(self, folders, files):
        """Инкрементальное обновление (без виджета loading в списке)"""
        # Создаем элементы (без сортировки для скорости во время загрузки)
        # Сортировка будет применена только в конце, в finalize
        items = self._create_display_items(folders, files, do_sort=False)

        # Сохраняем навигацию ([..])
        keep_count = 0
        keep_types = ['to_root_menu', 'parent', 's3_parent', 's3_back']

        for widget in self.walker:
            w = widget.original_widget if isinstance(widget, urwid.AttrMap) else widget
            if isinstance(w, SelectableText):
                if w.data.get('type') in keep_types:
                    keep_count += 1
                else:
                    break

        # Заменяем старые файлы новыми
        del self.walker[keep_count:]
        for item_widget in items:
            self.walker.append(item_widget)

        # Восстанавливаем фокус
        if len(self.walker) > 0:
            try:
                # Фокус на первый элемент после [..]
                focus_pos = min(keep_count, len(self.walker) - 1)
                # Если курсор уже был ниже, пытаемся сохранить позицию (опционально, но сложно при инкременте)
                self.listbox.set_focus(focus_pos)
            except:
                pass

        if self.app and hasattr(self.app, 'loop') and self.app.loop:
            self.app.loop.draw_screen()

    def _finalize_loading(self, folders, files):
        """Завершение загрузки"""
        self.loading_in_progress = False

        # Финальная перестройка списка. 
        # Если sort_mode задан (например 'size'), здесь произойдет сортировка.
        if self.sort_mode != 'none':
            items = self._create_display_items(folders, files, do_sort=True)

            keep_count = 0
            keep_types = ['to_root_menu', 'parent', 's3_parent', 's3_back']
            for widget in self.walker:
                w = widget.original_widget if isinstance(widget, urwid.AttrMap) else widget
                if isinstance(w, SelectableText):
                    if w.data.get('type') in keep_types:
                        keep_count += 1
                    else:
                        break

            del self.walker[keep_count:]
            for item_widget in items:
                self.walker.append(item_widget)

        # Обновляем статусную строку финальным сообщением
        sort_info = f"(sorted by {self.sort_mode})" if self.sort_mode != 'none' else "(unsorted)"
        msg = f"Loaded: {len(folders)} folders, {len(files)} files {sort_info}"
        self.app.show_result(msg)

        if len(self.walker) > 0:
            try:
                self.listbox.set_focus(0)
            except:
                pass

        if self.app and hasattr(self.app, 'loop') and self.app.loop:
            self.app.loop.draw_screen()

    def _create_display_items(self, folders, files, do_sort=True):
        """Создать виджеты для отображения папок и файлов S3"""
        items = []
        combined = []

        # Проверяем статус версионирования ОДИН РАЗ для бакета
        # (Оставляем для передачи в свойства файла, если понадобится логике, но не для отображения)
        versioning_enabled_bucket = False
        if self.current_bucket and self.s3_manager:
            vs = self.s3_manager.get_versioning_status_cached(self.current_bucket)
            versioning_enabled_bucket = vs in ['Enabled', 'Suspended']

        # Подготовка списка папок
        for folder in folders:
            key = folder['Key']
            folder_name = key.rstrip('/').split('/')[-1]
            combined.append({
                'type': 's3_dir',
                'name': folder_name,
                'key': key,
                'size': 0,
                'mtime': None
            })

        # Подготовка списка файлов
        for file in files:
            key = file['Key']
            file_name = key.split('/')[-1]

            # Получаем количество версий (если оно было подсчитано в list_objects_lazy)
            v_count = file.get('version_count', 1)

            combined.append({
                'type': 's3_file',
                'name': file_name,
                'key': key,
                'size': file.get('Size', 0),
                'mtime': file.get('LastModified'),
                'version_count': v_count,
                'versioning_enabled': versioning_enabled_bucket
            })

        # Сортировка
        if do_sort and self.sort_mode != 'none':
            combined = self.sort_items(combined)

        # Создание виджетов
        for item in combined:
            if item['type'] == 's3_dir':
                label = f"/{item['name']}"
                data = {
                    'type': 's3_dir',
                    'name': item['name'],
                    'key': item['key'],
                    'can_select': False
                }
                attr = None
            else:
                size_str = self.fs_browser.format_size(item['size']) if hasattr(self.fs_browser,
                                                                                'format_size') else format_size(
                    item['size'])
                time_str = item['mtime'].strftime('%Y-%m-%d %H:%M') if item['mtime'] else ''

                # Логика отображения версий: ПОКАЗЫВАТЬ ТОЛЬКО ЕСЛИ > 1
                v_count = item.get('version_count', 1)
                if v_count > 1:
                    version_hint = f' [{v_count}]'
                else:
                    version_hint = ''  # [v] больше не отображается

                # label = f" {item['name']:50} {size_str:>10} {time_str}{version_hint}"
                name = item["name"]
                # Если имя длиннее 40, берем 39 символов и добавляем '>', иначе оставляем как есть
                display_name = name if len(name) <= 50 else name[:49] + ">"
                label = f" {display_name:50} {size_str:>10} {time_str}{version_hint}"

                data = {
                    'type': 's3_file',
                    'name': item['name'],
                    'key': item['key'],
                    'size': item['size'],
                    'mtime': item['mtime'],
                    'can_select': True,
                    'version_count': v_count  # Сохраняем кол-во версий в объекте
                }
                attr = 'file'

            text = SelectableText(f'  {label}', data, self)
            items.append(urwid.AttrMap(text, attr, focus_map='selected'))

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
                self.app.show_result(
                    f'Cannot connect to {self.current_endpoint}: {self.s3_manager.connection_error[:80]}')
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

                # label = f'[BUCKET] {bucket["name"]:40} {date_str}'
                label = f'*{bucket["name"]:40} {date_str} {bucket["versioning_mark"]}'

                data = {'type': 'bucket', 'name': bucket['name'], 'can_select': True}
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        else:
            # 1. Сначала считаем объекты (это быстро, т.к. данные берутся из cache или HEAD запроса)
            total_count, total_size = self.s3_manager.count_objects(self.current_bucket, self.current_prefix)

            # 2. Логика сброса сортировки:
            # Если объектов много (>1000), принудительно отключаем сортировку для скорости
            if total_count is not None and total_count > 1000:
                self.sort_mode = 'none'
            # Иначе - оставляем тот режим, который выбрал пользователь (например, 'size')

            self.update_header(f'[S3 Mode - {self.current_endpoint}] Sort: {self.sort_mode}')

            # Формируем путь в заголовке
            display_prefix = self.current_prefix
            # if self.current_prefix else '/'

            if total_count is not None:
                count_info = f' [{total_count} objects, {format_size(total_size)}]'
            else:
                count_info = ''

            self.path_text.set_text(f'S3: /{self.current_endpoint}/{self.current_bucket}/{display_prefix}{count_info}')

            # 3. Добавляем навигационные кнопки
            data = {'type': 'parent', 'can_select': False}
            if self.current_prefix:
                data = {'type': 's3_parent', 'can_select': False}
                text = SelectableText(' [..] Parent', data, self)
            else:
                data = {'type': 's3_back', 'can_select': False}
                text = SelectableText(' [..] Back to buckets', data, self)

            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

            # 4. ЗАПУСКАЕМ ЛЕНИВУЮ ЗАГРУЗКУ
            self._refresh_s3_objects_lazy()

            return  # Выход - остальное в фоновом потоке

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
            # label = f'[DIR ] {item_data["name"]:40}  <DIR>           {mtime}'
            # label = f'/{item_data["name"]:40}            {mtime}'
            name = item_data["name"]
            # Если имя длиннее 40, берем 39 символов и добавляем '>', иначе оставляем как есть
            display_name = name if len(name) <= 40 else name[:39] + ">"
            label = f'/{display_name:40}            {mtime}'

            data = {
                'type': 'fs_dir',
                'name': item_data['name'],
                'size': item_data['size'],
                'mtime': item_data['mtime'],
                'can_select': True
            }
            text = SelectableText(f'  {label}', data, self)
            # self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
            self.walker.append(urwid.AttrMap(text, 'body', focus_map='selected'))

        for item_data in files:
            mtime = item_data['mtime'].strftime('%Y-%m-%d %H:%M:%S') if item_data['mtime'] else ' ' * 19
            # label = f'[FILE] {item_data["name"]:40} {self.format_size(item_data["size"]):>10}         {mtime}'
            # label = f' {item_data["name"]:40} {self.format_size(item_data["size"]):>10} {mtime}'
            name = item_data["name"]
            # Если имя длиннее 40, берем 39 символов и добавляем '>', иначе оставляем как есть
            display_name = name if len(name) <= 40 else name[:39] + ">"
            label = f' {display_name:40} {self.format_size(item_data["size"]):>10} {mtime}'

            data = {
                'type': 'fs_file',
                'name': item_data['name'],
                'size': item_data['size'],
                'mtime': item_data['mtime'],
                'can_select': True
            }
            text = SelectableText(f'  {label}', data, self)
            # self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
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
            # FIX: Для файловой системы сортировка по умолчанию - Name
            self.sort_mode = 'name'
            self.refresh()

        elif item_type == 'root_endpoint':
            self.mode = 's3'
            self.current_endpoint = data['name']
            endpoint_config = data['config']
            self.s3_manager = S3Manager(endpoint_config)
            self.current_bucket = None
            self.current_prefix = ''
            # FIX: Для S3 отключаем сортировку по умолчанию (грузим как есть)
            self.sort_mode = 'none'
            self.refresh()

        elif item_type == 'endpoint':
            self.current_endpoint = data['name']
            endpoint_config = data['config']
            self.s3_manager = S3Manager(endpoint_config)
            self.current_bucket = None
            self.current_prefix = ''
            self.sort_mode = 'none'  # FIX: То же самое для прямого выбора эндпоинта
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

        elif item_type == 'fs_file':
            self.view_item()

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
            version_lines.append(f"{idx + 1}. {latest_mark}{version_id} {size:>10} {mtime}")

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
                    close_callback()  # Вызываем возврат (например, в список версий)

            # viewer = FileViewerDialog(f'View: {title}', content, self.app.close_dialog)
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
                self.app.wake_up()  # Будим цикл и при ошибке

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
            ('dialogf4', 'white', 'dark blue'),
            ('dialog_title', 'black', 'light cyan'),
            ('edit', 'black', 'light cyan'),
            ('edit_focus', 'white', 'dark cyan'),
            ('button', 'black', 'light gray'),
            ('button_focus', 'white', 'dark cyan'),
            ('error', 'light red', 'dark blue'),
            ('info_name', 'yellow', 'dark blue'),
            ('info_value', 'white', 'dark blue'),

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

    def wakeup(self):
        """Принудительно разбудить MainLoop из другого потока"""
        if self.use_pipe:
            try:
                os.write(self.pipe_w, b'!')
            except (OSError, AttributeError):
                pass
        else:
            # Fallback для Windows или если pipe не настроен
            # Это менее эффективно, но лучше чем ничего
            pass

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
        if platform.system() == 'Windows':
            # Включаем "сердцебиение" для Windows, чтобы интерфейс не зависал
            self.loop.set_alarm_in(0.1, self._windows_heartbeat)
        # Пытаемся использовать пайп (для Linux), но игнорируем ошибки на Windows
        if self.use_pipe:
            try:
                self.loop.watch_file(self.pipe_r, self.loop_wakeup_callback)
            except Exception:
                pass # На Windows watch_file для пайпов не работает, сработает heartbeat

        self.loop.run()

    def _windows_heartbeat(self, loop=None, user_data=None):
        """Периодическое обновление экрана для Windows"""
        self.loop.draw_screen()
        # Перезапускаем таймер каждые 0.1 секунды
        self.loop.set_alarm_in(0.1, self._windows_heartbeat)

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
        elif key == 'f4':
            active_panel = self.get_active_panel()
            if active_panel:
                active_panel.show_item_info()
        elif key == 'f5':
            self.copy_items()
        # elif key == 'f5':
        #    self.show_item_info()
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
                        self.show_result(
                            f'Deleted old versions: {progress.success_count}, Failed: {progress.fail_count}')

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
                # items_info.append(f"[FILE] {item['name']}")
                items_info.append(f" {item['name']}")
                total_bytes += item.get('size', 0)

            elif item_type == 'fs_dir':
                dir_path = os.path.join(source_panel.fs_browser.current_path, item['name'])
                all_files = source_panel.fs_browser.list_all_files(dir_path)
                analyzed.append({'type': 'fs_dir', 'item': item, 'files': all_files, 'dir_path': dir_path})
                # items_info.append(f"[DIR ] {item['name']} ({len(all_files)} files)")
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
                # items_info.append(f"[DIR ] {item['name']} ({len(all_objects)} objects)")
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

            self._do_copy_with_progress(analyzed, source_panel, dest_panel, target_name, focus_name, is_move=is_move,
                                        total_bytes=total_bytes)

        dialog = CopyMoveDialog(operation, source_desc, dest_path, callback)
        self.show_dialog(dialog)

    def _check_overwrite(self, filename, source_info, dest_info, callback, is_s3_dest=False):
        """Показать диалог подтверждения перезаписи"""
        dialog = OverwriteDialog(filename, source_info, dest_info, callback, show_version_options=is_s3_dest)
        self.show_dialog(dialog)

    def _do_copy_with_progress(self, analyzed, source_panel, dest_panel, target_name, focus_name, is_move=False,
                               total_bytes=0):
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
                                'size': existing.get('Size', 0),
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
                                dest_key = target_name.rstrip('/') + '/' + item['name'] + '/' + file_info[
                                    'rel_path'].replace(os.sep, '/')
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
                                        'size': existing.get('Size', 0),
                                        'mtime': existing.get('LastModified')
                                    }

                                    def show_overwrite_dialog():
                                        def on_choice(choice):
                                            user_choice['value'] = choice
                                            choice_event.set()
                                            self.close_dialog()
                                            self.show_dialog(progress)

                                        self._check_overwrite(file_info['rel_path'], source_info, dest_info, on_choice,
                                                              is_s3_dest=True)

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
                                'size': item.get('size', 0),
                                'mtime': item.get('mtime')
                                # 'size': item['size'],
                                # 'mtime': item['mtime']
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

                    if source_panel.s3_manager.download_object(source_panel.current_bucket, item['key'], dest_path,
                                                               version_id=item.get('VersionId')):
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
                                dest_path = os.path.join(dest_panel.fs_browser.current_path, target_name,
                                                         rel_key.replace('/', os.sep))
                            else:
                                dest_path = os.path.join(dest_panel.fs_browser.current_path,
                                                         rel_key.replace('/', os.sep))
                        else:
                            if target_name:
                                dest_path = os.path.join(dest_panel.fs_browser.current_path, target_name, item['name'],
                                                         rel_key.replace('/', os.sep))
                            else:
                                dest_path = os.path.join(dest_panel.fs_browser.current_path, item['name'],
                                                         rel_key.replace('/', os.sep))

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
                                'size': item.get('size', 0),
                                'mtime': item.get('mtime', datetime.now())
                            }
                            dest_info = {
                                'size': existing.get('Size', 0),
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
                            dest_key,
                            version_id=item.get('VersionId')
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
                                    'size': existing.get('Size', 0),
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
                                'size': item.get('size', 0),
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

                                        self._check_overwrite(file_info['rel_path'], source_info, dest_info, on_choice,
                                                              is_s3_dest=False)

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
                                    'size': existing.get('Size', 0),
                                    'mtime': existing.get('LastModified')
                                }

                                def show_overwrite_dialog():
                                    def on_choice(choice):
                                        user_choice['value'] = choice
                                        choice_event.set()
                                        self.close_dialog()
                                        self.show_dialog(progress)

                                    self._check_overwrite(obj['Key'], source_info, dest_info, on_choice,
                                                          is_s3_dest=True)

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
                        version_id = item.get('VersionId')
                        source_panel.s3_manager.delete_object(source_panel.current_bucket, item['key'],
                                                              version_id=version_id)

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


class FileInfoDialog(urwid.WidgetWrap):
    """Диалог детальной информации о файле/бакете"""

    def __init__(self, title, info_dict, close_callback):
        self.close_callback = close_callback

        items = []

        keys_for_calc = [k for k in info_dict.keys() if k != 'URL_FULL' and not k.startswith('---')]
        max_key_len = max([len(k) for k in keys_for_calc]) if keys_for_calc else 0

        for key, value in info_dict.items():
            if key.startswith('---'):
                items.append(urwid.Divider())
                sep_text = urwid.Text(key.replace('-', '').strip(), align='center')
                # Принудительно задаем фон
                items.append(urwid.AttrMap(sep_text, 'info_name'))
                continue

            if key == 'URL_FULL':
                items.append(urwid.Divider())
                items.append(urwid.Text(('info_name', "Presigned URL (1h):")))
                edit = urwid.Edit("", str(value))
                items.append(urwid.AttrMap(edit, 'info_value'))
                continue

            key_str = f"{key}:".ljust(max_key_len + 2)
            val_str = str(value)

            text_widget = urwid.Text([
                ('info_name', key_str),
                ('info_value', val_str)
            ])
            # Оборачиваем каждую строку в 'dialog', чтобы пробелы тоже были синими
            items.append(urwid.AttrMap(text_widget, 'dialogf4'))

        # Оборачиваем сам ListBox, чтобы пустые места были синими
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker(items))
        listbox_map = urwid.AttrMap(listbox, 'dialogf4')

        ok_button = urwid.Button('[ OK ]')
        urwid.connect_signal(ok_button, 'click', self.on_ok)

        buttons = urwid.Columns([
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(ok_button, 'button', focus_map='button_focus')),
            ('weight', 1, urwid.Text('')),
        ], dividechars=0)

        # Оборачиваем кнопки в стиль dialog, чтобы фон вокруг них был синим
        buttons_map = urwid.AttrMap(buttons, 'dialogf4')

        pile = urwid.Pile([
            ('pack', urwid.Divider()),
            ('weight', 1, listbox_map),  # Используем обернутый listbox
            ('pack', urwid.Divider()),
            ('pack', buttons_map),  # Используем обернутые кнопки
            ('pack', urwid.Divider()),
        ])

        # Заливаем Filler стилем dialog
        fill = urwid.Filler(pile, valign='top', height=('relative', 95))
        fill_map = urwid.AttrMap(fill, 'dialogf4')

        linebox = urwid.LineBox(fill_map, title=title)

        # Финальная обертка рамки
        super().__init__(urwid.AttrMap(linebox, 'dialogf4'))

    def on_ok(self, button):
        self.close_callback()

    def keypress(self, size, key):
        if key in ('esc', 'enter', 'f4'):
            self.on_ok(None)
            return None
        return super().keypress(size, key)


#if __name__ == '__main__':
#    s3_config = S3Config('s3_config.json')
#    app = DualPaneApp(s3_config)
#    app.run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='S3 Commander - TUI File Manager for S3')
    
    # Режим 1: Обычный файл (по умолчанию)
    parser.add_argument('-c', '--config', default='s3_config.json', 
                        help='Path to plaintext config file (default: s3_config.json)')
    
    # Режим 2: Зашифрованный файл
    parser.add_argument('-e', '--encrypted-config', 
                        help='Path to encrypted config file (Mode 2). Requires password.')
    
    # Режим 3: Vault
    parser.add_argument('--vault-url', 
                        help='Vault URL (e.g. http://127.0.0.1:8200). Activates Mode 3.')
    parser.add_argument('--vault-path', 
                        help='Path to secret in Vault (e.g. secret/data/s3commander)')
    parser.add_argument('--vault-user', 
                        help='Vault username (will prompt if missing)')
    parser.add_argument('--vault-pass', 
                        help='Vault password (will prompt if missing - INSECURE in history)')
    
    args = parser.parse_args()

    # Инициализация конфига с аргументами
    s3_config = S3Config(args)

    # Запуск приложения
    app = DualPaneApp(s3_config)
    app.run()

