# Redis Commander TUI - Документация разработчика

## Версия 1.1.0

---

## Содержание

1. [Архитектура](#архитектура)
2. [Структура кода](#структура-кода)
3. [Основные компоненты](#основные-компоненты)
4. [Работа с данными](#работа-с-данными)
5. [Расширение функционала](#расширение-функционала)
6. [Тестирование](#тестирование)
7. [Производительность](#производительность)
8. [Известные проблемы](#известные-проблемы)

---

## Архитектура

### Общая структура

```
┌─────────────────────────────────────────────────┐
│           RedisCommanderUI (Main)               │
│  - EventLoop (urwid.MainLoop)                   │
│  - Палитра цветов                               │
│  - Обработчики событий                          │
└────────────┬────────────────────────────────────┘
             │
       ┌─────┴──────┬──────────────┬──────────────┐
       │            │              │              │
┌──────▼──────┐ ┌──▼─────────┐ ┌──▼──────────┐ ┌─▼────────────┐
│ Connection  │ │ KeyListView│ │ AddKeyDialog│ │ Console      │
│ Management  │ │            │ │             │ │ Interface    │
└──────┬──────┘ └──┬─────────┘ └──┬──────────┘ └─┬────────────┘
       │           │              │              │
┌──────▼──────┐ ┌──▼─────────┐ ┌──▼──────────┐ ┌─▼────────────┐
│ Redis       │ │ KeyListItem│ │ Validation  │ │ Command      │
│ Connection  │ │            │ │             │ │ History      │
└─────────────┘ └────────────┘ └─────────────┘ └──────────────┘
```

### Паттерны проектирования

1. **MVC (Model-View-Controller)**
   - Model: `RedisConnection`, `ConnectionProfile`
   - View: Urwid виджеты (`KeyListView`, `AddKeyDialog`)
   - Controller: `RedisCommanderUI`

2. **Observer Pattern**
   - Использование urwid signals для событий
   - `urwid.connect_signal()` для подписки

3. **Strategy Pattern**
   - Разные стратегии загрузки конфигурации (plaintext, encrypted, Vault)
   - Методы `_load_plaintext_config()`, `_load_encrypted_config()`, `_load_from_vault()`

4. **Singleton**
   - Один экземпляр `RedisCommanderUI` на приложение

---

## Структура кода

### Основные классы

```python
# ============= Модели данных =============
class ConnectionProfile:
    """Профиль подключения к Redis"""
    - name, host, port
    - authentication (password, username)
    - ssl/tls параметры
    - cluster_mode, cluster_nodes

class RedisConnection:
    """Менеджер подключения"""
    - active_client (standalone или cluster)
    - connect(), disconnect()
    - select_db() (только standalone)

# ============= UI компоненты =============
class KeyListItem(urwid.WidgetWrap):
    """Элемент списка ключей"""
    - Отображение иконки типа
    - Поддержка отметки (marked)
    - Callback при выборе

class KeyListView(urwid.WidgetWrap):
    """Виртуализированный список ключей"""
    - Фильтрация (apply_filter)
    - Отметка (marked_keys)
    - Кэширование виджетов (key_cache)

class AddKeyDialog(urwid.WidgetWrap):
    """Диалог добавления/редактирования"""
    - Динамические виджеты по типу
    - Валидация данных
    - Подтверждение изменений

class ScrollBar(urwid.WidgetWrap):
    """Индикатор прокрутки"""
    - Визуальный скроллбар
    - Стрелки вверх/вниз

class CommandPromptWrapper(urwid.WidgetWrap):
    """Обёртка для консольного промпта"""
    - История команд (↑/↓)
    - Callback для Enter

# ============= Главный класс =============
class RedisCommanderUI:
    """Главное приложение"""
    - Управление подключениями
    - Построение UI
    - Обработка событий
```

---

## Основные компоненты

### 1. Система подключений

#### ConnectionProfile

```python
profile = ConnectionProfile(
    name='prod_cluster',
    host='redis-node1.prod',
    port=7000,
    cluster_mode=True,
    cluster_nodes=[
        ('redis-node1.prod', 7000),
        ('redis-node2.prod', 7001),
        ('redis-node3.prod', 7002)
    ]
)
```

**Ключевые атрибуты:**
- `cluster_mode` (bool) - Режим кластера
- `cluster_nodes` (List[Tuple[str, int]]) - Список узлов
- `readonly` (bool) - Режим только для чтения

#### RedisConnection

```python
conn = RedisConnection(profile)
success, message = conn.connect()

if success:
    client = conn.active_client  # redis.Redis или RedisClient
    
    # Standalone
    if not conn.is_cluster:
        conn.select_db(1)
    
    # Cluster
    else:
        keys = conn.active_client.keys('*')
```

**Важно:**
- `active_client` возвращает правильный клиент (standalone/cluster)
- `is_cluster` - флаг для проверки режима
- `select_db()` работает только в standalone

---

### 2. Виртуализированный список ключей

#### Архитектура KeyListView

```python
class KeyListView:
    all_keys: List[Tuple[bytes, str]]      # Все ключи
    filtered_keys: List[Tuple[bytes, str]]  # После фильтра
    marked_keys: Set[bytes]                 # Отмеченные
    key_cache: Dict[bytes, KeyListItem]     # Кэш виджетов
    walker: SimpleFocusListWalker           # Urwid walker
```

**Оптимизация:**
1. **Кэширование виджетов** - создаём KeyListItem только один раз
2. **Ленивая загрузка** - виджеты создаются по мере необходимости
3. **Фильтрация** - не пересоздаём виджеты, используем кэш

**Пример использования:**

```python
# Установка ключей
keys_with_types = [
    (b'user:1001', 'hash'),
    (b'session:abc', 'string'),
    (b'queue:tasks', 'list')
]
key_list_view.set_keys(keys_with_types)

# Фильтрация
key_list_view.apply_filter('user:*')

# Отметка
key_list_view.mark_by_pattern('session:*')
marked = key_list_view.get_marked_keys()
```

---

### 3. Система событий

#### Urwid Signals

```python
# В KeyListView
signals = ['key_selected']

# Эмиссия события
urwid.emit_signal(self, 'key_selected', key)

# В RedisCommanderUI
urwid.connect_signal(
    self.key_list_view, 
    'key_selected', 
    self.on_key_select
)

def on_key_select(self, key: bytes):
    self.current_key = key
    self.display_key_details(key)
```

**Важные события:**
- `key_selected` - выбран ключ
- `close` - закрытие диалога

---

### 4. Консольный интерфейс

#### История команд

```python
class RedisCommanderUI:
    command_history: List[str]  # Все команды
    history_index: int          # Текущая позиция (-1 = новая)
    current_input: str          # Временное хранение ввода
```

**Навигация:**

```python
def navigate_history(self, direction: str):
    if direction == 'up':
        # Сохраняем текущий ввод при первом нажатии
        if self.history_index == -1:
            self.current_input = self.command_prompt.get_edit_text()
        
        # Переход к предыдущей команде
        if self.history_index == -1:
            self.history_index = len(self.command_history) - 1
        elif self.history_index > 0:
            self.history_index -= 1
    
    elif direction == 'down':
        # Переход к следующей команде
        if self.history_index < len(self.command_history) - 1:
            self.history_index += 1
        else:
            # Восстанавливаем текущий ввод
            self.history_index = -1
            self.command_prompt.set_edit_text(self.current_input)
            return
    
    # Установка текста из истории
    command = self.command_history[self.history_index]
    self.command_prompt.set_edit_text(command)
```

**Персистентность:**
- История сохраняется в `~/.redis_commander_history`
- Последние 100 команд
- Автозагрузка при старте

---

### 5. Работа с Redis Cluster

#### Сканирование ключей

```python
def _scan_cluster_keys_with_types_iter(self, client):
    keys_with_types = []
    
    if client.is_cluster and client.cluster_nodes:
        # Сканируем каждый master node
        for node_id, node_conn in client.cluster_nodes.items():
            cursor = 0
            
            while True:
                # SCAN на конкретном узле
                cursor, keys = self._scan_node(
                    node_conn, cursor, 
                    match='*', count=100
                )
                
                for key in keys:
                    # Получаем тип через правильный узел
                    key_type = client.type(key)
                    keys_with_types.append((key, key_type))
                
                if cursor == 0:
                    break
    
    return keys_with_types
```

**Особенности кластера:**
1. Нет команды SELECT (только DB0)
2. Мульти-ключевые операции требуют одного хэш-слота
3. SCAN выполняется на каждом master node отдельно
4. Автоматическая маршрутизация команд по слотам

#### Обработка ошибок кластера

```python
try:
    result = client.execute_command('SET', key, value)
except RedisClusterError as e:
    if 'CROSSSLOT' in str(e):
        # Ключи в разных слотах
        self.set_status("Keys must be in same slot")
    elif 'MOVED' in str(e):
        # Ключ переместился на другой узел
        self.set_status("Key moved to another node")
```

---

## Работа с данными

### Типы данных Redis

#### 1. String

```python
# Создание
client.set(key, value)

# Чтение
value = client.get(key)

# В диалоге AddKeyDialog
# Многострочный текст → заменяем \n на \\n
final_value = '\\n'.join(value.split('\n'))
client.set(key, final_value)
```

#### 2. Hash

```python
# Создание
pairs = {
    'field1': 'value1',
    'field2': 'value2'
}
client.hset(key, mapping=pairs)

# Чтение
hash_data = client.hgetall(key)

# Отображение в UI
for field, val in hash_data.items():
    field_str = field.decode('utf-8', errors='replace')
    val_str = val.decode('utf-8', errors='replace')
    self.detail_walker.append(
        urwid.Columns([
            ('weight', 1, urwid.Text(field_str)),
            ('weight', 2, urwid.Text(val_str))
        ])
    )
```

#### 3. List

```python
# Создание
items = ['item1', 'item2', 'item3']
client.rpush(key, *items)

# Чтение (первые 100)
list_data = client.lrange(key, 0, 99)

# Вставка формата в диалоге
"""
item1
item2
item3
"""
```

#### 4. Set

```python
# Создание
members = ['member1', 'member2', 'member3']
client.sadd(key, *members)

# Чтение
set_data = client.smembers(key)
```

#### 5. Sorted Set (ZSet)

```python
# Создание
pairs = {
    'member1': 1.0,
    'member2': 2.5,
    'member3': 10.0
}
client.zadd(key, pairs)

# Чтение
zset_data = client.zrange(key, 0, 99, withscores=True)

# Формат в диалоге: member:score
"""
member1:1.0
member2:2.5
member3:10.0
"""
```

#### 6. Bitmap

```python
# Создание пустой строки
client.set(key, '')

# Установка битов
client.execute_command('SETBIT', key, offset, bit, key=key)

# Формат в диалоге: offset:bit
"""
0:1
1:0
100:1
"""
```

#### 7. Stream

```python
# Добавление записи
args = [key, '*', 'field1', 'value1', 'field2', 'value2']
client.execute_command('XADD', *args, key=key)

# Формат в диалоге: field:value
"""
field1:value1
field2:value2
"""
```

---

## Расширение функционала

### Добавление нового типа данных

1. **Добавить в type_icons (KeyListItem):**

```python
type_icons = {
    'string': '[St]',
    'hash': '[Hs]',
    'mytype': '[Mt]',  # Новый тип
}
```

2. **Добавить RadioButton (AddKeyDialog):**

```python
urwid.RadioButton(
    self.type_group, 
    'MyType',
    on_state_change=lambda btn, state: 
        self.on_type_changed(btn, state, 'mytype')
)
```

3. **Реализовать виджет ввода:**

```python
def update_value_widget(self, key_type):
    if key_type == 'mytype':
        help_text = urwid.Text('Enter mytype format')
        self.value_edit = urwid.AttrMap(
            urwid.Edit('', multiline=True),
            'input', 'input_focus'
        )
        self.value_container.contents.extend([
            (help_text, ('pack', None)),
            (urwid.LineBox(self.value_edit), ('weight', 1))
        ])
```

4. **Реализовать сохранение:**

```python
def on_save(self, button):
    # ...
    elif key_type == 'mytype':
        value = self.get_value_text()
        # Парсинг и сохранение
        client.execute_command('MYTYPE.SET', key, value)
```

5. **Реализовать отображение:**

```python
def display_key_details(self, key):
    # ...
    elif key_type == 'mytype':
        value = client.execute_command('MYTYPE.GET', key)
        self.detail_walker.append(urwid.Text(value))
```

---

### Добавление нового режима безопасности

```python
# В load_profiles()
def load_profiles(self):
    if self.args.new_vault_provider:
        profiles_data = self._load_from_new_provider()
    # ...
    
    return self._parse_profiles(profiles_data)

def _load_from_new_provider(self):
    """Загрузка из нового провайдера"""
    # Реализация
    return profiles_dict
```

**Аргументы командной строки:**

```python
parser.add_argument(
    '--new-vault-provider',
    help='URL нового провайдера'
)
parser.add_argument(
    '--new-vault-token',
    help='Токен доступа'
)
```

---

### Кастомизация UI

#### Изменение цветовой схемы

```python
palette = [
    ('header', 'white', 'dark blue', 'bold'),
    ('footer', 'white', 'dark green'),  # Изменено
    ('key_item', 'yellow', 'black'),     # Изменено
    # ...
]
```

#### Добавление новой панели

```python
# Создание виджета
self.new_panel = urwid.LineBox(
    urwid.ListBox(urwid.SimpleListWalker([])),
    title='New Panel'
)

# Добавление в layout
content = urwid.Columns([
    ('weight', 1, self.left_panel),
    ('weight', 1, self.right_panel),
    ('weight', 1, self.new_panel),  # Новая панель
], dividechars=1)
```

---

## Тестирование

### Unit тесты

```python
import unittest
from redis_commander_tui import ConnectionProfile, RedisConnection

class TestConnectionProfile(unittest.TestCase):
    def test_standalone_profile(self):
        profile = ConnectionProfile(
            name='test',
            host='localhost',
            port=6379
        )
        self.assertEqual(profile.cluster_mode, False)
    
    def test_cluster_profile(self):
        profile = ConnectionProfile(
            name='cluster',
            host='node1',
            port=7000,
            cluster_mode=True,
            cluster_nodes=[
                ('node1', 7000),
                ('node2', 7001)
            ]
        )
        self.assertEqual(profile.cluster_mode, True)
        self.assertEqual(len(profile.cluster_nodes), 2)

class TestRedisConnection(unittest.TestCase):
    def test_connect_standalone(self):
        profile = ConnectionProfile('test', 'localhost', 6379)
        conn = RedisConnection(profile)
        success, msg = conn.connect()
        self.assertTrue(success)
        self.assertIsNotNone(conn.client)
        conn.disconnect()
```

### Интеграционные тесты

```python
class TestRedisCluster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Запуск локального кластера для тестов
        cls.cluster = start_test_cluster()
    
    def test_cluster_scan(self):
        profile = ConnectionProfile(
            'test_cluster',
            'localhost', 7000,
            cluster_mode=True
        )
        conn = RedisConnection(profile)
        conn.connect()
        
        # Добавляем тестовые ключи
        client = conn.active_client
        for i in range(100):
            client.set(f'test:{i}', f'value_{i}')
        
        # Сканируем
        keys = list(client.scan_iter(match='test:*'))
        self.assertEqual(len(keys), 100)
```

---

## Производительность

### Узкие места

1. **SCAN больших баз:**
   - Ограничение: 5000 ключей
   - Решение: Использовать фильтры, увеличить count в SCAN

2. **Отрисовка списка:**
   - Проблема: Создание виджетов занимает время
   - Решение: Кэширование в `key_cache`

3. **Cluster SCAN:**
   - Проблема: Последовательное сканирование узлов
   - Решение: Можно распараллелить через `concurrent.futures`

### Оптимизации

#### 1. Параллельное сканирование кластера

```python
from concurrent.futures import ThreadPoolExecutor

def _scan_cluster_parallel(self, client):
    keys_with_types = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        
        for node_id, node_conn in client.cluster_nodes.items():
            future = executor.submit(
                self._scan_single_node, 
                node_conn
            )
            futures.append(future)
        
        for future in futures:
            node_keys = future.result()
            keys_with_types.extend(node_keys)
    
    return keys_with_types
```

#### 2. Ленивая загрузка деталей

```python
def display_key_details(self, key: bytes):
    # Показываем базовую информацию сразу
    self.detail_walker[:] = [
        urwid.Text(f'Key: {key.decode()}'),
        urwid.Text('Loading...')
    ]
    
    # Асинхронная загрузка значения
    def load_value():
        value = self.current_connection.active_client.get(key)
        self.loop.draw_screen()  # Перерисовка
    
    import threading
    threading.Thread(target=load_value).start()
```

#### 3. Виртуализация списка (будущее)

Для работы с миллионами ключей - реализовать истинную виртуализацию:
- Загружать только видимые элементы
- Динамически подгружать при прокрутке

---

## Известные проблемы

### 1. Redis Cluster: THREE.CapsuleGeometry

**Проблема:**
```python
# НЕ РАБОТАЕТ в кластере
import * as THREE from 'three'
geometry = new THREE.CapsuleGeometry(1, 1, 4, 8)
```

**Причина:** CapsuleGeometry добавлена в r142, доступна только r128

**Решение:**
```python
# Используйте альтернативы
geometry = new THREE.CylinderGeometry(0.5, 0.5, 2, 32)
# или
geometry = new THREE.SphereGeometry(1, 32, 16)
```

---

### 2. Encoding issues

**Проблема:** Некоторые ключи содержат невалидный UTF-8

**Решение:**
```python
key_str = key.decode('utf-8', errors='replace')
# 'replace' заменяет невалидные байты на �
```

---

### 3. CROSSSLOT errors в кластере

**Проблема:**
```python
# Ошибка: keys must be in same hash slot
client.mget(['user:1001', 'session:abc'])
```

**Решение:** Используйте хэш-теги
```python
client.mget(['{user}:1001', '{user}:2002'])
```

---

### 4. Медленная загрузка при большом количестве ключей

**Временное решение:**
- Ограничение 5000 ключей
- Используйте фильтры

**Долгосрочное решение:**
- Реализовать пагинацию
- Виртуализировать список

---

## Best Practices

### 1. Обработка ошибок

```python
try:
    result = client.execute_command('GET', key)
except RedisClusterError as e:
    # Специфичные ошибки кластера
    logger.error(f"Cluster error: {e}")
    self.set_status(f"Cluster error: {e}", 'error')
except RedisConnectionError as e:
    # Проблемы с подключением
    logger.error(f"Connection error: {e}")
    self.set_status("Connection lost", 'error')
except RedisError as e:
    # Общие Redis ошибки
    logger.error(f"Redis error: {e}")
    self.set_status(f"Error: {e}", 'error')
except Exception as e:
    # Неожиданные ошибки
    logger.exception("Unexpected error")
    self.set_status(f"Unexpected error: {e}", 'error')
```

### 2. Логирование

```python
# Важные события
logger.info(f"Connected to {host}:{port}")
logger.info(f"Executed: {command}")

# Ошибки
logger.error(f"Failed to connect: {error}")
logger.exception("Unexpected error")  # С traceback

# Отладка
logger.debug(f"Key cache size: {len(self.key_cache)}")
```

### 3. Работа с bytes и str

```python
# Redis возвращает bytes
key = b'user:1001'

# Декодирование для UI
key_str = key.decode('utf-8', errors='replace')

# Кодирование для Redis
client.get(key_str.encode('utf-8'))

# Или используйте decode_responses=False в клиенте
```

---

## Дорожная карта

### v1.2.0 (планируется)
- [ ] Пагинация списка ключей
- [ ] Экспорт/импорт ключей (JSON, CSV)
- [ ] Поддержка Redis Sentinel
- [ ] Графики статистики

### v1.3.0 (планируется)
- [ ] Pub/Sub мониторинг
- [ ] Lua скрипты
- [ ] Бенчмарки производительности
- [ ] Плагинная система

### v2.0.0 (будущее)
- [ ] Веб-интерфейс (опционально)
- [ ] Кластерная аналитика
- [ ] Автоматическая оптимизация
- [ ] ML-powered предсказания

---

## Вклад в проект

### Процесс

1. Fork репозитория
2. Создайте feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit изменения (`git commit -m 'Add AmazingFeature'`)
4. Push в branch (`git push origin feature/AmazingFeature`)
5. Откройте Pull Request

### Code Style

- **PEP 8** для Python кода
- **Type hints** для публичных методов
- **Docstrings** для классов и функций
- **Логирование** важных операций

```python
def connect_to_profile(self, profile: ConnectionProfile) -> None:
    """
    Подключение к профилю Redis.
    
    Args:
        profile: Профиль подключения
        
    Raises:
        RedisConnectionError: При ошибке подключения
    """
    # Реализация
```

---

## Лицензия

MIT License - см. LICENSE файл

**Автор:** Тарасов Дмитрий  
**Email:** [скрыто]  
**GitHub:** [ссылка на репозиторий]
