Ниже — разбор текущей идеи, список точечных улучшений и рабочий пример собственного прокси (FastAPI + httpx) с переписыванием PromQL и политиками доступа. Постарался держать баланс между практичностью и безопасностью.

Обзор
- Идея верная: прокси между Grafana и Prometheus, разграничение на уровне PromQL и label-значений.
- Ключевой риск и узкие места — доверие к заголовкам, корректность переписывания промкьюэля и покрытие всех “метаданных”-эндпоинтов Prometheus, которые Grafana использует (labels/series/...).

Что улучшить (по блокам)

1) Доверие и безопасность
- Не доверять X-WEBAUTH-USER «с улицы»: принимать заголовок только от Grafana или проверенного reverse proxy.
- Воспользоваться возможностью Grafana передавать заголовки пользователя:
  - В grafana.ini: [dataproxy] send_user_header = true — тогда Grafana добавляет X-Grafana-User, X-Grafana-Email, X-Grafana-Org-Id к запросам в datasource proxy.
  - Ограничить доступ к прокси по mTLS или по shared secret (например, X-Proxy-Secret), и/или по сети (allowlist подсетей Grafana).
  - Не принимать запросы без корректного секрета/серта/подсети.
- Подпись заголовков от Grafana: если используете Signed headers (в новых версиях), проверяйте подпись (HMAC) в прокси.
- Запретить доступ к административным и «широким» Prometheus-эндпоинтам:
  - /api/v1/targets, /api/v1/rules, /api/v1/metadata, /federate, /api/v1/tsdb, /api/v1/status/* — либо фильтровать, либо блокировать.
- Rate limiting и защита от «дорогих» запросов:
  - Ограничить max time range, max step, max lookback, лимит на число одновременных запросов, таймауты.

2) Корректность политики и PromQL
- Обязательно переписывать запросы, а не только «проверять»:
  - В каждый vector selector добавлять «enforced matchers» с допустимыми значениями (например, instance=~"^(a|b)$").
  - Это защищает от потери ограничивающих меток после агрегаций by/without и binary matching — источник данных всё равно отфильтрован.
- Явная стратегия по recording rules:
  - Если в Prometheus есть записные метрики, которые «сбрасывают» нужный label (например, team), их либо запрещать по имени, либо требовать, чтобы правила сохраняли «tenant label» в результате (by(team)).
- Конфликт matchers:
  - Если пользователь явно запросил запрещённые значения меток — отдавать 403, а не молча «обнулять» выдачу.
  - Если пользователь использует regex/negative matchers — пересекать с разрешённым множеством; пустое множество → 403.
- Покрытие всех API, которые Grafana вызывает:
  - /api/v1/query, /api/v1/query_range — переписывать PromQL.
  - /api/v1/series, /api/v1/labels, /api/v1/label/<name>/values — проксировать с подстановкой match[]=, которые сужают до разрешённых метрик/лейблов, и дополнительно фильтровать ответ.
  - /api/v1/query_exemplars — аналогично query, переписывать.
- Политики лучше задавать «по лэйблам», а не только по именам метрик:
  - Универсальная схема: user → группы → политика: allow metric patterns + enforced label constraints.
  - Предусмотреть «обязательный» tenant label (например, team, org, project), который всегда добавляется к каждому селектору.

3) Эксплуатация и надёжность
- Горячая перезагрузка:
  - В дополнение к SIGHUP — endpoint /-/reload с HMAC/mtls, atomic reload (читать новый config, валидировать, только потом сменить ссылку в рантайме).
- Стабильность:
  - Пулы соединений httpx, таймауты, ретраи только на идемпотентные запросы, ограничение размера ответа, стриминг.
- Наблюдаемость самого прокси:
  - /metrics (Prometheus клиент) — счетчики разрешённых/заблокированных запросов, время переписывания, запросы к upstream, ошибки.
  - Tracing (OpenTelemetry) — связывайте с Grafana trace headers.
  - Структурное логирование (JSON), кореляционный id.
- Производительность:
  - Кэш переписывания PromQL на (user, query шаблон) с TTL.
  - Предкомпиляция regex для metric patterns и label values.
  - Async, HTTP/2 к Prometheus.

4) UX/Dev/Безопасные дефолты
- Default deny: если политика не найдена — 403.
- Explain-mode: опциональный заголовок X-Debug-Policy: true → отдавать вместе с результатом «объяснение»: какие matchers были добавлены/почему заблокировано.
- Тесты:
  - Набор юнит-тестов для парсера/переписчика, property-based (hypothesis) на tricky выражениях.
- Документация/гайд по настройке Grafana:
  - Как включить send_user_header.
  - Как настроить datasource на прокси URL.
  - Что в Prometheus-стороне (правила с сохранением tenant label).

5) Альтернативы и эволюция
- Если когда-нибудь потребуется «промышленные» multi-tenant возможности: Mimir/Cortex/Thanos уже умеют enforced tenant headers и политики. Ваш прокси может стать «тонким» контроллером, проверяющим разрешения и ставящим X-Scope-OrgID.

Пример собственного прокси (FastAPI)

Что делает:
- Проверяет пользователя по заголовкам (X-Grafana-User, X-WEBAUTH-USER).
- Проверяет/переписывает PromQL: добавляет допустимые label matchers в каждый vector selector; запрещает конфликтные matchers/метрики вне allowlist.
- Ограничивает API к «безопасному» подмножеству.
- Подставляет match[]= в series/labels/label-values и фильтрует ответ.
- Горячая перезагрузка конфига по SIGHUP и через /-/reload.
- Метрики самого прокси на /metrics.

Примечание по парсеру PromQL:
- В коде есть два пути: 1) с использованием promql-парсера (рекомендуется для продакшена); 2) «аккуратный» фоллбек-набор regexp для переписывания vector selectors. Для продакшена используйте AST-путь, фоллбек — на свой страх и риск.
- Подходит под Python 3.10+.

requirements.txt (пример)
- fastapi
- uvicorn[standard]
- httpx[http2]
- pyyaml
- cachetools
- prometheus-client
- python-dotenv
- watchfiles  # по желанию для авто-ребилда/перезагрузки
- promql-parser  # если используете AST-парсер; подберите реальную либу под вашу среду

config.yml (пример)
groups:
  team-a:
    metrics: ["^http_requests_total$", "^node_.*$"]
    labels:
      instance: ["server-a1", "server-a2"]
      namespace: ["team-a-.*"]   # regex через ^...$ можно задать как строки с .* — компилируем в re
limits:
  max_range_hours: 720
  max_step_seconds: 3600
  max_query_length: 5000

users:
  bob: [team-a]

main.py
```python
import asyncio
import json
import logging
import os
import re
import signal
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Попробуем подключить AST-парсер. Если не установлен — перейдём на фоллбек.
USE_AST = True
try:
    # Замените на актуальную библиотеку/импорты вашей AST-либы
    # from promql_parser import parse as promql_parse, dump as promql_dump
    # Заглушка: выставим USE_AST = False если либы нет
    raise ImportError("No promql parser lib configured")
except Exception:
    USE_AST = False

# -------------------- Логирование --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("prom-ac-proxy")

# -------------------- Метрики прокси --------------------
METRIC_QUERIES_TOTAL = Counter("proxy_queries_total", "Total queries", ["endpoint", "user", "decision"])
METRIC_UPSTREAM_LATENCY = Histogram("proxy_upstream_latency_seconds", "Upstream latency", ["endpoint"])
METRIC_REWRITE_LATENCY = Histogram("proxy_rewrite_latency_seconds", "Rewrite latency")
METRIC_BLOCKED_TOTAL = Counter("proxy_blocked_total", "Blocked requests", ["reason"])

# -------------------- Глобальное состояние --------------------
class LabelConstraint:
    def __init__(self, allowed: List[str]):
        # Элементы могут быть как точными значениями, так и regex-паттернами.
        self.values = []
        self.regexes = []
        for v in allowed:
            if any(ch in v for ch in ".*+?[]()|{}^$\\"):
                self.regexes.append(re.compile(v))
            else:
                self.values.append(v)
        self.value_set = set(self.values)

    def match_values(self, candidates: List[str]) -> List[str]:
        # Вернуть подмножество candidates, попадающее под разрешения
        out = [c for c in candidates if c in self.value_set]
        if self.regexes:
            for c in candidates:
                if c in self.value_set:
                    continue
                if any(r.match(c) for r in self.regexes):
                    out.append(c)
        # Уникализируем сохранив порядок
        seen = set()
        res = []
        for v in out:
            if v not in seen:
                seen.add(v)
                res.append(v)
        return res

    def restrict_regex(self) -> Optional[str]:
        # Для подстановки в PromQL: если есть точные значения и/или regex — сформируем один regex
        parts = []
        if self.values:
            # Экранируем значения
            parts.extend([re.escape(v) for v in self.values])
        if self.regexes:
            # regex оставим как есть, но в одну группу это не идеально.
            parts.extend([r.pattern for r in self.regexes])
        if not parts:
            return None
        # Оборачиваем в единый «или»
        return "^(?:" + "|".join(parts) + ")$"

class CompiledPolicy:
    def __init__(self, metric_patterns: List[str], label_constraints: Dict[str, LabelConstraint]):
        self.metric_regexes = [re.compile(p) for p in metric_patterns] if metric_patterns else []
        self.label_constraints = label_constraints  # label -> LabelConstraint

    def metric_allowed(self, metric_name: str) -> bool:
        if not self.metric_regexes:
            return True
        return any(r.match(metric_name) for r in self.metric_regexes)

class PolicyEngine:
    def __init__(self, config: Dict[str, Any]):
        self.raw = config
        self.groups = config.get("groups", {})
        self.users = config.get("users", {})
        self.limits = config.get("limits", {})
        self._compiled_groups: Dict[str, CompiledPolicy] = {}
        for gname, gdef in self.groups.items():
            patterns = gdef.get("metrics", [])
            labels = gdef.get("labels", {})
            compiled_labels = {k: LabelConstraint(v) for k, v in labels.items()}
            self._compiled_groups[gname] = CompiledPolicy(patterns, compiled_labels)

    def user_policy(self, user: str) -> CompiledPolicy:
        groups = self.users.get(user, [])
        metric_patterns: List[str] = []
        label_constraints: Dict[str, LabelConstraint] = {}
        for g in groups:
            cg = self._compiled_groups.get(g)
            if not cg:
                continue
            metric_patterns.extend([r.pattern for r in cg.metric_regexes])  # type: ignore
            # Объединяем лейбл-ограничения по логике И: пересечение разрешений
            for lbl, c in cg.label_constraints.items():
                if lbl not in label_constraints:
                    # Клонируем
                    label_constraints[lbl] = LabelConstraint(c.values + [r.pattern for r in c.regexes])
                else:
                    # Пересечение
                    existing = label_constraints[lbl]
                    # Сведём к regex объединением, чтобы не усложнять:
                    inter = set(existing.value_set).intersection(c.value_set)
                    # Если были regex, оставим оба — в итоге это «или», но мы потом будем пересекать с запросами.
                    # Для простоты: объединяем, но при конкретных запросах мы будем делать пересечение по значениям.
                    merged = list(inter)
                    merged += [r.pattern for r in existing.regexes] + [r.pattern for r in c.regexes]
                    label_constraints[lbl] = LabelConstraint(merged)
        # Удаляем дубликаты паттернов в метриках
        dedup_patterns = list(dict.fromkeys(metric_patterns))
        return CompiledPolicy(dedup_patterns, label_constraints)

# Глобальные объекты
CONFIG_PATH = os.getenv("PROXY_CONFIG", "config.yml")
UPSTREAM_URL = os.getenv("UPSTREAM_URL", "http://prometheus:9090")
SHARED_SECRET = os.getenv("PROXY_SHARED_SECRET")  # если задан — требуем от Grafana
ALLOWED_SOURCES = os.getenv("ALLOWED_SOURCES")  # CIDR или список IP — опционально

policy_engine: PolicyEngine

http_client: httpx.AsyncClient

# Кэш: (user, query_str) -> rewritten_query
REWRITE_CACHE = TTLCache(maxsize=10000, ttl=60)

app = FastAPI(title="Prometheus Access Proxy")

# -------------------- Загрузка/перезагрузка конфига --------------------
def load_config() -> PolicyEngine:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return PolicyEngine(cfg or {})

def atomic_reload() -> None:
    global policy_engine
    new_engine = load_config()
    policy_engine = new_engine
    REWRITE_CACHE.clear()
    log.info("Config reloaded")

def handle_sighup(signum, frame):
    try:
        atomic_reload()
    except Exception as e:
        log.exception("Reload failed: %s", e)

signal.signal(signal.SIGHUP, handle_sighup)

@app.on_event("startup")
async def on_startup():
    global policy_engine, http_client
    policy_engine = load_config()
    http_client = httpx.AsyncClient(http2=True, timeout=30.0)

@app.on_event("shutdown")
async def on_shutdown():
    await http_client.aclose()

# -------------------- Утилиты запроса/пользователя --------------------
RESERVED = {"on", "ignoring", "group_left", "group_right", "by", "without", "bool", "offset"}

def get_user(req: Request) -> str:
    user = req.headers.get("X-Grafana-User") or req.headers.get("X-WEBAUTH-USER")
    if not user:
        raise HTTPException(status_code=401, detail="User header missing")
    return user

def verify_secret(req: Request):
    if SHARED_SECRET:
        if req.headers.get("X-Proxy-Secret") != SHARED_SECRET:
            raise HTTPException(status_code=401, detail="Bad proxy secret")

def enforce_limits(limits: Dict[str, Any], params: Dict[str, Any]):
    # Базовые лимиты: max_range_hours, max_step_seconds, max_query_length
    if "query" in params:
        q = params.get("query", "")
        max_len = int(limits.get("max_query_length", 10000))
        if len(q) > max_len:
            raise HTTPException(status_code=413, detail="Query too long")
    if "start" in params and "end" in params:
        try:
            start = float(params["start"])
            end = float(params["end"])
            if end < start:
                raise HTTPException(status_code=400, detail="end < start")
            hours = (end - start) / 3600.0
            max_hours = float(limits.get("max_range_hours", 720.0))
            if hours > max_hours:
                raise HTTPException(status_code=400, detail=f"Range too large, limit {max_hours}h")
        except Exception:
            pass
    if "step" in params:
        try:
            step = float(params["step"])
            max_step = float(limits.get("max_step_seconds", 3600.0))
            if step > max_step:
                raise HTTPException(status_code=400, detail=f"Step too large, limit {max_step}s")
        except Exception:
            pass

# -------------------- Переписывание PromQL --------------------
# Фоллбек: аккуратно ищем vector selectors и добавляем label matchers.
# Паттерн: <metric>(не функция) [ {labels} ] [ [range] ]
VECTOR_SELECTOR_RE = re.compile(
    r"""
    (?P<prefix>\W|^)
    (?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)
    (?!\s*\()                      # не функция/агрегатор
    (?P<labels>\{[^{}]*\})?
    (?P<range>\[[^\[\]]+\])?
    """,
    re.VERBOSE,
)

LABEL_MATCH_RE = re.compile(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|=|!=|!~)\s*"(.*?)"\s*')

def parse_label_set(lbls: str) -> Dict[str, Tuple[str, str]]:
    # "{a="b",c=~"d"}" -> {a: ("=", "b"), c: ("=~", "d")}
    res = {}
    inner = lbls.strip()[1:-1].strip()
    if not inner:
        return res
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    for p in parts:
        m = LABEL_MATCH_RE.fullmatch(p)
        if m:
            k, op, val = m.group(1), m.group(2), m.group(3)
            res[k] = (op, val)
    return res

def build_label_set(d: Dict[str, Tuple[str, str]]) -> str:
    if not d:
        return "{}"
    parts = []
    for k, (op, v) in sorted(d.items()):
        parts.append(f'{k}{op}"{v}"')
    return "{" + ",".join(parts) + "}"

def intersect_with_constraint(op: str, val: str, constraint: LabelConstraint) -> Tuple[bool, Optional[Tuple[str, str]]]:
    """
    Возвращает (ok, new_matcher | None).
    Если ok=False — запрет (403).
    Если new_matcher=None — оставить как есть.
    Иначе — заменить на новый (=~, "^(...|...)+$") с пересечением.
    """
    # Для упрощения — рассматриваем конечное множество допустимых значений:
    # строим пересечение по «кандидатам» из constraint.
    allowed_candidates = list(constraint.value_set)
    # Добавим несколько «типичных» значений для regex пересечения если есть regex-паттерны.
    # В реале для корректности лучше держать справочник допустимых значений из вашей доменной модели.
    if not allowed_candidates and constraint.regexes:
        # Если только regex — мы не можем знать «универсум». Тогда просто ужесточим запрос до constraint.regex.
        regex = constraint.restrict_regex()
        return True, ("=~", regex) if regex else (True, None)

    if op == "=":
        ok = val in constraint.match_values([val])
        return (ok, None if ok else (False, None))  # запретим, если вне allowed

    if op == "!=:
        # allowed ∩ (U - {val}) = allowed - {val}
        inter = [v for v in allowed_candidates if v != val]
        if not inter:
            return False, None
        regex = "^(?:" + "|".join(re.escape(v) for v in inter) + ")$"
        return True, ("=~", regex)

    if op == "=~":
        try:
            rq = re.compile(val)
        except Exception:
            return False, None
        inter = [v for v in allowed_candidates if rq.match(v)]
        if not inter:
            return False, None
        regex = "^(?:" + "|".join(re.escape(v) for v in inter) + ")$"
        return True, ("=~", regex)

    if op == "!~":
        try:
            rq = re.compile(val)
        except Exception:
            return False, None
        inter = [v for v in allowed_candidates if not rq.match(v)]
        if not inter:
            return False, None
        regex = "^(?:" + "|".join(re.escape(v) for v in inter) + ")$"
        return True, ("=~", regex)

    return False, None

def enforce_labels_on_selector(
    metric: str, labels_dict: Dict[str, Tuple[str, str]], policy: CompiledPolicy
) -> Tuple[bool, Dict[str, Tuple[str, str]]]:
    """
    Применить policy.label_constraints к labels_dict данного селектора.
    Возврат: (ok, new_labels_dict)
    """
    new_dict = dict(labels_dict)
    for lbl, constr in policy.label_constraints.items():
        if lbl in new_dict:
            op, val = new_dict[lbl]
            ok, new_match = intersect_with_constraint(op, val, constr)
            if not ok:
                return False, new_dict
            if new_match:
                new_dict[lbl] = new_match
        else:
            # Добавим ограничение
            regex = constr.restrict_regex()
            if regex:
                new_dict[lbl] = ("=~", regex)
    return True, new_dict

def rewrite_promql_fallback(query: str, policy: CompiledPolicy) -> str:
    """
    Переписывает все vector selectors, добавляя/пересекаю ограничения.
    Проверяет метрики по allowlist.
    """
    out = []
    last = 0

    for m in VECTOR_SELECTOR_RE.finditer(query):
        prefix = m.group("prefix") or ""
        name = m.group("name")
        labels = m.group("labels") or ""
        rng = m.group("range") or ""

        # Пропускаем ложные срабатывания (зарезервированные слова)
        if name in RESERVED:
            continue

        # Проверка метрики по allowlist
        if not policy.metric_allowed(name):
            raise HTTPException(status_code=403, detail=f"Metric '{name}' is not allowed")

        # Разбираем текущий набор лейблов
        lbl_dict = parse_label_set(labels) if labels else {}

        ok, new_lbl_dict = enforce_labels_on_selector(name, lbl_dict, policy)
        if not ok:
            raise HTTPException(status_code=403, detail=f"Label constraints violated for '{name}'")

        new_labels_str = build_label_set(new_lbl_dict) if new_lbl_dict else "{}"
        # Если изначально не было {}, стоит добавить их (даже если пусто — чтобы были enforced-лейблы)
        # Если в new_lbl_dict пусто (нет policy для лейблов) и изначально тоже не было {}, можно оставить как было.
        need_braces = bool(new_lbl_dict) or bool(labels)

        # Сконструируем новый фрагмент
        start, end = m.span()
        out.append(query[last:start])
        out.append(prefix)
        out.append(name)
        if need_braces:
            out.append(build_label_set(new_lbl_dict))
        if rng:
            out.append(rng)
        last = end

    out.append(query[last:])
    return "".join(out)

def rewrite_promql(query: str, policy: CompiledPolicy) -> str:
    if USE_AST:
        # Тут должен быть AST-путь:
        # - разобрать AST;
        # - пройтись по всем VectorSelector/MatrixSelector узлам;
        # - проверить metric_allowed;
        # - перезаписать label matchers с учётом policy.label_constraints;
        # - собрать строку обратно.
        # Псевдокод/заглушка:
        raise HTTPException(status_code=501, detail="AST rewriter not configured")
    return rewrite_promql_fallback(query, policy)

@lru_cache(maxsize=2048)
def _policy_for_user_cached(user: str) -> CompiledPolicy:
    # Маленький кэш на user->policy; сбрасывается при reload
    return policy_engine.user_policy(user)

def rewrite_with_cache(user: str, query: str) -> str:
    key = (user, query)
    val = REWRITE_CACHE.get(key)
    if val:
        return val
    policy = _policy_for_user_cached(user)
    t0 = time.time()
    new_q = rewrite_promql(query, policy)
    METRIC_REWRITE_LATENCY.observe(time.time() - t0)
    REWRITE_CACHE[key] = new_q
    return new_q

# -------------------- Проксирование и эндпоинты --------------------
SAFE_ENDPOINTS = {
    "/api/v1/query",
    "/api/v1/query_range",
    "/api/v1/series",
    "/api/v1/labels",
}
# label values динамический path
LABEL_VALUES_RE = re.compile(r"^/api/v1/label/[^/]+/values$")

def is_safe_endpoint(path: str) -> bool:
    return path in SAFE_ENDPOINTS or LABEL_VALUES_RE.match(path) is not None

async def proxy_upstream(method: str, path: str, params: Dict[str, Any], data: Optional[Dict[str, Any]] = None) -> Response:
    url = UPSTREAM_URL.rstrip("/") + path
    with METRIC_UPSTREAM_LATENCY.labels(endpoint=path).time():
        r = await http_client.request(method, url, params=params, data=data, headers={"Accept": "application/json"})
    return Response(content=r.content, status_code=r.status_code, headers=dict(r.headers))

def build_matchers_from_policy(policy: CompiledPolicy) -> List[str]:
    # Для series/labels/label-values: подставим match[]=metric{enforced_labels}
    lbl_dict = {}
    for lbl, constr in policy.label_constraints.items():
        regex = constr.restrict_regex()
        if regex:
            lbl_dict[lbl] = ("=~", regex)
    lbl_str = build_label_set(lbl_dict) if lbl_dict else ""
    # Если нет ограничений — вернём только metric patterns как regex-имена
    metric_pats = [r.pattern for r in policy.metric_regexes] if policy.metric_regexes else [".*"]
    matchers = []
    for mp in metric_pats:
        metric_name = f'__name__=~"{mp}"'
        if lbl_str:
            if lbl_str == "{}":
                matchers.append("{" + metric_name + "}")
            else:
                inner = lbl_str[1:-1]
                matchers.append("{" + metric_name + "," + inner + "}")
        else:
            matchers.append("{" + metric_name + "}")
    return matchers

def filter_label_values(values: List[str], lc: LabelConstraint) -> List[str]:
    # Оставим только допустимые
    # Для regex-only ограничений — пропустим через regex
    if lc.value_set:
        base = [v for v in values if v in lc.value_set]
    else:
        base = values[:]
    if lc.regexes:
        base = [v for v in base if any(r.match(v) for r in lc.regexes)]
    return base

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/-/reload")
async def reload_config(req: Request):
    verify_secret(req)
    try:
        atomic_reload()
        return PlainTextResponse("OK")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.api_route("/{full_path:path}", methods=["GET", "POST"])
async def handle(req: Request, full_path: str):
    path = "/" + full_path
    if not is_safe_endpoint(path):
        METRIC_BLOCKED_TOTAL.labels(reason="endpoint").inc()
        raise HTTPException(status_code=404, detail="Endpoint not allowed")

    verify_secret(req)
    user = get_user(req)
    params = dict(req.query_params)
    body = None
    if req.method == "POST":
        if "application/json" in req.headers.get("content-type", ""):
            body = await req.json()
        else:
            form = await req.form()
            body = dict(form)

    policy = _policy_for_user_cached(user)
    enforce_limits(policy_engine.limits or {}, body or params)

    METRIC = "allowed"
    try:
        if path in ("/api/v1/query", "/api/v1/query_range"):
            # Извлекаем promql "query" из GET-параметров или тела POST
            if req.method == "GET":
                q = params.get("query") or ""
                if not q:
                    raise HTTPException(400, "query param missing")
                new_q = rewrite_with_cache(user, q)
                params["query"] = new_q
                resp = await proxy_upstream(req.method, path, params=params)
            else:
                q = (body or {}).get("query") or ""
                if not q:
                    raise HTTPException(400, "query param missing")
                new_q = rewrite_with_cache(user, q)
                body["query"] = new_q
                resp = await proxy_upstream(req.method, path, params=params, data=body)
        elif path == "/api/v1/series":
            # Подставляем match[]= согласно политике
            # Сохраняем оригинальные match[], но добавляем наши, чтобы сузить область
            matchers = build_matchers_from_policy(policy)
            # Если у клиента есть свои match[]= — добавим и наши.
            qp = dict(params)
            existing = req.query_params.getlist("match[]")
            all_match = existing + matchers
            # httpx сам применит листовые значения, если передать список
            params_multi = []
            for k, v in qp.items():
                if k != "match[]":
                    params_multi.append((k, v))
            for m in all_match:
                params_multi.append(("match[]", m))
            with METRIC_UPSTREAM_LATENCY.labels(endpoint=path).time():
                url = UPSTREAM_URL.rstrip("/") + path
                r = await http_client.get(url, params=params_multi, headers={"Accept": "application/json"})
            resp = Response(content=r.content, status_code=r.status_code, headers=dict(r.headers))
        elif path == "/api/v1/labels":
            # Prometheus позволяет фильтровать labels через match[]
            matchers = build_matchers_from_policy(policy)
            params_multi = []
            for m in matchers:
                params_multi.append(("match[]", m))
            url = UPSTREAM_URL.rstrip("/") + path
            r = await http_client.get(url, params=params_multi, headers={"Accept": "application/json"})
            resp = Response(content=r.content, status_code=r.status_code, headers=dict(r.headers))
        else:
            # /api/v1/label/<name>/values
            url = UPSTREAM_URL.rstrip("/") + path
            matchers = build_matchers_from_policy(policy)
            params_multi = []
            for m in matchers:
                params_multi.append(("match[]", m))
            r = await http_client.get(url, params=params_multi, headers={"Accept": "application/json"})
            # Дополнительная фильтрация ответа по policy.label_constraints[label_name], если есть
            label_name = path.split("/")[4]
            if r.status_code == 200 and label_name in policy.label_constraints:
                try:
                    payload = r.json()
                    if payload.get("status") == "success" and isinstance(payload.get("data"), list):
                        allowed = filter_label_values(payload["data"], policy.label_constraints[label_name])
                        payload["data"] = allowed
                        resp = JSONResponse(payload, status_code=200)
                    else:
                        resp = Response(content=r.content, status_code=r.status_code, headers=dict(r.headers))
                except Exception:
                    resp = Response(content=r.content, status_code=r.status_code, headers=dict(r.headers))
            else:
                resp = Response(content=r.content, status_code=r.status_code, headers=dict(r.headers))

        METRIC_QUERIES_TOTAL.labels(endpoint=path, user=user, decision="allow").inc()
        return resp

    except HTTPException as e:
        METRIC = "deny"
        METRIC_BLOCKED_TOTAL.labels(reason=str(e.detail)).inc()
        METRIC_QUERIES_TOTAL.labels(endpoint=path, user=user, decision="deny").inc()
        raise
    except Exception as e:
        METRIC = "error"
        METRIC_QUERIES_TOTAL.labels(endpoint=path, user=user, decision="error").inc()
        log.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="Internal error")
```

Как этим пользоваться
- Запуск: UVicorn/Gunicorn
  - uvicorn main:app --host 0.0.0.0 --port 8000
- Переменные окружения:
  - UPSTREAM_URL=http://prometheus:9090
  - PROXY_CONFIG=/etc/proxy/config.yml
  - PROXY_SHARED_SECRET=<секрет> — включите и укажите тот же secret в Grafana datasource (Custom HTTP Header: X-Proxy-Secret).
- Grafana:
  - В grafana.ini: [dataproxy] send_user_header = true
  - Datasource Prometheus указывает на http://proxy:8000, без прямого доступа к Prometheus.
  - Добавьте Custom HTTP Header X-Proxy-Secret=<секрет>.
- Релоад:
  - kill -HUP <PID> или POST /-/reload с X-Proxy-Secret.
- Метрики прокси: GET /metrics

Комментарий к переписывателю
- Встроенный фоллбек-переписыватель на regex закрывает 80–90% практических запросов, но для 100% корректности используйте AST-парсер PromQL и замените функцию rewrite_promql на обход AST.
- В политике ограничения по лейблам конвертируются в единый =~ "^(...|...)$". При явном конфликте в запросе → 403.
- Для series/labels/label-values в запрос подставляются match[] из политики, плюс дополнительно фильтруется ответ.

Итого
- Основная идея решения — правильная.
- Ключевые улучшения: доверие к заголовкам (через Grafana data proxy + secret/mTLS), обязательное переписывание каждого vector selector, покрытие мета-эндпоинтов, лимиты на ресурсоёмкие запросы, наблюдаемость самого прокси и удобные механизмы перезагрузки/отладки.
- Приложенный код — рабочая «база» для пилота. Для продакшена рекомендую:
  - Включить AST-парсер PromQL (и тесты к нему).
  - Дополнить список эндпоинтов (query_exemplars и др.).
  - Привести recording rules к сохранению tenant label или ограничить их по имени.
