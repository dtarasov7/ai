Я помогу вам настроить мониторинг распределения master узлов Redis кластера по ЦОД. Вот решение:

## 1. Скрипты для Zabbix Agent

### Скрипт обнаружения узлов кластера
`/etc/zabbix/scripts/redis_cluster_discovery.sh`:

```bash
#!/bin/bash

# Параметры подключения
REDIS_HOST="localhost"
REDIS_PORT="6379"
REDIS_USER="zabbix_monitor"
REDIS_PASS="$1"
DC_FILE="/etc/redis/dc_mapping.txt"

# Получаем информацию о кластере
CLUSTER_NODES=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT --user $REDIS_USER --pass $REDIS_PASS --tls --cert /path/to/cert.pem --key /path/to/key.pem --cacert /path/to/ca.pem CLUSTER NODES 2>/dev/null)

if [ $? -ne 0 ]; then
    echo '{"data":[]}'
    exit 1
fi

# Формируем JSON для Zabbix discovery
echo '{"data":['
first=1

while IFS= read -r line; do
    [ -z "$line" ] && continue
    
    node_id=$(echo "$line" | awk '{print $1}')
    node_addr=$(echo "$line" | awk '{print $2}' | cut -d: -f1)
    node_port=$(echo "$line" | awk '{print $2}' | cut -d: -f2 | cut -d@ -f1)
    node_flags=$(echo "$line" | awk '{print $3}')
    master_id=$(echo "$line" | awk '{print $4}')
    
    # Определяем роль узла
    if echo "$node_flags" | grep -q "master"; then
        role="master"
    else
        role="slave"
    fi
    
    # Получаем ЦОД из файла
    dc=$(grep "^$node_addr" "$DC_FILE" | awk '{print $2}')
    
    [ $first -eq 0 ] && echo ","
    echo -n "{
        \"{#NODE_ID}\":\"$node_id\",
        \"{#NODE_ADDR}\":\"$node_addr\",
        \"{#NODE_PORT}\":\"$node_port\",
        \"{#NODE_ROLE}\":\"$role\",
        \"{#NODE_DC}\":\"$dc\",
        \"{#MASTER_ID}\":\"$master_id\"
    }"
    first=0
done <<< "$CLUSTER_NODES"

echo ']}'
```

### Скрипт проверки распределения master узлов
`/etc/zabbix/scripts/redis_cluster_check.sh`:

```bash
#!/bin/bash

# Параметры подключения
REDIS_HOST="localhost"
REDIS_PORT="6379"
REDIS_USER="zabbix_monitor"
REDIS_PASS="$1"
DC_FILE="/etc/redis/dc_mapping.txt"

# Получаем информацию о кластере
CLUSTER_NODES=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT --user $REDIS_USER --pass $REDIS_PASS --tls --cert /path/to/cert.pem --key /path/to/key.pem --cacert /path/to/ca.pem CLUSTER NODES 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "ERROR: Cannot connect to Redis"
    exit 1
fi

# Создаем ассоциативные массивы
declare -A dc_masters
declare -A node_info
declare -A master_slave_pairs

# Парсим информацию о узлах
while IFS= read -r line; do
    [ -z "$line" ] && continue
    
    node_id=$(echo "$line" | awk '{print $1}')
    node_addr=$(echo "$line" | awk '{print $2}' | cut -d: -f1)
    node_port=$(echo "$line" | awk '{print $2}' | cut -d: -f2 | cut -d@ -f1)
    node_flags=$(echo "$line" | awk '{print $3}')
    master_id=$(echo "$line" | awk '{print $4}')
    
    # Получаем ЦОД
    dc=$(grep "^$node_addr" "$DC_FILE" | awk '{print $2}')
    
    # Сохраняем информацию о узле
    node_info[$node_id]="$node_addr:$node_port|$dc"
    
    # Если это master, увеличиваем счетчик для ЦОД
    if echo "$node_flags" | grep -q "master"; then
        ((dc_masters[$dc]++))
        master_slave_pairs[$node_id]=""
    else
        # Если это slave, запоминаем пару master-slave
        master_slave_pairs[$master_id]=$node_id
    fi
done <<< "$CLUSTER_NODES"

# Проверяем распределение
problem_found=0
problem_details=""

for dc in "${!dc_masters[@]}"; do
    if [ ${dc_masters[$dc]} -gt 1 ]; then
        problem_found=1
        problem_details="${problem_details}DC $dc has ${dc_masters[$dc]} masters. "
        
        # Находим проблемные пары
        for master_id in "${!master_slave_pairs[@]}"; do
            slave_id=${master_slave_pairs[$master_id]}
            
            if [ -n "$slave_id" ]; then
                master_info=(${node_info[$master_id]//|/ })
                slave_info=(${node_info[$slave_id]//|/ })
                
                master_dc=${master_info[1]}
                slave_dc=${slave_info[1]}
                
                # Если master и slave в одном ЦОД
                if [ "$master_dc" == "$slave_dc" ] && [ "$master_dc" == "$dc" ]; then
                    problem_details="${problem_details}Master ${master_info[0]} and slave ${slave_info[0]} both in $dc. "
                    problem_details="${problem_details}Failover command: redis-cli -h ${slave_info[0]%:*} -p ${slave_info[0]#*:} --user $REDIS_USER --tls CLUSTER FAILOVER. "
                fi
            fi
        done
    fi
done

if [ $problem_found -eq 1 ]; then
    echo "$problem_details"
else
    echo "OK"
fi
```

### Скрипт для получения метрик узла
`/etc/zabbix/scripts/redis_node_info.sh`:

```bash
#!/bin/bash

NODE_ID="$1"
METRIC="$2"
REDIS_USER="zabbix_monitor"
REDIS_PASS="$3"
REDIS_HOST="localhost"
REDIS_PORT="6379"

# Получаем информацию о конкретном узле
NODE_INFO=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT --user $REDIS_USER --pass $REDIS_PASS --tls --cert /path/to/cert.pem --key /path/to/key.pem --cacert /path/to/ca.pem CLUSTER NODES 2>/dev/null | grep "^$NODE_ID")

case "$METRIC" in
    "role")
        if echo "$NODE_INFO" | grep -q "master"; then
            echo "master"
        else
            echo "slave"
        fi
        ;;
    "connected")
        if echo "$NODE_INFO" | grep -q "connected"; then
            echo "1"
        else
            echo "0"
        fi
        ;;
    *)
        echo "Unknown metric"
        ;;
esac
```

## 2. ACL права для пользователя Redis

Создайте пользователя с минимальными необходимыми правами:

```redis
ACL SETUSER zabbix_monitor on >your_password_here ~* &* -@all +cluster|nodes +cluster|info +cluster|slots +ping
```

## 3. Zabbix шаблон (YAML формат)

`redis_cluster_dc_monitoring.yaml`:

```yaml
zabbix_export:
  version: '6.4'
  template_groups:
    - uuid: 7df96b18c230490a9b8a000000000001
      name: Templates/Databases
  templates:
    - uuid: 8f5da09e4c4749d5b6f1000000000001
      template: 'Redis Cluster DC Distribution'
      name: 'Redis Cluster DC Distribution Monitoring'
      description: 'Monitor Redis cluster master nodes distribution across data centers'
      groups:
        - name: Templates/Databases
      items:
        - uuid: 8f5da09e4c4749d5b6f1000000000002
          name: 'Redis cluster DC distribution check'
          type: ZABBIX_ACTIVE
          key: 'redis.cluster.dc.check[{$REDIS_PASSWORD}]'
          delay: '60s'
          history: '7d'
          trends: '0'
          value_type: TEXT
          description: 'Check if master nodes are properly distributed across DCs'
          preprocessing:
            - type: TRIM
              parameters:
                - ''
          tags:
            - tag: component
              value: redis
            - tag: type
              value: cluster
      discovery_rules:
        - uuid: 8f5da09e4c4749d5b6f1000000000003
          name: 'Redis cluster nodes discovery'
          type: ZABBIX_ACTIVE
          key: 'redis.cluster.discovery[{$REDIS_PASSWORD}]'
          delay: '300s'
          lifetime: '1d'
          description: 'Discover Redis cluster nodes'
          item_prototypes:
            - uuid: 8f5da09e4c4749d5b6f1000000000004
              name: 'Node {#NODE_ADDR}:{#NODE_PORT} role'
              type: ZABBIX_ACTIVE
              key: 'redis.node.info[{#NODE_ID},role,{$REDIS_PASSWORD}]'
              delay: '60s'
              history: '7d'
              trends: '0'
              value_type: TEXT
              tags:
                - tag: node
                  value: '{#NODE_ADDR}:{#NODE_PORT}'
                - tag: dc
                  value: '{#NODE_DC}'
            - uuid: 8f5da09e4c4749d5b6f1000000000005
              name: 'Node {#NODE_ADDR}:{#NODE_PORT} connected'
              type: ZABBIX_ACTIVE
              key: 'redis.node.info[{#NODE_ID},connected,{$REDIS_PASSWORD}]'
              delay: '30s'
              history: '7d'
              value_type: UNSIGNED
              tags:
                - tag: node
                  value: '{#NODE_ADDR}:{#NODE_PORT}'
      triggers:
        - uuid: 8f5da09e4c4749d5b6f1000000000006
          expression: 'last(/Redis Cluster DC Distribution/redis.cluster.dc.check[{$REDIS_PASSWORD}])<>"OK"'
          name: 'Redis cluster: Multiple masters in same DC'
          priority: HIGH
          description: |
            Multiple master nodes detected in the same datacenter.
            This can happen after a failover and reduces fault tolerance.
            
            Problem details: {ITEM.LASTVALUE}
          manual_close: 'YES'
          tags:
            - tag: scope
              value: availability
      macros:
        - macro: '{$REDIS_PASSWORD}'
          value: 'your_redis_password'
          description: 'Redis user password for monitoring'
  graphs: []
  graph_prototypes: []
```

## 4. Настройка Zabbix Agent

Добавьте в конфигурацию агента `/etc/zabbix/zabbix_agentd.conf`:

```ini
# Redis cluster monitoring
UserParameter=redis.cluster.discovery[*],/etc/zabbix/scripts/redis_cluster_discovery.sh "$1"
UserParameter=redis.cluster.dc.check[*],/etc/zabbix/scripts/redis_cluster_check.sh "$1"
UserParameter=redis.node.info[*],/etc/zabbix/scripts/redis_node_info.sh "$1" "$2" "$3"
```

## 5. Установка и настройка

1. Создайте директорию для скриптов:
```bash
mkdir -p /etc/zabbix/scripts
chmod 755 /etc/zabbix/scripts
```

2. Скопируйте скрипты и сделайте их исполняемыми:
```bash
chmod +x /etc/zabbix/scripts/*.sh
chown zabbix:zabbix /etc/zabbix/scripts/*.sh
```

3. Создайте файл с маппингом ЦОД `/etc/redis/dc_mapping.txt` с содержимым из вашего примера.

4. Настройте TLS сертификаты в скриптах (замените пути на актуальные).

5. Создайте пользователя в Redis с необходимыми правами.

6. Импортируйте шаблон в Zabbix и примените его к хостам кластера.

7. Установите макрос `{$REDIS_PASSWORD}` с паролем пользователя мониторинга.

При срабатывании триггера вы получите подробную информацию о проблеме, включая команды для ручного переключения master-slave ролей.
