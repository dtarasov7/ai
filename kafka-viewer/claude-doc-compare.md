# Kafka Viewer - Полное описание функционала

## 📋 Текущий функционал

### 🔐 **1. Управление подключением**

#### Поддерживаемые методы аутентификации:
- **PLAINTEXT** - без шифрования
- **SSL** - TLS шифрование
- **SASL_PLAINTEXT** - SASL аутентификация без шифрования
- **SASL_SSL** - SASL + TLS

#### Поддерживаемые SASL механизмы:
- PLAIN
- SCRAM-SHA-256
- SCRAM-SHA-512

#### Методы загрузки конфигурации:
```bash
# 1. Обычный JSON файл
./kafka_viewer.py --config config.json

# 2. Зашифрованный конфиг (с паролем)
./kafka_viewer.py --encrypted-config secure.enc

# 3. HashiCorp Vault
./kafka_viewer.py --vault-url http://vault:8200 --vault-path secret/kafka

# 4. CLI аргументы
./kafka_viewer.py --bootstrap-servers localhost:9092 \
  --security-protocol SSL \
  --ssl-ca-file ca.pem
```

#### Поддержка mTLS (mutual TLS):
```python
# Клиентская аутентификация через сертификаты
--ssl-cert-file client.crt
--ssl-key-file client.key
--ssl-password key_password
```

---

### 📁 **2. Управление топиками**

#### Просмотр топиков:
- ✅ Список всех топиков (включая internal `__*`)
- ✅ Фильтрация по имени (substring, case-insensitive)
- ✅ Автообновление списка (R)

#### Создание топика (N):
```
Presets:
  - Manual (Custom)
  - Temporary Debug (24h, delete)
  - Short Lived (7 days, delete)
  - Compacted KV (Keys+Values)
  - High Durability (3 replicas)

Параметры:
  - num_partitions
  - replication_factor
  - cleanup.policy (delete|compact)
  - retention.ms
  - retention.bytes
  - segment.bytes
  - min.insync.replicas
  - compression.type
  - max.message.bytes
```

**Безопасность:**
- ❌ Запрет создания internal топиков (`__*`)
- ✅ Проверка infinite retention (требует `retention.bytes` при `retention.ms=-1`)

#### Удаление топика (F8):
- ✅ Подтверждение перед удалением
- ❌ Запрет удаления internal топиков

#### Информация о топике (F2):
```
Отображает:
  - Количество партиций
  - Replication factor
  - Общее количество записей
  - Список consumer groups
  - Полную конфигурацию топика
```

---

### 📨 **3. Просмотр сообщений**

#### Режимы загрузки:
```python
# Snapshot настройки (O)
snapshot_mode:
  - "tail" - последние N записей из каждой партиции
  - "from_beginning" - с начала

snapshot_tail_n = 500        # на партицию
snapshot_max_total = 5000    # лимит для всех партиций
```

#### Отображение:
```
Timestamp           Topic         Offset     Size    Key          Value
2024-01-24 10:30:45 orders[0]     12345      1.5K    user_123     {"order": ...}
```

**Колонки:**
- Timestamp (с миллисекундами)
- Topic[partition]
- Offset
- Size (B/KB/MB)
- Key (truncated)
- Value (truncated)

#### Автоподстройка под ширину терминала:
- Динамическое вычисление ширины колонок
- Адаптация при изменении размера окна

---

### 🔍 **4. Фильтрация и поиск**

#### Фильтрация топиков (F7 в списке топиков):
```
Filter mask: "order"
→ Показывает: orders, order-events, customer-orders
```

#### Фильтрация сообщений (F7 в списке сообщений):
```
Поля:
  - Key (substring)
  - Value (substring)
  - Partition (exact match)
  - Offset (exact match)

Логика: AND (все условия должны выполняться)
```

**Заголовок обновляется:**
```
Messages [Time↓] Filter: value:*error*, partition:*0*
```

---

### 📊 **5. Сортировка сообщений (S)**

```
Режимы:
  - Unsorted (по partition, offset - как пришло)
  - Timestamp (↑↓)
  - Partition (↑↓)
  - Size (↑↓)

Direction:
  - Ascending
  - Descending
```

**Индикатор в заголовке:**
```
Messages [Time↓]    # Сортировка по времени, descending
Messages [Part↑]    # По партиции, ascending
```

---

### 🔎 **6. Детальный просмотр сообщения (Enter)**

#### Режимы отображения (F4 переключение):

**TEXT режим:**
```
        Topic: orders
    Timestamp: 1706095845000 ms
     DateTime: 2024-01-24T10:30:45+01:00
    Published: 5 minutes ago
       Offset: 12345
    Partition: 0
         Size: 1.5 KB
          Key: user_123

        Value: (text, F4 toggle)
 {
   "order_id": "ORD-001",
   "amount": 99.99
 }
```

**HEX режим:**
```
        Value: (hex, F4 toggle)
 00000000  7b 22 6f 72 64 65 72 5f  69 64 22 3a 22 4f 52 44  |{"order_id":"ORD|
 00000010  2d 30 30 31 22 2c 22 61  6d 6f 75 6e 74 22 3a 39  |-001","amount":9|
 00000020  39 2e 39 39 7d                                    |9.99}|
```

**Авто-определение режима:**
- Если есть непечатные символы → HEX
- Иначе → TEXT

---

### 💾 **7. Экспорт сообщений (S в детальном просмотре)**

#### Форматы:

**1. Full Message Dump (JSON):**
```json
{
  "topic": "orders",
  "partition": 0,
  "offset": 12345,
  "timestamp": 1706095845000,
  "timestamp_iso": "2024-01-24T10:30:45",
  "key_str": "user_123",
  "value_json": {
    "order_id": "ORD-001"
  },
  "value_type": "json"
}
```

**Обработка разных типов value:**
```python
value_type:
  - "json"    → value_json (parsed)
  - "text"    → value_text + value_base64
  - "binary"  → value_base64 + "<binary data>"
```

**2. Raw Value Only (Binary):**
```bash
# Сохраняет чистые байты
msg_orders_0_12345.bin
```

**Фичи:**
- ✅ Автозаполнение имени файла: `msg_{topic}_{partition}_{offset}.json`
- ✅ Автосмена расширения при выборе формата
- ✅ Enter для быстрого сохранения

---

### 📬 **8. Отправка сообщений (P)**

```
Topic: orders

Key (optional): user_123

Value:
┌──────────────────────────┐
│ {"order_id": "ORD-002",  │
│  "amount": 149.99}       │
└──────────────────────────┘

[Send] [Cancel]
```

**Особенности:**
- ✅ Multiline редактор для value
- ✅ Optional key
- ✅ UTF-8 encoding
- ❌ Запрет отправки в internal топики (`__*`)
- ✅ Автообновление snapshot после отправки

---

### 👥 **9. Consumer Groups мониторинг (G)**

#### Обзор всех групп:
```
GROUP ID                      STATE      TOPICS  TOTAL LAG  MAX LAG (Topic)
my-service-consumer           Stable     3       15432      12000 (orders)
analytics-stream              Empty      1       0          0
dead-letter-processor         Dead       2       -          -
```

**Цветовая индикация:**
- 🟢 Зеленый - lag = 0
- 🟡 Желтый - lag > 0
- 🔴 Красный - lag > 10000
- ⚫ Серый - Empty/Dead

#### Детали группы (Enter):
```
Group: my-service-consumer | State: Stable | Total Lag: 15432

TOPIC                         PART    LAG        CURRENT      LOG-END
orders                        0       12000      100000       112000
orders                        1       3000       50000        53000
notifications                 0       432        25000        25432

[F9] Reset ALL topics | [F10] Reset Selected Topic
```

---

### 🔄 **10. Reset Consumer Offsets**

#### Стратегии сброса (F9 - все топики, F10 - выбранный):

**1. To Latest (Skip all):**
```python
# Переместить на конец (пропустить backlog)
new_offset = end_offset
```

**2. To Earliest (Replay all):**
```python
# Переместить в начало (обработать всё заново)
new_offset = beginning_offset
```

**3. By Duration:**
```
Examples:
  30m  → 30 минут назад
  2h   → 2 часа назад
  7d   → 7 дней назад

new_offset = offset_at(now - duration)
```

**4. Specific DateTime:**
```
ISO 8601 format:
  2024-01-24T12:00:00
  2024-01-24T12:00:00+01:00

new_offset = offset_at(datetime)
```

#### Процесс:

**Шаг 1 - Конфигурация:**
```
Reset Offsets for Group: my-consumer
Scope: ONLY topic 'orders'

Select Strategy:
  ○ To Latest
  ● By Duration
  ○ Specific DateTime

Duration: [1h]

[Preview] [Cancel]
```

**Шаг 2 - Dry Run:**
```
TOPIC          PART  OLD        NEW        CHANGE
orders         0     100000     99000      -1000
orders         1     50000      49500      -500

Scope: ONLY orders

[CONFIRM RESET] [Back]
```

**Шаг 3 - Execution:**
```python
# Попытка 1: Современный метод (Kafka 2.4+)
admin_client.alter_consumer_group_offsets(group_id, offsets)

# Fallback: Legacy метод
consumer = KafkaConsumer(group_id=group_id)
consumer.commit(offsets)
```

---

### 🔐 **11. ACL Management (F3, F4)**

#### F3 - ACL текущего топика:
```
Showing ACLs that apply to topic: orders
(includes LITERAL match, PREFIXED patterns, and wildcard '*')

Resource       Principal            Host         Operation       Perm    Pattern
orders         User:app-service     *            READ            ALLOW   Literal
orders         User:app-service     *            WRITE           ALLOW   Literal
ord*           User:admin           *            ALL             ALLOW   Prefixed
*              User:monitoring      192.168.1.5  DESCRIBE        ALLOW   Literal
```

**Логика сопоставления:**
```python
Matches topic "orders":
  1. LITERAL "orders"      → точное совпадение
  2. PREFIXED "ord"        → orders.startswith("ord")
  3. LITERAL "*"           → wildcard
  4. LITERAL "TOP*"        → обработка суффикса (нестандарт)
```

#### Фильтрация ACL (/):
```
Filter ACLs:

Principal (substring): [app-service]
Host (substring): [192.168]

Operation:
  ● ANY    ○ DESCRIBE
  ○ READ   ○ ALTER
  ○ WRITE  ...

Permission:
  ● ANY
  ○ ALLOW
  ○ DENY

Pattern Type:
  ● ANY
  ○ LITERAL
  ○ PREFIXED

[Apply] [Clear All] [Cancel]
```

#### F4 - Меню ресурсов:
```
Select resource type:

[1] Current Topic (orders)
[2] All Topics
[3] Consumer Groups           → выбор группы → ACL
[4] Cluster
[5] Transactional IDs         → ввод ID → ACL
[6] By Principal              → выбор principal → все ACL

[Cancel]
```

**Навигация по диалогам:**
```
Stack: [Main Menu] → [Groups Selection] → [Group ACLs]
Esc возвращает на предыдущий уровень
```

---

### ⌨️ **12. Горячие клавиши**

#### Глобальные:
```
Q         - Quit
Esc       - Close dialog / Exit
R         - Refresh topics
Tab       - Switch focus (topics ↔ messages)
←→        - Navigate panels
```

#### В списке топиков:
```
Enter     - Открыть топик
N         - New topic
F2        - Topic Info
F3        - Topic ACLs
F4        - ACL Resource Menu
F7        - Filter topics
F8        - Delete topic
G         - Consumer Groups Monitor
```

#### В списке сообщений:
```
Enter     - View message details
F7        - Filter messages
S         - Sort messages
O         - Offsets configuration
P         - Produce message
```

#### В детальном просмотре:
```
F4        - Toggle HEX/TEXT
S         - Save message
Esc/Q     - Close
```

#### В Consumer Groups:
```
Enter     - Group details
F9        - Reset ALL offsets
F10       - Reset selected topic
```

---

### 🎨 **13. UI/UX особенности**

#### Цветовая схема:
```python
palette = [
    ("body", "white", "dark blue"),
    ("footer", "white", "dark blue"),
    ("reversed", "black", "light cyan"),      # selected row
    ("header", "white,bold", "dark blue"),
    ("dialog_bg", "black", "light gray"),
    ("error", "light red", "black"),
    ("edit_field", "black", "dark cyan"),
]
```

#### Адаптивная ширина столбцов:
```python
def _reformat_messages(self, width):
    col_timestamp = 28
    col_topic = 13
    col_offset = 10
    col_size = 8
    col_key = 12
    col_value = max(20, width - col_timestamp - col_topic - ...)
```

#### Динамический статус-бар:
```
Topics | Profile: production | Topic: orders | SSL | Msg: 1234/5000 (p0@99999) | 
N:NewTopic G:Groups Enter:View F2:Info F3:ACL F4:ACLMenu F7:Filter S:Sort O:Offsets P:Produce R:Refresh Q:Quit
```

#### Прогресс индикаторы:
```
Loading...
Loading consumer groups analysis (this may take a moment)...
Calculating new offsets...
```

---

## 🆚 Сравнение с официальными Kafka CLI утилитами

### **kafka-topics.sh**

| Функция | kafka_viewer.py | kafka-topics.sh | Преимущество |
|---------|-----------------|-----------------|--------------|
| **Список топиков** | ✅ TUI + фильтр | `--list` | 🎯 **Viewer** - интерактивный фильтр в реальном времени |
| **Создание** | ✅ Presets + validation | `--create` с параметрами | 🎯 **Viewer** - шаблоны, защита от ошибок |
| **Удаление** | ✅ С подтверждением | `--delete` | 🎯 **Viewer** - случайное удаление сложнее |
| **Описание** | ✅ Красивый вывод | `--describe` (текст) | 🎯 **Viewer** - структурированное отображение |
| **Конфигурация** | ✅ Readable format | `--describe --config` | 🎯 **Viewer** - отформатировано в таблице |
| **Изменение конфига** | ❌ Нет | `--alter --config` | 🎯 **CLI** - больше опций |
| **Изменение партиций** | ❌ Нет | `--alter --partitions` | 🎯 **CLI** - единственный способ |

**Вывод:** Viewer лучше для просмотра и базового управления, CLI нужен для продвинутых операций.

---

### **kafka-console-consumer.sh**

| Функция | kafka_viewer.py | kafka-console-consumer.sh | Преимущество |
|---------|-----------------|---------------------------|--------------|
| **Чтение с начала** | ✅ Snapshot mode | `--from-beginning` | 🟰 **Равны** |
| **Чтение с конца** | ✅ Tail mode | По умолчанию | 🟰 **Равны** |
| **Фильтрация** | ✅ Интерактивная (key, value, partition) | ❌ Только через pipe + grep | 🎯 **Viewer** - встроенная фильтрация |
| **Форматирование** | ✅ JSON pretty-print автоматически | `--property print.key=true` | 🎯 **Viewer** - автоформат |
| **Hex dump** | ✅ F4 toggle | ❌ Нет | 🎯 **Viewer** - бинарные данные |
| **Поиск** | ✅ Filter + Sort | ❌ Только через grep | 🎯 **Viewer** - интерактивный поиск |
| **Экспорт** | ✅ JSON/Binary | ❌ Только stdout | 🎯 **Viewer** - структурированный экспорт |
| **Offset control** | ⚠️ Snapshot (не live seek) | `--partition --offset` | 🎯 **CLI** - точный контроль offset |
| **Consumer group** | ❌ Не использует group | `--group` | 🎯 **CLI** - для продакшена |
| **Streaming** | ❌ Snapshot only | ✅ Continuous | 🎯 **CLI** - для реального стриминга |

**Вывод:** 
- **Viewer** - для дебага, анализа снапшотов, визуального изучения
- **CLI** - для продакшен мониторинга, стриминга, скриптов

---

### **kafka-console-producer.sh**

| Функция | kafka_viewer.py | kafka-console-producer.sh | Преимущество |
|---------|-----------------|---------------------------|--------------|
| **Отправка сообщения** | ✅ P в TUI | `echo "msg"` + pipe | 🎯 **Viewer** - GUI форма |
| **Key + Value** | ✅ Отдельные поля | `--property parse.key=true` | 🎯 **Viewer** - удобнее |
| **Multiline** | ✅ Редактор | ❌ Сложно | 🎯 **Viewer** - встроенный редактор |
| **Batch send** | ❌ По одному | ✅ Из файла/stdin | 🎯 **CLI** - массовая отправка |
| **Headers** | ❌ Нет | ✅ `--property parse.headers=true` | 🎯 **CLI** |
| **Компрессия** | ✅ Из конфига | `--compression-codec` | 🟰 **Равны** |

**Вывод:** 
- **Viewer** - для ручных тестовых сообщений
- **CLI** - для скриптов, автоматизации, batch

---

### **kafka-consumer-groups.sh**

| Функция | kafka_viewer.py | kafka-consumer-groups.sh | Преимущество |
|---------|-----------------|--------------------------|--------------|
| **Список групп** | ✅ G → таблица | `--list` | 🎯 **Viewer** - визуальнее |
| **Описание группы** | ✅ Enter на группе | `--describe --group` | 🎯 **Viewer** - интерактивно |
| **Lag мониторинг** | ✅ Агрегированный + детальный | `--describe` | 🎯 **Viewer** - Total Lag, Max Lag, цвета |
| **Reset offsets** | ✅ Визард с 4 стратегиями | `--reset-offsets --to-*` | 🎯 **Viewer** - Dry Run preview, UI |
| **Delete group** | ❌ Нет | `--delete --group` | 🎯 **CLI** |
| **Members** | ⚠️ Частично | `--describe --members` | 🎯 **CLI** - детали членов |
| **State** | ✅ Показывает | `--describe --state` | 🟰 **Равны** |

**Вывод:** 
- **Viewer** - для визуального мониторинга lag, безопасного reset
- **CLI** - для скриптов, автоматизации, удаления групп

---

### **kafka-acls.sh**

| Функция | kafka_viewer.py | kafka-acls.sh | Преимущество |
|---------|-----------------|---------------|--------------|
| **Список ACL** | ✅ F3, F4 меню | `--list` | 🎯 **Viewer** - по типам ресурсов |
| **Фильтрация** | ✅ Интерактивная (/) | `--topic --principal` | 🎯 **Viewer** - live фильтр |
| **По топику** | ✅ + wildcard matching | `--topic orders` | 🎯 **Viewer** - показывает PREFIXED |
| **По группе** | ✅ Выбор из списка | `--group` | 🎯 **Viewer** - удобнее |
| **По principal** | ✅ Выбор из списка | `--principal User:*` | 🎯 **Viewer** - все ACL principal |
| **Создание ACL** | ❌ Нет | `--add --allow-principal` | 🎯 **CLI** - единственный способ |
| **Удаление ACL** | ❌ Нет | `--remove` | 🎯 **CLI** - единственный способ |
| **Pattern types** | ✅ Показывает LITERAL, PREFIXED | `--resource-pattern-type` | 🟰 **Равны** |

**Вывод:** 
- **Viewer** - для изучения, аудита, понимания ACL
- **CLI** - для изменения ACL (add/remove)

---

### **kafka-configs.sh**

| Функция | kafka_viewer.py | kafka-configs.sh | Преимущество |
|---------|-----------------|------------------|--------------|
| **Конфиг топика** | ✅ F2 → вся конфигурация | `--describe --entity-type topics` | 🎯 **Viewer** - форматирование |
| **Изменение конфига** | ⚠️ Только при создании | `--alter --add-config` | 🎯 **CLI** - изменение существующих |
| **Broker config** | ❌ Нет | `--entity-type brokers` | 🎯 **CLI** |
| **Dynamic config** | ❌ Нет | `--entity-type users/clients` | 🎯 **CLI** |

**Вывод:** CLI обязателен для управления конфигом после создания.

---

### **kafka-log-dirs.sh**

| Функция | kafka_viewer.py | kafka-log-dirs.sh | Преимущество |
|---------|-----------------|-------------------|--------------|
| **Размер топика на диске** | ❌ Нет | `--describe --topic-list` | 🎯 **CLI** |
| **Распределение партиций** | ❌ Нет | `--describe` | 🎯 **CLI** |

**Вывод:** CLI единственный инструмент.

---

### **kafka-metadata-shell.sh** (Kafka 3.3+)

| Функция | kafka_viewer.py | kafka-metadata-shell.sh | Преимущество |
|---------|-----------------|-------------------------|--------------|
| **KRaft metadata** | ❌ Нет | ✅ SQL-like queries | 🎯 **CLI** |

**Вывод:** Специализированный инструмент для KRaft.

---

## 🎯 Итоговая таблица: Когда использовать что?

| Задача | Kafka Viewer TUI | Kafka CLI | Причина |
|--------|------------------|-----------|---------|
| **Изучение структуры кластера** | 🏆 | ⭐ | Визуальная навигация |
| **Дебаг отдельных сообщений** | 🏆 | ⭐ | Hex viewer, pretty-print |
| **Поиск по содержимому** | 🏆 | ⭐⭐ | Интерактивный фильтр vs grep |
| **Мониторинг consumer lag** | 🏆 | ⭐⭐ | Агрегация, цвета, Total Lag |
| **Безопасный reset offsets** | 🏆 | ⭐ | Dry run preview, UI |
| **Изучение ACL** | 🏆 | ⭐ | Wildcard matching, фильтры |
| **Создание топика (разовое)** | 🏆 | ⭐ | Presets, validation |
| **Отправка тестового сообщения** | 🏆 | ⭐ | Multiline editor |
| | | | |
| **Streaming консьюминг** | ❌ | 🏆 | Viewer = snapshot only |
| **Batch отправка сообщений** | ❌ | 🏆 | CLI из файла/pipe |
| **Автоматизация (скрипты)** | ❌ | 🏆 | CLI + jq + bash |
| **Управление ACL (add/remove)** | ❌ | 🏆 | Viewer read-only |
| **Изменение конфига топика** | ❌ | 🏆 | Viewer только при создании |
| **Управление brokers** | ❌ | 🏆 | Viewer не работает с brokers |
| **Reassignment партиций** | ❌ | 🏆 | kafka-reassign-partitions.sh |
| **Preferred replica election** | ❌ | 🏆 | CLI специализированные команды |
| **Анализ disk usage** | ❌ | 🏆 | kafka-log-dirs.sh |

---

## 💡 Рекомендации по использованию

### **Kafka Viewer идеален для:**

1. **Development & QA:**
   ```bash
   # Быстрая проверка что попало в топик
   ./kafka_viewer.py --profile dev
   # → Enter на топик → смотрим последние сообщения
   ```

2. **Troubleshooting:**
   ```bash
   # Клиент не получает сообщения - почему?
   # → G → группа → смотрим lag
   # → F10 → reset to latest (если застряла)
   ```

3. **Security Audit:**
   ```bash
   # Кто имеет доступ к sensitive топикам?
   # → F4 → By Principal → выбираем User:unknown
   # → видим все ACL этого пользователя
   ```

4. **Learning Kafka:**
   ```bash
   # Новичку легче понять структуру через UI
   # чем читать --help у 15 разных команд
   ```

### **Kafka CLI обязателен для:**

1. **Production Operations:**
   ```bash
   # Автоматический мониторинг lag
   kafka-consumer-groups.sh --bootstrap-server prod:9092 \
     --describe --group my-app | awk '{print $6}' | \
     send_to_prometheus
   ```

2. **CI/CD:**
   ```bash
   # Создание топика в pipeline
   kafka-topics.sh --create --topic events-$ENV \
     --config retention.ms=86400000
   ```

3. **Data Migration:**
   ```bash
   # Копирование топика
   kafka-console-consumer.sh --topic source \
     --from-beginning --max-messages 1000000 | \
   kafka-console-producer.sh --topic dest
   ```

4. **Компликованные операции:**
   ```bash
   # Reassignment партиций между brokers
   kafka-reassign-partitions.sh --execute \
     --reassignment-json-file plan.json
   ```

---

## 🔮 Что можно добавить в Viewer для паритета?

### **Высокий приоритет:**

1. **Live streaming режим** (вместо только snapshot)
2. **Изменение конфига существующего топика**
