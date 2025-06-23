# Установка и настройка системы резервного копирования S3

## Требования

- Ceph 17.2.7 с S3 API
- rclone v1.65.2
- bash 4.0+
- jq (опционально, для более точного сравнения списков объектов)
- достаточное дисковое пространство для бэкапов и архивов

## Установка

### 1. Подготовка окружения

```bash
# Создание каталогов
sudo mkdir -p /backup /archive /opt/s3-backup
sudo chown $USER:$USER /backup /archive /opt/s3-backup

# Копирование скриптов
cp s3-backup.sh /opt/s3-backup/
cp s3-archive.sh /opt/s3-backup/
chmod +x /opt/s3-backup/*.sh
```

### 2. Настройка rclone

```bash
# Создание конфигурации rclone
rclone config

# Пример конфигурации для Ceph S3:
# [s3]
# type = s3
# provider = Ceph
# access_key_id = YOUR_ACCESS_KEY
# secret_access_key = YOUR_SECRET_KEY
# endpoint = http://your-ceph-cluster:8080
# acl = private
# bucket_acl = private
# upload_cutoff = 200M
# chunk_size = 64M
# disable_checksum = true
# use_multipart_uploads = true
# multipart_chunk_size = 64M
# multipart_threshold = 200M
```

### 3. Проверка настроек

```bash
# Проверка доступности S3
rclone lsd s3:

# Проверка текущих бакетов
rclone lsd s3: | grep storage-

# Тестовый запуск backup скрипта
/opt/s3-backup/s3-backup.sh

# Тестовый запуск archive скрипта
/opt/s3-backup/s3-archive.sh
```

### 4. Настройка cron

```bash
# Установка cron заданий
crontab -e

# Добавить строки из crontab конфигурации
```

### 5. Настройка логротации

```bash
# Копирование конфигурации logrotate
sudo cp logrotate.conf /etc/logrotate.d/s3-backup

# Проверка конфигурации
sudo logrotate -d /etc/logrotate.d/s3-backup
```

## Мониторинг

### Метрики Prometheus

Скрипты создают метрики в формате Prometheus в файлах:
- `/backup/storage-YYYYMMD-backup/metrics-DD-HH-MM.txt`
- `/archive/storage-YYYYMMD/archive-metrics-DD-HH-MM.txt`

### Основные метрики

**Backup метрики:**
- `s3_backup_copied_objects_total` - количество скопированных объектов
- `s3_backup_deleted_objects_total` - количество удаленных объектов
- `s3_backup_copy_duration_seconds` - время копирования
- `s3_backup_script_duration_seconds` - общее время выполнения
- `s3_backup_copied_bytes_total` - размер скопированных данных
- `s3_backup_success` - флаг успешного выполнения
- `s3_backup_error` - метрики ошибок

**Archive метрики:**
- `s3_archive_copied_objects_total` - количество архивированных объектов
- `s3_archive_copy_duration_seconds` - время архивации
- `s3_archive_script_duration_seconds` - общее время выполнения
- `s3_archive_copied_bytes_total` - размер архивированных данных
- `s3_archive_success` - флаг успешного выполнения
- `s3_archive_average_speed_bytes_per_second` - средняя скорость копирования
- `s3_archive_error` - метрики ошибок

### Настройка Prometheus

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 's3-backup'
    static_configs:
      - targets: ['localhost:9090']
    file_sd_configs:
      - files:
        - '/backup/*/metrics-*.txt'
        - '/archive/*/archive-metrics-*.txt'
    scrape_interval: 30s
```

## Логирование

### Структура логов

```
/backup/storage-YYYYMMD-backup/
├── backup.log                    # Общий лог backup и archive
├── rclone-DD-HH-MM.log           # Лог rclone для каждого запуска
├── metrics-DD-HH-MM.txt          # Метрики для каждого запуска
├── objects-DD-HH-MM.json         # Список объектов
├── objects-previous.json         # Предыдущий список объектов
├── DD-HH-MM/                     # Инкрементальный бэкап
└── DD-HH-MM-deleted/             # Список удаленных объектов
    └── deleted-objects.txt

/archive/storage-YYYYMMD/
├── [содержимое бакета]
├── rclone-archive-DD-HH-MM.log   # Лог архивации
└── archive-metrics-DD-HH-MM.txt  # Метрики архивации
```

### Анализ логов

```bash
# Просмотр общего лога
tail -f /backup/storage-$(date +%Y%m%d | sed 's/.$/0/')-backup/backup.log

# Поиск ошибок
grep ERROR /backup/*/backup.log

# Статистика по backup
grep "Copied objects" /backup/*/backup.log | tail -10

# Статистика по archive
grep "Archive completed" /backup/*/backup.log
```

## Диагностика проблем

### Общие проблемы

1. **Скрипт не запускается**
   ```bash
   # Проверка lock файла
   ls -la /opt/s3-backup/*.lock
   
   # Проверка процессов
   ps aux | grep s3-backup
   ```

2. **Ошибки rclone**
   ```bash
   # Проверка конфигурации
   rclone config show s3
   
   # Тестовое подключение
   rclone lsd s3: -v
   ```

3. **Нехватка места**
   ```bash
   # Проверка свободного места
   df -h /backup /archive
   
   # Очистка старых логов
   find /backup -name "rclone-*.log" -mtime +30 -delete
   ```

4. **Проблемы с производительностью**
   ```bash
   # Мониторинг нагрузки
   iostat -x 1
   
   # Настройка rclone параметров в скриптах
   # Уменьшить --transfers и --checkers
   ```

### Восстановление после сбоя

1. **Очистка lock файлов**
   ```bash
   rm -f /opt/s3-backup/*.lock
   ```

2. **Восстановление timestamp файла**
   ```bash
   # Если потерян timestamp, установить время последнего успешного бэкапа
   echo "2024-01-01 12:00:00" > /opt/s3-backup/last_backup_time
   ```

3. **Пересоздание списка объектов**
   ```bash
   # Удалить предыдущий список для полного сканирования
   rm -f /backup/*/objects-previous.json
   ```

## Рекомендации по эксплуатации

### Безопасность
- Установить корректные права доступа на каталоги и файлы
- Использовать отдельные S3 ключи с минимальными правами
- Регулярно ротировать ключи доступа

### Производительность
- Мониторить загрузку сети и дисковой подсистемы
- Настраивать параметры rclone под конкретную инфраструктуру
- Использовать SSD для временных файлов

### Надежность
- Регулярно проверять метрики и логи
- Настроить алерты на основе метрик Prometheus
- Периодически тестировать восстановление данных

### Масштабирование
- При росте объемов данных увеличить параметры rclone
- Рассмотреть распараллеливание на несколько инстансов
- Использовать dedicated сети для трафика бэкапов