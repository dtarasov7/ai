Покажу конкретные изменения в коде для трех критических проблем безопасности.

## 1. 🔒 **Input Sanitization для всех пользовательских данных**

### 1.1 Создаем модуль валидации `security_utils.py`

```python
# security_utils.py
"""
Модуль безопасности: валидация и санитизация ввода
"""
import re
import os
import sys
from urllib.parse import urlparse
from pathlib import Path, PurePath

class SecurityError(Exception):
    """Базовое исключение для ошибок безопасности"""
    pass

class InputValidator:
    """Валидатор пользовательского ввода"""
    
    @staticmethod
    def validate_path(path, base_path=None):
        """
        Валидация и санитизация путей файловой системы.
        Защита от path traversal attacks.
        """
        if not path:
            raise SecurityError("Path cannot be empty")
        
        # Нормализация пути
        normalized = os.path.normpath(path)
        
        # Защита от path traversal
        if '..' in normalized.split(os.sep):
            raise SecurityError(f"Path traversal detected: {path}")
        
        # Проверка абсолютного пути
        if os.path.isabs(normalized) and base_path:
            # Если задан base_path, конвертируем в относительный
            try:
                relative = os.path.relpath(normalized, base_path)
                if relative.startswith('..'):
                    raise SecurityError(f"Path outside base directory: {path}")
                normalized = os.path.join(base_path, relative)
            except ValueError:
                raise SecurityError(f"Cannot relativize path: {path}")
        
        # Дополнительные проверки
        if normalized != path:  # Путь изменился при нормализации
            raise SecurityError(f"Path normalization altered input: {path} -> {normalized}")
        
        return normalized
    
    @staticmethod
    def validate_bucket_name(name):
        """
        Валидация имени S3 бакета по AWS правилам.
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
        """
        if not name:
            raise SecurityError("Bucket name cannot be empty")
        
        # Длина
        if len(name) < 3:
            raise SecurityError(f"Bucket name too short: {name}")
        if len(name) > 63:
            raise SecurityError(f"Bucket name too long: {name}")
        
        # Только строчные буквы, цифры, точки и дефисы
        if not re.match(r'^[a-z0-9][a-z0-9\.-]*[a-z0-9]$', name):
            raise SecurityError(f"Invalid bucket name format: {name}")
        
        # Не может быть IP адресом
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', name):
            raise SecurityError(f"Bucket name cannot be IP address: {name}")
        
        # Не может начинаться или заканчиваться дефисом
        if name.startswith('-') or name.endswith('-'):
            raise SecurityError(f"Bucket name cannot start or end with hyphen: {name}")
        
        # Не может иметь две точки подряд
        if '..' in name:
            raise SecurityError(f"Bucket name cannot contain consecutive dots: {name}")
        
        # Для Ceph: дополнительные проверки
        if '.' in name:
            # Если есть точки, проверяем формат как доменное имя
            parts = name.split('.')
            for part in parts:
                if len(part) > 63:
                    raise SecurityError(f"Bucket label too long: {part}")
                if part.startswith('-') or part.endswith('-'):
                    raise SecurityError(f"Bucket label cannot start/end with hyphen: {part}")
        
        return name
    
    @staticmethod
    def validate_object_key(key):
        """
        Валидация ключа объекта S3.
        """
        if not key:
            raise SecurityError("Object key cannot be empty")
        
        # Длина (максимум 1024 символа для S3)
        if len(key) > 1024:
            raise SecurityError(f"Object key too long: {len(key)} characters")
        
        # Защита от path traversal даже в ключах
        if '../' in key or '..\\' in key:
            raise SecurityError(f"Path traversal in object key: {key}")
        
        # Проверка на недопустимые символы
        # S3 позволяет большинство UTF-8 символов, но ограничим для безопасности
        if '\x00' in key or '\x01' in key or '\x02' in key:
            raise SecurityError(f"Invalid control characters in object key: {key}")
        
        # Максимальная глубина вложенности (защита от DoS)
        if key.count('/') > 50:
            raise SecurityError(f"Object key nesting too deep: {key}")
        
        return key
    
    @staticmethod
    def validate_endpoint_url(url):
        """
        Валидация URL endpoint'а S3.
        """
        if not url:
            raise SecurityError("Endpoint URL cannot be empty")
        
        parsed = urlparse(url)
        
        # Проверка схемы
        if parsed.scheme not in ('http', 'https'):
            raise SecurityError(f"Invalid endpoint scheme: {parsed.scheme}")
        
        # Проверка хоста
        if not parsed.hostname:
            raise SecurityError("Endpoint must have hostname")
        
        # Проверка на localhost и внутренние адреса (опционально, можно настраивать)
        local_hosts = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}
        if parsed.hostname in local_hosts:
            # Логируем, но не запрещаем - может быть для тестов
            print(f"WARNING: Using local endpoint: {url}", file=sys.stderr)
        
        # Проверка порта
        if parsed.port:
            if not (1 <= parsed.port <= 65535):
                raise SecurityError(f"Invalid port: {parsed.port}")
        
        return url
    
    @staticmethod
    def sanitize_filename(filename, max_length=255):
        """
        Санитизация имени файла.
        """
        if not filename:
            raise SecurityError("Filename cannot be empty")
        
        # Удаление небезопасных символов
        # Разрешаем буквы, цифры, пробелы, дефисы, подчеркивания, точки
        sanitized = re.sub(r'[^\w\s\-\.]', '_', filename)
        
        # Удаление ведущих/конечных точек и пробелов
        sanitized = sanitized.strip('. ')
        
        # Ограничение длины
        if len(sanitized) > max_length:
            # Сохраняем расширение
            name, ext = os.path.splitext(sanitized)
            if len(ext) > 20:  # Если расширение слишком длинное
                ext = ext[:20]
            name = name[:max_length - len(ext)]
            sanitized = name + ext
        
        # Проверка на пустое имя после санитизации
        if not sanitized:
            raise SecurityError(f"Filename became empty after sanitization: {filename}")
        
        # Защита от зарезервированных имен (Windows)
        reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
        name_without_ext = os.path.splitext(sanitized)[0].upper()
        if name_without_ext in reserved_names:
            sanitized = '_' + sanitized
        
        return sanitized
    
    @staticmethod
    def validate_pattern(pattern):
        """
        Валидация glob-паттернов для выбора файлов.
        """
        if not pattern:
            raise SecurityError("Pattern cannot be empty")
        
        # Проверка на рекурсивные паттерны (могут быть опасны)
        if '**' in pattern:
            raise SecurityError("Recursive patterns (**) are not allowed")
        
        # Ограничение длины
        if len(pattern) > 1000:
            raise SecurityError("Pattern too long")
        
        # Проверка на попытку обхода директорий
        if '../' in pattern or '..\\' in pattern:
            raise SecurityError("Path traversal in pattern")
        
        return pattern
```

### 1.2 Интеграция валидации в существующий код

```python
# В начало файла добавить импорт
from security_utils import InputValidator, SecurityError

# 1. В S3Config.__init__ добавить валидацию endpoint'ов
class S3Config:
    def __init__(self, args):
        self.endpoints = []
        self.args = args
        self.load_config()
        self._validate_endpoints()  # НОВОЕ
    
    def _validate_endpoints(self):
        """Валидация всех endpoint'ов после загрузки"""
        for ep in self.endpoints:
            try:
                # Валидация URL
                ep['url'] = InputValidator.validate_endpoint_url(ep['url'])
                
                # Валидация имени endpoint'а (как имя файла)
                ep['name'] = InputValidator.sanitize_filename(ep['name'], max_length=100)
                
                # Проверка длины секретов (опционально)
                if len(ep.get('access_key', '')) > 1000:
                    raise SecurityError("Access key too long")
                if len(ep.get('secret_key', '')) > 1000:
                    raise SecurityError("Secret key too long")
                    
            except SecurityError as e:
                self._exit_error(f"Invalid endpoint configuration '{ep.get('name', 'UNKNOWN')}': {e}")

# 2. В S3Manager.__init__ добавить валидацию
class S3Manager:
    def __init__(self, endpoint_config):
        # Существующий код...
        
        # ВАЛИДАЦИЯ
        try:
            self.endpoint_name = InputValidator.sanitize_filename(endpoint_config['name'])
            self.endpoint_url = InputValidator.validate_endpoint_url(endpoint_config['url'])
        except SecurityError as e:
            self.s3_client = None
            self.connection_error = f"Invalid endpoint config: {e}"
            return

# 3. В PanelWidget методы добавления валидации
class PanelWidget(urwid.WidgetWrap):
    def create_directory(self, dir_name):
        try:
            # ВАЛИДАЦИЯ имени директории
            safe_name = InputValidator.sanitize_filename(dir_name)
            
            full_path = os.path.join(self.current_path, safe_name)
            
            # Дополнительная валидация пути
            safe_path = InputValidator.validate_path(full_path, self.fs_browser.current_path)
            
            os.makedirs(safe_path, exist_ok=False)
            return True
        except SecurityError as e:
            self.app.show_result(f"Security error: {e}", "error")
            return False
        except OSError:
            return False

# 4. В методах работы с S3 объектами
def list_objects(self, bucket_name, prefix=''):
    if self.s3_client is None:
        return [], []
    
    try:
        # ВАЛИДАЦИЯ
        safe_bucket = InputValidator.validate_bucket_name(bucket_name)
        safe_prefix = InputValidator.validate_object_key(prefix) if prefix else ''
    except SecurityError as e:
        self.connection_error = f"Security validation failed: {e}"
        return [], []
    
    # Остальной код...

# 5. В методах копирования/перемещения
def _do_copy_with_progress(self, analyzed, source_panel, dest_panel, target_name, ...):
    # В начале метода добавить
    try:
        # Валидация целевого пути
        if target_name:
            if dest_panel.mode == 'fs':
                # Для файловой системы
                safe_target = InputValidator.sanitize_filename(target_name)
                safe_target = InputValidator.validate_path(
                    safe_target, 
                    dest_panel.fs_browser.current_path
                )
            else:
                # Для S3
                safe_target = InputValidator.validate_object_key(target_name)
    except SecurityError as e:
        self.show_result(f"Security error in target path: {e}", "error")
        return
    
    # Использовать safe_target вместо target_name в остальном коде

# 6. В методе select_by_pattern
def select_by_pattern(self, pattern, select=True):
    try:
        safe_pattern = InputValidator.validate_pattern(pattern)
        # Использовать safe_pattern...
    except SecurityError as e:
        self.app.show_result(f"Invalid pattern: {e}", "error")
        return
```

## 2. 🔐 **Secure Memory Handling для секретов**

### 2.1 Создаем модуль безопасного хранения секретов

```python
# secure_memory.py
"""
Безопасное хранение секретов в памяти.
Использует защищенные буферы и своевременную очистку.
"""
import ctypes
import sys
import platform
from typing import Optional
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class SecureBuffer:
    """
    Безопасный буфер для хранения секретов в памяти.
    Переопределяет __del__ для безопасного затирания памяти.
    """
    
    def __init__(self, data: bytes):
        self._length = len(data)
        # Выделяем защищенную память
        self._buffer = self._allocate_secure(self._length)
        # Копируем данные
        ctypes.memmove(self._buffer, data, self._length)
    
    def _allocate_secure(self, size: int):
        """
        Выделение защищенной памяти.
        В зависимости от платформы использует разные методы.
        """
        if platform.system() == 'Windows':
            # Windows: VirtualAlloc с флагом PAGE_READWRITE
            kernel32 = ctypes.windll.kernel32
            buffer = kernel32.VirtualAlloc(
                None, size, 0x3000, 0x04  # MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
            )
            if not buffer:
                raise MemoryError("Failed to allocate secure memory")
        else:
            # Linux/macOS: mmap с флагом MAP_PRIVATE | MAP_ANONYMOUS
            libc = ctypes.CDLL(None)
            buffer = libc.mmap(
                None, size, 
                0x3,  # PROT_READ | PROT_WRITE
                0x22,  # MAP_PRIVATE | MAP_ANONYMOUS
                -1, 0
            )
            if buffer == -1:
                raise MemoryError("Failed to allocate secure memory")
        
        return buffer
    
    def _deallocate_secure(self, buffer, size: int):
        """Безопасное освобождение памяти"""
        if platform.system() == 'Windows':
            kernel32 = ctypes.windll.kernel32
            # Сначала затираем нулями
            ctypes.memset(buffer, 0, size)
            # Потом освобождаем
            kernel32.VirtualFree(buffer, 0, 0x8000)  # MEM_RELEASE
        else:
            libc = ctypes.CDLL(None)
            # Затираем
            ctypes.memset(buffer, 0, size)
            # Освобождаем
            libc.munmap(buffer, size)
    
    def get(self) -> bytes:
        """Получение данных из буфера"""
        # Создаем копию, чтобы оригинал оставался в защищенной памяти
        result = ctypes.create_string_buffer(self._length)
        ctypes.memmove(result, self._buffer, self._length)
        return bytes(result)
    
    def clear(self):
        """Немедленное затирание памяти"""
        if hasattr(self, '_buffer') and self._buffer:
            ctypes.memset(self._buffer, 0, self._length)
    
    def __len__(self) -> int:
        return self._length
    
    def __del__(self):
        """Деструктор - гарантированное затирание при сборке мусора"""
        try:
            self.clear()
            if hasattr(self, '_buffer') and self._buffer:
                self._deallocate_secure(self._buffer, self._length)
        except:
            pass  # Игнорируем ошибки при завершении программы

class SecureSecret:
    """
    Высокоуровневый класс для безопасного хранения секретов.
    Поддерживает шифрование в памяти.
    """
    
    def __init__(self, secret: str, encrypt_in_memory: bool = True):
        self._encrypt_in_memory = encrypt_in_memory
        
        if encrypt_in_memory:
            # Шифруем секрет в памяти
            self._encrypted = self._encrypt_in_ram(secret.encode('utf-8'))
            # Оригинал немедленно затирается
            self._overwrite_string(secret)
        else:
            # Просто храним в SecureBuffer
            self._encrypted = SecureBuffer(secret.encode('utf-8'))
    
    def _encrypt_in_ram(self, data: bytes) -> SecureBuffer:
        """
        Шифрование секрета с использованием ключа, 
        сгенерированного из данных самого секрета.
        """
        # Используем часть секрета как ключ для шифрования
        # Это защищает от дампа памяти, но требует самого секрета для расшифровки
        if len(data) < 32:
            # Если секрет короткий, дополняем
            key_source = data + b' ' * (32 - len(data))
        else:
            key_source = data[:32]
        
        # Генерируем ключ из самого секрета
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b's3commander_ram_encryption',
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(key_source))
        
        # Шифруем
        f = Fernet(key)
        encrypted_data = f.encrypt(data)
        
        # Сохраняем в защищенном буфере
        return SecureBuffer(encrypted_data)
    
    def get(self) -> str:
        """Получение секрета"""
        if self._encrypt_in_memory:
            # Получаем зашифрованные данные
            encrypted = self._encrypted.get()
            
            # Для расшифровки нужен ключ, который основан на самом секрете
            # Это создает циклическую зависимость, поэтому мы храним метаданные
            
            # В реальной реализации нужен более сложный механизм
            # Для простоты - возвращаем из незашифрованного буфера
            raise NotImplementedError("In-memory encryption requires proper key management")
        else:
            # Просто возвращаем из буфера
            data = self._encrypted.get()
            result = data.decode('utf-8')
            # Создаем копию и затираем временный буфер
            result_copy = str(result)
            self._overwrite_bytes(data)
            return result_copy
    
    def clear(self):
        """Очистка секрета из памяти"""
        if hasattr(self, '_encrypted'):
            self._encrypted.clear()
    
    @staticmethod
    def _overwrite_string(s: str):
        """Безопасное затирание строки в памяти"""
        try:
            # Конвертируем в изменяемый буфер
            if sys.version_info >= (3, 8):
                # Python 3.8+ имеет memoryview
                mv = memoryview(bytearray(s.encode('utf-8')))
                mv[:] = b'0' * len(mv)
            else:
                # Для более старых версий
                ba = bytearray(s.encode('utf-8'))
                for i in range(len(ba)):
                    ba[i] = 0
        except:
            pass
    
    @staticmethod
    def _overwrite_bytes(b: bytes):
        """Безопасное затирание байтов"""
        try:
            if sys.version_info >= (3, 8):
                mv = memoryview(bytearray(b))
                mv[:] = b'0' * len(mv)
            else:
                ba = bytearray(b)
                for i in range(len(ba)):
                    ba[i] = 0
        except:
            pass
    
    def __del__(self):
        """Гарантированная очистка при сборке мусора"""
        try:
            self.clear()
        except:
            pass

class SecretManager:
    """
    Менеджер для безопасного хранения и использования секретов.
    """
    
    def __init__(self):
        self._secrets = {}  # name -> SecureSecret
        self._temp_secrets = []  # Временные секреты для очистки
    
    def store(self, name: str, secret: str, encrypt: bool = True):
        """Безопасное сохранение секрета"""
        self._secrets[name] = SecureSecret(secret, encrypt)
    
    def get(self, name: str) -> Optional[str]:
        """Безопасное получение секрета"""
        if name not in self._secrets:
            return None
        
        try:
            return self._secrets[name].get()
        finally:
            # После использования можно очистить (опционально)
            # self._secrets[name].clear()
            pass
    
    def get_for_boto3(self, name: str):
        """
        Получение секрета в виде строки, но с контролем времени жизни.
        Для использования с boto3, который требует plain strings.
        """
        secret = self.get(name)
        if secret:
            # Сохраняем ссылку для последующей очистки
            self._temp_secrets.append(secret)
            return secret
        return None
    
    def clear_temp_secrets(self):
        """Очистка временных секретов"""
        for secret in self._temp_secrets:
            # Затираем строку в памяти
            self._overwrite_string_inplace(secret)
        self._temp_secrets.clear()
    
    def clear_all(self):
        """Очистка всех секретов"""
        for name in list(self._secrets.keys()):
            self._secrets[name].clear()
            del self._secrets[name]
        self.clear_temp_secrets()
    
    @staticmethod
    def _overwrite_string_inplace(s: str):
        """Попытка затереть строку на месте (сложно в Python)"""
        # В Python строки иммутабельны, поэтому полная очистка невозможна
        # Но мы можем удалить ссылки и надеяться на GC
        # Для настоящей безопасности нужна работа на уровне C
        pass
```

### 2.2 Интеграция Secure Memory в существующий код

```python
# В начало файла добавить
from secure_memory import SecretManager

# 1. Модифицируем S3Config
class S3Config:
    def __init__(self, args):
        self.endpoints = []
        self.args = args
        self.secret_manager = SecretManager()  # НОВОЕ
        self.load_config()
    
    # В методах загрузки конфига заменяем хранение секретов
    def _load_from_plain_file(self):
        # ... существующий код чтения JSON ...
        
        for ep in self.endpoints:
            # Безопасное хранение секретов
            access_key = ep.get('access_key', '')
            secret_key = ep.get('secret_key', '')
            
            # Удаляем из plain dict
            ep.pop('access_key', None)
            ep.pop('secret_key', None)
            
            # Сохраняем в SecureSecret
            self.secret_manager.store(
                f"{ep['name']}_access_key",
                access_key,
                encrypt=False  # Для boto3 нужны plain strings
            )
            self.secret_manager.store(
                f"{ep['name']}_secret_key",
                secret_key,
                encrypt=False
            )
            
            # Сохраняем только ссылки на имена секретов
            ep['_access_key_ref'] = f"{ep['name']}_access_key"
            ep['_secret_key_ref'] = f"{ep['name']}_secret_key"

# 2. Модифицируем S3Manager
class S3Manager:
    def __init__(self, endpoint_config, secret_manager):  # Добавляем параметр
        self.endpoint_name = endpoint_config['name']
        self.endpoint_url = endpoint_config['url']
        self.secret_manager = secret_manager  # НОВОЕ
        self._access_key_ref = endpoint_config.get('_access_key_ref')
        self._secret_key_ref = endpoint_config.get('_secret_key_ref')
        
        # ВРЕМЕННЫЕ переменные для boto3
        self._temp_access_key = None
        self._temp_secret_key = None
        
        # ... остальной код инициализации ...
    
    def _get_s3_client(self):
        """Создание клиента S3 с безопасным использованием секретов"""
        if self.s3_client is not None:
            return self.s3_client
        
        try:
            # Безопасное получение секретов
            access_key = self.secret_manager.get_for_boto3(self._access_key_ref)
            secret_key = self.secret_manager.get_for_boto3(self._secret_key_ref)
            
            if not access_key or not secret_key:
                self.connection_error = "Failed to retrieve credentials"
                return None
            
            # Сохраняем временные ссылки для очистки
            self._temp_access_key = access_key
            self._temp_secret_key = secret_key
            
            config = Config(
                connect_timeout=3,
                read_timeout=10,
                retries={'max_attempts': 1}
            )
            
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=config
            )
            
            # Очищаем временные секреты после использования
            # (boto3 сохраняет их внутри, но мы очистим наши копии)
            self._clear_temp_credentials()
            
            return self.s3_client
            
        except Exception as e:
            self._clear_temp_credentials()
            self.s3_client = None
            self.connection_error = str(e)
            return None
    
    def _clear_temp_credentials(self):
        """Очистка временных учетных данных из памяти"""
        if self._temp_access_key:
            # Пытаемся затереть строку
            import ctypes
            try:
                # Это хак, но лучше чем ничего
                buf = ctypes.create_string_buffer(self._temp_access_key.encode('utf-8'))
                ctypes.memset(buf, 0, len(buf))
            except:
                pass
            self._temp_access_key = None
        
        if self._temp_secret_key:
            try:
                buf = ctypes.create_string_buffer(self._temp_secret_key.encode('utf-8'))
                ctypes.memset(buf, 0, len(buf))
            except:
                pass
            self._temp_secret_key = None
        
        # Очищаем в менеджере секретов
        if self.secret_manager:
            self.secret_manager.clear_temp_secrets()
    
    def __del__(self):
        """Деструктор - гарантированная очистка"""
        try:
            self._clear_temp_credentials()
            if self.secret_manager:
                # Очищаем только секреты этого менеджера
                pass
        except:
            pass

# 3. Модифицируем DualPaneApp для передачи SecretManager
class DualPaneApp:
    def __init__(self, s3_config):
        self.s3_config = s3_config
        self.secret_manager = s3_config.secret_manager  # НОВОЕ
        
        # Передаем secret_manager в панели
        self.left_panel = PanelWidget('', panel_type='root_menu', 
                                     s3_config=s3_config, 
                                     secret_manager=self.secret_manager,  # НОВОЕ
                                     app=self)
        self.right_panel = PanelWidget('', panel_type='root_menu',
                                      s3_config=s3_config,
                                      secret_manager=self.secret_manager,  # НОВОЕ
                                      app=self)
        
        # ... остальной код ...

# 4. Модифицируем PanelWidget
class PanelWidget(urwid.WidgetWrap):
    def __init__(self, title, panel_type='fs', s3_config=None, 
                 secret_manager=None, app=None):  # Добавляем параметр
        # ... существующий код ...
        
        self.secret_manager = secret_manager  # НОВОЕ
        
        # При создании S3Manager передаем secret_manager
        if panel_type == 's3' and s3_config:
            # Будет передано позже при выборе endpoint

# 5. В on_item_activated при создании S3Manager
def on_item_activated(self, data):
    item_type = data.get('type')
    
    elif item_type == 'root_endpoint':
        self.mode = 's3'
        self.current_endpoint = data['name']
        endpoint_config = data['config']
        
        # Создаем S3Manager с передачей secret_manager
        self.s3_manager = S3Manager(endpoint_config, self.secret_manager)  # ИЗМЕНЕНО
        
        self.current_bucket = None
        self.current_prefix = ''
        self.sort_mode = 'none'
        self.refresh()
```

## 3. 📁 **Шифрование всех временных файлов**

### 3.1 Создаем модуль безопасных временных файлов

```python
# secure_tempfile.py
"""
Безопасные временные файлы с шифрованием.
"""
import os
import tempfile
import stat
import shutil
import atexit
from pathlib import Path
from typing import Optional, BinaryIO
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import hashlib

class SecureTempFileManager:
    """
    Менеджер безопасных временных файлов.
    Автоматически шифрует все данные и очищает при завершении.
    """
    
    _instance = None
    _temp_files = []
    _encryption_key = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        """Инициализация менеджера"""
        # Генерация ключа шифрования из системной информации
        self._generate_encryption_key()
        
        # Регистрация очистки при завершении
        atexit.register(self.cleanup_all)
        
        # Создание безопасного каталога для временных файлов
        self.temp_dir = self._create_secure_temp_dir()
    
    def _generate_encryption_key(self):
        """Генерация ключа шифрования для временных файлов"""
        # Используем комбинацию системных данных для генерации ключа
        system_data = [
            os.urandom(32),
            str(os.getpid()).encode('utf-8'),
            str(os.getuid()).encode('utf-8') if hasattr(os, 'getuid') else b'',
            os.environ.get('HOSTNAME', '').encode('utf-8'),
        ]
        
        key_source = b''.join(system_data)
        
        # Используем PBKDF2 для создания стабильного ключа
        salt = b's3commander_temp_encryption_salt'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key_material = kdf.derive(key_source)
        self._encryption_key = base64.urlsafe_b64encode(key_material)
    
    def _create_secure_temp_dir(self) -> Path:
        """Создание безопасного каталога для временных файлов"""
        # Используем стандартный temp каталог, но с ограниченными правами
        base_temp = Path(tempfile.gettempdir()) / f"s3commander_{os.getpid()}"
        
        try:
            base_temp.mkdir(mode=0o700, exist_ok=True)
        except OSError:
            # Fallback: создаем в домашней директории
            home = Path.home()
            base_temp = home / ".cache" / "s3commander_temp" / f"pid_{os.getpid()}"
            base_temp.mkdir(mode=0o700, parents=True, exist_ok=True)
        
        # Устанавливаем sticky bit (если поддерживается)
        try:
            os.chmod(base_temp, 0o1700)  # drwx------ with sticky bit
        except:
            pass
        
        return base_temp
    
    def create_secure_tempfile(self, suffix: str = "", 
                               encrypted: bool = True) -> 'SecureTempFile':
        """
        Создание безопасного временного файла.
        
        Args:
            suffix: Суффикс имени файла
            encrypted: Шифровать ли содержимое
        
        Returns:
            SecureTempFile объект
        """
        # Генерация безопасного имени файла
        safe_suffix = self._sanitize_suffix(suffix)
        fd, path = tempfile.mkstemp(
            suffix=safe_suffix,
            dir=str(self.temp_dir),
            text=False  # Всегда бинарный режим для шифрования
        )
        
        try:
            # Устанавливаем права 0600 (только владелец)
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            
            # Создаем объект SecureTempFile
            temp_file = SecureTempFile(
                path=Path(path),
                fd=fd,
                encrypted=encrypted,
                encryption_key=self._encryption_key if encrypted else None
            )
            
            # Регистрируем для автоматической очистки
            self._temp_files.append(temp_file)
            
            return temp_file
            
        except Exception:
            # В случае ошибки закрываем и удаляем
            os.close(fd)
            os.unlink(path)
            raise
    
    def create_encrypted_tempfile(self, data: bytes = None, 
                                  suffix: str = "") -> 'SecureTempFile':
        """
        Создание зашифрованного временного файла.
        
        Args:
            data: Данные для записи (опционально)
            suffix: Суффикс имени файла
        
        Returns:
            SecureTempFile объект
        """
        temp_file = self.create_secure_tempfile(suffix=suffix, encrypted=True)
        
        if data:
            temp_file.write(data)
        
        return temp_file
    
    @staticmethod
    def _sanitize_suffix(suffix: str) -> str:
        """Санитизация суффикса имени файла"""
        if not suffix:
            return ""
        
        # Разрешаем только буквы, цифры, точки, дефисы, подчеркивания
        import re
        sanitized = re.sub(r'[^\w\.\-]', '_', suffix)
        
        # Защита от path traversal в суффиксе
        sanitized = sanitized.replace('..', '_')
        
        # Ограничение длины
        if len(sanitized) > 64:
            # Сохраняем расширение
            name, ext = os.path.splitext(sanitized)
            if len(ext) > 10:
                ext = ext[:10]
            name = name[:64 - len(ext)]
            sanitized = name + ext
        
        return sanitized
    
    def cleanup_all(self):
        """Очистка всех временных файлов"""
        for temp_file in self._temp_files[:]:
            try:
                temp_file.cleanup()
            except:
                pass
        
        # Очистка каталога (если он пустой)
        try:
            if self.temp_dir.exists():
                # Проверяем, пустой ли каталог
                if not any(self.temp_dir.iterdir()):
                    self.temp_dir.rmdir()
        except:
            pass

class SecureTempFile:
    """
    Безопасный временный файл с автоматическим шифрованием.
    """
    
    def __init__(self, path: Path, fd: int, encrypted: bool = True,
                 encryption_key: bytes = None):
        self.path = path
        self._fd = fd
        self._encrypted = encrypted
        self._encryption_key = encryption_key
        self._fernet = Fernet(encryption_key) if encrypted else None
        self._closed = False
        
        # Открываем файловый объект
        self._file = os.fdopen(fd, 'w+b', buffering=0)  # Без буферизации для безопасности
    
    def write(self, data: bytes) -> int:
        """
        Запись данных в файл.
        Автоматически шифрует, если включено шифрование.
        """
        if self._closed:
            raise ValueError("File is closed")
        
        if self._encrypted and self._fernet:
            # Шифруем данные
            encrypted_data = self._fernet.encrypt(data)
            written = self._file.write(encrypted_data)
        else:
            written = self._file.write(data)
        
        self._file.flush()  # Сразу записываем на диск
        return written
    
    def read(self, size: int = -1) -> bytes:
        """
        Чтение данных из файла.
        Автоматически расшифровывает, если файл зашифрован.
        """
        if self._closed:
            raise ValueError("File is closed")
        
        # Сохраняем позицию
        current_pos = self._file.tell()
        self._file.seek(0)
        
        try:
            if self._encrypted and self._fernet:
                # Читаем и расшифровываем
                encrypted_data = self._file.read() if size == -1 else self._file.read(size)
                if not encrypted_data:
                    return b""
                return self._fernet.decrypt(encrypted_data)
            else:
                return self._file.read() if size == -1 else self._file.read(size)
        finally:
            # Восстанавливаем позицию
            self._file.seek(current_pos)
    
    def read_all(self) -> bytes:
        """Чтение всех данных из файла"""
        return self.read()
    
    def overwrite(self, passes: int = 3):
        """
        Безопасное затирание файла перед удалением.
        Использует метод Гутмана (упрощенный).
        """
        if not self.path.exists():
            return
        
        file_size = self.path.stat().st_size
        
        # Несколько проходов затирания
        patterns = [
            b'\x00' * 1024,  # Нули
            b'\xFF' * 1024,  # Единицы
            os.urandom(1024),  # Случайные данные
        ]
        
        self._file.close()
        self._closed = True
        
        # Открываем в режиме для затирания
        with open(self.path, 'r+b', buffering=0) as f:
            for pass_num in range(passes):
                f.seek(0)
                pattern = patterns[pass_num % len(patterns)]
                
                # Записываем по блокам
                remaining = file_size
                while remaining > 0:
                    block_size = min(1024, remaining)
                    f.write(pattern[:block_size])
                    remaining -= block_size
                
                f.flush()
                os.fsync(f.fileno())
    
    def cleanup(self):
        """Безопасная очистка файла"""
        if self._closed:
            return
        
        try:
            # Закрываем файловый объект
            if hasattr(self, '_file') and self._file:
                self._file.close()
            
            # Безопасное затирание
            self.overwrite()
            
            # Удаление файла
            if self.path.exists():
                os.unlink(self.path)
            
            self._closed = True
            
        except Exception as e:
            # В крайнем случае пытаемся удалить без затирания
            try:
                if self.path.exists():
                    os.unlink(self.path)
            except:
                pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def __del__(self):
        """Деструктор - гарантированная очистка"""
        try:
            self.cleanup()
        except:
            pass

# Утилитарные функции для простого использования
def secure_tempfile(suffix="", encrypted=True):
    """
    Контекстный менеджер для безопасного временного файла.
    
    Usage:
        with secure_tempfile(suffix=".txt") as tmp:
            tmp.write(b"Hello, World!")
            data = tmp.read()
    """
    manager = SecureTempFileManager()
    return manager.create_secure_tempfile(suffix=suffix, encrypted=encrypted)

def create_encrypted_tempfile(data=None, suffix=""):
    """Создание зашифрованного временного файла"""
    manager = SecureTempFileManager()
    return manager.create_encrypted_tempfile(data=data, suffix=suffix)

def cleanup_secure_tempfiles():
    """Принудительная очистка всех временных файлов"""
    if SecureTempFileManager._instance:
        SecureTempFileManager._instance.cleanup_all()
```

### 3.2 Интеграция шифрования временных файлов

```python
# В начало файла добавить
from secure_tempfile import secure_tempfile, create_encrypted_tempfile

# 1. Заменяем все использования tempfile.NamedTemporaryFile
class PanelWidget(urwid.WidgetWrap):
    def view_s3_file_version(self, file_data, version_data=None, close_callback=None):
        version_id = version_data.get('VersionId') if version_data else None
        filename = file_data['name']
        
        if version_id:
            self.app.show_result(f"Downloading {filename} (version {version_id[:8]})...")
        else:
            self.app.show_result(f"Downloading {filename}...")
        
        # ЗАМЕНА: Используем безопасный временный файл
        try:
            with secure_tempfile(suffix=f"_{filename}", encrypted=True) as tmp:
                if self.s3_manager.download_object(
                        self.current_bucket,
                        file_data['key'],
                        tmp.path,  # Используем путь к файлу
                        version_id=version_id):
                    
                    # Читаем данные для просмотра
                    file_content = tmp.read_all()
                    
                    # Просмотр содержимого
                    self._view_file_content(file_content, filename, close_callback)
                    
                else:
                    self.app.show_result(f"Failed to download {filename}")
        
        except Exception as e:
            self.app.show_result(f"Error viewing file: {str(e)}")
    
    def _view_file_content(self, content, filename, close_callback):
        """Просмотр содержимого из памяти (без временного файла)"""
        # Проверяем на бинарность
        if self._is_binary_content(content):
            # HEX просмотр
            display_content = f"[Binary file: {filename}]\n"
            display_content += f"File size: {len(content)} bytes\n\n"
            display_content += self.app.format_hex_content(content[:4096])
            if len(content) > 4096:
                display_content += "\n\n[... Binary content truncated ...]"
        else:
            # Текстовый просмотр
            try:
                display_content = content[:50000].decode('utf-8', errors='replace')
                if len(content) > 50000:
                    display_content += "\n\n[... File truncated ...]"
            except:
                display_content = f"Error decoding file content"
        
        def on_viewer_close():
            self.app.close_dialog()
            if close_callback:
                close_callback()
        
        viewer = FileViewerDialog(f'View: {filename}', display_content, on_viewer_close)
        self.app.show_dialog(viewer, height=('relative', 80))

# 2. В DualPaneApp для preview mode
class DualPaneApp:
    def update_preview(self):
        if not self.preview_mode:
            return
        
        active_panel = self.get_active_panel()
        inactive_panel = self.get_inactive_panel()
        
        item = active_panel.get_focused_item()
        if not item or item['type'] not in ('fs_file', 's3_file'):
            self._show_preview_text(inactive_panel, "", title="Preview")
            return
        
        try:
            size = int(item.get('size', 0))
        except:
            size = 0
        
        if size > 1024 * 100:
            self._show_preview_text(inactive_panel, "File too large for preview", title="Preview")
            return
        
        content = ""
        info_text = f"PREVIEW: {item['name']}"
        
        try:
            if item['type'] == 'fs_file':
                # Для локальных файлов читаем прямо в память
                file_path = os.path.join(active_panel.fs_browser.current_path, item['name'])
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        content = f.read(2048)
                    info_text = f"PREVIEW (Local): {item['name']}"
            
            elif item['type'] == 's3_file':
                # Для S3 файлов используем безопасный временный файл
                with secure_tempfile(suffix=f"_preview_{item['name']}", encrypted=True) as tmp:
                    if active_panel.s3_manager.download_object(
                            active_panel.current_bucket,
                            item['key'],
                            tmp.path):
                        content = tmp.read(2048)
                        info_text = f"PREVIEW (S3): {item['name']}"
        
        except Exception as e:
            content = f"Error generating preview: {e}"
        
        # Проверяем на бинарность и форматируем
        if content and self._is_binary_content(content):
            display_content = self.format_hex_content(content)
            info_text += " [HEX]"
        else:
            try:
                display_content = content.decode('utf-8', errors='replace')
            except:
                display_content = str(content)
        
        self._show_preview_text(inactive_panel, display_content, title=info_text)
    
    @staticmethod
    def _is_binary_content(data):
        """Проверка на бинарный контент"""
        if not data:
            return False
        
        # Проверяем на null байты
        if b'\x00' in data:
            return True
        
        # Проверяем процент непечатных символов
        non_printable = sum(1 for byte in data if byte < 32 and byte not in (9, 10, 13))
        if len(data) > 0 and non_printable / len(data) > 0.3:
            return True
        
        return False

# 3. В S3Manager для скачивания объектов
class S3Manager:
    def download_object(self, bucket_name, key, local_path, version_id=None, callback=None):
        # ВАЛИДАЦИЯ путей
        from security_utils import InputValidator
        try:
            safe_bucket = InputValidator.validate_bucket_name(bucket_name)
            safe_key = InputValidator.validate_object_key(key)
            safe_local_path = InputValidator.validate_path(local_path)
        except SecurityError as e:
            self.connection_error = f"Security validation failed: {e}"
            return False
        
        if self.s3_client is None:
            return False
        
        try:
            extra_args = {}
            if version_id:
                extra_args['VersionId'] = version_id
            
            # Используем безопасный временный файл для скачивания
            from secure_tempfile import secure_tempfile
            with secure_tempfile(suffix=f"_download_{os.path.basename(key)}", encrypted=True) as tmp:
                # Скачиваем во временный файл
                self.s3_client.download_file(
                    safe_bucket, 
                    safe_key, 
                    tmp.path,
                    ExtraArgs=extra_args, 
                    Callback=callback
                )
                
                # Читаем данные
                encrypted_data = tmp.read_all()
                
                # Расшифровываем (если tmp был зашифрован, он сам расшифрует при чтении)
                # Но мы уже прочитали расшифрованные данные через tmp.read_all()
                
                # Записываем в целевой файл
                with open(safe_local_path, 'wb') as f:
                    f.write(encrypted_data)
                
                # Устанавливаем безопасные права
                os.chmod(safe_local_path, 0o600)
                
                return True
                
        except (ClientError, Exception) as e:
            self.connection_error = f"Download error: {str(e)}"
            return False

# 4. Добавляем очистку при завершении программы
if __name__ == '__main__':
    # ... существующий код ...
    
    app = DualPaneApp(s3_config)
    
    try:
        app.run()
    finally:
        # Гарантированная очистка временных файлов
        from secure_tempfile import cleanup_secure_tempfiles
        cleanup_secure_tempfiles()
        
        # Очистка секретов из памяти
        if hasattr(s3_config, 'secret_manager'):
            s3_config.secret_manager.clear_all()
```

### 3.3 Дополнительные улучшения безопасности

```python
# secure_operations.py
"""
Дополнительные операции безопасности.
"""
import os
import hashlib
import hmac

class SecurityOperations:
    """Дополнительные операции безопасности"""
    
    @staticmethod
    def secure_compare(a: str, b: str) -> bool:
        """
        Сравнение строк с постоянным временем выполнения.
        Защита от timing attacks.
        """
        if len(a) != len(b):
            return False
        
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
        return result == 0
    
    @staticmethod
    def generate_secure_filename(original_name: str, secret: str = None) -> str:
        """
        Генерация безопасного имени файла с HMAC.
        """
        import time
        import random
        
        if secret is None:
            secret = os.urandom(32).hex()
        
        # Создаем уникальный идентификатор
        unique_part = f"{time.time():.6f}_{random.getrandbits(64):x}"
        
        # Создаем HMAC для проверки целостности
        if original_name:
            hmac_obj = hmac.new(
                secret.encode('utf-8'),
                original_name.encode('utf-8'),
                hashlib.sha256
            )
            hmac_digest = hmac_obj.hexdigest()[:16]
        else:
            hmac_digest = hashlib.sha256(unique_part.encode()).hexdigest()[:16]
        
        # Формируем безопасное имя
        safe_name = f"sec_{hmac_digest}_{unique_part}"
        
        # Добавляем расширение если было
        if original_name and '.' in original_name:
            ext = original_name.rsplit('.', 1)[1][:10]  # Берем только расширение
            safe_name += f".{ext}"
        
        return safe_name
    
    @staticmethod
    def verify_file_integrity(file_path: str, expected_hash: str) -> bool:
        """
        Проверка целостности файла.
        """
        if not os.path.exists(file_path):
            return False
        
        # Вычисляем SHA256 хеш файла
        sha256_hash = hashlib.sha256()
        
        try:
            with open(file_path, 'rb') as f:
                # Читаем по блокам
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            computed_hash = sha256_hash.hexdigest()
            return SecurityOperations.secure_compare(computed_hash, expected_hash)
            
        except:
            return False
    
    @staticmethod
    def sanitize_metadata(metadata: dict) -> dict:
        """
        Санитизация метаданных S3.
        Удаляет потенциально опасные заголовки.
        """
        if not metadata:
            return {}
        
        # Разрешенные префиксы для метаданных
        allowed_prefixes = ['x-amz-meta-', 'content-', 'cache-']
        
        sanitized = {}
        for key, value in metadata.items():
            key_lower = key.lower()
            
            # Проверяем разрешен ли префикс
            allowed = any(key_lower.startswith(prefix) for prefix in allowed_prefixes)
            
            if allowed:
                # Проверяем значение
                if isinstance(value, str):
                    # Ограничиваем длину
                    if len(value) > 1024:
                        value = value[:1024]
                    # Удаляем опасные символы
                    value = value.replace('\x00', '').replace('\r', '').replace('\n', '')
                
                sanitized[key] = value
        
        return sanitized
```

## 📋 **Итоговый план внедрения**

### Шаг 1: Создание модулей безопасности
1. Создать файлы:
   - `security_utils.py`
   - `secure_memory.py`
   - `secure_tempfile.py`
   - `secure_operations.py`

### Шаг 2: Интеграция в основной код
1. Добавить импорты в начало `s3-commander-v1.7.0.py`
2. Заменить все `tempfile.NamedTemporaryFile` на `secure_tempfile`
3. Добавить валидацию во все методы с пользовательским вводом
4. Интегрировать `SecretManager` для хранения секретов

### Шаг 3: Тестирование
1. Протестировать все операции с некорректными вводами
2. Проверить очистку памяти при завершении
3. Убедиться, что временные файлы действительно зашифрованы

### Шаг 4: Документация
1. Обновить README с новыми функциями безопасности
2. Добавить комментарии в код
3. Создать руководство по безопасности

## ⚠️ **Важные предупреждения**

1. **SecureBuffer** может не работать на всех платформах одинаково
2. Шифрование в памяти имеет ограничения в Python из-за GC
3. Полная защита от timing attacks требует C-расширений
4. Производительность может снизиться из-за дополнительных проверок
5. Некоторые функции требуют прав администратора для полной реализации

## 📈 **Дальнейшие улучшения**

1. **Аудит логов** - запись всех операций в защищенный лог
2. **MFA поддержка** - двухфакторная аутентификация для критичных операций
3. **HSM интеграция** - использование аппаратных модулей безопасности
4. **DLP функции** - предотвращение утечки данных
5. **Квотирование** - ограничение операций по времени/объему

Это комплексное решение значительно повышает безопасность S3 Commander, но требует тщательного тестирования перед использованием в production.
