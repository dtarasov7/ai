На основе анализа вашей ситуации и результатов поиска, я вижу классическую проблему с пулом соединений в Nginx reverse proxy при высокой нагрузке. Вот основные причины и решения:

## Основная причина проблемы

**Отсутствие или неправильная настройка keepalive соединений** между Server1 (Nginx reverse proxy) и upstream серверами. Когда нагрузка высокая (125000 запросов за 10 минут), Nginx начинает создавать новые TCP соединения для каждого запроса, что добавляет задержки из-за TCP handshake.

## Ключевые проблемы и решения

### 1. Настройка upstream keepalive
Для каждого worker процесса Nginx ограничено количество keepalive соединений к upstream серверам.  При высокой нагрузке этого лимита не хватает, и Nginx вынужден создавать новые соединения, что добавляет задержки.

**Решение:**
```nginx
upstream backend {
    server server2_ip:port;
    keepalive 32;  # Количество keepalive соединений на worker
}

location / {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}
```

### 2. Оптимизация таймаутов
При высокой нагрузке стандартные таймауты могут быть недостаточными. 

**Решение:**
```nginx
location / {
    proxy_read_timeout 60s;
    proxy_connect_timeout 5s;
    proxy_next_upstream error timeout http_502 http_503 http_504;
}
```

### 3. Максимальное количество соединений
При нагрузке в ~200 запросов/секунду может не хватать лимита соединений. 

**Решение:**
```nginx
upstream backend {
    server server2_ip:port max_conns=1000;
    keepalive 64;
}
```

### 4. Проверка сетевой инфраструктуры
Проблема может быть на уровне LoadBalancer или FW при высокой нагрузке.  Даже если Server2 обрабатывает запросы быстро, промежуточные компоненты могут создавать задержки при установлении соединений.

## Диагностические шаги

1. **Проверьте количество активных соединений** на Server1:
   ```bash
   netstat -an | grep ESTABLISHED | wc -l
   ```

2. **Мониторьте upstream response time** в реальном времени:
   ```nginx
   log_format custom '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    '$upstream_response_time $request_time';
   ```

3. **Проверьте параметры worker_processes и worker_connections**:
   ```nginx
   events {
       worker_connections 10240;
   }
   ```

## Почему это происходит именно при высокой нагрузке?

Без нагрузки Nginx использует keepalive соединения эффективно. При высокой нагрузке:
- Пул keepalive соединений исчерпывается 
- Nginx создает новые TCP соединения для каждого запроса
- TCP handshake добавляет 1-3 RTT (round-trip time) задержки
- При сетевой задержке 100ms это может добавить 300ms+ на каждое новое соединение
- При нагрузке в 200 RPS соединения создаются постоянно, накапливая задержки

## Дополнительные рекомендации

1. **Увеличьте keepalive_requests** (количество запросов на соединение):
   ```nginx
   keepalive_requests 10000;
   ```

2. **Настройте keepalive_timeout** для upstream:
   ```nginx
   upstream backend {
       keepalive_timeout 60s;  # 
   }
   ```

3. **Проверьте производительность LoadBalancer и FW** под нагрузкой - они могут стать узким местом при установлении новых соединений.

Эта проблема типична для reverse proxy конфигураций с высокой нагрузкой и решается правильной настройкой пула соединений между компонентами инфраструктуры. 
