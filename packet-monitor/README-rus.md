# packet-monitor

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-v1.6.0-brightgreen)](CHANGELOG-rus.md)

`packet-monitor` это терминальный монитор и анализатор сетевых пакетов, написанный на Python с использованием Scapy и Urwid.

Он поддерживает:
- live-захват с выбранного интерфейса или с `any`
- офлайн-анализ файлов `pcap` и `pcapng`
- список пакетов и представление flows/conversations
- UI-фильтрацию, exclusions и profiles
- Follow Stream для TCP/TLS-ориентированного анализа
- экспорт всех пакетов или только текущей отфильтрованной выборки

> Используйте этот инструмент только на системах и трафике, которые принадлежат вам или на анализ которых у вас есть разрешение.

## Скриншот

![packet-monitor screenshot](images/packet-monitor1.png)

## Требования

- Python 3.8+
- `scapy`
- `urwid`
- root/admin-привилегии для live-захвата на большинстве систем

Пример пакетов для Debian/Ubuntu:
- `python3`
- `python3-scapy`
- `python3-urwid`

## Быстрый старт

### Live capture

```bash
sudo python3 packet-monitor.py
```

Захват на конкретном интерфейсе:

```bash
sudo python3 packet-monitor.py -i eth0
```

Захват с BPF-фильтром:

```bash
sudo python3 packet-monitor.py -i eth0 -f "tcp port 443"
```

### Офлайн-анализ

Открыть файл захвата:

```bash
python3 packet-monitor.py -r capture.pcap
```

или:

```bash
python3 packet-monitor.py -r capture.pcapng
```

### CLI-параметры

- `-i`, `--interface` - интерфейс захвата
- `-r`, `--read` - открыть `pcap` / `pcapng`
- `-f`, `--filter` - BPF-фильтр в синтаксисе `tcpdump`
- `--ipv6` - включить расширенную IPv6-статистику
- `--version` - вывести версию

## Основные возможности

### Список пакетов

- timestamp, интерфейс, протокол, endpoints, порты и `Info`
- compact и wide режимы для `Info`
- packet details с разобранными полями и hexdump

### Flows / Conversations

- агрегация по 5-tuple
- drill-down от flow к соответствующим пакетам
- исключение flow и просмотр flow details

### Фильтрация

- UI-фильтры по протоколу, IP, порту, интерфейсу, `Info` и payload
- диалог поиска по payload
- exclusions по протоколу или stream

### Follow Stream

- TCP reassembly payload по sequence number с deduplication ретрансмитов и заглушками для gap
- TLS handshake summary без расшифровки
- экспорт stream text/raw data

### Экспорт и профили

- сохранение всех захваченных пакетов или только отфильтрованных
- сохранение, загрузка и удаление профилей
- профили могут хранить текущие filters, exclusions и BPF

## Горячие клавиши

Основные клавиши:
- `F1` / `H` - помощь
- `Q` - выход
- `P` - пауза/продолжение захвата в live-режиме
- `S` - сохранить/экспортировать пакеты
- `F` - открыть UI-фильтры
- `/` - поиск по payload
- `G` - переключить packets / flows
- `O` - профили
- `W` - переключить compact / wide `Info`

В режиме packets:
- `Enter` - детали пакета
- `T` - follow stream
- `X` - исключить текущий stream или protocol
- `B` - задать capture BPF в live-режиме

В режиме flows:
- `Enter` - drill-down к пакетам
- `D` - детали flow
- `T` - follow stream
- `X` - исключить выбранный flow
- `V` - переключить источник flows: filtered / all

## Документация

Подробные руководства:
- [UserGuide.md](UserGuide.md) - руководство на английском
- [UserGuide-ru.md](UserGuide-ru.md) - руководство на русском

Архитектурные диаграммы:
- [diagamms/README.md](diagamms/README.md)

## Примечания

- `-i any` на Linux обычно дает Linux cooked capture (`SLL` / `SLL2`), а не Ethernet.
- BPF это capture-time фильтр и он недоступен в offline-режиме.
- TLS decryption не выполняется; анализируются только metadata и структура handshake.

## Contributing

При сообщении о проблемах укажите:
- ОС и версию Python
- live или offline режим
- шаги воспроизведения
- пример `pcap` / `pcapng`, если возможно

## Лицензия

MIT. См. [LICENSE](LICENSE).

## Автор

**Tarasov Dmitry**
- Email: dtarasov7@gmail.com

## Attribution

Часть этого кода была создана с использованием внешней генеративной помощи.
