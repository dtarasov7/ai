# Да, однозначно стоит добавить auto-reconnect

Это **критически важная** функциональность для production-систем. Без неё любой сетевой сбой, перезапуск Redis, failover в кластере — и клиент "умирает" навсегда.

## Что нужно реализовать

1. **Автоматический reconnect** при потере соединения
2. **Экспоненциальный backoff** (чтобы не DDoS'ить сервер при проблемах)
3. **Retry логика** для команд с настраиваемым количеством попыток
4. **Health check** соединений в пуле
5. **Callbacks** для мониторинга (on_connect, on_disconnect, on_reconnect)

---

## Полная реализация

### 1. Добавляем новые исключения и конфигурацию

```python
import time
import random
from dataclasses import dataclass
from typing import Callable


class RedisRetryError(RedisError):
    """Ошибка после исчерпания попыток retry"""
    pass


@dataclass
class RetryConfig:
    """Конфигурация retry/reconnect логики"""
    max_retries: int = 3                    # Максимум попыток выполнить команду
    retry_on_timeout: bool = True           # Retry при timeout
    retry_on_connection_error: bool = True  # Retry при ошибке соединения
    
    # Exponential backoff
    base_delay: float = 0.1                 # Начальная задержка (секунды)
    max_delay: float = 10.0                 # Максимальная задержка
    exponential_base: float = 2.0           # База экспоненты
    jitter: bool = True                     # Добавлять случайный jitter
    
    # Reconnect
    reconnect_on_error: bool = True         # Переподключаться при ошибке
    max_reconnect_attempts: int = 10        # Максимум попыток reconnect
    
    def get_delay(self, attempt: int) -> float:
        """Вычислить задержку с exponential backoff"""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        if self.jitter:
            # Добавляем случайный jitter ±25%
            delay = delay * (0.75 + random.random() * 0.5)
        return delay
```

### 2. Обновляем RedisConnection с поддержкой reconnect

```python
class RedisConnection:
    """Подключение к одному Redis узлу с поддержкой reconnect"""

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 ssl_check_hostname: bool = True,
                 # Новые параметры
                 retry_config: Optional[RetryConfig] = None,
                 on_connect: Optional[Callable[['RedisConnection'], None]] = None,
                 on_disconnect: Optional[Callable[['RedisConnection', Exception], None]] = None):

        self.host = host
        self.port = port
        self.password = password
        self.username = username
        self.db = db
        self.socket_timeout = socket_timeout
        self.ssl = ssl
        self.ssl_ca_certs = ssl_ca_certs
        self.ssl_certfile = ssl_certfile
        self.ssl_keyfile = ssl_keyfile
        self.ssl_check_hostname = ssl_check_hostname
        
        # Retry/reconnect конфигурация
        self.retry_config = retry_config or RetryConfig()
        
        # Callbacks
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        
        # Состояние
        self.sock: Optional[socket.socket] = None
        self._is_connected = False
        self._reconnect_attempt = 0
        self._last_error: Optional[Exception] = None
        self._created_at: float = time.time()
        self._last_used_at: float = time.time()
        
        self._connect()

    def _connect(self):
        """Установить соединение с Redis"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.socket_timeout)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Keep-alive для обнаружения мёртвых соединений
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            sock.connect((self.host, self.port))

            if self.ssl:
                context = ssl_module.create_default_context()
                if self.ssl_ca_certs:
                    context.load_verify_locations(cafile=self.ssl_ca_certs)
                if self.ssl_certfile and self.ssl_keyfile:
                    context.load_cert_chain(certfile=self.ssl_certfile, keyfile=self.ssl_keyfile)
                if not self.ssl_check_hostname:
                    context.check_hostname = False
                    context.verify_mode = ssl_module.CERT_NONE
                sock = context.wrap_socket(sock, server_hostname=self.host)

            self.sock = sock
            self._is_connected = True
            self._reconnect_attempt = 0
            self._last_error = None

            # Аутентификация
            if self.password:
                if self.username:
                    self._execute_raw('AUTH', self.username, self.password)
                else:
                    self._execute_raw('AUTH', self.password)

            # Выбор базы данных
            if self.db != 0:
                self._execute_raw('SELECT', self.db)

            logger.info(f"Connected to {self.host}:{self.port} (db={self.db})")
            
            # Callback
            if self.on_connect:
                try:
                    self.on_connect(self)
                except Exception as e:
                    logger.warning(f"on_connect callback failed: {e}")
                    
        except Exception as e:
            self._is_connected = False
            self._last_error = e
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
            raise RedisConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")

    def _execute_raw(self, *args) -> Any:
        """Выполнить команду БЕЗ retry (для внутреннего использования)"""
        if not self.sock:
            raise RedisConnectionError("Not connected")
        command = RESPParser.encode_command(*args)
        self.sock.sendall(command)
        return RESPParser.decode_response(self.sock)

    def reconnect(self) -> bool:
        """
        Переподключиться к Redis.
        Возвращает True если успешно, иначе выбрасывает исключение.
        """
        self.close()
        
        last_error = None
        
        for attempt in range(self.retry_config.max_reconnect_attempts):
            self._reconnect_attempt = attempt + 1
            
            try:
                logger.info(f"Reconnecting to {self.host}:{self.port} "
                           f"(attempt {self._reconnect_attempt}/{self.retry_config.max_reconnect_attempts})")
                self._connect()
                logger.info(f"Reconnected to {self.host}:{self.port} successfully")
                return True
                
            except RedisConnectionError as e:
                last_error = e
                delay = self.retry_config.get_delay(attempt)
                logger.warning(f"Reconnect attempt {self._reconnect_attempt} failed: {e}. "
                              f"Retrying in {delay:.2f}s...")
                time.sleep(delay)
        
        raise RedisConnectionError(
            f"Failed to reconnect after {self.retry_config.max_reconnect_attempts} attempts. "
            f"Last error: {last_error}"
        )

    def execute_command(self, *args) -> Any:
        """Выполнить команду с автоматическим retry и reconnect"""
        last_error = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Проверяем соединение
                if not self._is_connected or not self.sock:
                    if self.retry_config.reconnect_on_error:
                        self.reconnect()
                    else:
                        raise RedisConnectionError("Not connected")
                
                # Выполняем команду
                self._last_used_at = time.time()
                return self._execute_raw(*args)
                
            except socket.timeout as e:
                last_error = e
                self._handle_connection_error(e)
                
                if not self.retry_config.retry_on_timeout:
                    raise RedisConnectionError(f"Command timeout: {e}")
                    
                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    logger.warning(f"Command timeout, retry {attempt + 1}/{self.retry_config.max_retries} "
                                  f"in {delay:.2f}s...")
                    time.sleep(delay)
                    
            except (socket.error, OSError, BrokenPipeError, ConnectionResetError) as e:
                last_error = e
                self._handle_connection_error(e)
                
                if not self.retry_config.retry_on_connection_error:
                    raise RedisConnectionError(f"Connection error: {e}")
                    
                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    logger.warning(f"Connection error: {e}. Retry {attempt + 1}/{self.retry_config.max_retries} "
                                  f"in {delay:.2f}s...")
                    time.sleep(delay)
                    
            except RedisError:
                # Redis ошибки (WRONGTYPE, MOVED и т.д.) — не retry
                raise
                
            except Exception as e:
                last_error = e
                self._handle_connection_error(e)
                
                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    logger.warning(f"Unexpected error: {e}. Retry {attempt + 1}/{self.retry_config.max_retries} "
                                  f"in {delay:.2f}s...")
                    time.sleep(delay)
        
        raise RedisRetryError(
            f"Command failed after {self.retry_config.max_retries + 1} attempts. "
            f"Last error: {last_error}"
        )

    def _handle_connection_error(self, error: Exception):
        """Обработать ошибку соединения"""
        self._is_connected = False
        self._last_error = error
        
        # Callback
        if self.on_disconnect:
            try:
                self.on_disconnect(self, error)
            except Exception as e:
                logger.warning(f"on_disconnect callback failed: {e}")
        
        # Закрываем сокет
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def close(self):
        """Закрыть соединение"""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
        self._is_connected = False

    def ping(self) -> bool:
        """Проверить соединение"""
        try:
            return self._execute_raw('PING') == 'PONG'
        except:
            return False

    def is_connected(self) -> bool:
        """Проверить статус соединения"""
        return self._is_connected and self.sock is not None

    @property
    def connection_info(self) -> Dict[str, Any]:
        """Информация о соединении"""
        return {
            'host': self.host,
            'port': self.port,
            'db': self.db,
            'is_connected': self._is_connected,
            'reconnect_attempts': self._reconnect_attempt,
            'last_error': str(self._last_error) if self._last_error else None,
            'created_at': self._created_at,
            'last_used_at': self._last_used_at,
            'idle_time': time.time() - self._last_used_at,
        }
```

### 3. Обновляем ConnectionPool с health check

```python
class ConnectionPool:
    """Пул соединений с health check и auto-reconnect"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 ssl_check_hostname: bool = True,
                 max_connections: int = 50,
                 min_idle: int = 5,
                 max_idle_time: int = 300,
                 # Новые параметры
                 retry_config: Optional[RetryConfig] = None,
                 health_check_interval: int = 30,
                 on_connect: Optional[Callable] = None,
                 on_disconnect: Optional[Callable] = None):
        
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
            'retry_config': retry_config or RetryConfig(),
            'on_connect': on_connect,
            'on_disconnect': on_disconnect,
        }
        
        self.max_connections = max_connections
        self.min_idle = min_idle
        self.max_idle_time = max_idle_time
        self.health_check_interval = health_check_interval
        
        self._pool: deque = deque()
        self._in_use: Dict[int, RedisConnection] = {}
        self._lock = threading.RLock()
        self._created_count = 0
        self._total_connections_created = 0
        self._failed_connections = 0
        
        self._warm_up()
    
    def _warm_up(self):
        """Создать минимальное количество соединений"""
        for _ in range(self.min_idle):
            try:
                conn = self._create_connection()
                self._pool.append((conn, time.time()))
            except Exception as e:
                logger.warning(f"Failed to create warm-up connection: {e}")
                self._failed_connections += 1
                break
    
    def _create_connection(self) -> RedisConnection:
        """Создать новое соединение"""
        with self._lock:
            if self._created_count >= self.max_connections:
                raise RedisConnectionError(
                    f"Connection pool exhausted (max={self.max_connections}, "
                    f"in_use={len(self._in_use)})"
                )
            
        conn = RedisConnection(**self.connection_kwargs)
        
        with self._lock:
            self._created_count += 1
            self._total_connections_created += 1
            
        logger.debug(f"Created new connection (total: {self._created_count})")
        return conn
    
    def get_connection(self) -> RedisConnection:
        """Получить соединение из пула с health check"""
        deadline = time.time() + self.connection_kwargs.get('socket_timeout', 5)
        
        while time.time() < deadline:
            with self._lock:
                # Пытаемся взять из пула
                while self._pool:
                    conn, last_used = self._pool.popleft()
                    
                    # Проверяем, не устарело ли соединение
                    idle_time = time.time() - last_used
                    if idle_time > self.max_idle_time:
                        logger.debug(f"Connection idle for {idle_time:.1f}s, closing")
                        self._close_connection(conn)
                        continue
                    
                    # Health check для давно неиспользованных соединений
                    if idle_time > self.health_check_interval:
                        if not self._health_check(conn):
                            self._close_connection(conn)
                            continue
                    
                    # Соединение валидно
                    self._in_use[id(conn)] = conn
                    return conn
            
            # Пул пуст — пробуем создать новое соединение
            try:
                conn = self._create_connection()
                with self._lock:
                    self._in_use[id(conn)] = conn
                return conn
            except RedisConnectionError as e:
                if "pool exhausted" in str(e).lower():
                    # Ждём освобождения соединения
                    time.sleep(0.1)
                    continue
                raise
        
        raise RedisConnectionError("Timeout waiting for connection from pool")
    
    def _health_check(self, conn: RedisConnection) -> bool:
        """Проверить здоровье соединения"""
        try:
            return conn.ping()
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False
    
    def release_connection(self, conn: RedisConnection, discard: bool = False):
        """Вернуть соединение в пул"""
        with self._lock:
            conn_id = id(conn)
            
            if conn_id not in self._in_use:
                # Соединение не из этого пула
                logger.warning("Attempted to release unknown connection")
                return
            
            del self._in_use[conn_id]
            
            # Если соединение битое или нужно отбросить
            if discard or not conn.is_connected():
                self._close_connection(conn)
                return
            
            # Возвращаем в пул
            if len(self._pool) < self.max_connections:
                self._pool.append((conn, time.time()))
            else:
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
        discard = False
        try:
            yield conn
        except (socket.error, OSError, BrokenPipeError, ConnectionResetError):
            discard = True
            raise
        finally:
            self.release_connection(conn, discard=discard)
    
    def close_all(self):
        """Закрыть все соединения"""
        with self._lock:
            while self._pool:
                conn, _ = self._pool.popleft()
                try:
                    conn.close()
                except:
                    pass
            
            for conn in self._in_use.values():
                try:
                    conn.close()
                except:
                    pass
            
            self._in_use.clear()
            self._created_count = 0
    
    def reconnect_all(self):
        """Переподключить все соединения (при failover)"""
        with self._lock:
            # Закрываем все idle соединения
            while self._pool:
                conn, _ = self._pool.popleft()
                try:
                    conn.close()
                except:
                    pass
                self._created_count = max(0, self._created_count - 1)
        
        # Прогреваем заново
        self._warm_up()
        logger.info(f"Pool reconnected with {len(self._pool)} connections")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Статистика пула"""
        with self._lock:
            return {
                'host': self.connection_kwargs['host'],
                'port': self.connection_kwargs['port'],
                'max_connections': self.max_connections,
                'created': self._created_count,
                'idle': len(self._pool),
                'in_use': len(self._in_use),
                'available': self.max_connections - len(self._in_use),
                'total_created': self._total_connections_created,
                'failed': self._failed_connections,
            }
```

### 4. Обновляем RedisClient

```python
class RedisClient:
    """Redis клиент с полной поддержкой Cluster и auto-reconnect"""

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 decode_responses: bool = False, is_cluster: bool = False,
                 # Pool параметры
                 use_pool: bool = True,
                 max_connections: int = 50,
                 min_idle_connections: int = 5,
                 # Retry параметры
                 max_retries: int = 3,
                 retry_on_timeout: bool = True,
                 retry_on_connection_error: bool = True,
                 retry_base_delay: float = 0.1,
                 retry_max_delay: float = 10.0,
                 # Cluster параметры
                 topology_refresh_interval: int = 30,
                 topology_refresh_on_error: bool = True,
                 # Callbacks
                 on_connect: Optional[Callable] = None,
                 on_disconnect: Optional[Callable] = None,
                 on_reconnect: Optional[Callable] = None):

        self.host = host
        self.port = port
        self.password = password
        self.username = username
        self.db = db
        self.socket_timeout = socket_timeout
        self.ssl = ssl
        self.ssl_ca_certs = ssl_ca_certs
        self.ssl_certfile = ssl_certfile
        self.ssl_keyfile = ssl_keyfile
        self.decode_responses = decode_responses
        self.is_cluster = is_cluster
        self.use_pool = use_pool
        self.max_connections = max_connections
        
        # Retry конфигурация
        self.retry_config = RetryConfig(
            max_retries=max_retries,
            retry_on_timeout=retry_on_timeout,
            retry_on_connection_error=retry_on_connection_error,
            base_delay=retry_base_delay,
            max_delay=retry_max_delay,
        )
        
        # Cluster
        self.topology_refresh_interval = topology_refresh_interval
        self.topology_refresh_on_error = topology_refresh_on_error
        self._last_topology_refresh: float = 0
        self._topology_lock = threading.Lock()
        
        # Callbacks
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_reconnect = on_reconnect
        
        # Состояние
        self.pool: Optional[ConnectionPool] = None
        self.cluster_pools: Dict[str, ConnectionPool] = {}
        self.cluster_slots: Dict[int, str] = {}
        self.connection: Optional[RedisConnection] = None
        
        # Для обратной совместимости
        self.cluster_nodes: Dict[str, RedisConnection] = {}
        
        self._init_connection()

    def _create_pool(self, host: str, port: int) -> ConnectionPool:
        """Создать пул соединений для узла"""
        return ConnectionPool(
            host=host,
            port=port,
            password=self.password,
            username=self.username,
            db=self.db if not self.is_cluster else 0,
            socket_timeout=self.socket_timeout,
            ssl=self.ssl,
            ssl_ca_certs=self.ssl_ca_certs,
            ssl_certfile=self.ssl_certfile,
            ssl_keyfile=self.ssl_keyfile,
            max_connections=self.max_connections,
            retry_config=self.retry_config,
            on_connect=self._on_node_connect,
            on_disconnect=self._on_node_disconnect,
        )
    
    def _on_node_connect(self, conn: RedisConnection):
        """Callback при подключении к узлу"""
        if self.on_connect:
            try:
                self.on_connect(conn)
            except:
                pass
    
    def _on_node_disconnect(self, conn: RedisConnection, error: Exception):
        """Callback при отключении от узла"""
        if self.on_disconnect:
            try:
                self.on_disconnect(conn, error)
            except:
                pass

    def _init_connection(self):
        """Инициализация соединений"""
        if self.use_pool:
            self.pool = self._create_pool(self.host, self.port)
        else:
            self.connection = RedisConnection(
                host=self.host,
                port=self.port,
                password=self.password,
                username=self.username,
                db=self.db,
                socket_timeout=self.socket_timeout,
                ssl=self.ssl,
                retry_config=self.retry_config,
            )
        
        if self.is_cluster:
            self._load_cluster_topology()
            self._last_topology_refresh = time.time()

    def _get_connection(self, node_id: Optional[str] = None) -> Tuple[RedisConnection, ConnectionPool]:
        """Получить соединение (и пул для возврата)"""
        if node_id and node_id in self.cluster_pools:
            pool = self.cluster_pools[node_id]
            return pool.get_connection(), pool
        
        if self.use_pool and self.pool:
            return self.pool.get_connection(), self.pool
        
        return self.connection, None

    def _release_connection(self, conn: RedisConnection, pool: Optional[ConnectionPool], 
                           discard: bool = False):
        """Вернуть соединение"""
        if pool:
            pool.release_connection(conn, discard=discard)

    def execute_command(self, *args, key: Optional[Union[str, bytes]] = None) -> Any:
        """Выполнить команду с полной поддержкой retry и reconnect"""
        
        # Периодическое обновление топологии кластера
        if self.is_cluster:
            self._maybe_refresh_topology()
        
        max_redirects = 5
        redirect_count = 0
        
        # Определяем ключ для роутинга
        if key is None and len(args) > 1:
            key = args[1]
        
        # Определяем узел
        node_id = None
        if self.is_cluster and key:
            slot = self._get_slot(key)
            node_id = self.cluster_slots.get(slot)
        
        last_error = None
        
        while redirect_count < max_redirects:
            conn = None
            pool = None
            discard_connection = False
            
            try:
                conn, pool = self._get_connection(node_id)
                
                # Команда выполняется с retry внутри RedisConnection
                response = conn.execute_command(*args)
                
                if self.decode_responses:
                    response = self._decode_response(response)
                return response
                
            except RedisError as e:
                error_msg = str(e)
                last_error = e
                
                # MOVED редирект
                if error_msg.startswith('MOVED'):
                    parts = error_msg.split()
                    if len(parts) >= 3:
                        slot = int(parts[1])
                        node_addr = parts[2]
                        host, port = node_addr.split(':')
                        node_id = f"{host}:{int(port)}"
                        
                        # Создаём пул для нового узла
                        if node_id not in self.cluster_pools:
                            try:
                                self.cluster_pools[node_id] = self._create_pool(host, int(port))
                                logger.info(f"Added new cluster node: {node_id}")
                            except Exception as pool_error:
                                logger.error(f"Failed to create pool for {node_id}: {pool_error}")
                                raise
                        
                        self.cluster_slots[slot] = node_id
                        redirect_count += 1
                        
                        # Обновляем топологию в фоне
                        if self.topology_refresh_on_error:
                            self._maybe_refresh_topology(force=True)
                        
                        continue
                
                # ASK редирект
                elif error_msg.startswith('ASK'):
                    parts = error_msg.split()
                    if len(parts) >= 3:
                        node_addr = parts[2]
                        host, port = node_addr.split(':')
                        temp_node_id = f"{host}:{int(port)}"
                        
                        # Получаем или создаём соединение
                        if temp_node_id not in self.cluster_pools:
                            self.cluster_pools[temp_node_id] = self._create_pool(host, int(port))
                        
                        temp_conn, temp_pool = self._get_connection(temp_node_id)
                        try:
                            temp_conn.execute_command('ASKING')
                            response = temp_conn.execute_command(*args)
                            if self.decode_responses:
                                response = self._decode_response(response)
                            return response
                        finally:
                            self._release_connection(temp_conn, temp_pool)
                
                # CLUSTERDOWN — обновляем топологию
                elif 'CLUSTERDOWN' in error_msg:
                    logger.error(f"Cluster is down: {error_msg}")
                    discard_connection = True
                    if self.topology_refresh_on_error:
                        time.sleep(1)  # Даём кластеру восстановиться
                        self._maybe_refresh_topology(force=True)
                    raise
                
                raise
            
            except (socket.error, OSError, BrokenPipeError, 
                    ConnectionResetError, RedisConnectionError) as e:
                last_error = e
                discard_connection = True
                logger.warning(f"Connection error: {e}")
                
                # Пробуем обновить топологию
                if self.is_cluster and self.topology_refresh_on_error:
                    try:
                        self._maybe_refresh_topology(force=True)
                    except:
                        pass
                
                raise RedisConnectionError(f"Connection failed: {e}")
            
            finally:
                if conn and pool:
                    self._release_connection(conn, pool, discard=discard_connection)
        
        raise RedisClusterError(f"Too many redirects ({max_redirects}). Last error: {last_error}")

    def _maybe_refresh_topology(self, force: bool = False):
        """Обновить топологию кластера если нужно"""
        if not self.is_cluster:
            return
        
        now = time.time()
        
        if not force and (now - self._last_topology_refresh) < self.topology_refresh_interval:
            return
        
        with self._topology_lock:
            # Повторная проверка под локом
            if not force and (time.time() - self._last_topology_refresh) < self.topology_refresh_interval:
                return
            
            try:
                self._load_cluster_topology()
                self._last_topology_refresh = time.time()
                
                if self.on_reconnect:
                    try:
                        self.on_reconnect()
                    except:
                        pass
                        
            except Exception as e:
                logger.error(f"Failed to refresh cluster topology: {e}")

    def _load_cluster_topology(self):
        """Загрузить топологию кластера"""
        slots_info = None
        errors = []
        
        # Пробуем получить от любого доступного узла
        pools_to_try = [self.pool] + list(self.cluster_pools.values())
        
        for pool in pools_to_try:
            if pool is None:
                continue
            try:
                conn = pool.get_connection()
                try:
                    slots_info = conn.execute_command('CLUSTER', 'SLOTS')
                    break
                finally:
                    pool.release_connection(conn)
            except Exception as e:
                errors.append(str(e))
        
        if slots_info is None:
            raise RedisClusterError(f"Cannot get cluster slots: {errors}")
        
        new_slots: Dict[int, str] = {}
        new_nodes: set = set()
        
        for slot_range in slots_info:
            start_slot = slot_range[0]
            end_slot = slot_range[1]
            master_info = slot_range[2]
            
            node_host = master_info[0]
            if isinstance(node_host, bytes):
                node_host = node_host.decode('utf-8')
            node_port = master_info[1]
            node_id = f"{node_host}:{node_port}"
            new_nodes.add(node_id)
            
            if node_id not in self.cluster_pools:
                try:
                    self.cluster_pools[node_id] = self._create_pool(node_host, node_port)
                except Exception as e:
                    logger.error(f"Failed to create pool for {node_id}: {e}")
                    continue
            
            for slot in range(start_slot, end_slot + 1):
                new_slots[slot] = node_id
        
        # Удаляем старые узлы
        for node_id in list(self.cluster_pools.keys()):
            if node_id not in new_nodes:
                pool = self.cluster_pools.pop(node_id)
                pool.close_all()
                logger.info(f"Removed stale node: {node_id}")
        
        self.cluster_slots = new_slots
        logger.info(f"Cluster topology: {len(self.cluster_pools)} nodes, {len(new_slots)} slots")

    def reconnect(self):
        """Принудительно переподключить все соединения"""
        logger.info("Forcing reconnection...")
        
        if self.pool:
            self.pool.reconnect_all()
        
        for node_id, pool in self.cluster_pools.items():
            try:
                pool.reconnect_all()
            except Exception as e:
                logger.error(f"Failed to reconnect {node_id}: {e}")
        
        if self.is_cluster:
            self._maybe_refresh_topology(force=True)
        
        if self.on_reconnect:
            try:
                self.on_reconnect()
            except:
                pass

    def health_check(self) -> Dict[str, Any]:
        """Проверить здоровье всех соединений"""
        result = {
            'healthy': True,
            'nodes': {},
            'pool_stats': self.pool_stats() if hasattr(self, 'pool_stats') else {},
        }
        
        # Проверяем основной пул
        try:
            if self.ping():
                result['nodes']['main'] = {'status': 'ok'}
            else:
                result['nodes']['main'] = {'status': 'ping_failed'}
                result['healthy'] = False
        except Exception as e:
            result['nodes']['main'] = {'status': 'error', 'error': str(e)}
            result['healthy'] = False
        
        # Проверяем узлы кластера
        for node_id, pool in self.cluster_pools.items():
            try:
                conn = pool.get_connection()
                try:
                    if conn.ping():
                        result['nodes'][node_id] = {'status': 'ok'}
                    else:
                        result['nodes'][node_id] = {'status': 'ping_failed'}
                        result['healthy'] = False
                finally:
                    pool.release_connection(conn)
            except Exception as e:
                result['nodes'][node_id] = {'status': 'error', 'error': str(e)}
                result['healthy'] = False
        
        return result

    def pool_stats(self) -> Dict[str, Any]:
        """Статистика всех пулов"""
        stats = {}
        if self.pool:
            stats['main'] = self.pool.stats
        for node_id, pool in self.cluster_pools.items():
            stats[node_id] = pool.stats
        return stats

    def close(self):
        """Закрыть все соединения"""
        if self.pool:
            self.pool.close_all()
        for pool in self.cluster_pools.values():
            pool.close_all()
        self.cluster_pools.clear()
        if self.connection:
            self.connection.close()
```

---

## Пример использования

```python
import logging
logging.basicConfig(level=logging.INFO)

# Callbacks для мониторинга
def on_connect(conn):
    print(f"✅ Connected to {conn.host}:{conn.port}")

def on_disconnect(conn, error):
    print(f"❌ Disconnected from {conn.host}:{conn.port}: {error}")

def on_reconnect():
    print("🔄 Cluster topology refreshed")

# Создание клиента
client = RedisClient(
    host='redis.example.com',
    port=6379,
    password='secret',
    is_cluster=True,
    
    # Retry настройки
    max_retries=3,
    retry_on_timeout=True,
    retry_on_connection_error=True,
    retry_base_delay=0.1,
    retry_max_delay=10.0,
    
    # Pool настройки
    use_pool=True,
    max_connections=50,
    
    # Cluster настройки
    topology_refresh_interval=30,
    topology_refresh_on_error=True,
    
    # Callbacks
    on_connect=on_connect,
    on_disconnect=on_disconnect,
    on_reconnect=on_reconnect,
)

# Использование — retry происходит автоматически
try:
    client.set('key', 'value')
    value = client.get('key')
except RedisRetryError as e:
    print(f"Failed after all retries: {e}")
except RedisConnectionError as e:
    print(f"Connection failed: {e}")

# Health check
health = client.health_check()
print(f"Cluster healthy: {health['healthy']}")

# Статистика пулов
stats = client.pool_stats()
for node, node_stats in stats.items():
    print(f"{node}: {node_stats}")

# Принудительный reconnect (например, после failover)
client.reconnect()

# Закрытие
client.close()
```

---

## Что даёт эта реализация

| Функция | Описание |
|---------|----------|
| **Auto-retry** | Автоматические повторные попытки при timeout и connection errors |
| **Exponential backoff** | Умная задержка между попытками (0.1s → 0.2s → 0.4s → ... → max 10s) |
| **Jitter** | Случайный разброс задержек (защита от thundering herd) |
| **Auto-reconnect** | Автоматическое переподключение при потере соединения |
| **Health check** | Проверка соединений в пуле перед использованием |
| **Connection pooling** | Переиспользование соединений с правильным lifecycle |
| **Cluster failover** | Автоматическое обновление топологии при MOVED/CLUSTERDOWN |
| **Callbacks** | Хуки для мониторинга (Prometheus, логи, alerting) |
| **Graceful degradation** | Клиент продолжает работать при частичных сбоях |
