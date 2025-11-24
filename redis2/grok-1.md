```yaml
---
zabbix_export:
  version: '6.4'
  date: '2023-10-01T00:00:00Z'  # Placeholder; adjust as needed
  groups:
    - name: Templates/Applications  # Assuming a group; adjust to your Zabbix setup
  templates:
    - template: 'Redis Cluster DC Balance'
      name: 'Redis Cluster DC Balance'
      description: 'Template for monitoring Redis cluster master distribution across DCs to detect imbalances (e.g., multiple masters in one DC).'
      groups:
        - name: Templates/Applications
      applications:
        - name: 'Redis Cluster'
      items:
        - name: 'Redis DC Balance Check'
          description: 'Checks if there are multiple masters in any single DC. Returns "OK" if balanced, or a detailed string with imbalance info, affected pair, and failover command if imbalanced.'
          type: ZABBIX_ACTIVE  # Or ZABBIX_PASSIVE if preferred; assumes agent active mode
          key: 'redis.dc.balance'
          delay: '1m'  # Update every 1 minute; adjust as needed
          history: '7d'
          trends: '0'  # Text item, no trends
          value_type: TEXT
          applications:
            - name: 'Redis Cluster'
          preprocessing: []  # No preprocessing needed
      triggers:
        - expression: '{Redis Cluster DC Balance:redis.dc.balance.strlen()}>0'
          name: 'Redis Cluster DC Imbalance Detected'
          description: "Imbalance in Redis master distribution across DCs.\nDetails: {ITEM.VALUE1}"
          priority: HIGH  # Severity: High
          manual_close: 'YES'  # Allow manual close after fix
          dependencies: []  # No dependencies
```

### Инструкции по настройке

#### 1. **ACL для пользователя в Redis**
Для мониторинга кластера требуется пользователь с минимальными правами на чтение информации о кластере. Не предоставляйте права на опасные команды (например, CLUSTER FAILOVER, SHUTDOWN и т.д.), так как это только для мониторинга.

Создайте пользователя в Redis (на всех нодах кластера, или используйте ACL файл для распространения):
```
ACL SETUSER monitor ON >your_secure_password +ping +info +cluster allchannels
```
- **Пояснения по правам**:
  - `+ping`: Для проверки соединения.
  - `+info`: Для получения общей информации (если нужно, например, INFO replication).
  - `+cluster`: Позволяет выполнять все CLUSTER команды, включая CLUSTER NODES и CLUSTER INFO (необходимы для парсинга структуры кластера). Это включает подкоманды вроде `nodes` и `info`.
  - `allchannels`: Если используются Pub/Sub, но опционально; можно убрать, если не нужно.
  - Не добавляйте `+cluster|failover` или другие write-команды — мониторинг только на чтение.
  - Замените `your_secure_password` на реальный пароль.
  - Если хотите минимизировать ещё больше, можно попробовать `+cluster~nodes +cluster~info`, но в Redis ACL это может не сработать для субкоманд — тестируйте.

Авторизация: Пользователь `monitor` будет использоваться в скрипте для подключения.

Для ручного failover (в команде из триггера) используйте привилегированного пользователя (например, default или отдельного admin с правами `+cluster` включая failover). Мониторинговый пользователь не должен иметь прав на failover.

#### 2. **Настройка Zabbix Agent**
- Установите Zabbix Agent v1 (как указано) на всех 6 серверах кластера.
- Добавьте в конфигурацию Zabbix Agent (`/etc/zabbix/zabbix_agentd.conf` или аналогичный):
  ```
  UserParameter=redis.dc.balance,/path/to/redis_dc_balance.sh
  ```
  - Замените `/path/to/redis_dc_balance.sh` на реальный путь к скрипту (см. ниже).
  - Перезапустите агент: `systemctl restart zabbix-agent` (или аналогично).

- Убедитесь, что файл с маппингом DC существует на каждом сервере: `/etc/redis/dc_mapping.txt` (или укажите свой путь в скрипте). Содержимое:
  ```
  10.0.1.10 DC1
  10.0.1.11 DC1
  10.0.2.10 DC2
  10.0.2.11 DC2
  10.0.3.10 DC3
  10.0.3.11 DC3
  ```

- Предполагается, что Redis слушает на стандартном порту 6379. TLS сертификаты должны быть доступны (укажите пути в скрипте).

#### 3. **Скриプト для Zabbix Agent (`redis_dc_balance.sh`)**
Сохраните этот скрипт на всех серверах (например, в `/usr/local/bin/redis_dc_balance.sh`), сделайте исполняемым (`chmod +x /usr/local/bin/redis_dc_balance.sh`).

```bash
#!/bin/bash

# Configuration
DC_MAPPING_FILE="/etc/redis/dc_mapping.txt"  # Path to DC mapping file
REDIS_PORT=6379  # Redis port
REDIS_USER="monitor"  # Monitoring user
REDIS_PASS="your_secure_password"  # Replace with actual password
CA_CERT="/path/to/ca.crt"  # Path to CA cert for TLS
CLIENT_CERT="/path/to/client.crt"  # Path to client cert
CLIENT_KEY="/path/to/client.key"  # Path to client key
# If using self-signed or no client certs, add --insecure and remove --cert/--key

# Read DC mapping into associative array
declare -A IP_TO_DC
while IFS= read -r line; do
  ip=$(echo "$line" | awk '{print $1}')
  dc=$(echo "$line" | awk '{print $2}')
  IP_TO_DC["$ip"]="$dc"
done < "$DC_MAPPING_FILE"

# Connect to local Redis and get CLUSTER NODES
CLUSTER_NODES=$(redis-cli --tls --cacert "$CA_CERT" --cert "$CLIENT_CERT" --key "$CLIENT_KEY" -u "rediss://$REDIS_USER:$REDIS_PASS@127.0.0.1:$REDIS_PORT" --raw CLUSTER NODES 2>/dev/null)

if [ -z "$CLUSTER_NODES" ]; then
  echo "ERROR: Failed to connect to Redis or retrieve CLUSTER NODES."
  exit 1
fi

# Parse CLUSTER NODES
declare -A MASTERS
declare -A DC_COUNTS
declare -A SLAVES  # To map master_id -> list of slave ips/dcs

while read -r line; do
  node_id=$(echo "$line" | awk '{print $1}')
  ip_port=$(echo "$line" | awk '{print $2}')
  ip=$(echo "$ip_port" | cut -d':' -f1)
  flags=$(echo "$line" | awk '{print $3}')
  master_id=$(echo "$line" | awk '{print $4}')

  dc=${IP_TO_DC["$ip"]}
  if [ -z "$dc" ]; then
    echo "ERROR: Unknown DC for IP $ip"
    exit 1
  fi

  if [[ "$flags" == *"master"* ]] && [[ "$flags" != *"fail"* ]]; then
    MASTERS["$node_id"]="$ip:$REDIS_PORT $dc"
    ((DC_COUNTS["$dc"]++))
    SLAVES["$node_id"]=""  # Initialize slaves list
  elif [[ "$flags" == *"slave"* ]]; then
    if [ "$master_id" != "-" ]; then
      SLAVES["$master_id"]="${SLAVES["$master_id"]} $ip:$REDIS_PORT $dc"
    fi
  fi
done <<< "$CLUSTER_NODES"

# Find crowded ( >1 master) and empty (0 master) DCs
CROWDED_DCS=()
EMPTY_DCS=()
for dc in "${!DC_COUNTS[@]}"; do
  count=${DC_COUNTS["$dc"]}
  if [ "$count" -gt 1 ]; then
    CROWDED_DCS+=("$dc ($count masters)")
  elif [ "$count" -eq 0 ]; then
    EMPTY_DCS+=("$dc")
  fi
done

if [ ${#CROWDED_DCS[@]} -eq 0 ]; then
  echo "OK"
  exit 0
fi

# Find problematic pairs: masters in crowded DC with slave in empty DC
OUTPUT="Imbalance detected. Crowded DCs: ${CROWDED_DCS[*]}. Empty DCs: ${EMPTY_DCS[*]}."
CANDIDATES=()

for master_id in "${!MASTERS[@]}"; do
  master_info=${MASTERS["$master_id"]}
  master_ip_port=$(echo "$master_info" | awk '{print $1}')
  master_dc=$(echo "$master_info" | awk '{print $2}')
  
  if [[ " ${CROWDED_DCS[*]} " =~ " $master_dc " ]]; then
    slaves=${SLAVES["$master_id"]}
    for slave in $slaves; do
      if [ -n "$slave" ]; then  # Skip empty
        slave_ip_port=$(echo "$slave" | awk '{print $1}')
        slave_dc=$(echo "$slave" | awk '{print $2}')
        if [[ " ${EMPTY_DCS[*]} " =~ " $slave_dc " ]]; then
          CANDIDATES+=("Pair: master $master_ip_port ($master_dc) -> slave $slave_ip_port ($slave_dc). Command for manual failover (run on slave's server): redis-cli --tls --cacert /path/to/ca.crt --cert /path/to/client.crt --key /path/to/client.key -u \"rediss://admin:admin_pass@$slave_ip_port\" CLUSTER FAILOVER")
        fi
      fi
    done
  fi
done

if [ ${#CANDIDATES[@]} -eq 0 ]; then
  OUTPUT="$OUTPUT No clear failover candidates found (no slaves in empty DCs)."
else
  OUTPUT="$OUTPUT Suggested fixes:"
  for candidate in "${CANDIDATES[@]}"; do
    OUTPUT="$OUTPUT\n- $candidate"
  done
fi

echo "$OUTPUT"
```

- **Пояснения по скрипту**:
  - Скрипт подключается к локальному Redis (localhost) для получения глобальной информации о кластере (CLUSTER NODES работает на любом ноде).
  - Парсит структуру, считает мастеры по DC.
  - Детектирует "причину": пары, где мастер в перегруженном DC, а слейв в пустом DC (это указывает на недавний failover без балансировки).
  - Выводит детали и команду для failover (используйте привилегированного пользователя `admin:admin_pass` — замените на реальные; пути к сертификатам тоже замените).
  - Если несколько пар, перечислит все.
  - Если ошибка, выводит ERROR (триггер не сработает, но проверьте логи).

#### 4. **Импорт шаблона в Zabbix**
- Сохраните YAML в файл (например, `redis_template.yaml`).
- В Zabbix UI: Configuration > Templates > Import > Выберите файл > Import.
- Примените шаблон ко всем 6 хостам (серверам кластера).

#### 5. **Тестирование**
- Симулируйте failover, проверьте item `redis.dc.balance` в Zabbix (Latest data).
- При имбалансе триггер сработает, и в описании проблемы будет полный текст с парой и командой.
- После ручного failover (используя предложенную команду) баланс восстановится, item вернёт "OK", триггер разрешится.
