Вот обновленная версия bash-скрипта на основе вашего запроса. Я сделал его более надежным, добавив обработку ошибок и поддержку дополнительных опций (например, указание протокола TLS версии для старых серверов). Скрипт по-прежнему не передает никаких данных прикладного уровня, не использует клиентские сертификаты и полагается только на минимальный TLS-handshake с помощью `openssl s_client`.

### Основные принципы работы:
- **Проверка на TLS/mTLS**: Пытается выполнить TLS-handshake. Если сервер запрашивает клиентский сертификат (CertificateRequest), определяет как mTLS.
- **Проверка на plain (обычное)**: Если TLS-handshake не удался, но TCP-порт открыт (проверяется без отправки данных).
- **Unknown**: Если порт недоступен или handshake не дает четкого результата.
- Требования: `bash`, `openssl`, `timeout` (из GNU coreutils), `nc` (netcat) для TCP-проверки (альтернатива bash-встроенной).

### Скрипт: `detect_port_tls.sh`

```bash
#!/usr/bin/env bash
# detect_port_tls.sh
# Определяет: plain | tls | mtls | unknown
# Использование:
#   ./detect_port_tls.sh PORT
#   ./detect_port_tls.sh HOST PORT
#   ./detect_port_tls.sh HOST:PORT
#
# Переменные окружения:
#   TIMEOUT   — таймаут в секундах (по умолчанию 5)
#   TLS_VERS  — версии TLS для попыток (по умолчанию: -tls1_2 -tls1_3; можно добавить -tls1_1 и т.д.)

set -u

TIMEOUT="${TIMEOUT:-5}"
TLS_VERS="${TLS_VERS:--tls1_2 -tls1_3}"  # По умолчанию TLS 1.2/1.3; добавьте -tls1 для старых серверов

usage() {
  echo "Usage: $0 PORT | HOST PORT | HOST:PORT" >&2
  exit 2
}

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; exit 3; }
}

parse_args() {
  local a1="${1-}" a2="${2-}"
  HOST="127.0.0.1"
  PORT=""

  if [[ -n "$a1" && -z "$a2" ]]; then
    if [[ "$a1" == *:* ]]; then
      HOST="${a1%:*}"
      PORT="${a1##*:}"
    else
      PORT="$a1"
    fi
  elif [[ -n "$a1" && -n "$a2" ]]; then
    HOST="$a1"
    PORT="$a2"
  else
    usage
  fi

  [[ "$PORT" =~ ^[0-9]{1,5}$ ]] || { echo "Invalid port: $PORT" >&2; exit 2; }
}

# Быстрый тест на открытый TCP-порт без отправки данных (используем nc для надежности)
tcp_open() {
  timeout "$TIMEOUT" nc -z -w "$TIMEOUT" "$HOST" "$PORT" 2>/dev/null
}

# Пытаемся выполнить TLS-рукопожатие без клиентских сертификатов
try_tls() {
  # Включаем отладочные сообщения рукопожатия, чтобы поймать CertificateRequest
  timeout "$TIMEOUT" openssl s_client \
    -connect "$HOST:$PORT" \
    -servername "$HOST" \
    -verify 0 \
    $TLS_VERS \
    -tlsextdebug -state -msg \
    -ign_eof \
    < /dev/null 2>&1
}

main() {
  need openssl
  need timeout
  need nc  # Для tcp_open
  parse_args "$@"

  # Сначала пробуем TLS-рукопожатие
  TLS_OUT="$(try_tls)"
  TLS_RC=$?

  # Признак успешного рукопожатия (появляется блок SSL-Session или Verify return code: 0)
  if echo "$TLS_OUT" | grep -qE "SSL-Session:|Verify return code: 0"; then
    # Проверим, запрашивал ли сервер клиентский сертификат (mTLS)
    if echo "$TLS_OUT" | grep -qiE 'CertificateRequest|Certificate Request|client certificate'; then
      echo "mtls"
      exit 0
    else
      echo "tls"
      exit 0
    fi
  fi

  # Если рукопожатие не удалось, но в логах явно проскакивает требование сертификата — mTLS
  if echo "$TLS_OUT" | grep -qiE 'certificate required|alert.*certificate|handshake failure'; then
    echo "mtls"
    exit 0
  fi

  # Если TLS не взлетел, проверим, вообще ли порт открыт
  if tcp_open; then
    echo "plain"
  else
    echo "unknown"
  fi
}

main "$@"
```

### Как использовать:
1. Сделайте скрипт исполняемым: `chmod +x detect_port_tls.sh`.
2. Примеры запуска:
   - `./detect_port_tls.sh 443` — проверка локального порта 443 (ожидается "tls" для HTTPS).
   - `./detect_port_tls.sh example.com 443` — проверка на удаленном хосте (может быть "tls" или "mtls").
   - `./detect_port_tls.sh 80` — обычно "plain" (HTTP без TLS).
   - `TIMEOUT=10 TLS_VERS="-tls1 -tls1_1 -tls1_2 -tls1_3" ./detect_port_tls.sh oldserver:443` — для старых серверов с поддержкой TLS 1.0/1.1.
   - `./detect_port_tls.sh 25` — SMTP без STARTTLS на этапе подключения (ожидается "plain").

### Замечания и ограничения:
- **Нет передачи данных**: Скрипт только устанавливает TCP-соединение и пытается TLS-handshake. Никаких HTTP-запросов, SMTP-команд и т.д.
- **mTLS-определение**: Работает, если сервер запрашивает сертификат на уровне TLS (CertificateRequest). Если mTLS требуется только после прикладной команды (например, в HTTP), это не определит — для этого нужно отправлять данные, чего мы избегаем.
- **Старые серверы**: Если сервер поддерживает только старые версии TLS/SSL, добавьте их в `TLS_VERS` (например, `-ssl3` для очень старых, но это редко).
- **Ошибки**: Если порт закрыт или firewall блокирует, вернется "unknown". Для отладки запустите с `bash -x` или проверьте вывод `TLS_OUT` (добавьте `echo "$TLS_OUT"` в скрипт).
- **Зависимости**: Убедитесь, что `openssl`, `timeout` и `nc` установлены (на Ubuntu: `apt install openssl coreutils netcat-openbsd`).

Если нужно доработать (например, добавить поддержку других инструментов или больше версий TLS), дайте знать!
