Готово! Я подготовил полный docker-compose с конфигурациями для всей цепочки.

## Что включено:

1. **docker-compose.yml** - запускает 3 сервиса:
   - Mock OpenSearch (Python заглушка)
   - OpenTelemetry Collector
   - Data Prepper

2. **otel-collector-config.yaml** - полная конфигурация с:
   - OTLP receivers (gRPC и HTTP)
   - Batch processing
   - Memory limiting
   - Экспорт в Data Prepper
   - Logging для отладки

3. **data-prepper-config.yaml** - pipelines для:
   - Traces (с service map)
   - Metrics
   - Logs

4. **data-prepper-data-prepper-config.yaml** - основные настройки Data Prepper

5. **Подробные инструкции** - пошаговое руководство по запуску и тестированию

## Быстрый старт:

```bash
# 1. Создайте файл mock_opensearch.py из предыдущего артефакта
# 2. Разместите все yaml файлы в одной директории
# 3. Запустите:
docker-compose up -d

# 4. Проверьте статус:
docker-compose ps

# 5. Запустите Java приложение
```

Все сервисы настроены с health checks, логированием и правильными зависимостями. Mock OpenSearch будет показывать все данные, которые Data Prepper пытается отправить!
