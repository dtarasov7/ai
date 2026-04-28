# Лабораторная работа 6. Сертификаты, секреты и delivery patterns

## Цель

Перевести доверенные материалы `shop-demo` из хаотичного состояния в управляемый контур с lifecycle, rotation и безопасной доставкой.

## Исходные материалы

- `shop-demo/manifests/`
- глава 6 курса
- markmap `markmaps/chapter_06_certs_and_secrets.mm`

## Ожидаемое время

90-120 минут

## Задание

1. Определите, какие доверенные материалы нужны системе:
   - ingress certificates;
   - service credentials;
   - API tokens;
   - CI secrets.
2. Для каждого класса данных укажите:
   - кто владелец;
   - где хранится;
   - кто ротирует;
   - как доставляется в приложение.
3. Выберите delivery pattern для:
   - современного сервиса;
   - legacy-приложения;
   - файлового сертификата.
4. Опишите модель доверия (trust model):
   - corporate CA;
   - internal CA;
   - bootstrap strategy.
5. Подготовьте rotation policy и recovery notes.
6. Подготовьте YAML-примеры:
   - `Certificate` для прикладного TLS;
   - `SecretsStoreImport` для доставки секрета файлом;
   - `Deployment` с mounted secret и отдельный вариант для ENV injection, если нужен legacy-путь.

## Что нужно сдать

- secret and certificate inventory;
- delivery matrix;
- certificate lifecycle scheme;
- манифесты доставки секрета в приложение;
- rotation and ownership policy.

## Критерии завершения

- различаются хранение, доставка и rotation;
- есть обоснование выбора delivery pattern;
- Kubernetes Secret не рассматривается как единственный доверенный контур;
- для критичных данных указаны TTL и владельцы.
