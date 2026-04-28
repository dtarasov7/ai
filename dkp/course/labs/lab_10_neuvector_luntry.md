# Лабораторная работа 10. NeuVector, Luntry и внешние security-платформы

## Цель

Научиться выбирать, когда встроенных механизмов DKP достаточно, а когда внешний container security product действительно закрывает полезный gap.

## Входные артефакты

- глава 10;
- markmap `markmaps/chapter_10_neuvector_luntry.mm`;
- список уже включённых DKP-механизмов: admission, RBAC, NetworkPolicy, `operator-trivy`, runtime audit, API audit, log forwarding;
- публичные материалы NeuVector и Luntry.

## Последовательность действий

1. Составьте decision matrix.

| Задача | DKP built-in | NeuVector | Luntry | Нужен ли внешний продукт |
| --- | --- | --- | --- | --- |
| Image scanning |  |  |  |  |
| Runtime protection |  |  |  |  |
| Network map |  |  |  |  |
| SOC workflow |  |  |  |  |
| Compliance evidence |  |  |  |  |

2. Подготовьте минимальный `ModuleConfig` для пилота NeuVector.

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: neuvector
spec:
  version: 1
  enabled: true
  settings:
    highAvailability: true
    controller:
      storageClass: nfs-rwx
    https:
      mode: CertManager
      certManager:
        clusterIssuerName: letsencrypt
```

3. Опишите безопасный rollout режимов для одного namespace:

- Discover: собрать поведение приложения;
- Monitor: увидеть нарушения без блокировки;
- Protect: включить enforcement только после review правил.

4. Для Luntry подготовьте список вопросов к вендору перед пилотом:

- версии DKP, Kubernetes, CRI и Linux kernel;
- требуемые privileged permissions, host mounts и eBPF capabilities;
- Helm values, RBAC и namespace labels;
- какие данные остаются внутри периметра;
- интеграции с SIEM, registry, audit log и DKP logging;
- сценарий обновления, backup/restore и работа в закрытом контуре.

## Что сдаёт слушатель

- decision matrix;
- план пилота NeuVector;
- список вопросов к Luntry;
- вывод: где внешний продукт полезен, а где он создаёт лишнюю сложность.

## Критерии завершения

- Решение принято по задачам, а не по “длинному списку функций”.
- Учтены ресурсы, privileged-доступ, storage, отказоустойчивость и false positives.
- Есть rollback из enforcement-режима.
- По Luntry явно отделены публично подтверждённые факты от вопросов, требующих вендорской документации.
