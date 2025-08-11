Для вашего запроса готов комплексный, детально документированный Python3 скрипт, который реализует хаос-тестирование кластера Ceph 17.2.7 по указанным типам отказов (сетевая задержка, отказы узлов, отказы сервисов). Скрипт берет конфигурацию и описание кластера из yaml-файлов, поддерживает dry-run режим и логирование.

Кроме того, даю пример yaml-файла, описывающего кластер с требуемым составом и ролями.

***

### Пример yaml файла описания кластера (cluster_description.yml):

```yaml
servers:
  - hostname: ceph-rgw-1
    roles: [rgw, haproxy, keepalived]
  - hostname: ceph-rgw-2
    roles: [rgw, haproxy, keepalived]
  - hostname: ceph-rgw-3
    roles: [rgw, haproxy, keepalived]
  - hostname: ceph-rgw-4
    roles: [rgw, haproxy, keepalived]

  - hostname: ceph-mds-1
    roles: [mds, haproxy, keepalived]
  - hostname: ceph-mds-2
    roles: [mds, haproxy, keepalived]

  - hostname: ceph-mgrmon-1
    roles: [mgr, mon, haproxy]
  - hostname: ceph-mgrmon-2
    roles: [mgr, mon, haproxy]
  - hostname: ceph-mgrmon-3
    roles: [mgr, mon, haproxy]
  - hostname: ceph-mgrmon-4
    roles: [mgr, mon, haproxy]
  - hostname: ceph-mgrmon-5
    roles: [mgr, mon, haproxy]

  - hostname: ceph-osd-1
    roles: [osd]
    osd_services: [osd0, osd1, osd2, osd3, osd4]
  - hostname: ceph-osd-2
    roles: [osd]
    osd_services: [osd5, osd6, osd7, osd8, osd9]
  - hostname: ceph-osd-3
    roles: [osd]
    osd_services: [osd10, osd11, osd12, osd13, osd14]
  - hostname: ceph-osd-4
    roles: [osd]
    osd_services: [osd15, osd16, osd17, osd18, osd19, osd20]
  - hostname: ceph-osd-5
    roles: [osd]
    osd_services: [osd21, osd22, osd23, osd24, osd25, osd26]
  - hostname: ceph-osd-6
    roles: [osd]
    osd_services: [osd27, osd28, osd29, osd30, osd31, osd32]
```

***

### Основной Python скрипт (chaos_ceph.py):

```python
import yaml
import subprocess
import random
import time
import logging
import argparse
from datetime import datetime

"""
Скрипт для хаос-тестирования кластера хранения Ceph 17.2.7.
Реализует: 
1) симуляцию сетевой задержки,
2) отказ узлов (серверов),
3) отказ отдельных сервисов (rgw, mds, mgr, osd, haproxy, keepalived).

Параметры задаются через конфиг файл и описание кластера через yaml.
Ведется подробный лог в файл с отметками времени.

Поддерживается dry-run режим для проверки без реальных изменений.

Автор: опытный разработчик Python, специалист по хаос-инжинирингу.
"""

# Глобальные константы для ограничений отказов сервисов
MAX_FAILS = {
    'rgw': 1,
    'mds': 1,
    'mgr': 1,
    'osd': 2,
    'haproxy': 1,
    'keepalived': 1
}

# Настройка логгирования
logging.basicConfig(
    filename='chaos_ceph.log',
    filemode='a',
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.DEBUG
)

class ChaosCephTester:
    def __init__(self, cluster_desc_file, config_file, dry_run=False):
        self.dry_run = dry_run
        self.load_cluster_description(cluster_desc_file)
        self.load_config(config_file)
        self.init_service_pools()
        logging.info("ChaosCephTester initialized.")

    def load_cluster_description(self, path):
        with open(path, 'r') as f:
            self.cluster = yaml.safe_load(f)
        logging.info(f"Cluster description loaded from {path}")
    
    def load_config(self, path):
        with open(path, 'r') as f:
            self.config = yaml.safe_load(f)
        logging.info(f"Config loaded from {path}")

    def init_service_pools(self):
        """
        Собирает отдельные списки для каждого типа сервиса для удобства выбора случайного
        """
        self.nodes = [s['hostname'] for s in self.cluster['servers']]
        self.role_to_nodes = {
            'rgw': [],
            'mds': [],
            'mgr': [],
            'mon': [],
            'osd_nodes': [],
            'haproxy': [],
            'keepalived': []
        }
        self.osd_services = []  # кортежи (hostname, osd_name)
        for server in self.cluster['servers']:
            roles = server.get('roles', [])
            for role in roles:
                if role in self.role_to_nodes:
                    self.role_to_nodes[role].append(server['hostname'])
            if 'osd' in roles:
                self.role_to_nodes['osd_nodes'].append(server['hostname'])
                osd_services = server.get('osd_services', [])
                # формируем список всех osd сервисов с привязкой к хосту
                for osd in osd_services:
                    self.osd_services.append((server['hostname'], osd))

        logging.info(f"Service pools initialized: { {k:len(v) for k,v in self.role_to_nodes.items()} }")
        logging.info(f"Total OSD services: {len(self.osd_services)}")

    def run(self):
        cycles = self.config['test_cycles']['count']
        cycle_duration = self.config['test_cycles']['cycle_duration_sec']
        interval = self.config['test_cycles']['interval_sec']

        for cycle_num in range(1, cycles + 1):
            fault_type = random.choice(['network_delay', 'node_failure', 'service_failure'])
            logging.info(f"Starting cycle {cycle_num}/{cycles} with fault type: {fault_type}")
            print(f"[{datetime.now()}] Цикл {cycle_num}/{cycles}: Тип отказа {fault_type}")

            try:
                if fault_type == 'network_delay':
                    self.simulate_network_delay(cycle_duration)
                elif fault_type == 'node_failure':
                    self.simulate_node_failure(cycle_duration)
                elif fault_type == 'service_failure':
                    self.simulate_service_failure(cycle_duration)
            except Exception as e:
                logging.error(f"Error during cycle {cycle_num}: {str(e)}")
            
            logging.info(f"Cycle {cycle_num} completed. Sleeping {interval}s before next cycle.")
            time.sleep(interval)

    def simulate_network_delay(self, duration):
        """
        Добавляет сетевую задержку с параметрами из конфигурации.
        Предполагается, что задержка применяется через tc netem на интерфейсах нужных серверов.
        """
        delays = self.config['network_delay']['delays_ms']  # список вариантов задержек

        delay = random.choice(delays)
        logging.info(f"Applying network delay: {delay}ms for {duration}s")
        print(f"Вводим сетевую задержку: {delay} ms")

        # Здесь для каждого сервера вводим задержку с помощью tc (пример для eth0)
        for server in self.nodes:
            self.apply_tc_delay(server, delay)

        if self.dry_run:
            logging.info("Dry-run mode: Skipping sleep and recovery for network delay")
            return

        time.sleep(duration)
        # Очистка настроек задержки после цикла
        for server in self.nodes:
            self.clear_tc_delay(server)

        logging.info("Network delay simulation finished.")

    def apply_tc_delay(self, server, delay_ms):
        """
        Применяет задержку в миллисекундах на интерфейсе eth0 сервера с помощью tc netem.
        """
        cmd_add = f"ssh {server} sudo tc qdisc add dev eth0 root netem delay {delay_ms}ms"
        cmd_change = f"ssh {server} sudo tc qdisc change dev eth0 root netem delay {delay_ms}ms"
        if self.dry_run:
            logging.info(f"Dry-run: would run: {cmd_add}")
            return
        # Сначала пробуем add, если ошибка, значит уже применено, делаем change
        try:
            subprocess.run(cmd_add, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            subprocess.run(cmd_change, shell=True, check=True)
        logging.debug(f"Applied tc delay {delay_ms}ms on {server}")

    def clear_tc_delay(self, server):
        """
        Убирает сетевую задержку с интерфейса eth0
        """
        cmd = f"ssh {server} sudo tc qdisc del dev eth0 root netem"
        if self.dry_run:
            logging.info(f"Dry-run: would run: {cmd}")
            return
        try:
            subprocess.run(cmd, shell=True, check=True)
            logging.debug(f"Cleared tc delay on {server}")
        except subprocess.CalledProcessError:
            # qdisc может не быть установлен
            logging.debug(f"tc qdisc del not set on {server}")

    def simulate_node_failure(self, duration):
        """
        Отключает один случайный узел из каждого типа (rgw, mds, mgr, osd_nodes)
        с последующим включением.
        """
        # Список сервисных ролей для выбора одного узла каждого типа
        node_types = ['rgw', 'mds', 'mgr', 'osd_nodes']

        failed_nodes = []
        for role in node_types:
            nodes = self.role_to_nodes.get(role, [])
            if not nodes:
                continue
            node = random.choice(nodes)
            failed_nodes.append(node)

        logging.info(f"Simulating node failures: {failed_nodes}")
        for node in failed_nodes:
            self.shutdown_node(node)

        if not self.dry_run:
            time.sleep(duration)

        for node in failed_nodes:
            self.start_node(node)

        logging.info("Node failure simulation finished.")

    def shutdown_node(self, node):
        """
        Отключает сервер node стандартным shutdown через ssh.
        """
        cmd = f"ssh {node} sudo systemctl stop ceph.target"
        # Здесь можно заменить на sudo shutdown -h now для полной остановки, но для безопасности используем остановку ceph.target
        logging.info(f"Shutting down node {node} via stop ceph.target")
        if self.dry_run:
            logging.info(f"Dry-run: would run: {cmd}")
            return
        subprocess.run(cmd, shell=True, check=True)

    def start_node(self, node):
        """
        Запускает сервер node через systemctl start ceph.target
        """
        cmd = f"ssh {node} sudo systemctl start ceph.target"
        logging.info(f"Starting node {node} via start ceph.target")
        if self.dry_run:
            logging.info(f"Dry-run: would run: {cmd}")
            return
        subprocess.run(cmd, shell=True, check=True)

    def simulate_service_failure(self, duration):
        """
        Останавливает случайно выбранные сервисы по ограничению:
        - 1 RGW, 1 MDS, 1 MGR, 2 OSD, 1 haproxy, 1 keepalived
        """
        to_stop = []
        # RGW
        rgw_nodes = self.role_to_nodes.get('rgw', [])
        if rgw_nodes:
            node = random.choice(rgw_nodes)
            to_stop.append((node, 'rgw'))

        # MDS
        mds_nodes = self.role_to_nodes.get('mds', [])
        if mds_nodes:
            node = random.choice(mds_nodes)
            to_stop.append((node, 'mds'))

        # MGR
        mgr_nodes = self.role_to_nodes.get('mgr', [])
        if mgr_nodes:
            node = random.choice(mgr_nodes)
            to_stop.append((node, 'mgr'))

        # 2 OSD
        osd_to_stop = random.sample(self.osd_services, k=min(len(self.osd_services), 2))
        for (node, osd) in osd_to_stop:
            to_stop.append((node, osd))

        # haproxy
        haproxy_nodes = self.role_to_nodes.get('haproxy', [])
        if haproxy_nodes:
            node = random.choice(haproxy_nodes)
            to_stop.append((node, 'haproxy'))

        # keepalived
        keepalived_nodes = self.role_to_nodes.get('keepalived', [])
        if keepalived_nodes:
            node = random.choice(keepalived_nodes)
            to_stop.append((node, 'keepalived'))

        logging.info(f"Simulating service failures on: {to_stop}")
        print("Отключаем сервисы:")
        for node, service in to_stop:
            print(f"  {service} на {node}")
            self.stop_service(node, service)

        if not self.dry_run:
            time.sleep(duration)

        for node, service in to_stop:
            self.start_service(node, service)

        logging.info("Service failure simulation finished.")

    def stop_service(self, node, service):
        """
        Останавливает сервис на node через systemctl.
        Для osd сервисов предполагается формат osd@N (например osd@5)
        Для обычных сервисов - просто имя
        """
        if service.startswith('osd'):
            # Останов OSD демона осд@N
            service_name = f"osd@{service[3:]}"
        else:
            service_name = service

        cmd = f"ssh {node} sudo systemctl stop {service_name}"
        logging.info(f"Stopping service {service_name} on {node}")
        if self.dry_run:
            logging.info(f"Dry-run: would run: {cmd}")
            return

        subprocess.run(cmd, shell=True, check=True)

    def start_service(self, node, service):
        """
        Запускает сервис на node через systemctl.
        """
        if service.startswith('osd'):
            service_name = f"osd@{service[3:]}"
        else:
            service_name = service

        cmd = f"ssh {node} sudo systemctl start {service_name}"
        logging.info(f"Starting service {service_name} on {node}")
        if self.dry_run:
            logging.info(f"Dry-run: would run: {cmd}")
            return
        subprocess.run(cmd, shell=True, check=True)

def parse_args():
    parser = argparse.ArgumentParser(description="Chaos testing for Ceph 17.2.7 cluster")
    parser.add_argument('--cluster', required=True, help="Path to cluster description YAML file")
    parser.add_argument('--config', required=True, help="Path to chaos test config YAML file")
    parser.add_argument('--dry-run', action='store_true', help="Run in dry-run mode without actual changes")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    tester = ChaosCephTester(args.cluster, args.config, dry_run=args.dry_run)
    tester.run()
```

***

### Пример конфигурационного файла (config.yml):

```yaml
test_cycles:
  count: 10             # количество циклов хаос-тестирования
  cycle_duration_sec: 60 # длительность каждого цикла в секундах
  interval_sec: 30       # интервал между циклами в секундах

network_delay:
  delays_ms: [50, 100, 200]  # варианты задержек для симуляции
```

***

### Объяснение архитектурных диаграмм в PlantUML

```plantuml
@startuml

title Архитектура скрипта хаос-тестирования Ceph

actor Operator as "Оператор запуска"

rectangle "ChaosCephTester" {
  component "Загрузка описания кластера" as LoadCluster
  component "Загрузка конфигурации" as LoadConfig
  component "Инициализация сервисных пулов" as InitPools
  component "Основной цикл" as MainLoop
  database "Логирование" as Logging

  MainLoop --> LoadCluster : Читает описание
  MainLoop --> LoadConfig : Читает конфиг
  MainLoop --> InitPools : Формирует списки сервисов
  MainLoop --> Logging : Записывает события

  MainLoop --> "Симуляция сбоев" as FailSim

}

rectangle "Симуляция сбоев" {
  component "Сетевая задержка"
  component "Отказ узлов"
  component "Отказ сервисов"
}

Operator --> MainLoop : Запускает скрипт

@enduml
```

***

``plantuml
@startuml

title Диаграмма последовательности запуска цикла

participant Operator
participant ChaosCephTester
participant Node

Operator -> ChaosCephTester : Запуск с параметрами
ChaosCephTester -> ChaosCephTester : Загрузка конфигурации и описания
ChaosCephTester -> ChaosCephTester : Инициализация

loop Для каждого цикла
    ChaosCephTester -> ChaosCephTester : Выбор типа отказа
    alt Network Delay
        ChaosCephTester -> Node : Добавить tc netem задержку
        Node -> ChaosCephTester : Подтверждение
        ChaosCephTester -> ChaosCephTester : Ожидание
        ChaosCephTester -> Node : Очистить tc netem
    else Node Failure
        ChaosCephTester -> Node : Остановить ceph.service (stop node)
        ChaosCephTester -> ChaosCephTester : Ожидание
        ChaosCephTester -> Node : Запустить ceph.service (start node)
    else Service Failure
        ChaosCephTester -> Node : Остановить сервисы
        ChaosCephTester -> ChaosCephTester : Ожидание
        ChaosCephTester -> Node : Запустить сервисы
    end
end

@enduml
```

---

Если нужно, могу дополнительно пояснить или адаптировать. Скрипт написан без сторонних библиотек, кроме pyyaml (общепринятая для работы с yaml). Все команды предполагают, что есть SSH-доступ к узлам с необходимыми правами для управления systemd и tc.

[1] https://habr.com/ru/companies/runity/articles/836246/
[2] https://habr.com/ru/companies/oleg-bunin/articles/431536/
[3] https://forum.proxmox.com/threads/ceph-17-2-7-ceph-device-ls-is-wrong.142025/
[4] https://selectel.ru/blog/ceph-operations/
[5] https://ceph.io/en/news/blog/2024/ceph-a-journey-to-1tibps/
[6] https://habr.com/ru/companies/flant/articles/495870/
[7] https://www.opennet.ru/60470
[8] https://habr.com/ru/articles/509054/
[9] https://habr.com/ru/articles/313644/
[10] https://habr.com/en/articles/133987/comments/
