Вот bash скрипт для определения типа соединения без использования сертификатов:

```bash
#!/bin/bash

# Скрипт для определения типа соединения (TLS, mTLS или обычное TCP)
# Использование: ./check_connection.sh <host> <port>

# Проверка аргументов
if [ $# -ne 2 ]; then
    echo "Использование: $0 <host> <port>"
    echo "Пример: $0 localhost 443"
    exit 1
fi

HOST="$1"
PORT="$2"
TIMEOUT=5

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Проверка соединения $HOST:$PORT..."
echo "----------------------------------------"

# Функция для проверки TLS/mTLS
check_tls() {
    local result
    
    # Попытка TLS handshake без предоставления сертификата
    # -showcerts показывает цепочку сертификатов сервера
    # -servername для SNI
    # -prexit завершает после handshake
    result=$(timeout $TIMEOUT openssl s_client \
        -connect "$HOST:$PORT" \
        -showcerts \
        -servername "$HOST" \
        -prexit \
        </dev/null 2>&1)
    
    local exit_code=$?
    
    # Если handshake успешен
    if [ $exit_code -eq 0 ] || echo "$result" | grep -q "SSL handshake has read"; then
        
        # Проверка на mTLS - ищем запрос клиентского сертификата
        if echo "$result" | grep -qE "(CertificateRequest|Client Certificate Types:|Acceptable client certificate|Request CERT)"; then
            echo -e "${YELLOW}🔐 Тип соединения: mTLS${NC}"
            echo "   Сервер запрашивает клиентский сертификат"
            
            # Дополнительная информация о требованиях mTLS
            if echo "$result" | grep -q "Acceptable client certificate CA names"; then
                echo "   Сервер указал список допустимых CA для клиентских сертификатов"
            fi
            return 2
        else
            echo -e "${GREEN}🔒 Тип соединения: TLS/SSL${NC}"
            
            # Определение версии TLS
            tls_version=$(echo "$result" | grep -oP "Protocol\s+:\s+\K[^\s]+")
            if [ -n "$tls_version" ]; then
                echo "   Версия протокола: $tls_version"
            fi
            
            # Информация о сертификате сервера
            cert_subject=$(echo "$result" | grep -m1 "subject=" | sed 's/subject=//')
            if [ -n "$cert_subject" ]; then
                echo "   Сертификат сервера: $cert_subject"
            fi
            return 1
        fi
    else
        return 0
    fi
}

# Функция для проверки обычного TCP
check_plain_tcp() {
    # Используем несколько методов для надежности
    
    # Метод 1: nc (netcat)
    if command -v nc &>/dev/null; then
        if timeout $TIMEOUT nc -z -v "$HOST" "$PORT" &>/dev/null; then
            return 0
        fi
    fi
    
    # Метод 2: bash built-in /dev/tcp
    if timeout $TIMEOUT bash -c "exec 3<>/dev/tcp/$HOST/$PORT" 2>/dev/null; then
        exec 3>&-
        return 0
    fi
    
    # Метод 3: telnet (если доступен)
    if command -v telnet &>/dev/null; then
        if timeout $TIMEOUT bash -c "echo quit | telnet $HOST $PORT" &>/dev/null; then
            return 0
        fi
    fi
    
    return 1
}

# Основная логика проверки
check_tls
tls_result=$?

if [ $tls_result -eq 0 ]; then
    # TLS handshake не удался, проверяем обычное TCP
    if check_plain_tcp; then
        echo -e "${GREEN}📡 Тип соединения: Plain TCP${NC}"
        echo "   Порт открыт, но не использует TLS/SSL"
        
        # Попытка определить протокол по порту
        case $PORT in
            80|8080|8000)
                echo "   Вероятно: HTTP"
                ;;
            22)
                echo "   Вероятно: SSH"
                ;;
            21)
                echo "   Вероятно: FTP"
                ;;
            23)
                echo "   Вероятно: Telnet"
                ;;
            25|587)
                echo "   Вероятно: SMTP"
                ;;
            3306)
                echo "   Вероятно: MySQL"
                ;;
            5432)
                echo "   Вероятно: PostgreSQL"
                ;;
            6379)
                echo "   Вероятно: Redis"
                ;;
            *)
                echo "   Неизвестный протокол"
                ;;
        esac
    else
        echo -e "${RED}❌ Ошибка: Не удалось подключиться${NC}"
        echo "   Возможные причины:"
        echo "   - Порт закрыт или недоступен"
        echo "   - Хост недоступен"
        echo "   - Блокировка файрволом"
    fi
fi

echo "----------------------------------------"

# Дополнительная проверка с nmap (если доступен)
if command -v nmap &>/dev/null && [ "$3" == "--nmap" ]; then
    echo ""
    echo "📊 Дополнительная информация (nmap):"
    nmap -sV -p "$PORT" "$HOST" 2>/dev/null | grep -E "^$PORT"
fi

exit 0
```

### Дополнительный упрощенный вариант:

```bash
#!/bin/bash

# Минималистичная версия для быстрой проверки

[ $# -ne 2 ] && { echo "Usage: $0 <host> <port>"; exit 1; }

HOST=$1
PORT=$2

# TLS проверка
TLS_CHECK=$(timeout 3 openssl s_client -connect $HOST:$PORT </dev/null 2>&1)

if echo "$TLS_CHECK" | grep -q "SSL handshake"; then
    if echo "$TLS_CHECK" | grep -qE "CertificateRequest|Client Certificate"; then
        echo "mTLS (mutual TLS) - требуется клиентский сертификат"
    else
        echo "TLS/SSL - стандартное шифрованное соединение"
    fi
elif timeout 2 bash -c "exec 3<>/dev/tcp/$HOST/$PORT" 2>/dev/null; then
    exec 3>&-
    echo "Plain TCP - обычное незашифрованное соединение"
else
    echo "Недоступен - порт закрыт или хост недоступен"
fi
```

### Использование:

```bash
# Сделать исполняемым
chmod +x check_connection.sh

# Проверить HTTPS сервер
./check_connection.sh google.com 443

# Проверить SSH
./check_connection.sh localhost 22

# Проверить с дополнительной информацией от nmap
./check_connection.sh example.com 443 --nmap
```

### Примеры вывода:

```bash
# TLS сервер
$ ./check_connection.sh google.com 443
🔍 Проверка соединения google.com:443...
----------------------------------------
🔒 Тип соединения: TLS/SSL
   Версия протокола: TLSv1.3
   Сертификат сервера: /CN=*.google.com
----------------------------------------

# mTLS сервер
$ ./check_connection.sh mtls-server.com 8443
🔍 Проверка соединения mtls-server.com:8443...
----------------------------------------
🔐 Тип соединения: mTLS
   Сервер запрашивает клиентский сертификат
   Сервер указал список допустимых CA для клиентских сертификатов
----------------------------------------

# Обычный TCP
$ ./check_connection.sh localhost 22
🔍 Проверка соединения localhost:22...
----------------------------------------
📡 Тип соединения: Plain TCP
   Порт открыт, но не использует TLS/SSL
   Вероятно: SSH
----------------------------------------
```

Скрипт работает без использования сертификатов и только проверяет тип ожидаемого соединения.
