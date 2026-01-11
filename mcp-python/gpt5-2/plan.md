Ниже — каркас обучающего курса по MCP (Model Context Protocol) и Python: теория (с короткими примерами) + практические задания и мини‑проект, чтобы к концу собрать рабочую связку “MCP‑сервер ↔ MCP‑клиент ↔ LLM‑host/инспектор”.[1][2]

## Модуль 1. Введение
**Цель:** понять, зачем MCP нужен и как устроена типовая интеграция “LLM ↔ инструменты/данные”.

### Теория
- MCP — протокол, который позволяет приложениям стандартизированно предоставлять контекст и “действия” (tools) LLM‑приложениям, отделяя слой контекста/инструментов от конкретной модели.[3]
- Базовые роли:
  - **Client** подключается к MCP‑server, запрашивает ресурсы/промпты/инструменты и вызывает tools.[3]
  - **Server** публикует primitives: resources / prompts / tools (и сопутствующие возможности).[3]
  - **Host** (LLM‑host) — среда, которая решает, когда читать ресурсы и когда вызывать tools (например, “Claude Desktop” или свой чат‑хост), а MCP даёт единый интерфейс.[3]

### Мини‑пример (что “публикует” сервер)
- Resources — “как GET”: отдать данные без сайд‑эффектов.[3]
- Tools — “как POST”: выполнить действие/вычисление/запрос (возможны сайд‑эффекты).[3]
- Prompts — шаблоны взаимодействия (переиспользуемые подсказки/структуры сообщений).[3]

### Практика
1) Установить окружение:
- `pip install "mcp[cli]"` или `uv add "mcp[cli]"`.[3]
2) Создать пустой репозиторий курса (структура):
- `server/`, `client/`, `examples/`, `README.md`, `pyproject.toml`.

## Модуль 2. MCP‑протокол
**Цель:** понимать “провода”: transport, типы сообщений, capabilities и инструменты диагностики.

### Теория: transport
- **stdio transport**: клиент запускает сервер как subprocess и обменивается JSON‑RPC сообщениями через stdin/stdout (сообщения разделяются переводом строки).[3]
- **Streamable HTTP**: стандарт для удалённых подключений (одна HTTP endpoint для двунаправленного обмена; в спецификации фигурирует как современная замена legacy‑подходов).[4][3]

### Теория: primitives и capabilities
- MCP‑server обычно объявляет поддержку primitives (prompts/resources/tools) и доп. возможностей (logging, completion и т.п.) на этапе инициализации.[3]
- В Python SDK акцент на primitives: Resources/Tools/Prompts и их discovery через `list_*` + вызовы `read_resource`/`call_tool`/`get_prompt`.[3]

### Инструмент: Inspector
- MCP Inspector — интерактивный инструмент тестирования/отладки: вкладки Resources/Prompts/Tools и панель уведомлений/логов.[1]
- Запуск инспектора типично делается через `npx @modelcontextprotocol/inspector ...`.[1]

### Практика
1) Выписать (в конспект) “матрицу”:
- Какой transport выбирается для локального dev (stdio) и для remote (Streamable HTTP).[4][3]
2) Смоделировать “happy path” последовательность:
- connect → initialize → list_tools → call_tool → получить результат (в терминах SDK).[3]

## Модуль 3. MCP SDK на Python
**Цель:** уметь быстро поднимать MCP‑server и писать MCP‑client под stdio/HTTP.

### Теория: FastMCP vs low-level
- Python SDK предлагает **FastMCP** для быстрого объявления tools/resources/prompts через декораторы.[3]
- Есть low‑level API `Server(...)` для полного контроля (handlers, lifespan, capabilities).[3]

### Пример: простой FastMCP сервер
```python
# server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Demo")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"
``` 


### Пример: MCP‑клиент (stdio) и вызов tool
- Подключение через `stdio_client(...)`, затем `ClientSession(...).initialize()` и `call_tool`.[3]

### Практика
1) Реализовать `server.py` с 2 tools и 1 resource:
- Tool: `add(a,b)` (синхронный).[3]
- Tool: `fetch_url(url)` (асинхронный, через `httpx`, с таймаутом).[3]
- Resource: `buildinfo://` (версия/commit/time).
2) Реализовать `client.py`:
- Поднять subprocess‑сервер через `StdioServerParameters(...)`.[3]
- Сделать `list_tools()` и один `call_tool()` (проверить JSON‑схему аргументов по списку tools).[3]

## Модуль 4. Отладка и мониторинг
**Цель:** быстро локализовывать ошибки протокола/схем/рантайма.

### Теория
- Инспектор показывает доступные tools/resources/prompts и позволяет вручную запускать tool с параметрами, а также видеть логи/уведомления.[1]
- В FastMCP инструменты контекста включают логирование и прогресс‑репорты через `Context` (например, `ctx.info(...)`, `ctx.report_progress(...)`).[3]

### Практика
1) Добавить логирование:
- В каждом tool логировать входные параметры и время выполнения (минимум: start/end).[3]
2) Добавить “длинную” операцию:
- Tool `hash_files(files: list[str])` с прогрессом (`ctx.report_progress(i, total)`).[3]
3) Прогнать через Inspector и убедиться, что:
- Вкладка Tools показывает схему/описание, а в Notifications видно логи.[1]

## Модуль 5. LLM‑хост
**Цель:** понимать, как MCP “встраивается” в хост и какие контракты важны для UX и безопасности.

### Теория
- MCP‑server можно тестировать в dev‑режиме через инструменты CLI, а затем устанавливать/подключать к хосту (пример: команды вида `mcp install ...`, `mcp dev ...`).[3]
- Для production‑подключений чаще рассматривают Streamable HTTP; SDK поддерживает запуск FastMCP с transport `"streamable-http"`.[3]

### Практика
1) Запустить сервер в dev‑режиме и проверить ручные вызовы.[3]
2) Поднять сервер на Streamable HTTP и проверить доступность со стороны клиента (отдельным скриптом).[3]

## Модуль 6. Интеграция с моделями
**Цель:** научиться “упаковывать” tools так, чтобы модель ими реально пользовалась.

### Теория (прикладная)
- Tools должны быть “discoverable”: чёткое имя, короткое описание, строгая схема аргументов и предсказуемые ошибки — это напрямую проверяется в Inspector (видно в списке tools и их схемах).[1]
- На практике есть два режима: модели, которые лучше вызывают tools “нативно”, и модели без fine‑tuning, которым требуется системный промпт с правилами вызова tool и форматом. (В рамках курса это оформляется как два шаблона system prompt и A/B тесты поведения.)

### Практика
1) Для каждого tool написать:
- 1–2 “позитивных” примера запроса (когда tool нужен).
- 1 “негативный” пример (когда tool не нужен).
2) Сделать policy‑валидацию входа:
- Ограничить URL (allowlist доменов) для `fetch_url`, чтобы продемонстрировать secure‑by‑default подход.

## Модуль 7. Практика (мини‑проект)
**Цель:** собрать end‑to‑end демо.

### Задание: “Ops‑Assistant MCP”
Собрать MCP‑server (Python) + MCP‑client, где сервер отдаёт:
- Resource `buildinfo://` и `health://`.  
- Tool `tail_logs(path, lines)` (безопасно: только из allowlist директорий).  
- Tool `run_diagnostic()` (имитация: возвращает JSON со статусами).  
- Prompt `incident_triage(error_text)` — шаблон для разбора инцидента.[3]

### Acceptance criteria
- Клиент:
  - Подключается по stdio, делает `list_tools()`/`list_resources()` и вызывает минимум 2 tools.[3]
- Отладка:
  - Прогон через Inspector: tools видны, вызовы работают, логи отображаются.[1]
- (Опционально) HTTP:
  - Сервер запускается как `"streamable-http"` и клиент умеет подключаться через `streamablehttp_client`.[3]

В каком формате удобнее отдать курс дальше: как набор markdown‑лекций + отдельные папки `labs/` с пошаговыми заданиями, или как “единый репозиторий” с ветками по модулям?

[1](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
[2](https://pypi.org/project/mcp/1.8.0/)
[3](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
[4](https://developers.cloudflare.com/agents/model-context-protocol/transport/)
[5](https://modelcontextprotocol.info/docs/concepts/transports/)
[6](https://docs.roocode.com/features/mcp/server-transports)
[7](https://github.com/ruslanmv/Simple-MCP-Server-with-Python)
[8](https://snyk.io/articles/how-to-debug-mcp-server-with-anthropic-inspector/)
[9](https://modelcontextprotocol.wiki/en/docs/concepts/transports)
[10](https://realpython.com/python-mcp-client/)
[11](https://anthropic.skilljar.com/introduction-to-model-context-protocol)
[12](https://modelcontextprotocol.info/specification/draft/basic/transports/)
[13](https://skywork.ai/skypage/en/MCP-Inspector-The-Definitive-Guide-for-AI-Engineers/1971458222611361792)
[14](https://www.reddit.com/r/modelcontextprotocol/comments/1jhhokc/mcp_servers_will_support_http_on_top_of_ssestdio/)
[15](https://github.com/RGGH/mcp-client-x)
[16](https://modelcontextprotocol.io/docs/tools/inspector)
[17](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1288)
[18](https://modelcontextprotocol.io/docs/develop/build-client)
[19](https://github.com/modelcontextprotocol/inspector)
[20](https://uithub.com/modelcontextprotocol/modelcontextprotocol/tree/main/docs/specification/2025-03-26)
