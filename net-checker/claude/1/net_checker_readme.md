# Ansible роль net-checker

Роль для проверки сетевой связанности между хостами с генерацией метрик в формате Prometheus.

## Описание

Роль `net-checker` позволяет проверять сетевую доступность хостов двумя способами:
- **ICMP** (ping) - проверка доступности по протоколу ICMP
- **TCP** - проверка доступности конкретного TCP порта

Роль поддерживает два режима работы:
1. **Режим 1** - интеграция с node_exporter через textfile collector
2. **Режим 2** - выполнение проверки и сохранение результатов локально на Ansible хосте

## Требования

- Ansible >= 2.9
- Для режима 1: установленный node_exporter с textfile collector модулем
- Для проверки TCP: утилита `nc` (netcat) или поддержка `/dev/tcp` в bash

## Переменные роли

### Обязательные переменные

| Переменная | Описание | Пример |
|-----------|----------|---------|
| `net_checker_mode` | Режим проверки: `icmp` или `tcp` | `icmp` |
| `net_checker_target_hosts` | Список хостов для проверки | см. примеры ниже |
| `net_checker_work_mode` | Режим работы: `1` или `2` | `1` |
| `net_checker_env` | Окружение для меток | `production` |
| `net_checker_is` | Идентификатор is для меток | `web` |
| `net_checker_job` | Имя job для меток | `connectivity_check` |

### Дополнительные переменные

| Переменная | Значение по умолчанию | Описание |
|-----------|----------------------|----------|
| `net_checker_tcp_port` | `80` | TCP порт для проверки (обязательно при mode: tcp) |
| `net_checker_textcollector_dir` | `/var/lib/node_exporter/textfile_collector` | Директория textfile collector |
| `net_checker_user` | `sys_net_checker` | Пользователь для выполнения проверок |
| `net_checker_node_exporter_user` | `sys_node_exporter` | Пользователь node_exporter |
| `net_checker_cron_minutes` | `5` | Интервал выполнения в минутах |
| `net_checker_local_results_dir` | `./net_checker_results` | Директория для сохранения результатов (режим 2) |
| `net_checker_timeout` | `5` | Таймаут для проверок в секундах |
| `net_checker_ping_count` | `3` | Количество ping пакетов |

## Примеры использования

### Режим 1: Node exporter + textfile collector

```yaml
- hosts: monitoring_targets
  roles:
    - role: net-checker
      vars:
        net_checker_mode: icmp
        net_checker_work_mode: 1
        net_checker_target_hosts:
          - name: web1
            ip: 192.168.1.10
          - name: web2
            ip: 192.168.1.11
          - db.example.com
        net_checker_env: production
        net_checker_is: web
        net_checker_job: connectivity_check
        net_checker_cron_minutes: 5
```

### Режим 2: Локальное сохранение результатов

```yaml
- hosts: web_servers
  roles:
    - role: net-checker
      vars:
        net_checker_mode: tcp
        net_checker_tcp_port: 443
        net_checker_work_mode: 2
        net_checker_target_hosts:
          - name: api1
            ip: 10.0.1.100
          - name: api2
            ip: 10.0.1.101
        net_checker_env: staging
        net_checker_is: frontend
        net_checker_job: api_check
        net_checker_local_results_dir: ./metrics
```

### Проверка TCP портов

```yaml
- hosts: load_balancers
  roles:
    - role: net-checker
      vars:
        net_checker_mode: tcp
        net_checker_tcp_port: 8080
        net_checker_work_mode: 1
        net_checker_target_hosts:
          - backend1.internal
          - backend2.internal
          - backend3.internal
        net_checker_env: production
        net_checker_is: lb
        net_checker_job: backend_health
```

## Форматы целевых хостов

Роль поддерживает два формата указания целевых хостов:

### Простой формат
```yaml
net_checker_target_hosts:
  - web1.example.com
  - 192.168.1.10
  - db.internal
```

### Расширенный формат
```yaml
net_checker_target_hosts:
  - name: web1
    ip: 192.168.1.10
  - name: database
    ip: 10.0.1.50
```

## Метрики Prometheus

Роль генерирует следующие метрики:

### net_checker_connectivity
- **Тип**: gauge
- **Описание**: Результат проверки связанности (1 - доступен, 0 - недоступен)
- **Метки**:
  - `source_hostname` - хост источник
  - `source_ip` - IP источника
  - `target_hostname` - целевой хост
  - `target_ip` - IP цели
  - `mode` - режим проверки (icmp/tcp)
  - `port` - порт (для TCP)
  - `env` - окружение
  - `new_is` - идентификатор is
  - `new_instance` - имя источника
  - `new_job` - имя job
  - `check_id` - уникальный ID проверки

### net_checker_response_time_ms
- **Тип**: gauge
- **Описание**: Время отклика в миллисекундах
- **Метки**: те же, что и у net_checker_connectivity

## Теги

### Cleanup
Для удаления всех созданных файлов, пользователей и заданий cron используйте тег `never`:

```bash
ansible-playbook -i inventory playbook.yml --tags never
```

Это удалит:
- Скрипты проверки
- Пользователя sys_net_checker (если нет других заданий)
- Задания cron
- Файлы метрик
- Правила sudoers

## Структура файлов роли

```
net-checker/
├── defaults/
│   └── main.yml
├── meta/
│   └── main.yml
├── tasks/
│   ├── main.yml
│   ├── mode1.yml
│   ├── mode2.yml
│   └── cleanup.yml
├── templates/
│   └── net_checker.sh.j2
└── README.md
```

## Безопасность

- В режиме 1 создается ограниченное правило sudoers только для изменения владельца файлов метрик
- Скрипты выполняются от имени специального системного пользователя
- Все временные файлы удаляются после выполнения

## Поддержка нескольких проверок

Роль поддерживает запуск нескольких независимых проверок на одном сервере. Для этого используется уникальный идентификатор `check_id`, который формируется из параметров проверки:

```
check_id = "{{ job }}_{{ mode }}_{{ port | default('icmp') }}"
```

Это позволяет:
- Различать скрипты разных проверок
- Создавать отдельные файлы метрик
- Разделять метки в Prometheus

## Требования к системе

### Режим 1
- Установленный node_exporter с textfile collector
- Наличие директории для textfile collector
- Права на создание пользователей и изменение crontab

### Режим 2
- Доступ для записи в локальную директорию результатов
- Временное место для выполнения скриптов

## Troubleshooting

### Ошибка "textcollector directory not found"
Убедитесь, что node_exporter установлен с модулем textfile collector и директория существует.

### Ошибка выполнения TCP проверки
Установите утилиту `nc` (netcat) или убедитесь, что bash поддерживает `/dev/tcp`.

### Проблемы с правами
Проверьте, что пользователь Ansible имеет права на создание пользователей и изменение sudoers файлов.