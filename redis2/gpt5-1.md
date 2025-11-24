Ниже — готовый набор: шаблон Zabbix 6.4 (YAML), скрипты для zabbix-agent v1 и UserParameter. Он решает три задачи:
- следит, чтобы в каждом ЦОД был ровно один master;
- при нарушении показывает, в каком ЦОД их оказалось >1 и какие именно master’ы;
- в тексте события выводит «причинную пару» master↔slave (для каждого master в проблемном ЦОД указывается его текущий slave; в вашей топологии 1:1 это и есть «бывший master ↔ новый master» после failover).

Предпосылки и договоренности:
- На каждом узле есть одинаковый файл соответствий IP→DC в формате:
  10.0.1.10 DC1
  10.0.1.11 DC1
  10.0.2.10 DC2
  10.0.2.11 DC2
  10.0.3.10 DC3
  10.0.3.11 DC3
- Доступ к Redis через TLS (rediss://) и ACL-пользователь.
- Шаблон применяем ко всем 6 серверам, но «кластерный аудит» запускаем только на одном выбранном хосте (чтобы не плодить дубли событий) — это управляется макросом {$RUN_AUDIT}. На остальных {$RUN_AUDIT}=0.

1) Права ACL для пользователя Redis (минимально достаточные)
Создайте пользователя zbx (имя любое) со строго необходимыми командами:
- CLUSTER NODES и CLUSTER INFO
- ROLE
- PING/INFO (на всякий случай)

Пример команд (выполнить от администратора Redis):
ACL SETUSER zbx resetpass >"S3cure-ChangeMe" resetkeys -@all +ping +info +role +cluster|info +cluster|nodes on

Примечания:
- -@all запрещает все категории команд; далее точечно включаем только нужные.
- Если у вас самоподписанный TLS, redis-cli может потребовать --cacert или --insecure — это передадим через макрос {$REDIS_CLI_OPTS}.

2) Скрипты для zabbix-agent

2.1. /usr/local/bin/redis_cluster_audit.sh
- Кластерный аудит: читает CLUSTER NODES, маппит IP→DC, строит JSON со сводкой и «причинными парами».
- Поддерживает rediss://, опции redis-cli (--cacert/--insecure) через аргумент -O.
- Если {$RUN_AUDIT}=0, скрипт возвращает компактный JSON-«заглушку» (чтобы зависимые items спокойно жили без триггеров).

Содержимое файла:
#!/usr/bin/env bash
# redis_cluster_audit.sh
# Requirements: bash 4+, redis-cli
set -euo pipefail

usage() {
  echo "Usage: $0 -u rediss://user:pass@host:6379 -m /path/dc_map.txt -N cluster_name -A 0|1 [-C /usr/bin/redis-cli] [-O 'extra opts']"
}

json_escape() {
  local s=${1//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\r'/}
  echo -n "$s"
}

# Defaults
REDIS_CLI="/usr/bin/redis-cli"
CLI_OPTS=""
CLUSTER_NAME="redis-cluster"
RUN_AUDIT="1"
REDIS_URI=""
DC_MAP_FILE="/etc/redis/dc_map.txt"

while getopts ":u:m:N:A:C:O:" opt; do
  case "$opt" in
    u) REDIS_URI="$OPTARG" ;;
    m) DC_MAP_FILE="$OPTARG" ;;
    N) CLUSTER_NAME="$OPTARG" ;;
    A) RUN_AUDIT="$OPTARG" ;;
    C) REDIS_CLI="$OPTARG" ;;
    O) CLI_OPTS="$OPTARG" ;;
    *) usage; exit 1 ;;
  esac
done

if [[ -z "${REDIS_URI}" || -z "${DC_MAP_FILE}" ]]; then
  usage; exit 1
fi

if [[ "${RUN_AUDIT}" != "1" ]]; then
  # Легальная заглушка, чтобы dependent items не падали
  echo "{\"cluster_name\":\"$(json_escape "$CLUSTER_NAME")\",\"masters_total\":0,\"masters_unique_dc\":0,\"masters_per_dc\":{},\"lld_dc\":[],\"dc_details\":{},\"ts\":$(date +%s),\"audit_active\":false}"
  exit 0
fi

# Читаем карту DC
declare -A DC_OF
if [[ ! -r "$DC_MAP_FILE" ]]; then
  echo "{\"error\":\"dc_map_file_not_found\",\"file\":\"$(json_escape "$DC_MAP_FILE")\"}"
  exit 0
fi
while read -r ip dc extra; do
  [[ -z "${ip}" || "${ip}" =~ ^# ]] && continue
  DC_OF["$ip"]="$dc"
done < "$DC_MAP_FILE"

# Получаем CLUSTER NODES
set +e
NODES_RAW="$("$REDIS_CLI" -u "$REDIS_URI" $CLI_OPTS --no-auth-warning cluster nodes 2>&1)"
RC=$?
set -e
if [[ $RC -ne 0 ]]; then
  echo "{\"error\":\"redis_cli_failed\",\"detail\":\"$(json_escape "$NODES_RAW")\"}"
  exit 0
fi

declare -A ROLE_OF NODEIP_OF NODEADDR_OF MASTER_OF REPLICAS_OF M_SLOTS
declare -A DC_MASTER_COUNT DC_OF_NODE
declare -a MASTER_IDS
declare -A MASTER_ID_BY_IP

parse_addr() {
  # input like 10.0.1.10:6379@16379 or hostname:6379@16379
  local a="$1"
  local hostport="${a%@*}"
  local host="${hostport%%:*}"
  local port="${hostport##*:}"
  echo "$host" "$port"
}

while IFS=$'\n' read -r line; do
  [[ -z "$line" ]] && continue
  # id addr flags master_id ping pong epoch link [slots...]
  # flags contains 'master' or 'slave'
  IFS=' ' read -r nid addr flags master_id _ _ _ _ slots <<< "$line"
  read -r ip port <<< "$(parse_addr "$addr")"
  NODEIP_OF["$nid"]="$ip"
  NODEADDR_OF["$nid"]="${ip}:${port}"
  DC_OF_NODE["$nid"]="${DC_OF[$ip]:-UNKNOWN}"
  if [[ "$flags" == *"master"* ]]; then
    ROLE_OF["$nid"]="master"
    MASTER_IDS+=("$nid")
    MASTER_ID_BY_IP["$ip"]="$nid"
    M_SLOTS["$nid"]="${slots:-}"
  elif [[ "$flags" == *"slave"* ]]; then
    ROLE_OF["$nid"]="slave"
    MASTER_OF["$nid"]="$master_id"
    REPLICAS_OF["$master_id"]+="${nid} "
  else
    ROLE_OF["$nid"]="other"
  fi
done <<< "$NODES_RAW"

# Подсчёт мастеров по DC
for mid in "${MASTER_IDS[@]}"; do
  dc="${DC_OF_NODE[$mid]:-UNKNOWN}"
  (( DC_MASTER_COUNT["$dc"]++ )) || true
done

# Массив DC для LLD
declare -a LLD_DC
for dc in "${!DC_MASTER_COUNT[@]}"; do
  LLD_DC+=("{\"{#DC}\":\"$(json_escape "$dc")\"}")
done

# Детализация по DC: списки мастеров и пары master<->slave
declare -A DC_MASTERS_LIST DC_PAIRS_LIST
for dc in "${!DC_MASTER_COUNT[@]}"; do
  masters_in_dc=""
  pairs_in_dc=""
  for mid in "${MASTER_IDS[@]}"; do
    if [[ "${DC_OF_NODE[$mid]}" == "$dc" ]]; then
      maddr="${NODEADDR_OF[$mid]}"
      masters_in_dc+="${maddr}, "
      # берём первого слейва (в вашей топологии 1:1), но если их несколько — перечислим всех
      slaves_str="${REPLICAS_OF[$mid]:-}"
      if [[ -n "$slaves_str" ]]; then
        pair_once=""
        for sid in $slaves_str; do
          saddr="${NODEADDR_OF[$sid]:-unknown}"
          sdc="${DC_OF_NODE[$sid]:-UNKNOWN}"
          pair_once+="${maddr}(${dc}) <-> ${saddr}(${sdc}); "
        done
        pairs_in_dc+="$pair_once"
      else
        pairs_in_dc+="${maddr}(${dc}) <-> NO_REPLICA; "
      fi
    endfi
  done
  # обрезаем хвосты ", " и "; "
  DC_MASTERS_LIST["$dc"]="${masters_in_dc%%, }"
  DC_PAIRS_LIST["$dc"]="${pairs_in_dc%%; }"
done

# Собираем masters[]
masters_json=""
for mid in "${MASTER_IDS[@]}"; do
  maddr="${NODEADDR_OF[$mid]}"
  mip="${NODEIP_OF[$mid]}"
  mdc="${DC_OF_NODE[$mid]:-UNKNOWN}"
  slots="${M_SLOTS[$mid]}"
  rep_json=""
  slaves_str="${REPLICAS_OF[$mid]:-}"
  if [[ -n "$slaves_str" ]]; then
    for sid in $slaves_str; do
      saddr="${NODEADDR_OF[$sid]:-unknown}"
      sip="${NODEIP_OF[$sid]:-unknown}"
      sdc="${DC_OF_NODE[$sid]:-UNKNOWN}"
      rep_json+="{\"id\":\"$sid\",\"addr\":\"$(json_escape "$saddr")\",\"ip\":\"$sip\",\"dc\":\"$(json_escape "$sdc")\"},"
    done
    rep_json="[${rep_json%,}]"
  else
    rep_json="[]"
  fi
  masters_json+="{\"id\":\"$mid\",\"addr\":\"$(json_escape "$maddr")\",\"ip\":\"$mip\",\"dc\":\"$(json_escape "$mdc")\",\"slots\":\"$(json_escape "$slots")\",\"replicas\":$rep_json},"
done
masters_json="[${masters_json%,}]"

# masters_per_dc
mpdc_json=""
for dc in "${!DC_MASTER_COUNT[@]}"; do
  mpdc_json+="\"$(json_escape "$dc")\":${DC_MASTER_COUNT[$dc]},"
done
mpdc_json="{${mpdc_json%,}}"

# dc_details
dc_det_json=""
for dc in "${!DC_MASTER_COUNT[@]}"; do
  dc_det_json+="\"$(json_escape "$dc")\":{\"masters_list\":\"$(json_escape "${DC_MASTERS_LIST[$dc]}")\",\"pairs_str\":\"$(json_escape "${DC_PAIRS_LIST[$dc]}")\"},"
done
dc_det_json="{${dc_det_json%,}}"

# lld_dc
lld_json="["
for e in "${LLD_DC[@]}"; do lld_json+="$e,"; done
lld_json="${lld_json%,}]"

# masters_unique_dc = количество DC, где count>0
masters_unique_dc=0
for dc in "${!DC_MASTER_COUNT[@]}"; do
  c=${DC_MASTER_COUNT[$dc]}
  if [[ $c -gt 0 ]]; then ((masters_unique_dc++)); fi
done

printf '{'
printf '"cluster_name":"%s",' "$(json_escape "$CLUSTER_NAME")"
printf '"masters_total":%d,' "${#MASTER_IDS[@]}"
printf '"masters_unique_dc":%d,' "$masters_unique_dc"
printf '"masters_per_dc":%s,' "$mpdc_json"
printf '"masters":%s,' "$masters_json"
printf '"lld_dc":%s,' "$lld_json"
printf '"dc_details":%s,' "$dc_det_json"
printf '"ts":%d,' "$(date +%s)"
printf '"audit_active":true'
printf '}\n'

2.2. /usr/local/bin/redis_role_local.sh
- Локальный статус узла (master|slave), можно использовать для справки на каждом хосте.

Содержимое файла:
#!/usr/bin/env bash
# redis_role_local.sh
set -euo pipefail

usage(){ echo "Usage: $0 -u rediss://user:pass@127.0.0.1:6379 [-C /usr/bin/redis-cli] [-O 'extra opts']"; }

REDIS_URI=""
REDIS_CLI="/usr/bin/redis-cli"
CLI_OPTS=""

while getopts ":u:C:O:" opt; do
  case "$opt" in
    u) REDIS_URI="$OPTARG" ;;
    C) REDIS_CLI="$OPTARG" ;;
    O) CLI_OPTS="$OPTARG" ;;
    *) usage; exit 1 ;;
  esac
done

[[ -z "$REDIS_URI" ]] && usage && exit 1

OUT="$("$REDIS_CLI" -u "$REDIS_URI" $CLI_OPTS --no-auth-warning role 2>/dev/null || true)"
role=$(echo "$OUT" | awk 'NR==1{print $1}')
[[ -z "$role" ]] && role="unknown"
echo "$role"

Права и владельцы:
chmod 0755 /usr/local/bin/redis_cluster_audit.sh /usr/local/bin/redis_role_local.sh
chown root:root /usr/local/bin/redis_*.sh

2.3. UserParameter для агента
Файл, например: /etc/zabbix/zabbix_agentd.d/redis_cluster.conf

UserParameter=redis.cluster.audit[*],/usr/local/bin/redis_cluster_audit.sh -u "$1" -m "$2" -N "$3" -A "$4" -O "$5"
UserParameter=redis.role.local[*],/usr/local/bin/redis_role_local.sh -u "$1" -O "$2"

Перезапустите агент:
systemctl restart zabbix-agent

3) Шаблон Zabbix 6.4 (YAML)
- Один master-item (JSON) + LLD по DC + зависимые items + триггеры.
- Триггеры активируются только если {$RUN_AUDIT}=1 на данном хосте.

Содержимое для импорта:
zabbix_export:
  version: '6.4'
  date: '2025-11-05T00:00:00Z'
  groups:
    - name: Templates/Databases
  templates:
    - template: 'Template Redis Cluster DC Balance TLS'
      name: 'Template Redis Cluster DC Balance TLS'
      description: 'Мониторинг распределения Redis masters по ЦОД. Требуются скрипты redis_cluster_audit.sh и redis_role_local.sh.'
      groups:
        - name: Templates/Databases
      macros:
        - macro: '{$CLUSTER_NAME}'
          value: 'redis-prod-cl1'
        - macro: '{$DC_MAP_FILE}'
          value: '/etc/redis/dc_map.txt'
        - macro: '{$REDIS_URI}'
          value: 'rediss://zbx:changeme@127.0.0.1:6379'
        - macro: '{$REDIS_CLI_OPTS}'
          value: ''           # например: --cacert /etc/ssl/certs/ca.pem  или  --insecure
        - macro: '{$RUN_AUDIT}'
          value: '0'          # Поставьте 1 на единственном хосте-контролёре кластера
      items:
        - name: 'Redis cluster audit JSON'
          key: 'redis.cluster.audit["{$REDIS_URI}","{$DC_MAP_FILE}","{$CLUSTER_NAME}","{$RUN_AUDIT}","{$REDIS_CLI_OPTS}"]'
          type: ZABBIX_AGENT
          value_type: TEXT
          trends: '0'
          history: 1d
          delay: '60s'
          description: 'Кластерная сводка в JSON. На одном хосте {$RUN_AUDIT}=1.'
        - name: 'Local Redis role'
          key: 'redis.role.local["{$REDIS_URI}","{$REDIS_CLI_OPTS}"]'
          type: ZABBIX_AGENT
          value_type: CHAR
          trends: '0'
          history: 7d
          delay: '60s'
          description: 'Локальная роль данного узла (master|slave|unknown).'
        - name: 'Masters unique DC count'
          key: 'redis.audit.masters.unique_dc'
          type: DEPENDENT
          master_item:
            key: 'redis.cluster.audit["{$REDIS_URI}","{$DC_MAP_FILE}","{$CLUSTER_NAME}","{$RUN_AUDIT}","{$REDIS_CLI_OPTS}"]'
          value_type: UINT64
          trends: '0'
          history: 7d
          preprocessing:
            - type: JSONPATH
              parameters:
                - '$.masters_unique_dc'
      discovery_rules:
        - name: 'Discover DCs from audit JSON'
          type: DEPENDENT
          key: 'redis.dc.discovery'
          master_item:
            key: 'redis.cluster.audit["{$REDIS_URI}","{$DC_MAP_FILE}","{$CLUSTER_NAME}","{$RUN_AUDIT}","{$REDIS_CLI_OPTS}"]'
          delay: '0'
          lifetime: 30d
          description: 'LLD ЦОДов из JSON (ключ {#DC}).'
          preprocessing:
            - type: JSONPATH
              parameters:
                - '$.lld_dc'
          item_prototypes:
            - name: 'Masters in {#DC}'
              key: 'redis.audit.dc.count[{#DC}]'
              type: DEPENDENT
              value_type: UINT64
              trends: '0'
              history: 30d
              master_item:
                key: 'redis.dc.discovery'
              preprocessing:
                - type: JSONPATH
                  parameters:
                    - '$.masters_per_dc["{#DC}"]'
            - name: 'Masters list in {#DC}'
              key: 'redis.audit.dc.masters_list[{#DC}]'
              type: DEPENDENT
              value_type: TEXT
              trends: '0'
              history: 7d
              master_item:
                key: 'redis.dc.discovery'
              preprocessing:
                - type: JSONPATH
                  parameters:
                    - '$.dc_details["{#DC}"].masters_list'
            - name: 'Master<->Slave pairs in {#DC}'
              key: 'redis.audit.dc.pairs[{#DC}]'
              type: DEPENDENT
              value_type: TEXT
              trends: '0'
              history: 7d
              master_item:
                key: 'redis.dc.discovery'
              preprocessing:
                - type: JSONPATH
                  parameters:
                    - '$.dc_details["{#DC}"].pairs_str'
          trigger_prototypes:
            - name: 'Redis {$CLUSTER_NAME}: В ЦОД {#DC} обнаружено >1 master (={ITEM.LASTVALUE})'
              expression: 'last(/Template Redis Cluster DC Balance TLS/redis.audit.dc.count[{#DC}])>1 and (0+{$RUN_AUDIT})=1'
              priority: HIGH
              description: |
                В одном ЦОД должен быть ровно 1 master. Фактические связи:
                {#DC} pairs: {ITEM.LASTVALUE1:regsub("(.*)","\\1")}
                Masters: {ITEM.LASTVALUE2}
              dependencies: []
              tags:
                - tag: 'redis'
                  value: 'cluster'
              manual_close: '1'
              opdata: 'Пары: {ITEM.LASTVALUE3}'
              # Привяжем items для подстановки в описание/опдату:
              # LASTVALUE1 -> redis.audit.dc.pairs[{#DC}]
              # LASTVALUE2 -> redis.audit.dc.masters_list[{#DC}]
              # LASTVALUE3 -> redis.audit.dc.pairs[{#DC}]
        - name: 'internal binding items for trigger text'
          type: DEPENDENT
          key: 'redis.dc.discovery.bind'
          master_item:
            key: 'redis.cluster.audit["{$REDIS_URI}","{$DC_MAP_FILE}","{$CLUSTER_NAME}","{$RUN_AUDIT}","{$REDIS_CLI_OPTS}"]'
          delay: '0'
      triggers:
        - name: 'Redis {$CLUSTER_NAME}: Кол-во уникальных ЦОД с master < 3 (={ITEM.LASTVALUE})'
          expression: 'last(/Template Redis Cluster DC Balance TLS/redis.audit.masters.unique_dc)<3 and (0+{$RUN_AUDIT})=1'
          priority: WARNING
          description: 'Ожидается 3 ЦОД с активными master. Проверьте распределение и состояние реплик.'
          tags:
            - tag: 'redis'
              value: 'cluster'

Примечание по текстам триггеров:
- Zabbix не вставляет значения произвольных items по имени в free-text без явной ссылки. Выше мы задали в триггер-прототипе опцию opdata и описание, но чтобы подставить строки с парами и списком мастеров, в UI после импорта откройте триггер-прототип и в полях «Описание»/«Operational data» подставьте напрямую ссылки на items:
  - Пары: {HOST.NAME:redis.audit.dc.pairs[{#DC}].last()}
  - Masters: {HOST.NAME:redis.audit.dc.masters_list[{#DC}].last()}

4) Что попадет в событие при проблеме
- Имя: Redis redis-prod-cl1: В ЦОД DC2 обнаружено >1 master (=2)
- Описание/Operational data:
  - Pары: 10.0.2.10(DC2) <-> 10.0.1.10(DC1); 10.0.2.11(DC2) <-> 10.0.3.11(DC3)
  - Masters: 10.0.2.10, 10.0.2.11
Инженеру сразу видно: в DC2 два master’а и для каждого master указан его текущий slave (что и есть «причинная пара» после failover).

5) Как развернуть
- Скопируйте скрипты и выдать права (см. выше).
- Создайте /etc/redis/dc_map.txt с вашими IP→DC.
- Настройте ACL пользователя zbx (см. пункт 1).
- Включите UserParameter-файл и перезапустите агент.
- Импортируйте YAML-шаблон в Zabbix 6.4.
- Привяжите шаблон ко всем 6 хостам.
- На одном выбранном хосте (например, redis-01) задайте на уровне хоста:
  - {$RUN_AUDIT}=1
  - {$REDIS_URI}=rediss://zbx:ВашПароль@127.0.0.1:6379
  - при необходимости {$REDIS_CLI_OPTS}=--cacert /etc/ssl/certs/ca-cert.pem или --insecure
- Убедитесь, что на остальных хостах {$RUN_AUDIT}=0 (по умолчанию).

6) Проверка
- На хосте-контролёре выполните вручную:
  /usr/local/bin/redis_cluster_audit.sh -u "rediss://zbx:PASS@127.0.0.1:6379" -m /etc/redis/dc_map.txt -N redis-prod-cl1 -A 1 -O "--cacert /etc/ssl/certs/ca-cert.pem"
  Должен вернуться JSON с masters_per_dc и dc_details.
- В Zabbix проверьте, что:
  - item “Redis cluster audit JSON” обновляется с кодом 0;
  - LLD создал по 1 набору items на каждый DC (DC1, DC2, DC3);
  - при имитации отказа одного master с последующим failover триггер по проблемному DC срабатывает и в тексте есть пары.

7) Ограничения и заметки
- Скрипт опирается на IP-адрес из поля addr CLUSTER NODES. Если там hostname, добавьте его в файл соответствий или переключите Redis на адреса IP.
- Если в каком-то DC будут отсутствовать записи в карте, скрипт пометит такой узел как UNKNOWN и это может попасть в счётчики. Рекомендуется держать карту полной.
- Текущая логика пар выводит все slave’ы каждого master. Для вашей модели 1 master ↔ 1 slave этого достаточно, и это как раз «причинная пара».
- Если хотите запускать аудит на всех 6 хостах, можно поставить {$RUN_AUDIT}=1 везде, но тогда будут 6 одинаковых алёртов. Обычно удобнее один «контролёр».

Если нужен вариант с авто‑выбором «контролёра» (например, хост с минимальным IP) либо добавление алёрта «slave в том же DC, что и его master», скажите — допилим шаблон и скрипт.
