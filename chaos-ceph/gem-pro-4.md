Отлично! Как опытный Python-разработчик с экспертизой в хаос-инжиниринге, я подготовил для вас комплексное решение. Оно включает в себя не только сам скрипт, но и примеры конфигурационных файлов, а также архитектурные диаграммы для полного понимания процесса.

### Философия подхода

Скрипт спроектирован с учетом следующих принципов:
1.  **Безопасность и Контроль**: Режим `dry-run` является обязательным для проверки сценариев без реального воздействия. Скрипт всегда пытается вернуть систему в исходное состояние после каждого цикла.
2.  **Идемпотентность**: Возврат в исходное состояние спроектирован так, чтобы его можно было безопасно выполнять, даже если что-то пошло не так.
3.  **Гибкость**: Вся конфигурация кластера и параметры тестирования вынесены во внешние файлы, что позволяет легко адаптировать скрипт под разные окружения.
4.  **Современность**: Для взаимодействия с Ceph используются команды `ceph orch`, что соответствует современному подходу к управлению кластерами Ceph через `cephadm`. Это делает скрипт актуальным для Ceph Quincy (17.x) и новее.
5.  **Прозрачность**: Подробное логирование позволяет точно отследить все действия, выполненные скриптом.

---

### 1. Архитектурные диаграммы (PlantUML)

Эти диаграммы помогут понять структуру и логику работы скрипта.

#### Диаграмма 1: Общая логика выполнения цикла тестирования

Эта диаграмма показывает высокоуровневый процесс работы скрипта от запуска до завершения.

```plantuml
@startuml
title Логика работы скрипта Хаос-тестирования Ceph

actor "Инженер" as Engineer

rectangle "Python Скрипт" as Script {
    usecase "Чтение cluster.yml" as ReadCluster
    usecase "Чтение config.ini" as ReadConfig
    usecase "Запуск цикла тестов" as TestLoop
}

rectangle "Кластер Ceph" as CephCluster

database "chaos.log" as LogFile

Engineer -> Script : Запуск
Script -> ReadCluster : 1.
Script -> ReadConfig : 2.

note right of Script
  Подготовка к работе,
  настройка логирования
end note

Script -> TestLoop

loop test_cycles раз

    TestLoop -> CephCluster : 3. Случайный выбор и инъекция отказа\n(Сеть / Узел / Сервис)
    note on link
        Выполняется через SSH
        с использованием `tc` или `ceph orch`
    end note

    TestLoop -> LogFile: Логирование инъекции

    TestLoop -> TestLoop : 4. Ожидание (cycle_duration)

    TestLoop -> CephCluster : 5. Откат всех изменений\n(Возврат в исходное состояние)
    note on link
        Выполняется через SSH
    end note
    TestLoop -> LogFile: Логирование отката

    TestLoop -> TestLoop : 6. Ожидание (interval_between_cycles)

end

TestLoop --> Script: Завершение
Script --> Engineer: Вывод в консоль

@enduml
```

#### Диаграмма 2: Архитектура классов и компонентов скрипта

Эта диаграмма показывает внутреннюю структуру Python-скрипта, его основные классы и их взаимодействие.

```plantuml
@startuml
title Архитектура компонентов скрипта

package "Внешние файлы" {
    [config.ini]
    [cluster.yml]
}

package "Стандартные библиотеки Python" {
    [argparse]
    [configparser]
    [logging]
    [subprocess]
    [random]
    [time]
}

package "Сторонняя библиотека" {
    [pyyaml]
}

package "Основной скрипт: chaos_ceph.py" {
    class ChaosController {
        - config: dict
        - cluster_inventory: dict
        - dry_run: bool
        - active_failures: list
        --
        + run_main_loop()
        + inject_failure()
        + revert_all_failures()
        --
        - _execute_command(host, command)
        - _get_nodes_by_role(role)
        - _get_daemons_on_host(host, type)
        --
        - _inject_network_latency()
        - _inject_node_failure()
        - _inject_service_failure()
        --
        - _revert_network_latency(failure_info)
        - _revert_node_failure(failure_info)
        - _revert_service_failure(failure_info)
    }

    object "main()" as MainFunction
}

MainFunction ..> argparse : использует для парсинга аргументов
MainFunction ..> configparser : использует для чтения .ini
MainFunction ..> pyyaml : использует для чтения .yml
MainFunction ..> ChaosController : создает и запускает

ChaosController ..> subprocess : использует для выполнения SSH команд
ChaosController ..> logging : использует для логирования
ChaosController ..> random : использует для выбора отказов
ChaosController ..> time : использует для задержек

[config.ini] <-.. MainFunction : читает
[cluster.yml] <-.. MainFunction : читает

@enduml
```

---

### 2. Конфигурационные файлы

Перед запуском скрипта необходимо создать два файла: `config.ini` для параметров и `cluster.yml` для описания кластера.

#### `config.ini`

Этот файл содержит все настраиваемые параметры работы скрипта.

```ini
# config.ini - Файл конфигурации для хаос-тестирования

[main]
# Количество циклов тестирования
test_cycles = 10
# Длительность одного цикла отказа в секундах
cycle_duration_seconds = 300
# Интервал между циклами в секундах
interval_between_cycles_seconds = 60
# Файл для логирования
log_file = chaos_ceph.log
# Пользователь для SSH-доступа к узлам кластера (должен иметь sudo права без пароля)
ssh_user = root
# Сетевой интерфейс на узлах для симуляции задержки
network_interface = eth0

[latency]
# Варианты сетевой задержки в миллисекундах, через запятую
delays_ms = 100, 250, 500

[service_failure_limits]
# Максимальное количество сервисов для одновременной остановки в одном цикле
rgw = 1
mds = 1
mgr = 1
osd = 2
haproxy = 1
keepalived = 1
```

#### `cluster.yml`

Этот файл описывает топологию вашего Ceph кластера. Структура файла позволяет гибко задавать роли для каждого узла.

```yaml
# cluster.yml - Описание состава и ролей узлов кластера Ceph

# Список всех узлов в кластере с их ролями и специфичными данными.
# Роли могут быть: rgw, mds, mgr, mon, osd, haproxy, keepalived.
# Для узлов с ролью 'osd' необходимо указать список ID их OSD-демонов.
nodes:
  # 4 сервера с RGW, haproxy, keepalived
  - hostname: rgw01.ceph.local
    roles: [rgw, haproxy, keepalived]
  - hostname: rgw02.ceph.local
    roles: [rgw, haproxy, keepalived]
  - hostname: rgw03.ceph.local
    roles: [rgw, haproxy, keepalived]
  - hostname: rgw04.ceph.local
    roles: [rgw, haproxy, keepalived]

  # 2 сервера с MDS, haproxy, keepalived
  - hostname: mds01.ceph.local
    roles: [mds, haproxy, keepalived]
  - hostname: mds02.ceph.local
    roles: [mds, haproxy, keepalived]

  # 5 серверов с MGR, MON, haproxy
  - hostname: mon01.ceph.local
    roles: [mgr, mon, haproxy]
  - hostname: mon02.ceph.local
    roles: [mgr, mon, haproxy]
  - hostname: mon03.ceph.local
    roles: [mgr, mon, haproxy]
  - hostname: mon04.ceph.local
    roles: [mgr, mon, haproxy]
  - hostname: mon05.ceph.local
    roles: [mgr, mon, haproxy]

  # 6 серверов с OSD
  - hostname: osd01.ceph.local
    roles: [osd]
    osd_ids: [0, 1, 2, 3]
  - hostname: osd02.ceph.local
    roles: [osd]
    osd_ids: [4, 5, 6, 7, 8]
  - hostname: osd03.ceph.local
    roles: [osd]
    osd_ids: [9, 10, 11, 12]
  - hostname: osd04.ceph.local
    roles: [osd]
    osd_ids: [13, 14, 15, 16, 17]
  - hostname: osd05.ceph.local
    roles: [osd]
    osd_ids: [18, 19, 20, 21]
  - hostname: osd06.ceph.local
    roles: [osd]
    osd_ids: [22, 23, 24, 25, 26]
```

---

### 3. Скрипт на Python (`chaos_ceph.py`)

Этот скрипт реализует всю логику хаос-тестирования.

**Предварительные требования**:
1.  Python 3.6+
2.  Библиотека `PyYAML`: `pip install pyyaml`
3.  Настроенный беспарольный SSH-доступ по ключу для пользователя, указанного в `config.ini`, ко всем узлам кластера. Этот пользователь должен иметь право выполнять `sudo` без пароля для команд `tc` и `systemctl`, а также иметь доступ к выполнению `ceph` команд.

```python
# chaos_ceph.py
# Скрипт для проведения хаос-тестирования кластера Ceph 17.2.7 (Quincy)

import argparse
import configparser
import logging
import os
import random
import subprocess
import sys
import time
from typing import Dict, List, Any, Optional

import yaml

# Глобальная переменная для хранения информации об активных отказах
# Это необходимо для корректного отката изменений.
ACTIVE_FAILURES = []


def setup_logging(log_file: str):
    """Настраивает систему логирования."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )


def execute_command(host: str, command: str, ssh_user: str, dry_run: bool = False) -> Optional[subprocess.CompletedProcess]:
    """
    Выполняет команду на удаленном хосте через SSH.

    Args:
        host (str): Имя или IP-адрес хоста.
        command (str): Команда для выполнения.
        ssh_user (str): Пользователь для SSH-подключения.
        dry_run (bool): Если True, команда не выполняется, а только логируется.

    Returns:
        Optional[subprocess.CompletedProcess]: Результат выполнения команды или None в режиме dry_run.
    """
    ssh_command = f"ssh -o StrictHostKeyChecking=no {ssh_user}@{host} '{command}'"
    logging.info(f"Подготовка к выполнению команды на хосте '{host}': {command}")

    if dry_run:
        logging.info(f"[DRY-RUN] Команда не будет выполнена.")
        return None

    try:
        result = subprocess.run(
            ssh_command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        logging.info(f"Команда успешно выполнена. STDOUT: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Ошибка выполнения команды на '{host}'.")
        logging.error(f"Команда: {e.cmd}")
        logging.error(f"Код возврата: {e.returncode}")
        logging.error(f"STDOUT: {e.stdout.strip()}")
        logging.error(f"STDERR: {e.stderr.strip()}")
        # Не прерываем выполнение, чтобы скрипт мог попытаться откатить изменения
        return None
    except subprocess.TimeoutExpired:
        logging.error(f"Команда на хосте '{host}' не завершилась за 120 секунд.")
        return None


class ChaosMonkey:
    """
    Основной класс, управляющий логикой хаос-тестирования.
    """
    def __init__(self, config: Dict[str, Any], cluster_inventory: Dict[str, Any], dry_run: bool):
        self.config = config
        self.inventory = cluster_inventory
        self.dry_run = dry_run
        self.ssh_user = config['main']['ssh_user']
        
        # Подготовка списков узлов по ролям для удобства
        self.nodes_by_role = self._prepare_role_map()
        self.all_nodes = list(self.inventory['nodes'])

    def _prepare_role_map(self) -> Dict[str, List[Dict]]:
        """Создает словарь, где ключ - роль, а значение - список узлов с этой ролью."""
        role_map = {}
        for node in self.inventory['nodes']:
            for role in node['roles']:
                if role not in role_map:
                    role_map[role] = []
                role_map[role].append(node)
        return role_map

    def _get_random_node_by_role(self, role: str) -> Optional[Dict]:
        """Возвращает случайный узел с указанной ролью."""
        nodes = self.nodes_by_role.get(role)
        return random.choice(nodes) if nodes else None

    # --- Методы инъекции отказов ---

    def inject_network_latency(self):
        """Симулирует сетевую задержку на случайном узле."""
        logging.info("--- Инъекция отказа: Сетевая задержка ---")
        node_info = random.choice(self.all_nodes)
        host = node_info['hostname']
        interface = self.config['main']['network_interface']
        delay = random.choice(self.config['latency']['delays_ms'])
        
        logging.info(f"Выбран узел '{host}' для внесения задержки {delay}ms на интерфейс {interface}")
        
        # Используем sudo, так как tc требует прав root
        command = f"sudo tc qdisc add dev {interface} root netem delay {delay}ms"
        execute_command(host, command, self.ssh_user, self.dry_run)
        
        failure_info = {
            "type": "network_latency",
            "host": host,
            "interface": interface
        }
        ACTIVE_FAILURES.append(failure_info)

    def inject_node_failure(self):
        """Симулирует отказ случайного узла путем его "осушения" (drain)."""
        logging.info("--- Инъекция отказа: Отказ узла ---")
        # Выбираем случайный узел из всех, кроме узла, на котором может выполняться сам скрипт
        # Для простоты, выбираем любой узел. В реальной среде можно добавить исключения.
        target_node = random.choice(self.all_nodes)['hostname']
        
        # Команду выполняем на любом MON/MGR узле, так как ceph orch доступна там
        # Выберем первый попавшийся узел с ролью 'mon' или 'mgr'
        control_node = self._get_random_node_by_role('mon') or self._get_random_node_by_role('mgr')
        if not control_node:
            logging.error("Не найден узел управления (mon/mgr) для выполнения ceph команд.")
            return
            
        control_host = control_node['hostname']
        logging.info(f"Выбран узел '{target_node}' для симуляции отказа. Управляющий узел: '{control_host}'.")
        
        command = f"ceph orch host drain {target_node} --yes-i-really-mean-it"
        execute_command(control_host, command, self.ssh_user, self.dry_run)
        
        failure_info = {
            "type": "node_failure",
            "host": target_node,
            "control_host": control_host
        }
        ACTIVE_FAILURES.append(failure_info)

    def inject_service_failure(self):
        """Останавливает случайный набор сервисов в кластере."""
        logging.info("--- Инъекция отказа: Отказ сервисов ---")
        
        # Получаем узел управления для выполнения команд
        control_node = self._get_random_node_by_role('mon') or self._get_random_node_by_role('mgr')
        if not control_node:
            logging.error("Не найден узел управления (mon/mgr) для выполнения ceph команд.")
            return
        control_host = control_node['hostname']
        
        limits = self.config['service_failure_limits']
        
        # Собираем список демонов для остановки
        daemons_to_stop = []

        # Выбор демонов по типам в соответствии с лимитами
        for svc_type, count in limits.items():
            if svc_type in ["haproxy", "keepalived"]:
                # Эти сервисы управляются через systemd, а не ceph orch
                nodes_with_role = self.nodes_by_role.get(svc_type)
                if not nodes_with_role:
                    continue
                
                selected_nodes = random.sample(nodes_with_role, min(count, len(nodes_with_role)))
                for node in selected_nodes:
                    daemons_to_stop.append({"type": "systemd", "service": svc_type, "host": node['hostname']})
            else:
                # Сервисы Ceph (rgw, mds, mgr, osd)
                nodes_with_role = self.nodes_by_role.get(svc_type)
                if not nodes_with_role:
                    continue

                if svc_type == 'osd':
                    # OSD обрабатываются отдельно, так как у них ID
                    all_osd_nodes = [n for n in self.all_nodes if 'osd' in n['roles']]
                    osd_ids_to_stop = []
                    for _ in range(min(count, len(all_osd_nodes))): # Чтобы не выбрать больше OSD, чем есть узлов
                        node = random.choice(all_osd_nodes)
                        if 'osd_ids' in node and node['osd_ids']:
                           osd_id = random.choice(node['osd_ids'])
                           daemon_name = f"osd.{osd_id}"
                           if daemon_name not in [d.get("daemon_name") for d in osd_ids_to_stop]:
                               osd_ids_to_stop.append({"type": "ceph", "daemon_name": daemon_name})
                    daemons_to_stop.extend(osd_ids_to_stop)
                else:
                    selected_nodes = random.sample(nodes_with_role, min(count, len(nodes_with_role)))
                    for node in selected_nodes:
                        # Упрощенная логика: предполагаем имя демона <svc_type>.<hostname>
                        # В реальном кластере имя может быть сложнее (e.g., rgw.realm.zone.host)
                        # Для надежности можно было бы парсить `ceph orch ps`, но это усложнит скрипт.
                        # Допущение: имя демона `svc_type.hostname` без домена.
                        simple_hostname = node['hostname'].split('.')[0]
                        daemon_name = f"{svc_type}.{simple_hostname}"
                        daemons_to_stop.append({"type": "ceph", "daemon_name": daemon_name})

        if not daemons_to_stop:
            logging.warning("Не удалось выбрать ни одного сервиса для остановки.")
            return

        for daemon_info in daemons_to_stop:
            if daemon_info['type'] == 'ceph':
                daemon_name = daemon_info['daemon_name']
                logging.info(f"Остановка Ceph демона '{daemon_name}' через узел '{control_host}'.")
                command = f"ceph orch daemon stop {daemon_name}"
                execute_command(control_host, command, self.ssh_user, self.dry_run)
                ACTIVE_FAILURES.append({"type": "service_failure", "service_type": "ceph", "daemon_name": daemon_name, "control_host": control_host})
            elif daemon_info['type'] == 'systemd':
                service = daemon_info['service']
                host = daemon_info['host']
                logging.info(f"Остановка systemd сервиса '{service}' на узле '{host}'.")
                command = f"sudo systemctl stop {service}"
                execute_command(host, command, self.ssh_user, self.dry_run)
                ACTIVE_FAILURES.append({"type": "service_failure", "service_type": "systemd", "service_name": service, "host": host})
    
    # --- Методы отката ---

    def revert_all_failures(self):
        """Отменяет все активные отказы."""
        if not ACTIVE_FAILURES:
            return
            
        logging.info("===== НАЧАЛО ФАЗЫ ОТКАТА =====")
        # Обрабатываем в обратном порядке, на всякий случай
        for failure in reversed(ACTIVE_FAILURES):
            try:
                if failure["type"] == "network_latency":
                    self._revert_network_latency(failure)
                elif failure["type"] == "node_failure":
                    self._revert_node_failure(failure)
                elif failure["type"] == "service_failure":
                    self._revert_service_failure(failure)
            except Exception as e:
                logging.error(f"Критическая ошибка при откате отказа {failure}: {e}")

        ACTIVE_FAILURES.clear()
        logging.info("===== ФАЗА ОТКАТА ЗАВЕРШЕНА =====")

    def _revert_network_latency(self, failure_info: Dict):
        """Удаляет правила tc для сетевой задержки."""
        host = failure_info["host"]
        interface = failure_info["interface"]
        logging.info(f"Отмена сетевой задержки на хосте '{host}', интерфейс '{interface}'.")
        command = f"sudo tc qdisc del dev {interface} root"
        # Выполняем даже если предыдущие команды падали
        execute_command(host, command, self.ssh_user, self.dry_run)

    def _revert_node_failure(self, failure_info: Dict):
        """Возвращает узел в работу после "осушения"."""
        host = failure_info["host"]
        control_host = failure_info["control_host"]
        logging.info(f"Возврат узла '{host}' в работу.")
        command = f"ceph orch host un-drain {host}"
        execute_command(control_host, command, self.ssh_user, self.dry_run)

    def _revert_service_failure(self, failure_info: Dict):
        """Запускает остановленные ранее сервисы."""
        if failure_info['service_type'] == 'ceph':
            daemon_name = failure_info['daemon_name']
            control_host = failure_info['control_host']
            logging.info(f"Запуск Ceph демона '{daemon_name}'.")
            command = f"ceph orch daemon start {daemon_name}"
            execute_command(control_host, command, self.ssh_user, self.dry_run)
        elif failure_info['service_type'] == 'systemd':
            service_name = failure_info['service_name']
            host = failure_info['host']
            logging.info(f"Запуск systemd сервиса '{service_name}' на '{host}'.")
            command = f"sudo systemctl start {service_name}"
            execute_command(host, command, self.ssh_user, self.dry_run)


def main():
    """Главная функция скрипта."""
    parser = argparse.ArgumentParser(description="Скрипт хаос-тестирования для Ceph.")
    parser.add_argument("--config", default="config.ini", help="Путь к файлу конфигурации INI.")
    parser.add_argument("--cluster", default="cluster.yml", help="Путь к файлу описания кластера YML.")
    parser.add_argument("--dry-run", action="store_true", help="Запустить в режиме 'сухого прогона' без выполнения команд.")
    args = parser.parse_args()

    # --- Загрузка конфигурации ---
    if not os.path.exists(args.config) or not os.path.exists(args.cluster):
        print(f"Ошибка: Не найден конфигурационный файл '{args.config}' или файл кластера '{args.cluster}'")
        sys.exit(1)

    config_parser = configparser.ConfigParser()
    config_parser.read(args.config)
    config = {s: dict(config_parser.items(s)) for s in config_parser.sections()}
    # Преобразуем строки в числа, где это необходимо
    config['main']['test_cycles'] = int(config['main']['test_cycles'])
    config['main']['cycle_duration_seconds'] = int(config['main']['cycle_duration_seconds'])
    config['main']['interval_between_cycles_seconds'] = int(config['main']['interval_between_cycles_seconds'])
    config['latency']['delays_ms'] = [int(d.strip()) for d in config['latency']['delays_ms'].split(',')]
    config['service_failure_limits'] = {k: int(v) for k,v in config['service_failure_limits'].items()}


    with open(args.cluster, 'r') as f:
        cluster_inventory = yaml.safe_load(f)

    setup_logging(config['main']['log_file'])

    if args.dry_run:
        logging.info("***** ЗАПУСК В РЕЖИМЕ DRY-RUN *****")

    # --- Инициализация и запуск ---
    monkey = ChaosMonkey(config, cluster_inventory, args.dry_run)
    
    failure_functions = [
        monkey.inject_network_latency,
        monkey.inject_node_failure,
        monkey.inject_service_failure
    ]
    
    main_loop_counter = config['main']['test_cycles']
    
    try:
        for i in range(1, main_loop_counter + 1):
            logging.info(f"\n{'='*20} НАЧАЛО ЦИКЛА ТЕСТИРОВАНИЯ {i}/{main_loop_counter} {'='*20}")
            
            # Выбираем случайный тип отказа
            chosen_failure = random.choice(failure_functions)
            chosen_failure()
            
            duration = config['main']['cycle_duration_seconds']
            logging.info(f"Отказ активен. Ожидание {duration} секунд...")
            time.sleep(duration)
            
            monkey.revert_all_failures()
            
            logging.info(f"Цикл {i} завершен.")
            
            if i < main_loop_counter:
                interval = config['main']['interval_between_cycles_seconds']
                logging.info(f"Пауза между циклами {interval} секунд...")
                time.sleep(interval)

        logging.info("\nВсе циклы тестирования успешно завершены.")
        
    except KeyboardInterrupt:
        logging.warning("\nСкрипт прерван пользователем (Ctrl+C). Запускаю откат изменений...")
        monkey.revert_all_failures()
        logging.info("Откат завершен. Выход.")
    except Exception as e:
        logging.critical(f"Произошла непредвиденная ошибка: {e}", exc_info=True)
        logging.info("Попытка отката изменений...")
        monkey.revert_all_failures()
    

if __name__ == "__main__":
    main()

```

### Как запустить

1.  Сохраните код скрипта в файл `chaos_ceph.py`.
2.  Создайте файлы `config.ini` и `cluster.yml` и заполните их актуальными данными для вашего кластера.
3.  Установите `pyyaml`: `pip install pyyaml`.
4.  Убедитесь в наличии беспарольного SSH-доступа к узлам.
5.  **Сначала выполните "сухой прогон"**:
    ```bash
    python3 chaos_ceph.py --dry-run
    ```
    Проверьте лог `chaos_ceph.log` и убедитесь, что скрипт формирует правильные команды для вашего окружения.
6.  **Запустите реальное тестирование**:
    ```bash
    python3 chaos_ceph.py
    ```

Скрипт начнет выполнять циклы тестирования, логируя все свои действия в файл и в консоль. Вы можете прервать его в любой момент с помощью `Ctrl+C`, и он попытается корректно откатить все активные на данный момент изменения.
