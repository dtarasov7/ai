"""
Simple Redis Client - Полная версия
Поддержка: RESP, Cluster, SSL, scan_iter, keyslot, get_node_from_key
"""
__version__ = "1.0.0"
__author__ = "Dmitry Tarasov"
__all__ = [
    'RedisClient', 
    'RedisConnection', 
    'RedisPipeline',
    'RedisError', 
    'RedisConnectionError', 
    'RedisClusterError',
    'ClusterNode'
]

import socket
import ssl as ssl_module
from typing import Optional, List, Dict, Any, Tuple, Union, Iterator
import logging

logger = logging.getLogger(__name__)


class RedisError(Exception):
    """Базовая ошибка Redis"""
    pass


class RedisConnectionError(RedisError):
    """Ошибка подключения"""
    pass


class RedisClusterError(RedisError):
    """Ошибка кластера"""
    pass


class RESPParser:
    """Парсер RESP протокола"""

    @staticmethod
    def encode_command(*args) -> bytes:
        """Кодирование команды в RESP формат"""
        parts = [f'*{len(args)}\r\n'.encode()]

        for arg in args:
            if isinstance(arg, bytes):
                data = arg
            elif isinstance(arg, str):
                data = arg.encode('utf-8')
            elif isinstance(arg, int):
                data = str(arg).encode('utf-8')
            elif isinstance(arg, float):
                data = str(arg).encode('utf-8')
            else:
                data = str(arg).encode('utf-8')

            parts.append(f'${len(data)}\r\n'.encode())
            parts.append(data)
            parts.append(b'\r\n')

        return b''.join(parts)

    @staticmethod
    def decode_response(sock) -> Any:
        """Декодирование ответа RESP"""
        line = RESPParser._read_line(sock)

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
            while len(bulk_data) < length:
                chunk = sock.recv(length - len(bulk_data))
                if not chunk:
                    raise RedisConnectionError("Connection closed")
                bulk_data += chunk
            sock.recv(2)
            return bulk_data
        elif prefix == '*':
            count = int(data)
            if count == -1:
                return None
            return [RESPParser.decode_response(sock) for _ in range(count)]
        else:
            raise RedisError(f"Unknown RESP prefix: {prefix}")

    @staticmethod
    def _read_line(sock) -> bytes:
        """Чтение строки до \r\n"""
        line = b''
        while True:
            char = sock.recv(1)
            if not char:
                raise RedisConnectionError("Connection closed")
            line += char
            if line.endswith(b'\r\n'):
                return line[:-2]


class RedisConnection:
    """Подключение к одному Redis узлу"""

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 ssl_check_hostname: bool = True):

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
        self.sock: Optional[socket.socket] = None
        self._connect()

    def _connect(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.socket_timeout)
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

            if self.password:
                if self.username:
                    self.execute_command('AUTH', self.username, self.password)
                else:
                    self.execute_command('AUTH', self.password)

            if self.db != 0:
                self.execute_command('SELECT', self.db)

            logger.info(f"Connected to {self.host}:{self.port} (db={self.db})")
        except Exception as e:
            if self.sock:
                self.sock.close()
                self.sock = None
            raise RedisConnectionError(f"Failed to connect: {e}")

    def execute_command(self, *args) -> Any:
        if not self.sock:
            raise RedisConnectionError("Not connected")
        try:
            command = RESPParser.encode_command(*args)
            self.sock.sendall(command)
            return RESPParser.decode_response(self.sock)
        except RedisError:
            raise
        except Exception as e:
            self.close()
            raise RedisConnectionError(f"Command failed: {e}")

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def ping(self) -> bool:
        try:
            return self.execute_command('PING') == 'PONG'
        except:
            return False


class ClusterNode:
    """Информация об узле кластера"""

    def __init__(self, host: str, port: int, node_id: str, slots: List[int]):
        self.host = host
        self.port = port
        self.node_id = node_id
        self.slots = slots

    def __repr__(self):
        return f"ClusterNode(host={self.host}, port={self.port}, slots={len(self.slots)})"

    def __str__(self):
        return f"{self.host}:{self.port}"


class RedisClient:
    """Redis клиент с полной поддержкой Cluster"""

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 password: Optional[str] = None, username: Optional[str] = None,
                 db: int = 0, socket_timeout: int = 5,
                 ssl: bool = False, ssl_ca_certs: Optional[str] = None,
                 ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None,
                 decode_responses: bool = False, is_cluster: bool = False):

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

        self.connection: Optional[RedisConnection] = None
        self.cluster_nodes: Dict[str, RedisConnection] = {}
        self.cluster_slots: Dict[int, str] = {}

        self._init_connection()

    def _init_connection(self):
        conn_kwargs = {
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
        }

        self.connection = RedisConnection(**conn_kwargs)

        if self.is_cluster:
            self._load_cluster_topology()

    def _load_cluster_topology(self):
        try:
            slots_info = self.connection.execute_command('CLUSTER', 'SLOTS')

            for slot_range in slots_info:
                start_slot = slot_range[0]
                end_slot = slot_range[1]
                master_info = slot_range[2]

                node_host = master_info[0].decode('utf-8')
                node_port = master_info[1]
                node_id = f"{node_host}:{node_port}"

                if node_id not in self.cluster_nodes:
                    conn = RedisConnection(
                        host=node_host,
                        port=node_port,
                        password=self.password,
                        username=self.username,
                        socket_timeout=self.socket_timeout,
                        ssl=self.ssl,
                        ssl_ca_certs=self.ssl_ca_certs,
                        ssl_certfile=self.ssl_certfile,
                        ssl_keyfile=self.ssl_keyfile
                    )
                    self.cluster_nodes[node_id] = conn

                for slot in range(start_slot, end_slot + 1):
                    self.cluster_slots[slot] = node_id

            logger.info(f"Loaded cluster: {len(self.cluster_nodes)} nodes")
        except Exception as e:
            logger.warning(f"Failed to load cluster topology: {e}")

    def _get_slot(self, key: Union[str, bytes]) -> int:
        """CRC16 hash slot calculation"""
        if isinstance(key, str):
            key = key.encode('utf-8')

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

    def _get_connection_for_key(self, key: Union[str, bytes]) -> RedisConnection:
        if not self.is_cluster:
            return self.connection

        slot = self._get_slot(key)
        node_id = self.cluster_slots.get(slot)

        if node_id and node_id in self.cluster_nodes:
            return self.cluster_nodes[node_id]

        return self.connection

    def execute_command(self, *args, key: Optional[Union[str, bytes]] = None) -> Any:
        max_redirects = 5
        redirect_count = 0

        if key is None and len(args) > 1:
            key = args[1]

        conn = self._get_connection_for_key(key) if key else self.connection

        while redirect_count < max_redirects:
            try:
                response = conn.execute_command(*args)
                if self.decode_responses:
                    response = self._decode_response(response)
                return response
            except RedisError as e:
                error_msg = str(e)

                if error_msg.startswith('MOVED'):
                    parts = error_msg.split()
                    if len(parts) >= 3:
                        slot = int(parts[1])
                        node_addr = parts[2]
                        host, port = node_addr.split(':')
                        node_id = f"{host}:{port}"

                        if node_id not in self.cluster_nodes:
                            conn = RedisConnection(
                                host=host, port=int(port),
                                password=self.password, username=self.username,
                                socket_timeout=self.socket_timeout, ssl=self.ssl
                            )
                            self.cluster_nodes[node_id] = conn
                        else:
                            conn = self.cluster_nodes[node_id]

                        self.cluster_slots[slot] = node_id
                        redirect_count += 1
                        continue

                elif error_msg.startswith('ASK'):
                    parts = error_msg.split()
                    if len(parts) >= 3:
                        node_addr = parts[2]
                        host, port = node_addr.split(':')
                        temp_conn = RedisConnection(
                            host=host, port=int(port),
                            password=self.password, username=self.username,
                            socket_timeout=self.socket_timeout, ssl=self.ssl
                        )
                        temp_conn.execute_command('ASKING')
                        response = temp_conn.execute_command(*args)
                        temp_conn.close()
                        if self.decode_responses:
                            response = self._decode_response(response)
                        return response
                raise

        raise RedisClusterError(f"Too many redirects")

    def _decode_response(self, response):
        if isinstance(response, bytes):
            return response.decode('utf-8', errors='replace')
        elif isinstance(response, list):
            return [self._decode_response(item) for item in response]
        elif isinstance(response, dict):
            return {self._decode_response(k): self._decode_response(v) for k, v in response.items()}
        return response

    # ============ Basic ============

    def ping(self) -> bool:
        try:
            response = self.execute_command('PING')
            return response in ('PONG', b'PONG')
        except:
            return False

    def info(self, section: Optional[str] = None) -> Dict[str, Any]:
        if section:
            response = self.execute_command('INFO', section)
        else:
            response = self.execute_command('INFO')

        if isinstance(response, bytes):
            response = response.decode('utf-8')

        result = {}
        current_section = None

        for line in response.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                if line.startswith('#'):
                    current_section = line[1:].strip().lower()
                    result[current_section] = {}
                continue
            if ':' in line:
                key, value = line.split(':', 1)
                try:
                    value = float(value) if '.' in value else int(value)
                except:
                    pass
                if current_section:
                    result[current_section][key] = value
                else:
                    result[key] = value
        return result

    def select(self, db: int):
        if self.is_cluster:
            raise RedisError("SELECT not allowed in cluster")
        self.execute_command('SELECT', db)
        self.db = db

    def dbsize(self) -> int:
        """DBSIZE - количество ключей в текущей БД"""
        if self.is_cluster:
            logger.warning("DBSIZE in cluster mode returns approximate count")
        return self.execute_command('DBSIZE')
    
    def flushdb(self, asynchronous: bool = False) -> str:
        """FLUSHDB - очистить текущую БД"""
        if self.is_cluster:
            raise RedisError("FLUSHDB requires cluster-wide operation")
        if asynchronous:
            return self.execute_command('FLUSHDB', 'ASYNC')
        return self.execute_command('FLUSHDB')
    
    def flushall(self, asynchronous: bool = False) -> str:
        """FLUSHALL - очистить все БД"""
        if asynchronous:
            return self.execute_command('FLUSHALL', 'ASYNC')
        return self.execute_command('FLUSHALL')


    # ============ Keys ============

    def keys(self, pattern: str = '*') -> List[bytes]:
        return self.execute_command('KEYS', pattern)

    def scan(self, cursor: int = 0, match: Optional[str] = None, 
             count: Optional[int] = None) -> Tuple[int, List[bytes]]:
        args = ['SCAN', cursor]
        if match:
            args.extend(['MATCH', match])
        if count:
            args.extend(['COUNT', count])
        response = self.execute_command(*args)
        return int(response[0]), response[1]

    def scan_iter(self, match: Optional[str] = None, count: int = 100) -> Iterator[bytes]:
        cursor = 0
        while True:
            cursor, keys = self.scan(cursor, match=match, count=count)
            for key in keys:
                yield key
            if cursor == 0:
                break

    def exists(self, *keys) -> int:
        return self.execute_command('EXISTS', *keys)

    def delete(self, *keys) -> int:
        return self.execute_command('DEL', *keys, key=keys[0] if keys else None)

    def type(self, key: Union[str, bytes]) -> bytes:
        return self.execute_command('TYPE', key, key=key)

    def ttl(self, key: Union[str, bytes]) -> int:
        return self.execute_command('TTL', key, key=key)

    def expire(self, key: Union[str, bytes], seconds: int) -> int:
        return self.execute_command('EXPIRE', key, seconds, key=key)

    def persist(self, key: Union[str, bytes]) -> int:
        return self.execute_command('PERSIST', key, key=key)

    def rename(self, old: Union[str, bytes], new: Union[str, bytes]) -> str:
        return self.execute_command('RENAME', old, new, key=old)

    # ============ String ============

    def get(self, key: Union[str, bytes]) -> Optional[bytes]:
        return self.execute_command('GET', key, key=key)

    def set(self, key: Union[str, bytes], value: Union[str, bytes, int, float],
            ex: Optional[int] = None, px: Optional[int] = None,
            nx: bool = False, xx: bool = False) -> Optional[str]:
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
        return self.execute_command('INCR', key, key=key)

    def strlen(self, key: Union[str, bytes]) -> int:
        return self.execute_command('STRLEN', key, key=key)

    # ============ Hash ============

    def hget(self, key: Union[str, bytes], field: Union[str, bytes]) -> Optional[bytes]:
        return self.execute_command('HGET', key, field, key=key)

    def hset(self, key: Union[str, bytes], field: Optional[Union[str, bytes]] = None,
             value: Optional[Union[str, bytes]] = None, mapping: Optional[Dict] = None) -> int:
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
        response = self.execute_command('HGETALL', key, key=key)
        result = {}
        for i in range(0, len(response), 2):
            result[response[i]] = response[i + 1]
        return result

    def hlen(self, key: Union[str, bytes]) -> int:
        return self.execute_command('HLEN', key, key=key)

    def hscan(self, key: Union[str, bytes], cursor: int = 0,
              match: Optional[str] = None, count: Optional[int] = None) -> Tuple[int, Dict]:
        args = ['HSCAN', key, cursor]
        if match:
            args.extend(['MATCH', match])
        if count:
            args.extend(['COUNT', count])
        response = self.execute_command(*args, key=key)
        new_cursor = int(response[0])
        items = response[1]
        result = {}
        for i in range(0, len(items), 2):
            result[items[i]] = items[i + 1]
        return new_cursor, result

    def hscan_iter(self, key: Union[str, bytes], match: Optional[str] = None, 
                   count: int = 100) -> Iterator[Tuple[bytes, bytes]]:
        cursor = 0
        while True:
            cursor, data = self.hscan(key, cursor, match=match, count=count)
            for field, value in data.items():
                yield field, value
            if cursor == 0:
                break

    # ============ List ============

    def lpush(self, key: Union[str, bytes], *values) -> int:
        return self.execute_command('LPUSH', key, *values, key=key)

    def rpush(self, key: Union[str, bytes], *values) -> int:
        return self.execute_command('RPUSH', key, *values, key=key)

    def llen(self, key: Union[str, bytes]) -> int:
        return self.execute_command('LLEN', key, key=key)

    def lrange(self, key: Union[str, bytes], start: int, stop: int) -> List[bytes]:
        return self.execute_command('LRANGE', key, start, stop, key=key)

    # ============ Set ============

    def sadd(self, key: Union[str, bytes], *members) -> int:
        return self.execute_command('SADD', key, *members, key=key)

    def smembers(self, key: Union[str, bytes]) -> set:
        result = self.execute_command('SMEMBERS', key, key=key)
        return set(result) if result else set()

    def scard(self, key: Union[str, bytes]) -> int:
        return self.execute_command('SCARD', key, key=key)

    def sscan(self, key: Union[str, bytes], cursor: int = 0,
              match: Optional[str] = None, count: Optional[int] = None) -> Tuple[int, List[bytes]]:
        args = ['SSCAN', key, cursor]
        if match:
            args.extend(['MATCH', match])
        if count:
            args.extend(['COUNT', count])
        response = self.execute_command(*args, key=key)
        return int(response[0]), response[1]

    def sscan_iter(self, key: Union[str, bytes], match: Optional[str] = None, 
                   count: int = 100) -> Iterator[bytes]:
        cursor = 0
        while True:
            cursor, members = self.sscan(key, cursor, match=match, count=count)
            for member in members:
                yield member
            if cursor == 0:
                break

    # ============ Sorted Set ============

    def zadd(self, key: Union[str, bytes], mapping: Dict[Union[str, bytes], float],
             nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> int:
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
        return self.execute_command('ZCARD', key, key=key)

    def zrange(self, key: Union[str, bytes], start: int, stop: int,
               withscores: bool = False, desc: bool = False) -> List:
        args = ['ZRANGE', key, start, stop]
        if withscores:
            args.append('WITHSCORES')
        response = self.execute_command(*args, key=key)
        if withscores and response:
            result = []
            for i in range(0, len(response), 2):
                result.append((response[i], float(response[i + 1])))
            return result
        return response

    def zscan(self, key: Union[str, bytes], cursor: int = 0,
              match: Optional[str] = None, count: Optional[int] = None) -> Tuple[int, List]:
        args = ['ZSCAN', key, cursor]
        if match:
            args.extend(['MATCH', match])
        if count:
            args.extend(['COUNT', count])
        response = self.execute_command(*args, key=key)
        new_cursor = int(response[0])
        items = response[1]
        result = []
        for i in range(0, len(items), 2):
            result.append((items[i], float(items[i + 1])))
        return new_cursor, result

    def zscan_iter(self, key: Union[str, bytes], match: Optional[str] = None, 
                   count: int = 100) -> Iterator[Tuple[bytes, float]]:
        cursor = 0
        while True:
            cursor, items = self.zscan(key, cursor, match=match, count=count)
            for member, score in items:
                yield member, score
            if cursor == 0:
                break

    # ============ Server ============

    def config_get(self, parameter: str) -> Dict:
        response = self.execute_command('CONFIG', 'GET', parameter)
        result = {}
        for i in range(0, len(response), 2):
            key = response[i]
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            value = response[i + 1]
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            result[key] = value
        return result

    def client_list(self) -> str:
        response = self.execute_command('CLIENT', 'LIST')
        if isinstance(response, bytes):
            return response.decode('utf-8')
        return response

    # ============ Cluster ============

    def keyslot(self, key: Union[str, bytes]) -> int:
        """Вычисляет hash slot для ключа (CRC16 % 16384)"""
        return self._get_slot(key)

    def get_node_from_key(self, key: Union[str, bytes]) -> ClusterNode:
        """Возвращает информацию об узле для ключа"""
        if not self.is_cluster:
            return ClusterNode(
                host=self.host,
                port=self.port,
                node_id=f"{self.host}:{self.port}",
                slots=[]
            )

        slot = self._get_slot(key)
        node_id = self.cluster_slots.get(slot)

        if node_id and node_id in self.cluster_nodes:
            host, port = node_id.split(':')
            return ClusterNode(
                host=host,
                port=int(port),
                node_id=node_id,
                slots=[slot]
            )

        return ClusterNode(
            host=self.host,
            port=self.port,
            node_id=f"{self.host}:{self.port}",
            slots=[]
        )

    def cluster_keyslot(self, key: Union[str, bytes]) -> int:
        """CLUSTER KEYSLOT - спросить сервер о слоте"""
        if not self.is_cluster:
            return self._get_slot(key)
        try:
            return self.execute_command('CLUSTER', 'KEYSLOT', key)
        except:
            return self._get_slot(key)

    def get_cluster_nodes(self) -> List[ClusterNode]:
        """Список всех узлов кластера"""
        if not self.is_cluster:
            return [ClusterNode(
                host=self.host,
                port=self.port,
                node_id=f"{self.host}:{self.port}",
                slots=[]
            )]

        nodes = []
        for node_id, conn in self.cluster_nodes.items():
            host, port = node_id.split(':')
            slots = [slot for slot, nid in self.cluster_slots.items() if nid == node_id]
            nodes.append(ClusterNode(
                host=host,
                port=int(port),
                node_id=node_id,
                slots=slots
            ))
        return nodes

    def scan_all_nodes_iter(self, match: Optional[str] = None, count: int = 100) -> Iterator[bytes]:
        """Итератор по ВСЕМ ключам кластера (все узлы)"""
        if not self.is_cluster:
            yield from self.scan_iter(match=match, count=count)
            return

        seen_keys = set()

        for node_id, node_conn in self.cluster_nodes.items():
            logger.debug(f"Scanning node {node_id}")
            cursor = 0
            while True:
                args = ['SCAN', cursor]
                if match:
                    args.extend(['MATCH', match])
                if count:
                    args.extend(['COUNT', count])
                try:
                    response = node_conn.execute_command(*args)
                    cursor = int(response[0])
                    keys = response[1]
                    for key in keys:
                        if key not in seen_keys:
                            seen_keys.add(key)
                            yield key
                    if cursor == 0:
                        break
                except Exception as e:
                    logger.error(f"Error scanning node {node_id}: {e}")
                    break

    def cluster_info(self) -> str:
        """CLUSTER INFO"""
        response = self.execute_command('CLUSTER', 'INFO')
        if isinstance(response, bytes):
            return response.decode('utf-8')
        return response

    def cluster_nodes(self) -> str:
        """CLUSTER NODES"""
        response = self.execute_command('CLUSTER', 'NODES')
        if isinstance(response, bytes):
            return response.decode('utf-8')
        return response

    # ============ Pipeline ============

    def pipeline(self, transaction: bool = True, shard_hint: Optional[str] = None):
        """Pipeline для batch операций"""
        return RedisPipeline(self)

    # ============ Close ============

    def close(self):
        """Закрыть все подключения"""
        if self.connection:
            self.connection.close()
        for conn in self.cluster_nodes.values():
            conn.close()
        self.cluster_nodes.clear()


class RedisPipeline:
    """Упрощенный Pipeline"""

    def __init__(self, client: RedisClient):
        self.client = client
        self.commands = []

    def execute(self):
        results = []
        for cmd, args, kwargs in self.commands:
            try:
                results.append(getattr(self.client, cmd)(*args, **kwargs))
            except Exception as e:
                results.append(e)
        self.commands.clear()
        return results

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.execute()
        return False

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.commands.append((name, args, kwargs))
            return self
        return method
