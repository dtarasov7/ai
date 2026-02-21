### Что выбрать для Jaeger **1.53** + **OpenSearch 2.19**

`jaeger-spark-dependencies.jar` **не привязан жёстко к версии Jaeger 1.53** (это отдельный Spark-job, который читает спаны из стораджа и пишет агрегированные “dependency links”, которые потом показывает UI). Важно в первую очередь, чтобы job умел работать **с вашим типом стораджа** и форматом индексов/префиксов. В документации Jaeger прямо сказано, что для продакшн-стораджей нужен внешний процесс агрегации зависимостей (spark-dependencies). 

Так как у вас backend **OpenSearch 2.19 (ветка 2.x)**, берите **spark-dependencies версии не ниже `v0.7.0`**, потому что именно в `v0.7.0` добавили поддержку OpenSearch.   
На практике лучше брать **последний доступный тег** — на текущий момент это **`v0.7.2`** (есть отдельный образ/вариант `-opensearch`). 

---

## Как скачать / получить JAR

### Вариант A (рекомендуется): запускать готовый container image (GHCR)
У `spark-dependencies` есть **вариантные теги образов**, включая `VERSION-opensearch` для OpenSearch 2.x/3.x.   
В GitHub Container Registry опубликован, например, тег **`v0.7.2-opensearch`**. 

Пример запуска:
```bash
docker pull ghcr.io/jaegertracing/spark-dependencies/spark-dependencies:v0.7.2-opensearch

docker run --rm \
  -e OS_NODES=http://opensearch:9200 \
  ghcr.io/jaegertracing/spark-dependencies/spark-dependencies:v0.7.2-opensearch \
  2026-02-20
```

Что важно для OpenSearch-конфига:
- `STORAGE=opensearch` (нужно при запуске “универсального” jar, а для `-opensearch`-образа обычно уже не требуется),
- `OS_NODES` — URL(ы) нод OpenSearch,
- опционально: `OS_NODES_WAN_ONLY`, `OS_USERNAME`, `OS_PASSWORD`, `OS_INDEX_PREFIX`, `OS_INDEX_DATE_SEPARATOR`, `OS_TIME_RANGE`. 

---

### Вариант B: “скачать jar” через извлечение из docker-образа
Отдельной “прямой” ссылки типа *download jaeger-spark-dependencies.jar* проект обычно не даёт как Maven-артефакт; зато JAR лежит **внутри образа** по пути **`/app/app.jar`**. Это видно из Dockerfile/entrypoint. 

Извлечь:
```bash
docker create --name sd \
  ghcr.io/jaegertracing/spark-dependencies/spark-dependencies:v0.7.2-opensearch

docker cp sd:/app/app.jar ./jaeger-spark-dependencies.jar
docker rm sd
```

Дальше этот jar можно запускать “как в контейнере” через main-class (entrypoint выбирает класс `OpenSearchDependenciesJob` для opensearch-варианта). 

---

### Вариант C: собрать JAR из исходников (если нужен “нативный” jar под вашу среду)
README проекта описывает сборку Maven’ом и запуск как unified-jar или storage-specific jar, включая OpenSearch. 

Общий принцип:
```bash
git clone https://github.com/jaegertracing/spark-dependencies.git
cd spark-dependencies
git checkout v0.7.2

./mvnw clean package -DskipTests
# затем запуск (пример из README):
STORAGE=opensearch OS_NODES=http://localhost:9200 \
  java -jar jaeger-spark-dependencies/target/jaeger-spark-dependencies-*.jar
```
(в репозитории `pom.xml` на main действительно “snapshot”, но при checkout тега вы собираете состояние под этот релиз; команды из README ориентируют, где лежат jar’ы после сборки). 

---

## Важное примечание про Jaeger 1.53
Jaeger v1 официально **EOL с 31 декабря 2025**, то есть Jaeger **1.53** уже вне поддержки (сегодня 21 февраля 2026).   
Это не мешает запустить spark-dependencies, но если вы упираетесь в совместимость библиотек/Java/Spark, самый надёжный путь — планировать апгрейд Jaeger.

--- 

### Короткая рекомендация именно для вашего кейса (OpenSearch 2.19)
- **Берите**: `ghcr.io/jaegertracing/spark-dependencies/spark-dependencies:v0.7.2-opensearch`   
- **Настройте**: `OS_NODES`, при необходимости `OS_USERNAME/OS_PASSWORD`, `OS_INDEX_PREFIX` (если у вас кастомный префикс индексов Jaeger).   
- Если нужен именно **jar-файл** — проще всего **вытащить `/app/app.jar` из контейнера**. 




Для **запуска `jaeger-spark-dependencies` v0.7.2** ориентируйтесь на **Java 21**.

Почему так:

- Официальный runtime-контейнер для v0.7.2 собран на базе **`eclipse-temurin:21 ... -jre`** — то есть сам проект предполагает запуск именно на **JRE 21**.   
- В README для интеграционных тестов прямо указано требование **“Java 21”** (Temurin рекомендован).   
- Startup-скрипт контейнера добавляет JVM-флаги, нужные Spark’у на **Java 21+** (`--add-opens ...`), что также подтверждает целевую версию рантайма.   

## Практически
- Поставьте **JRE/JDK 21** (например, Temurin 21).
- Проверьте:
  ```bash
  java -version
  ```
  Должно быть **21.x**.

## Если запускаете JAR вне контейнера
Обратите внимание: в контейнере JAR запускается не через `java -jar`, а через `-cp ... <MainClass>` и с набором `--add-opens`.   
Для OpenSearch-варианта main class:  
`io.jaegertracing.spark.dependencies.opensearch.OpenSearchDependenciesJob`   

То есть “в лоб” может понадобиться запуск примерно в таком стиле (флаги можно взять 1-в-1 из `entrypoint.sh` в репозитории/образе):

```bash
OS_NODES=http://opensearch:9200 \
java <SPARK_JAVA_OPTS_из_entrypoint.sh> -cp jaeger-spark-dependencies-v0.7.2.jar \
  io.jaegertracing.spark.dependencies.opensearch.OpenSearchDependenciesJob \
  2026-02-20
```

Если хотите — могу дать готовую команду целиком (с полным набором `--add-opens`) ровно как в `entrypoint.sh`, чтобы копипастить без ошибок.


Ниже — готовая команда **для запуска JAR напрямую (без Docker)** под **OpenSearch**, повторяющая ровно то, как это делает `entrypoint.sh` в `v0.7.2` (включая нужные `--add-opens` для Java 21+ и правильный `MainClass` для OpenSearch). 

### 1) Запуск `jaeger-spark-dependencies-v0.7.2.jar` (OpenSearch) — один копипаст

```bash
export OS_NODES="http://opensearch:9200"
# опционально:
# export OS_USERNAME="admin"
# export OS_PASSWORD="admin"
# export OS_INDEX_PREFIX="jaeger"   # если у вас кастомный префикс индексов

JAR="./jaeger-spark-dependencies-v0.7.2.jar"

java \
  --add-opens=java.base/java.lang=ALL-UNNAMED \
  --add-opens=java.base/java.lang.invoke=ALL-UNNAMED \
  --add-opens=java.base/java.lang.reflect=ALL-UNNAMED \
  --add-opens=java.base/java.io=ALL-UNNAMED \
  --add-opens=java.base/java.net=ALL-UNNAMED \
  --add-opens=java.base/java.nio=ALL-UNNAMED \
  --add-opens=java.base/java.util=ALL-UNNAMED \
  --add-opens=java.base/java.util.concurrent=ALL-UNNAMED \
  --add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED \
  --add-opens=java.base/sun.nio.ch=ALL-UNNAMED \
  --add-opens=java.base/sun.nio.cs=ALL-UNNAMED \
  --add-opens=java.base/sun.security.action=ALL-UNNAMED \
  --add-opens=java.base/sun.util.calendar=ALL-UNNAMED \
  -Djdk.reflect.useDirectMethodHandle=false \
  -Dorg.apache.logging.log4j.simplelog.StatusLogger.level=OFF \
  -cp "$JAR" \
  io.jaegertracing.spark.dependencies.opensearch.OpenSearchDependenciesJob \
  2026-02-20
```

*Примечания:*
- Дата в конце (`2026-02-20`) — это день (UTC), за который строятся dependency links. Сегодня **2026-02-21**, поэтому примером поставил “вчера”.  
- Если нужно поднять heap: добавьте, например, `JAVA_OPTS="-Xms1g -Xmx2g"` и вставьте `${JAVA_OPTS}` после блока `--add-opens` (как в entrypoint). 

---

### 2) Если вам ок Docker (обычно проще и надёжнее)

```bash
docker run --rm \
  -e OS_NODES="http://opensearch:9200" \
  ghcr.io/jaegertracing/spark-dependencies/spark-dependencies:v0.7.2-opensearch \
  2026-02-20
```

(в этом варианте всё с Java/классом/флагами уже правильно упаковано внутри образа). 
