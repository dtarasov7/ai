Ниже — готовый комплект: шаблон Zabbix 6.4 (YAML), bash‑скрипт(ы) для агента и ACL для Redis 7 (TLS+ACL, rediss://). Он решает две задачи:

- Обнаружить «аномалию ЦОД»: в одном и том же DC оказалось больше одного мастера (типичный эффект после автоматического failover).
- Показать, какая master–replica пара является причиной и дать готовую redis-cli команду для ручного переключения роли (CLUSTER FAILOVER) на нужной реплике в «другом» DC.

Как это работает
- Агент на каждом сервере раз в N секунд опрашивает кластер (CLUSTER NODES) через локальный redis-cli по TLS (rediss://), читает ваш файл соответствия IP→DC и строит JSON с топологией.
- Зависимые элементы в шаблоне вынимают из JSON: число конфликтующих DC, текстовую сводку по парам и команды на ручной failover.
- Триггер срабатывает, если в каком‑либо DC обнаружено ≥2 мастера, и в тексте события вы видите конкретные пары и команды.

Важные допущения
- На каждом узле подняты 2 процесса: 6379 и 6380 (они могут менять роль). Любой из них можно опросить — из CLUSTER NODES мы получим всю топологию.
- В каждом файле маппинга IP→DC присутствуют все IP узлов кластера (строго в формате “IP whitespace DC”, по одному узлу в строке).
- В cluster nodes у узлов объявлены IP (а не произвольные hostnames). Если объявлены имена — скрипт попробует их резолвить через getent ahosts.

Уровни доступа (ACL)
- Пользователь мониторинга (для Zabbix, безопасный read‑only): достаточно INFO/ROLE и чтения подкоманд CLUSTER.
- Пользователь оператор (для ручной команды CLUSTER FAILOVER): дополнительно право CLUSTER|FAILOVER.

Redis ACL (выполнить на одном из мастеров; пароли замените своими)
```
ACL SETUSER zbxmon ON >monitoring_password ~* +PING +INFO +ROLE \
  +CLUSTER|NODES +CLUSTER|SLOTS +CLUSTER|INFO +CLUSTER|MYID

ACL SETUSER zbxop  ON >operator_password  ~* +PING +INFO +ROLE \
  +CLUSTER|NODES +CLUSTER|SLOTS +CLUSTER|INFO +CLUSTER|MYID +CLUSTER|FAILOVER
```

1) Шаблон Zabbix 6.4 (YAML)
Импортируйте в Zabbix (Configuration → Templates → Import). Примените к хостам всех серверов кластера.

```
zabbix_export:
  version: '6.4'
  date: '2025-11-05T00:00:00Z'
  groups:
    - name: Templates
  templates:
    - template: Template Redis Cluster DC Anti-Colocation
      name: Template Redis Cluster DC Anti-Colocation
      description: |
        Мониторинг Redis OSS v7 Cluster (TLS+ACL). Обнаружение ситуации,
        когда в одном DC оказалось ≥2 мастеров, и/или master–replica пара
        оказалась в одном DC после failover. В событии показываются пары и
        готовые команды redis-cli для ручного ручного переключения ролей.
      macros:
        - macro: '{$REDIS_PORT1}'
          value: '6379'
        - macro: '{$REDIS_PORT2}'
          value: '6380'
        - macro: '{$REDIS_MON_USER}'
          value: 'zbxmon'
        - macro: '{$REDIS_MON_PASSWORD}'
          value: 'monitoring_password'
          description: 'Пароль пользователя мониторинга (ACL).'
        - macro: '{$REDIS_CACERT}'
          value: '/etc/redis/ca.pem'
          description: 'Путь к CA сертификату сервера Redis (TLS).'
        - macro: '{$REDIS_CLIENT_CERT}'
          value: ''
          description: 'Необязательно: client cert, если включен mTLS.'
        - macro: '{$REDIS_CLIENT_KEY}'
          value: ''
          description: 'Необязательно: client key, если включен mTLS.'
        - macro: '{$DC_MAP_FILE}'
          value: '/etc/redis/dc_map.txt'
          description: 'Файл с маппингом IP→DC. Формат: "IP<space>DC".'
        - macro: '{$DISCOVERY_INTERVAL}'
          value: '60'
      items:
        - name: 'Redis topology JSON (cluster-wide)'
          type: ZABBIX_AGENT_ACTIVE
          key: 'redis.topology.json[{HOST.CONN},{$REDIS_PORT1},{$REDIS_PORT2},{$REDIS_MON_USER},{$REDIS_MON_PASSWORD},{$REDIS_CACERT},{$REDIS_CLIENT_CERT},{$REDIS_CLIENT_KEY},{$DC_MAP_FILE}]'
          delay: '{$DISCOVERY_INTERVAL}'
          history: 1h
          trends: '0'
          value_type: TEXT
          description: 'JSON с полной топологией, сводкой по DC и подсказками для ручного CLUSTER FAILOVER.'
          preprocessing:
            - type: CHECK_JSON_ERROR
        - name: 'DC conflict count'
          type: DEPENDENT
          key: 'redis.dc.conflict.count'
          delay: '0'
          history: 30d
          value_type: NUMERIC_UNSIGNED
          description: 'Сколько DC имеют ≥2 мастеров.'
          preprocessing:
            - type: JSONPATH
              parameters:
                - $.conflict_count
          master_item:
            key: 'redis.topology.json[{HOST.CONN},{$REDIS_PORT1},{$REDIS_PORT2},{$REDIS_MON_USER},{$REDIS_MON_PASSWORD},{$REDIS_CACERT},{$REDIS_CLIENT_CERT},{$REDIS_CLIENT_KEY},{$DC_MAP_FILE}]'
        - name: 'Conflict details (text)'
          type: DEPENDENT
          key: 'redis.dc.conflicts.text'
          delay: '0'
          history: 14d
          trends: '0'
          value_type: TEXT
          description: 'Человекочитаемая сводка: какие пары master–replica и какие команды CLUSTER FAILOVER выполнить.'
          preprocessing:
            - type: JSONPATH
              parameters:
                - $.conflicts_text
          master_item:
            key: 'redis.topology.json[{HOST.CONN},{$REDIS_PORT1},{$REDIS_PORT2},{$REDIS_MON_USER},{$REDIS_MON_PASSWORD},{$REDIS_CACERT},{$REDIS_CLIENT_CERT},{$REDIS_CLIENT_KEY},{$DC_MAP_FILE}]'
        - name: 'Masters per DC (JSON)'
          type: DEPENDENT
          key: 'redis.dc.masters.json'
          delay: '0'
          history: 7d
          trends: '0'
          value_type: TEXT
          description: 'JSON-словарь: {"DC1":N,"DC2":M,...}.'
          preprocessing:
            - type: JSONPATH
              parameters:
                - $.masters_per_dc
          master_item:
            key: 'redis.topology.json[{HOST.CONN},{$REDIS_PORT1},{$REDIS_PORT2},{$REDIS_MON_USER},{$REDIS_MON_PASSWORD},{$REDIS_CACERT},{$REDIS_CLIENT_CERT},{$REDIS_CLIENT_KEY},{$DC_MAP_FILE}]'
        - name: 'Unknown DC IPs (if any)'
          type: DEPENDENT
          key: 'redis.dc.unknown_ips'
          delay: '0'
          history: 7d
          trends: '0'
          value_type: TEXT
          description: 'Список IP, для которых не найден DC в {$DC_MAP_FILE}.'
          preprocessing:
            - type: JSONPATH
              parameters:
                - $.unknown_dc_ips
          master_item:
            key: 'redis.topology.json[{HOST.CONN},{$REDIS_PORT1},{$REDIS_PORT2},{$REDIS_MON_USER},{$REDIS_MON_PASSWORD},{$REDIS_CACERT},{$REDIS_CLIENT_CERT},{$REDIS_CLIENT_KEY},{$DC_MAP_FILE}]'
      triggers:
        - name: 'Redis cluster: в одном DC обнаружено ≥2 мастеров'
          expression: '{Template Redis Cluster DC Anti-Colocation:redis.dc.conflict.count.last()}>0'
          priority: HIGH
          description: |
            Обнаружена «аномалия ЦОД» (несколько мастеров в одном DC). Детали и команды для ручного переключения:
            {Template Redis Cluster DC Anti-Colocation:redis.dc.conflicts.text.last()}
          tags:
            - tag: service
              value: redis
            - tag: scope
              value: availability
        - name: 'Redis cluster: в файле {$DC_MAP_FILE} не найдены DC для части IP'
          expression: 'length({Template Redis Cluster DC Anti-Colocation:redis.dc.unknown_ips.last()})>0'
          priority: WARNING
          description: |
            Некоторые адреса из CLUSTER NODES не сопоставлены с DC (см. список).
            Проверьте корректность {$DC_MAP_FILE}.
          dependencies:
            - name: 'Redis cluster: в одном DC обнаружено ≥2 мастеров'
              expression: '{Template Redis Cluster DC Anti-Colocation:redis.dc.conflict.count.last()}>0'
```

2) Конфигурация Zabbix Agent (UserParameter) и скрипты

2.1. UserParameter (на всех серверах кластера)
Создайте файл /etc/zabbix/zabbix_agentd.d/redis_cluster.conf:

```
# Топология кластера Redis в JSON.
# Параметры:
# 1: host (обычно {HOST.CONN})
# 2: port1 (обычно 6379)
# 3: port2 (обычно 6380)
# 4: user (ACL)
# 5: password (ACL)
# 6: cacert path
# 7: client cert (optional, '' если не используется)
# 8: client key  (optional, '' если не используется)
# 9: dc map file

UserParameter=redis.topology.json[*],/usr/local/bin/redis_cluster_topology.sh "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9"
```

Перезапустите агент:
- RHEL/CentOS: systemctl restart zabbix-agent
- Debian/Ubuntu: systemctl restart zabbix-agent

2.2. Скрипт /usr/local/bin/redis_cluster_topology.sh
Права: root:root, 0755. Зависимости: bash, redis-cli, getent (glibc). Без jq.

```
#!/usr/bin/env bash
set -euo pipefail

# Args:
# 1 host (обычно 127.0.0.1 или {HOST.CONN})
# 2 port1
# 3 port2
# 4 user
# 5 pass
# 6 cacert
# 7 client_cert ('' если нет)
# 8 client_key  ('' если нет)
# 9 dc_map_file

HOST="${1:-127.0.0.1}"
PORT1="${2:-6379}"
PORT2="${3:-6380}"
ACL_USER="${4:-}"
ACL_PASS="${5:-}"
CACERT="${6:-/etc/ssl/certs/ca-certificates.crt}"
CLIENT_CERT="${7:-}"
CLIENT_KEY="${8:-}"
DC_MAP_FILE="${9:-/etc/redis/dc_map.txt}"

TIMEOUT=3

die() { echo "$*" >&2; exit 1; }

have_cmd() { command -v "$1" >/dev/null 2>&1; }

have_cmd redis-cli || die "redis-cli not found"
[[ -r "$DC_MAP_FILE" ]] || die "DC map file not readable: $DC_MAP_FILE"
[[ -z "$CLIENT_CERT" || -r "$CLIENT_CERT" ]] || die "Client cert not readable: $CLIENT_CERT"
[[ -z "$CLIENT_KEY"  || -r "$CLIENT_KEY"  ]] || die "Client key not readable: $CLIENT_KEY"
[[ -r "$CACERT" ]] || die "CA cert not readable: $CACERT"

# Build redis-cli base
build_cli() {
  local host="$1" port="$2"
  local uri="rediss://${ACL_USER}:${ACL_PASS}@${host}:${port}"
  local args=( -u "$uri" --tls --cacert "$CACERT" --no-auth-warning --raw --timeout "$TIMEOUT" )
  [[ -n "$CLIENT_CERT" ]] && args+=( --cert "$CLIENT_CERT" )
  [[ -n "$CLIENT_KEY"  ]] && args+=( --key  "$CLIENT_KEY" )
  printf '%s\0' "${args[@]}"
}

try_cluster_nodes() {
  local host="$1" port="$2"
  local -a args
  IFS=$'\0' read -r -d '' -a args < <(build_cli "$host" "$port")
  # shellcheck disable=SC2068
  if out="$(${args[@]} cluster nodes 2>/dev/null)"; then
    if [[ -n "$out" ]]; then
      echo "$out"
      return 0
    fi
  fi
  return 1
}

# Resolve hostname to IP if needed
to_ip() {
  local h="$1"
  if [[ "$h" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$h"
  else
    getent ahosts "$h" | awk 'NR==1 {print $1; exit}' | tr -d '\r\n'
  fi
}

# DC lookup
dc_of_ip() {
  local ip="$1"
  awk -v ip="$ip" '$1==ip {print $2; found=1; exit} END{ if (!found) print "UNKNOWN"}' "$DC_MAP_FILE"
}

# 1) Получаем CLUSTER NODES
CNODES=""
if ! CNODES="$(try_cluster_nodes "$HOST" "$PORT1")"; then
  CNODES="$(try_cluster_nodes "$HOST" "$PORT2" || true)"
fi
[[ -n "$CNODES" ]] || die "Failed to fetch CLUSTER NODES from $HOST:$PORT1/$PORT2"

# 2) Разбираем узлы
# Формат строк: id addr:port@cport flags master_id ping_sent ping_recv config_epoch link_state [slots]
# flags содержит 'master' или 'slave' (иногда 'replica')
declare -A NODE_IP NODE_PORT NODE_FLAG NODE_MID NODE_DC
declare -A MASTERS_REPLICAS # key=master_id, val=space-separated replica_ids
UNKNOWN_IPS=()

while IFS=$'\n' read -r line; do
  [[ -z "$line" ]] && continue
  # Берем первые 8 колонок
  # shellcheck disable=SC2206
  parts=($line)
  id="${parts[0]}"
  addr="${parts[1]}"
  flags_orig="${parts[2]}"
  mid="${parts[3]}"

  hostport="${addr%%@*}"           # 10.0.1.10:6379
  host="${hostport%%:*}"
  port="${hostport##*:}"

  # normalize flags: master|slave
  flag="other"
  if [[ ",$flags_orig," == *",master,"* ]]; then
    flag="master"
  elif [[ ",$flags_orig," == *",slave,"* || ",$flags_orig," == *",replica,"* ]]; then
    flag="replica"
  fi

  ip="$(to_ip "$host")"
  if [[ -z "$ip" ]]; then
    ip="UNKNOWN"
  fi
  NODE_IP["$id"]="$ip"
  NODE_PORT["$id"]="$port"
  NODE_FLAG["$id"]="$flag"
  NODE_MID["$id"]="$mid"

  dc="$(dc_of_ip "$ip")"
  NODE_DC["$id"]="$dc"
  if [[ "$dc" == "UNKNOWN" ]]; then
    UNKNOWN_IPS+=("$ip")
  fi

  if [[ "$flag" == "replica" && "$mid" != "-" ]]; then
    if [[ -z "${MASTERS_REPLICAS[$mid]:-}" ]]; then
      MASTERS_REPLICAS[$mid]="$id"
    else
      MASTERS_REPLICAS[$mid]="${MASTERS_REPLICAS[$mid]} $id"
    fi
  fi
done <<< "$CNODES"

# 3) Собираем список мастеров и счетчики по DC
declare -A DC_MAST_CNT
MASTERS=()
for nid in "${!NODE_FLAG[@]}"; do
  if [[ "${NODE_FLAG[$nid]}" == "master" ]]; then
    MASTERS+=("$nid")
    dc="${NODE_DC[$nid]}"
    DC_MAST_CNT["$dc"]=$(( ${DC_MAST_CNT[$dc]:-0} + 1 ))
  fi
done

# 4) Определяем конфликтующие DC (>=2 мастеров)
CONFLICT_DCS=()
for dc in "${!DC_MAST_CNT[@]}"; do
  if (( ${DC_MAST_CNT[$dc]} >= 2 )); then
    CONFLICT_DCS+=("$dc")
  fi
done
conflict_count=${#CONFLICT_DCS[@]}

# 5) Готовим сводку и рекомендации (CLUSTER FAILOVER на реплике из "другого" DC)
conflicts_text=""
masters_per_dc_json="{"
first_dc=true
for dc in "${!DC_MAST_CNT[@]}"; do
  $first_dc || masters_per_dc_json+=","
  masters_per_dc_json+="\"${dc}\":${DC_MAST_CNT[$dc]}"
  first_dc=false
done
masters_per_dc_json+="}"

if (( conflict_count > 0 )); then
  for dc in "${CONFLICT_DCS[@]}"; do
    # Список мастеров в этом DC
    dc_masters=()
    for mid in "${MASTERS[@]}"; do
      if [[ "${NODE_DC[$mid]}" == "$dc" ]]; then
        dc_masters+=("$mid")
      fi
    done

    conflicts_text+="DC ${dc}: мастеров=${#dc_masters[@]}\n"
    for mid in "${dc_masters[@]}"; do
      m_ip="${NODE_IP[$mid]}"; m_port="${NODE_PORT[$mid]}"
      # Найти реплику этого мастера в другом DC
      replicas_str="${MASTERS_REPLICAS[$mid]:-}"
      picked_rep=""
      if [[ -n "$replicas_str" ]]; then
        for rid in $replicas_str; do
          if [[ "${NODE_DC[$rid]}" != "$dc" && "${NODE_DC[$rid]}" != "UNKNOWN" ]]; then
            picked_rep="$rid"
            break
          fi
        done
      fi

      if [[ -n "$picked_rep" ]]; then
        r_ip="${NODE_IP[$picked_rep]}"; r_port="${NODE_PORT[$picked_rep]}"; r_dc="${NODE_DC[$picked_rep]}"
        conflicts_text+=" - Пара (причина): master ${m_ip}:${m_port} (id=${mid}) ↔ replica ${r_ip}:${r_port} (id=${picked_rep}, DC=${r_dc})\n"
        conflicts_text+="   Команда (выполнить НА реплике ${r_ip}:${r_port}):\n"
        conflicts_text+="   redis-cli -u 'rediss://<OP_USER>:<OP_PASSWORD>@${r_ip}:${r_port}' --cacert ${CACERT} CLUSTER FAILOVER\n"
      else
        conflicts_text+=" - Мастер ${m_ip}:${m_port} (id=${mid}): не найдена реплика в другом DC — проверьте конфигурацию реплик.\n"
      fi
    done
  done
fi

# Список IP без DC
unknown_dc_ips=""
if (( ${#UNKNOWN_IPS[@]} > 0 )); then
  uniq=$(printf "%s\n" "${UNKNOWN_IPS[@]}" | sort -u | paste -sd "," -)
  unknown_dc_ips="$uniq"
fi

# 6) Печатаем JSON
# fields:
#  conflict_count (int)
#  masters_per_dc (json object)
#  conflicts_text (string, multi-line)
#  unknown_dc_ips (string, comma-separated)
printf '{'
printf '"conflict_count":%d,' "$conflict_count"
printf '"masters_per_dc":%s,' "$masters_per_dc_json"
# Экранируем переносы строк и кавычки в текстовом поле
esc_txt=$(printf "%s" "$conflicts_text" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
[[ -z "$esc_txt" ]] && esc_txt='""'
printf '"conflicts_text":%s,' "$esc_txt"
esc_unknown=$(printf "%s" "$unknown_dc_ips" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
[[ -z "$esc_unknown" ]] && esc_unknown='""'
printf '"unknown_dc_ips":%s' "$esc_unknown"
printf '}\n'
```

Примечания к скрипту
- Он автоматически пытается сначала порт 6379, затем 6380. Достаточно достучаться до любого локального процесса — топология будет полной.
- Если у вас нет mTLS, оставьте {$REDIS_CLIENT_CERT} и {$REDIS_CLIENT_KEY} пустыми.
- Для экранирования текста используется python3 (обычно предустановлен). Если его нет — скажите, дам вариант без Python.

3) Файл маппинга DC (на всех серверах)
Путь по умолчанию: /etc/redis/dc_map.txt. Формат строго такой:

```
10.0.1.10 DC1
10.0.2.10 DC2
10.0.3.10 DC3
```

Дополните всеми IP всех redis‑процессов кластера (фактические адреса, которые видны в CLUSTER NODES).

4) Что появится в событии Zabbix
При срабатывании триггера вы увидите, например:

- DC DC2: мастеров=2
  - Пара (причина): master 10.0.2.10:6380 (id=abcd...) ↔ replica 10.0.1.10:6379 (id=efgh..., DC=DC1)
    Команда (выполнить НА реплике 10.0.1.10:6379):
    redis-cli -u 'rediss://<OP_USER>:<OP_PASSWORD>@10.0.1.10:6379' --cacert /etc/redis/ca.pem CLUSTER FAILOVER

Замените <OP_USER>/<OP_PASSWORD> на ACL‑пользователя с правом +CLUSTER|FAILOVER (например, zbxop). Команда запускается на узле‑реплике в «нужном» DC; текущий мастер автоматически станет его репликой, что уберет «два мастера в одном DC».

5) Мини‑чек‑лист по установке
- Установить redis-cli на все сервера.
- Создать пользователей ACL zbxmon и zbxop (см. выше).
- Положить /etc/redis/dc_map.txt на все сервера (одинаковые копии).
- Положить CA в {$REDIS_CACERT} (и при mTLS — client cert/key).
- Скопировать скрипт в /usr/local/bin/redis_cluster_topology.sh, дать права 0755.
- Добавить UserParameter, перезапустить zabbix-agent.
- Импортировать шаблон в Zabbix и привесить его ко всем узлам кластера.

Если хотите, могу адаптировать:
- Формат файла маппинга (например, CSV).
- Имена/DC‑метки из внешнего CMDB/Consul.
- Интервалы опроса и уровни приоритета триггеров.
- Вывод команд с автоматической подстановкой имени пользователя (без пароля) или формирование «двухступенчатой» подсказки (включая CLUSTER FAILOVER TAKEOVER для аварийных случаев).
