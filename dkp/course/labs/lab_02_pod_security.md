# Лабораторная работа 2. Pod security и минимальные требования допуска

## Цель

Превратить требования к безопасности запускаемых приложений `shop-demo` в общие правила платформы, а не в ручную проверку манифестов.

## Исходные материалы

- манифесты `shop-demo`:
  - [`00-namespaces.yaml`](../shop-demo/manifests/00-namespaces.yaml)
  - [`10-frontend.yaml`](../shop-demo/manifests/10-frontend.yaml)
  - [`20-orders.yaml`](../shop-demo/manifests/20-orders.yaml)
  - [`30-payments.yaml`](../shop-demo/manifests/30-payments.yaml)
  - [`40-platform-tools.yaml`](../shop-demo/manifests/40-platform-tools.yaml)
  - [`kustomization.yaml`](../shop-demo/manifests/kustomization.yaml)
- [глава 2 курса](../chapter_2/index.html)
- markmap [`markmaps/chapter_02_pod_security.mm`](../markmaps/chapter_02_pod_security.mm)

## Ожидаемое время

75-120 минут

## Задание

1. Просмотрите базовые манифесты `frontend`, `orders` и `payments`.
2. Определите, какие проблемы минимальные требования допуска должны закрыть в первую очередь:
   - mutable tags;
   - отсутствие ресурсов;
   - отсутствие probes;
   - избыточные привилегии;
   - использование неподходящих registry.
3. Подготовьте target state для namespace:
   - какой PSS-уровень нужен;
   - где достаточно официального уровня PSS `baseline`;
   - где нужен путь к `restricted`.
4. Составьте черновик `OperationPolicy`:
   - allowed registries;
   - required requests/limits;
   - required probes;
   - disallowed tags.
5. Подготовьте примеры манифестов:
   - `ModuleConfig` для `admission-policy-engine` в режиме `Warn`;
   - `OperationPolicy` с `match`, чтобы было видно, на какие namespace она действует;
   - фрагмент `Deployment`, где исправлены `securityContext`, probes и resources.
6. Опишите rollout:
   - warning stage;
   - исправление нарушений;
   - deny stage;
   - исключения для legacy.

## Что нужно сдать

- policy matrix по namespace;
- черновик минимальных требований допуска в виде YAML-манифестов;
- план rollout от `warn` к `deny`;
- список технического долга по приложениям.

## Критерии завершения

- не используется стратегия “сразу всё в deny”;
- видны различия между PSS и эксплуатационными требованиями вроде probes, ресурсов и разрешённых registry;
- есть отдельная стратегия для legacy-приложений;
- политика описана как platform default, а не как единичная ручная проверка.
