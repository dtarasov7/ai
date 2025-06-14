<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" class="logo" width="120"/>

## Архитектура решения GitLab Runners с Kaniko в Kubernetes с S3 кешем и мультитенантностью

### Основные компоненты и требования

- Kubernetes кластер, где будут развернуты GitLab Runners.
- GitLab сервер вне кластера.
- S3 совместимый сервис Ceph (версия 17.2.7), вне кластера, для хранения кеша Kaniko.
- Kaniko для сборки Docker-образов в режиме multistage без Docker daemon.
- Несколько изолированных GitLab Runners, каждый на фиксированных воркер-нодах (для требований ИБ).
- Мультитенантность: у каждого раннера свой кеш в отдельном S3 бакете с отдельными учетными данными.
- Параллельное выполнение до 20 заданий на каждый раннер.
- Мониторинг раннеров через Prometheus, развернутый в Kubernetes.

---

## Варианты архитектуры

### Вариант 1: Отдельные GitLab Runner на выделенных нодах с Kaniko и отдельными S3 бакетами

- На каждой выделенной ноде Kubernetes запускается один GitLab Runner, настроенный с Kubernetes executor.
- Каждый Runner имеет свои переменные окружения для аутентификации в отдельном S3 бакете (Ceph) для кеша Kaniko.
- Kaniko запускается внутри пайплайна как контейнер, использующий `gcr.io/kaniko-project/executor:debug`.
- Кеш Kaniko настраивается на использование S3 бакета с уникальными ключами доступа для каждого раннера.
- Теги GitLab Runner используются для маршрутизации заданий на нужный раннер.
- Параллелизм контролируется параметром `concurrent = 20` в конфигурации раннера.
- Мониторинг через Prometheus собирает метрики с раннеров и Kubernetes.

**Плюсы:**

- Полная изоляция кеша и заданий между раннерами.
- Соответствие требованиям безопасности (фиксация раннеров на конкретных нодах).
- Легко масштабировать и управлять кешем.

**Минусы:**

- Требуется больше ресурсов, так как каждый раннер — отдельный процесс.
- Управление несколькими секретами для S3 и раннеров усложняется.

---

### Вариант 2: Один GitLab Runner с несколькими параллельными executor-ами и разделением кеша по пайплайнам

- Запускается один GitLab Runner на выделенной ноде с Kubernetes executor.
- Внутри пайплайна передается переменная, указывающая на конкретный S3 бакет и учетные данные для кеша Kaniko.
- Kaniko в каждом задании использует соответствующий S3 бакет, передаваемый через переменные CI.
- Параллелизм достигается за счет executor-ов внутри одного раннера.
- Мультитенантность реализуется логикой CI/CD и переменными, но не изоляцией на уровне раннеров.

**Плюсы:**

- Меньше ресурсов на управление раннерами.
- Проще обновлять и поддерживать один раннер.

**Минусы:**

- Меньшая изоляция, возможны риски безопасности.
- Сложнее гарантировать выделение ресурсов и изоляцию по требованиям ИБ.

---

## Конфигурация GitLab Runner (пример для варианта 1)

```toml
concurrent = 20
check_interval = 0

[[runners]]
  name = "runner-java"
  url = "https://gitlab.example.com/"
  token = "TOKEN_JAVA"
  executor = "kubernetes"
  [runners.kubernetes]
    namespace = "gitlab-runners"
    node_selector = { "kubernetes.io/hostname" = "worker-node-java" }
    image = "alpine:latest"
    privileged = false
    [runners.kubernetes.volumes]
      # volume для секретов с S3 ключами
  [runners.cache]
    Type = "s3"
    Path = "runner-java-cache"
    Shared = false
    [runners.cache.s3]
      ServerAddress = "ceph-s3.example.com"
      AccessKey = "ACCESS_KEY_JAVA"
      SecretKey = "SECRET_KEY_JAVA"
      BucketName = "gitlab-runner-java-cache"
      Insecure = true
```

Аналогично для других раннеров с разными токенами, node_selector и S3 бакетами.

---

## Пример пайплайна для сборки с Kaniko

```yaml
stages:
  - build

variables:
  DOCKER_DRIVER: "overlay2"
  DOCKER_TLS_CERTDIR: ""
  # Переменные для Kaniko
  DOCKER_CONFIG: "/kaniko/.docker/"
  KANIKO_CACHE_BUCKET: "gitlab-runner-java-cache"
  AWS_ACCESS_KEY_ID: "$AWS_ACCESS_KEY_ID"
  AWS_SECRET_ACCESS_KEY: "$AWS_SECRET_ACCESS_KEY"
  AWS_REGION: "us-east-1"

build_image:
  stage: build
  image:
    name: gcr.io/kaniko-project/executor:debug
    entrypoint: [""]
  script:
    - echo "{\"auths\":{\"$CI_REGISTRY\":{\"auth\":\"$(echo -n "$CI_REGISTRY_USER:$CI_REGISTRY_PASSWORD" | base64 -w0)\"}}}" > /kaniko/.docker/config.json
    - /kaniko/executor --dockerfile $CI_PROJECT_DIR/Dockerfile --context $CI_PROJECT_DIR --destination $CI_REGISTRY_IMAGE:$CI_COMMIT_REF_SLUG --cache=true --cache-repo=$CI_REGISTRY_IMAGE/cache --cache-ttl=168h --cache-dir=s3://$KANIKO_CACHE_BUCKET
  tags:
    - java-runner
  parallel: 20
  rules:
    - if: '$CI_PIPELINE_SOURCE == "push"'
```


---

## Манифест для деплоя GitLab Runner (пример)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gitlab-runner-java
  namespace: gitlab-runners
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gitlab-runner-java
  template:
    metadata:
      labels:
        app: gitlab-runner-java
    spec:
      nodeSelector:
        kubernetes.io/hostname: worker-node-java
      containers:
        - name: gitlab-runner
          image: gitlab/gitlab-runner:latest
          volumeMounts:
            - name: config
              mountPath: /etc/gitlab-runner
            - name: s3-credentials
              mountPath: /etc/s3-credentials
          env:
            - name: AWS_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: s3-credentials-java
                  key: access_key
            - name: AWS_SECRET_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: s3-credentials-java
                  key: secret_key
      volumes:
        - name: config
          configMap:
            name: gitlab-runner-config-java
        - name: s3-credentials
          secret:
            secretName: s3-credentials-java
```


---

## Мониторинг через Prometheus

- Развернуть Prometheus в кластере.
- Включить в конфигурации GitLab Runner метрики (`metrics_server = true`).
- Настроить ServiceMonitor или PodMonitor для сбора метрик с раннеров.
- Использовать стандартные метрики GitLab Runner для алертов и дашбордов.

---

## Итог

| Вариант | Плюсы | Минусы |
| :-- | :-- | :-- |
| Отдельные раннеры на нодах | Изоляция, безопасность, простой кеш для каждого раннера | Большие затраты ресурсов, сложность управления секретами |
| Один раннер с разделением кеша | Экономия ресурсов, простота управления | Меньшая изоляция, риски безопасности |

Для требований ИБ и мультитенантности рекомендуется вариант с отдельными раннерами на фиксированных воркер-нодах, каждый с собственным кешем в отдельном S3 бакете и отдельными учетными данными.

---

Если нужны подробные скрипты регистрации раннеров, настройка секретов и примеры конфигураций CI/CD, могу подготовить дополнительно.

<div style="text-align: center">⁂</div>

[^1]: https://docs.gitlab.com/ci/docker/using_kaniko/

[^2]: https://arborxr.com/blog/developers-journal-building-unprivileged-multi-arch-images-with-kaniko-and-gitlab-ci

[^3]: https://gitlab.com/gitlab-org/gitlab-runner/-/issues/35989

[^4]: https://github.com/GoogleContainerTools/kaniko

[^5]: https://gitlab.cn/docs/en/ee/ci/docker/using_kaniko.html

[^6]: https://www.reddit.com/r/devops/comments/pkazs6/should_i_run_gitlab_runner_on_kubernetes_cluster/?tl=ru

[^7]: https://overcast.blog/gitlab-ci-kaniko-building-container-image-in-kubernetes-runners-without-privileged-mode-663a274e8a07

[^8]: https://habr.com/ru/articles/764568/

