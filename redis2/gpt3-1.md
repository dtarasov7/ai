Ниже приведён полный-рабочий комплект для Zabbix 6.4, предназначенный для обнаружения ситуации, когда после аварийного переключения два master-узла оказываются в одном и том же дата-центре.

Содержимое включает  
• YAML-шаблон;  
• три shell-скрипта (discovery, проверка распределения, получение метрик узла);  
• UserParameter’ы для zabbix-agent v1;  
• минимальный ACL-профиль Redis;  
• краткую инструкцию по установке.

──────────────────────────────────────────────────────────────────────────────
1. ACL-пользователь Redis
──────────────────────────────────────────────────────────────────────────────
Создайте пользователя (имя по умолчанию zabbix_monitor). Права сведены к
минимально-необходимым для чтения кластера и (при ручном вмешательстве)
выполнения CLUSTER FAILOVER:

```
ACL SETUSER zabbix_monitor on >StrongPa55 \
    ~*                                 \          # доступ к любым ключам не нужен, но ~* проще, т.к. мы ничего не читаем
    -@all                              \          # убрать все категории
    +ping +auth                        \          # базовые
    +cluster|nodes +cluster|info +cluster|myid    # мониторинг
    +cluster|failover                             # команда, которую админ сможет выполнить вручную
```

──────────────────────────────────────────────────────────────────────────────
2. Скрипты (путь /opt/zabbix/scripts)
──────────────────────────────────────────────────────────────────────────────
Все скрипты принимают одинаковые параметры (передаются Zabbix-агентом):

```
$1 – пользователь Redis
$2 – пароль
$3 – путь к ca.pem
$4 – путь к client.crt
$5 – путь к client.key
```

Файл с привязкой «IP ⇒ DC» (dc_mapping.txt) располагается на каждом узле
и передаётся в скрипты как переменная DC_FILE.

2.1 redis_cluster_discovery.sh
──────────────────────────────
```bash
#!/bin/bash
set -euo pipefail

REDIS_USER="$1"; REDIS_PASS="$2"
CA="$3"; CERT="$4"; KEY="$5"
DC_FILE="/etc/redis/dc_mapping.txt"
CLI="redis-cli --tls --cacert $CA --cert $CERT --key $KEY \
      --user $REDIS_USER --pass $REDIS_PASS -h 127.0.0.1"

# снимаем CLUSTER NODES одним вызовом
NODES="$($CLI CLUSTER NODES)"

echo '{"data":['
first=1
while read -r line; do
  [[ -z "$line" ]] && continue
  nid=$(awk '{print $1}' <<<"$line")
  addr=$(awk '{print $2}' <<<"$line" | cut -d@ -f1)      # ip:port
  ip=${addr%:*}; port=${addr#*:}
  flags=$(awk '{print $3}' <<<"$line")
  role=$(grep -q master <<<"$flags" && echo master || echo slave)
  dc=$(awk -vip="$ip" '$1==ip{print $2}' "$DC_FILE")

  [[ $first -eq 0 ]] && echo ","
  printf '{"{#NODE_ID}":"%s","{#NODE_IP}":"%s","{#NODE_PORT}":"%s","{#NODE_ROLE}":"%s","{#NODE_DC}":"%s"}' \
          "$nid" "$ip" "$port" "$role" "$dc"
  first=0
done <<<"$NODES"
echo ']}'
```

2.2 redis_cluster_check.sh
──────────────────────────
```bash
#!/bin/bash
set -euo pipefail

REDIS_USER="$1"; REDIS_PASS="$2"
CA="$3"; CERT="$4"; KEY="$5"
DC_FILE="/etc/redis/dc_mapping.txt"
CLI="redis-cli --tls --cacert $CA --cert $CERT --key $KEY \
      --user $REDIS_USER --pass $REDIS_PASS -h 127.0.0.1"

declare -A dc_master_cnt master_dc node_ip_port slaves_of

while read -r line; do
  [[ -z "$line" ]] && continue
  nid=$(awk '{print $1}' <<<"$line")
  addr=$(awk '{print $2}' <<<"$line" | cut -d@ -f1)
  ip=${addr%:*}; port=${addr#*:}
  flags=$(awk '{print $3}' <<<"$line")
  parent=$(awk '{print $4}' <<<"$line")
  dc=$(awk -vip="$ip" '$1==ip{print $2}' "$DC_FILE")

  node_ip_port[$nid]="$ip:$port"
  [[ $flags == *master* ]] && { ((dc_master_cnt[$dc]++)); master_dc[$nid]="$dc"; }
  [[ $flags != *master* ]] && slaves_of[$parent]="$nid"

done <<<"$($CLI CLUSTER NODES)"

msg=""
for dc in "${!dc_master_cnt[@]}"; do
  if (( dc_master_cnt[$dc] > 1 )); then
    msg+="DC $dc has ${dc_master_cnt[$dc]} masters. "
    # ищем конкретные пары
    for mid in "${!master_dc[@]}"; do
      [[ ${master_dc[$mid]} != "$dc" ]] && continue
      sid=${slaves_of[$mid]:-}
      [[ -z $sid ]] && continue
      pair_master=${node_ip_port[$mid]}
      pair_slave=${node_ip_port[$sid]}
      msg+="Master $pair_master and slave-turned-master $pair_slave are both in $dc. "
      msg+="Manual fix: redis-cli -h ${pair_slave%:*} -p ${pair_slave#*:} --tls "
      msg+="--user $REDIS_USER --pass '****' CLUSTER FAILOVER TAKEOVER. "
    done
  fi
done

[[ -z "$msg" ]] && echo "OK" || echo "$msg"
```

2.3 redis_node_info.sh
──────────────────────
```bash
#!/bin/bash
set -euo pipefail
NODE_ID="$1"; METRIC="$2"
REDIS_USER="$3"; REDIS_PASS="$4"
CA="$5"; CERT="$6"; KEY="$7"

CLI="redis-cli --tls --cacert $CA --cert $CERT --key $KEY \
      --user $REDIS_USER --pass $REDIS_PASS -h 127.0.0.1"
LINE="$($CLI CLUSTER NODES | grep "^$NODE_ID")" || { echo 0; exit 1; }

case "$METRIC" in
  role)    grep -q master <<<"$(awk '{print $3}' <<<"$LINE")" && echo master || echo slave ;;
  connected) grep -q connected <<<"$LINE" && echo 1 || echo 0 ;;
  *) echo "0" ;;
esac
```

Скрипты сделайте исполняемыми:
```
chmod 750 /opt/zabbix/scripts/*.sh
chown zabbix:zabbix /opt/zabbix/scripts
```

──────────────────────────────────────────────────────────────────────────────
3. UserParameter’ы (добавьте в /etc/zabbix/zabbix_agentd.conf.d/redis_cluster.conf)
──────────────────────────────────────────────────────────────────────────────
```
# $1 user  $2 pass  $3 ca  $4 crt  $5 key
UserParameter=redis.cluster.discovery[*],/opt/zabbix/scripts/redis_cluster_discovery.sh "$1" "$2" "$3" "$4" "$5"
UserParameter=redis.cluster.dc.check[*],/opt/zabbix/scripts/redis_cluster_check.sh "$1" "$2" "$3" "$4" "$5"
UserParameter=redis.node.info[*],/opt/zabbix/scripts/redis_node_info.sh "$1" "$2" "$3" "$4" "$5" "$6" "$7"
```

──────────────────────────────────────────────────────────────────────────────
4. Zabbix-шаблон (redis_cluster_dc.yaml)
──────────────────────────────────────────────────────────────────────────────
```yaml
zabbix_export:
  version: '6.4'
  templates:
    - name: 'Redis Cluster – DC distribution'
      description: 'Контроль, чтобы в одном DC не оказалось >1 master-узла'
      key: 'tmpl.redis.dc'
      groups:
        - name: 'Templates/Databases'
      macros:
        - macro: '{$REDIS_USER}'
          value: 'zabbix_monitor'
        - macro: '{$REDIS_PASS}'
          value: 'StrongPa55'
        - macro: '{$TLS_CA}'
          value: '/etc/redis/tls/ca.pem'
        - macro: '{$TLS_CERT}'
          value: '/etc/redis/tls/client.crt'
        - macro: '{$TLS_KEY}'
          value: '/etc/redis/tls/client.key'

      items:
        - name: 'DC distribution status'
          key: 'redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$TLS_CA},{$TLS_CERT},{$TLS_KEY}]'
          type: ZABBIX_ACTIVE
          value_type: TEXT
          delay: 60s
          history: 7d
          trends: '0'

      discovery_rules:
        - name: 'Redis cluster nodes LLD'
          key: 'redis.cluster.discovery[{$REDIS_USER},{$REDIS_PASS},{$TLS_CA},{$TLS_CERT},{$TLS_KEY}]'
          type: ZABBIX_ACTIVE
          delay: 5m
          keep_lost_resources: 1
          lifetime: 1d
          item_prototypes:
            - name: 'Node {#NODE_IP}:{#NODE_PORT} role'
              key: 'redis.node.info[{#NODE_ID},role,{$REDIS_USER},{$REDIS_PASS},{$TLS_CA},{$TLS_CERT},{$TLS_KEY}]'
              type: ZABBIX_ACTIVE
              value_type: TEXT
              delay: 1m
            - name: 'Node {#NODE_IP}:{#NODE_PORT} connected'
              key: 'redis.node.info[{#NODE_ID},connected,{$REDIS_USER},{$REDIS_PASS},{$TLS_CA},{$TLS_CERT},{$TLS_KEY}]'
              type: ZABBIX_ACTIVE
              value_type: UNSIGNED
              delay: 30s

      triggers:
        - name: 'Redis: >1 master в одном DC'
          priority: HIGH
          expression: 'find(/Redis Cluster – DC distribution/redis.cluster.dc.check[{$REDIS_USER},{$REDIS_PASS},{$TLS_CA},{$TLS_CERT},{$TLS_KEY}],,"like","OK")=0'
          description: |
            После failover два master-узла оказались в одном DC.
            Детали: {ITEM.VALUE}
          manual_close: 'YES'
```

──────────────────────────────────────────────────────────────────────────────
5. Порядок установки
──────────────────────────────────────────────────────────────────────────────
1.  Разместите **dc_mapping.txt** на всех 6 узлах:  
    ```
    10.0.1.10 DC1
    10.0.1.11 DC1
    10.0.2.10 DC2
    10.0.2.11 DC2
    10.0.3.10 DC3
    10.0.3.11 DC3
    ```

2.  Установите TLS-файлы и убедитесь, что redis-cli на узлах
    работает по URI вида  
    ```
    redis-cli --tls -h 127.0.0.1 --user zabbix_monitor --pass StrongPa55 PING
    ```

3.  Скопируйте скрипты и пропишите UserParameter’ы, перезапустите zabbix-agent:
    ```
    systemctl restart zabbix-agent
    ```

4.  Импортируйте шаблон yaml через «Configuration → Templates → Import» и
    привяжите его ко всем 6 узлам.

5.  На каждом хосте в Zabbix переопределите макросы {$REDIS_PASS},
    {$TLS_*} если пути/пароль отличаются.

──────────────────────────────────────────────────────────────────────────────
6. Что увидит дежурный
──────────────────────────────────────────────────────────────────────────────
При появлении **двух master-ов в одном DC** триггер перейдёт в состояние *PROBLEM*.

В тексте события будет, например:

```
DC DC2 has 2 masters. Master 10.0.2.10:6379 and slave-turned-master 10.0.2.11:6379 are both in DC2. 
Manual fix: redis-cli -h 10.0.2.11 -p 6379 --tls --user zabbix_monitor --pass '****' CLUSTER FAILOVER TAKEOVER.
```

Тем самым оператор сразу знает:

• конкретную пару узлов;  
• команду, которую надо выполнить для ручного переключения
  (после восстановления первоначального master’а).

Готово – мониторинг катастрофоустойчивости кластера реализован.
