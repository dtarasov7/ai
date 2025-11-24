---
markmap:
  initialExpandLevel: 2
  colorFreezeLevel: 2
---

# Инжектирование секретов из Vault в Deckhouse

## Подходы
- С использованием модуля Deckhouse: secrets-store-integration
- Без использования модуля (ручные/альтернативные решения)
- Доп. автоматизация перезапусков: pod-reloader

## С secrets-store-integration (рекомендуемый)
- Что делает модуль
  - Устанавливает/настраивает Secrets Store CSI Driver
  - Подключает Vault provider для CSI
  - Упрощает декларацию источников секретов (через SecretProviderClass и/или обертки Deckhouse)
- Потоки инжектирования
  - Монтирование как том (in-memory, tmpfs)
    - Pod монтирует volume из CSI
    - Приложение читает секреты из файлов
    - Ротация: файлы обновляются драйвером на томе
    - Перезапуск: не нужен, если приложение поддерживает hot-reload; иначе — сторонние механизмы
  - Синхронизация в Kubernetes Secret
    - CSI синхронизирует значения в нативный Secret (опция sync)
    - Приложение потребляет Secret: env/volume
    - Ротация: Secret обновляется при изменении в Vault
    - Перезапуск: через pod-reloader (rolling restart)
- Аутентификация в Vault
  - Kubernetes Auth (ServiceAccount JWT, аудитория)
  - AppRole / JWT-OIDC (при необходимости)
  - Политики Vault с минимальными правами (RBAC/Policies)
- Плюсы
  - Нативная интеграция с Deckhouse
  - Меньше ручной обвязки
  - Можно выбрать mount-only или sync-to-Secret
- Минусы/учесть
  - При sync → секреты попадают в etcd (включайте encryption-at-rest)
  - При mount-only → приложение должно уметь перечитывать файлы

## Без secrets-store-integration
- Вариант A: Ручная установка Secrets Store CSI + Vault Provider
  - Объекты
    - SecretProviderClass (описывает путь в Vault, формат выдачи, sync=true/false)
    - ServiceAccount/Role/RoleBinding для Kubernetes Auth
  - Режимы
    - Mount-only
      - Файлы на in-memory volume, автоматическая ротация
      - Перезапуск: только при необходимости (hot-reload в приложении)
    - Sync-to-Secret
      - Создание/обновление Kubernetes Secret
      - Перезапуск: через pod-reloader
  - Плюсы: гибкость, контроль версий драйверов/провайдера
  - Минусы: больше ручной поддержки
- Вариант B: External Secrets Operator (ESO)
  - Объекты
    - SecretStore / ClusterSecretStore (доступ к Vault)
    - ExternalSecret (mapping Vault → Kubernetes Secret)
  - Поведение
    - Пишет значения в нативный Secret (env/volume для Pod)
    - Ротация: по расписанию или при изменениях
    - Перезапуск: через pod-reloader
  - Плюсы: богатые шаблоны, агрегирование из разных источников
  - Минусы: секреты в etcd (включать encryption-at-rest)
- Вариант C: Vault Agent Injector (Mutating Webhook)
  - Механика
    - Аннотации в Pod → добавляется init/sidecar с Vault Agent
    - Аутентификация: Kubernetes Auth
    - Агент рендерит секреты в общий том (например, emptyDir) по шаблону
  - Ротация
    - Sidecar обновляет файлы и продлевает токены
    - Перезапуск: не обязателен (hot-reload приложения); иначе — триггер внешнего перезапуска
  - Плюсы: секреты не попадают в Kubernetes Secret/etcd
  - Минусы: сложнее отладка/наблюдаемость, требуется поддержка hot-reload
- Вариант D: Прямой доступ приложения к Vault (SDK/HTTP)
  - Приложение само получает токен (Kubernetes Auth), читает/кеширует секреты
  - Ротация: логика в приложении (watch/renew)
  - Плюсы: наименьшая поверхность в Kubernetes
  - Минусы: логика секретов в коде, сложнее универсализация

## pod-reloader (дополнительно)
- Для чего
  - Отслеживает изменение Kubernetes Secret/ConfigMap
  - Триггерит rolling restart у Deployment/StatefulSet/DaemonSet
- Когда нужен
  - Sync-to-Secret (CSI, ESO): да
  - Mount-only (CSI, Vault Agent): нет (изменение файлов не видно контроллеру)
- Настройка
  - Автоматический режим: label/annotation (например, reloader.stakater.com/auto: "true")
  - Точечный режим: перечисление зависимостей (reloader.stakater.com/targets: "<ns>/<secret>,...")
  - Границы: не реагирует на изменения файлов в смонтированных томах
- Паттерны триггера при mount-only
  - Sidecar, который обновляет аннотацию Pod/Deployment при изменении файла
  - Обновление dummy ConfigMap/Secret → reloader ловит изменение
  - Применение checksum-annotaton паттерна в манифестах (helm/kustomize)

## Безопасность и соответствие
- Минимизация прав
  - Узкоспециализированные Vault policies (на конкретные пути)
  - ServiceAccount на workload-уровне (не кластерном)
- Защита Secret в Kubernetes
  - Включить encryption-at-rest для etcd (обязательно при sync-to-Secret)
  - Ограничить права чтения Secret через RBAC/OPA/Gatekeeper
- Сетевые меры
  - NetworkPolicy до Vault/Injector/ESO/CSI
  - mTLS к Vault, проверка CA
- Аудит и наблюдаемость
  - Аудит Vault (enable audit devices)
  - Метрики CSI/ESO/Vault Agent
  - Алерты на токен-ренью и ошибки авторизации

## Выбор подхода (как решить)
- Нужны секреты вне etcd?
  - Да → Mount-only (CSI) или Vault Agent
  - Нет → Sync-to-Secret (CSI/ESO) + pod-reloader
- Требуется hot-reload без рестартов?
  - Да → Mount-only (CSI) или Vault Agent + поддержка reread в приложении
  - Нет → Sync-to-Secret + pod-reloader
- Простота эксплуатации
  - Максимально просто → secrets-store-integration (Deckhouse)
  - Гибкость/совмещение источников → ESO
  - Полный контроль и минимум следа в K8s → Vault Agent / прямой доступ

## Короткие дорожные карты (how-to)
- secrets-store-integration (sync-to-Secret)
  - Создать SecretProviderClass (Vault path/role, sync: true)
  - Привязать ServiceAccount с корректной JWT аудиторияй
  - Подключить Secret в Pod (env/volume)
  - Включить pod-reloader для workload
- secrets-store-integration (mount-only)
  - SecretProviderClass (sync: false)
  - volume/volumeMount в Pod
  - Обеспечить hot-reload (SIGHUP/fsnotify) или триггер через аннотации
- Vault Agent Injector
  - Аннотации в Pod (role, templates, refresh)
  - Общий том для приложения
  - Настроить реакцию приложения на обновление файлов или внешний триггер
- ESO
  - ClusterSecretStore/SecretStore (Vault creds)
  - ExternalSecret → Secret
  - Подключить Secret в Pod + pod-reloader
