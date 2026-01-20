Ниже — несколько рабочих архитектур (от «самой чистой» до «самой совместимой»), как сделать так, чтобы логи systemd‑сервисов `Abc*`:

1) попадали в Vector на этом же хосте  
2) уходили по сети на syslog‑сервер `srv1`  
3) **не** попадали в `/var/log/messages`  
4) **не терялись** при многочасовой недоступности Kafka и при аварийной перезагрузке

---

## Коротко (что бы я выбрал)

**Лучший вариант по “чистоте” и управляемости** — **вынести `Abc*` в отдельный journal namespace** (`LogNamespace=`), а Vector читать **только этот namespace** (`journal_namespace`). Тогда rsyslog вообще не увидит эти сообщения → они не попадут в `/var/log/messages` без сложных фильтров. `LogNamespace=` описан в systemd.exec.   
Vector умеет читать namespace через `journal_namespace`. 

Дальше:
- в Vector включить **end-to-end acknowledgements** + **disk buffer** на Kafka sink, чтобы при падении Kafka события гарантированно переживали рестарт/краш. 
- отправку на `srv1` сделать либо:
  - **через rsyslog** (самый типовой syslog-вывод + можно RELP/TLS/очереди на диск), либо
  - **напрямую из Vector через `socket` sink** (тогда нужно форматировать RFC3164/5424 строку). 

---

## Базовые “кирпичи” надежности (важно для всех вариантов)

### 1) Journald как первая ступень буферизации
Чтобы переживать перезагрузки, journald должен писать **на диск** (persistent). Это настраивается `Storage=persistent` (или `auto` + существующий `/var/log/journal`).   
Также обязательно ограничить/спланировать размер журнала `SystemMaxUse`, `SystemKeepFree` и т.п., иначе при долгой остановке downstream он начнет ротировать старое. 

Отдельно: journald может **дропать** при rate limit (`RateLimitInterval*`, `RateLimitBurst`).   
А imjournal/rsyslog отдельно отмечает, что sd_journal API не дает “счетчика потерь”, и journald пишет строку вида “Suppressed N messages…”. 

### 2) Vector: end-to-end acknowledgements + disk buffer
- В Vector есть **end-to-end acknowledgements**: источник, который поддерживает ack (journald source поддерживает), будет считать событие “принятым” только когда оно доставлено/зафиксировано на выходах.   
- Для переживания часов простоя Kafka нужен **disk buffer** на Kafka sink (`buffer.type: disk`) и достаточный `buffer.max_size`. Disk buffer синхронизируется на диск периодически (у Vector — ~каждые 500ms), и то, что уже синхронизировано, переживает crash.   
- Очень важно: `data_dir` Vector должен быть на **постоянном диске**, т.к. там хранятся и буферы, и чекпоинты. 

### 3) rsyslog: надежная сеть до srv1
Если отправка на `srv1` должна быть “не потерять при недоступности srv1”, rsyslog умеет **дисково-ассистированные очереди** (spool) для `omfwd`: `queue.filename`, `queue.saveOnShutdown="on"`, бесконечные ретраи.   
(Если `srv1` умеет RELP — это еще надежнее, но это уже отдельная договоренность.)

---

## Вариант 1 (рекомендованный): отдельный journald namespace для Abc* + Vector читает namespace

### Схема
`Abc*.service (stdout/stderr) → journald(namespace=abc) → Vector(journald source, namespace=abc) → Kafka (+disk buffer)`  
и параллельно  
`Vector → srv1 (через rsyslog или socket sink)`

### Как это решает “не попадать в /var/log/messages”
rsyslog (imjournal) по умолчанию читает **дефолтный** journal namespace. Если `Abc*` пишут в отдельный namespace — rsyslog их просто не увидит → `/var/log/messages` чистый без фильтров.

`LogNamespace=`: вывод сервиса идет в отдельный namespace, и в обычном `journalctl` его не видно без `--namespace`.   
Vector умеет читать namespace через `journal_namespace` (просто прокидывает `--namespace` в journalctl). 

### Плюсы
- Максимально “чисто”: **никаких** rsyslog‑фильтров/исключений для `/var/log/messages`.
- Удобно масштабировать: добавили новый `AbcX.service` → просто применили drop‑in.
- Namespace по умолчанию **persistent** (в отличие от default namespace, где `auto`). 

### Минусы/риски
- Нужны изменения unit-файлов (drop‑in) и systemd версии, где есть namespaces (в man отмечено “Added in version 245”). 
- Если отправлять на `srv1` **из Vector**, придется:
  - либо форматировать syslog‑строку и слать через `socket` sink (в Vector нет “syslog sink” как отдельного типа),
  - либо отправлять из Vector в локальный rsyslog (TCP/Unix socket), а rsyslog уже на `srv1`.

---

## Вариант 2: пометить Abc* facility=local6 и исключить local6 из /var/log/messages

Это “классика syslog”.

### Схема
`Abc* → journald (facility=local6) →`
- `Vector(journald) → Kafka`
- `rsyslog: local6.* → srv1`
- `rsyslog: *.info;local6.none → /var/log/messages` (или эквивалент)

Systemd позволяет задать facility/tag для stdout/stderr логов через `SyslogFacility=` и `SyslogIdentifier=` (когда StandardOutput/StandardError идут в journal/kmsg). 

### Плюсы
- Обычно самый простой путь, если `local6` у вас реально свободен/резервируется под Abc.
- Не требует namespace’ов.
- Отправка на `srv1` остается в rsyslog (нативный syslog).

### Минусы/риски
- Если `local6` уже используется другими компонентами — вы их тоже исключите из `/var/log/messages` (если делаете `local6.none`).
- rsyslog и Vector оба читают journald (двойное потребление) — не критично, но лишняя нагрузка.
- Все равно нужно аккуратно следить за размером journald и disk buffer, иначе при длинном даунтайме Kafka упретесь в диск.

---

## Вариант 3: rsyslog фильтрует Abc* и делает “stop”, чтобы не писать в messages

### Схема
`journald → rsyslog(imjournal) →`
- если `programname`/`syslogtag` начинается на `Abc`:  
  - отправить в `srv1`  
  - отправить в Vector (локально)  
  - `stop` (и поэтому **не** писать в `/var/log/messages`)
- остальное — как сейчас в `/var/log/messages`

### Плюсы
- Не нужно менять systemd units (кроме, возможно, `SyslogIdentifier=`, чтобы `programname` был стабильным). 
- Один “маршрутизатор” на входе (rsyslog), можно очень гибко рулить.

### Минусы/риски
- Самый частый источник ошибок: неправильно матчится `programname/syslogtag` → утечки в messages или наоборот дроп.
- Нужно аккуратно избегать **петель**: imjournal не защищает от лог-лупов при некоторых конфигурациях. 
- Надежность “rsyslog → Vector” зависит от транспорта и очередей (надо делать TCP + disk queue).

---

## Вариант 4: rsyslog как главный буфер/маршрутизатор, Vector принимает по syslog (TCP)

### Схема
`journald → rsyslog(imjournal) → (TCP) → Vector(syslog source) → Kafka`

И параллельно rsyslog отправляет на `srv1`.

### Большой нюанс по надежности
`syslog` source в Vector имеет **best effort** и **без acknowledgements**.   
То есть end-to-end ack от journald до Kafka вы уже не построите на уровне Vector (будет “принято по TCP” ≠ “надежно зафиксировано до Kafka”).

### Плюсы
- rsyslog умеет очень мощные дисковые очереди и ретраи, можно “держать” Vector downtime тоже.
- Один читатель journald (rsyslog), а не два.

### Минусы
- Слабее гарантии “до Kafka” именно в терминах end-to-end ack Vector’а (источник syslog не ack’ает). 
- Дедуп/повторы сложнее контролировать.

---

## Вариант 5: Abc* пишут в отдельные файлы, Vector читает file source

### Схема
`Abc* StandardOutput=append:/var/log/abc/*.log → Vector(file source) → Kafka`  
и отдельно отправка в `srv1`.

### Плюсы
- Полная изоляция от journald/rsyslog: точно не попадет в `/var/log/messages`.
- Префикс Abc* автоматически “отделен” по пути.

### Минусы
- Нужно решать logrotate/права/атомарность, мультистроки и т.п.
- Теряете часть journald-метаданных.
- Если делать “дублирующий файл” из Vector через `file sink` — он **не гарантирует fsync** и не обещает “железную” долговечность записей при краше.   
  (Поэтому как “страховочный WAL” лучше использовать именно disk buffer Vector’а, а не file sink.)

---

## Сравнение вариантов (критерии: messages, надежность при Kafka down+crash, сложность)

| Вариант | Не писать в `/var/log/messages` | Надежность при долгом Kafka down + crash | Сложность внедрения | Комментарий |
|---|---:|---:|---:|---|
| **1) LogNamespace + Vector journald namespace** | Отлично (rsyslog не видит) | Отлично (journald persistent + Vector disk buffer + ack)  | Средняя | Самый “инженерно правильный” |
| **2) SyslogFacility=local6 + `local6.none` в messages** | Хорошо (если local6 только для Abc) | Отлично (при правильном Vector disk buffer + ack)  | Низкая | Очень практичный, но нужен “свободный facility” |
| **3) rsyslog filter + stop** | Хорошо (если фильтр правильный) | Хорошо/Отлично (зависит от очередей rsyslog + disk buffer Vector)  | Средняя | Гибко, но легко ошибиться в фильтрах |
| **4) rsyslog → Vector(syslog source)** | Хорошо | Средне (syslog source без ack)  | Средняя | Часто делают, но это компромисс по гарантиям |
| **5) В файл + Vector file source** | Отлично | Средне/Хорошо | Высокая | Много ручной “эксплуатации логов” |

---

## Как именно закрыть требование “не терять при многочасовой недоступности Kafka и при аварийной перезагрузке”

Независимо от выбранного маршрута до `srv1`, для Kafka я бы делал так:

1) **Journald persistent + достаточно места**
   - `Storage=persistent` (или `auto` + `/var/log/journal`), иначе после ребута вы теряете журнал.   
   - Настроить `SystemMaxUse`, `SystemKeepFree` под ваш объем логов и worst-case простоя. 

2) **Vector: включить acknowledgements и disk buffer на Kafka sink**
   - Глобально `acknowledgements.enabled: true` (или на Kafka sink).   
   - На Kafka sink: `buffer.type: disk`, `buffer.max_size: …`, `when_full: block` (по умолчанию `block`). Disk buffer переживает crash для уже синхронизированных данных.   
   - Убедиться, что `data_dir` Vector на постоянном диске. 

3) **Vector journald source: отключить `current_boot_only`**
   По умолчанию `current_boot_only: true`.   
   Для сценария “Kafka лежала, сервер ребутнулся” вам нужно **дочитать хвост предыдущего boot** → ставьте `current_boot_only: false`.

4) **Сайзинг буфера под “часы недоступности”**
   Нужно заложить объем:
   ```
   required_bytes ≈ avg_event_bytes * events_per_sec * outage_sec * safety_factor
   ```
   И этот объем нужно распределить как минимум между:
   - journald (чтобы не выкинул старое, пока Vector стоит/заблокирован),
   - disk buffer Vector на Kafka sink (чтобы после чтения из journald не потерять до Kafka).

5) **Следить за journald rate limiting**
   Если `Abc*` могут “шуметь” бурстами — настройте `RateLimitInterval* / RateLimitBurst` (или отключите для системы/подхода), иначе journald может дропнуть. 

---

## Практическая “опорная” конфигурация (примерно, без привязки к вашему exact YAML)

### Vector (ключевые идеи)
- `data_dir` на диск
- `acknowledgements.enabled: true`
- `journald` source (желательно namespace или filter по `_SYSTEMD_UNIT`)
- Kafka sink с `buffer.type: disk`

Ссылки на поведение:
- global `acknowledgements` и `data_dir`   
- journald source: include_units/include_matches, `data_dir`, `current_boot_only`   
- kafka sink: `buffer.type=disk`, `buffer.max_size`   
- buffering model: sync ~500ms 

### rsyslog (если он отвечает за доставку на srv1 “надежно”)
Использовать TCP/TLS и дисково-ассистированную очередь на action `omfwd`. 

---

## Итоговая рекомендация по выбору

- Если вы **можете** менять unit-файлы и systemd достаточно свежий: **Вариант 1 (LogNamespace)** — лучший: он архитектурно отделяет Abc‑логи от `/var/log/messages` без “магии” в rsyslog.   
- Если namespace по каким-то причинам нельзя: **Вариант 2 (SyslogFacility=local6 + local6.none)** — самый быстрый и обычно самый дешевый в сопровождении, при условии что facility можно зарезервировать.   
- Если нужно “всё маршрутизировать правилами” и вы готовы тщательно тестировать: **Вариант 3 (rsyslog filter + stop)**.

Главное для защиты от потерь при Kafka down + crash: **(journald persistent + Vector acknowledgements + Vector disk buffer + current_boot_only=false + правильный сайзинг диска)**. 
