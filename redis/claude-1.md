Для автоматического возврата роли master на восстановившийся узел в Redis Cluster, вам понадобятся скрипты, которые будут выполнять ручной failover. Вот готовые решения:

## Скрипт 1: Автоматический возврат роли master

```bash
#!/bin/bash
# /usr/local/bin/redis-restore-master.sh
# Скрипт для возврата роли master на восстановившийся узел

set -euo pipefail

# Конфигурация
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_AUTH="${REDIS_AUTH:-}"
MAX_WAIT_TIME=60  # Максимальное время ожидания синхронизации (сек)
RETRY_INTERVAL=5   # Интервал между попытками (сек)

# Функция для выполнения redis-cli команд
redis_cmd() {
    if [[ -n "$REDIS_AUTH" ]]; then
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_AUTH" "$@"
    else
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@"
    fi
}

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Проверка доступности Redis
check_redis_available() {
    if ! redis_cmd PING &>/dev/null; then
        log "ERROR: Redis недоступен на $REDIS_HOST:$REDIS_PORT"
        return 1
    fi
    return 0
}

# Получение текущей роли узла
get_node_role() {
    redis_cmd INFO replication | grep "^role:" | cut -d: -f2 | tr -d '\r'
}

# Проверка состояния кластера
check_cluster_state() {
    local state=$(redis_cmd CLUSTER INFO | grep "^cluster_state:" | cut -d: -f2 | tr -d '\r')
    if [[ "$state" == "ok" ]]; then
        return 0
    else
        log "WARNING: Состояние кластера: $state"
        return 1
    fi
}

# Получение ID текущего узла
get_node_id() {
    redis_cmd CLUSTER MYID | tr -d '\r'
}

# Проверка синхронизации с master
check_replication_sync() {
    local master_link_status=$(redis_cmd INFO replication | grep "^master_link_status:" | cut -d: -f2 | tr -d '\r')
    if [[ "$master_link_status" == "up" ]]; then
        return 0
    else
        return 1
    fi
}

# Основная логика
main() {
    log "Запуск скрипта восстановления роли master"
    
    # Проверка доступности Redis
    if ! check_redis_available; then
        exit 1
    fi
    
    # Получение текущей роли
    current_role=$(get_node_role)
    log "Текущая роль узла: $current_role"
    
    # Если узел уже master, выходим
    if [[ "$current_role" == "master" ]]; then
        log "Узел уже является master. Выход."
        exit 0
    fi
    
    # Если узел не slave, что-то пошло не так
    if [[ "$current_role" != "slave" ]]; then
        log "ERROR: Неожиданная роль узла: $current_role"
        exit 1
    fi
    
    # Ожидание стабилизации кластера
    log "Ожидание стабилизации кластера..."
    wait_time=0
    while ! check_cluster_state && [ $wait_time -lt $MAX_WAIT_TIME ]; do
        sleep $RETRY_INTERVAL
        wait_time=$((wait_time + RETRY_INTERVAL))
    done
    
    # Проверка синхронизации с master
    log "Проверка синхронизации с текущим master..."
    wait_time=0
    while ! check_replication_sync && [ $wait_time -lt $MAX_WAIT_TIME ]; do
        sleep $RETRY_INTERVAL
        wait_time=$((wait_time + RETRY_INTERVAL))
    done
    
    # Получение ID узла для логирования
    node_id=$(get_node_id)
    log "ID текущего узла: $node_id"
    
    # Выполнение failover
    log "Инициирование failover для возврата роли master..."
    if redis_cmd CLUSTER FAILOVER; then
        log "Команда failover отправлена успешно"
        
        # Ожидание завершения failover
        sleep 5
        
        # Проверка новой роли
        new_role=$(get_node_role)
        if [[ "$new_role" == "master" ]]; then
            log "SUCCESS: Роль master успешно восстановлена"
            exit 0
        else
            log "WARNING: Failover выполнен, но роль осталась: $new_role"
            exit 1
        fi
    else
        log "ERROR: Не удалось выполнить failover"
        exit 1
    fi
}

# Запуск основной логики
main
```

## Скрипт 2: Мониторинг и автоматический запуск восстановления

```bash
#!/bin/bash
# /usr/local/bin/redis-monitor-failback.sh
# Мониторинг статуса узла и автоматический запуск восстановления

set -euo pipefail

# Конфигурация
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_AUTH="${REDIS_AUTH:-}"
MARKER_FILE="/var/lib/redis/preferred_master_${REDIS_PORT}"
CHECK_INTERVAL=30  # Интервал проверки (сек)
RESTORE_SCRIPT="/usr/local/bin/redis-restore-master.sh"

# Функция для выполнения redis-cli команд
redis_cmd() {
    if [[ -n "$REDIS_AUTH" ]]; then
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_AUTH" "$@" 2>/dev/null
    else
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@" 2>/dev/null
    fi
}

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Создание marker файла для обозначения preferred master
create_marker() {
    if [[ ! -f "$MARKER_FILE" ]]; then
        touch "$MARKER_FILE"
        log "Создан marker файл: $MARKER_FILE"
    fi
}

# Основной цикл мониторинга
main() {
    log "Запуск мониторинга для автоматического failback"
    
    # Проверяем, должен ли этот узел быть preferred master
    if [[ ! -f "$MARKER_FILE" ]]; then
        log "Узел не помечен как preferred master. Создайте файл $MARKER_FILE для активации"
        exit 0
    fi
    
    while true; do
        # Проверяем доступность Redis
        if redis_cmd PING &>/dev/null; then
            # Получаем текущую роль
            current_role=$(redis_cmd INFO replication | grep "^role:" | cut -d: -f2 | tr -d '\r' || echo "unknown")
            
            # Если узел slave, но должен быть master
            if [[ "$current_role" == "slave" ]]; then
                log "Обнаружено: узел является slave, запускаем восстановление..."
                
                # Экспортируем переменные окружения для дочернего скрипта
                export REDIS_HOST REDIS_PORT REDIS_AUTH
                
                # Запускаем скрипт восстановления
                if "$RESTORE_SCRIPT"; then
                    log "Восстановление завершено успешно"
                else
                    log "Ошибка при восстановлении"
                fi
            fi
        else
            log "WARNING: Redis недоступен"
        fi
        
        sleep $CHECK_INTERVAL
    done
}

# Обработка сигналов для корректного завершения
trap 'log "Получен сигнал завершения"; exit 0' SIGTERM SIGINT

# Запуск
main
```

## Скрипт 3: Системный сервис для автоматического восстановления

```bash
#!/bin/bash
# /usr/local/bin/redis-failback-service.sh
# Сервис для автоматического восстановления роли master

# Создание systemd unit файла
cat > /etc/systemd/system/redis-failback@.service << 'EOF'
[Unit]
Description=Redis Failback Service for port %i
After=redis@%i.service
Requires=redis@%i.service

[Service]
Type=simple
Environment="REDIS_PORT=%i"
Environment="REDIS_HOST=127.0.0.1"
# Раскомментируйте и установите пароль если нужно
#Environment="REDIS_AUTH=your_password"
ExecStartPre=/bin/sleep 10
ExecStart=/usr/local/bin/redis-monitor-failback.sh
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Systemd unit файл создан: /etc/systemd/system/redis-failback@.service"
```

## Скрипт 4: Управление preferred masters

```bash
#!/bin/bash
# /usr/local/bin/redis-manage-preferred-masters.sh
# Управление узлами, которые должны быть preferred masters

set -euo pipefail

# Функция помощи
usage() {
    cat << EOF
Использование: $0 [команда] [порт]

Команды:
  enable [порт]   - Пометить узел как preferred master
  disable [порт]  - Убрать метку preferred master
  list            - Показать все preferred masters
  status          - Показать статус всех узлов кластера

Пример:
  $0 enable 6379
  $0 disable 6380
  $0 list
EOF
    exit 1
}

# Проверка аргументов
if [[ $# -lt 1 ]]; then
    usage
fi

COMMAND=$1
MARKER_DIR="/var/lib/redis"

case $COMMAND in
    enable)
        if [[ $# -lt 2 ]]; then
            echo "Ошибка: укажите порт"
            usage
        fi
        PORT=$2
        MARKER_FILE="${MARKER_DIR}/preferred_master_${PORT}"
        touch "$MARKER_FILE"
        echo "Узел на порту $PORT помечен как preferred master"
        
        # Активация сервиса
        systemctl enable redis-failback@${PORT}.service
        systemctl start redis-failback@${PORT}.service
        echo "Сервис redis-failback@${PORT} активирован"
        ;;
        
    disable)
        if [[ $# -lt 2 ]]; then
            echo "Ошибка: укажите порт"
            usage
        fi
        PORT=$2
        MARKER_FILE="${MARKER_DIR}/preferred_master_${PORT}"
        rm -f "$MARKER_FILE"
        echo "Метка preferred master удалена для порта $PORT"
        
        # Деактивация сервиса
        systemctl stop redis-failback@${PORT}.service
        systemctl disable redis-failback@${PORT}.service
        echo "Сервис redis-failback@${PORT} деактивирован"
        ;;
        
    list)
        echo "Preferred masters:"
        for marker in ${MARKER_DIR}/preferred_master_*; do
            if [[ -f "$marker" ]]; then
                port=$(basename "$marker" | sed 's/preferred_master_//')
                echo "  - Порт: $port"
            fi
        done
        ;;
        
    status)
        echo "Статус узлов Redis Cluster:"
        for port in 6379 6380 6381 6382 6383 6384; do
            if redis-cli -p $port PING &>/dev/null; then
                role=$(redis-cli -p $port INFO replication | grep "^role:" | cut -d: -f2 | tr -d '\r')
                marker_file="${MARKER_DIR}/preferred_master_${port}"
                preferred=""
                if [[ -f "$marker_file" ]]; then
                    preferred=" [PREFERRED MASTER]"
                fi
                echo "  - Порт $port: $role$preferred"
            fi
        done
        ;;
        
    *)
        echo "Неизвестная команда: $COMMAND"
        usage
        ;;
esac
```

## Установка и использование:

1. **Установите скрипты:**
```bash
# Сделайте скрипты исполняемыми
chmod +x /usr/local/bin/redis-restore-master.sh
chmod +x /usr/local/bin/redis-monitor-failback.sh
chmod +x /usr/local/bin/redis-manage-preferred-masters.sh
chmod +x /usr/local/bin/redis-failback-service.sh

# Создайте systemd сервис
/usr/local/bin/redis-failback-service.sh
systemctl daemon-reload
```

2. **Пометьте узлы как preferred masters:**
```bash
# Для каждого узла, который должен быть master
/usr/local/bin/redis-manage-preferred-masters.sh enable 6379
/usr/local/bin/redis-manage-preferred-masters.sh enable 6381
/usr/local/bin/redis-manage-preferred-masters.sh enable 6383
```

3. **Проверьте статус:**
```bash
/usr/local/bin/redis-manage-preferred-masters.sh status
```

Теперь при восстановлении упавшего master-узла, роль автоматически вернется к нему через процедуру failover.
