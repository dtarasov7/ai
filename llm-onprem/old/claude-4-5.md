деструктивных действий ВСЕГДА запрашивай подтверждение с обоснованием.

Начинай расследование."""
        }
    ]
    
    # Итеративное расследование
    for iteration in range(15):
        response = requests.post(LLM_API, json={
            "model": "gigachat-latest",
            "messages": messages,
            "tools": load_soar_mcp_tools(),
            "max_tokens": 3000
        })
        
        response_data = response.json()
        
        # Обработка tool calls
        tool_results = []
        for content_block in response_data['content']:
            if content_block['type'] == 'tool_use':
                tool_name = content_block['name']
                tool_input = content_block['input']
                
                print(f"\n[{iteration+1}] 🔧 {tool_name}")
                print(f"    Input: {json.dumps(tool_input, indent=2)}")
                
                # Проверка на деструктивные действия
                if tool_name in ['isolate_host', 'block_ip', 'disable_user_account']:
                    approval = request_approval(tool_name, tool_input, investigation_log)
                    
                    if not approval:
                        tool_result = {'status': 'cancelled', 'reason': 'Approval denied'}
                        print(f"    ❌ Action cancelled by analyst")
                    else:
                        tool_result = execute_soar_mcp(tool_name, tool_input)
                        print(f"    ✓ Executed with approval")
                else:
                    tool_result = execute_soar_mcp(tool_name, tool_input)
                    print(f"    Result: {json.dumps(tool_result, indent=2)[:200]}...")
                
                investigation_log.append({
                    'timestamp': datetime.now().isoformat(),
                    'tool': tool_name,
                    'input': tool_input,
                    'result': tool_result
                })
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block['id'],
                    "content": json.dumps(tool_result)
                })
            
            elif content_block['type'] == 'text':
                print(f"\n[LLM Analysis]\n{content_block['text']}\n")
                
                # Проверка на завершение расследования
                if 'Расследование завершено' in content_block['text'] or \
                   'Investigation complete' in content_block['text']:
                    save_investigation_report(alert, investigation_log, content_block['text'])
                    return {
                        'status': 'completed',
                        'log': investigation_log,
                        'summary': content_block['text']
                    }
        
        if not tool_results:
            break
        
        messages.append({"role": "assistant", "content": response_data['content']})
        messages.append({"role": "user", "content": tool_results})
    
    return {'status': 'incomplete', 'log': investigation_log}

def request_approval(action, params, context):
    """Запрос подтверждения у аналитика для деструктивных действий"""
    print("\n" + "="*60)
    print(f"⚠️  APPROVAL REQUIRED: {action}")
    print("="*60)
    print(f"Parameters: {json.dumps(params, indent=2)}")
    print(f"\nContext: {len(context)} investigation steps completed")
    print("\nApprove this action? [Y/N]: ", end='')
    
    # В реальной системе - через web UI или Slack interactive button
    response = input().strip().upper()
    return response == 'Y'

def save_investigation_report(alert, log, summary):
    """Сохранение отчета о расследовании"""
    report = {
        'alert': alert,
        'investigation_log': log,
        'summary': summary,
        'timestamp': datetime.now().isoformat()
    }
    
    filename = f"investigation_{alert['host']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(f"/var/log/soar/{filename}", 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✓ Investigation report saved: {filename}")

# Использование
alert = {
    'rule_name': 'Suspicious PowerShell Execution',
    'host': 'DESKTOP-USER01',
    'severity': 'high',
    'description': 'Encoded PowerShell command detected',
    'timestamp': '2024-12-07T15:23:41Z'
}

result = investigate_security_alert(alert)
```

---

## Сценарий 17: Проектирование архитектуры решений с учетом требований

**Текущая проблема:**
Задача: "Нужна система для обработки 10K запросов/сек с latency <100ms". Архитектор тратит 5-8 часов: выбор компонентов, проектирование архитектуры, оценка capacity, создание диаграмм.

**Как LLM помогает (с RAG):**
- RAG: текущий стек, успешные паттерны архитектуры, ограничения инфраструктуры
- LLM проектирует архитектуру с учетом требований и контекста компании
- Генерирует: архитектурные диаграммы (PlantUML/Mermaid), capacity planning, cost estimation

**Примеры запросов:**

```
Требования: "Разработать систему обработки платежей: 10K TPS, latency <100ms, PCI DSS compliance, 99.99% availability"

Workflow LLM + RAG:

1. [LLM анализирует требования]
   → Функциональные: payment processing, fraud detection, notifications
   → Non-functional: 10K TPS, <100ms latency, high availability, compliance

2. [RAG: текущий стек]
   → Найдено: используем PostgreSQL, Redis, Python, Kubernetes

3. [RAG: compliance требования]
   → Найдено: PCI DSS требует шифрование, audit logging, network segmentation

4. [LLM проектирует архитектуру]
   → API Gateway (rate limiting, auth) 
   → Payment Service (Python FastAPI, stateless)
   → Fraud Detection Service (ML model)
   → PostgreSQL (transactional data, encrypted)
   → Redis (caching, session storage)
   → Message Queue (async notifications)
   → Audit Log Service (compliance)

5. [LLM генерирует capacity planning]
   → 10K TPS = 10000 req/sec
   → При latency budget 100ms: можно обработать 1 req в 100ms
   → Нужно: 10000 / (1000/100) = 1000 параллельных workers
   → Payment Service: 10 pods × 100 workers = 1000 workers
   → PostgreSQL: master + 2 read replicas (read-heavy workload)
   → Redis: 3-node cluster (HA)

6. [LLM создает диаграмму PlantUML]

```plantuml
@startuml
!define RECTANGLE
