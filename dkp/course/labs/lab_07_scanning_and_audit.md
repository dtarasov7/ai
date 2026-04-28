# Лабораторная работа 7. Scanning, supply chain и разбор найденных проблем

## Цель

Собрать слой обнаружения проблем для `shop-demo` и замкнуть найденные проблемы (findings) на конкретные инженерные действия.

## Исходные материалы

- манифесты `shop-demo`:
  - [`00-namespaces.yaml`](../shop-demo/manifests/00-namespaces.yaml)
  - [`10-frontend.yaml`](../shop-demo/manifests/10-frontend.yaml)
  - [`20-orders.yaml`](../shop-demo/manifests/20-orders.yaml)
  - [`30-payments.yaml`](../shop-demo/manifests/30-payments.yaml)
  - [`40-platform-tools.yaml`](../shop-demo/manifests/40-platform-tools.yaml)
  - [`kustomization.yaml`](../shop-demo/manifests/kustomization.yaml)
- [глава 7 курса](../chapter_7/index.html)
- markmap [`markmaps/chapter_07_scanning_and_audit.mm`](../markmaps/chapter_07_scanning_and_audit.mm)

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
