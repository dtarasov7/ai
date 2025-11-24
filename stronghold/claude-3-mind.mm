# Диаграмма вариантов инжектирования секретов в Deckhouse

```markdown
# Инжектирование секретов в Deckhouse

## Stronghold в том же кластере

### С secrets-store-integration

#### Автоматическая конфигурация
- connectionConfiguration: DiscoverLocalStronghold
- Автообнаружение Stronghold
- Минимальная настройка

#### CSI Driver
- Монтирование как volume
- Автообновление секретов (каждые 2 минуты)
- ReadOnly файловая система

#### Методы доставки в приложение
- Прямое чтение файлов
  - /mnt/secrets/secret-name
  - Требует изменения кода
- Wrapper script для env
  - Читает файлы при старте
  - Экспортирует как переменные
- Init container
  - Подготавливает секреты
  - Передает основному контейнеру

### Без secrets-store-integration

#### Native K8s Secrets
- Создание через kubectl
- Ручное управление
- Base64 кодирование

#### External Secrets Operator
- Синхронизация из Stronghold
- Создает K8s секреты
- Периодическое обновление

#### Vault Agent Injector
- Sidecar контейнер
- Шаблонизация секретов
- Динамическое обновление

#### Direct API calls
- Приложение обращается к Stronghold
- Требует Vault SDK
- Полный контроль

## Stronghold вне кластера

### С secrets-store-integration

#### Ручная конфигурация
- connectionConfiguration: Manual
- Указание URL и authPath
- Настройка CA сертификата

#### Аутентификация
- Kubernetes auth (remote)
  - JWT токены ServiceAccount
  - Настройка для каждого кластера
- AppRole
  - RoleID + SecretID
  - Программная аутентификация
- Token
  - Прямая аутентификация
  - Требует ротации

#### Сетевые требования
- HTTPS доступ (443)
- Firewall правила
- Network policies
- Приватные соединения (VPN/Peering)

#### Методы доставки
- CSI volumes
  - Те же что и для локального
- Environment variables
  - Через annotations
  - Через configmaps

### Без secrets-store-integration

#### Vault Secrets Operator
- CRD для секретов
- Синхронизация в K8s secrets
- Multi-cluster поддержка

#### Sealed Secrets
- Шифрование на клиенте
- Расшифровка в кластере
- GitOps friendly

#### External Secrets Operator
- Поддержка множества backends
- Централизованная конфигурация
- Namespace isolation

#### CI/CD Pipeline
- Jenkins/GitLab интеграция
- Инжект при деплое
- Template substitution

#### Custom Controllers
- Operator pattern
- Business logic
- Fine-grained control

## Сравнение подходов

### Производительность
- Локальный Stronghold
  - ✅ Минимальная латентность
  - ✅ Нет сетевых задержек
  - ❌ Нагрузка на master nodes
- Внешний Stronghold
  - ❌ Сетевая латентность
  - ✅ Выделенные ресурсы
  - ✅ Масштабируемость

### Безопасность
- С secrets-store-integration
  - ✅ Нет секретов в etcd
  - ✅ Временные credentials
  - ✅ Audit trail
- Без secrets-store-integration
  - ❌ Секреты в K8s secrets
  - ⚠️ Base64 не шифрование
  - ⚠️ RBAC ограничения

### Управляемость
- Централизованный
  - ✅ Единая точка управления
  - ✅ Консистентность
  - ❌ Single point of failure
- Распределенный
  - ✅ Независимость кластеров
  - ❌ Сложность синхронизации
  - ❌ Дублирование настроек

### Сложность внедрения
- Простые решения
  - K8s Secrets (базовый)
  - secrets-store-integration + local
  - Sealed Secrets
- Средние решения
  - External Secrets Operator
  - Vault Agent Injector
  - secrets-store-integration + remote
- Сложные решения
  - Custom operators
  - Multi-cluster federation
  - Hybrid подходы

## Рекомендации по выбору

### Small/Dev окружения
- K8s Secrets + RBAC
- Sealed Secrets для GitOps
- Local Stronghold для изоляции

### Production (один кластер)
- secrets-store-integration + local Stronghold
- Vault Agent для legacy apps
- External Secrets как fallback

### Enterprise (multi-cluster)
- Централизованный Stronghold
- secrets-store-integration везде
- Backup стратегия обязательна

### Compliance требования
- Внешний HSM-backed Stronghold
- Полный audit trail
- Encryption at rest & in transit
```

Эта mind map структура показывает:

1. **Два основных разветвления** по расположению Stronghold (в кластере / вне кластера)
2. **Подразделение** на варианты с secrets-store-integration и без него
3. **Детализацию** каждого подхода с техническими особенностями
4. **Сравнительный анализ** по ключевым критериям
5. **Рекомендации** для различных сценариев использования

Для визуализации этой mind map можно использовать:
- Online инструменты: [markmap.js.org](https://markmap.js.org)
- VSCode extension: Markmap
- Экспорт в HTML/SVG для презентаций

Структура позволяет быстро оценить все доступные варианты и выбрать подходящий под конкретные требования проекта.
