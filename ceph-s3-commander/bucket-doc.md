Вот инструкция, которую можно включить в `README.md` или отправить пользователям. Она описывает новые возможности конфигурации для работы со списками бакетов.

***

# Руководство по настройке списка бакетов и S3-совместимых хранилищ

В новой версии **S3 Commander** добавлена гибкая система управления списком бакетов. Это решает проблемы доступа, когда у пользователя нет прав на просмотр всех бакетов (`s3:ListAllMyBuckets`) или когда нужно подключить скрытые/общие бакеты.

Теперь файл `s3_buckets.txt` больше не используется. Все настройки задаются в основном конфигурационном файле `config.json`.

## 1. Режим ограниченного доступа (Strict Mode)
**Когда использовать:** У вас есть ключи доступа, но нет прав на получение списка всех бакетов (политика `Deny` на `ListAllMyBuckets`). Обычно при входе вы получали ошибку "Access Denied".

**Решение:** Используйте параметр `"buckets"`.
Если этот параметр задан, программа **не пытается** получить список через API, а сразу отображает указанные бакеты.

```json
{
  "name": "Restricted Access",
  "url": "https://s3.amazonaws.com",
  "access_key": "MY_KEY",
  "secret_key": "MY_SECRET",
  "buckets": [
    "project-alpha-data",
    "personal-backup"
  ]
}
```

## 2. Режим дополнительных бакетов (Additive Mode)
**Когда использовать:** У вас есть права на просмотр списка бакетов, но вы хотите добавить в список дополнительные (например, бакеты другого отдела или публичные бакеты, которые не видны в вашем аккаунте по умолчанию).

**Решение:** Используйте параметр `"extra_buckets"`.
Программа получит основной список через API и **добавит** к нему указанные бакеты.

```json
{
  "name": "Corporate S3",
  "url": "https://s3.corp.net",
  "access_key": "MY_KEY",
  "secret_key": "MY_SECRET",
  "extra_buckets": [
    "marketing-shared",
    "public-logs"
  ]
}
```
     
***

## Полный пример конфигурационного файла

Ниже приведен пример `config.json`, демонстрирующий все возможные варианты настройки:

```json
{
  "endpoints": [
    {
      "name": "Standard AWS",
      "url": "https://s3.amazonaws.com",
      "access_key": "AKIA...",
      "secret_key": "SECRET..."
    },
    {
      "name": "Restricted User (No Listing)",
      "comment": "Нет прав на ListBuckets, задаем список вручную",
      "url": "https://s3.us-east-1.amazonaws.com",
      "access_key": "AKIA...",
      "secret_key": "SECRET...",
      "buckets": [
        "my-work-bucket",
        "my-logs-bucket"
      ]
    },
    {
      "name": "Team Share (Additive)",
      "comment": "Листинг работает, но добавляем общие бакеты",
      "url": "https://storage.yandexcloud.net",
      "access_key": "key...",
      "secret_key": "secret...",
      "extra_buckets": [
        "shared-team-folder"
      ]
    }
  ]
}
```