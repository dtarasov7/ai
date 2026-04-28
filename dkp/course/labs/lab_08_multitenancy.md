# Лабораторная работа 8. Мультиарендность и безопасный проектный шаблон

## Цель

Научиться оформлять новый проект в DKP не как вручную созданный namespace, а как управляемый tenant: с квотами, default deny, администраторами и понятной зоной ответственности.

## Входные артефакты

- [глава 8](../chapter_8/index.html);
- markmap [`markmaps/chapter_08_multitenancy.mm`](../markmaps/chapter_08_multitenancy.mm);
- учебный сценарий [`shop-demo`](../shop-demo/README.md);
- доступ к учебному DKP-кластеру или dry-run окружению для проверки YAML.

## Последовательность действий

1. Включите или опишите включение модуля `multitenancy-manager`.

```yaml
apiVersion: deckhouse.io/v1alpha1
kind: ModuleConfig
metadata:
  name: multitenancy-manager
spec:
  version: 1
  enabled: true
  settings:
    allowNamespacesWithoutProjects: false
```

2. Создайте проект `payments` на основе встроенного шаблона.

```yaml
apiVersion: deckhouse.io/v1alpha2
kind: Project
metadata:
  name: payments
spec:
  description: "Payment services for shop-demo"
  projectTemplateName: default
  parameters:
    resourceQuota:
      requests:
        cpu: 5
        memory: 5Gi
        storage: 10Gi
      limits:
        cpu: 8
        memory: 8Gi
    networkPolicy: Isolated
    podSecurityProfile: Restricted
    extendedMonitoringEnabled: true
    administrators:
      - subject: Group
        name: payments-admins
```

3. Проверьте, какие ресурсы появились после создания проекта.

```bash
d8 k get projects payments
d8 k get resourcequota,networkpolicy,rolebinding -n payments
```

4. Подготовьте черновик `ProjectTemplate` для команд `shop-demo`: квота, default deny и роль администратора проекта.

5. Опишите, как шаблон будет обновляться: кто владелец, как тестировать изменение и как откатывать ошибку.

## Что сдаёт слушатель

- YAML `Project` для `payments`;
- черновик `ProjectTemplate`;
- список ресурсов, которые должен создать шаблон;
- короткое объяснение, почему обычный namespace хуже для управляемой платформы.

## Критерии завершения

- Проект имеет квоты и стартовый сетевой набор требований.
- Администраторы проекта заданы явно, а не выданы вручную “где-то в RBAC”.
- Есть решение, как новые проекты будут получать одинаковые security-настройки.
- Описан риск изменения `ProjectTemplate` для уже существующих проектов.
