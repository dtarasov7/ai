#!/usr/bin/env python3
"""
RadosGW Log Filter - скрипт для фильтрации логов из сокета RadosGW
"""

import os
import sys
import json
import socket
import time
import re
import argparse
import logging
from logging.handlers import RotatingFileHandler
from systemd import journal
import signal

# Настройка логирования самого скрипта
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[RotatingFileHandler('/var/log/ceph/rgw_filter.log', maxBytes=10485760, backupCount=5)]
)
logger = logging.getLogger('rgw_filter')

class RGWLogFilter:
    def __init__(self, socket_path, output_path, filter_rules):
        self.socket_path = socket_path
        self.output_path = output_path
        self.filter_rules = filter_rules
        self.running = False
        self.sock = None
        self.setup_output_logging()
        
    def setup_output_logging(self):
        """Настройка логирования для отфильтрованных сообщений"""
        self.rgw_logger = logging.getLogger('rgw_filtered')
        self.rgw_logger.setLevel(logging.INFO)
        
        # Создаем каталог для логов, если он не существует
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # Настраиваем ротацию логов
        handler = RotatingFileHandler(
            self.output_path,
            maxBytes=50*1024*1024,  # 50 МБ
            backupCount=10
        )
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        self.rgw_logger.addHandler(handler)
        
    def should_filter(self, log_entry):
        """Определяет, должен ли лог быть отфильтрован"""
        try:
            # Если это проверка доступности от HAProxy
            if isinstance(log_entry, dict):
                # Фильтрация GET запросов к корню от HAProxy
                if log_entry.get('method') == 'GET' and log_entry.get('uri') == '/' and 'user_agent' in log_entry:
                    user_agent = log_entry.get('user_agent', '')
                    if 'HAProxy' in user_agent:
                        return True
                
                # Проверка по настроенным правилам фильтрации
                for rule in self.filter_rules:
                    field, pattern = rule
                    if field in log_entry and re.search(pattern, str(log_entry[field])):
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Ошибка при обработке фильтрации: {e}")
            return False
            
    def connect_socket(self):
        """Подключение к сокету RadosGW"""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        retry_count = 0
        max_retries = 5
        
        while retry_count < max_retries:
            try:
                self.sock.connect(self.socket_path)
                logger.info(f"Подключено к сокету: {self.socket_path}")
                return True
            except socket.error as e:
                retry_count += 1
                logger.warning(f"Попытка {retry_count}/{max_retries}: Не удалось подключиться к сокету: {e}")
                time.sleep(5)
                
        logger.error(f"Не удалось подключиться к сокету после {max_retries} попыток")
        return False
        
    def process_logs(self):
        """Чтение логов из сокета и их фильтрация"""
        if not self.connect_socket():
            return False
            
        self.running = True
        buffer = b""
        
        try:
            while self.running:
                data = self.sock.recv(4096)
                if not data:
                    logger.warning("Соединение с сокетом закрыто")
                    time.sleep(1)
                    if not self.connect_socket():
                        continue
                
                buffer += data
                lines = buffer.split(b'\n')
                buffer = lines.pop()  # Оставляем неполную последнюю строку в буфере
                
                for line in lines:
                    if not line:
                        continue
                    
                    try:
                        log_entry = json.loads(line)
                        if not self.should_filter(log_entry):
                            self.rgw_logger.info(line.decode('utf-8', errors='ignore'))
                    except json.JSONDecodeError:
                        # Если не удалось разобрать JSON, записываем строку как есть
                        logger.warning(f"Не удалось разобрать JSON: {line}")
                        if not self.should_filter({"raw": line.decode('utf-8', errors='ignore')}):
                            self.rgw_logger.info(line.decode('utf-8', errors='ignore'))
                    except Exception as e:
                        logger.error(f"Ошибка при обработке лога: {e}")
                
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки")
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Закрытие соединения с сокетом"""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.running = False
        logger.info("Соединение с сокетом закрыто")
        
    def stop(self):
        """Остановка процесса фильтрации"""
        self.running = False
        logger.info("Остановка сервиса фильтрации логов")


def create_systemd_service(args):
    """Создание systemd сервиса для автозапуска фильтра логов"""
    service_content = f"""[Unit]
Description=RadosGW Log Filter Service
After=ceph-radosgw@rgw.target
Requires=ceph-radosgw@rgw.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {os.path.abspath(__file__)} --socket {args.socket} --output {args.output}
Restart=on-failure
RestartSec=10
User=ceph
Group=ceph

[Install]
WantedBy=multi-user.target
"""
    
    service_path = "/etc/systemd/system/rgw-log-filter.service"
    try:
        with open(service_path, 'w') as f:
            f.write(service_content)
        
        print(f"Файл сервиса создан: {service_path}")
        print("Для активации сервиса выполните:")
        print("sudo systemctl daemon-reload")
        print("sudo systemctl enable rgw-log-filter")
        print("sudo systemctl start rgw-log-filter")
        return True
    except Exception as e:
        print(f"Ошибка при создании файла сервиса: {e}")
        return False


def signal_handler(sig, frame):
    """Обработчик сигналов для корректного завершения"""
    global log_filter
    if log_filter:
        log_filter.stop()
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RadosGW Log Filter")
    parser.add_argument('--socket', default='/var/run/ceph/rgw_ops.sock', help='Путь к сокету RadosGW')
    parser.add_argument('--output', default='/var/log/ceph/rgw_filtered.log', help='Путь к выходному файлу логов')
    parser.add_argument('--create-service', action='store_true', help='Создать systemd сервис')
    
    args = parser.parse_args()
    
    if args.create_service:
        create_systemd_service(args)
        sys.exit(0)
    
    # Правила фильтрации: (поле, регулярное выражение)
    filter_rules = [
        ('method', '^GET$'),
        ('uri', '^/$'),
        ('user_agent', 'HAProxy|health[ _]check|monitoring'),
        ('status', '^(200|204|401|403|404)$'),  # Фильтровать частые обычные коды ответа
    ]
    
    log_filter = RGWLogFilter(args.socket, args.output, filter_rules)
    
    # Настройка обработчиков сигналов для корректного завершения
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Запуск фильтра логов RadosGW")
    log_filter.process_logs()
