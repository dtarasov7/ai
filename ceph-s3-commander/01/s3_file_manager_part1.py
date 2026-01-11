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
from datetime import datetime
import tempfile
import shutil
import json
import threading
import time


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
    """Менеджер для работы с S3 Ceph"""

    def __init__(self, endpoint_config):
        self.endpoint_name = endpoint_config['name']
        self.endpoint_url = endpoint_config['url']
        self.access_key = endpoint_config['access_key']
        self.secret_key = endpoint_config['secret_key']
        self.is_connected = False
        self.connection_error = None

        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
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


class OverwriteDialog(urwid.WidgetWrap):
    """Диалог подтверждения перезаписи файла"""

    def __init__(self, filename, source_info, dest_info, callback, show_version_options=False):
        self.callback = callback

        title_text = urwid.Text('File already exists!', align='center')
        file_text = urwid.Text(f'File: {filename}')

        source_text = urwid.Text(
            f'Source: {format_size(source_info["size"])} | {source_info["mtime"].strftime("%Y-%m-%d %H:%M:%S")}'
        )
        dest_text = urwid.Text(
            f'Target: {format_size(dest_info["size"])} | {dest_info["mtime"].strftime("%Y-%m-%d %H:%M:%S")}'
        )

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
            urwid.Divider(),
            title_text,
            urwid.Divider(),
            file_text,
            urwid.Divider(),
            source_text,
            dest_text,
            urwid.Divider(),
            buttons,
            urwid.Divider(),
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
