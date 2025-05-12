"""
Экспортер метрик Prometheus для RADOSGW.

Этот модуль собирает метрики из API RADOSGW, кэширует их асинхронно
и предоставляет через HTTP/HTTPS-эндпоинт для сбора Prometheus.
"""

import argparse
import logging
import time
import traceback
from collections import Counter, defaultdict
from http.server import HTTPServer
from threading import Lock, Event, Thread
from typing import DefaultDict, Dict, List, Optional, Tuple
import requests
from requests.exceptions import RequestException
from prometheus_client import GaugeMetricFamily, CounterMetricFamily
from prometheus_client.exposition import generate_latest


class CollectorMetrics:
    """
    Класс для управления метриками о производительности сборщика.
    Хранит и обновляет метрики, такие как время сбора, ошибки и время ожидания.
    """

    def __init__(self) -> None:
        """
        Инициализация объекта CollectorMetrics.
        Создает словарь для хранения метрик и инициализирует их.
        """
        # Словарь для хранения метрик (ключ - имя метрики, значение - объект метрики)
        self._metrics: Dict[str, GaugeMetricFamily | CounterMetricFamily] = {}
        self._init_static_metrics()  # Инициализация статических метрик
        self._init_dynamic_metrics()  # Инициализация динамических метрик

    def _init_static_metrics(self) -> None:
        """
        Инициализация статических метрик, которые не изменяются во время работы.
        Например, информация о версии и режиме работы сборщика.
        """
        # Метрика с информацией о сборщике (версия и режим)
        info = GaugeMetricFamily(
            "radosgw_collector_info",
            "Information about the RADOSGW collector",
            labels=["version", "mode"],
        )
        info.add_metric(["1.0", "async"], 1)  # Устанавливаем значение 1 для версии 1.0 в асинхронном режиме
        self._metrics["info"] = info

    def _init_dynamic_metrics(self) -> None:
        """
        Инициализация динамических метрик, которые обновляются при каждом сборе.
        Например, время сбора, количество ошибок и время ожидания.
        """
        self._metrics.update(
            {
                "scrape_duration": GaugeMetricFamily(
                    "radosgw_collector_scrape_duration_seconds",
                    "Time taken to scrape metrics from RADOSGW",
                ),
                "scrape_errors": CounterMetricFamily(
                    "radosgw_collector_scrape_errors_total",
                    "Total number of scrape errors",
                    labels=["error_type"],
                ),
                "wait_time": GaugeMetricFamily(
                    "radosgw_collector_metrics_wait_time_seconds",
                    "Time spent waiting for metrics to be available",
                ),
            }
        )

    def update_success(self, duration: float) -> None:
        """
        Обновление метрик после успешного сбора данных.

        Args:
            duration: Время, затраченное на сбор метрик, в секундах.
        """
        self._init_dynamic_metrics()  # Переинициализация динамических метрик
        self._metrics["scrape_duration"].add_metric([], duration)  # Установка времени сбора

    def update_failure(self, duration: float, error_type: str) -> None:
        """
        Обновление метрик после ошибки при сборе данных.

        Args:
            duration: Время, затраченное на неудачный сбор, в секундах.
            error_type: Тип ошибки (например, 'request_error').
        """
        self._init_dynamic_metrics()  # Переинициализация динамических метрик
        self._metrics["scrape_errors"].add_metric([error_type], 1)  # Увеличение счетчика ошибок
        self._metrics["scrape_duration"].add_metric([], duration)  # Установка времени сбора

    def update_wait_time(self, wait_time: float) -> None:
        """
        Обновление метрик для времени ожидания.

        Args:
            wait_time: Время ожидания в секундах.
        """
        self._init_dynamic_metrics()  # Переинициализация динамических метрик
        self._metrics["wait_time"].add_metric([], wait_time)  # Установка времени ожидания

    def collect(self) -> List[GaugeMetricFamily | CounterMetricFamily]:
        """
        Сбор всех метрик для Prometheus.

        Returns:
            Список объектов метрик.
        """
        return list(self._metrics.values())  # Возвращаем все метрики в виде списка


class RADOSGWCollector:
    """
    Класс для сбора метрик из API RADOSGW.
    Выполняет HTTP-запросы, парсит ответы и преобразует их в метрики Prometheus.
    """

    def __init__(
        self,
        host: str,
        admin_entry: str,
        access_key: str,
        secret_key: str,
        store: str,
        insecure: bool,
        timeout: int,
        tag_list: str,
    ) -> None:
        """
        Инициализация сборщика метрик RADOSGW.

        Args:
            host: URL хоста RADOSGW API (например, 'http://localhost:8080').
            admin_entry: Путь к административному API (например, 'admin').
            access_key: Ключ доступа S3.
            secret_key: Секретный ключ S3.
            store: Идентификатор хранилища.
            insecure: Отключение проверки SSL (True - отключить).
            timeout: Тайм-аут HTTP-запросов в секундах.
            tag_list: Список тегов, разделенных запятыми.

        Raises:
            ValueError: Если access_key или secret_key пусты.
        """
        if not access_key or not secret_key:
            raise ValueError("Ключ доступа и секретный ключ не должны быть пустыми")
        # Сохраняем параметры для последующего использования
        self.host = host
        self.access_key = access_key
        self.secret_key = secret_key
        self.store = store
        self.insecure = insecure
        self.timeout = timeout
        self.tag_list = tag_list
        # Формируем базовый URL для API
        self.url = f"{host}/{admin_entry}"
        if insecure:
            logging.warning("Включено небезопасное SSL-соединение. Используйте с осторожностью.")
        # Создаем HTTP-сессию для запросов
        self.session = self._session()
        # Словарь для хранения метрик Prometheus
        self._prometheus_metrics: Dict[str, GaugeMetricFamily | CounterMetricFamily] = {}
        # Словарь для хранения данных об использовании (пользователи, бакеты, категории)
        self.usage_dict: DefaultDict[str, Dict[str, Dict[str, Counter]]] = defaultdict(dict)
        self._setup_empty_prometheus_metrics()  # Инициализация пустых метрик

    def _session(self) -> requests.Session:
        """
        Создание HTTP-сессии для запросов к RADOSGW API.

        Returns:
            Настроенный объект requests.Session с аутентификацией.
        """
        session = requests.Session()
        session.auth = (self.access_key, self.secret_key)  # Устанавливаем S3-аутентификацию
        return session

    def _setup_empty_prometheus_metrics(self) -> None:
        """
        Инициализация пустых метрик Prometheus.
        Создает метрики с нужными метками для последующего заполнения.
        """
        # Метки для метрик бакетов (bucket, owner, category, store + дополнительные теги)
        b_labels = ["bucket", "owner", "category", "store"]
        if self.tag_list:
            b_labels += self.tag_list.split(",")
        # Метки для метрик пользователей (user, store + дополнительные теги)
        u_labels = ["user", "store"]
        if self.tag_list:
            u_labels += self.tag_list.split(",")

        # Создаем словарь метрик с их описаниями и метками
        self._prometheus_metrics = {
            "ops": CounterMetricFamily(
                "radosgw_ops",
                "Number of operations",
                labels=b_labels,
            ),
            "bytes_sent": CounterMetricFamily(
                "radosgw_bytes_sent",
                "Bytes sent by RADOSGW",
                labels=b_labels,
            ),
            "bucket_usage_bytes": GaugeMetricFamily(
                "radosgw_bucket_usage_bytes",
                "Bytes used by buckets",
                labels=b_labels,
            ),
            "user_quota_enabled": GaugeMetricFamily(
                "radosgw_user_quota_enabled",
                "Whether user quota is enabled",
                labels=u_labels,
            ),
            "user_quota_max_size": GaugeMetricFamily(
                "radosgw_user_quota_max_size_bytes",
                "Maximum size allowed by user quota",
                labels=u_labels,
            ),
        }

    def _request_data(self, query: str, args: str) -> Optional[Dict]:
        """
        Запрос данных из API RADOSGW.

        Args:
            query: Тип запроса API (например, 'usage', 'bucket').
            args: Аргументы запроса.

        Returns:
            Словарь с данными JSON или None в случае ошибки.
        """
        try:
            # Выполняем GET-запрос к API с указанными параметрами
            response = self.session.get(
                f"{self.url}/{query}",
                params={"format": "json", "args": args},
                verify=not self.insecure,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                data = response.json()
                # Проверяем, что ответ - словарь
                if not isinstance(data, dict):
                    logging.error(f"Неверный тип ответа JSON: {type(data)}")
                    return None
                return data
            logging.warning(f"Ошибка запроса API, статус: {response.status_code}")
            return None
        except (RequestException, json.JSONDecodeError) as e:
            logging.error(f"Ошибка при запросе данных: {e}")
            return None

    def _get_usage(self, entry: Dict) -> None:
        """
        Обработка данных об использовании из ответа API.

        Args:
            entry: Запись данных об использовании.
        """
        # Проверяем, что входные данные - словарь
        if not isinstance(entry, dict):
            logging.warning(f"Неверный тип записи: {type(entry)}")
            return
        # Получаем владельца бакета (owner или user)
        bucket_owner = entry.get("owner") or entry.get("user")
        if not bucket_owner:
            return
        # Обрабатываем данные для каждого бакета
        for bucket in entry.get("buckets", []):
            bucket_name = bucket.get("bucket")
            if not bucket_name:
                continue
            # Обрабатываем категории операций
            for category in bucket.get("categories", []):
                cat_name = category.get("category")
                if not cat_name:
                    continue
                ops = category.get("ops", 0)
                bytes_sent = category.get("bytes_sent", 0)
                # Сохраняем данные в usage_dict
                if bucket_name not in self.usage_dict[bucket_owner]:
                    self.usage_dict[bucket_owner][bucket_name] = defaultdict(Counter)
                self.usage_dict[bucket_owner][bucket_name][cat_name].update(
                    {"ops": ops, "bytes_sent": bytes_sent}
                )

    def _get_bucket_usage(self, bucket: Dict) -> None:
        """
        Обработка данных об использовании бакетов.

        Args:
            bucket: Данные о бакете.
        """
        # Проверяем, что входные данные - словарь
        if not isinstance(bucket, dict):
            logging.warning(f"Неверный тип данных бакета: {type(bucket)}")
            return
        bucket_name = bucket.get("bucket")
        owner = bucket.get("owner")
        if not bucket_name or not owner:
            return
        # Получаем данные об использовании бакета
        usage = bucket.get("usage", {}).get("rgw.main", {})
        size = usage.get("size_actual", 0)
        # Формируем метки для метрики
        labels = [bucket_name, owner, "none", self.store]
        if self.tag_list:
            labels += [""] * len(self.tag_list.split(","))
        # Добавляем метрику использования бакета
        self._prometheus_metrics["bucket_usage_bytes"].add_metric(labels, size)

    def _get_user_info(self, user: Dict) -> None:
        """
        Обработка данных о пользователях.

        Args:
            user: Данные о пользователе.
        """
        # Проверяем, что входные данные - словарь
        if not isinstance(user, dict):
            logging.warning(f"Неверный тип данных пользователя: {type(user)}")
            return
        user_id = user.get("user_id")
        if not user_id:
            return
        # Получаем данные о квоте пользователя
        quota = user.get("quota", {})
        # Формируем метки для метрик
        labels = [user_id, self.store]
        if self.tag_list:
            labels += [""] * len(self.tag_list.split(","))
        # Добавляем метрики о квоте
        self._prometheus_metrics["user_quota_enabled"].add_metric(
            labels, 1 if quota.get("enabled") else 0
        )
        self._prometheus_metrics["user_quota_max_size"].add_metric(
            labels, quota.get("max_size", 0)
        )

    def _get_rgw_users(self) -> List[Dict]:
        """
        Получение списка пользователей RGW.

        Returns:
            Список словарей с данными о пользователях.
        """
        data = self._request_data("metadata/user", "")
        return data.get("data", []) if data else []

    def _update_usage_metrics(self) -> None:
        """
        Обновление метрик использования из usage_dict.
        """
        # Перебираем данные об использовании для каждого владельца
        for owner, buckets in self.usage_dict.items():
            for bucket, categories in buckets.items():
                for category, counters in categories.items():
                    # Формируем метки для метрик
                    labels = [bucket, owner, category, self.store]
                    if self.tag_list:
                        labels += [""] * len(self.tag_list.split(","))
                    # Добавляем метрики операций и отправленных байтов
                    self._prometheus_metrics["ops"].add_metric(labels, counters["ops"])
                    self._prometheus_metrics["bytes_sent"].add_metric(
                        labels, counters["bytes_sent"]
                    )

    def collect(self) -> List[GaugeMetricFamily | CounterMetricFamily]:
        """
        Сбор всех метрик из RADOSGW.

        Returns:
            Список объектов метрик Prometheus.
        """
        self._setup_empty_prometheus_metrics()  # Переинициализация метрик
        # Запрашиваем данные об использовании, бакетах и пользователях
        rgw_usage = self._request_data("usage", "show-summary=False")
        rgw_bucket = self._request_data("bucket", "stats=True")
        rgw_users = self._get_rgw_users()

        # Обрабатываем полученные данные
        if rgw_usage:
            for entry in rgw_usage.get("entries", []):
                self._get_usage(entry)
        if rgw_bucket:
            for bucket in rgw_bucket:
                self._get_bucket_usage(bucket)
        for user in rgw_users:
            self._get_user_info(user)
        self._update_usage_metrics()

        return list(self._prometheus_metrics.values())  # Возвращаем собранные метрики


class AsyncMetricsUpdater:
    """
    Класс для асинхронного обновления и кэширования метрик.
    Периодически собирает метрики и сохраняет их в кэш для быстрого доступа.
    """

    def __init__(self, collector: RADOSGWCollector, interval: int) -> None:
        """
        Инициализация обновителя метрик.

        Args:
            collector: Экземпляр RADOSGWCollector для сбора метрик.
            interval: Интервал обновления метрик в секундах.

        Raises:
            ValueError: Если интервал меньше 10 секунд.
        """
        # Проверяем минимальный интервал обновления
        if interval < 10:
            logging.warning("Интервал слишком мал. Используется минимум 10 секунд.")
            interval = 10
        self.collector = collector  # Сборщик метрик
        self.interval = interval  # Интервал обновления
        self._lock = Lock()  # Блокировка для синхронизации доступа к кэшу
        # Кэш метрик, доступный для HTTP-запросов
        self._metrics_cache: List[GaugeMetricFamily | CounterMetricFamily] = []
        # Метрики о производительности сборщика
        self._collector_metrics = CollectorMetrics()
        self._stop_event = Event()  # Событие для остановки обновления
        # Событие, указывающее, выполняется ли обновление
        self._update_in_progress = Event()
        self._update_in_progress.set()  # Изначально обновление не выполняется
        self._thread: Optional[Thread] = None  # Поток для обновления метрик

    def start(self) -> None:
        """
        Запуск фонового потока для обновления метрик.
        Создает и запускает поток, который периодически обновляет метрики.
        """
        self._thread = Thread(target=self._update_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """
        Остановка фонового потока обновления.
        Устанавливает событие остановки и ожидает завершения потока.
        """
        self._stop_event.set()
        if self._thread:
            self._thread.join()

    def _update_loop(self) -> None:
        """
        Цикл периодического обновления метрик.
        Запрашивает метрики у сборщика, кэширует их и обновляет метрики производительности.
        """
        while not self._stop_event.is_set():
            start_time = time.time()  # Время начала сбора
            self._update_in_progress.clear()  # Указываем, что обновление началось
            try:
                # Собираем метрики приложения
                app_metrics = self.collector.collect()
                duration = time.time() - start_time  # Время сбора
                # Обновляем метрики производительности
                self._collector_metrics.update_success(duration)
                # Кэшируем метрики с использованием блокировки
                with self._lock:
                    self._metrics_cache = app_metrics + self._collector_metrics.collect()
            except RequestException as e:
                logging.error(f"Ошибка запроса при обновлении метрик: {e}")
                self._collector_metrics.update_failure(time.time() - start_time, "request_error")
            except json.JSONDecodeError as e:
                logging.error(f"Ошибка декодирования JSON при обновлении метрик: {e}")
                self._collector_metrics.update_failure(time.time() - start_time, "json_error")
            except (ValueError, KeyError, TypeError) as e:
                # Логируем ошибки обработки данных с трассировкой стека
                logging.error(f"Ошибка обработки данных при обновлении метрик: {e}\n{traceback.format_exc()}")
                self._collector_metrics.update_failure(time.time() - start_time, "data_error")
            finally:
                # Указываем, что обновление завершено
                self._update_in_progress.set()
            time.sleep(self.interval)  # Ожидаем до следующего обновления

    def get_metrics(self) -> List[GaugeMetricFamily | CounterMetricFamily]:
        """
        Получение кэшированных метрик.

        Returns:
            Список кэшированных объектов метрик.
        """
        wait_start = time.time()  # Время начала ожидания
        # Ожидаем завершения текущего обновления
        self._update_in_progress.wait()
        wait_time = time.time() - wait_start  # Время ожидания
        if wait_time > 0:
            self._collector_metrics.update_wait_time(wait_time)
        # Возвращаем копию кэша метрик
        with self._lock:
            return self._metrics_cache.copy()


class MetricsHandler(BaseHTTPRequestHandler):
    """
    Класс для обработки HTTP-запросов к экспортеру.
    Обрабатывает запросы /metrics и возвращает метрики в формате Prometheus.
    """

    def __init__(self, metrics_updater: AsyncMetricsUpdater, *args, **kwargs) -> None:
        """
        Инициализация обработчика HTTP-запросов.

        Args:
            metrics_updater: Экземпляр AsyncMetricsUpdater для получения метрик.
            args: Позиционные аргументы для BaseHTTPRequestHandler.
            kwargs: Именованные аргументы для BaseHTTPRequestHandler.
        """
        self.metrics_updater = metrics_updater  # Обновитель метрик
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        """
        Обработка GET-запросов.
        Возвращает метрики для пути /metrics или ошибку для неверного пути.
        """
        if self.path == "/metrics":
            self.send_response(200)  # Успешный ответ
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            # Получаем метрики и отправляем их в формате Prometheus
            metrics = self.metrics_updater.get_metrics()
            self.wfile.write(generate_latest(metrics))
        else:
            self.send_response(404)  # Ошибка для неверного пути
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Неверный эндпоинт\n")


def parse_args() -> argparse.Namespace:
    """
    Парсинг аргументов командной строки.

    Returns:
        Объект с разобранными аргументами.
    """
    parser = argparse.ArgumentParser(description="Экспортер Prometheus для RADOSGW")
    parser.add_argument("--host", default="http://localhost:8080", help="Хост RADOSGW")
    parser.add_argument("--access-key", required=True, help="Ключ доступа S3")
    parser.add_argument("--secret-key", required=True, help="Секретный ключ S3")
    parser.add_argument("--store", default="default", help="Идентификатор хранилища")
    parser.add_argument("--insecure", action="store_true", help="Отключить проверку SSL")
    parser.add_argument("--timeout", type=int, default=5, help="Тайм-аут HTTP-запросов")
    parser.add_argument("--interval", type=int, default=30, help="Интервал обновления метрик")
    parser.add_argument("--port", type=int, default=8000, help="Порт HTTP-сервера")
    parser.add_argument("--tls-cert", help="Файл сертификата TLS")
    parser.add_argument("--tls-key", help="Файл ключа TLS")
    parser.add_argument("--tag-list", default="", help="Список тегов, разделенных запятыми")
    parser.add_argument(
        "--bindip", default="0.0.0.0", help="IP-адрес для привязки сервера (например, 0.0.0.0 или 127.0.0.1)"
    )
    return parser.parse_args()


def run_http_server(
    metrics_updater: AsyncMetricsUpdater,
    bindip: str,
    port: int,
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
) -> None:
    """
    Запуск HTTP/HTTPS-сервера для экспорта метрик.

    Args:
        metrics_updater: Экземпляр AsyncMetricsUpdater для получения метрик.
        bindip: IP-адрес для привязки сервера.
        port: Порт сервера.
        certfile: Путь к файлу сертификата TLS.
        keyfile: Путь к файлу ключа TLS.
    """
    import ssl

    # Внутренний класс обработчика для передачи metrics_updater
    class Handler(MetricsHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(metrics_updater, *args, **kwargs)

    # Создаем сервер с указанным IP и портом
    server = HTTPServer((bindip, port), Handler)
    if certfile and keyfile:
        # Настраиваем TLS, если указаны сертификаты
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    else:
        logging.warning("Запуск HTTP-сервера без SSL. Рекомендуется использовать TLS.")
    server.serve_forever()  # Запускаем сервер


def main() -> None:
    """
    Главная функция для запуска экспортера.
    Инициализирует сборщик, обновитель и сервер.
    """
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    args = parse_args()  # Парсим аргументы командной строки
    # Создаем сборщик метрик
    collector = RADOSGWCollector(
        args.host,
        "admin",
        args.access_key,
        args.secret_key,
        args.store,
        args.insecure,
        args.timeout,
        args.tag_list,
    )
    # Создаем обновитель метрик
    metrics_updater = AsyncMetricsUpdater(collector, args.interval)
    metrics_updater.start()  # Запускаем обновление метрик
    try:
        # Запускаем HTTP/HTTPS-сервер
        run_http_server(metrics_updater, args.bindip, args.port, args.tls_cert, args.tls_key)
    except KeyboardInterrupt:
        metrics_updater.stop()  # Останавливаем обновление при прерывании


if __name__ == "__main__":
    main()

