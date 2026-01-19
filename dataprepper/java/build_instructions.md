# Инструкции по сборке и запуску OpenTelemetry Java приложения

## Структура проекта

Создайте следующую структуру директорий:

```
otel-test/
├── Dockerfile
├── pom.xml
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── oteltest/
│                       └── Main.java
└── output/
```

## Шаг 1: Подготовка файлов

Создайте все файлы согласно артефактам:
- `Main.java` в `src/main/java/com/example/oteltest/`
- `pom.xml` в корне проекта
- `Dockerfile` в корне проекта
- Создайте пустую папку `output/` для результатов сборки

## Шаг 2: Сборка в Docker

Выполните сборку и извлечение артефактов:

```bash
# Из корневой директории проекта otel-test/
docker build --output=output .
```

После успешной сборки в папке `output/` появятся:
- `otel-test-1.0.0.jar` - ваше приложение
- `opentelemetry-javaagent.jar` - OpenTelemetry agent

## Шаг 3: Запуск с OpenTelemetry (вариант 1 - консольный вывод)

Базовый запуск с выводом телеметрии в консоль:

```bash
cd output

java -javaagent:./opentelemetry-javaagent.jar \
  -Dotel.service.name=otel-test-service \
  -Dotel.traces.exporter=logging \
  -Dotel.metrics.exporter=logging \
  -Dotel.logs.exporter=logging \
  -jar otel-test-1.0.0.jar
```

## Шаг 4: Запуск с OTLP экспортером (вариант 2)

Для отправки данных в Jaeger, Zipkin или другой OTLP-совместимый бэкенд:

### Запуск Jaeger (опционально)

```bash
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

Jaeger UI будет доступен на: http://localhost:16686

### Запуск приложения с OTLP

```bash
cd output

java -javaagent:./opentelemetry-javaagent.jar \
  -Dotel.service.name=otel-test-service \
  -Dotel.traces.exporter=otlp \
  -Dotel.metrics.exporter=otlp \
  -Dotel.logs.exporter=otlp \
  -Dotel.exporter.otlp.endpoint=http://localhost:4317 \
  -Dotel.exporter.otlp.protocol=grpc \
  -jar otel-test-1.0.0.jar
```

## Основные параметры OpenTelemetry Agent

### Обязательные параметры:
- `-javaagent:./opentelemetry-javaagent.jar` - подключение агента
- `-Dotel.service.name=<имя>` - имя вашего сервиса

### Экспортеры:
- `logging` - вывод в консоль (для тестирования)
- `otlp` - отправка в OTLP-совместимый бэкенд
- `zipkin` - отправка в Zipkin
- `jaeger` - отправка в Jaeger (legacy)

### Дополнительные полезные параметры:

```bash
# Уровень логирования агента
-Dotel.javaagent.debug=true

# Атрибуты ресурса
-Dotel.resource.attributes=environment=dev,version=1.0.0

# Настройка семплирования (0.0 - 1.0)
-Dotel.traces.sampler=parentbased_traceidratio
-Dotel.traces.sampler.arg=0.5

# OTLP через HTTP
-Dotel.exporter.otlp.protocol=http/protobuf
-Dotel.exporter.otlp.endpoint=http://localhost:4318
```

## Что будет происходить

Приложение будет:
1. Выполнять циклические операции обработки заказов
2. Автоматически создавать spans для каждого метода (благодаря агенту)
3. Случайно генерировать ошибки (~5% случаев)
4. Экспортировать traces, metrics и logs

## Проверка работы

### С консольным выводом:
Вы увидите в консоли JSON-объекты со spans, включающие:
- `traceId` и `spanId`
- Имена методов
- Длительность выполнения
- Статус операций

### С Jaeger:
1. Откройте http://localhost:16686
2. Выберите сервис "otel-test-service"
3. Нажмите "Find Traces"
4. Изучите визуализацию traces

## Остановка

Нажмите `Ctrl+C` для остановки приложения.

Для остановки Jaeger:
```bash
docker stop jaeger
docker rm jaeger
```

## Устранение проблем

### Ошибка "Class not found"
Убедитесь, что вы находитесь в папке `output/` при запуске.

### Агент не работает
Проверьте, что путь к `opentelemetry-javaagent.jar` корректен и файл существует.

### OTLP экспортер не подключается
Убедитесь, что Jaeger или другой backend запущен и доступен на указанном порту.