```python
# chaos_ceph.py

import argparse
import configparser
import logging
import random
import subprocess
import sys
import time
from typing import List, Dict, Any, Tuple

import yaml


class ChaosCeph:
    """
    Класс для проведения хаос-тестирования кластера Ceph.
    Инкапсулирует всю логику по взаимодействию с кластером,
    конфигурацией и выполнением хаос-сценариев.
    Поддерживает режим dry-run для симуляции без реальных действий.
    """

    def __init__(self, config_path: str, cluster_path: str, dry_run: bool = False):
        """
        Инициализирует экземпляр ChaosCeph.

        :param config_path: Путь к файлу конфигурации (.ini).
        :param cluster_path: Путь к файлу с описанием кластера (.yml).
        :param dry_run: Флаг режима dry-run (симуляция без реальных команд).
        """
        self.config = self._load_config(config_path)
        self.cluster_info = self._load_cluster_info(cluster_path)
        self.logger = self._setup_logging()
        self.dry_run = dry_run

        # Параметры из конфигурации
        self.ssh_user = self.config.get('main', 'ssh_user')
        self.cycles = self.config.getint('main', 'cycles')
        self.cycle_duration = self.config.getint('main', 'cycle_duration_seconds')
        self.interval = self.config.getint('main', 'interval_between_cycles_seconds')

        self.logger.info("=" * 50)
        self.logger.info("Инициализация Chaos-инженера для Ceph завершена.")
        self.logger.info(f"Режим dry-run: {'ВКЛЮЧЕН' if self.dry_run else 'ВЫКЛЮЧЕН'}")
        self.logger.info(f"Запланировано циклов: {self.cycles}")
        self.logger.info(f"Длительность цикла: {self.cycle_duration} сек.")
        self.logger.info(f"Интервал между циклами: {self.interval} сек.")
        self.logger.info("=" * 50)

    def _load_config(self, path: str) -> configparser.ConfigParser:
        """Загружает конфигурацию из INI-файла."""
        try:
            config = configparser.ConfigParser()
            if not config.read(path):
                raise FileNotFoundError(f"Файл конфигурации не найден: {path}")
            return config
        except Exception as e:
            print(f"Ошибка при чтении файла конфигурации {path}: {e}")
            sys.exit(1)

    def _load_cluster_info(self, path: str) -> Dict[str, Any]:
        """Загружает информацию о кластере из YAML-файла."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Файл описания кластера не найден: {path}")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Ошибка при парсинге YAML-файла {path}: {e}")
            sys.exit(1)

    def _setup_logging(self) -> logging.Logger:
        """Настраивает систему логирования."""
        log_file = self.config.get('main', 'log_file')
        logger = logging.getLogger('ChaosCeph')
        logger.setLevel(logging.INFO)

        # Обработчик для записи в файл
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)

        # Обработчик для вывода в консоль
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)

        # Форматтер
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        logger.addHandler(fh)
        logger.addHandler(ch)

        return logger

    def _execute_ssh_command(self, hostname: str, command: str) -> Tuple[bool, str, str]:
        """
        Выполняет команду на удаленном узле по SSH.
        В режиме dry-run симулирует выполнение, не запуская реальную команду.

        :param hostname: Имя хоста для подключения.
        :param command: Команда для выполнения.
        :return: Кортеж (успех: bool, stdout: str, stderr: str).
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Симуляция выполнения на {hostname}: {command}")
            return True, "[DRY-RUN] Simulated STDOUT", ""
        
        ssh_command = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',  # Для автоматизации
            '-o', 'BatchMode=yes',            # Не запрашивать пароль
            f'{self.ssh_user}@{hostname}',
            command
        ]
        self.logger.debug(f"Выполнение на {hostname}: {' '.join(ssh_command)}")
        try:
            process = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                check=False,  # Не выбрасывать исключение при ненулевом коде возврата
                encoding='utf-8'
            )
            if process.returncode != 0:
                self.logger.warning(
                    f"Команда на {hostname} завершилась с ошибкой (код {process.returncode}):\n"
                    f"STDOUT: {process.stdout.strip()}\n"
                    f"STDERR: {process.stderr.strip()}"
                )
                return False, process.stdout, process.stderr
            return True, process.stdout, process.stderr
        except Exception as e:
            self.logger.error(f"Критическая ошибка при выполнении SSH-команды на {hostname}: {e}")
            return False, "", str(e)

    def _get_nodes_by_type(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Группирует узлы по типам на основе их основных ролей.
        Типы: 'rgw', 'mds', 'mgr_mon', 'osd'.
        """
        node_types = {'rgw': [], 'mds': [], 'mgr_mon': [], 'osd': []}
        for node in self.cluster_info['nodes']:
            roles = node['roles']
            if 'rgw' in roles:
                node_types['rgw'].append(node)
            elif 'mds' in roles:
                node_types['mds'].append(node)
            elif 'mgr' in roles or 'mon' in roles:
                node_types['mgr_mon'].append(node)
            elif 'osd' in roles:
                node_types['osd'].append(node)
        return node_types

    def _get_all_nodes(self) -> List[Dict[str, Any]]:
        """Возвращает список всех узлов в кластере."""
        return self.cluster_info['nodes']

    def inject_network_latency(self):
        """
        Сценарий: введение сетевой задержки на случайном узле.
        Использует утилиту `tc` (traffic control).
        """
        self.logger.info("--- СЦЕНАРИЙ: СЕТЕВАЯ ЗАДЕРЖКА ---")
        target_node = random.choice(self._get_all_nodes())
        hostname = target_node['hostname']
        interface = self.config.get('network_latency', 'network_interface')
        latency_options = self.config.get('network_latency', 'latency_options_ms').split(',')
        latency = random.choice(latency_options).strip()

        add_latency_cmd = (
            f"sudo tc qdisc add dev {interface} root netem delay {latency}ms"
        )
        del_latency_cmd = (
            f"sudo tc qdisc del dev {interface} root netem"
        )

        self.logger.info(f"Вводим задержку {latency}ms на узле {hostname} (интерфейс {interface})")
        success, _, _ = self._execute_ssh_command(hostname, add_latency_cmd)

        if not success:
            self.logger.error(f"Не удалось ввести задержку на {hostname}. Пропускаем цикл.")
            # Попытка очистить, если правило было добавлено частично
            self._execute_ssh_command(hostname, del_latency_cmd)
            return

        try:
            self.logger.info(f"Задержка активна. Ожидаем {self.cycle_duration} секунд...")
            time.sleep(self.cycle_duration)
        finally:
            self.logger.info(f"Устраняем задержку на узле {hostname}")
            self._execute_ssh_command(hostname, del_latency_cmd)

    def inject_node_failure(self):
        """
        Сценарий: симуляция отказов узлов по типам.
        Для каждого типа узла случайно решаем, отключать ли один узел (с вероятностью 50%).
        Максимум один узел на тип одновременно.
        Симуляция отказа - принудительная перезагрузка.
        """
        self.logger.info("--- СЦЕНАРИЙ: ОТКАЗ УЗЛОВ ---")
        node_types = self._get_nodes_by_type()
        targets = []

        for node_type, nodes in node_types.items():
            if not nodes:
                self.logger.warning(f"Не найдены узлы типа '{node_type}'. Пропускаем.")
                continue
            # Случайно решаем, отключать ли узел этого типа (вероятность 50%)
            if random.random() < 0.5:
                target_node = random.choice(nodes)
                hostname = target_node['hostname']
                targets.append(hostname)
                self.logger.info(f"Симулируем отказ узла {hostname} типа '{node_type}' (перезагрузка)")

                # Команда на перезагрузку (в фоне, чтобы не ждать)
                reboot_cmd = "sudo nohup reboot -f &"
                self._execute_ssh_command(hostname, reboot_cmd)

        if not targets:
            self.logger.info("В этом цикле не выбрано ни одного узла для отказа.")
            return

        self.logger.info(f"Отказы узлов активированы для: {', '.join(targets)}")
        self.logger.info(f"Ожидаем {self.cycle_duration} секунд (узлы должны восстановиться самостоятельно)...")
        time.sleep(self.cycle_duration)

    def _get_service_name(self, role: str, hostname: str, entity_id: Any = None) -> str:
        """Формирует имя systemd-сервиса на основе роли и конфигурации."""
        template = self.config.get('service_failure', f'{role}_service_name')
        
        # Подстановка ID для шаблонных сервисов
        if '%i' in template:
            # Для OSD id - это число. Для других - имя хоста (часто).
            instance_id = entity_id if entity_id is not None else hostname
            return template.replace('%i', str(instance_id))
        return template

    def inject_service_failure(self):
        """
        Сценарий: отказ набора случайных сервисов на разных узлах.
        """
        self.logger.info("--- СЦЕНАРИЙ: ОТКАЗ СЕРВИСОВ ---")
        services_to_kill = []
        
        # Собираем цели для атаки согласно заданным правилам
        service_map = {
            'rgw': 1, 'mds': 1, 'mgr': 1, 'osd': 2, 'haproxy': 1, 'keepalived': 1
        }

        for role, count in service_map.items():
            candidate_nodes = [n for n in self.cluster_info['nodes'] if role in n['roles']]
            if not candidate_nodes:
                self.logger.warning(f"Не найдены узлы с ролью '{role}'. Пропускаем.")
                continue

            if role == 'osd':
                # Для OSD: собираем все OSD с их узлами
                osd_pool = []
                for node in candidate_nodes:
                    for osd_id in node.get('osd_ids', []):
                        osd_pool.append({'hostname': node['hostname'], 'osd_id': osd_id})
                
                if len(osd_pool) < count:
                    self.logger.warning(f"Недостаточно OSD ({len(osd_pool)}) для выбора {count}. Пропускаем OSD.")
                    continue
                
                chosen_osds = random.sample(osd_pool, count)
                for osd in chosen_osds:
                    service_name = self._get_service_name('osd', osd['hostname'], osd['osd_id'])
                    services_to_kill.append({'hostname': osd['hostname'], 'service': service_name})
            else:
                # Для остальных: выбираем случайные узлы
                if len(candidate_nodes) < count:
                    self.logger.warning(f"Недостаточно узлов с ролью '{role}' ({len(candidate_nodes)}) для выбора {count}. Пропускаем.")
                    continue
                
                chosen_nodes = random.sample(candidate_nodes, count)
                for node in chosen_nodes:
                    hostname = node['hostname']
                    service_name = self._get_service_name(role, hostname, hostname)  # hostname как ID
                    services_to_kill.append({'hostname': hostname, 'service': service_name})

        if not services_to_kill:
            self.logger.error("Не удалось выбрать ни одного сервиса для остановки. Пропускаем цикл.")
            return

        self.logger.info("Останавливаем следующие сервисы:")
        for target in services_to_kill:
            self.logger.info(f"  - Сервис: {target['service']} на узле: {target['hostname']}")
            stop_cmd = f"sudo systemctl stop {target['service']}"
            self._execute_ssh_command(target['hostname'], stop_cmd)

        try:
            self.logger.info(f"Сервисы остановлены. Ожидаем {self.cycle_duration} секунд...")
            time.sleep(self.cycle_duration)
        finally:
            self.logger.info("Восстанавливаем остановленные сервисы:")
            for target in services_to_kill:
                self.logger.info(f"  - Запускаем сервис: {target['service']} на узле: {target['hostname']}")
                start_cmd = f"sudo systemctl start {target['service']}"
                self._execute_ssh_command(target['hostname'], start_cmd)

    def run_chaos_cycles(self):
        """
        Основной цикл выполнения хаос-тестирования.
        """
        self.logger.info("Начинаем хаос-тестирование...")
        
        # Список доступных "обезьян хаоса"
        chaos_monkeys = [
            self.inject_network_latency,
            self.inject_node_failure,
            self.inject_service_failure
        ]

        for i in range(1, self.cycles + 1):
            self.logger.info(f"\n{'='*20} ЦИКЛ {i}/{self.cycles} {'='*20}")
            
            # Выбираем случайный тип отказа
            chosen_monkey = random.choice(chaos_monkeys)
            
            try:
                chosen_monkey()
                self.logger.info(f"Цикл {i} завершен успешно.")
            except Exception as e:
                self.logger.error(f"В цикле {i} произошла непредвиденная ошибка: {e}", exc_info=True)

            if i < self.cycles:
                self.logger.info(f"Пауза перед следующим циклом: {self.interval} секунд.")
                time.sleep(self.interval)

        self.logger.info("\n" + "=" * 50)
        self.logger.info("Все циклы хаос-тестирования завершены.")
        self.logger.info("=" * 50)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Инструмент для хаос-тестирования кластера Ceph.")
    parser.add_argument(
        '-c', '--config',
        default='config.ini',
        help='Путь к файлу конфигурации (по умолчанию: config.ini)'
    )
    parser.add_argument(
        '-i', '--inventory',
        default='cluster.yml',
        help='Путь к файлу с описанием кластера (по умолчанию: cluster.yml)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Включить режим dry-run (симуляция без реальных команд)'
    )
    args = parser.parse_args()

    try:
        chaos_runner = ChaosCeph(
            config_path=args.config,
            cluster_path=args.inventory,
            dry_run=args.dry_run
        )
        chaos_runner.run_chaos_cycles()
    except Exception as main_exc:
        print(f"Критическая ошибка при запуске скрипта: {main_exc}")
        sys.exit(1)

```
