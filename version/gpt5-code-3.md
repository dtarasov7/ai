Ниже — готовый bash-скрипт, который реализует описанное решение: ведёт state.json, генерирует метрики в формате Prometheus (для textfile collector node-exporter), обрабатывает отсутствие ПО на сервере (deleted), кодирует версии в число, пишет метрики атомарно, использует lock для предотвращения параллельных запусков и экспортирует дополнительные служебные метрики.

Заполните переменную app_list и реализуйте функцию get_app_version под вашу среду.

```bash
#!/usr/bin/env bash
# app-version-collector.sh
# Хранит версии приложений в state.json и экспортирует метрики для Prometheus textfile collector.
# Требования: bash, jq, sed, hostname, date; рекомендуется flock (util-linux).
# Развёртывание: через Ansible роль (создание директорий, установка зависимостей, cron и т.п.)

set -u -o pipefail
umask 022

# =========================
# Настройки (можно переопределять через ENV)
# =========================
# Список приложений (имена). Пример: "nginx openssl httpd"
app_list=${app_list:-"nginx openssl"}

# Имя узла (label nodename / instance). При необходимости переопределите через ENV.
NODENAME=${NODENAME:-$(hostname -s 2>/dev/null || hostname)}

# Рабочая директория и файлы состояния/метрик
WORKDIR=${WORKDIR:-/home/sys_app_finder}
STATE_FILE=${STATE_FILE:-"$WORKDIR/state.json"}

# Директория textfile collector'а node-exporter
TEXTFILE_DIR=${TEXTFILE_DIR:-/var/srv/node_exporter/textfile_collector}
METRICS_FILE=${METRICS_FILE:-"$TEXTFILE_DIR/app_versions.prom"}

# Файл локировки
LOCK_FILE=${LOCK_FILE:-/home/sys_app_finder/app_version_collector.lock}

# Таймаут локировки (сек)
LOCK_TIMEOUT=${LOCK_TIMEOUT:-0}

# =========================
# Вспомогательные функции
# =========================

log() {
  # Лог в stderr с таймштампом
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "[$ts] $*" >&2
}

# Экранирование значений для меток Prometheus (\, ", \n, \r)
prom_label_escape() {
  local s=${1:-}
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/ }
  s=${s//$'\r'/ }
  echo -n "$s"
}

# Нормализация версии к числу:
# - Отбрасывает суффиксы (-, +, ~ и всё после)
# - Извлекает первую подпоследовательность вида N(.N){0,3}
# - Дополняет до 4 компонентов нулями
# - Каждая из 3 младших компонент кодируется шириной 4 цифры
# - Формула: major*10^12 + minor*10^8 + patch*10^4 + build
encode_version() {
  local version="$1"

  # Отбрасываем pre-release/metadata суффиксы
  version=$(echo -n "$version" | sed 's/[+~-].*$//')

  # Извлекаем первые до 4 числовых компонентов (например, из "nginx/1.25.4" -> "1.25.4")
  local extracted
  extracted=$(echo -n "$version" | sed -nE 's/.*?([0-9]+(\.[0-9]+){0,3}).*/\1/p')
  if [[ -z "$extracted" ]]; then
    # Если ничего не распознали — считаем версию 0
    echo -n "0"
    return 0
  fi

  local IFS='.'
  read -r -a parts <<< "$extracted"

  # Дополняем до 4 компонент
  while [[ ${#parts[@]} -lt 4 ]]; do
    parts+=("0")
  done

  # Приводим каждую к числу и ограничиваем разумно (0..999999 для major, 0..9999 для остальных)
  local major minor patch build
  major=$(( ${parts[0]//[^0-9]/} + 0 ))
  minor=$(( ${parts[1]//[^0-9]/} + 0 )); [[ $minor -gt 9999 ]] && minor=9999
  patch=$(( ${parts[2]//[^0-9]/} + 0 )); [[ $patch -gt 9999 ]] && patch=9999
  build=$(( ${parts[3]//[^0-9]/} + 0 )); [[ $build -gt 9999 ]] && build=9999

  # Печатаем: major + 3 блока по 4 цифры
  # Пример: 1.22.1 -> 1 0022 0001 0000 => 1002200010000
  printf "%d%04d%04d%04d" "$major" "$minor" "$patch" "$build"
}

# Заглушка: получить версию для appname.
# Должна:
# - Установить глобальную переменную VERSION (строковая версия)
# - Вернуть 1, если ПО есть на сервере и VERSION получена
# - Вернуть 0, если ПО нет на сервере
# ВНИМАНИЕ: Возвращаемое значение 1/0 НЕ соответствует обычному shell-успеху/ошибке!
# Реализация должна быть добавлена под вашу среду.
VERSION=""
get_app_version() {
  local appname="$1"
  VERSION=""
  # TODO: реализуйте получение версии для "$appname"
  # Пример контракта:
  # VERSION="1.25.4"
  # return 1   # ПО найдено и версия получена
  return 0     # ПО не найдено (по умолчанию заглушка)
}

# Атомарная запись файла (через временный рядом в той же ФС)
atomic_write() {
  local target="$1"
  local tmp="${target}.tmp.$$"
  cat > "$tmp" && mv -f "$tmp" "$target"
}

# =========================
# Подготовка окружения
# =========================

START_TS=$(date +%s)
COLLECTOR_SUCCESS=1

# Проверим зависимости
if ! command -v jq >/dev/null 2>&1; then
  log "jq not found, cannot proceed"
  COLLECTOR_SUCCESS=0
fi

#mkdir -p "$WORKDIR" "$TEXTFILE_DIR" || {
#  log "Cannot create dirs: $WORKDIR or $TEXTFILE_DIR"
#  COLLECTOR_SUCCESS=0
#}

# Захват lock (предпочтительно flock, иначе мягкий fallback)
LOCK_ACQUIRED=0
cleanup() {
  local rc=$?
  # Пишем метрики коллектора (даже при ошибках), чтобы не оставлять стайлы
  local DURATION=$(( $(date +%s) - START_TS ))
  {
    echo "# HELP app_version_collector_success Success (1) or failure (0) of the collector run"
    echo "# TYPE app_version_collector_success gauge"
    printf 'app_version_collector_success{instance="%s"} %d\n' "$(prom_label_escape "$NODENAME")" "$COLLECTOR_SUCCESS"
    echo "# HELP app_version_collector_duration_seconds Collector run duration in seconds"
    echo "# TYPE app_version_collector_duration_seconds gauge"
    printf 'app_version_collector_duration_seconds{instance="%s"} %d\n' "$(prom_label_escape "$NODENAME")" "$DURATION"
  } > "${METRICS_FILE}.collector.tmp.$$"
  mv -f "${METRICS_FILE}.collector.tmp.$$" "${METRICS_FILE}.collector" 2>/dev/null || true

  # Освобождаем lock
  if [[ $LOCK_ACQUIRED -eq 1 ]]; then
    if command -v flock >/dev/null 2>&1; then
      # FD 200 закроется сам при завершении
      :
    else
      rm -f "$LOCK_FILE" 2>/dev/null || true
    fi
  fi
  exit $rc
}
trap cleanup EXIT

if [[ $COLLECTOR_SUCCESS -ne 1 ]]; then
  log "Collector prerequisites not met; writing only collector_* metrics and exiting"
  exit 1
fi

# Локировка
if command -v flock >/dev/null 2>&1; then
  # shellcheck disable=SC2129
  exec 200>"$LOCK_FILE"
  if ! flock -n ${LOCK_TIMEOUT:+-w "$LOCK_TIMEOUT"} 200; then
    log "Another instance is running, exiting"
    exit 0
  fi
  LOCK_ACQUIRED=1
else
  # Fallback: простой lock-файл (не такой надёжный, но лучше чем ничего)
  if [[ -e "$LOCK_FILE" ]]; then
    log "Lock file exists ($LOCK_FILE), exiting"
    exit 0
  fi
  echo $$ > "$LOCK_FILE"
  LOCK_ACQUIRED=1
fi

# =========================
# Загрузка state.json
# =========================
if [[ -s "$STATE_FILE" ]]; then
  if ! jq empty "$STATE_FILE" 2>/dev/null; then
    log "Invalid JSON in $STATE_FILE; moving aside and starting fresh"
    mv -f "$STATE_FILE" "${STATE_FILE}.corrupt.$(date +%s)" || true
    echo '{"apps":{}}' > "$STATE_FILE"
  fi
else
  echo '{"apps":{}}' > "$STATE_FILE"
fi

STATE_JSON=$(cat "$STATE_FILE")

# =========================
# Подготовка файла метрик
# =========================
NOW=$(date +%s)
METRICS_TMP="${METRICS_FILE}.tmp.$$"

{
  echo "# HELP app_version_info Application version info with labels (nodename, appname, version, prev_version)"
  echo "# TYPE app_version_info gauge"

  echo "# HELP app_version_numeric Application version encoded as number (for comparisons)"
  echo "# TYPE app_version_numeric gauge"

  echo "# HELP app_version_change_time_seconds Unix time of the last version change"
  echo "# TYPE app_version_change_time_seconds gauge"

  echo "# HELP app_version_scrape_timestamp_seconds Unix time when the scan occurred"
  echo "# TYPE app_version_scrape_timestamp_seconds gauge"
} > "$METRICS_TMP"

# =========================
# Основной цикл по приложениям
# =========================
for app in $app_list; do
  # Вызов get_app_version: по контракту возвращает 1 если ПО найдено (и установила VERSION), 0 если нет.
  VERSION=""
  set +e
  get_app_version "$app"
  rc=$?
  set -e
  # Внимание: rc==1 => ПО найдено, rc==0 => нет (инверсия обычного bash)
  present=0
  if [[ $rc -eq 1 ]]; then
    present=1
  elif [[ $rc -eq 0 ]]; then
    present=0
  else
    log "get_app_version for '$app' returned unexpected code $rc; mark as not present"
    present=0
  fi

  # Обновляем STATE_JSON согласно логике
  if [[ $present -eq 1 ]]; then
    # ПО найдено, VERSION установлена (строка)
    STATE_JSON=$(jq \
      --arg app "$app" \
      --arg version "$VERSION" \
      --argjson now "$NOW" \
      '
      .apps = (.apps // {}) |
      .apps[$app] = (
        if .apps[$app] == null then
          { current: $version, previous: $version, changes_total: 0, change_time: $now }
        else
          (.apps[$app] |
            if .current != $version then
              .previous = (.current // $version)
              | .current = $version
              | .changes_total = ((.changes_total // 0) + 1)
              | .change_time = $now
            else .
            end)
        end
      )
      ' <<< "$STATE_JSON")
  else
    # ПО не найдено. Если оно есть в state.json — переводим в "deleted" (при необходимости).
    STATE_JSON=$(jq \
      --arg app "$app" \
      --argjson now "$NOW" \
      '
      if (.apps // {}) | has($app) then
        .apps[$app] |= (
          if .current != "deleted" then
            .previous = (.current // "deleted")
            | .current = "deleted"
            | .changes_total = ((.changes_total // 0) + 1)
            | .change_time = $now
          else .
          end
        )
      else
        .
      end
      ' <<< "$STATE_JSON")
  fi

  # Проверим, есть ли приложение в state (для случая, когда ПО отсутствует и в state его никогда не было)
  if jq -e --arg app "$app" '(.apps // {}) | has($app)' <<< "$STATE_JSON" >/dev/null; then
    cur=$(jq -r --arg app "$app" '.apps[$app].current' <<< "$STATE_JSON")
    prev=$(jq -r --arg app "$app" '.apps[$app].previous' <<< "$STATE_JSON")
    chg=$(jq -r --arg app "$app" '.apps[$app].change_time // 0' <<< "$STATE_JSON")

    # Метки
    ln=$(prom_label_escape "$NODENAME")
    la=$(prom_label_escape "$app")
    lv=$(prom_label_escape "$cur")
    lp=$(prom_label_escape "$prev")

    # info-машинка (всегда 1)
    printf 'app_version_info{nodename="%s",appname="%s",version="%s",prev_version="%s"} 1\n' "$ln" "$la" "$lv" "$lp" >> "$METRICS_TMP"

    # numeric
    if [[ "$cur" == "deleted" ]]; then
      printf 'app_version_numeric{nodename="%s",appname="%s"} 0\n' "$ln" "$la" >> "$METRICS_TMP"
    else
      enc=$(encode_version "$cur")
      printf 'app_version_numeric{nodename="%s",appname="%s"} %s\n' "$ln" "$la" "$enc" >> "$METRICS_TMP"
    fi

    # время последней смены версии
    printf 'app_version_change_time_seconds{nodename="%s",appname="%s"} %s\n' "$ln" "$la" "$chg" >> "$METRICS_TMP"
  fi

  if [[ $present -eq 1 ]]; then
    # Метрика времени сканирования для каждого приложения
    printf 'app_version_scrape_timestamp_seconds{instance="%s",appname="%s"} %s\n' \
      "$(prom_label_escape "$NODENAME")" "$(prom_label_escape "$app")" "$NOW" >> "$METRICS_TMP"
  fi
done

# =========================
# Запись метрик и состояния (атомарно)
# =========================
# 1) Метрики
mv -f "$METRICS_TMP" "$METRICS_FILE"

# 2) Обновлённый state.json
# Пишем атомарно
echo "$STATE_JSON" | jq '.' | atomic_write "$STATE_FILE" || {
  log "Failed to write state file"
  COLLECTOR_SUCCESS=0
}

# Успешное завершение
exit 0
```

Пояснения и примечания:
- get_app_version: вы реализуете логику получения строковой версии. По контракту:
  - должна установить глобальную переменную VERSION (строка);
  - вернуть 1, если ПО найдено на сервере и VERSION получена;
  - вернуть 0, если ПО отсутствует.
- При отсутствии ПО:
  - если приложение есть в state.json — метрики генерируются как numeric=0, info с version="deleted", а в state: previous := старый current, current := "deleted", changes_total++ и change_time := now;
  - если в state.json его никогда не было — метрики для этого приложения не создаются.
- Кодирование версий:
  - encode_version поддерживает форматы вроде "1.22.1", "2.4.54.3", "nginx/1.25", "1.2rc1", отбрасывает суффиксы после -, +, ~.
  - Возвращаемое число удобно для сравнений, delta/changes и т.д.
- Метрики:
  - app_version_info{nodename, appname, version, prev_version} 1
  - app_version_numeric{nodename, appname} <число|0>
  - app_version_change_time_seconds{nodename, appname} <unix_ts>
  - app_version_scrape_timestamp_seconds{instance, appname} <unix_ts>
  - Дополнительно записываются служебные: app_version_collector_success{instance}, app_version_collector_duration_seconds{instance} в отдельный файл .prom с суффиксом .collector (не мешает основным метрикам).
- Файл метрик пишется атомарно для textfile collector (tmp + mv).
- Имеется локировка через flock (если доступен), иначе — мягкий fallback на lock-файл.
- state.json хранит объект вида:
  {
    "apps": {
      "nginx": {
        "current": "1.25.4",
        "previous": "1.24.0",
        "changes_total": 3,
        "change_time": 1728624005
      }
    }
  }

Под ваши нужды подправьте:
- app_list
- реализацию get_app_version
- пути (WORKDIR, TEXTFILE_DIR, STATE_FILE)
- NODENAME при желании.
