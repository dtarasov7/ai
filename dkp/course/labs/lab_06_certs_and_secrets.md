# Лабораторная работа 6. Сертификаты, секреты и delivery patterns

## Цель

Перевести доверенные материалы `shop-demo` из хаотичного состояния в управляемый контур с lifecycle, rotation и безопасной доставкой.

## Исходные материалы

- манифесты `shop-demo`:
  - [`00-namespaces.yaml`](../shop-demo/manifests/00-namespaces.yaml)
  - [`10-frontend.yaml`](../shop-demo/manifests/10-frontend.yaml)
  - [`20-orders.yaml`](../shop-demo/manifests/20-orders.yaml)
  - [`30-payments.yaml`](../shop-demo/manifests/30-payments.yaml)
  - [`40-platform-tools.yaml`](../shop-demo/manifests/40-platform-tools.yaml)
  - [`kustomization.yaml`](../shop-demo/manifests/kustomization.yaml)
- [глава 6 курса](../chapter_6/index.html)
- markmap [`markmaps/chapter_06_certs_and_secrets.mm`](../markmaps/chapter_06_certs_and_secrets.mm)

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
