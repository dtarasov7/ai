prompt = f"""Ты эксперт по кибербезопасности. Проанализируй код на уязвимости:
- SQL/NoSQL injection
- XSS (Cross-Site Scripting)
- CSRF
- Hardcoded secrets (пароли, API ключи)
- Небезопасные конфигурации (SSL verification disabled, etc.)
- Path traversal
- Command injection

Для каждой уязвимости укажи:
1. Тип уязвимости
2. Номер строки
3. Описание риска
4. Код исправления

Код:
```
{code}
```

Анализ:"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 1500,
        'temperature': 0.2  # Низкая temperature для точности
    })
    
    return response.json()['choices'][0]['text']

# .gitlab-ci.yml
# security-scan:
#   script:
#     - python security_scanner.py src/app.py
#     - if grep -q "КРИТИЧЕСКАЯ" report.txt; then exit 1; fi
```

---

## Сценарий 7: Создание инструкций для пользователей

**Текущая проблема:**
IT-служба получает повторяющиеся вопросы (как подключиться к VPN, как настроить почту, как запросить доступ). Инженеры тратят 20-30 минут на создание инструкции.

**Как LLM помогает:**
- Генерирует пошаговые инструкции с скриншотами (описание мест для скриншотов)
- Адаптирует сложность под аудиторию (technical vs non-technical)
- Создает версии для разных ОС (Windows, macOS, Linux)

**Примеры запросов:**
```
# Запрос:
"Создай инструкцию для сотрудников: как подключиться к корпоративному VPN OpenVPN на Windows. Целевая аудитория - нетехнические сотрудники"

# Ответ LLM:
# Подключение к корпоративному VPN

## Требования
- Компьютер с Windows 10/11
- Логин и пароль (получить у IT-отдела)
- Конфигурационный файл client.ovpn (прикреплен к письму)

## Шаг 1: Установка OpenVPN
1. Скачайте установщик с официального сайта: https://openvpn.net/community-downloads/
2. Запустите установщик от имени администратора
3. Нажмите "Next" → "I Agree" → "Next" → "Install"
4. Дождитесь завершения установки

[Место для скриншота: окно установщика]

## Шаг 2: Настройка конфигурации
1. Откройте папку: C:\Program Files\OpenVPN\config
2. Скопируйте файл client.ovpn в эту папку
3. Если система запросит права администратора - подтвердите

[Место для скриншота: проводник с файлом]

## Шаг 3: Подключение
1. Найдите значок OpenVPN GUI в системном трее (правый нижний угол)
2. Нажмите правой кнопкой → "Connect"
3. Введите ваш логин и пароль
4. Дождитесь появления зеленого значка (подключено)

[Место для скриншота: системный трей с зеленым значком]

## Проверка подключения
Откройте браузер и перейдите на http://internal.company.com
Если страница открылась - VPN работает корректно.

## Проблемы?
Свяжитесь с IT-отделом: helpdesk@company.com или +7 (495) 123-45-67
```

**Требуется для реализации:**
- Web-интерфейс для ввода темы инструкции
- API LLM
- Шаблоны для разных типов инструкций
- Опционально: интеграция с wiki/Confluence для публикации

**Оценка эффекта:**
- ⏱️ Экономия времени: 30 мин → 5 мин = −83% времени
- 📉 Снижение нагрузки на helpdesk: −30% повторяющихся обращений
- 📚 Улучшение качества документации: единообразие, полнота

**Пример реального применения:**
```python
# instruction_generator.py
import requests

def generate_instruction(topic, audience, os_list):
    os_text = ", ".join(os_list) if len(os_list) > 1 else os_list[0]
    
    prompt = f"""Создай подробную пошаговую инструкцию для сотрудников компании.

Тема: {topic}
Целевая аудитория: {audience}
Операционные системы: {os_text}

Требования к инструкции:
- Используй простой язык без жаргона
- Нумерованные шаги
- Отметь места для скриншотов как [Место для скриншота: описание]
- Добавь раздел "Проблемы?" с контактами IT-отдела
- Если инструкция для нескольких ОС - создай отдельные секции

Инструкция:"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 2000,
        'temperature': 0.4
    })
    
    return response.json()['choices'][0]['text']

# Интеграция с Confluence API
def publish_to_wiki(title, content, space_key='IT'):
    confluence_api = "https://wiki.company.com/rest/api/content"
    # ... код публикации ...

if __name__ == '__main__':
    instruction = generate_instruction(
        topic="Подключение к корпоративному VPN OpenVPN",
        audience="нетехнические сотрудники",
        os_list=["Windows", "macOS"]
    )
    print(instruction)
```

---

### 🟡 Блок 2: С RAG (средняя сложность внедрения)

---

## Сценарий 8: Интеллектуальный поиск по внутренней документации

**Текущая проблема:**
Инженеры тратят 15-45 минут на поиск информации в Confluence, Wiki, Google Docs. Поиск по ключевым словам дает нерелевантные результаты. Документация разрозненна.

**Как LLM помогает (с RAG):**
- RAG-база индексирует всю внутреннюю документацию (Confluence, SharePoint, локальные Markdown)
- Семантический поиск вместо keyword matching
- LLM синтезирует ответ из нескольких документов с указанием источников

**Примеры запросов:**
```
Запрос инженера: "Какой процесс согласования для открытия порта 443 на DMZ?"

RAG находит фрагменты из:
- Документ "Процессы ИБ.docx": раздел про firewall changes
- Confluence страница "DMZ Network Policy" 
- Ticket template в Jira

LLM генерирует ответ:
"Процесс согласования открытия порта 443 на DMZ:

1. Создайте заявку в Jira (проект SEC, тип 'Firewall Change')
2. Укажите: source IP, destination IP, порт, обоснование
3. Заявка согласуется с:
   - Руководителем вашего отдела
   - Службой ИБ (SOC)
   - Сетевым архитектором
4. После согласования выполняется в течение 2 рабочих дней
5. Изменение тестируется и документируется в change log

Источники:
- Процессы ИБ.docx, стр. 15
- https://wiki.company.com/DMZ_Network_Policy
- Jira template: SEC-FIREWALL-CHANGE"
```

**Требуется для реализации:**

**RAG-компоненты:**
- **Vector database:** Qdrant, Milvus или Weaviate (open-source)
- **Embedding model:** multilingual-e5-large (поддержка русского) или rubert-tiny
- **Document loader:** Unstructured.io для парсинга DOCX, PDF, HTML
- **Chunk strategy:** 500 токенов с overlap 50 токенов
- **Retrieval:** Top-5 документов по cosine similarity

**Источники данных:**
- Confluence (API: export pages as HTML/Markdown)
- SharePoint/OneDrive (Microsoft Graph API)
- Локальные .md/.txt файлы (file system scan)
- Процедуры ИБ (.docx, .pdf)

**Периодичность обновления:**
- Полная переиндексация: 1 раз в неделю
- Инкрементальная: каждые 6 часов (мониторинг изменений через API)

**Формат хранения:**
```json
{
  "doc_id": "confluence_page_12345",
  "title": "DMZ Network Policy",
  "chunk": "Процесс согласования firewall changes...",
  "metadata": {
    "source": "https://wiki.company.com/pages/12345",
    "updated": "2024-11-15",
    "access_level": "internal"
  },
  "embedding": [0.123, -0.456, ...]
}
```

**Оценка эффекта:**
- ⏱️ Экономия времени: 30 мин поиска → 2 мин = −93% времени
- 📉 Снижение нагрузки на senior: −40% консультаций "где найти документ X"
- 📊 Улучшение onboarding: новые сотрудники находят ответы самостоятельно (−50% времени адаптации)
- 🔍 Повышение использования документации: +60% обращений к wiki

**Пример реального применения:**

```python
# rag_documentation_search.py
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import requests

# Инициализация
qdrant = QdrantClient(host="localhost", port=6333)
embedding_model = SentenceTransformer('intfloat/multilingual-e5-large')

def search_documentation(query):
    # 1. Embedding запроса
    query_vector = embedding_model.encode(query).tolist()
    
    # 2. Поиск в векторной БД
    search_results = qdrant.search(
        collection_name="company_docs",
        query_vector=query_vector,
        limit=5
    )
    
    # 3. Формирование контекста для LLM
    context = "\n\n---\n\n".join([
        f"Источник: {hit.payload['title']} ({hit.payload['source']})\n{hit.payload['chunk']}"
        for hit in search_results
    ])
    
    # 4. Генерация ответа LLM
    prompt = f"""Ты помощник IT-службы. Ответь на вопрос сотрудника, используя информацию из документации.
Обязательно укажи источники (название документа и ссылку).

Вопрос: {query}

Документация:
{context}

Ответ:"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 800,
        'temperature': 0.3
    })
    
    answer = response.json()['choices'][0]['text']
    return answer

# Пример использования
if __name__ == '__main__':
    query = "Какой процесс согласования для открытия порта 443 на DMZ?"
    answer = search_documentation(query)
    print(answer)
```

**Скрипт индексации документов:**
```python
# index_documents.py
from atlassian import Confluence
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

# Подключение к Confluence
confluence = Confluence(url='https://wiki.company.com', 
                       username='bot@company.com', 
                       password='token')

# Инициализация
qdrant = QdrantClient(host="localhost", port=6333)
embedding_model = SentenceTransformer('intfloat/multilingual-e5-large')
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

# Создание коллекции
qdrant.recreate_collection(
    collection_name="company_docs",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
)

# Индексация
def index_confluence_space(space_key):
    pages = confluence.get_all_pages_from_space(space_key, expand='body.storage')
    
    for page in pages:
        # Извлечение текста
        content = page['body']['storage']['value']
        # Удаление HTML тегов (простейший вариант)
        text = re.sub('<[^<]+?>', '', content)
        
        # Разбиение на чанки
        chunks = text_splitter.split_text(text)
        
        # Индексация каждого чанка
        for i, chunk in enumerate(chunks):
            embedding = embedding_model.encode(chunk).tolist()
            
            qdrant.upsert(
                collection_name="company_docs",
                points=[{
                    "id": f"{page['id']}_chunk_{i}",
                    "vector": embedding,
                    "payload": {
                        "title": page['title'],
                        "chunk": chunk,
                        "source": f"https://wiki.company.com/pages/{page['id']}",
                        "updated": page['version']['when']
                    }
                }]
            )
        
        print(f"✓ Indexed: {page['title']} ({len(chunks)} chunks)")

index_confluence_space("IT")
index_confluence_space("SECURITY")
```

---

## Сценарий 9: Анализ инцидентов ИБ с контекстом из SIEM

**Текущая проблема:**
SOC-аналитики получают алерты из SIEM (Wazuh, OSSIM): IP попытался зайти 100 раз, обнаружена anomaly. Нужно понять: это атака или false positive? Анализ занимает 15-40 минут на инцидент.

**Как LLM помогает (с RAG):**
- RAG содержит базу знаний: MITRE ATT&CK, CVE, прошлые инциденты, whitelists
- LLM анализирует алерт + контекст → классифицирует угрозу, предлагает действия
- Автоматизация triage (сортировка critical/high/medium/low)

**Примеры запросов:**
```json
Алерт из SIEM:
{
  "timestamp": "2024-12-07T15:23:41Z",
  "event": "Multiple failed SSH login attempts",
  "source_ip": "203.0.113.45",
  "destination": "db-prod-01",
  "count": 127,
  "username": "root"
}

RAG находит:
1. IP 203.0.113.45 в базе threat intelligence (известный сканер)
2. MITRE ATT&CK: T1110.001 (Brute Force: Password Guessing)
3. Прошлый инцидент: аналогичная атака с этого IP (2024-11-20)
4. Whitelist: IP отсутствует в whitelist

LLM генерирует анализ:
"🔴 КРИТИЧЕСКИЙ ИНЦИДЕНТ: Brute-force атака на SSH

Анализ:
- Источник: 203.0.113.45 (известный сканер, зафиксирован в threat feeds)
- Цель: db-prod-01 (продуктовая база данных)
- Тип атаки: Brute Force (MITRE ATT&CK: T1110.001)
- 127 неудачных попыток входа за 2 минуты
- История: аналогичная атака 17 дней назад

Рекомендации:
1. СРОЧНО: Заблокировать IP 203.0.113.45 на firewall
2. Проверить логи на предмет успешных входов
3. Убедиться, что SSH доступен только через VPN
4. Настроить fail2ban для автоблокировки
5. Создать тикет SEC-1234 для расследования

Приоритет: CRITICAL
Предполагаемое время обработки: 1 час"
```

**Требуется для реализации:**

**RAG-компоненты:**
- **Vector DB:** Qdrant для хранения threat intelligence, CVE, MITRE ATT&CK
- **Источники данных:**
  - MITRE ATT&CK framework (JSON export)
  - CVE database (NVD JSON feeds)
  - Threat intelligence feeds (AlienVault OTX, CISA alerts)
  - История инцидентов (экспорт из SIEM/ticketing system)
  - Whitelists/blacklists (CSV/JSON)

**Интеграция с SIEM:**
- Webhook из Wazuh/OSSIM в API LLM-системы
- Парсинг алертов (JSON)
- Обогащение данными (GeoIP, WHOIS, VirusTotal API)

**Формат данных:**
```json
{
  "alert_id": "wazuh_12345",
  "raw_alert": {...},
  "enrichment": {
    "geoip": {"country": "CN", "city": "Beijing"},
    "virustotal": {"malicious": 5, "suspicious": 2},
    "mitre_tactics": ["Credential Access"]
  },
  "rag_context": [...]
}
```

**Оценка эффекта:**
- ⏱️ Экономия времени: 30 мин анализа → 3 мин = −90% времени на triage
- 🎯 Точность классификации: 85-90% (снижение false positives на 60%)
- 📊 Улучшение SLA: MTTR для инцидентов −40%
- 🔒 Снижение рисков: быстрое реагирование на critical threats (с 1 часа до 5 минут)

**Пример реального применения:**

```python
# siem_incident_analyzer.py
from flask import Flask, request, jsonify
import requests
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

app = Flask(__name__)
qdrant = QdrantClient(host="localhost", port=6333)
embedding_model = SentenceTransformer('intfloat/multilingual-e5-large')

# Webhook endpoint для SIEM
@app.route('/webhook/siem', methods=['POST'])
def analyze_alert():
    alert = request.json
    
    # 1. Обогащение данными
    enriched = enrich_alert(alert)
    
    # 2. Поиск в RAG (threat intelligence, MITRE ATT&CK)
    context = get_threat_context(enriched)
    
    # 3. Анализ LLM
    analysis = analyze_with_llm(enriched, context)
    
    # 4. Отправка в ticketing system (если critical)
    if analysis['priority'] == 'CRITICAL':
        create_ticket(analysis)
    
    return jsonify(analysis)

def enrich_alert(alert):
    # GeoIP lookup
    ip = alert['source_ip']
    geoip = requests.get(f'https://ipapi.co/{ip}/json/').json()
    
    # VirusTotal check (если есть API key)
    vt_response = requests.get(
        f'https://www.virustotal.com/api/v3/ip_addresses/{ip}',
        headers={'x-apikey': 'YOUR_VT_API_KEY'}
    ).json()
    
    return {
        **alert,
        'geoip': geoip,
        'virustotal': vt_response.get('data', {}).get('attributes', {})
    }

def get_threat_context(enriched_alert):
    # Формирование запроса для RAG
    query = f"""
    IP: {enriched_alert['source_ip']}
    Event: {enriched_alert['event']}
    Country: {enriched_alert['geoip'].get('country')}
    """
    
    query_vector = embedding_model.encode(query).tolist()
    
    # Поиск релевантных угроз
    results = qdrant.search(
        collection_name="threat_intelligence",
        query_vector=query_vector,
        limit=5
    )
    
    context = []
    for hit in results:
        context.append({
            'type': hit.payload['type'],  # mitre_attack, cve, past_incident
            'content': hit.payload['content'],
            'relevance': hit.score
        })
    
    return context

def analyze_with_llm(enriched, context):
    context_text = "\n\n".join([
        f"[{c['type']}] {c['content']}"
        for c in context
    ])
    
    prompt = f"""Ты аналитик SOC (Security Operations Center). Проанализируй инцидент ИБ.

Алерт:
{enriched['event']}
Source IP: {enriched['source_ip']}
Страна: {enriched['geoip'].get('country')}
Count: {enriched.get('count', 1)}

Контекст из базы знаний:
{context_text}

Выполни анализ:
1. Классифицируй угрозу (тип атаки, MITRE ATT&CK тактики)
2. Оцени критичность: CRITICAL/HIGH/MEDIUM/LOW
3. Определи: это реальная атака или false positive?
4. Предложи конкретные действия для реагирования

Формат ответа:
Тип угрозы: ...
MITRE ATT&CK: ...
Критичность: ...
Оценка: реальная атака / false positive
Рекомендации:
1. ...
2. ...
"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 1000,
        'temperature': 0.2
    })
    
    analysis_text = response.json()['choices'][0]['text']
    
    # Парсинг приоритета
    priority = 'MEDIUM'
    if 'CRITICAL' in analysis_text:
        priority = 'CRITICAL'
    elif 'HIGH' in analysis_text:
        priority = 'HIGH'
    
    return {
        'alert_id': enriched.get('id'),
        'analysis': analysis_text,
        'priority': priority,
        'timestamp': enriched['timestamp']
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

## Сценарий 10: Автоматическая генерация Runbook для типовых инцидентов

**Текущая проблема:**
При инцидентах (сервис упал, диск переполнен, сертификат истек) инженеры каждый раз заново вспоминают шаги. Runbook'и устаревают или отсутствуют. На создание уходит 1-2 часа.

**Как LLM помогает (с RAG):**
- RAG содержит историю похожих инцидентов + best practices
- LLM генерирует пошаговый runbook: диагностика → решение → проверка → документирование
- Runbook адаптируется под конкретную систему (из конфигурации в RAG)

**Примеры запросов:**
```
Запрос: "Создай runbook для инцидента: веб-сервер nginx на prod-web-01 не отвечает (502 Bad Gateway)"

RAG находит:
- Прошлые инциденты с nginx 502 (логи, решения)
- Документация инфраструктуры: prod-web-01 → backend: app-server-01:8080
- Best practices: проверка логов, перезапуск, мониторинг

LLM генерирует runbook:
---
# RUNBOOK: Nginx 502 Bad Gateway на prod-web-01

## Симптомы
- HTTP 502 Bad Gateway при обращении к https://app.company.com
- Nginx запущен, но не может достучаться до backend

## Диагностика

### Шаг 1: Проверка статуса nginx
```bash
ssh prod-web-01
systemctl status nginx
# Ожидается: active (running)
```

### Шаг 2: Проверка логов nginx
```bash
tail -f /var/log/nginx/error.log
# Ищем: "connect() failed (111: Connection refused) while connecting to upstream"
```

### Шаг 3: Проверка backend app-server
```bash
ssh app-server-01
systemctl status myapp
curl -I http://localhost:8080/health
```

## Решение

### Если backend не отвечает:
```bash
ssh app-server-01
systemctl restart myapp
# Ждем 30 секунд
systemctl status myapp
```

### Если проблема с сетью:
```bash
# Проверка firewall между nginx и backend
iptables -L -n | grep 8080
# Если порт заблокирован:
iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
```

## Проверка восстановления
```bash
curl -I https://app.company.com
# Ожидается: HTTP/2 200
```

## Мониторинг
- Наблюдать за метриками в Grafana: dashboard "Nginx Performance"
- Проверить логи в течение 15 минут

## Документирование
1. Обновить тикет в системе: описание проблемы, причина, решение
2. Если это новая проблема - добавить в Knowledge Base

## Эскалация
Если проблема не решена за 15 минут:
- Уведомить tech lead: @john.doe
- Созвать war room: #incident-response
---
```

**Требуется для реализации:**

**RAG-компоненты:**
- История инцидентов (экспорт из ticketing system, логи)
- Конфигурация инфраструктуры (inventory Ansible, CMDB)
- Best practices документы (wiki, runbooks)
- Логи мониторинга (Prometheus, Grafana)

**Интеграция:**
- Ticketing API (Jira, ServiceNow) для импорта/экспорта runbook
- Ansible dynamic inventory для получения актуальной конфигурации

**Формат хранения инцидентов:**
```json
{
  "incident_id": "INC-2024-1234",
  "title": "Nginx 502 Bad Gateway",
  "symptoms": "Web app не отвечает, 502 error",
  "root_cause": "Backend app crashed из-за OOM",
  "solution": "Перезапуск app, увеличение памяти",
  "resolution_time": "15 minutes",
  "tags": ["nginx", "502", "backend"]
}
```

**Оценка эффекта:**
- ⏱️ Экономия времени: 1.5 часа создание runbook → 10 минут = −90%
- 📉 MTTR: сокращение на 30-40% благодаря готовым runbook
- 📚 База знаний: автоматическое накопление опыта (каждый инцидент → runbook)
- 🎓 Onboarding: новые инженеры решают инциденты по runbook без эскалации

**Пример реального применения:**

```python
# runbook_generator.py
import requests
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

qdrant = QdrantClient(host="localhost", port=6333)
embedding_model = SentenceTransformer('intfloat/multilingual-e5-large')

def generate_runbook(incident_description, system_name):
    # 1. Поиск похожих инцидентов в RAG
    query_vector = embedding_model.encode(incident_description).tolist()
    
    similar_incidents = qdrant.search(
        collection_name="incident_history",
        query_vector=query_vector,
        limit=3
    )
    
    # 2. Получение конфигурации системы
    system_config = get_system_config(system_name)
    
    # 3. Формирование контекста
    context = format_context(similar_incidents, system_config)
    
    # 4. Генерация runbook через LLM
    prompt = f"""Создай детальный runbook для инцидента.

Инцидент: {incident_description}
Система: {system_name}

Контекст из прошлых инцидентов:
{context}

Конфигурация системы:
{system_config}

Создай runbook в формате:
# RUNBOOK: [название]
## Симптомы
## Диагностика (пошаговые команды с ожидаемым выводом)
## Реш