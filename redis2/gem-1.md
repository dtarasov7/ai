Отлично, с учетом ваших уточнений, мы полностью меняем подход. Вместо внешней проверки на сервере Zabbix, мы будем использовать `UserParameter` на Zabbix агентах, установленных на каждом сервере Redis. Это соответствует вашему требованию применять шаблон ко всем серверам.

Вот пошаговый план и готовые компоненты:

### Шаг 1: Создание пользователя Redis с правами ACL

Для выполнения команды `CLUSTER NODES` скрипту мониторинга необходим доступ к кластеру. Создадим для этого специального пользователя с минимально необходимыми правами.

Подключитесь к любому из master-узлов вашего кластера с правами администратора и выполните команду:

```
ACL SETUSER zabbix-monitor on >YourSecretPassword +@cluster
```

*   `zabbix-monitor`: Имя пользователя.
*   `YourSecretPassword`: Замените на надежный пароль.
*   `+@cluster`: Предоставляет доступ к командам, необходимым для опроса состояния кластера (включая `CLUSTER NODES`), без предоставления прав на чтение данных или изменение конфигурации.

Запомните имя пользователя и пароль, они понадобятся для настройки.

### Шаг 2: Скрипт для Zabbix Агента

Этот скрипт будет размещен на **каждом** из 6 серверов вашего кластера. Он будет подключаться к локальному узлу Redis, получать информацию обо всем кластере и проверять распределение мастеров по ЦОД.

Создайте файл `/etc/zabbix/scripts/check_redis_dc_masters.sh` на каждом сервере:

```bash
#!/bin/bash

# Скрипт для Zabbix Agent, проверяющий наличие нескольких master-узлов Redis в одном ЦОД.
# Запускается локально на каждом узле кластера.

# --- Параметры, передаваемые из zabbix_agentd.conf ---
DC_MAP_FILE="$1"
REDIS_USER="$2"
REDIS_PASSWORD="$3"
REDIS_PORT="${4:-6379}"
# Опциональный путь к CA сертификату для TLS
REDIS_CACERT_PATH="$5"

# --- Проверка входных данных ---
if [[ -z "$DC_MAP_FILE" || -z "$REDIS_USER" || -z "$REDIS_PASSWORD" ]]; then
  echo "ERROR: Missing arguments. Usage: $0 <dc_map_file> <user> <password> [port] [cacert_path]"
  exit 1
fi

if [ ! -f "$DC_MAP_FILE" ]; then
  echo "ERROR: DC mapping file not found at $DC_MAP_FILE"
  exit 1
fi

# --- Формирование команды redis-cli с поддержкой TLS и ACL ---
CLI_COMMAND="redis-cli -h 127.0.0.1 -p $REDIS_PORT --user $REDIS_USER --pass $REDIS_PASSWORD --tls"

# Добавляем CA сертификат, если путь к нему указан
if [ -n "$REDIS_CACERT_PATH" ]; then
  if [ -f "$REDIS_CACERT_PATH" ]; then
    CLI_COMMAND="$CLI_COMMAND --cacert $REDIS_CACERT_PATH"
  else
    echo "ERROR: CA certificate file not found at $REDIS_CACERT_PATH"
    exit 1
  fi
fi

CLI_COMMAND="$CLI_COMMAND cluster nodes"

# --- Основная логика ---
# Выполняем команду и получаем информацию о узлах кластера. [1]
CLUSTER_NODES_OUTPUT=$(eval $CLI_COMMAND 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$CLUSTER_NODES_OUTPUT" ]; then
  echo "ERROR: Failed to execute redis-cli or connect to local Redis node on port $REDIS_PORT."
  exit 1
fi

# Извлекаем IP-адреса только активных master-узлов
MASTER_IPS=$(echo "$CLUSTER_NODES_OUTPUT" | grep 'master' | grep -v 'fail' | awk '{print $2}' | sed 's/:.*//')

declare -A DC_MASTER_COUNT
declare -A MASTER_TO_DC

# Заполняем информацию о ЦОД для каждого мастера
for IP in $MASTER_IPS; do
  DC=$(grep -w "$IP" "$DC_MAP_FILE" | awk '{print $2}')
  if [ -n "$DC" ]; then
    ((DC_MASTER_COUNT[$DC]++))
    MASTER_TO_DC[$IP]=$DC
  else
    # Если IP мастера не найден в файле карты - это тоже проблема
    echo "ERROR: Master with IP $IP not found in DC mapping file."
    exit 1
  fi
done

# Ищем ЦОД с количеством мастеров > 1 и формируем вывод
PROBLEM_OUTPUT=""
for DC in "${!DC_MASTER_COUNT[@]}"; do
  if [ "${DC_MASTER_COUNT[$DC]}" -gt 1 ]; then
    PROBLEM_IPS=""
    for IP in "${!MASTER_TO_DC[@]}"; do
      if [ "${MASTER_TO_DC[$IP]}" == "$DC" ]; then
        PROBLEM_IPS="$PROBLEM_IPS $IP"
      fi
    done
    # Формируем строку с информацией о проблеме
    PROBLEM_OUTPUT+="PROBLEM: Multiple masters found in DC '$DC'. IPs:${PROBLEM_IPS}. "
  fi
done

# Выводим результат. Пустая строка означает, что все в порядке.
echo "$PROBLEM_OUTPUT"

exit 0
```

**Настройка прав доступа (на каждом сервере):**
```sh
sudo mkdir -p /etc/zabbix/scripts
sudo chown -R zabbix:zabbix /etc/zabbix/scripts
sudo chmod 750 /etc/zabbix/scripts/check_redis_dc_masters.sh
```

### Шаг 3: Настройка Zabbix Агента

На **каждом** из 6 серверов добавьте следующую строку в файл конфигурации Zabbix агента (`/etc/zabbix/zabbix_agentd.conf`):

```
# Позволяет запускать скрипт проверки Redis HA
# Параметры передаются из ключа элемента данных в Zabbix UI
UserParameter=redis.ha.dc.check[*],/etc/zabbix/scripts/check_redis_dc_masters.sh "$1" "$2" "$3" "$4" "$5"
```

После изменения конфигурации **перезапустите Zabbix агент** на каждом сервере:
```sh
sudo systemctl restart zabbix-agent
```

### Шаг 4: Шаблон для Zabbix 6.4

Этот YAML-файл можно импортировать в Zabbix. Он содержит макросы для гибкой настройки, элемент данных для запуска скрипта и триггер, который срабатывает на проблему и включает в себя детали.

Файл `template_redis_ha_dc_check_agent.yml`:
```yaml
zabbix_export:
  version: '6.4'
  template_groups:
    - uuid: a571c0d144b14fd4a87a9d9b2aa9fcd6
      name: Templates/Applications
  templates:
    - uuid: 8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d
      template: 'Template App Redis HA DC Check Agent'
      name: 'Template App Redis HA DC Check Agent'
      description: |
        Monitors Redis Cluster for a situation where more than one master node is located in the same Data Center.
        
        This template uses a UserParameter on the Zabbix agent.
        
        Setup:
        1. Create a Redis user with ACL: `ACL SETUSER zabbix-monitor on >password +@cluster`
        2. Place the `check_redis_dc_masters.sh` script in `/etc/zabbix/scripts/` on each Redis node.
        3. Add `UserParameter=redis.ha.dc.check[*],/etc/zabbix/scripts/check_redis_dc_masters.sh "$1" "$2" "$3" "$4" "$5"` to zabbix_agentd.conf on each node and restart the agent.
        4. Apply this template to all Redis cluster nodes.
        5. Configure the macros {$REDIS.USER}, {$REDIS.PASSWORD}, etc., on the hosts or template.
      groups:
        - name: Templates/Applications
      macros:
        - macro: '{$REDIS.CACERT.PATH}'
          value: ''
          description: 'Optional: Full path to the Redis CA certificate for TLS verification.'
        - macro: '{$REDIS.DC_MAP.PATH}'
          value: '/etc/redis/redis_dc_map.txt'
          description: 'Full path to the file mapping IPs to Data Centers.'
        - macro: '{$REDIS.PASSWORD}'
          value: 'YourSecretPassword'
          description: 'Password for the Redis monitoring user.'
        - macro: '{$REDIS.PORT}'
          value: '6379'
          description: 'Port of the local Redis instance.'
        - macro: '{$REDIS.USER}'
          value: 'zabbix-monitor'
          description: 'Username for the Redis monitoring user (ACL).'
      items:
        - uuid: 5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b
          name: 'Redis: HA DC master distribution'
          type: ZABBIX_AGENT
          key: 'redis.ha.dc.check[{$REDIS.DC_MAP.PATH},{$REDIS.USER},{$REDIS.PASSWORD},{$REDIS.PORT},{$REDIS.CACERT.PATH}]'
          delay: 5m
          history: 7d
          value_type: TEXT
          description: |
            Checks the distribution of Redis master nodes across data centers.
            - Returns an empty string if OK.
            - Returns a descriptive problem string if more than one master is found in a single DC.
          tags:
            - tag: application
              value: Redis
      triggers:
        - uuid: f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6
          expression: 'strlen(last(/Template App Redis HA DC Check Agent/redis.ha.dc.check[{$REDIS.DC_MAP.PATH},{$REDIS.USER},{$REDIS.PASSWORD},{$REDIS.PORT},{$REDIS.CACERT.PATH}]))>0'
          name: 'High: More than one Redis master in a single DC ({HOST.NAME})'
          opdata: 'Details: {ITEM.LASTVALUE}'
          priority: HIGH
          description: |
            A failover event likely occurred, resulting in two or more Redis masters residing in the same data center. This violates the disaster recovery policy.
            Manual intervention is required to rebalance the masters.
            Problem details are in the trigger operational data.
          manual_close: 'YES'

```

### Шаг 5: Настройка в Zabbix

1.  **Импорт шаблона:**
    *   Перейдите в `Data collection` -> `Templates`.
    *   Нажмите `Import` и выберите файл `template_redis_ha_dc_check_agent.yml`.

2.  **Применение шаблона и настройка макросов:**
    *   Перейдите к **каждому из 6 хостов** вашего Redis кластера в Zabbix.
    *   На вкладке `Templates` привяжите новый шаблон `Template App Redis HA DC Check Agent`.
    *   Перейдите на вкладку `Macros` -> `Inherited and host macros`.
    *   **Обязательно** измените значения макросов, как минимум `{$REDIS.PASSWORD}`. Если пути или порт отличаются от значений по умолчанию, измените также `{$REDIS.DC_MAP.PATH}` и `{$REDIS.PORT}`. Если вы используете самоподписанные сертификаты, укажите путь в `{$REDIS.CACERT.PATH}`.

### Как это будет работать

1.  Каждые 5 минут Zabbix агент на каждом из 6 серверов будет запускать скрипт `check_redis_dc_masters.sh`.
2.  Скрипт подключится к локальному инстансу Redis по TLS, получит состояние всего кластера, проанализирует его и сравнит с картой ЦОД.
3.  Если все в порядке, скрипт вернет пустую строку. Элемент данных в Zabbix будет пустым.
4.  Если будет обнаружен ЦОД с двумя мастерами (например, `DC2` с мастерами `10.0.2.10` и `10.0.2.11`), скрипт вернет строку вида: `PROBLEM: Multiple masters found in DC 'DC2'. IPs: 10.0.2.10 10.0.2.11.`.
5.  Триггер, настроенный на проверку длины строки (`strlen(...)>0`), сработает.
6.  В Zabbix вы увидите алерт, и в поле "Operational data" (или в описании проблемы) будет выведена та самая строка с указанием ЦОД и IP-адресов, что позволит вам немедленно понять, где именно произошла проблема.

**Важное замечание:** Поскольку проверка выполняется на всех узлах, в случае проблемы вы получите 6 одинаковых алертов (по одному от каждого хоста). Это ожидаемое поведение при таком подходе. Вы можете сгруппировать их по тегам или использовать корреляцию событий в Zabbix, если хотите получать только одно уведомление на весь кластер.
