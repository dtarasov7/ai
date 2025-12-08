ение (с конкретными командами)
## Проверка восстановления
## Мониторинг
## Документирование
## Эскалация (если не решено за X минут)

Runbook:"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 2500,
        'temperature': 0.3
    })
    
    return response.json()['choices'][0]['text']

def get_system_config(system_name):
    # Получение из Ansible inventory или CMDB
    # Заглушка:
    return {
        'hostname': 'prod-web-01',
        'role': 'nginx reverse proxy',
        'backend': 'app-server-01:8080',
        'monitoring': 'grafana dashboard: nginx-performance'
    }

# Использование
incident = "Веб-сервер nginx на prod-web-01 не отвечает (502 Bad Gateway)"
runbook = generate_runbook(incident, "prod-web-01")
print(runbook)
```

---

## Сценарий 11: Сравнение технических решений с учетом контекста инфраструктуры

**Текущая проблема:**
При выборе между технологиями (PostgreSQL vs MongoDB, Kubernetes vs Docker Swarm, nginx vs HAProxy) инженеры тратят 3-5 часов на сбор информации, сравнение характеристик, оценку соответствия требованиям компании.

**Как LLM помогает (с RAG):**
- RAG содержит: требования компании, текущий стек технологий, опыт команды, ограничения (бюджет, железо)
- LLM сравнивает варианты в контексте ВАШЕЙ инфраструктуры, а не абстрактно
- Выдает матрицу решений + рекомендацию с обоснованием

**Примеры запросов:**
```
Запрос: "Что выбрать для хранилища логов: Elasticsearch или ClickHouse? Объем 500GB/день, retention 90 дней"

RAG находит:
- Текущий стек: Python, PostgreSQL, Redis
- Опыт команды: 3 инженера знают SQL, 0 знают Lucene
- Оборудование: 5 серверов по 64GB RAM, SSD
- Требования ИБ: данные должны храниться on-premise

LLM генерирует сравнение:
---
# Сравнение: Elasticsearch vs ClickHouse для хранилища логов

## Краткая рекомендация
**ClickHouse** — лучший выбор для вашей инфраструктуры

## Сравнительная таблица

| Критерий | Elasticsearch | ClickHouse | Вес |
|----------|---------------|------------|-----|
| **Производительность записи** | 100K events/sec | 500K events/sec | 🔴 |
| **Сжатие данных** | 3x | 10-20x | 🔴 |
| **Требования к RAM** | 64GB (минимум) | 32GB (достаточно) | 🟡 |
| **Язык запросов** | DSL (сложный) | SQL (знаком команде) | 🔴 |
| **Горизонтальное масштабирование** | Отличное | Хорошее | 🟢 |
| **Full-text search** | Отличный | Базовый | 🟡 |
| **Retention управление** | Ручное (ILM) | Автоматическое (TTL) | 🟢 |

## Анализ в контексте вашей инфраструктуры

### ClickHouse (рекомендуется)
✅ **Плюсы для вас:**
- Ваша команда знает SQL → нулевое время обучения
- Сжатие 10-20x → 500GB/день превратятся в 25-50GB (экономия дискового пространства)
- 32GB RAM достаточно → укладываемся в текущее железо
- TTL для retention → автоматическое удаление старых данных без скриптов

❌ **Минусы:**
- Слабый full-text search (но для логов обычно ищут по полям, а не по тексту)
- Меньше готовых интеграций (но есть Vector, Fluent Bit)

### Elasticsearch
✅ **Плюсы:**
- Мощный full-text search
- Больше ready-made решений (ELK stack)

❌ **Минусы для вас:**
- Команда не знает Lucene DSL → 2-3 месяца обучения
- Требует 64GB RAM минимум → придется расширять железо (+800K рублей)
- Сжатие только 3x → 500GB/день = 165GB/день на диске (5TB за 90 дней)
- ILM политики нужно настраивать вручную

## Рекомендация
Используйте **ClickHouse** потому что:
1. Команда сразу продуктивна (SQL)
2. Экономия на железе: ~1.5млн рублей (не нужно расширять RAM и диски)
3. Простота эксплуатации: автоматический retention, меньше moving parts

## План внедрения
1. Развернуть ClickHouse кластер (3 ноды) — 2 дня
2. Настроить Vector/Fluent Bit для отправки логов — 1 день
3. Создать таблицы с TTL 90 дней — 2 часа
4. Миграция дашбордов из Grafana — 1 день

Итого: 5 рабочих дней
---
```

**Требуется для реализации:**

**RAG-компоненты:**
- Текущий стек технологий (Ansible inventory, documentation)
- Матрица навыков команды (HR data, surveys)
- Требования ИБ и compliance (политики безопасности)
- Ограничения инфраструктуры (CPU, RAM, disk, network)
- История решений (Architecture Decision Records - ADR)

**Формат данных в RAG:**
```json
{
  "type": "infrastructure_constraint",
  "category": "hardware",
  "content": "5 серверов: AMD EPYC 7543, 64GB RAM, 2TB NVMe SSD, 10Gbit network"
},
{
  "type": "team_skill",
  "content": "Python: 5 инженеров (expert), Go: 1 инженер (intermediate), SQL: 3 инженера (expert)"
},
{
  "type": "security_requirement",
  "content": "Все данные должны храниться on-premise, шифрование at-rest обязательно"
}
```

**Оценка эффекта:**
- ⏱️ Экономия времени: 4 часа research → 15 минут = −94%
- 💰 Экономия бюджета: обоснованный выбор экономит от 500K до 5M рублей (избежание неудачных технологий)
- 📉 Снижение рисков: учет реальных ограничений (навыки, железо) → меньше failed projects (−70%)
- 🎯 Качество решений: взвешенный анализ вместо "выбираем что популярнее"

**Пример реального применения:**

```python
# tech_comparison.py
import requests
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

qdrant = QdrantClient(host="localhost", port=6333)
embedding_model = SentenceTransformer('intfloat/multilingual-e5-large')

def compare_technologies(tech_a, tech_b, use_case, requirements):
    # 1. Получение контекста инфраструктуры из RAG
    context_queries = [
        f"текущий технологический стек",
        f"навыки команды {tech_a} {tech_b}",
        f"оборудование сервера ресурсы",
        f"требования безопасности"
    ]
    
    infrastructure_context = []
    for query in context_queries:
        query_vector = embedding_model.encode(query).tolist()
        results = qdrant.search(
            collection_name="infrastructure_docs",
            query_vector=query_vector,
            limit=2
        )
        infrastructure_context.extend([hit.payload['content'] for hit in results])
    
    context_text = "\n".join(infrastructure_context)
    
    # 2. Генерация сравнения
    prompt = f"""Ты архитектор IT-систем. Сравни две технологии для конкретного use case с учетом реальной инфраструктуры компании.

Use case: {use_case}
Технология A: {tech_a}
Технология B: {tech_b}

Требования: {requirements}

Контекст инфраструктуры компании:
{context_text}

Создай сравнение в формате:
1. **Краткая рекомендация** (какую выбрать и почему одной фразой)
2. **Сравнительная таблица** (критерии, оценки, вес критерия)
3. **Анализ в контексте вашей инфраструктуры**:
   - Плюсы/минусы технологии A ДЛЯ ВАС
   - Плюсы/минусы технологии B ДЛЯ ВАС
4. **Обоснование рекомендации** (3-5 главных причин)
5. **Оценка TCO** (если возможно)
6. **План внедрения** (шаги и сроки)

Сравнение:"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 2500,
        'temperature': 0.4
    })
    
    return response.json()['choices'][0]['text']

# Пример использования
comparison = compare_technologies(
    tech_a="Elasticsearch",
    tech_b="ClickHouse",
    use_case="Хранилище логов приложений и систем",
    requirements="500GB/день, retention 90 дней, полнотекстовый поиск желателен"
)

print(comparison)

# Сохранение в Architecture Decision Record
with open(f"ADR-{datetime.now().strftime('%Y%m%d')}-log-storage.md", 'w') as f:
    f.write(f"# ADR: Выбор хранилища логов\n\n")
    f.write(f"Дата: {datetime.now()}\n\n")
    f.write(comparison)
```

---

### 🔵 Блок 3: С MCP (высокая сложность внедрения)

---

## Сценарий 12: Автоматическое реагирование на инциденты мониторинга через MCP

**Текущая проблема:**
Alertmanager (Prometheus) отправляет алерты (CPU high, disk full, service down). Инженер получает уведомление в 3 AM, логинится, выполняет стандартные действия (перезапуск, очистка, масштабирование). Занимает 15-30 минут, нарушается сон.

**Как LLM помогает (с MCP):**
- MCP сервер предоставляет инструменты: restart_service, clear_disk, scale_deployment, check_logs
- LLM получает алерт → анализирует → выполняет действия через MCP → документирует
- Автоматизация 60-80% типовых инцидентов без участия человека

**Примеры запросов:**

```
Алерт из Prometheus Alertmanager:
{
  "alert": "DiskSpaceHigh",
  "instance": "app-server-02",
  "value": "92%",
  "severity": "warning"
}

LLM анализирует + действует через MCP:

1. [MCP: check_disk_usage]
   → /var/log занимает 45GB (старые логи приложения)

2. [Решение LLM]
   → Безопасно удалить логи старше 30 дней

3. [MCP: execute_command]
   → find /var/log/myapp -name "*.log" -mtime +30 -delete

4. [MCP: check_disk_usage]
   → Диск освобожден: 67% использовано

5. [MCP: send_notification]
   → Slack #ops: "✓ Автоматически решен инцидент DiskSpaceHigh на app-server-02. Удалено 25GB старых логов. Диск: 92% → 67%"

6. [MCP: create_ticket]
   → Создан тикет OPS-5678 с описанием действий
```

**Требуется для реализации:**

**MCP серверы (инструменты):**

1. **Infrastructure MCP** — управление инфраструктурой
   ```python
   # Tools:
   - restart_service(host, service_name)
   - stop_service(host, service_name)
   - check_service_status(host, service_name)
   - execute_command(host, command, safe_mode=True)
   - check_disk_usage(host, path)
   - check_logs(host, service, lines=100)
   ```

2. **Kubernetes MCP** — для кластеров K8s
   ```python
   # Tools:
   - scale_deployment(namespace, deployment, replicas)
   - restart_pod(namespace, pod_name)
   - get_pod_logs(namespace, pod_name, lines)
   - describe_pod(namespace, pod_name)
   ```

3. **Notification MCP** — уведомления
   ```python
   # Tools:
   - send_slack(channel, message)
   - send_email(to, subject, body)
   - create_pagerduty_incident(title, description)
   ```

4. **Ticketing MCP** — документирование
   ```python
   # Tools:
   - create_ticket(title, description, priority)
   - update_ticket(ticket_id, comment)
   - close_ticket(ticket_id, resolution)
   ```

**Архитектура с MCP:**
```
┌─────────────────┐
│ Prometheus/     │
│ Alertmanager    │
└────────┬────────┘
         │ webhook
         ▼
┌─────────────────┐
│ LLM Orchestrator│ ← Анализ алерта
│ (Python app)    │   Выбор действий
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LLM (GigaChat)  │ ← Reasoning + tool selection
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│          MCP Server Manager             │
├─────────────┬──────────────┬────────────┤
│ Infra MCP   │ K8s MCP      │ Notif MCP  │
│ (Ansible)   │ (kubectl)    │ (Slack API)│
└─────────────┴──────────────┴────────────┘
         │
         ▼
┌─────────────────┐
│ Infrastructure  │
└─────────────────┘
```

**Безопасность MCP:**
- Whitelist разрешенных команд (только read-only + safe operations)
- Dry-run mode для критических действий (предпросмотр перед выполнением)
- Approval workflow для деструктивных операций (требуется подтверждение инженера)
- Полное журналирование всех MCP вызовов с user/timestamp/command

**Формат MCP tool definition:**
```json
{
  "name": "restart_service",
  "description": "Перезапускает systemd сервис на указанном хосте",
  "parameters": {
    "host": {"type": "string", "description": "Hostname или IP"},
    "service_name": {"type": "string", "description": "Имя systemd сервиса"}
  },
  "safety_level": "medium",
  "requires_approval": false
}
```

**Оценка эффекта:**
- ⏱️ Экономия времени: 25 мин ручной работы → 2 мин автоматически = −92%
- 🌙 Улучшение work-life balance: −80% ночных вызовов инженеров
- 📊 Улучшение SLA: MTTR с 20 минут до 3 минут (−85%)
- 🤖 Автоматизация: 60-80% типовых инцидентов решаются без человека

**Пример реального применения:**

```python
# incident_responder.py
from flask import Flask, request
import requests
import json

app = Flask(__name__)
LLM_API = "http://llm-api:8000/v1/messages"
MCP_TOOLS = load_mcp_tools()  # Загрузка определений MCP tools

@app.route('/webhook/alertmanager', methods=['POST'])
def handle_alert():
    alerts = request.json['alerts']
    
    for alert in alerts:
        if alert['status'] == 'firing':
            response = respond_to_incident(alert)
            log_incident(alert, response)
    
    return '', 200

def respond_to_incident(alert):
    # 1. Формирование запроса к LLM с MCP tools
    messages = [
        {
            "role": "user",
            "content": f"""Ты система автоматического реагирования на инциденты.

Получен алерт:
- Alert: {alert['labels']['alertname']}
- Instance: {alert['labels']['instance']}
- Severity: {alert['labels']['severity']}
- Description: {alert['annotations']['description']}
- Value: {alert['annotations'].get('value', 'N/A')}

Проанализируй инцидент и выполни необходимые действия:
1. Диагностика (используй check_* tools)
2. Решение проблемы (если это типовой инцидент)
3. Уведомление команды
4. Создание тикета с описанием действий

Если проблема критическая или нетиповая - создай инцидент в PagerDuty для эскалации.

Действуй."""
        }
    ]
    
    # 2. Отправка запроса к LLM с включенными MCP tools
    llm_response = requests.post(LLM_API, json={
        "model": "gigachat-latest",
        "messages": messages,
        "tools": MCP_TOOLS,  # Список доступных MCP инструментов
        "max_tokens": 2000
    })
    
    response_data = llm_response.json()
    
    # 3. Обработка ответа LLM (tool calls)
    result = {"actions": [], "summary": ""}
    
    for content_block in response_data['content']:
        if content_block['type'] == 'tool_use':
            # LLM решил использовать MCP tool
            tool_result = execute_mcp_tool(
                content_block['name'],
                content_block['input']
            )
            result['actions'].append({
                'tool': content_block['name'],
                'input': content_block['input'],
                'result': tool_result
            })
        
        elif content_block['type'] == 'text':
            result['summary'] = content_block['text']
    
    return result

def execute_mcp_tool(tool_name, parameters):
    """Выполнение MCP tool через соответствующий MCP сервер"""
    
    # Маршрутизация на нужный MCP сервер
    if tool_name.startswith('k8s_'):
        mcp_server = "http://k8s-mcp:8001"
    elif tool_name.startswith('infra_'):
        mcp_server = "http://infra-mcp:8002"
    elif tool_name.startswith('notify_'):
        mcp_server = "http://notify-mcp:8003"
    else:
        raise ValueError(f"Unknown tool: {tool_name}")
    
    # Вызов MCP сервера
    response = requests.post(f"{mcp_server}/execute", json={
        'tool': tool_name,
        'parameters': parameters
    })
    
    return response.json()

def log_incident(alert, response):
    """Журналирование инцидента и действий"""
    incident_log = {
        'timestamp': alert['startsAt'],
        'alert': alert['labels']['alertname'],
        'instance': alert['labels']['instance'],
        'actions_taken': response['actions'],
        'summary': response['summary']
    }
    
    # Сохранение в БД/Elasticsearch
    save_to_audit_log(incident_log)
    
    # Отправка в Slack
    notify_slack(f"🤖 Автоматически обработан инцидент {alert['labels']['alertname']}\n{response['summary']}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
```

**Пример MCP сервера (Infrastructure):**

```python
# infra_mcp_server.py
from flask import Flask, request, jsonify
import subprocess
import paramiko

app = Flask(__name__)

# Whitelist безопасных команд
SAFE_COMMANDS = {
    'check_disk': 'df -h',
    'check_memory': 'free -h',
    'check_service': 'systemctl status {service}',
    'list_large_files': 'du -sh /var/log/* | sort -rh | head -10'
}

SAFE_OPERATIONS = [
    'restart_service',
    'check_disk_usage',
    'check_logs',
    'clean_old_logs'
]

@app.route('/execute', methods=['POST'])
def execute_tool():
    data = request.json
    tool_name = data['tool']
    params = data['parameters']
    
    # Проверка безопасности
    if tool_name not in SAFE_OPERATIONS:
        return jsonify({'error': 'Tool not whitelisted'}), 403
    
    # Выполнение tool
    if tool_name == 'check_disk_usage':
        result = check_disk_usage(params['host'], params.get('path', '/'))
    
    elif tool_name == 'restart_service':
        result = restart_service(params['host'], params['service_name'])
    
    elif tool_name == 'clean_old_logs':
        result = clean_old_logs(params['host'], params['path'], params['days'])
    
    else:
        result = {'error': 'Tool not implemented'}
    
    # Журналирование
    log_mcp_call(tool_name, params, result)
    
    return jsonify(result)

def check_disk_usage(host, path):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username='automation', key_filename='/root/.ssh/id_rsa')
    
    stdin, stdout, stderr = ssh.exec_command(f'df -h {path}')
    output = stdout.read().decode()
    
    # Парсинг вывода
    lines = output.strip().split('\n')
    if len(lines) > 1:
        usage_line = lines[1].split()
        return {
            'path': path,
            'size': usage_line[1],
            'used': usage_line[2],
            'available': usage_line[3],
            'use_percent': usage_line[4],
            'status': 'ok'
        }
    
    return {'error': 'Failed to parse df output'}

def restart_service(host, service_name):
    # Использование Ansible для безопасного перезапуска
    playbook = f"""
---
- hosts: {host}
  tasks:
    - name: Restart service
      systemd:
        name: {service_name}
        state: restarted
    """
    
    result = subprocess.run(
        ['ansible-playbook', '-'],
        input=playbook.encode(),
        capture_output=True
    )
    
    if result.returncode == 0:
        return {'status': 'success', 'message': f'Service {service_name} restarted'}
    else:
        return {'status': 'error', 'message': result.stderr.decode()}

def clean_old_logs(host, path, days):
    # Dry-run сначала
    command = f"find {path} -name '*.log' -mtime +{days}"
    
    ssh = paramiko.SSHClient()
    ssh.connect(host, username='automation', key_filename='/root/.ssh/id_rsa')
    
    stdin, stdout, stderr = ssh.exec_command(command)
    files_to_delete = stdout.read().decode().strip().split('\n')
    
    if not files_to_delete or files_to_delete == ['']:
        return {'status': 'success', 'message': 'No files to delete', 'deleted_count': 0}
    
    # Реальное удаление
    delete_command = f"find {path} -name '*.log' -mtime +{days} -delete"
    stdin, stdout, stderr = ssh.exec_command(delete_command)
    
    return {
        'status': 'success',
        'message': f'Deleted {len(files_to_delete)} log files',
        'deleted_count': len(files_to_delete),
        'freed_space': '~X GB'  # Можно вычислить точно
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8002)
```

---

## Сценарий 13: Автоматическое создание и применение Ansible playbooks через MCP

**Текущая проблема:**
Получена задача: "Установи PostgreSQL 15 на 5 новых серверов, настрой репликацию, добавь в мониторинг". Инженер пишет playbook 2-3 часа, тестирует, применяет. Если ошибка — правит и перезапускает.

**Как LLM помогает (с MCP):**
- LLM генерирует Ansible playbook из текстового описания
- MCP инструменты: validate_playbook, run_playbook_check, apply_playbook, rollback
- LLM применяет playbook, анализирует ошибки, автоматически исправляет и переприменяет

**Примеры запросов:**

```
Задача: "Установи PostgreSQL 15 на серверы db-[01-05], настрой master-slave репликацию (db-01 = master), добавь в Prometheus node_exporter"

Workflow LLM + MCP:

1. [LLM генерирует playbook]
   → 150 строк YAML (install, configure replication, setup monitoring)

2. [MCP: validate_playbook]
   → ansible-playbook --syntax-check
   → Результат: ✓ Синтаксис корректен

3. [MCP: run_playbook_check]
   → ansible-playbook --check (dry-run)
   → Результат: Warning - переменная replication_password не установлена

4. [LLM исправляет]
   → Добавляет запрос пароля через ansible-vault

5. [MCP: apply_playbook]
   → ansible-playbook -i inventory playbook.yml
   → Выполнение... 

6. [Ошибка на db-03]
   → TASK [Install PostgreSQL] failed: Package not found

7. [LLM анализирует]
   → db-03 использует другой дистрибутив (CentOS вместо Ubuntu)
   → Исправляет playbook (добавляет when: ansible_os_family == "Debian")

8. [MCP: apply_playbook]
   → Retry на db-03
   → Результат: ✓ Все 5 серверов настроены успешно

9. [MCP: run_tests]
   → Проверка репликации: psql -c "SELECT * FROM pg_stat_replication"
   → Проверка мониторинга: curl http://db-01:9100/metrics
   → Результат: ✓ Все тесты пройдены

10. [MCP: create_documentation]
    → Создан тикет с описанием установки
    → Обновлена inventory documentation
```

**Требуется для реализации:**

**MCP серверы:**

1. **Ansible MCP**
   ```python
   Tools:
   - generate_playbook(description, hosts, requirements)
   - validate_playbook(playbook_content)
   - run_playbook_check(playbook_path, inventory)  # dry-run
   - apply_playbook(playbook_path, inventory, tags=None)
   - rollback_playbook(playbook_path, inventory)
   - get_playbook_facts(hosts)
   ```

2. **Testing MCP**
   ```python
   Tools:
   - run_serverspec_tests(host, test_suite)
   - check_service_health(host, service)
   - verify_connectivity(source, destination, port)
   ```

3. **Documentation MCP**
   ```python
   Tools:
   - update_inventory_doc(hosts, role, description)
   - create_runbook(title, steps)
   - update_cmdb(hosts, attributes)
   ```

**Архитектура:**
```
┌──────────────┐
│    User      │ "Установи PostgreSQL на 5 серверов"
└──────┬───────┘
       │
       ▼
┌──────────────┐
│     LLM      │ Генерирует playbook
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│      Ansible MCP             │
├──────────────┬───