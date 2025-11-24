Ниже — простой bash‑скрипт, который пытается определить, что ожидает сервис на порту: обычное (без TLS), TLS или mTLS. Данных уровня приложения не отправляет, клиентских сертификатов не использует — лишь минимальный TLS‑handshake.

Скрипт опирается на openssl s_client:
- если TLS‑рукопожатие успешно — считаем TLS;
- если сервер запрашивает клиентский сертификат (CertificateRequest) — считаем mTLS;
- если TLS‑рукопожатие не удаётся, но TCP‑порт доступен — считаем обычное (без TLS);
- если порт недоступен — unknown.

Требования: bash, openssl, timeout (GNU coreutils).

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

set -u

TIMEOUT="${TIMEOUT:-5}"

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

# Быстрый тест на открытый TCP-порт без отправки данных
tcp_open() {
  timeout "$TIMEOUT" bash -c "exec 3<>/dev/tcp/$HOST/$PORT" 2>/dev/null
}

# Пытаемся выполнить TLS-рукопожатие без клиентских сертификатов
try_tls() {
  # Включаем отладочные сообщения рукопожатия, чтобы поймать CertificateRequest
  timeout "$TIMEOUT" openssl s_client \
    -connect "$HOST:$PORT" \
    -servername "$HOST" \
    -verify 0 \
    -tlsextdebug -state -msg \
    -ign_eof \
    < /dev/null 2>&1
}

main() {
  need openssl
  need timeout
  parse_args "$@"

  # Сначала пробуем TLS-рукопожатие
  TLS_OUT="$(try_tls)"
  TLS_RC=$?

  # Признак успешного рукопожатия (появляется блок SSL-Session)
  if echo "$TLS_OUT" | grep -q "SSL-Session:"; then
    # Проверим, запрашивал ли сервер клиентский сертификат (mTLS)
    if echo "$TLS_OUT" | grep -qiE 'CertificateRequest|Certificate Request'; then
      # Сервер запросил клиентский сертификат — mTLS (возможно обязательный, возможно опциональный)
      echo "mtls"
      exit 0
    else
      echo "tls"
      exit 0
    fi
  fi

  # Если рукопожатие не удалось, но в логах явно проскакивает требование сертификата — тоже mTLS
  if echo "$TLS_OUT" | grep -qiE 'certificate required|alert.*certificate'; then
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

Примеры:
- ./detect_port_tls.sh 443 → tls (локальный 443, если HTTPS)
- ./detect_port_tls.sh example.com 443 → tls или mtls
- ./detect_port_tls.sh 25 → plain (SMTP без STARTTLS на этапе подключения)
- TIMEOUT=2 ./detect_port_tls.sh 8443 → mtls (если сервер требует клиентский сертификат)

Замечания и ограничения:
- Скрипт не отправляет данных прикладного уровня (HTTP/SMTP и т.д.), только TLS‑handshake.
- Если сервер запрашивает клиентский сертификат только после прикладной команды (например, HTTP location с client_auth), без отправки запроса это определить нельзя.
- Очень старые серверы, поддерживающие только TLS 1.0/1.1, могут быть определены как plain. При необходимости можно добавить попытки с -tls1/-tls1_1.
