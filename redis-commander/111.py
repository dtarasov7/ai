Я помогу вам убрать неиспользуемую логику дерева из кода. Вот обновленная версия:

```python
#!/usr/bin/env python3
"""
Redis Commander TUI - Terminal User Interface в стиле Redis Commander
Полная функциональность: просмотр ключей, выполнение команд, добавление ключей
"""

import urwid
import redis
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import OrderedDict, defaultdict
import logging

__VERSION__ = "0.6.0"
__AUTHOR__ = "Тарасов Дмитрий"

# Настройка логирования
logging.basicConfig(
    filename='redis_tui_audit.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('redis_commander_tui')


class ConnectionProfile:
    """Профиль подключения к Redis"""
    def __init__(self, name: str, host: str = 'localhost', port: int = 6379,
             password: Optional[str] = None, username: Optional[str] = None,
             ssl: bool = False, ssl_ca_certs: Optional[str] = None,
             ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
             socket_path: Optional[str] = None, readonly: bool = False,
             cluster_mode: bool = False,
             cluster_nodes: Optional[List[Tuple[str, int]]] = None):
        self.name = name
        self.host = host
        self.port = port
        self.password = password
        self.username = username
        self.ssl = ssl
        self.ssl_ca_certs = ssl_ca_certs
        self.ssl_certfile = ssl_certfile
        self.ssl_keyfile = ssl_keyfile
        self.socket_path = socket_path
        self.readonly = readonly
        self.cluster_mode = cluster_mode
        self.cluster_nodes = cluster_nodes or [(host, port)]

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'host': self.host,
            'port': self.port,
            'ssl': self.ssl,
            'readonly': self.readonly
        }


class RedisConnection:
    """Менеджер подключений к Redis"""

    def __init__(self, profile: ConnectionProfile):
        self.profile = profile
        self.client: Optional[redis.Redis] = None
        self.cluster_client: Optional[redis.RedisCluster] = None
        self.connected = False
        self.current_db = 0
        self.is_cluster = profile.cluster_mode

    def connect(self) -> Tuple[bool, str]:
        """Подключение к Redis или Redis Cluster"""
        try:
            if self.profile.cluster_mode:
                return self._connect_cluster()
            else:
                return self._connect_standalone()
        except Exception as e:
            self.connected = False
            logger.error(f"Connection failed: {e}")
            return False, str(e)

    def _connect_standalone(self) -> Tuple[bool, str]:
        """Подключение к standalone Redis"""
        try:
            kwargs = {
                'db': 0,
                'socket_timeout': 5,
                'decode_responses': False
            }

            if self.profile.socket_path:
                kwargs['unix_socket_path'] = self.profile.socket_path
            else:
                kwargs['host'] = self.profile.host
                kwargs['port'] = self.profile.port

            if self.profile.password:
                kwargs['password'] = self.profile.password

            if self.profile.username:
                kwargs['username'] = self.profile.username

            if self.profile.ssl:
                kwargs['ssl'] = True
                if self.profile.ssl_ca_certs:
                    kwargs['ssl_ca_certs'] = self.profile.ssl_ca_certs
                if self.profile.ssl_certfile:
                    kwargs['ssl_certfile'] = self.profile.ssl_certfile
                if self.profile.ssl_keyfile:
                    kwargs['ssl_keyfile'] = self.profile.ssl_keyfile

            self.client = redis.Redis(**kwargs)
            self.client.ping()
            self.connected = True
            self.current_db = 0
            logger.info(f"Connected to {self.profile.host}:{self.profile.port}")
            return True, "Connected"

        except Exception as e:
            self.connected = False
            logger.error(f"Connection failed: {e}")
            return False, str(e)

    def _connect_cluster(self) -> Tuple[bool, str]:
        """Подключение к Redis Cluster"""
        try:
            kwargs = {
                'host': self.profile.host,
                'port': self.profile.port,
                'decode_responses': False,
                'skip_full_coverage_check': True,
                'socket_timeout': 5,
            }

            if self.profile.password:
                kwargs['password'] = self.profile.password

            if self.profile.ssl:
                kwargs['ssl'] = True
                if self.profile.ssl_ca_certs:
                    kwargs['ssl_ca_certs'] = self.profile.ssl_ca_certs
                if self.profile.ssl_certfile:
                    kwargs['ssl_certfile'] = self.profile.ssl_certfile
                if self.profile.ssl_keyfile:
                    kwargs['ssl_keyfile'] = self.profile.ssl_keyfile

            logger.info(f"Connecting to Redis Cluster at {self.profile.host}:{self.profile.port}")

            self.cluster_client = redis.RedisCluster(**kwargs)
            self.cluster_client.ping()
            self.connected = True
            self.is_cluster = True

            try:
                cluster_info = self.cluster_client.cluster_info()
                logger.info(f"Cluster state: {cluster_info.get('cluster_state', 'unknown')}")
            except:
                pass

            return True, "Connected to cluster"

        except redis.exceptions.RedisClusterException as e:
            logger.error(f"Redis Cluster error: {e}")
            return False, f"Cluster error: {str(e)}"
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False, str(e)

    @property
    def active_client(self):
        """Возвращает активный клиент"""
        if self.is_cluster:
            return self.cluster_client
        return self.client

    def select_db(self, db: int) -> Tuple[bool, str]:
        """Переключение на другую базу данных (не поддерживается в кластере)"""
        if self.is_cluster:
            return False, "Redis Cluster supports only DB0"

        if not self.connected:
            return False, "Not connected"

        try:
            self.client.select(db)
            self.current_db = db
            logger.info(f"Switched to DB:{db}")
            return True, f"Switched to DB:{db}"
        except Exception as e:
            logger.error(f"Failed to switch DB: {e}")
            return False, str(e)

    def disconnect(self):
        if self.client:
            self.client.close()
            self.connected = False
            logger.info(f"Disconnected from {self.profile.host}:{self.profile.port}")


class AddKeyDialog(urwid.WidgetWrap):
    """Диалог добавления нового ключа"""
    signals = ['close']

    def __init__(self, connection: RedisConnection, on_success_callback):
        self.connection = connection
        self.on_success = on_success_callback

        # Поля ввода
        self.key_edit = urwid.Edit('Key: ')
        self.type_group = []
        self.type_buttons = [
            urwid.RadioButton(self.type_group, 'String', state=True),
            urwid.RadioButton(self.type_group, 'Hash'),
            urwid.RadioButton(self.type_group, 'List'),
            urwid.RadioButton(self.type_group, 'Set'),
            urwid.RadioButton(self.type_group, 'ZSet'),
        ]
        self.value_edit = urwid.Edit('Value: ', multiline=True)
        self.ttl_edit = urwid.Edit('TTL (seconds, optional): ')

        # Кнопки
        save_btn = urwid.Button('Save', on_press=self.on_save)
        cancel_btn = urwid.Button('Cancel', on_press=self.on_cancel)

        # Компоновка
        body = [
            self.key_edit,
            urwid.Divider(),
            urwid.Text('Type:'),
        ]
        body.extend(self.type_buttons)
        body.extend([
            urwid.Divider(),
            self.value_edit,
            urwid.Divider(),
            self.ttl_edit,
            urwid.Divider(),
            urwid.Columns([
                urwid.AttrMap(save_btn, 'button', 'button_focus'),
                urwid.AttrMap(cancel_btn, 'button', 'button_focus'),
            ]),
        ])

        pile = urwid.Pile(body)
        fill = urwid.Filler(pile, valign='top')
        padding = urwid.Padding(fill, left=2, right=2)
        linebox = urwid.LineBox(padding, title='Add New Key')

        super().__init__(urwid.AttrMap(linebox, 'dialog'))

    def get_selected_type(self) -> str:
        """Получить выбранный тип"""
        for i, btn in enumerate(self.type_buttons):
            if btn.state:
                return ['string', 'hash', 'list', 'set', 'zset'][i]
        return 'string'

    def on_save(self, button):
        """Сохранение ключа с проверкой для кластера"""
        key = self.key_edit.get_edit_text().strip()
        value = self.value_edit.get_edit_text().strip()
        key_type = self.get_selected_type()
        ttl_text = self.ttl_edit.get_edit_text().strip()

        if not key:
            self.show_error("Key cannot be empty")
            return

        # Проверка для кластера
        if self.connection.is_cluster:
            if '{' in key and '}' in key:
                import re
                if not re.search(r'\{.*?\}', key):
                    self.show_error("Invalid hash tag format. Use {tag} to ensure keys land on same node.")
                    return

        try:
            ttl = int(ttl_text) if ttl_text else None

            client = self.connection.active_client

            if key_type == 'string':
                client.set(key, value)
            elif key_type == 'hash':
                pairs = {}
                for line in value.split('\n'):
                    if ':' in line:
                        k, v = line.split(':', 1)
                        pairs[k.strip()] = v.strip()
                if pairs:
                    client.hset(key, mapping=pairs)
            elif key_type == 'list':
                items = [item.strip() for item in value.split('\n') if item.strip()]
                if items:
                    client.rpush(key, *items)
            elif key_type == 'set':
                items = [item.strip() for item in value.split('\n') if item.strip()]
                if items:
                    client.sadd(key, *items)
            elif key_type == 'zset':
                pairs = {}
                for line in value.split('\n'):
                    if ':' in line:
                        member, score = line.rsplit(':', 1)
                        try:
                            pairs[member.strip()] = float(score.strip())
                        except ValueError:
                            pass
                if pairs:
                    client.zadd(key, pairs)

            if ttl:
                client.expire(key, ttl)

            logger.info(f"Created key: {key} (type: {key_type})")
            self.on_success()
            self._emit('close')

        except redis.exceptions.RedisClusterException as e:
            self.show_error(f"Cluster error: {e}")
            logger.error(f"Cluster error creating key: {e}")
        except Exception as e:
            self.show_error(f"Failed to create key: {e}")
            logger.error(f"Failed to create key: {e}")

    def show_error(self, message):
        """Показать сообщение об ошибке"""
        error_text = urwid.Text(('error', f"Error: {message}"))
        self.body.contents.insert(0, (error_text, ('pack', None)))

    def on_cancel(self, button):
        """Отмена"""
        self._emit('close')


class RedisCommanderUI:
    """Главное окно в стиле Redis Commander"""

    palette = [
        ('header', 'white', 'dark blue', 'bold'),
        ('header_text', 'white', 'dark blue'),
        ('footer', 'white', 'dark blue'),
        ('sidebar', 'light gray', 'dark blue'),
        ('sidebar_focus', 'white', 'dark blue', 'bold'),
        ('connection', 'light cyan', 'dark blue'),
        ('connection_selected', 'black', 'light cyan', 'bold'),
        ('key_folder', 'white', 'dark blue'),
        ('key_folder_focus', 'black', 'light cyan', 'bold'),
        ('key_item', 'yellow', 'dark blue'),
        ('key_item_focus', 'black', 'light cyan', 'bold'),
        ('button', 'white', 'dark blue'),
        ('button_focus', 'white', 'light blue', 'bold'),
        ('button_danger', 'white', 'dark red'),
        ('info_label', 'light cyan', 'dark blue'),
        ('info_value', 'white', 'dark blue'),
        ('tab_active', 'white', 'light blue', 'bold'),
        ('tab_inactive', 'light gray', 'dark blue'),
        ('error', 'light red', 'dark blue'),
        ('success', 'light green', 'dark blue'),
        ('dialog', 'white', 'dark blue'),
        ('background', 'white', 'dark blue'),
    ]

    def __init__(self):
        self.connections: Dict[str, RedisConnection] = {}
        self.current_connection: Optional[RedisConnection] = None
        self.profiles = self.load_profiles()
        self.keys_list: List[bytes] = []  # Простой список ключей
        self.current_key: Optional[bytes] = None
        self.console_mode = False
        self.max_db = 15

        # Создаем интерфейс
        self.create_ui()

        # Автоматически подключаемся к первому профилю
        if self.profiles:
            first_profile = list(self.profiles.values())[0]
            self.connect_to_profile(first_profile)

        self.loop = urwid.MainLoop(
            self.main_frame,
            palette=self.palette,
            unhandled_input=self.handle_input,
            pop_ups=True
        )

    def get_key_type_icon(self, key: str) -> str:
        """Получить иконку для типа ключа"""
        ascii_icons = {
            'string': '[St] ',
            'hash': '[Hs] ',
            'list': '[Li] ',
            'set': '[Se] ',
            'zset': '[Zs] ',
            'stream': '[Tr] ',
            'none': '[No] ',
            'unknown': '[?] ',
        }

        if not self.current_connection or not self.current_connection.connected:
            return ascii_icons['unknown']

        try:
            client = self.current_connection.active_client
            key_type = client.type(key.encode('utf-8', errors='replace'))

            if isinstance(key_type, bytes):
                key_type = key_type.decode('utf-8').lower()
            else:
                key_type = str(key_type).lower()

            return ascii_icons.get(key_type, ascii_icons['unknown'])
        except Exception as e:
            logger.error(f"Error getting key type for {key}: {e}")
            return ascii_icons['unknown']

    def load_profiles(self) -> Dict[str, ConnectionProfile]:
        """Загрузка профилей с поддержкой кластера"""
        profiles = {}
        profiles_file = 'redis_profiles.json'

        if os.path.exists(profiles_file):
            try:
                with open(profiles_file, 'r') as f:
                    data = json.load(f)
                    for name, config in data.items():
                        clean_config = {}

                        base_params = ['name', 'host', 'port', 'password', 'username',
                                       'ssl', 'socket_path', 'readonly', 'ssl_ca_certs',
                                       'ssl_certfile', 'ssl_keyfile']

                        for param in base_params:
                            if param in config:
                                clean_config[param] = config[param]

                        if 'cluster_mode' in config:
                            clean_config['cluster_mode'] = bool(config['cluster_mode'])

                        if 'cluster_nodes' in config:
                            nodes = config['cluster_nodes']
                            if isinstance(nodes, list):
                                formatted_nodes = []
                                for node in nodes:
                                    if isinstance(node, str):
                                        if ':' in node:
                                            host, port_str = node.split(':', 1)
                                            try:
                                                port = int(port_str)
                                                formatted_nodes.append((host, port))
                                            except ValueError:
                                                logger.warning(f"Invalid port in node {node}")
                                    elif isinstance(node, dict):
                                        host = node.get('host', 'localhost')
                                        port = node.get('port', 6379)
                                        try:
                                            port = int(port)
                                            formatted_nodes.append((host, port))
                                        except ValueError:
                                            logger.warning(f"Invalid port in node {node}")
                                    elif isinstance(node, list) and len(node) == 2:
                                        host, port = node[0], node[1]
                                        try:
                                            port = int(port)
                                            formatted_nodes.append((str(host), port))
                                        except ValueError:
                                            logger.warning(f"Invalid port in node {node}")

                                if formatted_nodes:
                                    clean_config['cluster_nodes'] = formatted_nodes

                        try:
                            if 'host' not in clean_config:
                                if 'cluster_nodes' in clean_config and clean_config['cluster_nodes']:
                                    clean_config['host'] = clean_config['cluster_nodes'][0][0]
                                    clean_config['port'] = clean_config['cluster_nodes'][0][1]
                                else:
                                    clean_config['host'] = 'localhost'
                                    clean_config['port'] = 6379

                            profiles[name] = ConnectionProfile(**clean_config)

                        except TypeError as e:
                            logger.error(f"Invalid config for profile '{name}': {e}")
                            minimal_config = {
                                'name': name,
                                'host': config.get('host', 'localhost'),
                                'port': config.get('port', 6379),
                                'cluster_mode': config.get('cluster_mode', False)
                            }
                            if 'password' in config:
                                minimal_config['password'] = config['password']
                            profiles[name] = ConnectionProfile(**minimal_config)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in profiles file: {e}")
                profiles['localhost'] = ConnectionProfile('localhost', 'localhost', 6379)
            except Exception as e:
                logger.error(f"Failed to load profiles: {e}")
                profiles['localhost'] = ConnectionProfile('localhost', 'localhost', 6379)

        if not profiles:
            profiles['localhost'] = ConnectionProfile('localhost', 'localhost', 6379)

        return profiles

    def create_ui(self):
        """Создание интерфейса"""
        # Header
        header_text = urwid.Text([
            ('header_text', ' ● '),
            ('header_text', 'Redis Commander TUI')
        ], align='left')

        self.header = urwid.AttrMap(
            urwid.Padding(header_text, left=1, right=1),
            'header'
        )

        # Toolbar
        self.commands_btn = urwid.Button('F5: Commands')
        self.add_key_btn = urwid.Button('F4: Add New Key')
        self.refresh_btn = urwid.Button('F2: Refresh')
        self.disconnect_btn = urwid.Button('F9: Disconnect')
        self.help_btn = urwid.Button('F1: Help')
        self.exit_btn = urwid.Button('F10: Exit')

        urwid.connect_signal(self.refresh_btn, 'click', lambda b: self.refresh_keys())
        urwid.connect_signal(self.commands_btn, 'click', lambda b: self.toggle_console())
        urwid.connect_signal(self.add_key_btn, 'click', lambda b: self.show_add_key_dialog())
        urwid.connect_signal(self.disconnect_btn, 'click', lambda b: self.disconnect())
        urwid.connect_signal(self.exit_btn, 'click', lambda b: self.exit_main())
        urwid.connect_signal(self.help_btn, 'click', lambda b: self.show_help())

        toolbar = urwid.Columns([
            ('pack', urwid.AttrMap(self.refresh_btn, 'button', 'button_focus')),
            ('pack', urwid.Text(' ')),
            ('pack', urwid.AttrMap(self.add_key_btn, 'button', 'button_focus')),
            ('pack', urwid.Text(' ')),
            ('pack', urwid.AttrMap(self.commands_btn, 'button', 'button_focus')),
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(self.disconnect_btn, 'button_danger', 'button_focus')),
            ('pack', urwid.Text(' ')),
            ('pack', urwid.AttrMap(self.help_btn, 'button', 'button_focus')),
            ('pack', urwid.Text(' ')),
            ('pack', urwid.AttrMap(self.exit_btn, 'button', 'button_focus')),
        ], dividechars=0)

        # Левая панель - список ключей
        self.connection_tree = urwid.SimpleListWalker([])
        self.connection_listbox = urwid.ListBox(self.connection_tree)

        left_panel = urwid.LineBox(
            urwid.AttrMap(self.connection_listbox, 'sidebar'),
            title='Connections & Keys'
        )

        # Правая панель - детали ключа
        self.detail_walker = urwid.SimpleListWalker([])
        self.detail_listbox = urwid.ListBox(self.detail_walker)

        right_panel = urwid.LineBox(
            urwid.AttrMap(self.detail_listbox, 'background'),
            title='Details'
        )

        # Основная область
        content = urwid.Columns([
            ('weight', 1, left_panel),
            ('weight', 3, right_panel),
        ], dividechars=1)

        # Tabs
        self.tab_text = urwid.Text('')

        # Статус
        self.status_text = urwid.Text('Ready')

        # Консоль
        self.console_history = urwid.SimpleListWalker([])
        self.console_listbox = urwid.ListBox(self.console_history)
        self.command_prompt = urwid.Edit('redis> ')

        console_content = urwid.Pile([
            ('weight', 1, urwid.AttrMap(self.console_listbox, 'background')),
            ('pack', urwid.Divider('─')),
            ('pack', urwid.AttrMap(self.command_prompt, 'footer')),
        ])

        self.console_panel = urwid.LineBox(
            console_content,
            title='Redis Console'
        )

        # Основное тело
        self.main_content = urwid.Pile([
            ('pack', urwid.AttrMap(urwid.Padding(toolbar, left=1, right=1), 'background')),
            ('weight', 1, urwid.AttrMap(content, 'background')),
        ])

        # Footer pile
        self.footer_pile = urwid.Pile([
            urwid.AttrMap(self.tab_text, 'footer'),
            urwid.AttrMap(self.status_text, 'footer'),
        ])

        self.main_frame = urwid.Frame(
            header=self.header,
            body=self.main_content,
            footer=self.footer_pile
        )

        self.update_connection_tree()

    def toggle_console(self):
        """Переключение консоли"""
        if self.console_mode:
            # Выключаем консоль
            toolbar = self.create_toolbar()
            content_area = urwid.Columns([
                ('weight', 1, urwid.LineBox(
                    urwid.AttrMap(self.connection_listbox, 'sidebar'),
                    title='Connections & Keys'
                )),
                ('weight', 3, urwid.LineBox(
                    urwid.AttrMap(self.detail_listbox, 'background'),
                    title='Details'
                )),
            ], dividechars=1)

            self.main_content.contents = [
                (urwid.AttrMap(urwid.Padding(toolbar, left=1, right=1), 'background'), ('pack', None)),
                (urwid.AttrMap(content_area, 'background'), ('weight', 1)),
            ]
            self.console_mode = False
            self.set_status("Console closed")
        else:
            # Включаем консоль
            toolbar = self.create_toolbar()
            content_area = urwid.Columns([
                ('weight', 1, urwid.LineBox(
                    urwid.AttrMap(self.connection_listbox, 'sidebar'),
                    title='Connections & Keys'
                )),
                ('weight', 3, urwid.LineBox(
                    urwid.AttrMap(self.detail_listbox, 'background'),
                    title='Details'
                )),
            ], dividechars=1)

            self.main_content.contents = [
                (urwid.AttrMap(urwid.Padding(toolbar, left=1, right=1), 'background'), ('pack', None)),
                (urwid.AttrMap(content_area, 'background'), ('weight', 2)),
                (urwid.AttrMap(self.console_panel, 'background'), ('weight', 1)),
            ]
            self.console_mode = True

            if len(self.console_history) == 0:
                self.console_history.append(
                    urwid.Text(('success', 'Redis Console - Type commands and press Enter. Type "exit" or press Esc to close.'))
                )
                self.console_history.append(urwid.Divider())

            self.main_content.focus_position = 2
            self.console_panel.original_widget.focus_position = 2
            self.set_status("Console opened (press F2 to close)")

    def create_toolbar(self):
        """Создание тулбара"""
        return urwid.Columns([
            ('pack', urwid.AttrMap(self.refresh_btn, 'button', 'button_focus')),
            ('pack', urwid.Text(' ')),
            ('pack', urwid.AttrMap(self.add_key_btn, 'button', 'button_focus')),
            ('pack', urwid.Text(' ')),
            ('pack', urwid.AttrMap(self.commands_btn, 'button', 'button_focus')),
            ('weight', 1, urwid.Text('')),
            ('pack', urwid.AttrMap(self.disconnect_btn, 'button_danger', 'button_focus')),
            ('pack', urwid.Text(' ')),
            ('pack', urwid.AttrMap(self.help_btn, 'button', 'button_focus')),
            ('pack', urwid.Text(' ')),
            ('pack', urwid.AttrMap(self.exit_btn, 'button', 'button_focus')),
        ], dividechars=0)

    def execute_command(self):
        """Выполнение команды из консоли"""
        if not self.current_connection or not self.current_connection.connected:
            self.console_history.append(urwid.Text(('error', '✗ Not connected to Redis')))
            self.console_history.append(urwid.Divider())
            if len(self.console_history) > 0:
                self.console_listbox.set_focus(len(self.console_history) - 1)
            return

        command = self.command_prompt.get_edit_text().strip()
        if not command:
            return

        if command.lower() in ['exit', 'quit']:
            self.toggle_console()
            return

        self.console_history.append(urwid.Text(('info_label', f'redis> {command}')))

        try:
            client = self.current_connection.active_client
            is_cluster = self.current_connection.is_cluster

            parts = command.split()
            cmd = parts[0].upper()
            args = parts[1:]

            if is_cluster:
                unsupported_commands = ['SELECT', 'MOVE', 'SWAPDB', 'MIGRATE', 'RANDOMKEY']
                if cmd in unsupported_commands:
                    self.console_history.append(
                        urwid.Text(('error', f"(error) Command '{cmd}' not supported in Redis Cluster"))
                    )
                    self.console_history.append(urwid.Divider())
                    self.command_prompt.set_edit_text('')
                    return

                if cmd.startswith('CLUSTER'):
                    result = client.execute_command(cmd, *args)

                elif cmd == 'KEYS':
                    pattern = args[0] if args else '*'
                    keys = []
                    for node in client.get_nodes():
                        if node.server_type == 'master':
                            try:
                                node_keys = node.keys(pattern)
                                keys.extend(node_keys)
                            except Exception as e:
logger.warning(f"Error getting keys from node: {e}")
                    result = keys
                elif cmd == 'SCAN':
                    cursor = int(args[0]) if args and args[0].isdigit() else 0
                    pattern = args[1] if len(args) > 1 else '*'
                    count = int(args[2]) if len(args) > 2 else 10

                    all_keys = []
                    for node in client.get_nodes():
                        if node.server_type == 'master':
                            try:
                                node_cursor = 0
                                while True:
                                    node_cursor, batch = node.scan(node_cursor, match=pattern, count=count)
                                    all_keys.extend(batch)
                                    if node_cursor == 0:
                                        break
                            except Exception as e:
                                logger.warning(f"Error scanning node: {e}")

                    result = [0, all_keys[:count]] if all_keys else [0, []]
                elif cmd == 'INFO':
                    if args and args[0].lower() in ['cluster', 'keyspace', 'memory', 'cpu']:
                        section = args[0].lower()
                        info_results = []
                        for node in client.get_nodes():
                            if node.server_type == 'master':
                                try:
                                    node_info = node.info(section)
                                    info_results.append(f"--- {node.host}:{node.port} ---\n{node_info}")
                                except Exception as e:
                                    info_results.append(f"--- {node.host}:{node.port} ERROR: {e} ---")
                        result = "\n".join(info_results)
                    else:
                        result = client.execute_command(cmd, *args)
                elif cmd == 'DBSIZE':
                    total = 0
                    for node in client.get_nodes():
                        if node.server_type == 'master':
                            try:
                                total += node.dbsize()
                            except Exception as e:
                                logger.warning(f"Error getting dbsize from node: {e}")
                    result = total
                elif cmd in ['FLUSHALL', 'FLUSHDB']:
                    results = []
                    for node in client.get_nodes():
                        if node.server_type == 'master':
                            try:
                                node_result = node.execute_command(cmd, *args)
                                results.append(f"{node.host}:{node.port}: {node_result}")
                            except Exception as e:
                                results.append(f"{node.host}:{node.port}: ERROR - {e}")
                    result = "\n".join(results)
                else:
                    result = client.execute_command(cmd, *args)
            else:
                result = client.execute_command(cmd, *args)

            result_str = self.format_redis_result(cmd, result)

            if '\n' in result_str:
                for line in result_str.split('\n'):
                    self.console_history.append(urwid.Text(('success', line)))
            else:
                self.console_history.append(urwid.Text(('success', result_str)))

            logger.info(f"Executed: {command} => {result_str[:100]}")
            self.command_prompt.set_edit_text('')

            modifying_commands = [
                'SET', 'DEL', 'HSET', 'HDEL', 'LPUSH', 'RPUSH', 'LPOP', 'RPOP',
                'SADD', 'SREM', 'ZADD', 'ZREM', 'FLUSHDB', 'FLUSHALL', 'RENAME',
                'RENAMENX', 'EXPIRE', 'EXPIREAT', 'PERSIST', 'APPEND', 'DECR',
                'INCR', 'LSET', 'LTRIM', 'MSET', 'PEXPIRE', 'PEXPIREAT', 'PSETEX',
                'SETEX', 'SETNX', 'STREAM', 'HSETNX', 'HMSET', 'LPUSHX', 'RPUSHX', 'SINTERSTORE',
                'SUNIONSTORE', 'SDIFFSTORE', 'ZINTERSTORE', 'ZUNIONSTORE', 'ZREM',
                'ZREMRANGEBYLEX', 'ZREMRANGEBYRANK', 'ZREMRANGEBYSCORE'
            ]

            if cmd in modifying_commands:
                self.refresh_keys()

        except redis.ResponseError as e:
            self.console_history.append(urwid.Text(('error', f'(error) {str(e)}')))
            logger.error(f"Redis error: {e}")
        except redis.exceptions.RedisClusterException as e:
            self.console_history.append(urwid.Text(('error', f'(cluster error) {str(e)}')))
            logger.error(f"Redis cluster error: {e}")
        except Exception as e:
            self.console_history.append(urwid.Text(('error', f'(error) {str(e)}')))
            logger.error(f"Command failed: {e}")

        self.console_history.append(urwid.Divider())

        if len(self.console_history) > 0:
            self.console_listbox.set_focus(len(self.console_history) - 1)

        if len(self.console_history) > 200:
            self.console_history[:] = self.console_history[-150:]

    def format_redis_result(self, cmd: str, result) -> str:
        """Форматирование результата Redis команды"""
        if cmd == 'PING':
            if result is True or result == b'PONG' or result == 'PONG':
                return 'PONG'
            elif isinstance(result, bytes):
                return result.decode('utf-8', errors='replace')
            elif isinstance(result, str):
                return result
            else:
                return 'PONG'
        elif result is None:
            return '(nil)'
        elif isinstance(result, bool):
            return 'OK' if result else '(error)'
        elif isinstance(result, int):
            return f'(integer) {result}'
        elif isinstance(result, bytes):
            try:
                decoded = result.decode('utf-8', errors='replace')
                return f'"{decoded}"'
            except:
                return f'<bytes: {len(result)}>'
        elif isinstance(result, str):
            return f'"{result}"'
        elif isinstance(result, list):
            if len(result) == 0:
                return '(empty list or set)'
            else:
                result_lines = []
                for i, item in enumerate(result[:50]):
                    if isinstance(item, bytes):
                        try:
                            decoded = item.decode("utf-8", errors="replace")
                            result_lines.append(f'{i + 1}) "{decoded}"')
                        except:
                            result_lines.append(f'{i + 1}) <bytes: {len(item)}>')
                    elif isinstance(item, str):
                        result_lines.append(f'{i + 1}) "{item}"')
                    elif isinstance(item, list):
                        if i == 0 and len(item) == 2 and isinstance(item[0], int):
                            result_lines.append(f'{i + 1}) 1) "{item[0]}"')
                            result_lines.append(f'   2) {self.format_redis_result("SCAN", item[1])}')
                        else:
                            result_lines.append(f'{i + 1}) {item}')
                    else:
                        result_lines.append(f'{i + 1}) {str(item)}')

                if len(result) > 50:
                    result_lines.append(f'... and {len(result) - 50} more items')

                return '\n'.join(result_lines)
        elif isinstance(result, dict):
            if len(result) == 0:
                return '(empty hash)'
            else:
                result_lines = []
                for i, (key, value) in enumerate(list(result.items())[:50]):
                    if isinstance(key, bytes):
                        try:
                            key = key.decode("utf-8", errors="replace")
                        except:
                            key = f'<bytes: {len(key)}>'

                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8", errors="replace")
                        except:
                            value = f'<bytes: {len(value)}>'

                    result_lines.append(f'{i + 1}) "{key}" => "{value}"')

                if len(result) > 50:
                    result_lines.append(f'... and {len(result) - 50} more fields')

                return '\n'.join(result_lines)
        else:
            return str(result)

    def update_connection_tree(self):
        """Обновление списка подключений и ключей"""
        self.connection_tree[:] = []

        for name, profile in self.profiles.items():
            conn = self.connections.get(name)

            if conn and conn.connected:
                icon = '● '
                if conn.is_cluster:
                    server_label = f"{icon}{profile.name} [CLUSTER]"
                    style = 'connection'
                else:
                    server_label = f"{icon}{profile.name} ({profile.host}:{profile.port})"
                    style = 'connection'
            else:
                icon = '○ '
                server_label = f"{icon}{profile.name} ({profile.host}:{profile.port})"
                style = 'connection'

            server_btn = urwid.Button(server_label, on_press=self.on_server_select,
                                      user_data=name)

            if conn and conn.connected:
                self.connection_tree.append(urwid.AttrMap(server_btn, style, 'connection_selected'))
            else:
                self.connection_tree.append(urwid.AttrMap(server_btn, style, 'sidebar_focus'))

            # Показываем базы данных для подключенного сервера
            if conn and conn.connected:
                if conn.is_cluster:
                    # Для кластера только DB0
                    is_current = (self.current_connection == conn)
                    db_icon = '  ▪ ' if is_current else '  ▫ '
                    db_label = f"{db_icon}DB0"

                    db_btn = urwid.Button(db_label, on_press=self.on_db_select,
                                          user_data=(name, 0))

                    if is_current:
                        item = urwid.AttrMap(db_btn, 'connection_selected', 'connection_selected')
                    else:
                        item = urwid.AttrMap(db_btn, 'key_folder', 'key_folder_focus')

                    self.connection_tree.append(item)

                    # Список ключей для текущей БД
                    if is_current:
                        self.add_keys_to_tree()
                else:
                    # Standalone
                    db_key_counts = self.get_all_db_key_counts(conn)

                    for db_num in range(self.max_db + 1):
                        is_current = (self.current_connection == conn and
                                      conn.current_db == db_num)

                        db_icon = '  ▪ ' if is_current else '  ▫ '
                        key_count = db_key_counts.get(db_num, 0)

                        if key_count > 0:
                            db_label = f"{db_icon}DB{db_num} ({key_count} keys)"
                        else:
                            db_label = f"{db_icon}DB{db_num}"

                        db_btn = urwid.Button(db_label, on_press=self.on_db_select,
                                              user_data=(name, db_num))

                        if is_current:
                            item = urwid.AttrMap(db_btn, 'connection_selected', 'connection_selected')
                        else:
                            item = urwid.AttrMap(db_btn, 'key_folder', 'key_folder_focus')

                        self.connection_tree.append(item)

                        # Список ключей для текущей БД
                        if is_current:
                            self.add_keys_to_tree()

        self.update_tabs()

    def add_keys_to_tree(self):
        """Добавление ключей в дерево как простой список"""
        for key in self.keys_list:
            try:
                key_str = key.decode('utf-8', errors='replace')
                icon = self.get_key_type_icon(key_str)
                label = f"    {icon}{key_str}"
                btn = urwid.Button(label, on_press=self.on_key_select, user_data=key)
                item = urwid.AttrMap(btn, 'key_item', 'key_item_focus')
                self.connection_tree.append(item)
            except Exception as e:
                logger.error(f"Error adding key to tree: {e}")

    def get_all_db_key_counts(self, conn: RedisConnection) -> Dict[int, int]:
        """Получить количество ключей во всех базах данных"""
        db_counts = {}

        if not conn or not conn.connected:
            return db_counts

        if conn.is_cluster:
            try:
                total_keys = conn.active_client.dbsize()
                if total_keys > 0:
                    db_counts[0] = total_keys
            except Exception as e:
                logger.error(f"Failed to get cluster key count: {e}")
            return db_counts

        current_db = conn.current_db

        try:
            for db_num in range(self.max_db + 1):
                try:
                    conn.client.select(db_num)
                    count = conn.client.dbsize()
                    if count > 0:
                        db_counts[db_num] = count
                except Exception as e:
                    logger.error(f"Failed to get key count for DB{db_num}: {e}")
                    continue

            conn.client.select(current_db)

        except Exception as e:
            logger.error(f"Failed to get all DB key counts: {e}")
            try:
                conn.client.select(current_db)
            except:
                pass

        return db_counts

    def on_server_select(self, button, profile_name: str):
        """Выбор сервера"""
        profile = self.profiles.get(profile_name)
        if not profile:
            return

        if profile_name in self.connections and self.connections[profile_name].connected:
            self.current_connection = self.connections[profile_name]
            self.set_status(f"Already connected to {profile.name}", 'success')
        else:
            self.connect_to_profile(profile)

        self.refresh_keys()
        self.update_connection_tree()

    def connect_to_profile(self, profile: ConnectionProfile):
        """Подключение к профилю"""
        if profile.cluster_mode:
            if profile.cluster_nodes:
                first_node = profile.cluster_nodes[0]
                server_key = f"cluster:{first_node[0]}:{first_node[1]}"
            else:
                server_key = f"cluster:{profile.host}:{profile.port}"
        else:
            if profile.socket_path:
                server_key = f"unix:{profile.socket_path}"
            else:
                server_key = f"{profile.host}:{profile.port}"

        for existing_name, conn in self.connections.items():
            if conn.connected:
                if (conn.is_cluster == profile.cluster_mode and
                        conn.profile.host == profile.host and
                        conn.profile.port == profile.port):

                    if profile.cluster_mode:
                        if (hasattr(conn.profile, 'cluster_nodes') and
                                conn.profile.cluster_nodes == profile.cluster_nodes):
                            self.current_connection = conn
                            self.set_status(f"Already connected to cluster {server_key}", 'success')
                            self.refresh_keys()
                            return
                    else:
                        self.current_connection = conn
                        self.set_status(f"Already connected to {server_key}", 'success')
                        self.refresh_keys()
                        return

        conn = RedisConnection(profile)
        success, message = conn.connect()

        if success:
            self.connections[profile.name] = conn
            self.current_connection = conn

            if profile.cluster_mode:
                node_count = len(profile.cluster_nodes) if hasattr(profile, 'cluster_nodes') else 1
                self.set_status(f"Connected to Redis Cluster ({node_count} nodes)", 'success')
            else:
                self.set_status(f"Connected to {profile.host}:{profile.port}", 'success')

            self.refresh_keys()
        else:
            self.set_status(f"Connection failed: {message}", 'error')

    def on_db_select(self, button, data: Tuple[str, int]):
        """Выбор базы данных"""
        profile_name, db_num = data

        conn = self.connections.get(profile_name)
        if not conn or not conn.connected:
            return

        if conn.is_cluster:
            if db_num != 0:
                self.set_status("Redis Cluster supports only DB0", 'warning')
                return
            self.current_connection = conn
            self.set_status("Redis Cluster (DB0)", 'success')
            self.refresh_keys()
            self.update_connection_tree()
        else:
            self.current_connection = conn
            success, message = conn.select_db(db_num)

            if success:
                self.set_status(f"Switched to DB{db_num}", 'success')
                self.refresh_keys()
                self.update_connection_tree()
            else:
                self.set_status(f"Failed to switch DB: {message}", 'error')

    def on_key_select(self, button, key: bytes):
        """Выбор ключа"""
        if not self.current_connection or not self.current_connection.connected:
            return

        self.current_key = key
        self.display_key_details(self.current_key)

    def disconnect(self):
        """Отключение от текущего сервера"""
        if self.current_connection:
            name = self.current_connection.profile.name
            self.current_connection.disconnect()
            del self.connections[name]
            self.current_connection = None
            self.set_status(f"Disconnected from {name}", 'success')
            self.keys_list = []
            self.update_connection_tree()

    def exit_main(self):
        raise urwid.ExitMainLoop()

    def refresh_keys(self):
        """Обновление списка ключей"""
        if not self.current_connection or not self.current_connection.connected:
            return

        try:
            client = self.current_connection.active_client
            keys = []

            self.set_status("Scanning keys...")

            if self.current_connection.is_cluster:
                # Для кластера сканируем через все мастер-ноды
                if hasattr(client, 'scan_iter'):
                    max_keys = 5000
                    scan_count = 0

                    for key in client.scan_iter(match='*', count=100):
                        keys.append(key)
                        scan_count += 1

                        if scan_count % 100 == 0:
                            self.set_status(f"Scanning... Found {scan_count} keys")

                        if scan_count >= max_keys:
                            self.set_status(f"Stopped at {max_keys} keys (limit reached)")
                            break
            else:
                # Standalone режим
                cursor = 0
                while True:
                    cursor, batch = client.scan(cursor, match='*', count=100)
                    keys.extend(batch)
                    if cursor == 0:
                        break
                    if len(keys) >= 5000:
                        break

            # Убираем дубликаты и сортируем
            seen = set()
            unique_keys = []
            for key in keys:
                if key not in seen:
                    seen.add(key)
                    unique_keys.append(key)

            # Сортируем ключи
            unique_keys.sort()
            self.keys_list = unique_keys

            self.update_connection_tree()

            if self.current_connection.is_cluster:
                self.set_status(f"Loaded {len(unique_keys)} keys from cluster", 'success')
            else:
                self.set_status(f"Loaded {len(unique_keys)} keys", 'success')

            if self.current_key:
                self.display_key_details(self.current_key)

        except Exception as e:
            self.set_status(f"Error loading keys: {e}", 'error')
            logger.error(f"Error loading keys: {e}")

    def display_key_details(self, key: bytes):
        """Отображение деталей ключа"""
        if not self.current_connection or not self.current_connection.connected:
            return

        try:
            client = self.current_connection.active_client
            key_str = key.decode('utf-8', errors='replace')

            try:
                key_type = client.type(key)
                if isinstance(key_type, bytes):
                    key_type = key_type.decode('utf-8')
                ttl = client.ttl(key)
            except Exception as e:
                self.set_status(f"Error getting key info: {e}", 'error')
                return

            self.detail_walker[:] = []

            self.detail_walker.append(urwid.Text([
                ('info_label', 'Key: '),
                ('info_value', key_str)
            ]))
            self.detail_walker.append(urwid.Divider())

            info_items = [
                ('Type', key_type),
                ('TTL', f"{ttl}s" if ttl > 0 else 'No expiration' if ttl == -1 else 'N/A'),
            ]

            if self.current_connection.is_cluster:
                try:
                    slot = client.keyslot(key_str)
                    node = client.get_node_from_key(key_str)
                    info_items.extend([
                        ('Hash Slot', str(slot)),
                        ('Node', f"{node.host}:{node.port}"),
                    ])
                except Exception as e:
                    logger.warning(f"Could not get cluster info for key: {e}")

            try:
                if key_type == 'string':
                    size = client.strlen(key)
                    info_items.append(('Size', f"{size} bytes"))
                elif key_type == 'list':
                    size = client.llen(key)
                    info_items.append(('Length', str(size)))
                elif key_type == 'set':
                    size = client.scard(key)
                    info_items.append(('Members', str(size)))
                elif key_type == 'zset':
                    size = client.zcard(key)
                    info_items.append(('Members', str(size)))
                elif key_type == 'hash':
                    size = client.hlen(key)
                    info_items.append(('Fields', str(size)))
            except Exception as e:
                logger.warning(f"Could not get size info for key: {e}")

            for label, value in info_items:
                row = urwid.Columns([
                    ('weight', 1, urwid.AttrMap(urwid.Text(label), 'info_label')),
                    ('weight', 2, urwid.AttrMap(urwid.Text(str(value)), 'info_value')),
                ])
                self.detail_walker.append(row)

            self.detail_walker.append(urwid.Divider())
            self.detail_walker.append(urwid.Text(('info_label', 'Value:')))
            self.detail_walker.append(urwid.Divider())

            try:
                if key_type == 'string':
                    value = client.get(key)
                    if value is None:
                        self.detail_walker.append(urwid.Text(('error', 'Key not found')))
                    else:
                        try:
                            value_str = value.decode('utf-8', errors='replace')
                            self.detail_walker.append(urwid.Text(value_str))
                        except:
                            self.detail_walker.append(
                                urwid.Text(f'<binary data: {len(value)} bytes>')
                            )

                elif key_type == 'hash':
                    hash_data = client.hgetall(key)
                    if not hash_data:
                        self.detail_walker.append(urwid.Text('(empty hash)'))
                    else:
                        for field, val in hash_data.items():
                            try:
                                field_str = field.decode('utf-8', errors='replace')
                                val_str = val.decode('utf-8', errors='replace')
                                row = urwid.Columns([
                                    ('weight', 1, urwid.Text(('key_folder', field_str))),
                                    ('weight', 2, urwid.Text(val_str)),
                                ])
                                self.detail_walker.append(row)
                            except:
                                row = urwid.Columns([
                                    ('weight', 1, urwid.Text(('key_folder', '<binary field>'))),
                                    ('weight', 2, urwid.Text(f'<binary: {len(val)} bytes>')),
                                ])
                                self.detail_walker.append(row)

                elif key_type == 'list':
                    list_data = client.lrange(key, 0, 99)
                    if not list_data:
                        self.detail_walker.append(urwid.Text('(empty list)'))
                    else:
                        for idx, item in enumerate(list_data):
                            try:
                                item_str = item.decode('utf-8', errors='replace')
                                self.detail_walker.append(urwid.Text(f"[{idx}] {item_str}"))
                            except:
                                self.detail_walker.append(
                                    urwid.Text(f"[{idx}] <binary: {len(item)} bytes>")
                                )

                elif key_type == 'set':
                    set_data = list(client.smembers(key))[:100]
                    if not set_data:
                        self.detail_walker.append(urwid.Text('(empty set)'))
                    else:
                        for item in set_data:
                            try:
                                item_str = item.decode('utf-8', errors='replace')
                                self.detail_walker.append(urwid.Text(f"• {item_str}"))
                            except:
                                self.detail_walker.append(
                                    urwid.Text(f"• <binary: {len(item)} bytes>")
                                )

                elif key_type == 'zset':
                    zset_data = client.zrange(key, 0, 99, withscores=True)
                    if not zset_data:
                        self.detail_walker.append(urwid.Text('(empty zset)'))
                    else:
                        for member, score in zset_data:
                            try:
                                member_str = member.decode('utf-8', errors='replace')
                                row = urwid.Columns([
                                    ('weight', 2, urwid.Text(member_str)),
                                    ('weight', 1, urwid.Text(('info_value', str(score)))),
                                ])
                                self.detail_walker.append(row)
                            except:
                                row = urwid.Columns([
                                    ('weight', 2, urwid.Text(f'<binary: {len(member)} bytes>')),
                                    ('weight', 1, urwid.Text(('info_value', str(score)))),
                                ])
                                self.detail_walker.append(row)

                else:
                    self.detail_walker.append(urwid.Text(f'Unknown key type: {key_type}'))

            except Exception as e:
                self.detail_walker.append(
                    urwid.Text(('error', f'Error retrieving value: {str(e)}'))
                )
                logger.error(f"Error retrieving value for key {key_str}: {e}")

            if not self.current_connection.profile.readonly:
                self.detail_walker.append(urwid.Divider())
                delete_btn = urwid.Button('Delete Key', on_press=lambda b: self.delete_key(key))
                self.detail_walker.append(
                    urwid.AttrMap(delete_btn, 'button_danger', 'button_focus')
                )

        except Exception as e:
            self.set_status(f"Error displaying key: {e}", 'error')
            logger.error(f"Error displaying key {key}: {e}")
            self.detail_walker[:] = [
                urwid.Text(('error', f'Error: {str(e)}'))
            ]

    def delete_key(self, key: bytes):
        """Удаление ключа"""
        if not self.current_connection:
            return

        try:
            client = self.current_connection.active_client
            deleted = client.delete(key)

            if deleted:
                self.set_status(f"Key deleted", 'success')
            else:
                self.set_status(f"Key not found", 'warning')

            self.refresh_keys()
            self.detail_walker[:] = []

        except Exception as e:
            self.set_status(f"Delete failed: {e}", 'error')
            logger.error(f"Delete failed for key {key}: {e}")

    def update_tabs(self):
        """Обновление табов"""
        tabs = []

        if self.current_connection and self.current_connection.connected:
            name = self.current_connection.profile.name

            if self.current_connection.is_cluster:
                try:
                    client = self.current_connection.active_client
                    cluster_info = client.cluster_info()
                    state = cluster_info.get('cluster_state', 'unknown')

                    if state == 'ok':
                        icon = '🟢'
                        style = 'success'
                    else:
                        icon = '🔴'
                        style = 'error'

                    label = f" {icon} {name} [Cluster] "
                    tabs.append((style, label))

                except Exception as e:
                    label = f" ⚠ {name} [Cluster] "
                    tabs.append(('warning', label))
            else:
                db = self.current_connection.current_db
                label = f" ● {name} [DB{db}] "
                tabs.append(('tab_active', label))

        self.tab_text.set_text(tabs if tabs else '')

    def show_add_key_dialog(self):
        """