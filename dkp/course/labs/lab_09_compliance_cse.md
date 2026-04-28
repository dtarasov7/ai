# Лабораторная работа 9. Compliance, CIS и DKP CSE

## Цель

Научиться читать compliance-отчёт как evidence для инженерного анализа, а не как автоматическое доказательство безопасности.

## Входные артефакты

- глава 9;
- markmap `markmaps/chapter_09_compliance_cse.mm`;
- включённый или описанный `operator-trivy`;
- namespace `payments` из предыдущих лабораторных.

## Последовательность действий

1. Включите `operator-trivy` и пометьте namespace для scanning.

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: operator-trivy
spec:
  version: 1
  enabled: true
---
apiVersion: v1
kind: Namespace
metadata:
  name: payments
  labels:
    security-scanning.deckhouse.io/enabled: ""
```

2. Найдите compliance-отчёты и отчёты по ресурсам.

```bash
d8 k get clustercompliancereports.aquasecurity.github.io -A
d8 k get vulnerabilityreports -A
d8 k get configauditreports -A
d8 k get exposedsecretreports -A
```

3. Выберите три findings и разберите их по схеме:

| Finding | Почему появился | Риск | Исправление | Владелец |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

4. Отдельно отметьте, что автоматическая проверка не покрывает: threat model, корректность бизнес-доступов, исключения, регламент break-glass и работу с внешними системами.

5. Подготовьте короткий audit pack для `shop-demo`.

## Что сдаёт слушатель

- список найденных reports;
- таблицу минимум из трёх findings;
- список ручных проверок, которые нельзя заменить CIS dashboard;
- вывод: что даёт DKP CSE и чего не заменяет сертифицированная редакция.

## Критерии завершения

- Findings превращены в конкретные действия, а не просто переписаны из отчёта.
- В отчёте есть owner и срок исправления.
- Слушатель может объяснить разницу между compliance, CIS и реальной security posture.
- Слушатель не делает вывод “CSE включён, значит всё безопасно”.
