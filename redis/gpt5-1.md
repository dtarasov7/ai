Коротко: в Redis Cluster автоматического “автовозврата” роли master нет. Когда упавший master возвращается, он всегда поднимается как replica (slave) нового мастера. Если вы хотите вернуть мастерство на восстановившийся узел, нужно инициировать ручной failover с этого узла: redis-cli cluster failover. Делать это лучше «аккуратно» (без TAKEOVER), дождавшись, пока реплика догонит мастера по offset’ам.

Ниже — готовые bash‑скрипты.

— Скрипт для запуска на восстановившемся узле
- Ждет, пока узел увидит кластер и синхронизируется с текущим мастером.
- Делает управляемый failover (cluster failover), при необходимости — force.
- Идемпотентен: если узел уже master — ничего не делает.

Сохраните как /usr/local/bin/redis-failback.sh и сделайте исполняемым.

```bash
#!/usr/bin/env bash
# redis-failback.sh
# Возвращает роль master на восстановившийся узел Redis Cluster.
# Работает для Redis OSS 6.x.

set -euo pipefail

# Настройки: можно прокинуть через переменные окружения
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-6379}"
AUTH="${AUTH:-}"                # или используйте REDISCLI_AUTH
THRESHOLD="${THRESHOLD:-10000}" # допустимое расхождение offset'ов
WAIT_SYNC_SECS="${WAIT_SYNC_SECS:-60}"
WAIT_CLUSTER_OK_SECS="${WAIT_CLUSTER_OK_SECS:-60}"
FORCE_ON_TIMEOUT="${FORCE_ON_TIMEOUT:-true}"  # по таймауту пробовать cluster failover force

CLI=(redis-cli -c -h "$HOST" -p "$PORT")
[[ -n "${AUTH}" ]] && CLI+=(-a "$AUTH")

log() { echo "[$(date +'%F %T')] $*"; }

# Проверка доступности
if ! "${CLI[@]}" PING >/dev/null 2>&1; then
  log "Redis на ${HOST}:${PORT} недоступен."
  exit 1
fi

# Если уже мастер — выходим
role="$("${CLI[@]}" INFO replication | awk -F: '/^role/{gsub(/\r/,"");print $2}')"
if [[ "$role" == "master" ]]; then
  log "Узел уже master — ничего делать не нужно."
  exit 0
fi
if [[ "$role" != "slave" && "$role" != "replica" ]]; then
  log "Неожиданная роль: $role"
  exit 1
fi

# Ждем cluster_state:ok
end=$((SECONDS + WAIT_CLUSTER_OK_SECS))
while true; do
  state="$("${CLI[@]}" CLUSTER INFO | awk -F: '/^cluster_state/{gsub(/\r/,"");print $2}')"
  if [[ "$state" == "ok" ]]; then
    break
  fi
  if (( SECONDS >= end )); then
    log "cluster_state != ok слишком долго (>${WAIT_CLUSTER_OK_SECS}s). Продолжаем осторожно."
    break
  fi
  sleep 1
done

# Узнаем текущего мастера
master_host="$("${CLI[@]}" INFO replication | awk -F: '/^master_host/{gsub(/\r/,"");print $2}')"
master_port="$("${CLI[@]}" INFO replication | awk -F: '/^master_port/{gsub(/\r/,"");print $2}')"
link_status="$("${CLI[@]}" INFO replication | awk -F: '/^master_link_status/{gsub(/\r/,"");print $2}')"

if [[ -z "$master_host" || -z "$master_port" ]]; then
  log "Не удалось определить текущего мастера."
  exit 1
fi

log "Текущий мастер: ${master_host}:${master_port}, link_status=${link_status}"

# Ждем, пока реплика догонит мастера (offset'ы близки)
end=$((SECONDS + WAIT_SYNC_SECS))
while true; do
  # На реплике есть slave_repl_offset
  slave_off="$("${CLI[@]}" INFO replication | awk -F: '/^slave_repl_offset/{gsub(/\r/,"");print $2}')"
  # На мастере есть master_repl_offset
  master_off="$(redis-cli -h "$master_host" -p "$master_port" ${AUTH:+-a "$AUTH"} INFO replication \
               | awk -F: '/^master_repl_offset/{gsub(/\r/,"");print $2}')"

  # Если вдруг пусто — подождем
  if [[ -z "${slave_off:-}" || -z "${master_off:-}" ]]; then
    sleep 1
  else
    diff=$(( master_off - slave_off ))
    (( diff < 0 )) && diff=$(( -diff ))
    if (( diff <= THRESHOLD )); then
      log "Offsets близки (diff=${diff} <= ${THRESHOLD}). Можно делать failover."
      break
    fi
  fi

  if (( SECONDS >= end )); then
    log "Не дождались синхронизации за ${WAIT_SYNC_SECS}s."
    break
  fi
  sleep 1
done

# Пробуем управляемый failover
set +e
log "Выполняю: CLUSTER FAILOVER (graceful)"
"${CLI[@]}" CLUSTER FAILOVER >/tmp/redis-failback.out 2>&1
rc=$?
set -e

if (( rc != 0 )); then
  if [[ "${FORCE_ON_TIMEOUT}" == "true" ]]; then
    log "CLUSTER FAILOVER не удался (rc=$rc). Пробую: CLUSTER FAILOVER FORCE"
    "${CLI[@]}" CLUSTER FAILOVER FORCE
  else
    log "CLUSTER FAILOVER не удался (rc=$rc). Завершаю без FORCE."
    exit $rc
  fi
fi

# Ждем смены роли на master
for i in {1..30}; do
  new_role="$("${CLI[@]}" INFO replication | awk -F: '/^role/{gsub(/\r/,"");print $2}')"
  if [[ "$new_role" == "master" ]]; then
    log "Успех: узел стал master."
    exit 0
  fi
  sleep 1
done

log "Роль так и не сменилась на master. Проверьте логи Redis."
exit 1
```

Как использовать
- Запустить вручную на восстановившемся узле:
  - HOST, PORT, AUTH передайте через env при необходимости.
  - Пример: HOST=10.0.0.12 PORT=7001 AUTH='s3cr3t' /usr/local/bin/redis-failback.sh
- Или повесить на systemd как пост‑хук после старта Redis.

Пример unit‑файла (фрагмент)
```ini
# /etc/systemd/system/redis@7001.service.d/failback.conf
[Service]
Environment=HOST=127.0.0.1
Environment=PORT=7001
# Environment=AUTH=s3cr3t
ExecStartPost=/usr/local/bin/redis-failback.sh
```

— Опционально: оркестратор для всех трех бывших мастеров
Если у вас есть инвентарь узлов и портов, можно запустить failback удаленно по SSH, когда «старый» мастер вернулся.

```bash
#!/usr/bin/env bash
# cluster-failback-all.sh
# Запускает failback на наборе узлов (каждый скрипт выполнится локально на целевом).

set -euo pipefail

# Список "хост:порт"
NODES=(
  "redis-m1:7001"
  "redis-m2:7002"
  "redis-m3:7003"
)

AUTH="${AUTH:-}"       # при необходимости
SCRIPT_PATH="/usr/local/bin/redis-failback.sh"

for hp in "${NODES[@]}"; do
  host="${hp%%:*}"
  port="${hp##*:}"
  echo ">>> ${host}:${port}"
  ssh -o StrictHostKeyChecking=no "redis@${host}" \
    "HOST=${host} PORT=${port} AUTH='${AUTH}' ${SCRIPT_PATH}"
done
```

Замечания и тонкости
- Безопаснее начинать с «graceful» failover (CLUSTER FAILOVER без аргументов) — он дождется выравнивания репликации. FORCE/TAKEOVER используйте только если нужно вернуть мастерство любой ценой.
- Избегайте «пинг‑понга»: включайте этот механизм только на тех узлах, которые действительно хотите считать «предпочитаемыми мастерами» (можно создать флаг-файл и в начале скрипта проверять его наличие).
- Если за время простоя вы делали resharding (перераспределяли слоты), простой failover не «вернет» старую раскладку слотов. В таком случае слоты нужно переносить обратно через redis-cli --cluster reshard (это отдельная операция).
- Скрипты рассчитаны на Redis OSS 6.x, но работают и на 7.x. Терминология slave/replica в INFO может отличаться — учтено в проверке роли.

Если хотите, могу адаптировать скрипт под вашу топологию (имена/порты узлов) или добавить health‑чеки (latency, cluster_state по всем мастерам) перед переключением.
