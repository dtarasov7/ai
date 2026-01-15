# Redis Commander TUI - Руководство пользователя

## Версия 1.1.0

---

## Содержание

1. [Введение](#введение)
2. [Установка и запуск](#установка-и-запуск)
3. [Конфигурация подключений](#конфигурация-подключений)
4. [Интерфейс пользователя](#интерфейс-пользователя)
5. [Работа с ключами](#работа-с-ключами)
6. [Консоль Redis](#консоль-redis)
7. [Горячие клавиши](#горячие-клавиши)
8. [Режимы безопасности](#режимы-безопасности)
9. [FAQ](#faq)

---

## Введение

**Redis Commander TUI** — это терминальный пользовательский интерфейс для управления Redis и Redis Cluster. Программа предоставляет удобный способ просмотра, редактирования и управления данными в Redis без необходимости использования командной строки.

### Основные возможности

- ✅ Поддержка **Redis Standalone** и **Redis Cluster**
- ✅ Множественные профили подключений
- ✅ Просмотр и редактирование всех типов данных Redis
- ✅ Интерактивная консоль для выполнения команд
- ✅ Фильтрация и массовые операции с ключами
- ✅ Три режима безопасности (plaintext, encrypted, Vault)
- ✅ История команд
- ✅ Визуальная навигация по базам данных

---

## Установка и запуск

### Требования

```bash
Python 3.7+
pip install urwid redis cryptography
```

Для работы с зашифрованными конфигурациями:
```bash
pip install cryptography
```

Для работы с HashiCorp Vault:
```bash
pip install hvac
```

### Запуск программы

#### Режим 1: Обычный файл конфигурации (по умолчанию)

```bash
python redis_commander_tui-v1.1.0.py
# или
python redis_commander_tui-v1.1.0.py -c /path/to/config.json
```

#### Режим 2: Зашифрованный файл

```bash
python redis_commander_tui-v1.1.0.py -e encrypted_config.enc
# Программа запросит пароль для расшифровки
```

#### Режим 3: HashiCorp Vault

```bash
python redis_commander_tui-v1.1.0.py \
  --vault-url http://vault.example.com:8200 \
  --vault-path secret/data/redis-commander
# Программа запросит username и password для Vault
```

---

## Конфигурация подключений

### Формат файла конфигурации

Создайте файл `redis_profiles.json`:

```json
{
  "localhost": {
    "name": "localhost",
    "host": "localhost",
    "port": 6379,
    "password": null,
    "ssl": false,
    "readonly": false,
    "cluster_mode": false
  },
  "production_cluster": {
    "name": "production_cluster",
    "host": "redis-node1.prod.com",
    "port": 7000,
    "password": "secret_password",
    "ssl": true,
    "ssl_ca_certs": "/path/to/ca.pem",
    "cluster_mode": true,
    "cluster_nodes": [
      ["redis-node1.prod.com", 7000],
      ["redis-node2.prod.com", 7001],
      ["redis-node3.prod.com", 7002]
    ]
  },
  "unix_socket": {
    "name": "local_socket",
    "socket_path": "/var/run/redis/redis.sock",
    "cluster_mode": false
  }
}
```

### Параметры профиля

| Параметр | Тип | Описание |
|----------|-----|----------|
| `name` | string | Имя профиля |
| `host` | string | Хост Redis сервера |
| `port` | integer | Порт (по умолчанию 6379) |
| `password` | string/null | Пароль для аутентификации |
| `username` | string/null | Имя пользователя (Redis 6+) |
| `ssl` | boolean | Использовать SSL/TLS |
| `ssl_ca_certs` | string | Путь к CA сертификату |
| `ssl_certfile` | string | Путь к клиентскому сертификату |
| `ssl_keyfile` | string | Путь к приватному ключу |
| `socket_path` | string | Путь к Unix socket |
| `readonly` | boolean | Режим только для чтения |
| `cluster_mode` | boolean | Redis Cluster режим |
| `cluster_nodes` | array | Список узлов кластера |

### Создание зашифрованной конфигурации

Используйте отдельный скрипт `encryptor.py`:

```python
# encryptor.py
import json
import getpass
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import os

# Загружаем plaintext конфиг
with open('redis_profiles.json', 'r') as f:
    config = json.load(f)

# Запрашиваем пароль
password = getpass.getpass("Enter encryption password: ")
salt = os.urandom(16)

# Генерируем ключ
kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=salt,
    iterations=100000,
    backend=default_backend()
)
key = base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))

# Шифруем
f = Fernet(key)
encrypted_data = f.encrypt(json.dumps(config).encode('utf-8'))

# Сохраняем: salt + encrypted_data
with open('redis_profiles.enc', 'wb') as out:
    out.write(salt + encrypted_data)

print("✓ Config encrypted successfully")
```

---

## Интерфейс пользователя

### Структура экрана

```
┌─────────────────────────────────────────────────────────────┐
│ ● Redis Commander TUI                           [Header]    │
├─────────────────────────────────────────────────────────────┤
│ [F1: Help] [F2: Commands] [F3: Add] [F4: Edit] [F8: Del]   │
├──────────────────────┬──────────────────────────────────────┤
│ Connections & Keys   │ Details                              │
│                      │                                      │
│ ● localhost         │ Key: user:1001                       │
│   ▪ DB0 (1234 keys) │ Type: hash                           │
│   ▫ DB1             │ TTL: No expiration                   │
│                      │                                      │
│ [St] user:1001      │ Value:                               │
│ [Hs] session:abc    │   name: John Doe                     │
│ [Li] queue:tasks    │   email: john@example.com            │
│                      │   age: 30                            │
├──────────────────────┴──────────────────────────────────────┤
│ ● localhost [DB0]                              [Status Bar] │
│ Loaded 1234 keys                                            │
└─────────────────────────────────────────────────────────────┘
```

### Панели

1. **Левая панель** - Дерево подключений и список ключей
2. **Правая панель** - Детальная информация о выбранном ключе
3. **Консоль** (F2) - Интерактивная консоль Redis команд

### Индикаторы

- `●` - Активное подключение
- `○` - Неактивное подключение
- `▪` - Текущая база данных
- `▫` - Другая база данных
- `[St]` - String
- `[Hs]` - Hash
- `[Li]` - List
- `[Se]` - Set
- `[Zs]` - Sorted Set
- `✓` - Отмеченный ключ

---

## Работа с ключами

### Просмотр ключей

1. Выберите подключение в левой панели
2. Выберите базу данных (DB0, DB1, ...)
3. Ключи отобразятся автоматически
4. Нажмите **Enter** на ключе для просмотра деталей

### Добавление нового ключа

**Клавиша: F3**

1. Нажмите **F3**
2. Заполните форму:
   - **Key** - имя ключа
   - **Type** - выберите тип (String, Hash, List, Set, ZSet, Bitmap, Stream)
   - **Value** - введите значение в соответствии с типом
   - **TTL** - время жизни в секундах (опционально)
3. Нажмите **F7** (Save) или **Esc** (Cancel)

#### Форматы значений по типам

**String:**
```
Любой текст или JSON
Многострочный текст поддерживается
```

**Hash:**
```
field1:value1
field2:value2
field3:value3
```

**List:**
```
item1
item2
item3
```

**Set:**
```
member1
member2
member3
```

**ZSet:**
```
member1:1.0
member2:2.5
member3:10.0
```

**Bitmap:**
```
0:1
1:0
100:1
```

**Stream:**
```
field1:value1
field2:value2
```

### Редактирование ключа

**Клавиша: F4**

1. Выберите ключ в списке
2. Нажмите **F4**
3. Измените значение
4. Сохраните **F7**

### Удаление ключей

#### Одиночное удаление

1. Просмотрите детали ключа
2. Нажмите кнопку **Delete Key** внизу панели деталей
3. Подтвердите удаление

#### Массовое удаление

1. Отметьте ключи клавишей **Пробел**
2. Нажмите **F8**
3. Подтвердите удаление

### Фильтрация ключей

**Клавиша: /**

1. Нажмите **/**
2. Введите паттерн:
   - `user:*` - все ключи начинающиеся с "user:"
   - `*session*` - все ключи содержащие "session"
   - `temp:?123` - temp:a123, temp:b123 и т.д.
3. Нажмите **Apply**

### Массовая отметка

**Ctrl+A** - Отметить по паттерну  
**Ctrl+U** - Снять все отметки  
**Пробел** - Переключить отметку на текущем элементе

---

## Консоль Redis

### Открытие консоли

**Клавиша: F2**

Консоль отображается в правой части экрана или занимает нижнюю панель.

### Выполнение команд

```
redis> SET mykey "Hello"
OK

redis> GET mykey
"Hello"

redis> KEYS user:*
1) "user:1001"
2) "user:1002"
3) "user:1003"

redis> HGETALL user:1001
1) "name" => "John Doe"
2) "email" => "john@example.com"
```

### Навигация по истории

- **Page Up** (Ctrl+P) - Предыдущая команда
- **Page Down** (Ctrl+N) - Следующая команда

### Специальные команды консоли

- `exit` или `quit` - Закрыть консоль
- `clear` - Очистить историю консоли

### Поддержка Redis Cluster

Консоль автоматически адаптируется к режиму кластера:

```
redis> CLUSTER INFO
cluster_state: ok
cluster_known_nodes: 6

redis> KEYS *
# Сканирует все мастер-ноды автоматически

redis> DBSIZE
# Суммирует размер всех мастер-нод
```

**Ограничения в кластере:**
- Команда `SELECT` не поддерживается (только DB0)
- Мульти-ключевые операции требуют одного хэш-слота

---

## Горячие клавиши

### Основные

| Клавиша | Действие |
|---------|----------|
| **F1** или **?** | Справка |
| **F2** | Переключить консоль |
| **F3** | Добавить новый ключ |
| **F4** | Редактировать ключ |
| **F8** | Удалить отмеченные ключи |
| **F9** | Отключиться от сервера |
| **F10** | Выход из программы |
| **F11** | Обновить список ключей |
| **Q** | Выход (не в консоли) |
| **Tab** | Переключение между панелями |
| **Esc** | Закрыть консоль/диалог |

### Работа со списком ключей

| Клавиша | Действие |
|---------|----------|
| **Enter** | Просмотреть детали ключа |
| **Пробел** | Отметить/снять отметку |
| **/** | Открыть фильтр |
| **Ctrl+A** | Отметить по паттерну |
| **Ctrl+U** | Снять все отметки |
| **↑** / **↓** | Навигация по списку |

### Консоль

| Клавиша | Действие |
|---------|----------|
| **Enter** | Выполнить команду |
| **Page Up** | Предыдущая команда из истории |
| **Page Down** | Следующая команда из истории |
| **Esc** | Закрыть консоль |

---

## Режимы безопасности

### Режим 1: Plaintext конфигурация

**Использование:**
```bash
python redis_commander_tui-v1.1.0.py -c redis_profiles.json
```

**Безопасность:**
- ⚠️ Пароли хранятся в открытом виде
- ✅ Подходит для локальной разработки
- ⚠️ НЕ рекомендуется для продакшена

---

### Режим 2: Зашифрованная конфигурация

**Создание:**
```bash
python encryptor.py
# Введите пароль
# Создастся redis_profiles.enc
```

**Использование:**
```bash
python redis_commander_tui-v1.1.0.py -e redis_profiles.enc
Enter decryption password: ********
```

**Безопасность:**
- ✅ Пароли защищены шифрованием AES
- ✅ Используется PBKDF2 для деривации ключа
- ✅ Подходит для продакшена
- ⚠️ Требует надежного мастер-пароля

---

### Режим 3: HashiCorp Vault

**Настройка Vault:**
```bash
# Включите userpass auth
vault auth enable userpass

# Создайте пользователя
vault write auth/userpass/users/redis-admin password=secure_password

# Сохраните конфигурацию
vault kv put secret/redis-commander @redis_profiles.json
```

**Использование:**
```bash
python redis_commander_tui-v1.1.0.py \
  --vault-url https://vault.company.com:8200 \
  --vault-path secret/data/redis-commander

Vault username: redis-admin
Vault password: ********
```

**Безопасность:**
- ✅ Централизованное управление секретами
- ✅ Аудит доступа
- ✅ Ротация паролей
- ✅ Рекомендуется для enterprise

---

## FAQ

### Как работать с Redis Cluster?

В конфигурации укажите `"cluster_mode": true` и список узлов:

```json
{
  "cluster_mode": true,
  "cluster_nodes": [
    ["node1.example.com", 7000],
    ["node2.example.com", 7001]
  ]
}
```

Программа автоматически обнаружит остальные узлы и правильно маршрутизирует команды.

---

### Ограничения по количеству ключей?

Да, для производительности установлено ограничение **5000 ключей** при сканировании. Используйте фильтры для работы с большими базами.

---

### Как переключаться между базами данных?

В **Standalone режиме**: Кликните на DB0, DB1... в левой панели.  
В **Cluster режиме**: Доступна только DB0 (ограничение Redis Cluster).

---

### Можно ли редактировать бинарные данные?

Программа показывает бинарные данные как `<binary data: N bytes>`. Редактирование бинарных данных не поддерживается в текущей версии.

---

### История команд сохраняется?

Да, последние **100 команд** сохраняются в `~/.redis_commander_history` и доступны после перезапуска.

---

### Как работает режим только для чтения?

Установите `"readonly": true` в профиле. В этом режиме:
- Кнопки удаления/редактирования скрыты
- Модифицирующие команды не блокируются (контроль на стороне Redis)

---

### Поддержка SSL/TLS?

Да, укажите в конфигурации:

```json
{
  "ssl": true,
  "ssl_ca_certs": "/path/to/ca.pem",
  "ssl_certfile": "/path/to/client-cert.pem",
  "ssl_keyfile": "/path/to/client-key.pem"
}
```

---

## Логи и отладка

Логи записываются в `redis_tui_audit.log`:

```bash
tail -f redis_tui_audit.log
```

Уровень логирования: **INFO**  
Включает: подключения, выполненные команды, ошибки.

---

## Обратная связь

**Автор:** Тарасов Дмитрий  
**Версия:** 1.1.0  
**Лицензия:** MIT

Для сообщений об ошибках и предложений используйте issue tracker проекта.
