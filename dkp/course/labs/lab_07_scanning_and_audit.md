# Лабораторная работа 7. Scanning, supply chain и разбор найденных проблем

## Цель

Собрать слой обнаружения проблем для `shop-demo` и замкнуть найденные проблемы (findings) на конкретные инженерные действия.

## Исходные материалы

- `shop-demo/manifests/`
- глава 7 курса
- markmap `markmaps/chapter_07_scanning_and_audit.mm`

## Ожидаемое время

90-120 минут

## Задание

1. Разберите три типа сигналов:
   - CVE в образе;
   - shell inside container;
   - подозрительная операция в API audit.
2. Для каждого определите:
   - приоритет;
   - владельца;
   - первый corrective action;
   - какие запреты, политики или ограничения нужно усилить после разбора.
3. Опишите минимальные требования к supply chain:
   - trusted registries;
   - mutable tags policy;
   - digest pinning;
   - следующий этап зрелости: signatures and SBOM.
4. Подготовьте путь разбора сигнала (triage-flow) от обнаружения до изменения конфигурации.
5. Сформулируйте SLA на разбор найденных проблем (findings) по severity.
6. Подготовьте YAML-примеры corrective actions:
   - включение scanning для namespace через label;
   - `FalcoAuditRules` для дополнительного runtime-сигнала;
   - `Deployment` с image digest вместо mutable tag;
   - policy, которая запрещает `latest` и недоверенные registry.

## Что нужно сдать

- triage matrix `signal -> owner -> priority -> action`;
- минимальные требования к supply chain;
- манифесты, которыми найденные проблемы (findings) превращаются в изменение конфигурации;
- короткий runbook для найденных проблем, похожих на инцидент (incident-like findings);
- список предотвращающих мер, которые должны пересматриваться по итогам расследования.

## Критерии завершения

- найденные проблемы (findings) не остаются “для информации”;
- есть различие между CVE, runtime и API signals;
- есть связка с политиками допуска, IAM, network policy или image policy;
- указаны владельцы и сроки реакции.
