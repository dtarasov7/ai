# Анализ модуля Redis Client

## Общая оценка

Это **качественный, production-ready** Redis клиент с впечатляющим функционалом:
- Полная реализация RESP-протокола без зависимостей
- Поддержка Redis Cluster с MOVED/ASK редиректами
- SSL/TLS, аутентификация, scan_iter
- Корректная обработка hash tags `{}`

## Топ-3 рекомендации с готовым кодом

---

### 1. Connection Pool (критически важно для продакшена)

**Проблема:** Каждое соединение создаётся заново и никогда не переиспользуется. При высокой нагрузке это убьёт производительность и исчерпает файловые дескрипторы.

**Решение:** Добавить класс `ConnectionPool` и интегрировать его в `RedisClient`.

```python
import threading
from collections import deque
from contextlib import contextmanager
import time


class ConnectionPool:
    """Пул соединений для Redis"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 ssl_check_hostname: bool = True,
                 max_connections: int = 50,
                 min_idle: int = 5,
                 max_idle_time: int = 300):
        
        self.connection_kwargs = {
            'host': host,
            'port': port,
            'password': password,
            'username': username,
            'db': db,
            'socket_timeout': socket_timeout,
            'ssl': ssl,
            'ssl_ca_certs': ssl_ca_certs,
            'ssl_certfile': ssl_certfile,
            'ssl_keyfile': ssl_keyfile,
            'ssl_check_hostname': ssl_check_hostname,
        }
        
        self.max_connections = max_connections
        self.min_idle = min_idle
        self.max_idle_time = max_idle_time
        
        self._pool: deque = deque()  # (connection, last_used_time)
        self._in_use: set = set()
        self._lock = threading.RLock()
        self._created_count = 0
        
        # Предварительно создаём минимальное количество соединений
        self._warm_up()
    
    def _warm_up(self):
        """Создать минимальное количество соединений"""
        for _ in range(self.min_idle):
            try:
                conn = self._create_connection()
                self._pool.append((conn, time.time()))
            except Exception as e:
                logger.warning(f"Failed to create warm-up connection: {e}")
                break
    
    def _create_connection(self) -> RedisConnection:
        """Создать новое соединение"""
        with self._lock:
            if self._created_count >= self.max_connections:
                raise RedisConnectionError(
                    f"Connection pool exhausted (max={self.max_connections})"
                )
            conn = RedisConnection(**self.connection_kwargs)
            self._created_count += 1
            logger.debug(f"Created new connection (total: {self._created_count})")
            return conn
    
    def get_connection(self) -> RedisConnection:
        """Получить соединение из пула"""
        with self._lock:
            # Пытаемся взять из пула
            while self._pool:
                conn, last_used = self._pool.popleft()
                
                # Проверяем, не устарело ли соединение
                if time.time() - last_used > self.max_idle_time:
                    self._close_connection(conn)
                    continue
                
                # Проверяем, живое ли соединение
                try:
                    if conn.ping():
                        self._in_use.add(id(conn))
                        return conn
                except:
                    self._close_connection(conn)
                    continue
            
            # Пул пуст — создаём новое соединение
            conn = self._create_connection()
            self._in_use.add(id(conn))
            return conn
    
    def release_connection(self, conn: RedisConnection):
        """Вернуть соединение в пул"""
        with self._lock:
            conn_id = id(conn)
            if conn_id in self._in_use:
                self._in_use.discard(conn_id)
                
                # Проверяем, не переполнен ли пул
                if len(self._pool) < self.max_connections:
                    self._pool.append((conn, time.time()))
                else:
                    self._close_connection(conn)
            else:
                # Соединение не из пула — просто закрываем
                self._close_connection(conn)
    
    def _close_connection(self, conn: RedisConnection):
        """Закрыть соединение"""
        with self._lock:
            self._created_count = max(0, self._created_count - 1)
        try:
            conn.close()
        except:
            pass
    
    @contextmanager
    def connection(self):
        """Контекстный менеджер для соединения"""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.release_connection(conn)
    
    def close_all(self):
        """Закрыть все соединения"""
        with self._lock:
            # Закрываем соединения в пуле
            while self._pool:
                conn, _ = self._pool.popleft()
                try:
                    conn.close()
                except:
                    pass
            self._created_count = 0
            self._in_use.clear()
    
    @property
    def stats(self) -> Dict[str, int]:
        """Статистика пула"""
        with self._lock:
            return {
                'total_created': self._created_count,
                'idle': len(self._pool),
                'in_use': len(self._in_use),
                'max_connections': self.max_connections,
            }
```

**Изменения в `RedisClient.__init__`:**

```python
class RedisClient:
    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 decode_responses: bool = False, is_cluster: bool = False,
                 # Новые параметры для пула
                 max_connections: int = 50,
                 min_idle_connections: int = 5,
                 use_pool: bool = True):
        
        # ... существующий код ...
        
        self.use_pool = use_pool
        self.pool: Optional[ConnectionPool] = None
        self.cluster_pools: Dict[str, ConnectionPool] = {}  # Пулы для каждого узла кластера
        
        self._init_connection()
    
    def _init_connection(self):
        pool_kwargs = {
            'host': self.host,
            'port': self.port,
            'password': self.password,
            'username': self.username,
            'db': self.db,
            'socket_timeout': self.socket_timeout,
            'ssl': self.ssl,
            'ssl_ca_certs': self.ssl_ca_certs,
            'ssl_certfile': self.ssl_certfile,
            'ssl_keyfile': self.ssl_keyfile,
            'max_connections': self.max_connections if hasattr(self, 'max_connections') else 50,
        }
        
        if self.use_pool:
            self.pool = ConnectionPool(**pool_kwargs)
            # Для обратной совместимости
            self.connection = self.pool.get_connection()
            self.pool.release_connection(self.connection)
            self.connection = None
        else:
            self.connection = RedisConnection(**{k: v for k, v in pool_kwargs.items() 
                                                  if k != 'max_connections'})
        
        if self.is_cluster:
            self._load_cluster_topology()
    
    def _get_connection(self) -> RedisConnection:
        """Получить соединение (из пула или напрямую)"""
        if self.use_pool and self.pool:
            return self.pool.get_connection()
        return self.connection
    
    def _release_connection(self, conn: RedisConnection):
        """Вернуть соединение"""
        if self.use_pool and self.pool:
            self.pool.release_connection(conn)
    
    # Обновлённый execute_command
    def execute_command(self, *args, key: Optional[Union[str, bytes]] = None) -> Any:
        max_redirects = 5
        redirect_count = 0
        
        if key is None and len(args) > 1:
            key = args[1]
        
        conn = None
        pool = None
        
        try:
            if self.is_cluster and key:
                slot = self._get_slot(key)
                node_id = self.cluster_slots.get(slot)
                if node_id and node_id in self.cluster_pools:
                    pool = self.cluster_pools[node_id]
                    conn = pool.get_connection()
                else:
                    pool = self.pool
                    conn = self._get_connection()
            else:
                pool = self.pool
                conn = self._get_connection()
            
            while redirect_count < max_redirects:
                try:
                    response = conn.execute_command(*args)
                    if self.decode_responses:
                        response = self._decode_response(response)
                    return response
                except RedisError as e:
                    error_msg = str(e)
                    
                    if error_msg.startswith('MOVED'):
                        # ... существующая логика MOVED ...
                        # Но теперь создаём пул для нового узла
                        parts = error_msg.split()
                        if len(parts) >= 3:
                            slot = int(parts[1])
                            node_addr = parts[2]
                            host, port = node_addr.split(':')
                            node_id = f"{host}:{port}"
                            
                            if node_id not in self.cluster_pools:
                                self.cluster_pools[node_id] = ConnectionPool(
                                    host=host, port=int(port),
                                    password=self.password, username=self.username,
                                    socket_timeout=self.socket_timeout, ssl=self.ssl,
                                    max_connections=self.max_connections if hasattr(self, 'max_connections') else 50
                                )
                            
                            # Освобождаем старое соединение
                            if pool:
                                pool.release_connection(conn)
                            
                            pool = self.cluster_pools[node_id]
                            conn = pool.get_connection()
                            self.cluster_slots[slot] = node_id
                            redirect_count += 1
                            continue
                    
                    elif error_msg.startswith('ASK'):
                        # ... существующая логика ASK ...
                        pass
                    
                    raise
            
            raise RedisClusterError("Too many redirects")
        
        finally:
            if pool and conn:
                pool.release_connection(conn)
    
    def close(self):
        """Закрыть все подключения"""
        if self.pool:
            self.pool.close_all()
        for pool in self.cluster_pools.values():
            pool.close_all()
        self.cluster_pools.clear()
        if self.connection:
            self.connection.close()
    
    def pool_stats(self) -> Dict[str, Any]:
        """Статистика пулов соединений"""
        stats = {}
        if self.pool:
            stats['main'] = self.pool.stats
        for node_id, pool in self.cluster_pools.items():
            stats[node_id] = pool.stats
        return stats
```

---

### 2. Автоматическое обновление топологии кластера

**Проблема:** Топология грузится только при старте. При failover или добавлении узлов клиент не узнает об изменениях до получения MOVED (неэффективно).

**Решение:**

```python
import time
import threading


class RedisClient:
    def __init__(self, ...,
                 # Новые параметры
                 topology_refresh_interval: int = 30,
                 topology_refresh_on_error: bool = True):
        
        # ... существующий код ...
        
        self.topology_refresh_interval = topology_refresh_interval
        self.topology_refresh_on_error = topology_refresh_on_error
        self._last_topology_refresh: float = 0
        self._topology_lock = threading.Lock()
        self._refresh_in_progress = False
        
        self._init_connection()
    
    def _maybe_refresh_topology(self, force: bool = False):
        """Обновить топологию, если пора"""
        if not self.is_cluster:
            return
        
        now = time.time()
        
        # Проверяем, нужно ли обновление
        if not force and (now - self._last_topology_refresh) < self.topology_refresh_interval:
            return
        
        # Избегаем параллельных обновлений
        with self._topology_lock:
            if self._refresh_in_progress:
                return
            
            # Повторная проверка под локом
            if not force and (time.time() - self._last_topology_refresh) < self.topology_refresh_interval:
                return
            
            self._refresh_in_progress = True
        
        try:
            self._load_cluster_topology()
            self._last_topology_refresh = time.time()
            logger.info("Cluster topology refreshed successfully")
        except Exception as e:
            logger.error(f"Failed to refresh cluster topology: {e}")
        finally:
            with self._topology_lock:
                self._refresh_in_progress = False
    
    def _load_cluster_topology(self):
        """Обновлённая загрузка топологии с поддержкой реплик"""
        try:
            # Пробуем получить CLUSTER SLOTS от любого доступного узла
            slots_info = None
            errors = []
            
            # Сначала пробуем основное соединение
            try:
                conn = self._get_connection()
                slots_info = conn.execute_command('CLUSTER', 'SLOTS')
                self._release_connection(conn)
            except Exception as e:
                errors.append(f"main: {e}")
            
            # Если не получилось, пробуем другие узлы
            if slots_info is None:
                for node_id, pool in list(self.cluster_pools.items()):
                    try:
                        conn = pool.get_connection()
                        slots_info = conn.execute_command('CLUSTER', 'SLOTS')
                        pool.release_connection(conn)
                        break
                    except Exception as e:
                        errors.append(f"{node_id}: {e}")
            
            if slots_info is None:
                raise RedisClusterError(f"Cannot get cluster slots from any node: {errors}")
            
            new_slots: Dict[int, str] = {}
            new_nodes: set = set()
            
            for slot_range in slots_info:
                start_slot = slot_range[0]
                end_slot = slot_range[1]
                master_info = slot_range[2]
                # replicas = slot_range[3:]  # Для будущего использования
                
                if isinstance(master_info[0], bytes):
                    node_host = master_info[0].decode('utf-8')
                else:
                    node_host = master_info[0]
                node_port = master_info[1]
                node_id = f"{node_host}:{node_port}"
                new_nodes.add(node_id)
                
                # Создаём пул для нового узла
                if node_id not in self.cluster_pools:
                    try:
                        self.cluster_pools[node_id] = ConnectionPool(
                            host=node_host,
                            port=node_port,
                            password=self.password,
                            username=self.username,
                            socket_timeout=self.socket_timeout,
                            ssl=self.ssl,
                            ssl_ca_certs=self.ssl_ca_certs,
                            ssl_certfile=self.ssl_certfile,
                            ssl_keyfile=self.ssl_keyfile,
                            max_connections=getattr(self, 'max_connections', 50),
                        )
                        logger.info(f"Added cluster node: {node_id}")
                    except Exception as e:
                        logger.error(f"Failed to connect to cluster node {node_id}: {e}")
                        continue
                
                for slot in range(start_slot, end_slot + 1):
                    new_slots[slot] = node_id
            
            # Удаляем старые узлы, которых больше нет
            old_nodes = set(self.cluster_pools.keys()) - new_nodes
            for node_id in old_nodes:
                logger.info(f"Removing stale cluster node: {node_id}")
                pool = self.cluster_pools.pop(node_id, None)
                if pool:
                    pool.close_all()
            
            # Атомарно обновляем слоты
            self.cluster_slots = new_slots
            
            # Обновляем cluster_nodes для обратной совместимости
            self.cluster_nodes = {
                node_id: pool.get_connection() 
                for node_id, pool in self.cluster_pools.items()
            }
            # Сразу освобождаем
            for node_id, conn in self.cluster_nodes.items():
                self.cluster_pools[node_id].release_connection(conn)
            
            logger.info(f"Cluster topology loaded: {len(self.cluster_pools)} nodes, {len(new_slots)} slots")
            
        except Exception as e:
            logger.error(f"Failed to load cluster topology: {e}")
            raise
    
    def execute_command(self, *args, key: Optional[Union[str, bytes]] = None) -> Any:
        """Обновлённый execute_command с обновлением топологии"""
        
        # Периодическое обновление топологии
        self._maybe_refresh_topology()
        
        max_redirects = 5
        redirect_count = 0
        
        if key is None and len(args) > 1:
            key = args[1]
        
        conn = None
        pool = None
        
        try:
            # ... получение соединения (как в пункте 1) ...
            
            while redirect_count < max_redirects:
                try:
                    response = conn.execute_command(*args)
                    if self.decode_responses:
                        response = self._decode_response(response)
                    return response
                    
                except RedisError as e:
                    error_msg = str(e)
                    
                    # При MOVED обновляем топологию
                    if error_msg.startswith('MOVED'):
                        if self.topology_refresh_on_error:
                            self._maybe_refresh_topology(force=True)
                        
                        # ... существующая логика редиректа ...
                        redirect_count += 1
                        continue
                    
                    # При CLUSTERDOWN тоже обновляем
                    elif 'CLUSTERDOWN' in error_msg:
                        logger.error(f"Cluster is down: {error_msg}")
                        if self.topology_refresh_on_error:
                            self._maybe_refresh_topology(force=True)
                        raise
                    
                    elif error_msg.startswith('ASK'):
                        # ... существующая логика ASK ...
                        pass
                    
                    raise
            
            raise RedisClusterError("Too many redirects")
            
        finally:
            if pool and conn:
                pool.release_connection(conn)
    
    def refresh_topology(self):
        """Принудительное обновление топологии (публичный метод)"""
        self._maybe_refresh_topology(force=True)
```

---

### 3. Настоящий Pipeline (batch через один сокет)

**Проблема:** Текущий pipeline просто последовательно выполняет команды — это не даёт никакого ускорения.

**Решение:** Реальный pipeline отправляет все команды разом и читает все ответы.

```python
class RedisPipeline:
    """Настоящий Pipeline с batch-отправкой команд"""
    
    def __init__(self, client: 'RedisClient', transaction: bool = False):
        self.client = client
        self.transaction = transaction
        self._commands: List[Tuple[str, tuple, dict]] = []
        self._raw_commands: List[bytes] = []  # Закодированные команды
        self._executed = False
    
    def _add_command(self, *args, **kwargs):
        """Добавить команду в очередь"""
        if self._executed:
            raise RedisError("Pipeline already executed")
        
        # Сохраняем сырые аргументы для RESP
        self._raw_commands.append(RESPParser.encode_command(*args))
        # Сохраняем для отладки
        cmd_name = args[0] if args else 'UNKNOWN'
        self._commands.append((cmd_name, args, kwargs))
        return self
    
    def execute(self) -> List[Any]:
        """Выполнить все команды и вернуть результаты"""
        if self._executed:
            raise RedisError("Pipeline already executed")
        
        if not self._raw_commands:
            return []
        
        self._executed = True
        
        # В кластерном режиме группируем команды по узлам
        if self.client.is_cluster:
            return self._execute_cluster()
        else:
            return self._execute_single()
    
    def _execute_single(self) -> List[Any]:
        """Выполнить pipeline на одном узле"""
        conn = None
        pool = self.client.pool
        
        try:
            conn = self.client._get_connection()
            
            # Добавляем MULTI/EXEC для транзакции
            if self.transaction:
                all_commands = [RESPParser.encode_command('MULTI')]
                all_commands.extend(self._raw_commands)
                all_commands.append(RESPParser.encode_command('EXEC'))
            else:
                all_commands = self._raw_commands
            
            # Отправляем все команды одним пакетом
            batch = b''.join(all_commands)
            conn.sock.sendall(batch)
            
            # Читаем все ответы
            results = []
            
            if self.transaction:
                # Читаем OK от MULTI
                RESPParser.decode_response(conn.sock)
                
                # Читаем QUEUED от каждой команды
                for _ in self._raw_commands:
                    RESPParser.decode_response(conn.sock)
                
                # Читаем результат EXEC (массив результатов)
                exec_result = RESPParser.decode_response(conn.sock)
                if exec_result is None:
                    raise RedisError("Transaction aborted (WATCH condition failed)")
                results = exec_result
            else:
                for _ in self._raw_commands:
                    try:
                        response = RESPParser.decode_response(conn.sock)
                        if self.client.decode_responses:
                            response = self.client._decode_response(response)
                        results.append(response)
                    except RedisError as e:
                        results.append(e)
            
            return results
            
        finally:
            if conn:
                self.client._release_connection(conn)
    
    def _execute_cluster(self) -> List[Any]:
        """Выполнить pipeline в кластере (группировка по узлам)"""
        from collections import defaultdict
        
        # Группируем команды по узлам
        node_commands: Dict[str, List[Tuple[int, bytes]]] = defaultdict(list)
        
        for idx, (cmd_name, args, kwargs) in enumerate(self._commands):
            # Определяем ключ для роутинга
            key = kwargs.get('key')
            if key is None and len(args) > 1:
                key = args[1]
            
            if key:
                slot = self.client._get_slot(key)
                node_id = self.client.cluster_slots.get(slot, 
                    f"{self.client.host}:{self.client.port}")
            else:
                node_id = f"{self.client.host}:{self.client.port}"
            
            node_commands[node_id].append((idx, self._raw_commands[idx]))
        
        # Выполняем команды на каждом узле
        results = [None] * len(self._commands)
        
        for node_id, commands in node_commands.items():
            pool = self.client.cluster_pools.get(node_id, self.client.pool)
            conn = None
            
            try:
                if pool:
                    conn = pool.get_connection()
                else:
                    # Fallback на основное соединение
                    conn = self.client._get_connection()
                
                # Отправляем batch
                batch = b''.join(cmd for _, cmd in commands)
                conn.sock.sendall(batch)
                
                # Читаем ответы
                for original_idx, _ in commands:
                    try:
                        response = RESPParser.decode_response(conn.sock)
                        if self.client.decode_responses:
                            response = self.client._decode_response(response)
                        results[original_idx] = response
                    except RedisError as e:
                        results[original_idx] = e
            
            except Exception as e:
                # Помечаем все команды этого узла как ошибочные
                for original_idx, _ in commands:
                    results[original_idx] = RedisConnectionError(f"Node {node_id} failed: {e}")
            
            finally:
                if conn and pool:
                    pool.release_connection(conn)
        
        return results
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None and not self._executed:
            self.execute()
        return False
    
    def __len__(self):
        return len(self._commands)
    
    # Методы-обёртки для команд
    def get(self, key):
        return self._add_command('GET', key, key=key)
    
    def set(self, key, value, ex=None, px=None, nx=False, xx=False):
        args = ['SET', key, value]
        if ex is not None:
            args.extend(['EX', ex])
        if px is not None:
            args.extend(['PX', px])
        if nx:
            args.append('NX')
        if xx:
            args.append('XX')
        return self._add_command(*args, key=key)
    
    def delete(self, *keys):
        return self._add_command('DEL', *keys, key=keys[0] if keys else None)
    
    def incr(self, key):
        return self._add_command('INCR', key, key=key)
    
    def hset(self, key, field=None, value=None, mapping=None):
        args = ['HSET', key]
        if mapping:
            for k, v in mapping.items():
                args.extend([k, v])
        elif field is not None and value is not None:
            args.extend([field, value])
        return self._add_command(*args, key=key)
    
    def hget(self, key, field):
        return self._add_command('HGET', key, field, key=key)
    
    def hgetall(self, key):
        return self._add_command('HGETALL', key, key=key)
    
    def lpush(self, key, *values):
        return self._add_command('LPUSH', key, *values, key=key)
    
    def rpush(self, key, *values):
        return self._add_command('RPUSH', key, *values, key=key)
    
    def lrange(self, key, start, stop):
        return self._add_command('LRANGE', key, start, stop, key=key)
    
    def sadd(self, key, *members):
        return self._add_command('SADD', key, *members, key=key)
    
    def smembers(self, key):
        return self._add_command('SMEMBERS', key, key=key)
    
    def zadd(self, key, mapping, nx=False, xx=False, gt=False, lt=False):
        args = ['ZADD', key]
        if nx: args.append('NX')
        if xx: args.append('XX')
        if gt: args.append('GT')
        if lt: args.append('LT')
        for member, score in mapping.items():
            args.extend([score, member])
        return self._add_command(*args, key=key)
    
    def expire(self, key, seconds):
        return self._add_command('EXPIRE', key, seconds, key=key)
    
    def ttl(self, key):
        return self._add_command('TTL', key, key=key)
    
    def exists(self, *keys):
        return self._add_command('EXISTS', *keys, key=keys[0] if keys else None)
    
    # Генерик для любой команды
    def execute_command(self, *args, key=None):
        return self._add_command(*args, key=key)


# Обновляем метод pipeline в RedisClient
class RedisClient:
    # ... существующий код ...
    
    def pipeline(self, transaction: bool = False) -> RedisPipeline:
        """
        Создать pipeline для batch-операций.
        
        Args:
            transaction: Если True, команды выполняются в MULTI/EXEC блоке
        
        Example:
            pipe = client.pipeline()
            pipe.set('key1', 'value1')
            pipe.get('key1')
            pipe.incr('counter')
            results = pipe.execute()  # [True, b'value1', 1]
            
            # Или через контекстный менеджер:
            with client.pipeline() as pipe:
                pipe.set('key1', 'value1')
                pipe.get('key1')
            # execute() вызывается автоматически
        """
        return RedisPipeline(self, transaction=transaction)
```

---

## Пример использования всех улучшений

```python
# Создание клиента с пулом соединений
client = RedisClient(
    host='redis-cluster.example.com',
    port=6379,
    password='secret',
    is_cluster=True,
    use_pool=True,
    max_connections=100,
    topology_refresh_interval=30,
    decode_responses=True
)

# Проверка статистики пула
print(client.pool_stats())
# {'main': {'total_created': 5, 'idle': 4, 'in_use': 1, 'max_connections': 100}}

# Принудительное обновление топологии
client.refresh_topology()

# Использование настоящего pipeline
pipe = client.pipeline()
for i in range(1000):
    pipe.set(f'key:{i}', f'value:{i}')
    pipe.expire(f'key:{i}', 3600)
results = pipe.execute()  # Всё за один round-trip на каждый узел!

# Pipeline с транзакцией
with client.pipeline(transaction=True) as pipe:
    pipe.incr('counter')
    pipe.get('counter')
# Атомарно выполнится как MULTI/INCR/GET/EXEC

# Закрытие с освобождением всех ресурсов
client.close()
```

---

## Дополнительные рекомендации (следующий приоритет)

| # | Улучшение | Сложность | Важность |
|---|-----------|-----------|----------|
| 4 | Поддержка реплик (READONLY + read_from_replicas) | Средняя | Высокая |
| 5 | Multi-key команды с группировкой по слотам (MGET, MSET, DEL) | Средняя | Высокая |
| 6 | Pub/Sub (SUBSCRIBE, PSUBSCRIBE, PUBLISH) | Средняя | Средняя |
| 7 | Lua scripts (EVAL, EVALSHA с проверкой слотов) | Низкая | Средняя |
| 8 | WATCH/UNWATCH для оптимистичных транзакций | Низкая | Низкая |
