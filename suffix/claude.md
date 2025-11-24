Поскольку роль править нельзя, у вас есть несколько способов решить эту задачу. Рассмотрю наиболее эффективные подходы.

## Способ 1: Динамические переменные в `all.yml` (Самый простой)

Этот способ не требует изменения ни роли, ни плейбука. Вся логика находится в файле `group_vars/group1/all.yml`.

**Файл `group_vars/group1/all.yml`:**

```yaml
---
# Определяем наборы переменных для разных suffix
config_sets:
  dev:
    db_host: "db-dev.example.com"
    db_port: 5432
    app_debug: true
    log_level: "debug"
  stage:
    db_host: "db-stage.example.com"
    db_port: 5432
    app_debug: true
    log_level: "info"
  prod:
    db_host: "db-prod.example.com"
    db_port: 5432
    app_debug: false
    log_level: "error"

# Устанавливаем значения переменных динамически на основе suffix
# Если suffix не задан или не найден, используем 'dev' как значение по умолчанию
db_host: "{{ config_sets[suffix | default('dev')].db_host }}"
db_port: "{{ config_sets[suffix | default('dev')].db_port }}"
app_debug: "{{ config_sets[suffix | default('dev')].app_debug }}"
log_level: "{{ config_sets[suffix | default('dev')].log_level }}"
```

**Запуск:**
```bash
ansible-playbook playbook.yml -e "suffix=prod"
```

## Способ 2: Использование `set_fact` в плейбуке

Если первый способ не подходит (например, слишком много переменных), можно добавить задачу `set_fact` перед вызовом роли.

**Файл `group_vars/group1/all.yml`:**

```yaml
---
# Все возможные конфигурации
configurations:
  dev:
    db_host: "db-dev.example.com"
    db_port: 5432
    app_debug: true
    log_level: "debug"
    api_url: "https://api-dev.example.com"
  prod:
    db_host: "db-prod.example.com"
    db_port: 5432
    app_debug: false
    log_level: "error"
    api_url: "https://api.example.com"
```

**Плейбук:**

```yaml
---
- hosts: group1
  tasks:
    - name: Установка переменных на основе suffix
      set_fact:
        db_host: "{{ configurations[suffix].db_host }}"
        db_port: "{{ configurations[suffix].db_port }}"
        app_debug: "{{ configurations[suffix].app_debug }}"
        log_level: "{{ configurations[suffix].log_level }}"
        api_url: "{{ configurations[suffix].api_url }}"
      when: suffix is defined and suffix in configurations

  roles:
    - your_role_name
```

## Способ 3: Использование `include_vars` в плейбуке

Этот способ позволяет хранить конфигурации в отдельных файлах.

**Структура каталогов:**
```
.
├── playbook.yml
├── group_vars/
│   └── group1/
│       └── all.yml          # Общие переменные
└── env_configs/
    ├── dev.yml
    ├── stage.yml
    └── prod.yml
```

**Файл `env_configs/dev.yml`:**
```yaml
---
db_host: "db-dev.example.com"
db_port: 5432
app_debug: true
log_level: "debug"
```

**Файл `env_configs/prod.yml`:**
```yaml
---
db_host: "db-prod.example.com"
db_port: 5432
app_debug: false
log_level: "error"
```

**Плейбук:**
```yaml
---
- hosts: group1
  tasks:
    - name: Загрузка переменных для окружения
      include_vars: "env_configs/{{ suffix }}.yml"
      when: suffix is defined

  roles:
    - your_role_name
```

## Способ 4: Комбинированный подход с проверкой

Для большей надежности можно добавить проверку существования suffix и установку значений по умолчанию.

**Файл `group_vars/group1/all.yml`:**

```yaml
---
# Конфигурации для разных окружений
envs:
  dev:
    db_host: "localhost"
    db_port: 5432
    app_debug: true
  prod:
    db_host: "db.prod.com"
    db_port: 5432
    app_debug: false

# Значения по умолчанию
default_env: dev

# Выбор текущего окружения
current_env: "{{ suffix | default(default_env) }}"

# Финальные переменные с проверкой существования окружения
db_host: "{{ envs[current_env].db_host if current_env in envs else envs[default_env].db_host }}"
db_port: "{{ envs[current_env].db_port if current_env in envs else envs[default_env].db_port }}"
app_debug: "{{ envs[current_env].app_debug if current_env in envs else envs[default_env].app_debug }}"
```

## Рекомендация

**Я рекомендую использовать Способ 1**, так как он:
- Не требует изменения плейбука
- Не требует изменения роли
- Вся логика находится в одном месте
- Легко поддерживается и расширяется
- Работает "из коробки" с существующей структурой

Этот подход позволяет роли использовать переменные `db_host`, `app_debug` и т.д. напрямую, не зная о существовании `suffix` и логике выбора значений.
