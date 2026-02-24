`jaeger-spark-dependencies` — это Spark‑джоб, и логирование там идет через **Log4j2** (в README прямо упоминается `LOG4J_STATUS_LOGGER_LEVEL` для StatusLogger Log4j2).   
Чтобы увести логи именно в **stdout**, нужно не “настроить Jaeger”, а **дать Log4j2 конфиг с Console appender, у которого `target = SYSTEM_OUT`**, и подключить этот конфиг при старте JVM. 

## Вариант для `java -jar ...` (самый простой и надежный)

### 1) Создайте файл `log4j2.properties` рядом с jar

Пример минимального конфига, который пишет в stdout:

```properties
status = warn
name = JaegerSparkDependencies

appenders = console

appender.console.type = Console
appender.console.name = STDOUT
appender.console.target = SYSTEM_OUT
appender.console.layout.type = PatternLayout
appender.console.layout.pattern = %d{ISO8601} %-5p [%t] %c{1.} - %m%n

rootLogger.level = info
rootLogger.appenderRefs = stdout
rootLogger.appenderRef.stdout.ref = STDOUT

# (опционально) приглушить шумные пакеты Spark/Hadoop
logger.spark.name = org.apache.spark
logger.spark.level = warn
logger.hadoop.name = org.apache.hadoop
logger.hadoop.level = warn
```

Параметр `target` у ConsoleAppender как раз и определяет, будет вывод в `SYSTEM_OUT` или `SYSTEM_ERR`. 

### 2) Запустите jar, указав Log4j2 конфиг через system property

```bash
STORAGE=cassandra \
java -Dlog4j.configurationFile=file:./log4j2.properties \
  -jar jaeger-spark-dependencies.jar
```

Log4j2 официально поддерживает задание пути к конфигу через system property `log4j.configurationFile`. 

## Если запускаете в контейнере (на всякий случай)
В README у образа/джоба предусмотрен `JAVA_OPTS` для проброса JVM‑флагов.   
Тогда обычно делают так: монтируют конфиг в контейнер и добавляют:

```bash
-e JAVA_OPTS="-Dlog4j.configurationFile=file:/path/log4j2.properties"
```

## Как быстро проверить, что подхватился именно ваш конфиг
Если есть сомнения, включите внутренние диагностические сообщения Log4j2 (StatusLogger) — в README для этого как раз приводится переменная `LOG4J_STATUS_LOGGER_LEVEL=DEBUG`.   
После этого в выводе будет видно, какой конфиг-файл Log4j2 реально нашел/загрузил.

## Важная ремарка про версии Spark / Log4j
Если вы вдруг используете **очень старую** сборку `spark-dependencies`, собранную на Spark **до 3.3**, там мог быть Log4j 1.x; начиная со Spark 3.3 Spark переехал на Log4j 2.x.   
Но для актуальных версий подход выше с `log4j2.properties` и `-Dlog4j.configurationFile=...` — правильный.

Если нужно, можно сделать формат логов “как в Spark template” (с MDC `mdc.taskName` и т.п.), но для вывода в stdout достаточно конфига выше.
