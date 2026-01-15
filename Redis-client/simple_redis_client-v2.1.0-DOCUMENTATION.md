# Simple Redis Client v2.1.0 - Документация

## Установка и Быстрый Старт

```python
from simple_redis_client import RedisClient

# Простое подключение
client = RedisClient(host='localhost', port=6379)
client.set('key', 'value')
print(client.get('key'))  # b'value'
client.close()
```

---

## Примеры Использования

### 1. Базовое подключение с decode_responses

```python
# Автоматическое декодирование байтов в строки
client = RedisClient(
    host='localhost',
    port=6379,
    decode_responses=True  # Возвращает строки вместо bytes
)

client.set('name', 'Alice')
print(client.get('name'))  # 'Alice' вместо b'Alice'
```

### 2. Подключение с паролем и выбором базы данных

```python
client = RedisClient(
    host='localhost',
    port=6379,
    password='your_password',
    username='default',  # Redis 6.0+
    db=2,  # Использовать БД номер 2
    decode_responses=True
)

client.ping()  # True
```

### 3. SSL/TLS подключение

```python
# С проверкой сертификата
client = RedisClient(
    host='redis.example.com',
    port=6380,
    ssl=True,
    ssl_ca_certs='/path/to/ca.crt',
    ssl_certfile='/path/to/client.crt',
    ssl_keyfile='/path/to/client.key'
)

# Без проверки сертификата (для self-signed)
client = RedisClient(
    host='localhost',
    port=6380,
    ssl=True,
    ssl_verify=False,  # Отключить проверку
    decode_responses=True
)
```

### 4. Настройка Connection Pool

```python
# Оптимизация для высоких нагрузок
client = RedisClient(
    host='localhost',
    port=6379,
    max_connections=100,  # Максимум соединений в пуле
    socket_timeout=10,    # Таймаут операций
    decode_responses=True
)

# Пул автоматически переиспользует соединения
for i in range(1000):
    client.set(f'key:{i}', f'value:{i}')
```

### 5. Работа с Redis Cluster

```python
# Подключение к кластеру
cluster = RedisClient(
    host='127.0.0.1',
    port=7000,
    is_cluster=True,
    decode_responses=True
)

# Автоматический роутинг по слотам
cluster.set('user:1000', 'Alice')
cluster.set('user:2000', 'Bob')

# Получить информацию о слоте
slot = cluster.keyslot('user:1000')
print(f"Key 'user:1000' belongs to slot {slot}")

# Hash tags для группировки ключей в одном слоте
cluster.set('user:{1000}:name', 'Alice')
cluster.set('user:{1000}:age', '25')
# Оба ключа в одном слоте благодаря {1000}
```

### 6. Чтение с реплик (Read from Replicas)

```python
# Распределение read запросов по репликам
cluster = RedisClient(
    host='127.0.0.1',
    port=7000,
    is_cluster=True,
    read_from_replicas=True,     # Читать с реплик
    replica_selector='random',   # random или round_robin
    decode_responses=True
)

# Запись идёт на мастер
cluster.set('key', 'value')

# Чтение может идти с реплики
value = cluster.get('key')

# Список узлов кластера
nodes = cluster.get_cluster_nodes()
for node in nodes:
    print(f"{node.role}: {node.host}:{node.port} ({len(node.slots)} slots)")
```

### 7. Автообновление топологии кластера

```python
cluster = RedisClient(
    host='127.0.0.1',
    port=7000,
    is_cluster=True,
    auto_refresh_topology=True,      # Автообновление
    topology_refresh_interval=300,   # Каждые 5 минут
    decode_responses=True
)

# Клиент автоматически обновляет маршрутизацию при failover

# Ручное обновление топологии
cluster.refresh_cluster_topology()
```

### 8. Redis Sentinel (High Availability)

```python
# Подключение через Sentinel
client = RedisClient(
    sentinels=[
        ('sentinel1.example.com', 26379),
        ('sentinel2.example.com', 26379),
        ('sentinel3.example.com', 26379)
    ],
    sentinel_service_name='mymaster',
    password='redis_password',
    decode_responses=True
)

# Клиент автоматически находит текущий мастер
client.set('key', 'value')
```

### 9. Работа со строками (Strings)

```python
client = RedisClient(decode_responses=True)

# SET с опциями
client.set('counter', 100, ex=60)  # Истекает через 60 секунд
client.set('flag', 'true', nx=True)  # SET if Not eXists
client.set('status', 'ok', xx=True)  # SET if eXists

# GET
value = client.get('counter')

# INCR / DECR
client.incr('counter')  # 101
client.decr('counter')  # 100

# TTL
ttl = client.ttl('counter')  # Оставшееся время жизни
client.persist('counter')    # Убрать expire
```

### 10. Работа с Hash

```python
# HSET одно поле
client.hset('user:1000', 'name', 'Alice')

# HSET несколько полей
client.hset('user:1000', mapping={
    'name': 'Alice',
    'age': '25',
    'city': 'Moscow'
})

# HGET
name = client.hget('user:1000', 'name')

# HGETALL
user = client.hgetall('user:1000')
print(user)  # {b'name': b'Alice', b'age': b'25', b'city': b'Moscow'}

# HLEN
count = client.hlen('user:1000')  # 3

# HDEL
client.hdel('user:1000', 'city')
```

### 11. Работа с List

```python
# LPUSH / RPUSH
client.lpush('queue', 'job1', 'job2', 'job3')
client.rpush('log', 'event1', 'event2')

# LLEN
length = client.llen('queue')

# LRANGE
items = client.lrange('queue', 0, -1)  # Все элементы

# LPOP / RPOP
job = client.lpop('queue')
last_event = client.rpop('log')
```

### 12. Работа с Set

```python
# SADD
client.sadd('tags', 'python', 'redis', 'nosql')

# SMEMBERS
tags = client.smembers('tags')  # set([b'python', b'redis', b'nosql'])

# SCARD
count = client.scard('tags')  # 3

# SISMEMBER
exists = client.sismember('tags', 'python')  # 1 (True)

# SREM
client.srem('tags', 'nosql')
```

### 13. Работа с Sorted Set

```python
# ZADD
client.zadd('leaderboard', {
    'Alice': 100.0,
    'Bob': 95.0,
    'Charlie': 110.0
})

# ZCARD
count = client.zcard('leaderboard')  # 3

# ZRANGE с scores
top3 = client.zrange('leaderboard', 0, 2, withscores=True)
# [(b'Bob', 95.0), (b'Alice', 100.0), (b'Charlie', 110.0)]

# ZREM
client.zrem('leaderboard', 'Bob')
```

### 14. Multi-key операции (кластер-безопасные)

```python
cluster = RedisClient(is_cluster=True, decode_responses=True)

# MSET - автоматическая группировка по слотам
cluster.mset({
    'key1': 'value1',
    'key2': 'value2',
    'key3': 'value3'
})

# MGET - автоматическая группировка по слотам
values = cluster.mget('key1', 'key2', 'key3')

# DEL - автоматическая группировка
deleted = cluster.delete('key1', 'key2', 'key3')

# Hash tags для операций в одном слоте
cluster.mset({
    'user:{1000}:name': 'Alice',
    'user:{1000}:age': '25',
    'user:{1000}:city': 'Moscow'
})
values = cluster.mget('user:{1000}:name', 'user:{1000}:age')
```

### 15. Pipeline для пакетной отправки команд

```python
# Контекстный менеджер
with client.pipeline() as pipe:
    pipe.set('key1', 'val1')
    pipe.set('key2', 'val2')
    pipe.incr('counter')
    pipe.get('key1')
    pipe.get('key2')
    results = pipe.execute()

print(results)
# ['OK', 'OK', 1, b'val1', b'val2']

# Ручное управление
pipe = client.pipeline()
for i in range(100):
    pipe.set(f'key:{i}', f'value:{i}')
results = pipe.execute()  # Все команды отправлены одним batch
```

### 16. Pipeline с транзакциями (MULTI/EXEC)

```python
# Атомарная транзакция
with client.pipeline(transaction=True) as pipe:
    pipe.set('account:1', 100)
    pipe.incr('account:1')
    pipe.decr('account:2')
    results = pipe.execute()

# Все команды выполнены атомарно
```

### 17. Lua Scripts - простое использование

```python
# EVAL
script = """
    local value = redis.call('GET', KEYS[1])
    if value then
        return redis.call('INCR', KEYS[1])
    else
        redis.call('SET', KEYS[1], ARGV[1])
        return tonumber(ARGV[1])
    end
"""

result = client.eval(script, 1, 'counter', '10')
print(result)  # 10 (если ключ не существовал)

# EVALSHA с автозагрузкой
sha = client.script_load(script)
result = client.evalsha(sha, 1, 'counter', '10')
```

### 18. Lua Scripts - продвинутое использование

```python
# Регистрация скрипта для удобного использования
increment_script = client.register_script("""
    local current = redis.call('GET', KEYS[1])
    if current then
        return redis.call('INCRBY', KEYS[1], ARGV[1])
    else
        redis.call('SET', KEYS[1], ARGV[1])
        return tonumber(ARGV[1])
    end
""")

# Вызов как функция
result = increment_script(keys=['mycounter'], args=['5'])
print(result)  # 5

result = increment_script(keys=['mycounter'], args=['3'])
print(result)  # 8

# Скрипт автоматически использует EVALSHA с fallback на EVAL
```

### 19. Lua Scripts в кластере с hash tags

```python
cluster = RedisClient(is_cluster=True, decode_responses=True)

# Скрипт для работы с несколькими ключами
multi_key_script = """
    redis.call('SET', KEYS[1], ARGV[1])
    redis.call('SET', KEYS[2], ARGV[2])
    return redis.call('GET', KEYS[1])
"""

# Все ключи должны быть в одном слоте (используем hash tag)
result = cluster.eval(
    multi_key_script,
    2,  # numkeys
    'user:{1000}:name',  # KEYS[1]
    'user:{1000}:age',   # KEYS[2]
    'Alice',             # ARGV[1]
    '25'                 # ARGV[2]
)

print(result)  # 'Alice'
```

### 20. SCAN итератор (memory-efficient)

```python
# Итерация по всем ключам без блокировки Redis
for key in client.scan_iter(match='user:*', count=100):
    print(key)

# SCAN в кластере (все узлы)
if client.is_cluster:
    all_keys = []
    for key in client.scan_iter(match='*'):
        all_keys.append(key)
```

### 21. Callbacks для мониторинга соединений

```python
def on_connect(conn):
    print(f"Connected to {conn.host}:{conn.port}")

def on_disconnect(conn):
    print(f"Disconnected from {conn.host}:{conn.port}")

def on_reconnect(conn, attempt):
    print(f"Reconnected to {conn.host}:{conn.port} after {attempt} attempts")

client = RedisClient(
    host='localhost',
    port=6379,
    # Callbacks передаются внутрь ConnectionPool
    decode_responses=True
)

# Для прямого подключения (без пула) callbacks работают так:
from simple_redis_client import RedisConnection

conn = RedisConnection(
    host='localhost',
    port=6379,
    on_connect=on_connect,
    on_disconnect=on_disconnect,
    on_reconnect=on_reconnect
)
```

### 22. Настройка логирования

```python
import logging

# Настроить логирование для просмотра внутренней работы клиента
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Включить DEBUG для детальной информации
logging.getLogger('simple_redis_client').setLevel(logging.DEBUG)

client = RedisClient(host='localhost', port=6379)
client.set('key', 'value')  # Увидите логи подключения и команд

# Отключить логи клиента (вернуться к NullHandler)
logging.getLogger('simple_redis_client').setLevel(logging.CRITICAL)
```

### 23. Health Checks

```python
# Проверка работоспособности
if client.ping():
    print("Redis is alive")

# В кластере можно проверить каждый узел
if client.is_cluster:
    for node in client.get_cluster_nodes():
        pool = client.cluster_pools.get(node.node_id)
        if pool:
            conn = pool.get_connection()
            try:
                healthy = conn.is_healthy()
                print(f"{node}: {'OK' if healthy else 'FAIL'}")
            finally:
                pool.release(conn)
```

### 24. Управление скриптами

```python
# Загрузить скрипт на все узлы кластера
script = "return redis.call('GET', KEYS[1])"
sha = client.script_load(script)
print(f"Script SHA: {sha}")

# Проверить существование скрипта
exists = client.script_exists(sha)
print(exists)  # [1] если есть

# Удалить все скрипты
client.script_flush()
```

### 25. Обработка ошибок

```python
from simple_redis_client import (
    RedisError, 
    RedisConnectionError, 
    RedisClusterError
)

try:
    client = RedisClient(host='invalid-host', port=6379)
    client.set('key', 'value')

except RedisConnectionError as e:
    print(f"Connection failed: {e}")

except RedisClusterError as e:
    print(f"Cluster error: {e}")

except RedisError as e:
    print(f"Redis error: {e}")

finally:
    client.close()
```

---

## Конфигурация параметров

### Основные параметры

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `host` | str | `'localhost'` | Хост Redis сервера |
| `port` | int | `6379` | Порт Redis сервера |
| `password` | str | `None` | Пароль для AUTH |
| `username` | str | `None` | Username для AUTH (Redis 6.0+) |
| `db` | int | `0` | Номер базы данных |
| `socket_timeout` | int | `5` | Таймаут операций в секундах |
| `decode_responses` | bool | `False` | Автодекодирование bytes в str |

### SSL/TLS параметры

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `ssl` | bool | `False` | Использовать SSL/TLS |
| `ssl_verify` | bool | `True` | Проверять сертификат сервера |
| `ssl_check_hostname` | bool | `True` | Проверять hostname в сертификате |
| `ssl_ca_certs` | str | `None` | Путь к CA сертификату |
| `ssl_certfile` | str | `None` | Путь к клиентскому сертификату |
| `ssl_keyfile` | str | `None` | Путь к приватному ключу |

### Cluster параметры

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `is_cluster` | bool | `False` | Режим кластера |
| `read_from_replicas` | bool | `False` | Читать с реплик |
| `replica_selector` | str | `'random'` | `'random'` или `'round_robin'` |
| `auto_refresh_topology` | bool | `True` | Автообновление топологии |
| `topology_refresh_interval` | int | `300` | Интервал обновления (сек) |

### Connection Pool параметры

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `max_connections` | int | `50` | Макс. соединений в пуле |

### Sentinel параметры

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `sentinels` | List[Tuple] | `None` | Список (host, port) Sentinel'ов |
| `sentinel_service_name` | str | `None` | Имя мастера в Sentinel |

---

## Best Practices

1. **Всегда закрывайте клиента** после использования:
   ```python
   try:
       client = RedisClient(...)
       # ваш код
   finally:
       client.close()
   ```

2. **Используйте decode_responses=True** для работы со строками:
   ```python
   client = RedisClient(decode_responses=True)
   ```

3. **Pipeline для массовых операций** (до 100x быстрее):
   ```python
   with client.pipeline() as pipe:
       for i in range(10000):
           pipe.set(f'key:{i}', i)
       pipe.execute()
   ```

4. **Hash tags в кластере** для multi-key операций:
   ```python
   # ✓ Правильно - все ключи в одном слоте
   client.mget('user:{1000}:name', 'user:{1000}:age')

   # ✗ Ошибка CROSSSLOT в кластере
   client.mget('user:1000:name', 'user:2000:name')
   ```

5. **Используйте scan_iter()** вместо keys() для больших датасетов:
   ```python
   # ✓ Memory-efficient
   for key in client.scan_iter(match='user:*'):
       process(key)

   # ✗ Блокирует Redis
   keys = client.execute_command('KEYS', 'user:*')
   ```

6. **Register scripts** для часто используемых Lua скриптов:
   ```python
   my_script = client.register_script("...")
   # EVALSHA с автоматическим fallback
   result = my_script(keys=['key1'], args=['arg1'])
   ```

---

## Производительность

- **Connection Pool**: Переиспользование соединений (до 10x быстрее)
- **Buffered I/O**: Чтение крупными блоками (до 5x быстрее парсинг RESP)
- **Pipeline**: Batch команды через один RTT (до 100x быстрее)
- **Auto-reconnect**: Экспоненциальный backoff предотвращает DDoS при сбоях

---

## Лицензия

MIT License

---

## Поддержка

- GitHub: https://github.com/yourusername/simple-redis-client
- Issues: https://github.com/yourusername/simple-redis-client/issues
