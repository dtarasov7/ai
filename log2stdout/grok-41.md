### Возможные варианты построения системы логирования

Я рассмотрел все реалистичные варианты маршрутизации логов сервисов Abc* (stdout/stderr через systemd → journald) в Vector → Kafka, с исключением из `/var/log/messages`, сохранением текущей функциональности rsyslog для других логов и защитой от потерь при длительном (часы) downtime Kafka и аварийном reboot. Основные ограничения:
- Journald по умолчанию persistent (проверьте `/etc/systemd/journald.conf: Storage=persistent`, `SystemMaxUse=10G` для буфера).
- Vector (vector.dev) — высокопроизводительный, с disk buffer для Kafka sink.
- Rsyslog уже использует `imjournal`, читает journald, фильтрует по `*.info` → `/var/log/messages` и `*.info local6.*` → srv1.
- Programname в journald для сервисов — имя unit (Abc*), фильтруется по `$programname =~ "Abc.*"`.

**Предварительные шаги для всех вариантов (обязательно):**
- Vector config: 
  ```
  [sources.journald]
  type = "journald"
  units.include = ["Abc.*"]  # или file/multiline если нужно

  [sinks.kafka]
  type = "kafka"
  inputs = ["journald"]  # или transform
  bootstrap_servers = ["kafka-host:9092"]
  buffer.type = "disk"
  buffer.max_size = "10GB"  # Для часов downtime
  buffer.disk.queue.path = "/var/lib/vector/kafka-buffer"
  buffer.disk.queue.durability = "permanent"  # fsync на write
  acknowledgements.enabled = true  # Ждать Kafka ACK
  ```
  Это обеспечивает: disk буфер (GB для часов логов), recovery после reboot (Vector хранит state в data_dir), retries.
- Развернуть Vector как systemd service, с `Restart=always`.
- Мониторинг Vector: internal_logs/metrics.

#### Вариант 1: Vector читает напрямую из journald (рекомендуемый)
- **Как работает:**
  - Vector `journald` source с `units.include = ["Abc.*"]` — читает только нужные unit'ы, tailing по cursor (stateful).
  - В rsyslog (`/etc/rsyslog.d/abc-exclude.conf`, перед `*.info` правилами):
    ```
    if $programname =~ "Abc.*" then {
      stop
    }
    ```
    Discard Abc* до записи в `/var/log/messages` или отправки (если они *.info). `systemctl restart rsyslog`.
- **Защита от потерь:**
  - Kafka down: Vector disk buffer (часы+ OK).
  - Reboot: journald persistent → Vector возобновит с cursor (не потеряет).
- **Плюсы:**
  - Минимальные изменения, native для systemd/Vector.
  - Нет extra disk IO (rsyslog не пишет файлы).
  - Полные journald fields (PID, unit, etc.).
  - Высокая производительность (journald multi-reader OK).
  - Нет дублирования в srv1 (если Abc* не local6).
- **Минусы:**
  - Два reader'а journald (rsyslog + Vector) — negligible load.
  - Если rsyslog lag'ует, cursor может отставать (редко).

#### Вариант 2: Rsyslog пишет Abc* в dedicated файл → Vector tail'ит файл
- **Как работает:**
  - Rsyslog (`/etc/rsyslog.d/abc-vector.conf`, перед другими правилами):
    ```
    if $programname =~ "Abc.*" then {
      /var/log/abc.log
      stop
    }
    ```
    Rotation: `outchannel(abc,|/var/log/abc.log,104857600,86400,/var/log/abc.log.older)`.
  - Vector `file` source: `include = ["/var/log/abc.log*"]`, `file_key = "filename"`, multiline/multiline_id если нужно.
- **Защита от потерь:**
  - Аналогично: rsyslog queue (spool), Vector disk buffer.
  - Reboot: journald → rsyslog imjournal stateful → file → Vector position persistent.
- **Плюсы:**
  - Vector не зависит от journald API (simpler если проблемы).
  - Легко inspect файл вручную.
- **Минусы:**
  - Extra hop (journald → rsyslog → file → Vector) — выше CPU/disk IO, bottleneck на rsyslog.
  - Потеря некоторых journald fields (нужен template в rsyslog: `$template abcJson,"%$all-json-template%\n"`).
  - Rotation complexity (logrotate/rsyslog outchannel).
  - Больше disk usage.

#### Вариант 3: Изменить unit-файлы Abc* сервисов (StandardOutput=syslog+local6)
- **Как работает:**
  - В [Service] unit'ов: `StandardOutput=syslog+local6`, `StandardError=syslog+local6`.
  - Rsyslog: перехватить `local6.*` → `/var/log/abc.log; stop` (чтобы не в messages/srv1).
  - Vector tail `/var/log/abc.log`.
- **Защита:** Аналогично варианту 2.
- **Плюсы:** Изоляция facility, нет фильтров по programname.
- **Минусы:**
  - Изменения в multiple unit'ах (override в `/etc/systemd/system/Abc*.service.d/` — OK, но maintenance).
  - Логи не в journald (query journalctl без Abc*).
  - Local6 может конфликтовать с текущим `local6.* → srv1`.

#### Вариант 4: Полностью отключить rsyslog для Abc* (глобальные изменения)
- **Как работает:**
  - Journald.conf: `ForwardToSyslog=no` — но отключит все syslog.
  - Или rsyslog: отключить imjournal, использовать только Vector.
- **Минусы:** Ломает текущие `*.info → messages/srv1`. Не подходит.

#### Вариант 5: Vector как syslog listener + systemd forward
- **Как работает:** Vector `syslog` source (UDP/TCP), journald `ForwardTo=syslog` с rate-limit, но фильтр по unit'ам нет.
- **Минусы:** Не selective (все логи), unreliable UDP, нет защиты (syslog не buffered хорошо).

#### Сравнение вариантов

| Вариант | Сложность настройки | Производительность | Надежность (downtime/reboot) | Disk IO | Maintenance | Рекомендация |
|---------|---------------------|--------------------|------------------------------|---------|-------------|--------------|
| **1: Vector journald + rsyslog discard** | Низкая (1 файл rsyslog) | Высокая (native) | Отличная (disk buffer + cursor) | Низкая | Низкая | **Лучший** — баланс всего. |
| **2: Rsyslog file → Vector tail** | Средняя (rsyslog template/rotation) | Средняя (extra hop) | Хорошая (file position) | Средняя | Средняя | Альтернатива если journald issues. |
| **3: Unit syslog+local6** | Высокая (multiple units) | Средняя | Хорошая | Средняя | Высокая | Только если изоляция facility критична. |
| **4: Глобальный off** | Высокая | — | — | — | Высокая | Не подходит. |
| **5: Syslog forward** | Средняя | Низкая (UDP) | Средняя (no ACK) | Низкая | Средняя | Не рекомендуется. |

**Итог:** Выберите **Вариант 1** — он оптимален, использует сильные стороны journald/Vector. Тестируйте: `journalctl -u Abc*`, Vector metrics, симулируйте downtime (`systemctl stop kafka`). Если >10GB логов/час — увеличьте buffer/journal limits.
