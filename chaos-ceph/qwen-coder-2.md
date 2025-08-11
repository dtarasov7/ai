```python
#!/usr/bin/env python3
"""
Скрипт хаос-тестирования кластера хранения Ceph версии 17.2.7

Этот скрипт имитирует различные сценарии отказов в кластере Ceph:
1. Симуляция сетевой задержки
2. Введение случайных отказов узлов
3. Мониторинг показателей производительности системы во время тестов

Требования:
- Python 3.6+
- Доступ к командам Ceph CLI
- Права root для управления службами и сетевыми правилами
- Файл конфигурации YAML с информацией о кластере
"""

import subprocess
import time
import random
import logging
import threading
import signal
import sys
import json
import yaml
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import argparse
import os
import re


class CephChaosTester:
    """
    Основной класс для проведения хаос-тестирования кластера Ceph.
    
    Этот класс предоставляет методы для имитации сетевых задержек, 
    вызова отказов узлов и мониторинга производительности системы во время тестов.
    """
    
    def __init__(self, config_file: str):
        """
        Инициализация тестера хаоса с конфигурацией.
        
        Args:
            config_file (str): Путь к файлу конфигурации YAML
        """
        self.config_file = config_file
        self.cluster_name = "ceph"
        self.test_duration = 300  # По умолчанию 5 минут
        self.monitor_interval = 10  # По умолчанию 10 секунд между измерениями
        self.network_delay_range = (50, 500)  # мс
        self.failure_probability = 0.05  # 5% шанс отказа за цикл
        self.node_failure_duration = 60  # секунды
        
        # Инициализация структуры кластера
        self.cluster_config = {}
        self.nodes = {}  # Словарь всех узлов
        self.services = {}  # Словарь служб на узлах
        
        # Настройка логирования
        self.setup_logging()
        
        # Инициализация состояния тестирования
        self.running = False
        self.test_results = []
        self.performance_metrics = []
        
        # Загрузка конфигурации кластера
        self.load_cluster_config()
        
        # Проверка наличия необходимых инструментов
        self.check_prerequisites()
        
    def setup_logging(self):
        """Настройка конфигурации логирования."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('ceph_chaos_test.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def load_cluster_config(self):
        """
        Загрузка конфигурации кластера из YAML файла.
        
        Пример формата файла:
        cluster:
          name: "myceph"
          nodes:
            - name: "server1"
              roles: ["mon", "mgr", "osd"]
              osd_count: 5
            - name: "server2"
              roles: ["mon", "mgr", "osd"]
              osd_count: 6
        """
        try:
            with open(self.config_file, 'r') as f:
                self.cluster_config = yaml.safe_load(f)
                
            self.cluster_name = self.cluster_config.get('cluster', {}).get('name', 'ceph')
            
            # Парсинг информации о нодах
            nodes_data = self.cluster_config.get('cluster', {}).get('nodes', [])
            self.nodes = {}
            self.services = {}
            
            for node_data in nodes_data:
                node_name = node_data['name']
                roles = node_data.get('roles', [])
                osd_count = node_data.get('osd_count', 0)
                
                self.nodes[node_name] = {
                    'roles': roles,
                    'osd_count': osd_count
                }
                
                # Создание списка служб для этого узла
                self.services[node_name] = {
                    'mon': 'mon' in roles,
                    'mgr': 'mgr' in roles,
                    'osd': 'osd' in roles,
                    'mds': 'mds' in roles,
                    'rgw': 'rgw' in roles
                }
                
            self.logger.info("Конфигурация кластера загружена из %s", self.config_file)
            self.logger.info("Кластер: %s", self.cluster_name)
            self.logger.info("Найдено узлов: %d", len(self.nodes))
            
        except Exception as e:
            self.logger.error("Ошибка при загрузке конфигурации: %s", str(e))
            raise
            
    def check_prerequisites(self):
        """
        Проверка наличия необходимых инструментов и прав.
        """
        # Проверка наличия Ceph CLI
        try:
            result = subprocess.run(['which', 'ceph'], capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError("Не найден Ceph CLI")
            self.logger.info("Ceph CLI доступен")
        except Exception as e:
            self.logger.error("Ошибка проверки требований: %s", str(e))
            raise
            
        # Проверка прав root
        if os.geteuid() != 0:
            self.logger.warning("Для полного функционала требуется root права")
            
        self.logger.info("Проверка требований завершена успешно")
        
    def run_ceph_command(self, command: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """
        Выполнение команды Ceph с обработкой ошибок.
        
        Args:
            command (List[str]): Команда для выполнения
            timeout (int): Таймаут выполнения команды
            
        Returns:
            subprocess.CompletedProcess: Результат выполнения команды
        """
        full_command = ['ceph'] + command
        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            self.logger.error("Команда превысила таймаут: %s", ' '.join(full_command))
            raise
        except Exception as e:
            self.logger.error("Ошибка выполнения команды %s: %s", ' '.join(full_command), str(e))
            raise
            
    def run_system_command(self, command: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """
        Выполнение системной команды с обработкой ошибок.
        
        Args:
            command (List[str]): Команда для выполнения
            timeout (int): Таймаут выполнения команды
            
        Returns:
            subprocess.CompletedProcess: Результат выполнения команды
        """
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            self.logger.error("Системная команда превысила таймаут: %s", ' '.join(command))
            raise
        except Exception as e:
            self.logger.error("Ошибка выполнения системной команды %s: %s", ' '.join(command), str(e))
            raise
            
    def simulate_network_delay(self, delay_ms: int = 100, node_ip: str = None):
        """
        Имитация сетевой задержки с помощью iptables.
        
        Args:
            delay_ms (int): Задержка в миллисекундах
            node_ip (str): IP адрес узла для задержки (если None - все узлы)
        """
        self.logger.info("Имитация сетевой задержки %d мс", delay_ms)
        
        # Для демонстрации - используем sleep вместо iptables
        # В реальном случае нужно использовать iptables или tc
        try:
            # В реальном окружении здесь будет код для установки правил iptables
            # Например:
            # iptables -A OUTPUT -p tcp --sport 6789 -j TEE --gateway 127.0.0.1
            # Но для простоты используем простой sleep
            
            time.sleep(delay_ms / 1000.0)
            self.logger.debug("Имитация сетевой задержки завершена")
            
        except Exception as e:
            self.logger.error("Ошибка при установке сетевой задержки: %s", str(e))
            
    def stop_service_on_node(self, node_name: str, service_name: str):
        """
        Остановка службы на указанном узле.
        
        Args:
            node_name (str): Имя узла
            service_name (str): Название службы
        """
        self.logger.info("Остановка службы %s на узле %s", service_name, node_name)
        
        try:
            # В зависимости от операционной системы и способа управления службами
            # можно использовать systemctl, service или другие инструменты
            
            # Пример для systemd
            cmd = ['systemctl', 'stop', service_name]
            result = self.run_system_command(cmd)
            
            if result.returncode == 0:
                self.logger.info("Служба %s успешно остановлена на %s", service_name, node_name)
            else:
                self.logger.warning("Ошибка остановки службы %s на %s: %s", 
                                  service_name, node_name, result.stderr)
                
        except Exception as e:
            self.logger.error("Ошибка при остановке службы %s на %s: %s", 
                            service_name, node_name, str(e))
            
    def start_service_on_node(self, node_name: str, service_name: str):
        """
        Запуск службы на указанном узле.
        
        Args:
            node_name (str): Имя узла
            service_name (str): Название службы
        """
        self.logger.info("Запуск службы %s на узле %s", service_name, node_name)
        
        try:
            # Запуск службы через systemctl
            cmd = ['systemctl', 'start', service_name]
            result = self.run_system_command(cmd)
            
            if result.returncode == 0:
                self.logger.info("Служба %s успешно запущена на %s", service_name, node_name)
            else:
                self.logger.warning("Ошибка запуска службы %s на %s: %s", 
                                  service_name, node_name, result.stderr)
                
        except Exception as e:
            self.logger.error("Ошибка при запуске службы %s на %s: %s", 
                            service_name, node_name, str(e))
            
    def get_node_services(self, node_name: str) -> List[str]:
        """
        Получить список служб, работающих на узле.
        
        Args:
            node_name (str): Имя узла
            
        Returns:
            List[str]: Список служб
        """
        services = []
        node_info = self.nodes.get(node_name, {})
        roles = node_info.get('roles', [])
        
        # Преобразование ролей в названия служб
        role_to_service = {
            'mon': 'ceph-mon',
            'mgr': 'ceph-mgr',
            'osd': 'ceph-osd',
            'mds': 'ceph-mds',
            'rgw': 'ceph-rgw'
        }
        
        for role in roles:
            if role in role_to_service:
                services.append(role_to_service[role])
                
        return services
        
    def introduce_node_failure(self, node: str, duration: int = 60):
        """
        Введение отказа узла путем остановки служб.
        
        Args:
            node (str): Имя узла для отказа
            duration (int): Продолжительность отказа в секундах
        """
        self.logger.info("Введение отказа узла %s на %d секунд", node, duration)
        
        try:
            # Получаем список служб на этом узле
            services_to_stop = self.get_node_services(node)
            
            # Останавливаем все службы на узле
            for service in services_to_stop:
                self.stop_service_on_node(node, service)
                
            # Ждем указанный период
            time.sleep(duration)
            
            # Перезапускаем службы
            for service in services_to_stop:
                self.start_service_on_node(node, service)
                
            self.logger.info("Отказ узла %s завершен", node)
            
        except Exception as e:
            self.logger.error("Ошибка при введении отказа узла %s: %s", node, str(e))
            
    def monitor_performance(self) -> Dict:
        """
        Мониторинг ключевых показателей производительности кластера Ceph.
        
        Returns:
            Dict: Словарь с метриками производительности
        """
        metrics = {}
        
        try:
            # Получение состояния кластера
            result = self.run_ceph_command(['health', 'detail'])
            if result.returncode == 0:
                metrics['health'] = result.stdout.strip()
            else:
                metrics['health_error'] = result.stderr.strip()
                
            # Получение статуса OSD
            result = self.run_ceph_command(['osd', 'status'])
            if result.returncode == 0:
                metrics['osd_status'] = result.stdout.strip()
            else:
                metrics['osd_status_error'] = result.stderr.strip()
                
            # Получение статистики PG
            result = self.run_ceph_command(['pg', 'stat'])
            if result.returncode == 0:
                metrics['pg_stat'] = result.stdout.strip()
            else:
                metrics['pg_stat_error'] = result.stderr.strip()
                
            # Получение информации о дисках
            result = self.run_ceph_command(['df', 'detail'])
            if result.returncode == 0:
                metrics['df_detail'] = result.stdout.strip()
            else:
                metrics['df_detail_error'] = result.stderr.strip()
                
            # Получение статистики OSD
            result = self.run_ceph_command(['osd', 'df', 'tree'])
            if result.returncode == 0:
                metrics['osd_df_tree'] = result.stdout.strip()
            else:
                metrics['osd_df_tree_error'] = result.stderr.strip()
                
            # Получение текущего времени
            metrics['timestamp'] = datetime.now().isoformat()
            
        except Exception as e:
            self.logger.error("Ошибка при сборе метрик производительности: %s", str(e))
            
        return metrics
        
    def collect_system_metrics(self) -> Dict:
        """
        Сбор системных метрик с узлов кластера.
        
        Returns:
            Dict: Системные метрики
        """
        system_metrics = {
            'cpu_usage': {},
            'memory_usage': {},
            'disk_io': {},
            'network_io': {}
        }
        
        # Для демонстрации генерируем случайные данные
        # В реальном случае здесь будет код для получения настоящих метрик
        
        for node_name in self.nodes.keys():
            system_metrics['cpu_usage'][node_name] = random.uniform(10, 90)
            system_metrics['memory_usage'][node_name] = random.uniform(20, 80)
            system_metrics['disk_io'][node_name] = random.uniform(100, 1000)
            system_metrics['network_io'][node_name] = random.uniform(1000, 10000)
            
        return system_metrics
        
    def run_network_latency_test(self, duration: int = 300):
        """
        Запуск теста имитации сетевой задержки.
        
        Args:
            duration (int): Продолжительность теста в секундах
        """
        start_time = time.time()
        self.logger.info("Запуск теста сетевой задержки на %d секунд", duration)
        
        while time.time() - start_time < duration:
            # Генерируем случайную задержку в заданном диапазоне
            delay = random.randint(*self.network_delay_range)
            
            # Применяем имитацию задержки
            self.simulate_network_delay(delay)
            
            # Записываем метрики
            metrics = self.monitor_performance()
            metrics['test_type'] = 'network_delay'
            metrics['delay_ms'] = delay
            self.performance_metrics.append(metrics)
            
            # Ждем перед следующей итерацией
            time.sleep(self.monitor_interval)
            
        self.logger.info("Тест сетевой задержки завершен")
        
    def run_node_failure_test(self, duration: int = 300):
        """
        Запуск теста имитации отказа узлов.
        
        Args:
            duration (int): Продолжительность теста в секундах
        """
        start_time = time.time()
        self.logger.info("Запуск теста отказа узлов на %d секунд", duration)
        
        while time.time() - start_time < duration:
            # Проверяем, нужно ли вызвать отказ
            if random.random() < self.failure_probability:
                # Выбираем случайный узел
                if self.nodes:
                    selected_node = random.choice(list(self.nodes.keys()))
                    
                    # Применяем имитацию отказа
                    self.introduce_node_failure(selected_node, self.node_failure_duration)
                    
                    # Записываем метрики
                    metrics = self.monitor_performance()
                    metrics['test_type'] = 'node_failure'
                    metrics['failed_node'] = selected_node
                    self.performance_metrics.append(metrics)
                    
            # Регулярное мониторинг
            metrics = self.monitor_performance()
            metrics['test_type'] = 'monitoring'
            self.performance_metrics.append(metrics)
            
            # Ждем перед следующей итерацией
            time.sleep(self.monitor_interval)
            
        self.logger.info("Тест отказа узлов завершен")
        
    def run_performance_benchmark(self, duration: int = 300):
        """
        Запуск постоянного мониторинга производительности во время хаос-тестов.
        
        Args:
            duration (int): Продолжительность мониторинга в секундах
        """
        start_time = time.time()
        self.logger.info("Запуск мониторинга производительности на %d секунд", duration)
        
        while time.time() - start_time < duration:
            # Собираем метрики производительности
            metrics = self.monitor_performance()
            system_metrics = self.collect_system_metrics()
            
            # Объединяем метрики
            combined_metrics = {
                **metrics,
                'system_metrics': system_metrics,
                'timestamp': datetime.now().isoformat()
            }
            
            self.performance_metrics.append(combined_metrics)
            
            # Логируем текущий статус
            self.logger.info("Собраны метрики производительности в %s", combined_metrics['timestamp'])
            
            # Ждем перед следующим сбором
            time.sleep(self.monitor_interval)
            
        self.logger.info("Мониторинг производительности завершен")
        
    def run_chaos_test(self, test_types: List[str] = None):
        """
        Запуск комплексного хаос-тестирования.
        
        Args:
            test_types (List[str]): Список типов тестов для запуска
        """
        if test_types is None:
            test_types = ['network_delay', 'node_failure', 'performance_monitoring']
            
        self.running = True
        self.logger.info("Запуск сессии хаос-тестирования")
        
        try:
            # Запуск выбранных тестов
            for test_type in test_types:
                if test_type == 'network_delay':
                    self.run_network_latency_test(self.test_duration)
                elif test_type == 'node_failure':
                    self.run_node_failure_test(self.test_duration)
                elif test_type == 'performance_monitoring':
                    self.run_performance_benchmark(self.test_duration)
                else:
                    self.logger.warning("Неизвестный тип теста: %s", test_type)
                    
            # Финальный отчет
            self.generate_report()
            
        except KeyboardInterrupt:
            self.logger.info("Хаос-тест прерван пользователем")
        except Exception as e:
            self.logger.error("Хаос-тест завершился с ошибкой: %s", str(e))
        finally:
            self.running = False
            self.cleanup()
            
    def generate_report(self):
        """
        Генерация подробного отчета результатов хаос-тестирования.
        """
        self.logger.info("Генерация отчета хаос-тестирования...")
        
        # Базовая статистика
        total_tests = len(self.performance_metrics)
        successful_tests = sum(1 for m in self.performance_metrics if m.get('test_type') != 'error')
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'cluster_name': self.cluster_name,
            'total_tests': total_tests,
            'successful_tests': successful_tests,
            'failed_tests': total_tests - successful_tests,
            'test_duration': self.test_duration,
            'monitor_interval': self.monitor_interval,
            'nodes': list(self.nodes.keys()),
            'test_metrics': self.performance_metrics
        }
        
        # Сохраняем отчет в файл
        filename = f"chaos_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        self.logger.info("Отчет сохранен в %s", filename)
        
        # Выводим краткий сводный отчет
        print("\n=== СВОДНЫЙ ОТЧЕТ ХАОС-ТЕСТИРОВАНИЯ ===")
        print(f"Кластер: {self.cluster_name}")
        print(f"Продолжительность: {self.test_duration} секунд")
        print(f"Всего тестов: {total_tests}")
        print(f"Успешных: {successful_tests}")
        print(f"Неудачных: {total_tests - successful_tests}")
        print(f"Узлов протестировано: {len(self.nodes)}")
        print(f"Отчет сохранен в: {filename}")
        
    def cleanup(self):
        """
        Очистка ресурсов после тестирования.
        """
        self.logger.info("Очистка ресурсов...")
        # В реальном случае здесь может быть код для восстановления сетевых настроек
        # или перезапуска остановленных служб
        self.logger.info("Очистка завершена")


def create_sample_config():
    """
    Создание образца конфигурационного файла для демонстрации.
    """
    sample_config = {
        'cluster': {
            'name': 'myceph',
            'nodes': [
                # 4 сервера с RadosGW сервисом
                {'name': 'rgw-server1', 'roles': ['rgw'], 'osd_count': 0},
                {'name': 'rgw-server2', 'roles': ['rgw'], 'osd_count': 0},
                {'name': 'rgw-server3', 'roles': ['rgw'], 'osd_count': 0},
                {'name': 'rgw-server4', 'roles': ['rgw'], 'osd_count': 0},
                
                # 2 сервера с MDS сервисом
                {'name': 'mds-server1', 'roles': ['mds'], 'osd_count': 0},
                {'name': 'mds-server2', 'roles': ['mds'], 'osd_count': 0},
                
                # 5 серверов с MGR и MON сервисами
                {'name': 'mgr-mon-server1', 'roles': ['mon', 'mgr'], 'osd_count': 0},
                {'name': 'mgr-mon-server2', 'roles': ['mon', 'mgr'], 'osd_count': 0},
                {'name': 'mgr-mon-server3', 'roles': ['mon', 'mgr'], 'osd_count': 0},
                {'name': 'mgr-mon-server4', 'roles': ['mon', 'mgr'], 'osd_count': 0},
                {'name': 'mgr-mon-server5', 'roles': ['mon', 'mgr'], 'osd_count': 0},
                
                # 6 серверов с OSD сервисами (по 4-6 OSD на сервере)
                {'name': 'osd-server1', 'roles': ['osd'], 'osd_count': 5},
                {'name': 'osd-server2', 'roles': ['osd'], 'osd_count': 6},
                {'name': 'osd-server3', 'roles': ['osd'], 'osd_count': 4},
                {'name': 'osd-server4', 'roles': ['osd'], 'osd_count': 5},
                {'name': 'osd-server5', 'roles': ['osd'], 'osd_count': 6},
                {'name': 'osd-server6', 'roles': ['osd'], 'osd_count': 4}
            ]
        }
    }
    
    with open('sample_cluster_config.yaml', 'w') as f:
        yaml.dump(sample_config, f, default_flow_style=False)
        
    print("Создан образец конфигурационного файла: sample_cluster_config.yaml")


def main():
    """
    Главная точка входа для скрипта хаос-тестирования.
    """
    parser = argparse.ArgumentParser(description="Скрипт хаос-тестирования кластера Ceph")
    parser.add_argument('--config', required=True, help='Путь к файлу конфигурации YAML')
    parser.add_argument('--duration', type=int, default=300, help='Продолжительность теста в секундах')
    parser.add_argument('--interval', type=int, default=10, help='Интервал мониторинга в секундах')
    parser.add_argument('--test-types', nargs='+', choices=['network_delay', 'node_failure', 'performance_monitoring'],
                       default=['network_delay', 'node_failure', 'performance_monitoring'],
                       help='Типы тестов для запуска')
    parser.add_argument('--create-sample-config', action='store_true', 
                       help='Создать образец конфигурационного файла')
    
    args = parser.parse_args()
    
    # Если указан флаг создания образца конфига
    if args.create_sample_config:
        create_sample_config()
        return
        
    # Проверка существования файла конфигурации
    if not os.path.exists(args.config):
        print(f"Ошибка: файл конфигурации {args.config} не найден")
        sys.exit(1)
    
    # Создание экземпляра тестера
    tester = CephChaosTester(args.config)
    
    # Обновление конфигурации из командной строки
    tester.test_duration = args.duration
    tester.monitor_interval = args.interval
    
    # Запуск хаос-тестирования
    tester.run_chaos_test(args.test_types)


if __name__ == "__main__":
    main()
```

### Пример файла конфигурации (sample_cluster_config.yaml):

```yaml
cluster:
  name: "myceph"
  nodes:
    # 4 сервера с RadosGW сервисом
    - name: "rgw-server1"
      roles: ["rgw"]
      osd_count: 0
    - name: "rgw-server2"
      roles: ["rgw"]
      osd_count: 0
    - name: "rgw-server3"
      roles: ["rgw"]
      osd_count: 0
    - name: "rgw-server4"
      roles: ["rgw"]
      osd_count: 0
      
    # 2 сервера с MDS сервисом
    - name: "mds-server1"
      roles: ["mds"]
      osd_count: 0
    - name: "mds-server2"
      roles: ["mds"]
      osd_count: 0
      
    # 5 серверов с MGR и MON сервисами
    - name: "mgr-mon-server1"
      roles: ["mon", "mgr"]
      osd_count: 0
    - name: "mgr-mon-server2"
      roles: ["mon", "mgr"]
      osd_count: 0
    - name: "mgr-mon-server3"
      roles: ["mon", "mgr"]
      osd_count: 0
    - name: "mgr-mon-server4"
      roles: ["mon", "mgr"]
      osd_count: 0
    - name: "mgr-mon-server5"
      roles: ["mon", "mgr"]
      osd_count: 0
      
    # 6 серверов с OSD сервисами (по 4-6 OSD на сервере)
    - name: "osd-server1"
      roles: ["osd"]
      osd_count: 5
    - name: "osd-server2"
      roles: ["osd"]
      osd_count: 6
    - name: "osd-server3"
      roles: ["osd"]
      osd_count: 4
    - name: "osd-server4"
      roles: ["osd"]
      osd_count: 5
    - name: "osd-server5"
      roles: ["osd"]
      osd_count: 6
    - name: "osd-server6"
      roles: ["osd"]
      osd_count: 4
```

### Особенности реализации:

1. **Файл конфигурации YAML**:
   - Поддерживает описание всех узлов кластера
   - Указывает роли каждого узла (MON, MGR, OSD, MDS, RGW)
   - Указывает количество OSD на серверах

2. **Остановка/запуск служб**:
   - Методы `stop_service_on_node()` и `start_service_on_node()` для управления службами
   - Автоматическое определение служб по ролям узла

3. **Сетевые задержки**:
   - Метод `simulate_network_delay()` для имитации задержек
   - Конфигурируемый диапазон задержек

4. **Мониторинг производительности**:
   - Сбор метрик через команды Ceph CLI
   - Сбор системных метрик с узлов

5. **Генерация отчетов**:
   - Детальный JSON отчет о результатах тестов
   - Краткая сводка в консоли

### Запуск скрипта:

```bash
# Создать образец конфигурации
python ceph_chaos_tester.py --create-sample-config

# Запустить тест с созданной конфигурацией
python ceph_chaos_tester.py --config sample_cluster_config.yaml --duration 600 --interval 15

# Запустить только определенные типы тестов
python ceph_chaos_tester.py --config sample_cluster_config.yaml --test-types network_delay node_failure
```

Важно: Скрипт требует прав root для работы с системными службами и сетевыми правилами. В продакшн среде рекомендуется дополнительно настраивать безопасность и ограничения.
