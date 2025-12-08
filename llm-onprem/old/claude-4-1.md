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
