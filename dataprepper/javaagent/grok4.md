Вот подробный ответ на ваш вопрос о настройке OpenTelemetry Java Agent для отправки **только трейсов** (traces) в OpenTelemetry Collector (otelcol), без логов и метрик. Я опираюсь на официальную документацию OpenTelemetry (например, из раздела Java Agent на opentelemetry.io), где описана автоматическая инструментация для Java-приложений.

### Краткий обзор
- OpenTelemetry Java Agent — это JAR-файл, который прикрепляется к вашему Java-приложению (начиная с Java 8+). Он автоматически собирает телеметрию (включая трейсы) из популярных библиотек (например, Spring, JDBC, HTTP-клиенты) без изменения кода.
- По умолчанию агент фокусируется на трейсах, но в некоторых конфигурациях или версиях может включать метрики и логи. Чтобы явно отключить метрики и логи, используйте системные свойства (или файл конфигурации).
- Экспортер для отправки в otelcol — это обычно OTLP (OpenTelemetry Protocol), который работает по gRPC или HTTP.

### Шаги по настройке
1. **Скачайте OpenTelemetry Java Agent**:
   - Загрузите последнюю версию JAR-файла `opentelemetry-javaagent.jar` с GitHub-репозитория OpenTelemetry (https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases). Например, версия 2.0+ поддерживает все необходимые опции.

2. **Запустите ваше Java-приложение с агентом**:
   - Добавьте `-javaagent` в команду запуска. Пример для вашего JAR-файла приложения:
     ```
     java -javaagent:/path/to/opentelemetry-javaagent.jar \
          -Dotel.metrics.exporter=none \
          -Dotel.logs.exporter=none \
          -Dotel.traces.exporter=otlp \
          -Dotel.exporter.otlp.endpoint=http://your-otelcol-host:4318 \
          -jar /path/to/your-app.jar
     ```
     - **Объяснение опций**:
       - `-Dotel.metrics.exporter=none`: Отключает экспорт метрик. Никакие метрики не будут собираться или отправляться.
       - `-Dotel.logs.exporter=none`: Отключает экспорт логов. Логи не будут передаваться в collector.
       - `-Dotel.traces.exporter=otlp`: Указывает, что трейсы должны экспортироваться через OTLP-протокол (по умолчанию это и есть, но лучше указать явно).
       - `-Dotel.exporter.otlp.endpoint=http://your-otelcol-host:4318`: Адрес вашего OpenTelemetry Collector. Замените `your-otelcol-host` на реальный хост (например, `localhost` для локальной разработки). Порт 4318 — стандартный для HTTP/OTLP; для gRPC используйте 4317.
     - Если вы хотите отключить сбор метрик/логов на уровне инструментации (не только экспорт), добавьте:
       - `-Dotel.instrumentation.metrics.enabled=false`
       - `-Dotel.instrumentation.logs.enabled=false` (доступно в версиях 1.20+).

3. **Альтернатива: Настройка через файл конфигурации**:
   - Если вы не хотите передавать все опции через командную строку, создайте YAML-файл (например, `otel-agent-config.yaml`) с таким содержимым:
     ```
     metrics:
       exporters: [none]
     logs:
       exporters: [none]
     traces:
       exporters: [otlp]
     service:
       telemetry:
         metrics:
           address: ""  # Отключает метрики
         logs:
           level: none  # Отключает логи
     exporters:
       otlp:
         endpoint: "http://your-otelcol-host:4318"
     ```
   - Затем запустите приложение с указанием файла:
     ```
     java -javaagent:/path/to/opentelemetry-javaagent.jar \
          -Dotel.javaagent.configuration-file=/path/to/otel-agent-config.yaml \
          -jar /path/to/your-app.jar
     ```

4. **Настройка OpenTelemetry Collector**:
   - Убедитесь, что ваш otelcol настроен на приём только трейсов. В конфигурации collector (файл `config.yaml`) укажите:
     ```
     receivers:
       otlp:
         protocols:
           http:  # Или grpc
             endpoint: 0.0.0.0:4318
     processors: []  # Если не нужны
     exporters:
       # Ваш экспортер (например, Jaeger, Zipkin или logging для тестов)
       logging:  # Для отладки
         loglevel: debug
     service:
       pipelines:
         traces:
           receivers: [otlp]
           exporters: [logging]  # Или ваш backend
         metrics: null  # Отключает пайплайн метрик
         logs: null     # Отключает пайплайн логов
     ```
   - Запустите collector: `otelcol --config=config.yaml`.

### Проверка
- Запустите приложение и сгенерируйте трафик (например, HTTP-запросы).
- В логах collector или в backend (например, Jaeger) вы увидите только трейсы. Метрик и логов не должно быть.
- Для отладки добавьте `-Dotel.javaagent.debug=true` в запуск агента — это выведет дополнительные логи о том, что собирается.

### Возможные проблемы и советы
- **Версия агента**: Убедитесь, что используете свежую версию (например, 2.0+). Старые версии могут не поддерживать отключение метрик/логов.
- **По умолчанию**: В большинстве случаев агент собирает только трейсы автоматически. Если вы видите метрики/логи, возможно, в вашем коде есть ручная инструментация — проверьте импорты из `io.opentelemetry.api`.
- **Ресурсы**: Если трейсы не отправляются, проверьте сетевые соединения и порты. Для HTTPS используйте `https://` в endpoint.
- **Дополнительная документация**: Посмотрите полную конфигурацию на https://opentelemetry.io/docs/zero-code/java/agent/ или русскоязычные статьи на Habr (например, о OpenTelemetry в распределённых системах).

Если у вас есть дополнительные детали (версия Java, агент или код примера), я могу уточнить!
