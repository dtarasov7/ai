# Анализ вариантов настройки логирования

Рассмотрю все возможные архитектуры решения вашей задачи:

## Вариант 1: Vector читает напрямую из journald + отправляет в syslog

### Архитектура:
```
systemd сервисы (Abc*) → journald → Vector → Kafka
                                      ↓
                                    srv1 (syslog)
```

### Конфигурация:

**systemd units** (опционально):
```ini
[Service]
SyslogIdentifier=Abc-service
SyslogFacility=local7
```

**Vector** (`/etc/vector/vector.toml`):
```toml
[sources.journald_abc]
type = "journald"
include_units = ["Abc*"]

[sinks.kafka]
type = "kafka"
inputs = ["journald_abc"]
bootstrap_servers = "kafka:9092"
topic = "logs"
encoding.codec = "json"

[sinks.kafka.buffer]
type = "disk"
max_size = 10737418240  # 10GB
when_full = "block"

[sinks.syslog_srv1]
type = "syslog"
inputs = ["journald_abc"]
address = "srv1:514"
mode = "udp"  # или tcp
```

**rsyslog** (`/etc/rsyslog.d/50-abc-exclude.conf`):
```
# Исключаем Abc* из /var/log/messages
:programname, startswith, "Abc" stop

# Остальное идет в messages
*.info /var/log/messages
```

### ✅ Плюсы:
- **Простая архитектура** - минимум компонентов
- **Полный контроль** - вся логика в Vector
- **Disk buffer** - защита от потери при недоступности Kafka
- **Единая точка обработки** - все трансформации в одном месте
- **Не нагружает rsyslog** дополнительной работой

### ❌ Минусы:
- **Дублирование отправки в syslog** - если rsyslog уже отправляет в srv1
- **Vector single point of failure** - если Vector упадет, логи не попадут в srv1
- **Нет встроенной буферизации для syslog sink** - может потерять при недоступности srv1

---

## Вариант 2: Разделение ответственности (рекомендуемый)

### Архитектура:
```
systemd (Abc*) → journald → Vector → Kafka (с disk buffer)
                     ↓
                  rsyslog → srv1 (syslog)
```

### Конфигурация:

**systemd units**:
```ini
[Service]
SyslogIdentifier=Abc-service
SyslogFacility=local7  # Отдельный facility
```

**Vector**:
```toml
[sources.journald_abc]
type = "journald"
include_units = ["Abc*"]

[sinks.kafka]
type = "kafka"
inputs = ["journald_abc"]
bootstrap_servers = "kafka:9092"
topic = "logs"
encoding.codec = "json"

[sinks.kafka.buffer]
type = "disk"
max_size = 21474836480  # 20GB
when_full = "block"
```

**rsyslog** (`/etc/rsyslog.d/50-abc.conf`):
```
# Отправляем local7 (Abc сервисы) в srv1
local7.* @@srv1:514

# Исключаем из messages
:syslogfacility-text, isequal, "local7" stop

# Остальное
*.info /var/log/messages
*.info local6.* @@srv1:514
```

### ✅ Плюсы:
- **Разделение задач**: Vector - Kafka, rsyslog - syslog
- **Надежность**: rsyslog имеет встроенную буферизацию и retry для syslog
- **Проверенная технология**: rsyslog стабилен для syslog forwarding
- **Минимальные изменения** в существующей конфигурации rsyslog
- **Disk buffer в Vector** защищает от потери при недоступности Kafka

### ❌ Минусы:
- **Два канала чтения** из journald (может создать небольшую нагрузку)
- **Более сложная отладка** - две системы логирования

---

## Вариант 3: Цепочка rsyslog → Vector → Kafka

### Архитектура:
```
systemd (Abc*) → journald → rsyslog → Vector (socket/file) → Kafka
                                ↓
                              srv1
```

### Конфигурация:

**rsyslog** (`/etc/rsyslog.d/50-abc.conf`):
```
# Отправляем в srv1
local7.* @@srv1:514

# Отправляем в Vector через socket
local7.* @@127.0.0.1:5140

# Исключаем из messages
:syslogfacility-text, isequal, "local7" stop
```

**Vector**:
```toml
[sources.syslog_input]
type = "syslog"
mode = "tcp"
address = "127.0.0.1:5140"

[sinks.kafka]
type = "kafka"
inputs = ["syslog_input"]
bootstrap_servers = "kafka:9092"
topic = "logs"

[sinks.kafka.buffer]
type = "disk"
max_size = 20971520000  # 20GB
when_full = "block"
```

### ✅ Плюсы:
- **Единая точка маршрутизации** - вся логика в rsyslog
- **Rsyslog буферизация** для отправки в srv1
- **Меньше чтения из journald**

### ❌ Минусы:
- **Дополнительный hop** - увеличивает задержку
- **Риск потери** между rsyslog и Vector (если Vector недоступен)
- **Усложнение архитектуры**
- **Нет встроенной буферизации** в rsyslog для omfwd в Vector
- **Возможность петли** при неправильной настройке

---

## Вариант 4: Файловый буфер через rsyslog

### Архитектура:
```
systemd (Abc*) → journald → rsyslog → файл → Vector (file source) → Kafka
                                ↓
                              srv1
```

### Конфигурация:

**rsyslog**:
```
local7.* @@srv1:514
local7.* /var/log/abc-services.log

:syslogfacility-text, isequal, "local7" stop
```

**Vector**:
```toml
[sources.abc_logs]
type = "file"
include = ["/var/log/abc-services.log"]
read_from = "end"

[sinks.kafka]
type = "kafka"
inputs = ["abc_logs"]
# ... disk buffer как выше
```

### ✅ Плюсы:
- **Файл как промежуточный буфер** - дополнительная защита
- **Простая отладка** - логи видны в файле
- **Vector читает в своем темпе**

### ❌ Минусы:
- **Дублирование на диске** - файл + Vector disk buffer
- **Ротация логов** - нужна настройка logrotate
- **Задержка** - Vector читает файл с задержкой
- **Парсинг** - Vector должен парсить syslog формат
- **Риск потери** при ротации файла

---

## Вариант 5: Отдельный journald namespace (современный подход)

### Архитектура:
```
systemd (Abc*) → journald namespace "abc" → Vector → Kafka
                                              ↓
                                            srv1
```

### Конфигурация:

**systemd units**:
```ini
[Service]
LogNamespace=abc
```

**journald** (`/etc/systemd/journald@abc.conf`):
```ini
[Journal]
Storage=persistent
SystemMaxUse=5G
```

**Vector**:
```toml
[sources.journald_abc]
type = "journald"
journal_directory = "/var/log/journal/abc"

[sinks.kafka]
# ... как выше
```

**rsyslog** - без изменений, не видит namespace

### ✅ Плюсы:
- **Полная изоляция** - логи Abc* не видны основному journald/rsyslog
- **Автоматически не попадают** в /var/log/messages
- **Отдельная конфигурация retention** для этих логов
- **Современный подход** (systemd 246+)

### ❌ Минусы:
- **Требует systemd 246+** (RHEL 8.4+, Ubuntu 20.10+)
- **Сложность отладки** - логи не в `journalctl` по умолчанию
- **Нужна отдельная отправка в srv1** через Vector
- **Дополнительное дисковое пространство** для журнала

---

## Сравнительная таблица

| Критерий | Вариант 1 | Вариант 2 | Вариант 3 | Вариант 4 | Вариант 5 |
|----------|-----------|-----------|-----------|-----------|-----------|
| **Защита от потери (Kafka)** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Защита от потери (srv1)** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Простота настройки** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **Производительность** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **Отладка** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Надежность** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 🏆 Рекомендация: **Вариант 2 (Разделение ответственности)**

### Обоснование:

1. **Защита от потери при недоступности Kafka**:
   - Vector disk buffer до 20GB (настраивается под ваши нужды)
   - При `when_full = "block"` сервисы будут блокироваться, но не потеряют логи
   - Альтернатива: `when_full = "drop_newest"` - сбросить новые при переполнении

2. **Защита от потери при аварийной перезагрузке**:
   - Disk buffer сохраняется на диске
   - journald persistence (проверьте `Storage=persistent` в `/etc/systemd/journald.conf`)
   - rsyslog queue на диске для отправки в srv1

3. **Защита отправки в srv1**:
   - rsyslog имеет встроенный механизм буферизации и retry
   - Надежнее чем Vector для syslog forwarding

### Дополнительные настройки для максимальной надежности:

**journald** (`/etc/systemd/journald.conf`):
```ini
[Journal]
Storage=persistent
SystemMaxUse=10G
RuntimeMaxUse=2G
```

**rsyslog** - добавить очередь:
```
$ActionQueueType LinkedList
$ActionQueueFileName srv1_queue
$ActionResumeRetryCount -1
$ActionQueueSaveOnShutdown on

local7.* @@srv1:514
```

**Vector** - мониторинг buffer:
```toml
[sinks.kafka.buffer]
type = "disk"
max_size = 21474836480
when_full = "block"

[sinks.internal_metrics]
type = "prometheus_exporter"
address = "0.0.0.0:9598"
```

### Проверка работоспособности:

```bash
# Проверка что Vector читает логи
journalctl -u Abc* -f | grep -v "test"

# Проверка метрик Vector
curl http://localhost:9598/metrics | grep buffer

# Проверка disk buffer
ls -lh /var/lib/vector/

# Тест отправки в rsyslog
logger -t Abc-test -p local7.info "Test message"
```

Эта архитектура обеспечивает максимальную надежность при минимальной сложности.
