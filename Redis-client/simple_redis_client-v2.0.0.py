"""
Simple Redis Client - Production Ready v2.0.0

Новые возможности:
- Auto-reconnect с экспоненциальным backoff
- Connection Pool
- Buffered I/O для RESP
- Настоящий Pipeline (batch через один сокет)
- Multi-key команды с группировкой по слотам
- Автообновление топологии кластера
- Поддержка Replica / Read-Only
- Sentinel support
- SSL без проверки сертификата
- Health checks
- Callbacks для мониторинга
"""

__version__ = "2.0.0"
__author__ = "Dmitry Tarasov"

__all__ = [
    'RedisClient',
    'RedisConnection', 
    'RedisPipeline',
    'RedisError',
    'RedisConnectionError',
    'RedisClusterError',
    'ClusterNode',
    'ConnectionPool'
]

import socket
import ssl as ssl_module
import time
import random
import logging
from typing import Optional, List, Dict, Any, Tuple, Union, Iterator, Callable
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)


# ============ Exceptions ============

class RedisError(Exception):
    """Базовая ошибка Redis"""
    pass


class RedisConnectionError(RedisError):
    """Ошибка подключения"""
    pass


class RedisClusterError(RedisError):
    """Ошибка кластера"""
    pass


# ============ Buffered Socket ============

class BufferedSocket:
    """Буферизованное чтение из сокета для ускорения I/O"""

    def __init__(self, sock: socket.socket, buffer_size: int = 8192):
        self._sock = sock
        self._buffer = b''
        self._buffer_size = buffer_size

    def recv(self, n: int) -> bytes:
        """Прочитать ровно n байт из буфера"""
        while len(self._buffer) < n:
            chunk = self._sock.recv(self._buffer_size)
            if not chunk:
                raise RedisConnectionError("Connection closed")
            self._buffer += chunk

        result = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return result

    def recv_line(self) -> bytes:
        """Прочитать строку до \r\n"""
        while b'\r\n' not in self._buffer:
            chunk = self._sock.recv(self._buffer_size)
            if not chunk:
                raise RedisConnectionError("Connection closed")
            self._buffer += chunk

        idx = self._buffer.index(b'\r\n')
        line = self._buffer[:idx]
        self._buffer = self._buffer[idx + 2:]
        return line

    def sendall(self, data: bytes):
        """Отправить данные"""
        return self._sock.sendall(data)

    def close(self):
        """Закрыть сокет"""
        try:
            self._sock.close()
        except:
            pass


# ============ RESP Parser ============

class RESPParser:
    """Парсер RESP протокола с буферизацией"""

    @staticmethod
    def encode_command(*args) -> bytes:
        """Кодирование команды в RESP формат"""
        parts = [f'*{len(args)}\r\n'.encode()]
        for arg in args:
            if isinstance(arg, bytes):
                data = arg
            elif isinstance(arg, str):
                data = arg.encode('utf-8')
            elif isinstance(arg, (int, float)):
                data = str(arg).encode('utf-8')
            else:
                data = str(arg).encode('utf-8')

            parts.append(f'${len(data)}\r\n'.encode())
            parts.append(data)
            parts.append(b'\r\n')

        return b''.join(parts)

    @staticmethod
    def encode_commands(commands: List[Tuple]) -> bytes:
        """Кодирование нескольких команд в один буфер (для pipeline)"""
        return b''.join(RESPParser.encode_command(*cmd) for cmd in commands)

    @staticmethod
    def decode_response(sock: BufferedSocket) -> Any:
        """Декодирование ответа RESP"""
        line = sock.recv_line()
        if not line:
            raise RedisConnectionError("Connection closed")

        prefix = chr(line[0])
        data = line[1:]

        if prefix == '+':
            return data.decode('utf-8', errors='replace')
        elif prefix == '-':
            error_msg = data.decode('utf-8', errors='replace')
            raise RedisError(error_msg)
        elif prefix == ':':
            return int(data)
        elif prefix == '$':
            length = int(data)
            if length == -1:
                return None
            bulk_data = sock.recv(length)
            sock.recv(2)  # \r\n
            return bulk_data
        elif prefix == '*':
            count = int(data)
            if count == -1:
                return None
            return [RESPParser.decode_response(sock) for _ in range(count)]
        else:
            raise RedisError(f"Unknown RESP prefix: {prefix}")


# ============ Connection ============

class RedisConnection:
    """Подключение к одному Redis узлу с auto-reconnect"""

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 ssl_check_hostname: bool = True, ssl_verify: bool = True,
                 max_reconnect_attempts: int = 3, reconnect_backoff_base: float = 0.1,
                 reconnect_backoff_max: float = 5.0,
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
        self.ssl_check_hostname = ssl_check_hostname
        self.ssl_verify = ssl_verify

        # Reconnect параметры
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_backoff_base = reconnect_backoff_base
        self.reconnect_backoff_max = reconnect_backoff_max

        # Callbacks
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_reconnect = on_reconnect

        self.sock: Optional[BufferedSocket] = None
        self._is_connected = False
        self._connect()

    def _connect(self):
        """Установка соединения"""
        try:
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_sock.settimeout(self.socket_timeout)
            raw_sock.connect((self.host, self.port))

            if self.ssl:
                context = ssl_module.create_default_context()

                if self.ssl_ca_certs:
                    context.load_verify_locations(cafile=self.ssl_ca_certs)

                if self.ssl_certfile and self.ssl_keyfile:
                    context.load_cert_chain(certfile=self.ssl_certfile, keyfile=self.ssl_keyfile)

                if not self.ssl_verify:
                    context.check_hostname = False
                    context.verify_mode = ssl_module.CERT_NONE
                elif not self.ssl_check_hostname:
                    context.check_hostname = False

                raw_sock = context.wrap_socket(raw_sock, server_hostname=self.host)

            self.sock = BufferedSocket(raw_sock)

            # Аутентификация
            if self.password:
                if self.username:
                    self._execute_command_internal('AUTH', self.username, self.password)
                else:
                    self._execute_command_internal('AUTH', self.password)

            # Выбор БД
            if self.db != 0:
                self._execute_command_internal('SELECT', self.db)

            self._is_connected = True
            logger.info(f"Connected to {self.host}:{self.port} (db={self.db})")

            if self.on_connect:
                self.on_connect(self)

        except Exception as e:
            if self.sock:
                self.sock.close()
                self.sock = None
            self._is_connected = False
            raise RedisConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")

    def _reconnect(self) -> bool:
        """Попытка переподключения с экспоненциальным backoff"""
        for attempt in range(self.max_reconnect_attempts):
            try:
                backoff = min(
                    self.reconnect_backoff_base * (2 ** attempt),
                    self.reconnect_backoff_max
                )

                if attempt > 0:
                    logger.info(f"Reconnect attempt {attempt + 1}/{self.max_reconnect_attempts} "
                              f"to {self.host}:{self.port} after {backoff:.2f}s")
                    time.sleep(backoff)

                self._connect()

                if self.on_reconnect:
                    self.on_reconnect(self, attempt + 1)

                return True

            except Exception as e:
                logger.warning(f"Reconnect attempt {attempt + 1} failed: {e}")

        return False

    def _execute_command_internal(self, *args) -> Any:
        """Внутреннее выполнение команды без retry"""
        if not self.sock:
            raise RedisConnectionError("Not connected")

        command = RESPParser.encode_command(*args)
        self.sock.sendall(command)
        return RESPParser.decode_response(self.sock)

    def execute_command(self, *args, retry: bool = True) -> Any:
        """Выполнение команды с auto-reconnect"""
        if not self._is_connected:
            raise RedisConnectionError("Not connected")

        try:
            return self._execute_command_internal(*args)

        except RedisError:
            raise

        except Exception as e:
            logger.error(f"Command failed: {e}")
            self._is_connected = False

            if self.on_disconnect:
                self.on_disconnect(self)

            if self.sock:
                self.sock.close()
                self.sock = None

            if retry:
                if self._reconnect():
                    return self.execute_command(*args, retry=False)

            raise RedisConnectionError(f"Command failed: {e}")

    def execute_pipeline(self, commands: List[Tuple]) -> List[Any]:
        """Выполнение пакета команд через один сокет"""
        if not self._is_connected or not self.sock:
            raise RedisConnectionError("Not connected")

        try:
            # Отправляем все команды одним sendall
            encoded = RESPParser.encode_commands(commands)
            self.sock.sendall(encoded)

            # Читаем все ответы
            results = []
            for _ in commands:
                try:
                    results.append(RESPParser.decode_response(self.sock))
                except RedisError as e:
                    results.append(e)

            return results

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            self._is_connected = False

            if self.on_disconnect:
                self.on_disconnect(self)

            if self.sock:
                self.sock.close()
                self.sock = None

            raise RedisConnectionError(f"Pipeline failed: {e}")

    def is_healthy(self) -> bool:
        """Health check соединения"""
        try:
            return self.ping()
        except:
            return False

    def ping(self) -> bool:
        """PING проверка"""
        try:
            response = self.execute_command('PING', retry=False)
            return response in ('PONG', b'PONG')
        except:
            return False

    def close(self):
        """Закрытие соединения"""
        if self.sock:
            self._is_connected = False

            if self.on_disconnect:
                try:
                    self.on_disconnect(self)
                except:
                    pass

            self.sock.close()
            self.sock = None


# ============ Connection Pool ============

class ConnectionPool:
    """Пул переиспользуемых соединений"""

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 ssl_check_hostname: bool = True, ssl_verify: bool = True,
                 max_connections: int = 50, min_idle_connections: int = 1,
                 health_check_interval: int = 30):

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
            'ssl_verify': ssl_verify
        }

        self.max_connections = max_connections
        self.min_idle_connections = min_idle_connections
        self.health_check_interval = health_check_interval

        self._pool: List[RedisConnection] = []
        self._in_use: set = set()
        self._lock = Lock()
        self._created_connections = 0
        self._last_health_check = 0

    def get_connection(self) -> RedisConnection:
        """Получить соединение из пула"""
        with self._lock:
            # Health check периодически
            current_time = time.time()
            if current_time - self._last_health_check > self.health_check_interval:
                self._health_check()
                self._last_health_check = current_time

            # Ищем готовое соединение
            while self._pool:
                conn = self._pool.pop()
                if conn.is_healthy():
                    self._in_use.add(id(conn))
                    return conn
                else:
                    conn.close()
                    self._created_connections -= 1

            # Создаём новое
            if self._created_connections < self.max_connections:
                conn = RedisConnection(**self.connection_kwargs)
                self._created_connections += 1
                self._in_use.add(id(conn))
                return conn

            raise RedisConnectionError("Connection pool exhausted")

    def release(self, conn: RedisConnection):
        """Вернуть соединение в пул"""
        with self._lock:
            conn_id = id(conn)
            if conn_id in self._in_use:
                self._in_use.remove(conn_id)

                if conn.is_healthy():
                    self._pool.append(conn)
                else:
                    conn.close()
                    self._created_connections -= 1

    def _health_check(self):
        """Проверка здоровья соединений в пуле"""
        healthy = []
        for conn in self._pool:
            if conn.is_healthy():
                healthy.append(conn)
            else:
                conn.close()
                self._created_connections -= 1

        self._pool = healthy

    def close_all(self):
        """Закрыть все соединения"""
        with self._lock:
            for conn in self._pool:
                conn.close()
            self._pool.clear()
            self._in_use.clear()
            self._created_connections = 0


# ============ Cluster Node ============

class ClusterNode:
    """Информация об узле кластера"""

    def __init__(self, host: str, port: int, node_id: str, slots: List[int],
                 role: str = 'master', replicas: Optional[List['ClusterNode']] = None):
        self.host = host
        self.port = port
        self.node_id = node_id
        self.slots = slots
        self.role = role
        self.replicas = replicas or []

    def __repr__(self):
        return f"ClusterNode(host={self.host}, port={self.port}, role={self.role}, slots={len(self.slots)})"

    def __str__(self):
        return f"{self.host}:{self.port}"


# ============ Redis Client ============

class RedisClient:
    """Production-ready Redis клиент с полной поддержкой Cluster"""

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 ssl_check_hostname: bool = True, ssl_verify: bool = True,
                 decode_responses: bool = False, is_cluster: bool = False,
                 max_connections: int = 50,
                 read_from_replicas: bool = False,
                 replica_selector: str = 'random',
                 auto_refresh_topology: bool = True,
                 topology_refresh_interval: int = 300,
                 sentinel_service_name: Optional[str] = None,
                 sentinels: Optional[List[Tuple[str, int]]] = None):

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
        self.ssl_verify = ssl_verify
        self.decode_responses = decode_responses
        self.is_cluster = is_cluster
        self.max_connections = max_connections

        # Replica support
        self.read_from_replicas = read_from_replicas
        self.replica_selector = replica_selector

        # Topology refresh
        self.auto_refresh_topology = auto_refresh_topology
        self.topology_refresh_interval = topology_refresh_interval
        self._last_topology_refresh = 0

        # Sentinel support
        self.sentinel_service_name = sentinel_service_name
        self.sentinels = sentinels

        # Cluster state
        self.cluster_pools: Dict[str, ConnectionPool] = {}
        self.cluster_slots: Dict[int, str] = {}
        self.cluster_nodes_info: Dict[str, ClusterNode] = {}
        self._pool_lock = Lock()

        # Main connection pool
        if sentinels and sentinel_service_name:
            master_host, master_port = self._discover_master_from_sentinel()
            self.host = master_host
            self.port = master_port

        self.main_pool = ConnectionPool(
            host=self.host, port=self.port,
            password=password, username=username,
            db=db, socket_timeout=socket_timeout,
            ssl=ssl, ssl_ca_certs=ssl_ca_certs,
            ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile,
            ssl_check_hostname=ssl_check_hostname, ssl_verify=ssl_verify,
            max_connections=max_connections
        )

        if self.is_cluster:
            self._load_cluster_topology()

    def _discover_master_from_sentinel(self) -> Tuple[str, int]:
        """Получить адрес мастера через Sentinel"""
        if not self.sentinels or not self.sentinel_service_name:
            raise RedisError("Sentinels not configured")

        for sentinel_host, sentinel_port in self.sentinels:
            try:
                sentinel_conn = RedisConnection(
                    host=sentinel_host, port=sentinel_port,
                    socket_timeout=self.socket_timeout
                )

                response = sentinel_conn.execute_command(
                    'SENTINEL', 'get-master-addr-by-name', self.sentinel_service_name
                )

                sentinel_conn.close()

                if response and len(response) == 2:
                    master_host = response[0].decode('utf-8') if isinstance(response[0], bytes) else response[0]
                    master_port = int(response[1])
                    logger.info(f"Discovered master from sentinel: {master_host}:{master_port}")
                    return master_host, master_port

            except Exception as e:
                logger.warning(f"Failed to contact sentinel {sentinel_host}:{sentinel_port}: {e}")

        raise RedisConnectionError("Failed to discover master from all sentinels")

    def _load_cluster_topology(self, force: bool = False):
        """Загрузка топологии кластера"""
        current_time = time.time()

        if not force and current_time - self._last_topology_refresh < self.topology_refresh_interval:
            return

        try:
            conn = self.main_pool.get_connection()
            try:
                slots_info = conn.execute_command('CLUSTER', 'SLOTS')
            finally:
                self.main_pool.release(conn)

            new_slots = {}
            new_nodes = {}

            for slot_range in slots_info:
                start_slot = slot_range[0]
                end_slot = slot_range[1]
                master_info = slot_range[2]

                master_host = master_info[0].decode('utf-8') if isinstance(master_info[0], bytes) else master_info[0]
                master_port = master_info[1]
                master_id = f"{master_host}:{master_port}"

                # Реплики
                replicas = []
                for replica_info in slot_range[3:]:
                    replica_host = replica_info[0].decode('utf-8') if isinstance(replica_info[0], bytes) else replica_info[0]
                    replica_port = replica_info[1]
                    replica_id = f"{replica_host}:{replica_port}"

                    replica_node = ClusterNode(
                        host=replica_host,
                        port=replica_port,
                        node_id=replica_id,
                        slots=[],
                        role='replica'
                    )
                    replicas.append(replica_node)

                    # Создаём пул для реплики
                    if replica_id not in self.cluster_pools:
                        self.cluster_pools[replica_id] = ConnectionPool(
                            host=replica_host, port=replica_port,
                            password=self.password, username=self.username,
                            socket_timeout=self.socket_timeout,
                            ssl=self.ssl, ssl_ca_certs=self.ssl_ca_certs,
                            ssl_certfile=self.ssl_certfile, ssl_keyfile=self.ssl_keyfile,
                            ssl_check_hostname=self.ssl_check_hostname, ssl_verify=self.ssl_verify,
                            max_connections=self.max_connections
                        )

                # Создаём или обновляем узел мастера
                slots_for_master = list(range(start_slot, end_slot + 1))

                if master_id in new_nodes:
                    new_nodes[master_id].slots.extend(slots_for_master)
                    new_nodes[master_id].replicas.extend(replicas)
                else:
                    new_nodes[master_id] = ClusterNode(
                        host=master_host,
                        port=master_port,
                        node_id=master_id,
                        slots=slots_for_master,
                        role='master',
                        replicas=replicas
                    )

                # Маппинг слотов
                for slot in slots_for_master:
                    new_slots[slot] = master_id

                # Создаём пул для мастера
                if master_id not in self.cluster_pools:
                    self.cluster_pools[master_id] = ConnectionPool(
                        host=master_host, port=master_port,
                        password=self.password, username=self.username,
                        socket_timeout=self.socket_timeout,
                        ssl=self.ssl, ssl_ca_certs=self.ssl_ca_certs,
                        ssl_certfile=self.ssl_certfile, ssl_keyfile=self.ssl_keyfile,
                        ssl_check_hostname=self.ssl_check_hostname, ssl_verify=self.ssl_verify,
                        max_connections=self.max_connections
                    )

            self.cluster_slots = new_slots
            self.cluster_nodes_info = new_nodes
            self._last_topology_refresh = current_time

            logger.info(f"Loaded cluster topology: {len(new_nodes)} nodes, {len(new_slots)} slots")

        except Exception as e:
            logger.error(f"Failed to load cluster topology: {e}")

    def _get_slot(self, key: Union[str, bytes]) -> int:
        """CRC16 hash slot calculation"""
        if isinstance(key, str):
            key = key.encode('utf-8')

        # Hash tag support
        start = key.find(b'{')
        if start != -1:
            end = key.find(b'}', start + 1)
            if end != -1 and end > start + 1:
                key = key[start + 1:end]

        crc = 0
        for byte in key:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc = crc << 1
            crc &= 0xFFFF

        return crc % 16384

    def _get_pool_for_key(self, key: Union[str, bytes], for_read: bool = False) -> ConnectionPool:
        """Получить пул соединений для ключа"""
        if not self.is_cluster:
            return self.main_pool

        # Автообновление топологии
        if self.auto_refresh_topology:
            self._load_cluster_topology()

        slot = self._get_slot(key)
        node_id = self.cluster_slots.get(slot)

        if not node_id:
            return self.main_pool

        # Если читаем и включено чтение с реплик
        if for_read and self.read_from_replicas:
            node_info = self.cluster_nodes_info.get(node_id)
            if node_info and node_info.replicas:
                if self.replica_selector == 'random':
                    replica = random.choice(node_info.replicas)
                    replica_pool = self.cluster_pools.get(replica.node_id)
                    if replica_pool:
                        return replica_pool
                elif self.replica_selector == 'round_robin':
                    # Простая реализация round-robin
                    replica = node_info.replicas[hash(key) % len(node_info.replicas)]
                    replica_pool = self.cluster_pools.get(replica.node_id)
                    if replica_pool:
                        return replica_pool

        pool = self.cluster_pools.get(node_id)
        return pool if pool else self.main_pool

    def execute_command(self, *args, key: Optional[Union[str, bytes]] = None,
                       for_read: bool = False) -> Any:
        """Выполнение команды с поддержкой кластера и редиректов"""
        max_redirects = 5
        redirect_count = 0

        if key is None and len(args) > 1:
            key = args[1]

        pool = self._get_pool_for_key(key, for_read=for_read) if key else self.main_pool

        while redirect_count < max_redirects:
            conn = pool.get_connection()
            try:
                response = conn.execute_command(*args)

                if self.decode_responses:
                    response = self._decode_response(response)

                return response

            except RedisError as e:
                error_msg = str(e)

                if error_msg.startswith('MOVED'):
                    # Обновляем топологию
                    parts = error_msg.split()
                    if len(parts) >= 3:
                        slot = int(parts[1])
                        node_addr = parts[2]
                        host, port_str = node_addr.split(':')
                        port = int(port_str)
                        node_id = f"{host}:{port}"

                        # Создаём новый пул если нужно
                        if node_id not in self.cluster_pools:
                            self.cluster_pools[node_id] = ConnectionPool(
                                host=host, port=port,
                                password=self.password, username=self.username,
                                socket_timeout=self.socket_timeout,
                                ssl=self.ssl, ssl_ca_certs=self.ssl_ca_certs,
                                ssl_certfile=self.ssl_certfile, ssl_keyfile=self.ssl_keyfile,
                                ssl_check_hostname=self.ssl_check_hostname, ssl_verify=self.ssl_verify,
                                max_connections=self.max_connections
                            )

                        self.cluster_slots[slot] = node_id
                        pool = self.cluster_pools[node_id]
                        redirect_count += 1

                        # Форсируем обновление топологии
                        if self.auto_refresh_topology:
                            self._load_cluster_topology(force=True)

                        continue

                elif error_msg.startswith('ASK'):
                    parts = error_msg.split()
                    if len(parts) >= 3:
                        node_addr = parts[2]
                        host, port_str = node_addr.split(':')

                        temp_conn = RedisConnection(
                            host=host, port=int(port_str),
                            password=self.password, username=self.username,
                            socket_timeout=self.socket_timeout,
                            ssl=self.ssl, ssl_ca_certs=self.ssl_ca_certs,
                            ssl_certfile=self.ssl_certfile, ssl_keyfile=self.ssl_keyfile,
                            ssl_check_hostname=self.ssl_check_hostname, ssl_verify=self.ssl_verify
                        )

                        try:
                            temp_conn.execute_command('ASKING')
                            response = temp_conn.execute_command(*args)

                            if self.decode_responses:
                                response = self._decode_response(response)

                            return response
                        finally:
                            temp_conn.close()

                raise

            finally:
                pool.release(conn)

        raise RedisClusterError("Too many redirects")

    def _decode_response(self, response):
        """Декодирование ответа"""
        if isinstance(response, bytes):
            return response.decode('utf-8', errors='replace')
        elif isinstance(response, list):
            return [self._decode_response(item) for item in response]
        elif isinstance(response, dict):
            return {self._decode_response(k): self._decode_response(v) 
                   for k, v in response.items()}
        return response

    # ============ Multi-key команды ============

    def mget(self, *keys) -> List[Optional[bytes]]:
        """MGET с группировкой по слотам"""
        if not self.is_cluster:
            return self.execute_command('MGET', *keys)

        # Группировка ключей по слотам
        slot_groups = defaultdict(list)
        key_order = {}

        for idx, key in enumerate(keys):
            slot = self._get_slot(key)
            slot_groups[slot].append(key)
            key_order[key] = idx

        # Если все ключи в одном слоте
        if len(slot_groups) == 1:
            return self.execute_command('MGET', *keys, key=keys[0], for_read=True)

        # Выполняем GET для каждого ключа
        results = [None] * len(keys)
        for slot, slot_keys in slot_groups.items():
            for key in slot_keys:
                value = self.execute_command('GET', key, key=key, for_read=True)
                results[key_order[key]] = value

        return results

    def mset(self, mapping: Dict[Union[str, bytes], Union[str, bytes]]) -> str:
        """MSET с группировкой по слотам"""
        if not self.is_cluster:
            args = ['MSET']
            for k, v in mapping.items():
                args.extend([k, v])
            return self.execute_command(*args)

        # Группировка по слотам
        slot_groups = defaultdict(dict)
        for key, value in mapping.items():
            slot = self._get_slot(key)
            slot_groups[slot][key] = value

        # Если все в одном слоте
        if len(slot_groups) == 1:
            args = ['MSET']
            for k, v in mapping.items():
                args.extend([k, v])
            first_key = next(iter(mapping.keys()))
            return self.execute_command(*args, key=first_key)

        # Выполняем SET для каждого ключа
        for slot, slot_mapping in slot_groups.items():
            for key, value in slot_mapping.items():
                self.execute_command('SET', key, value, key=key)

        return 'OK'

    def delete(self, *keys) -> int:
        """DEL с группировкой по слотам"""
        if not self.is_cluster:
            return self.execute_command('DEL', *keys, key=keys[0] if keys else None)

        # Группировка по слотам
        slot_groups = defaultdict(list)
        for key in keys:
            slot = self._get_slot(key)
            slot_groups[slot].append(key)

        # Если все в одном слоте
        if len(slot_groups) == 1:
            return self.execute_command('DEL', *keys, key=keys[0])

        # Удаляем по группам
        total = 0
        for slot, slot_keys in slot_groups.items():
            total += self.execute_command('DEL', *slot_keys, key=slot_keys[0])

        return total

    # ============ Basic Commands ============

    def ping(self) -> bool:
        """PING"""
        try:
            response = self.execute_command('PING')
            return response in ('PONG', b'PONG')
        except:
            return False

    def get(self, key: Union[str, bytes]) -> Optional[bytes]:
        """GET"""
        return self.execute_command('GET', key, key=key, for_read=True)

    def set(self, key: Union[str, bytes], value: Union[str, bytes, int, float],
            ex: Optional[int] = None, px: Optional[int] = None,
            nx: bool = False, xx: bool = False) -> Optional[str]:
        """SET"""
        args = ['SET', key, value]

        if ex is not None:
            args.extend(['EX', ex])
        if px is not None:
            args.extend(['PX', px])
        if nx:
            args.append('NX')
        if xx:
            args.append('XX')

        return self.execute_command(*args, key=key)

    def incr(self, key: Union[str, bytes]) -> int:
        """INCR"""
        return self.execute_command('INCR', key, key=key)

    def decr(self, key: Union[str, bytes]) -> int:
        """DECR"""
        return self.execute_command('DECR', key, key=key)

    def exists(self, *keys) -> int:
        """EXISTS"""
        if not keys:
            return 0
        return self.execute_command('EXISTS', *keys, key=keys[0], for_read=True)

    def ttl(self, key: Union[str, bytes]) -> int:
        """TTL"""
        return self.execute_command('TTL', key, key=key, for_read=True)

    def expire(self, key: Union[str, bytes], seconds: int) -> int:
        """EXPIRE"""
        return self.execute_command('EXPIRE', key, seconds, key=key)

    def persist(self, key: Union[str, bytes]) -> int:
        """PERSIST"""
        return self.execute_command('PERSIST', key, key=key)

    # ============ Hash Commands ============

    def hget(self, key: Union[str, bytes], field: Union[str, bytes]) -> Optional[bytes]:
        """HGET"""
        return self.execute_command('HGET', key, field, key=key, for_read=True)

    def hset(self, key: Union[str, bytes], field: Optional[Union[str, bytes]] = None,
             value: Optional[Union[str, bytes]] = None, mapping: Optional[Dict] = None) -> int:
        """HSET"""
        args = ['HSET', key]

        if mapping:
            for k, v in mapping.items():
                args.extend([k, v])
        elif field is not None and value is not None:
            args.extend([field, value])
        else:
            raise ValueError("field+value or mapping required")

        return self.execute_command(*args, key=key)

    def hgetall(self, key: Union[str, bytes]) -> Dict[bytes, bytes]:
        """HGETALL"""
        response = self.execute_command('HGETALL', key, key=key, for_read=True)
        result = {}
        for i in range(0, len(response), 2):
            result[response[i]] = response[i + 1]
        return result

    def hlen(self, key: Union[str, bytes]) -> int:
        """HLEN"""
        return self.execute_command('HLEN', key, key=key, for_read=True)

    # ============ List Commands ============

    def lpush(self, key: Union[str, bytes], *values) -> int:
        """LPUSH"""
        return self.execute_command('LPUSH', key, *values, key=key)

    def rpush(self, key: Union[str, bytes], *values) -> int:
        """RPUSH"""
        return self.execute_command('RPUSH', key, *values, key=key)

    def lpop(self, key: Union[str, bytes]) -> Optional[bytes]:
        """LPOP"""
        return self.execute_command('LPOP', key, key=key)

    def rpop(self, key: Union[str, bytes]) -> Optional[bytes]:
        """RPOP"""
        return self.execute_command('RPOP', key, key=key)

    def llen(self, key: Union[str, bytes]) -> int:
        """LLEN"""
        return self.execute_command('LLEN', key, key=key, for_read=True)

    def lrange(self, key: Union[str, bytes], start: int, stop: int) -> List[bytes]:
        """LRANGE"""
        return self.execute_command('LRANGE', key, start, stop, key=key, for_read=True)

    # ============ Set Commands ============

    def sadd(self, key: Union[str, bytes], *members) -> int:
        """SADD"""
        return self.execute_command('SADD', key, *members, key=key)

    def smembers(self, key: Union[str, bytes]) -> set:
        """SMEMBERS"""
        result = self.execute_command('SMEMBERS', key, key=key, for_read=True)
        return set(result) if result else set()

    def scard(self, key: Union[str, bytes]) -> int:
        """SCARD"""
        return self.execute_command('SCARD', key, key=key, for_read=True)

    def sismember(self, key: Union[str, bytes], member: Union[str, bytes]) -> int:
        """SISMEMBER"""
        return self.execute_command('SISMEMBER', key, member, key=key, for_read=True)

    # ============ Sorted Set Commands ============

    def zadd(self, key: Union[str, bytes], mapping: Dict[Union[str, bytes], float],
             nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> int:
        """ZADD"""
        args = ['ZADD', key]

        if nx:
            args.append('NX')
        if xx:
            args.append('XX')
        if gt:
            args.append('GT')
        if lt:
            args.append('LT')

        for member, score in mapping.items():
            args.extend([score, member])

        return self.execute_command(*args, key=key)

    def zcard(self, key: Union[str, bytes]) -> int:
        """ZCARD"""
        return self.execute_command('ZCARD', key, key=key, for_read=True)

    def zrange(self, key: Union[str, bytes], start: int, stop: int,
               withscores: bool = False) -> List:
        """ZRANGE"""
        args = ['ZRANGE', key, start, stop]

        if withscores:
            args.append('WITHSCORES')

        response = self.execute_command(*args, key=key, for_read=True)

        if withscores and response:
            result = []
            for i in range(0, len(response), 2):
                result.append((response[i], float(response[i + 1])))
            return result

        return response

    # ============ Scan ============

    def scan(self, cursor: int = 0, match: Optional[str] = None,
             count: Optional[int] = None) -> Tuple[int, List[bytes]]:
        """SCAN"""
        args = ['SCAN', cursor]

        if match:
            args.extend(['MATCH', match])
        if count:
            args.extend(['COUNT', count])

        response = self.execute_command(*args, for_read=True)
        return int(response[0]), response[1]

    def scan_iter(self, match: Optional[str] = None, count: int = 100) -> Iterator[bytes]:
        """Итератор SCAN"""
        cursor = 0
        while True:
            cursor, keys = self.scan(cursor, match=match, count=count)
            for key in keys:
                yield key
            if cursor == 0:
                break

    # ============ Cluster Utilities ============

    def keyslot(self, key: Union[str, bytes]) -> int:
        """Вычисляет hash slot для ключа"""
        return self._get_slot(key)

    def get_cluster_nodes(self) -> List[ClusterNode]:
        """Список всех узлов кластера"""
        if not self.is_cluster:
            return [ClusterNode(
                host=self.host,
                port=self.port,
                node_id=f"{self.host}:{self.port}",
                slots=[],
                role='master'
            )]

        return list(self.cluster_nodes_info.values())

    def refresh_cluster_topology(self):
        """Принудительное обновление топологии кластера"""
        if self.is_cluster:
            self._load_cluster_topology(force=True)

    # ============ Pipeline ============

    def pipeline(self, transaction: bool = False) -> 'RedisPipeline':
        """Создать pipeline"""
        return RedisPipeline(self, transaction=transaction)

    # ============ Close ============

    def close(self):
        """Закрыть все соединения"""
        self.main_pool.close_all()

        for pool in self.cluster_pools.values():
            pool.close_all()

        self.cluster_pools.clear()


# ============ Pipeline ============

class RedisPipeline:
    """Настоящий Pipeline с batch отправкой через один сокет"""

    def __init__(self, client: RedisClient, transaction: bool = False):
        self.client = client
        self.transaction = transaction
        self.commands: List[Tuple] = []
        self.command_keys: List[Optional[Union[str, bytes]]] = []

    def execute(self) -> List[Any]:
        """Выполнить все команды"""
        if not self.commands:
            return []

        # В режиме кластера группируем по узлам
        if self.client.is_cluster:
            return self._execute_cluster()
        else:
            return self._execute_single()

    def _execute_single(self) -> List[Any]:
        """Выполнение на одном узле"""
        pool = self.client.main_pool
        conn = pool.get_connection()

        try:
            if self.transaction:
                # MULTI/EXEC транзакция
                commands_with_multi = [('MULTI',)] + self.commands + [('EXEC',)]
                results = conn.execute_pipeline(commands_with_multi)
                # Возвращаем только результаты EXEC
                return results[-1] if results[-1] else []
            else:
                # Простой pipeline
                results = conn.execute_pipeline(self.commands)

                if self.client.decode_responses:
                    results = [self.client._decode_response(r) if not isinstance(r, Exception) else r 
                             for r in results]

                return results

        finally:
            pool.release(conn)
            self.commands.clear()
            self.command_keys.clear()

    def _execute_cluster(self) -> List[Any]:
        """Выполнение в кластере с группировкой по узлам"""
        # Группируем команды по узлам
        node_commands = defaultdict(list)
        command_order = []

        for idx, (cmd, key) in enumerate(zip(self.commands, self.command_keys)):
            if key:
                pool = self.client._get_pool_for_key(key)
            else:
                pool = self.client.main_pool

            node_id = id(pool)
            node_commands[node_id].append((idx, cmd, pool))
            command_order.append((node_id, len(node_commands[node_id]) - 1))

        # Выполняем на каждом узле
        node_results = {}
        for node_id, commands_list in node_commands.items():
            pool = commands_list[0][2]
            commands = [cmd for _, cmd, _ in commands_list]

            conn = pool.get_connection()
            try:
                results = conn.execute_pipeline(commands)
                node_results[node_id] = results
            finally:
                pool.release(conn)

        # Восстанавливаем порядок
        final_results = []
        for node_id, idx_in_node in command_order:
            result = node_results[node_id][idx_in_node]

            if self.client.decode_responses and not isinstance(result, Exception):
                result = self.client._decode_response(result)

            final_results.append(result)

        self.commands.clear()
        self.command_keys.clear()

        return final_results

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.execute()
        return False

    def __getattr__(self, name):
        """Перехват методов клиента"""
        def method(*args, **kwargs):
            # Определяем ключ из аргументов
            key = kwargs.get('key')
            if key is None and len(args) > 0:
                key = args[0]

            # Формируем команду
            cmd_name = name.upper()

            # Особые случаи
            if cmd_name == 'SET':
                cmd_args = ['SET', args[0], args[1]]
                if len(args) > 2:
                    cmd_args.extend(args[2:])
            elif cmd_name == 'HSET':
                cmd_args = ['HSET', args[0]]
                if 'mapping' in kwargs and kwargs['mapping']:
                    for k, v in kwargs['mapping'].items():
                        cmd_args.extend([k, v])
                elif len(args) >= 3:
                    cmd_args.extend([args[1], args[2]])
            else:
                cmd_args = [cmd_name] + list(args)

            self.commands.append(tuple(cmd_args))
            self.command_keys.append(key)

            return self

        return method


if __name__ == '__main__':
    # Примеры использования

    # 1. Простое подключение с auto-reconnect
    client = RedisClient(
        host='localhost',
        port=6379,
        decode_responses=True,
        max_connections=50
    )

    client.set('key', 'value')
    print(client.get('key'))

    # 2. Cluster с репликами
    cluster_client = RedisClient(
        host='localhost',
        port=7000,
        is_cluster=True,
        read_from_replicas=True,
        replica_selector='random',
        decode_responses=True
    )

    cluster_client.set('mykey', 'myvalue')
    print(cluster_client.get('mykey'))

    # 3. Pipeline
    with cluster_client.pipeline() as pipe:
        pipe.set('key1', 'val1')
        pipe.set('key2', 'val2')
        pipe.get('key1')
        pipe.get('key2')
        results = pipe.execute()
        print(results)

    # 4. Multi-key операции
    cluster_client.mset({'key1': 'val1', 'key2': 'val2', 'key3': 'val3'})
    values = cluster_client.mget('key1', 'key2', 'key3')
    print(values)

    # 5. Sentinel
    sentinel_client = RedisClient(
        sentinels=[('localhost', 26379), ('localhost', 26380)],
        sentinel_service_name='mymaster',
        decode_responses=True
    )

    # 6. SSL без проверки сертификата
    ssl_client = RedisClient(
        host='localhost',
        port=6380,
        ssl=True,
        ssl_verify=False,
        decode_responses=True
    )

    client.close()
