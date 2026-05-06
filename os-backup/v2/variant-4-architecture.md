# Вариант 4. Годовые snapshot repository и searchable snapshots для архивного поиска

## Суть варианта

В production-кластере остается только рабочий онлайн-горизонт. Архивные данные хранятся в годовых `snapshot repository`. После перехода на новый год старый годовой `snapshot repository` переводится в закрытое состояние, целиком резервируется внешней СРК и может быть убран с основного NFS. Если позже нужен поиск по архиву, соответствующий годовой `snapshot repository` возвращается из backup на NFS и подключается к отдельному поисковому контуру как searchable snapshot.

Это развитие варианта 3, но вместо обычного `local restore` используется `remote_snapshot`, то есть данные читаются из `snapshot repository` по требованию и кэшируются на search-нодах.

## Диаграммы

- [variant-4-architecture.puml](/home/devuser/opensearch/diagrams/variant-4-architecture.puml:1)
- [variant-4-flow.puml](/home/devuser/opensearch/diagrams/variant-4-flow.puml:1)

## Почему вариант 4 отличается от варианта 3

В варианте 3 архивный поиск требует:

- вернуть `snapshot repository`, если он не на NFS;
- восстановить индексы локально в recovery-кластер;
- ждать полного или заметного restore.

В варианте 4:

- `snapshot repository` тоже может потребоваться вернуть из backup на NFS;
- но сами архивные индексы не нужно полностью восстанавливать на локальный диск;
- они открываются как searchable snapshots и читаются по мере запросов.

Это уменьшает потребность в локальном диске и обычно ускоряет время до первого поиска.

## Модель данных

Как и в других вариантах, архив включает множество типов логов и множество индексов, например:

- `fw-2025.01.01 ... fw-2025.12.31`
- `proxy-2025.01.01 ... proxy-2025.12.31`
- `auth-2025.01.01 ... auth-2025.12.31`
- `os-2025.01.01 ... os-2025.12.31`
- `app-2025.01.01 ... app-2025.12.31`

Все эти индексы за год логически группируются в годовой `snapshot repository`.

## Архитектура

### Компоненты

1. Production-кластер OpenSearch 2.19:
- хранит только online-горизонт;
- выполняет текущую индексацию.

2. Активный short-term `snapshot repository`:
- для hourly DR-snapshot текущих write-индексов.

3. Активный годовой архивный `snapshot repository`:
- например `repo-archive-2026`;
- в течение года принимает финальные snapshot закрытых дневных индексов.

4. Закрытые годовые `snapshot repository`:
- `repo-archive-2025`;
- `repo-archive-2024`;
- после завершения года в них больше не пишут;
- они резервируются целиком и могут храниться вне основного NFS.

5. Внешняя СРК:
- резервирует активный short-term `snapshot repository`;
- резервирует активный годовой `snapshot repository`;
- хранит закрытые годовые `snapshot repository` как архив.

6. Отдельный search/recovery-контур:
- как минимум один узел с ролью `search`;
- локальный диск под cache searchable snapshots;
- используется только для архивного поиска.

### Пример конфигурации archival snapshot repository

```yaml
path.repo:
  - /mnt/opensearch-snapshots
```

```json
PUT /_snapshot/repo-archive-2026
{
  "type": "fs",
  "settings": {
    "location": "/mnt/opensearch-snapshots/archive-2026",
    "compress": true
  }
}
```

Для поиска по уже закрытому годовому `snapshot repository`, возвращенному из backup на NFS, его лучше регистрировать на archive-search-контуре в режиме `readonly`:

```json
PUT /_snapshot/repo-archive-2025-search
{
  "type": "fs",
  "settings": {
    "location": "/mnt/opensearch-snapshots/archive-2025",
    "readonly": true
  }
}
```

### Конфигурация search-ноды

По документации OpenSearch 2.19 для `remote_snapshot` нужен как минимум один узел с ролью `search`.

```yaml
node.name: archive-search-1
node.roles: [ search ]
node.search.cache.size: 200gb
```

### Пример открытия архивных индексов как searchable snapshots

```json
POST /_snapshot/repo-archive-2025-search/snap-2025-final/_restore
{
  "storage_type": "remote_snapshot",
  "indices": "fw-2025.*,proxy-2025.*,auth-2025.*,os-2025.*,app-2025.*",
  "include_global_state": false
}
```

## Логика snapshot и backup

### Логические snapshot внутри OpenSearch

1. `Hourly DR snapshot`:
- каждые 30-60 минут;
- текущие write-индексы всех семейств логов;
- short-term retention 7-30 дней.

2. `Daily sealed snapshot`:
- закрытые индексы предыдущего дня;
- записываются в активный годовой `snapshot repository`, например `repo-archive-2026`.

3. При смене года:
- создается новый активный `snapshot repository`, например `repo-archive-2027`;
- старый `repo-archive-2026` переводится в закрытый режим;
- в него больше ничего не дописывается.

### Резервное копирование snapshot repository внешней СРК

#### Активный short-term snapshot repository

- режим: `synthetic full weekly + daily incremental` или `full weekly + daily incremental`;
- retention: 30-45 дней.

#### Активный годовой snapshot repository

- режим: `full monthly + daily incremental` или `synthetic full weekly + daily incremental`;
- retention оперативного backup-контура: 90 дней.

#### Закрытый годовой snapshot repository

После перехода на новый год:

1. Старый годовой `snapshot repository` считается sealed.
2. Делается контрольный full backup этого `snapshot repository` в архивный backup-tier.
3. Retention:
- минимум 5 лет хранения данных;
- практически лучше 6-7 лет, чтобы покрыть пограничные даты и разбор инцидентов.
4. После верификации backup исходный каталог этого года можно:
- оставить на NFS, если места достаточно;
- либо удалить с основного NFS и восстанавливать из СРК только при необходимости поиска.

### Почему деление по годам полезно

- ниже metadata pressure на один `snapshot repository`;
- проще вернуть из backup только нужный год;
- проще управлять жизненным циклом архива;
- проще работать с version compatibility.

## Поиск по запросу регулятора без даты

Это центральный сценарий для варианта 4. Если дата неизвестна, поиск придется делать по годам, но searchable snapshots уменьшают стоимость этого процесса.

### Последовательность действий

1. Выполнить поиск по online-горизонту в production-кластере.

2. Если нужен полный поиск за 5 лет, определить список архивных годов:
- `2022`;
- `2023`;
- `2024`;
- `2025`.

3. Для каждого года:
- при необходимости восстановить соответствующий годовой `snapshot repository` из СРК на NFS;
- зарегистрировать этот `snapshot repository` в отдельном search-контуре;
- выполнить restore с `storage_type: remote_snapshot`;
- открыть только нужные семейства индексов;
- выполнить поиск;
- выгрузить результаты.

4. После завершения поиска по году:
- удалить searchable snapshot index из search-контура;
- при необходимости отключить `snapshot repository`;
- перейти к следующему году.

Если инфраструктура позволяет, можно держать подключенными 2-3 годовых `snapshot repository` параллельно и обрабатывать годы одновременно. Но базовый безопасный runbook лучше строить как последовательный проход "год за годом".

5. После прохода по всем годам:
- объединить результаты;
- дедуплицировать;
- отсортировать по времени;
- подготовить единый ответ.

### Что требуется по месту

В отличие от варианта 3, здесь обычно не нужен полный локальный объем под восстановленные индексы. Нужны:

- место под сам годовой `snapshot repository` на NFS, если его пришлось вернуть из СРК;
- место под cache на search-ноде;
- место под служебные метаданные OpenSearch.

### Что требуется по времени

Если годовой `snapshot repository` уже лежит на NFS:

- время на регистрацию;
- время на открытие searchable snapshot;
- время на прогрев cache во время первых запросов.

Если годовой `snapshot repository` сначала надо вернуть из СРК:

- добавляется время на restore самого `snapshot repository` из backup.

## DR-сценарий

1. Production восстанавливается из short-term `snapshot repository`, как в варианте 3.
2. Архивный поиск не блокирует возврат приема логов.
3. Отдельный search-контур поднимается только при необходимости доступа к архивным годам.

## Что делать, если за 5 лет меняется версия OpenSearch

Это критически важно и здесь. Searchable snapshots используют restore API, а значит подчиняются тем же правилам version compatibility.

### Практический подход

1. На каждый major upgrade тестировать открытие хотя бы одного архивного года в совместимом контуре.
2. Делить архив по годам, чтобы migration был управляемым.
3. Если старый год уже несовместим с текущей major-версией:
- поднять temporary cluster совместимой major-версии;
- зарегистрировать восстановленный годовой `snapshot repository`;
- выполнить restore;
- reindex или снять новый snapshot в новый годовой `snapshot repository`;
- после этого использовать уже новый snapshot для поиска через searchable snapshots.
4. Хранить автоматизацию разворота совместимого archive-search-контура.

## Плюсы

- Быстрее старт архивного поиска, чем при обычном local restore.
- Меньше локального диска под архивный поиск.
- Годовые `snapshot repository` удобно жизненно циклировать и отдавать в backup.
- Хорошо подходит для редких регуляторных запросов по старым данным.
- Production остается небольшим и быстро восстанавливаемым.

## Минусы

- Searchable snapshots доступны только в режиме read-only.
- Архивный поиск медленнее локального поиска по полностью восстановленным индексам.
- Если годовой `snapshot repository` убран с NFS, его все равно нужно сначала вернуть из СРК.
- Нужен отдельный search-контур и настройка cache.
- Version compatibility архива остается обязательной эксплуатационной задачей.

## Вывод

Вариант 4 является наиболее технологичным архивным вариантом для вашего кейса, если приемлемо:

- хранить архивные годы вне production;
- искать по ним через отдельный search-контур;
- поддерживать операционный процесс возврата годового `snapshot repository` из backup и проверки совместимости по major-версиям.

## Ссылки

- https://docs.opensearch.org/2.19/tuning-your-cluster/availability-and-recovery/snapshots/snapshot-restore/
- https://docs.opensearch.org/2.19/tuning-your-cluster/availability-and-recovery/snapshots/searchable_snapshot/
- https://docs.opensearch.org/latest/api-reference/snapshots/restore-snapshot/
- https://docs.opensearch.org/latest/tuning-your-cluster/availability-and-recovery/snapshots/snapshot-management/
- https://docs.opensearch.org/docs/api-reference/snapshots/create-repository/
