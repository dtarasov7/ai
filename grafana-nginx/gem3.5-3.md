Отличный документ! Описание решения очень четкое, структурированное и понятное. Оно покрывает проблему, архитектуру, механизм работы и преимущества. Это прекрасная основа.

Проанализируем его и предложим улучшения, после чего я создам свой вариант кода.

---

### 1. Анализ и сильные стороны

Ваше описание уже на высоком уровне. Особенно хочется отметить:

*   **Четкая постановка проблемы:** Проблема мультитенантности в связке Grafana OSS + Prometheus — классическая, и вы ее точно сформулировали.
*   **Правильный выбор инструментария:** FastAPI + HTTPX — современный, асинхронный и производительный стек для подобных задач.
*   **Ключевой акцент на AST-парсинг:** Это самый важный технический аспект. Использование AST вместо регулярных выражений — единственно верный способ надежно анализировать PromQL и избегать уязвимостей (например, через вложенные запросы или функции).
*   **Хорошая архитектура:** Схема `Grafana -> Nginx -> Proxy -> Prometheus` является стандартной и правильной. Nginx берет на себя аутентификацию и терминирование TLS, а прокси занимается только своей основной задачей.
*   **Продуманные фичи:** Горячая перезагрузка конфига, логирование — это признаки зрелого подхода к разработке сервиса для реальной эксплуатации.

### 2. Предложения по улучшению

Хотя описание отличное, его можно дополнить, чтобы сделать решение еще более надежным, функциональным и готовым к производственному использованию.

#### Улучшение 1: Безопасность и управление доступом

*   **Проблема:** В текущей конфигурации список пользователей и их групп хранится в `config.yml`. Это создает дублирование с источником правды (например, LDAP/Active Directory) и требует ручной синхронизации.
*   **Улучшение:**
    1.  **Интеграция с источником групп:** Вместо статического маппинга `users -> groups` в YAML, прокси мог бы сам обращаться к LDAP или другому IdP. Получив `X-WEBAUTH-USER: bob`, он бы делал LDAP-запрос "в каких группах состоит bob?" и динамически применял правила. Это устраняет ручную синхронизацию.
    2.  **Правила по умолчанию (Default Deny):** Явно указать, что если пользователь или группа не найдены в конфигурации, доступ запрещается по умолчанию.

#### Улучшение 2: Гибкость правил

*   **Проблема:** Текущая структура правил (`labels`) позволяет проверять только одно условие (`instance` должен быть в списке). Реальные запросы могут быть сложнее, например, `...{app="backend", env="prod"}`.
*   **Улучшение:** Сделать структуру правил более гибкой.
    ```yaml
    # Старый вариант
    labels:
      instance: ["server-a1", "server-a2"]

    # Улучшенный вариант (поддержка AND-логики и Regex)
    rules:
      - allow:
          metrics: ["^http_requests_total$"]
          # Правило сработает, если ВСЕ указанные метки совпадут
          labels:
            job: ["prometheus"]
            instance: ["^server-a.*"] # Поддержка regex для значений меток
      - allow:
          metrics: ["^node_.*"]
          labels:
            env: ["prod"]
    ```
    Это позволит создавать более гранулярные и мощные правила доступа.

#### Улучшение 3: Полнота функциональности (Критически важно!)

*   **Проблема:** Описание фокусируется на проксировании запросов данных (`/api/v1/query`, `query_range`). Но Grafana для работы использует и другие эндпоинты Prometheus API, например:
    *   `/api/v1/series`: для поиска метрик по меткам.
    *   `/api/v1/labels`: для получения списка всех имен меток.
    *   `/api/v1/label/{name}/values`: для автодополнения значений меток в переменных дашборда.
*   **Угроза:** Если не фильтровать ответы этих эндпоинтов, **пользователь сможет увидеть запрещенные имена метрик и значения меток** через автодополнение в Grafana, даже если не сможет запросить сами данные. Это утечка метаданных.
*   **Улучшение:**
    1.  **Проксирование и фильтрация ответов:** Прокси должен перехватывать запросы к `/api/v1/series`, `/api/v1/label/.../values`, отправлять их в Prometheus, а затем **фильтровать полученный JSON-ответ**, удаляя из него все метрики и метки, к которым у пользователя нет доступа согласно его правилам. Это сложнее, чем валидация запроса, так как требует модификации ответа.

#### Улучшение 4: Наблюдаемость и эксплуатация (Observability & Operations)

*   **Проблема:** Прокси — критический компонент в цепочке доставки метрик. Если он работает медленно или падает, дашборды перестают работать. Важно понимать, что с ним происходит.
*   **Улучшение:**
    1.  **Собственные метрики:** Прокси должен предоставлять собственные метрики в формате Prometheus на эндпоинте `/metrics`. Например:
        *   `proxy_requests_total{status="allowed|denied", user="..."}` — счетчик обработанных запросов.
        *   `proxy_request_duration_seconds` — гистограмма времени ответа.
    2.  **Health Check:** Добавить эндпоинт `/health` или `/ready`, который будет возвращать `200 OK`, если сервис жив и готов принимать трафик. Это стандарт для работы в Kubernetes и других оркестраторах.
    3.  **Graceful Shutdown:** Корректно обрабатывать сигналы `SIGTERM` для плавного завершения работы без обрыва соединений.

---

### 3. Мой вариант кода прокси (с учетом улучшений)

Вот пример реализации на Python с использованием FastAPI. Этот код включает в себя:
*   Базовую логику из вашего описания (AST-парсинг).
*   Улучшенную структуру конфигурации.
*   Горячую перезагрузку по `SIGHUP`.
*   Логирование.
*   Health check эндпоинт.
*   Обработку `GET` и `POST` запросов.
*   Комментарии, объясняющие ключевые моменты, включая **упоминание о необходимости фильтрации метаданных**.

**Файловая структура:**
```
.
├── proxy.py
├── config.yml
└── requirements.txt
```

**`requirements.txt`**
```
fastapi
uvicorn[standard]
httpx
pyyaml
lark  # Зависимость для promql-parser
promql-parser
```

**`config.yml`**
```yaml
# Адрес вышестоящего Prometheus
prometheus_url: "http://localhost:9090"

# Заголовок, из которого извлекается имя пользователя
user_header: "X-Webauth-User"

# Правила доступа
access_rules:
  # Группа инженеров команды Alpha
  team-alpha:
    - description: "Доступ к метрикам своих приложений"
      metrics:
        - "^app_alpha_.*"
      required_labels:
        # Запросы к этим метрикам ДОЛЖНЫ содержать метку env,
        # и её значение должно быть одним из перечисленных.
        env: ["prod", "stage"]
        dc: ["dc1"]

  # Группа инженеров команды Beta
  team-beta:
    - description: "Доступ к метрикам http-серверов команды Beta"
      metrics:
        - "http_requests_total"
      required_labels:
        # Можно использовать регулярные выражения для значений
        instance: ["^beta-server-.*"]

  # Группа SRE, у которых есть доступ к метрикам хостов
  team-sre:
    - description: "Доступ ко всем node_exporter метрикам"
      metrics:
        - "^node_.*"
      # Нет required_labels, значит можно запрашивать любые метки

# Сопоставление пользователей и групп
users:
  alice:
    - team-alpha
  bob:
    - team-beta
  charlie:
    - team-alpha
    - team-sre
```

**`proxy.py`**
```python
import logging
import os
import signal
import re
from functools import lru_cache
from typing import Any, Dict, List, Set

import httpx
import yaml
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from promql_parser import parse

# --- Конфигурация логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("prometheus_proxy")

# --- Глобальные переменные ---
CONFIG_PATH = os.getenv("CONFIG_PATH", "config.yml")
CONFIG: Dict[str, Any] = {}
app = FastAPI()
http_client: httpx.AsyncClient | None = None

# --- Управление конфигурацией ---
def load_config():
    """Загружает и валидирует конфигурационный файл."""
    global CONFIG
    logger.info(f"Загрузка конфигурации из {CONFIG_PATH}...")
    try:
        with open(CONFIG_PATH, "r") as f:
            new_config = yaml.safe_load(f)
        # TODO: Добавить валидацию схемы конфигурации
        CONFIG = new_config
        # Компилируем regex-паттерны один раз для производительности
        for group_rules in CONFIG.get("access_rules", {}).values():
            for rule in group_rules:
                rule["_metrics_re"] = [re.compile(p) for p in rule.get("metrics", [])]
                if "required_labels" in rule:
                    for label, patterns in rule["required_labels"].items():
                        rule["required_labels"][label] = {
                            "patterns": patterns,
                            "_re": [re.compile(p) for p in patterns],
                        }
        logger.info("Конфигурация успешно загружена.")
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации: {e}", exc_info=True)
        # Если конфиг не загрузился при старте, приложение не должно работать
        if not CONFIG:
            raise

def handle_sighup(signum, frame):
    """Обработчик сигнала SIGHUP для перезагрузки конфига."""
    logger.info("Получен сигнал SIGHUP, перезагружаю конфигурацию...")
    load_config()

# --- Логика проверки доступа ---

@lru_cache(maxsize=1024)
def check_query_permissions(user: str, query: str) -> bool:
    """
    Проверяет, имеет ли пользователь право на выполнение PromQL запроса.
    Кэширует результат для идентичных запросов.
    """
    user_groups = CONFIG.get("users", {}).get(user)
    if not user_groups:
        logger.warning(f"Доступ запрещен для '{user}': пользователь не найден в конфигурации.")
        return False

    # 1. Собрать все разрешенные правила для групп пользователя
    allowed_metrics_re: List[re.Pattern] = []
    # { "label_name": [re.Pattern, ...], ... }
    required_labels_re: Dict[str, List[re.Pattern]] = {}

    for group in user_groups:
        rules = CONFIG.get("access_rules", {}).get(group, [])
        for rule in rules:
            allowed_metrics_re.extend(rule.get("_metrics_re", []))
            for label, data in rule.get("required_labels", {}).items():
                if label not in required_labels_re:
                    required_labels_re[label] = []
                required_labels_re[label].extend(data["_re"])
    
    if not allowed_metrics_re:
        logger.warning(f"Доступ запрещен для '{user}': нет разрешенных метрик.")
        return False

    # 2. Распарсить запрос с помощью AST
    try:
        parsed_query = parse(query)
    except Exception as e:
        logger.warning(f"Не удалось распарсить PromQL запрос от '{user}': {e}")
        # Запросы с синтаксическими ошибками лучше пропустить до Prometheus, он сам вернет ошибку
        return True

    # 3. Проверить все селекторы метрик в AST
    for metric_node in parsed_query.walk("Metric"):
        metric_name = metric_node.name
        
        # 3.1. Проверка имени метрики
        if not any(p.match(metric_name) for p in allowed_metrics_re):
            logger.warning(f"Доступ запрещен для '{user}': метрика '{metric_name}' не разрешена.")
            return False

        # 3.2. Проверка обязательных меток
        present_labels = {label.name: label.value for label in metric_node.labels}
        
        for required_label, patterns in required_labels_re.items():
            # Если для какой-то из разрешенных метрик эта метка обязательна
            is_label_required_for_this_metric = False
            for group in user_groups:
                for rule in CONFIG.get("access_rules", {}).get(group, []):
                    if any(p.match(metric_name) for p in rule["_metrics_re"]):
                         if required_label in rule.get("required_labels", {}):
                            is_label_required_for_this_metric = True
                            break
                if is_label_required_for_this_metric:
                    break

            if not is_label_required_for_this_metric:
                continue

            # Метка обязательна, но отсутствует в запросе
            if required_label not in present_labels:
                logger.warning(f"Доступ запрещен для '{user}': запрос к '{metric_name}' должен содержать метку '{required_label}'.")
                return False

            # Метка есть, проверяем ее значение
            label_value = present_labels[required_label]
            if not any(p.match(label_value) for p in patterns):
                logger.warning(
                    f"Доступ запрещен для '{user}': значение '{label_value}' для метки '{required_label}' "
                    f"в запросе к '{metric_name}' не разрешено."
                )
                return False

    return True


# --- FastAPI эндпоинты ---

@app.on_event("startup")
async def startup_event():
    """Действия при старте приложения."""
    global http_client
    load_config()
    signal.signal(signal.SIGHUP, handle_sighup)
    timeout = httpx.Timeout(10.0, connect=30.0)
    http_client = httpx.AsyncClient(base_url=CONFIG["prometheus_url"], timeout=timeout)
    logger.info("Прокси-сервис запущен.")

@app.on_event("shutdown")
async def shutdown_event():
    """Действия при остановке приложения."""
    if http_client:
        await http_client.aclose()
    logger.info("Прокси-сервис остановлен.")

@app.get("/health")
def health_check():
    """Проверка жизнеспособности сервиса."""
    return {"status": "ok"}

# !!! ВАЖНО: Добавить эндпоинты для метрик, например, с prometheus-fastapi-instrumentator
# @app.get("/metrics") ...

@app.api_route("/api/v1/{path:path}", methods=["GET", "POST"])
async def proxy_prometheus_api(request: Request, path: str):
    """
    Основной проксирующий эндпоинт.
    """
    user_header = CONFIG.get("user_header", "X-Webauth-User")
    user = request.headers.get(user_header)

    if not user:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "error": f"Заголовок '{user_header}' отсутствует"},
        )

    # --- Обработка запросов данных (query, query_range) ---
    if path in ("query", "query_range"):
        if request.method == "POST":
            form_data = await request.form()
            query = form_data.get("query")
        else: # GET
            query = request.query_params.get("query")

        if not query:
             return JSONResponse(status_code=400, content={"status": "error", "error": "Параметр 'query' отсутствует"})

        if not check_query_permissions(user, query):
            return JSONResponse(
                status_code=403,
                content={"status": "error", "error": "Доступ к запрашиваемым метрикам запрещен"},
            )
        logger.info(f"Доступ разрешен для '{user}' к запросу: {query[:100]}...")

    # --- Обработка запросов метаданных (series, labels, и т.д.) ---
    elif path in ("series", "labels") or path.startswith("label/"):
        # !!! УЛУЧШЕНИЕ: Это место требует сложной логики.
        # 1. Сделать запрос в Prometheus.
        # 2. Получить JSON ответ.
        # 3. Отфильтровать ответ, удалив все метрики/метки, к которым у пользователя нет доступа.
        # 4. Вернуть отфильтрованный JSON.
        # Для простоты примера, мы пока просто блокируем или пропускаем эти запросы.
        # В реальной системе это нужно реализовать для полной безопасности.
        logger.warning(
            f"Запрос метаданных '{path}' от '{user}'. "
            "Внимание: фильтрация ответа не реализована в этом примере!"
        )

    # --- Проксирование запроса в Prometheus ---
    url = httpx.URL(path=f"/api/v1/{path}", query=request.query_params.raw)
    
    # Копируем заголовки, исключая host
    headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}

    # Читаем тело запроса
    body = await request.body()
    
    try:
        rp = await http_client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
        )
        # Возвращаем полный ответ от Prometheus, включая статус, заголовки и тело
        return Response(content=rp.content, status_code=rp.status_code, headers=dict(rp.headers))

    except httpx.RequestError as e:
        logger.error(f"Ошибка при запросе к Prometheus: {e}")
        return JSONResponse(
            status_code=502,
            content={"status": "error", "error": "Не удалось связаться с Prometheus"},
        )


if __name__ == "__main__":
    import uvicorn
    # Запуск: uvicorn proxy:app --reload
    uvicorn.run(app, host="0.0.0.0", port=8000)
```