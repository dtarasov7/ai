Отлично, это очень интересный и правильный сценарий для обеспечения катастрофоустойчивости Redis кластера. Мониторинг такой ситуации действительно важен, чтобы вручную или автоматически возвращать кластер в сбалансированное состояние.

Вот полное решение для мониторинга с использованием Zabbix, включающее права для пользователя Redis, скрипт для агента и шаблон для Zabbix.

### 1. Права доступа для пользователя Redis (ACL)

Для выполнения команд `CLUSTER NODES` (для получения карты кластера) и `CLUSTER FAILOVER` (которая будет в подсказке триггера) пользователю Zabbix необходимы права на работу с кластером. Создайте пользователя с минимально необходимыми привилегиями.

**Команда для создания пользователя:**
```shell
# Подключитесь к любому master-узлу кластера
redis-cli -h 10.0.1.10 -p 6379 --tls

# Введите пароль администратора, если требуется
AUTH <admin_user> <admin_password>

# Создайте пользователя zabbix с паролем и правами
ACL SETUSER zabbix on >YourStrongPasswordHere +@cluster

# Сохраните конфигурацию ACL
ACL SAVE
```
*   `zabbix`: имя пользователя.
*   `YourStrongPasswordHere`: **обязательно** замените на надежный пароль.
*   `+@cluster`: предоставляет доступ ко всем командам категории `CLUSTER`, что является безопасным и достаточным для нашей задачи.

### 2. Скрипт для Zabbix Агента

Этот скрипт будет выполнять основную логику: подключаться к локальному узлу Redis, анализировать состояние всего кластера, находить дата-центры с более чем одним мастером и формировать JSON для Zabbix.

Создайте файл `/etc/zabbix/scripts/redis_dc_check.sh` на **каждом** сервере кластера.

```bash
#!/bin/bash

# redis_dc_check.sh - Скрипт для Zabbix для проверки распределения мастеров Redis по ЦОД.

# --- Параметры подключения ---
# Эти значения будут переданы из Zabbix
REDIS_USER="$1"
REDIS_PASS="$2"
REDIS_HOST="127.0.0.1" # Всегда проверяем через локальный узел
REDIS_PORT="$3" # Порт мастер-узла на локальном сервере

# --- Конфигурационные файлы ---
DC_MAP_FILE="/etc/redis-dc-mapping.txt" # Файл с соответствием IP -> ЦОД

# --- Проверки ---
if ! command -v redis-cli &> /dev/null; then
    echo "{\"error\":\"redis-cli not found\"}"
    exit 1
fi

if [ ! -f "$DC_MAP_FILE" ]; then
    echo "{\"error\":\"DC mapping file not found at $DC_MAP_FILE\"}"
    exit 1
fi

# --- Основная логика ---

# 1. Загружаем карту ЦОД в ассоциативный массив (IP -> DC)
declare -A dc_map
while read -r ip dc; do
    dc_map["$ip"]="$dc"
done < "$DC_MAP_FILE"

# 2. Получаем информацию о узлах кластера
# Используем формат rediss:// для подключения с TLS
cluster_nodes_output=$(redis-cli rediss://"${REDIS_USER}":"${REDIS_PASS}"@"${REDIS_HOST}":"${REDIS_PORT}" CLUSTER NODES 2>/dev/null)

if [ -z "$cluster_nodes_output" ]; then
    echo "{\"error\":\"Failed to connect to Redis or get cluster nodes. Check credentials or TLS settings.\"}"
    exit 1
fi

# 3. Анализируем вывод CLUSTER NODES
declare -A dc_master_count # Счетчик мастеров в каждом ЦОД (DC -> count)
declare -A dc_masters_info # Информация о мастерах в каждом ЦОД (DC -> "ip1 ip2...")
declare -A node_info       # Карта: node_id -> "ip:port role master_id"
declare -A ip_to_nodeid    # Карта: ip:port -> node_id

while read -r line; do
    node_id=$(echo "$line" | awk '{print $1}')
    ip_port=$(echo "$line" | awk '{print $2}' | sed 's/@.*//')
    role=$(echo "$line" | awk '{print $3}' | sed 's/,//')
    master_id=$(echo "$line" | awk '{print $4}')
    
    ip=$(echo "$ip_port" | cut -d: -f1)
    
    node_info["$node_id"]="$ip_port $role $master_id"
    ip_to_nodeid["$ip_port"]="$node_id"

    if [[ "$role" == "master" ]]; then
        dc=${dc_map[$ip]}
        if [ -n "$dc" ]; then
            ((dc_master_count[$dc]++))
            dc_masters_info["$dc"]+="$ip_port "
        fi
    fi
done <<< "$cluster_nodes_output"


# 4. Формируем JSON для вывода
# Этот JSON будет содержать два основных блока:
# "discovery": для LLD Zabbix, чтобы обнаружить все ЦОД.
# "problems": для LLD, чтобы обнаружить только проблемные ЦОД и сформировать команду для исправления.

# Формируем блок "discovery"
discovery_json="["
first_dc=true
for dc in "${!dc_master_count[@]}"; do
    if ! $first_dc; then discovery_json+=","; fi
    discovery_json+="{\"{#DCNAME}\":\"$dc\",\"masters\":${dc_master_count[$dc]}}"
    first_dc=false
done
discovery_json+="]"

# Формируем блок "problems"
problems_json="["
first_problem=true
for dc in "${!dc_master_count[@]}"; do
    if (( ${dc_master_count[$dc]} > 1 )); then
        if ! $first_problem; then problems_json+=","; fi
        
        # Находим пару "неправильный" мастер и его "бывший" мастер (теперь слейв)
        # Логика: в проблемном ЦОД есть два мастера. Один из них - "стабильный", другой - "продвинутый" (бывший слейв).
        # Нам нужно найти "продвинутого" мастера и его нового слейва (бывшего мастера), чтобы предложить команду failover.
        
        problem_masters=(${dc_masters_info[$dc]})
        master1_ip_port=${problem_masters[0]}
        master2_ip_port=${problem_masters[1]}
        
        master1_id=${ip_to_nodeid[$master1_ip_port]}
        master2_id=${ip_to_nodeid[$master2_ip_port]}
        
        # Ищем слейва, который реплицируется с одного из этих мастеров
        remediation_cmd="Manual check required."
        remediation_pair=""
        
        while read -r line; do
            role=$(echo "$line" | awk '{print $3}' | sed 's/,//')
            if [[ "$role" == "slave" ]]; then
                current_node_id=$(echo "$line" | awk '{print $1}')
                master_of_slave_id=$(echo "$line" | awk '{print $4}')
                
                # Если слейв реплицируется с master1, то команда failover должна быть нацелена на этого слейва
                if [[ "$master_of_slave_id" == "$master1_id" ]]; then
                    remediation_pair="Master $master1_ip_port -> Slave $current_node_id"
                    remediation_cmd="redis-cli rediss://${REDIS_USER}:*****@${master1_ip_port} CLUSTER FAILOVER ${current_node_id}"
                    break
                fi
                # Если слейв реплицируется с master2
                if [[ "$master_of_slave_id" == "$master2_id" ]]; then
                    remediation_pair="Master $master2_ip_port -> Slave $current_node_id"
                    remediation_cmd="redis-cli rediss://${REDIS_USER}:*****@${master2_ip_port} CLUSTER FAILOVER ${current_node_id}"
                    break
                fi
            fi
        done <<< "$cluster_nodes_output"

        problems_json+="{\"{#PROBLEM_DC}\":\"$dc\", \"masters\":\"${dc_masters_info[$dc]}\", \"pair\":\"$remediation_pair\", \"command\":\"$remediation_cmd\"}"
        first_problem=false
    fi
done
problems_json+="]"


# Финальный JSON
echo "{\"discovery\":$discovery_json, \"problems\":$problems_json}"

```

**Настройка скрипта:**
1.  Сделайте скрипт исполняемым: `chmod +x /etc/zabbix/scripts/redis_dc_check.sh`.
2.  Убедитесь, что пользователь `zabbix` имеет право на выполнение этого скрипта.

### 3. Настройка Zabbix Агента

Добавьте `UserParameter` в конфигурационный файл вашего Zabbix агента (например, `/etc/zabbix/zabbix_agentd.conf` или в файл в директории `/etc/zabbix/zabbix_agentd.d/`).

Создайте файл `/etc/zabbix/zabbix_agentd.d/redis_cluster.conf`:
```ini
UserParameter=redis.cluster.dc.check[*],/etc/zabbix/scripts/redis_dc_check.sh "$1" "$2" "$3"
```
*   `$1`, `$2`, `$3` будут соответствовать пользователю, паролю и порту, которые мы передадим из Zabbix UI.

После добавления **перезапустите Zabbix агент**:
```shell
systemctl restart zabbix-agent
```

### 4. Шаблон для Zabbix

Этот YAML-шаблон можно импортировать в Zabbix (в разделе `Data collection` -> `Templates`).

```yaml
zabbix_export:
  version: '6.4'
  template_groups:
    - uuid: a571c0d1d5534318a8833a51d443221a
      name: Templates/Databases
  templates:
    - uuid: c1b2d3e4f5a64b7c8d9e0f1a2b3c4d5e
      name: 'Redis Cluster DC Integrity'
      description: |
        Monitors that no more than one Redis master is running in a single data center.
        
        Requirements:
        1. Zabbix Agent with UserParameter `redis.cluster.dc.check[*]`.
        2. A script `/etc/zabbix/scripts/redis_dc_check.sh`.
        3. A mapping file `/etc/redis-dc-mapping.txt` on each Redis host.
        4. Macros {$REDIS_USER}, {$REDIS_PASS}, {$REDIS_MASTER_PORT} must be configured on the host.
      groups:
        - name: Templates/Databases
      macros:
        - macro: '{$REDIS_MASTER_PORT}'
          value: '6379'
          description: 'Port of the local Redis master node.'
        - macro: '{$REDIS_PASS}'
          value: ''
          description: 'ACL password for the zabbix user.'
          type: SECRET_TEXT
        - macro: '{$REDIS_USER}'
          value: 'zabbix'
          description: 'ACL username for Redis monitoring.'
      items:
        - uuid: a1b2c3d4e5f64a7b8c9d0e1f2a3b4c5d
          name: 'Redis: DC Master Distribution Check'
          type: ZABBIX_AGENT
          key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$REDIS_MASTER_PORT}]'
          delay: 5m
          history: 2d
          trends: '0'
          value_type: TEXT
          description: 'Retrieves a JSON object with master distribution across data centers.'
      discovery_rules:
        - uuid: b1c2d3e4f5a64b7c8d9e0f1a2b3c4d5f
          name: 'Redis DC Discovery'
          type: DEPENDENT
          key: redis.dc.discovery
          master_item:
            key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$REDIS_MASTER_PORT}]'
          delay: '0'
          preprocessing:
            - type: JSONPATH
              parameters:
                - '$.discovery'
          item_prototypes:
            - uuid: c1d2e3f4a5b64c7d8e9f0a1b2c3d4e5a
              name: 'Redis: Number of masters in DC {#DCNAME}'
              type: DEPENDENT
              key: 'redis.cluster.masters.count[{#DCNAME}]'
              master_item:
                key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$REDIS_MASTER_PORT}]'
              delay: '0'
              history: 7d
              preprocessing:
                - type: JSONPATH
                  parameters:
                    - '$[?(@.''{#DCNAME}'' == ''{#DCNAME}'')].masters.first()'
                - type: DISCARD_UNCHANGED
          trigger_prototypes:
            - uuid: d1e2f3a4b5c64d7e8f9a0b1c2d3e4f5b
              expression: 'last(/Redis Cluster DC Integrity/redis.cluster.masters.count[{#DCNAME}])>1'
              name: 'More than one Redis master in DC {#DCNAME}'
              opdata: 'Masters: {ITEM.VALUE2}, Pair: {ITEM.VALUE3}'
              description: |
                Problem: More than one active Redis master detected in data center {#DCNAME}. This violates the DR strategy.
                
                Detected Masters: {ITEM.VALUE2}
                Identified Problematic Pair: {ITEM.VALUE3}
                
                Recommended command to fix (run from any server with redis-cli):
                {ITEM.VALUE4}
                
                This command will initiate a manual failover, promoting the slave back to master and restoring the correct cluster topology.
              priority: HIGH
              dependencies:
                - name: 'Redis Problem Details for DC {#DCNAME}'
                  expression: 'last(/Redis Cluster DC Integrity/redis.problem.dc.name[{#DCNAME}])=''{#DCNAME}'''
        - uuid: e1f2a3b4c5d64e7f8a9b0c1d2e3f4a5c
          name: 'Redis Problem Details Discovery'
          type: DEPENDENT
          key: redis.problem.discovery
          master_item:
            key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$REDIS_MASTER_PORT}]'
          delay: '0'
          preprocessing:
            - type: JSONPATH
              parameters:
                - '$.problems'
          item_prototypes:
            - uuid: f1a2b3c4d5e64f7a8b9c0d1e2f3a4b5d
              name: 'Redis Problem: DC Name for {#PROBLEM_DC}'
              type: DEPENDENT
              key: 'redis.problem.dc.name[{#PROBLEM_DC}]'
              master_item:
                key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$REDIS_MASTER_PORT}]'
              delay: '0'
              history: 2d
              trends: '0'
              value_type: TEXT
              preprocessing:
                - type: JSONPATH
                  parameters:
                    - '$[?(@.''{#PROBLEM_DC}'' == ''{#PROBLEM_DC}'')].''{#PROBLEM_DC}''.first()'
            - uuid: a2b3c4d5e6f74a8b9c0d1e2f3a4b5c6d
              name: 'Redis Problem: Masters in {#PROBLEM_DC}'
              type: DEPENDENT
              key: 'redis.problem.masters[{#PROBLEM_DC}]'
              master_item:
                key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$REDIS_MASTER_PORT}]'
              delay: '0'
              history: 2d
              trends: '0'
              value_type: TEXT
              preprocessing:
                - type: JSONPATH
                  parameters:
                    - '$[?(@.''{#PROBLEM_DC}'' == ''{#PROBLEM_DC}'')].masters.first()'
            - uuid: b2c3d4e5f6a74b8c9d0e1f2a3b4c5d6e
              name: 'Redis Problem: Pair in {#PROBLEM_DC}'
              type: DEPENDENT
              key: 'redis.problem.pair[{#PROBLEM_DC}]'
              master_item:
                key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$REDIS_MASTER_PORT}]'
              delay: '0'
              history: 2d
              trends: '0'
              value_type: TEXT
              preprocessing:
                - type: JSONPATH
                  parameters:
                    - '$[?(@.''{#PROBLEM_DC}'' == ''{#PROBLEM_DC}'')].pair.first()'
            - uuid: c2d3e4f5a6b74c8d9e0f1a2b3c4d5e6f
              name: 'Redis Problem: Remediation command for {#PROBLEM_DC}'
              type: DEPENDENT
              key: 'redis.problem.remediation[{#PROBLEM_DC}]'
              master_item:
                key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$REDIS_MASTER_PORT}]'
              delay: '0'
              history: 2d
              trends: '0'
              value_type: TEXT
              preprocessing:
                - type: JSONPATH
                  parameters:
                    - '$[?(@.''{#PROBLEM_DC}'' == ''{#PROBLEM_DC}'')].command.first()'

```

### Как все это работает вместе:

1.  **Применение шаблона:** Вы применяете шаблон `Redis Cluster DC Integrity` ко всем трем хостам вашего кластера в Zabbix.
2.  **Настройка макросов:** На каждом хосте в Zabbix вы должны переопределить макросы `{$REDIS_USER}` и `{$REDIS_PASS}` (установите пароль как "Secret text"), указав учетные данные созданного пользователя Redis. `{$REDIS_MASTER_PORT}` по умолчанию `6379`, что соответствует вашей конфигурации.
3.  **Сбор данных:** Каждые 5 минут (настраивается в `delay`) Zabbix агент на каждом хосте будет запускать скрипт `redis_dc_check.sh`.
4.  **Работа скрипта:** Скрипт подключается к локальному Redis, получает карту всего кластера, анализирует ее и возвращает единый JSON.
5.  **Обнаружение (LLD):**
    *   **Первое правило (`Redis DC Discovery`)** парсит ключ `"discovery"` из JSON и создает для каждого ЦОД (`DC1`, `DC2`, `DC3`) элемент данных, который хранит количество мастеров в этом ЦОД.
    *   **Второе правило (`Redis Problem Details Discovery`)** парсит ключ `"problems"`. Оно создает элементы данных (IP-адреса мастеров, пара master-slave, команда для исправления) **только для тех ЦОД, где есть проблема**.
6.  **Срабатывание триггера:**
    *   На первое правило обнаружения навешан прототип триггера. Он сработает, если значение элемента `Number of masters in DC {#DCNAME}` станет больше 1.
    *   В описании триггера используются макросы `{ITEM.VALUE2}`, `{ITEM.VALUE3}` и `{ITEM.VALUE4}`, которые подставят значения из элементов данных, созданных вторым правилом обнаружения.
    *   В итоге вы получите алерт, который будет выглядеть примерно так:

> **Problem: More than one Redis master in DC DC2**
>
> Problem: More than one active Redis master detected in data center DC2. This violates the DR strategy.
>
> Detected Masters: 10.0.2.10:6379 10.0.2.10:6380
>
> Identified Problematic Pair: Master 10.0.2.10:6380 -> Slave <id-бывшего-мастера>
>
> Recommended command to fix (run from any server with redis-cli):
> `redis-cli rediss://zabbix:*****@10.0.2.10:6380 CLUSTER FAILOVER <id-бывшего-мастера>`

Это решение полностью автоматизирует обнаружение проблемы и предоставляет всю необходимую информацию для ее быстрого устранения.
