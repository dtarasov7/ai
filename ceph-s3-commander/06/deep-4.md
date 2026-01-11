# S3 Commander - Детальная архитектурная документация

## Комплексные диаграммы архитектуры

### 1. Полная диаграмма последовательности запуска

```plantuml
@startuml
title Последовательность запуска S3 Commander

actor Пользователь
participant "s3-commander.py" as Main
participant "S3Config" as Config
participant "DualPaneApp" as App
participant "urwid.MainLoop" as Urwid
participant "PanelWidget\n(левая)" as LeftPanel
participant "PanelWidget\n(правая)" as RightPanel
participant "S3Manager" as S3Mgr
participant "FileSystemBrowser" as FSBrowser
participant "boto3.client" as Boto3

Пользователь -> Main: Запуск скрипта
Main -> Config: Создание S3Config()
activate Config
Config -> Config: load_config()
Config -> Config: Проверка s3_config.json
Config -> Config: create_default_config() если нужно
Config --> Main: Возвращает объект конфига
deactivate Config

Main -> App: Создание DualPaneApp(config)
activate App
App -> LeftPanel: Создание PanelWidget()
activate LeftPanel
LeftPanel -> LeftPanel: Инициализация
LeftPanel -> LeftPanel: mode = 'root_menu'
LeftPanel -> LeftPanel: walker = SimpleFocusListWalker()
LeftPanel -> LeftPanel: Создание интерфейса
LeftPanel --> App: Возврат панели
deactivate LeftPanel

App -> RightPanel: Создание PanelWidget()
activate RightPanel
RightPanel -> RightPanel: Инициализация
RightPanel -> RightPanel: mode = 'root_menu'
RightPanel -> RightPanel: Создание интерфейса
RightPanel --> App: Возврат панели
deactivate RightPanel

App -> App: Создание Frame с двумя панелями
App -> App: Настройка горячих клавиш
App -> App: Создание палитры цветов

App -> Urwid: Создание MainLoop()
activate Urwid
Urwid -> Urwid: Инициализация экрана
Urwid -> Urwid: Настройка кодировки UTF-8
Urwid -> Urwid: Регистрация обработчиков

Пользователь -> Urwid: Отображение интерфейса
Urwid -> App: Вызов App.run()
App -> Urwid: Запуск event loop
Urwid -> LeftPanel: Первоначальная отрисовка
LeftPanel -> LeftPanel: refresh()
LeftPanel -> LeftPanel: _refresh_root_menu()
LeftPanel --> Urwid: Отображение корневого меню

Urwid -> RightPanel: Первоначальная отрисовка
RightPanel -> RightPanel: refresh()
RightPanel -> RightPanel: _refresh_root_menu()
RightPanel --> Urwid: Отображение корневого меню

@enduml
```

### 2. Полная архитектурная диаграмма классов

```plantuml
@startuml
title Полная архитектура классов S3 Commander

package "Основные компоненты" {
  class DualPaneApp {
    - left_panel: PanelWidget
    - right_panel: PanelWidget
    - s3_config: S3Config
    - loop: urwid.MainLoop
    - overwrite_all: bool
    - version_all: bool
    - skip_all: bool
    + run()
    + handle_input(key)
    + get_active_panel()
    + get_inactive_panel()
    + show_dialog()
    + close_dialog()
    + show_result()
    + copy_items()
    + move_items()
    + delete_items()
    + create_directory()
    + _do_copy_with_progress()
    + _do_delete_with_progress()
    + _check_overwrite()
    + wakeup()
    - wake_up()
    - loop_wakeup_callback()
  }
  
  class PanelWidget {
    - title: str
    - panel_type: str
    - mode: str
    - s3_manager: S3Manager
    - fs_browser: FileSystemBrowser
    - current_endpoint: str
    - current_bucket: str
    - current_prefix: str
    - walker: SimpleFocusListWalker
    - listbox: ListBox
    - scrollbar: ScrollBar
    - sort_mode: str
    - sort_reverse: bool
    - loading_in_progress: bool
    + refresh()
    + on_item_activated(data)
    + view_item()
    + get_selected_items()
    + select_by_pattern()
    + invert_selection()
    + show_sort_dialog()
    + show_item_info()
    + _refresh_fs()
    + _refresh_s3()
    + _refresh_root_menu()
    + _refresh_s3_objects_lazy()
    + load_s3_objects_background()
    + _create_display_items()
    + sort_items()
    + _calculate_size()
    + view_s3_file_version()
    + show_version_select_dialog()
    + copy_version()
  }
  
  class S3Manager {
    - endpoint_name: str
    - endpoint_url: str
    - access_key: str
    - secret_key: str
    - s3_client: boto3.client
    - is_connected: bool
    - connection_error: str
    - object_cache: LRUCache
    - bucket_cache: LRUCache
    - versioning_status_cache: dict
    + list_buckets()
    + list_objects(bucket, prefix)
    + list_objects_lazy(bucket, prefix)
    + list_all_objects(bucket, prefix)
    + count_objects(bucket, prefix)
    + object_exists(bucket, key)
    + list_object_versions(bucket, key)
    + download_object(bucket, key, path)
    + upload_file(path, bucket, key)
    + copy_object(src_bucket, src_key, dst_bucket, dst_key)
    + delete_object(bucket, key)
    + delete_old_versions(bucket, key)
    + enable_versioning(bucket)
    + disable_versioning(bucket)
    + get_versioning_status(bucket)
    + get_versioning_status_cached(bucket)
    + invalidate_cache()
    + mark_s3_for_refresh()
  }
  
  class FileSystemBrowser {
    - current_path: str
    + list_directory()
    + list_all_files(path)
    + file_exists(file_path)
    + create_directory(dir_name)
    + format_size(size)
  }
}

package "Конфигурация и кеши" {
  class S3Config {
    - config_file: str
    - endpoints: list
    + load_config()
    + save_config()
    + create_default_config()
    + get_endpoints()
    + get_endpoint(name)
  }
  
  class LRUCache {
    - cache: OrderedDict
    - maxsize: int
    + get(key)
    + put(key, value)
    + invalidate(pattern)
  }
}

package "UI Компоненты" {
  class ScrollBar {
    - scrollbar_width: int
    + render(size, focus)
    + selectable()
    + keypress(size, key)
    + mouse_event(size, event, button, col, row, focus)
    - _create_scrollbar(height, thumb_top, thumb_height)
  }
  
  class SelectableText {
    - data: dict
    - panel: PanelWidget
    - selected: bool
    + selectable()
    + keypress(size, key)
  }
  
  abstract class DialogBase {
    # callback: function
    + keypress(size, key)
  }
  
  class InputDialog {
    - edit: urwid.Edit
    + on_ok(button)
    + on_cancel(button)
  }
  
  class ConfirmDialog {
    + on_yes(button)
    + on_no(button)
  }
  
  class ProgressDialog {
    - title_text: urwid.Text
    - progress_text: urwid.Text
    - file_text: urwid.Text
    - stats_text: urwid.Text
    - bytes_text: urwid.Text
    - cancelled: bool
    + update(current_file, file_size)
    + set_total(total_files, total_bytes)
    + add_success()
    + add_failure()
    + get_speed_str()
    + on_cancel(button)
  }
  
  class OverwriteDialog {
    - show_version_options: bool
    + on_choice(choice)
  }
  
  class SortDialog {
    - radio_group: list
    - reverse_checkbox: urwid.CheckBox
    + on_ok(button)
    + on_cancel(button)
  }
  
  class CopyMoveDialog {
    - dest_edit: urwid.Edit
    + on_ok(button)
    + on_cancel(button)
  }
  
  class VersionSelectDialog {
    - versions: list
    - file_data: dict
    - radio_group: list
    - listbox: urwid.ListBox
  }
  
  class FileViewerDialog {
    + on_close(button)
  }
  
  class FileInfoDialog {
    + on_ok(button)
  }
}

package "Вспомогательные утилиты" {
  class check_s3_endpoint_connectivity {
    + __call__(endpoint_url, timeout)
  }
  
  class get_focus_button {
    + __call__(widget)
  }
  
  class is_binary_file {
    + __call__(file_path)
  }
  
  class format_size {
    + __call__(size)
  }
}

' Связи между основными классами
DualPaneApp *--> PanelWidget : содержит 2
PanelWidget o--> S3Manager : использует
PanelWidget o--> FileSystemBrowser : использует
DualPaneApp o--> S3Config : использует
S3Manager o--> LRUCache : содержит 2
S3Manager ..> check_s3_endpoint_connectivity : вызывает
DualPaneApp ..> get_focus_button : вызывает

' UI связи
PanelWidget *--> SelectableText : содержит
PanelWidget *--> ScrollBar : содержит
DialogBase <|-- InputDialog
DialogBase <|-- ConfirmDialog
DialogBase <|-- ProgressDialog
DialogBase <|-- OverwriteDialog
DialogBase <|-- SortDialog
DialogBase <|-- CopyMoveDialog
DialogBase <|-- VersionSelectDialog
DialogBase <|-- FileViewerDialog
DialogBase <|-- FileInfoDialog

' Вспомогательные связи
FileSystemBrowser ..> format_size : использует
FileSystemBrowser ..> is_binary_file : использует

' Внешние зависимости
S3Manager ..> boto3.client : использует
DualPaneApp ..> urwid.MainLoop : использует

@enduml
```

### 3. Диаграмма состояний панели

```plantuml
@startuml
title Диаграмма состояний PanelWidget

[*] --> root_menu : Инициализация

state root_menu {
  [*] --> Отображение_меню
  Отображение_меню --> fs_mode : Выбор "FS Local"
  Отображение_меню --> s3_mode : Выбор "[S3] Endpoint"
}

state fs_mode {
  [*] --> Навигация_ФС
  Навигация_ФС : Может переходить по директориям\nПоддерживает сортировку\nВыделение файлов
  Навигация_ФС --> Навигация_ФС : Enter на папке
  Навигация_ФС --> Навигация_ФС : Enter на ".."
  Навигация_ФС --> root_menu : Enter на "Back to root menu"
}

state s3_mode {
  [*] --> Выбор_эндпоинта
  Выбор_эндпоинта : Показывает список endpoints\nиз конфигурации
  Выбор_эндпоинта --> Выбор_бакета : Выбор endpoint
  Выбор_бакета --> Выбор_бакета : Сортировка по имени/дате\nИндикация версионирования
  Выбор_бакета --> Выбор_бакета : Enter на бакете
  Выбор_бакета --> root_menu : Enter на "Back to root menu"
  Выбор_бакета --> Просмотр_бакета : Enter на бакете
  Просмотр_бакета : Ленивая загрузка объектов\nОтображение версий файлов\nСортировка по разным критериям
  Просмотр_бакета --> Выбор_бакета : Enter на "Back to buckets"
  Просмотр_бакета --> Просмотр_бакета : Enter на папке
  Просмотр_бакета --> Просмотр_бакета : Enter на ".."
  Просмотр_бакета --> Диалог_версий : F3 на файле с версиями
}

state Диалог_версий {
  [*] --> Просмотр_списка_версий
  Просмотр_списка_версий --> Просмотр_файла : F3 на версии
  Просмотр_списка_версий --> Копирование_версии : F5 на версии
  Просмотр_списка_версий --> Перемещение_версии : F6 на версии
  Просмотр_списка_версий --> Удаление_версии : F8 на версии
  Просмотр_списка_версий --> Просмотр_бакета : ESC
}

root_menu --> [*] : Закрытие приложения

@enduml
```

### 4. Диаграмма последовательности операций копирования

```plantuml
@startuml
title Детальная последовательность операций копирования

actor Пользователь
participant "DualPaneApp" as App
participant "PanelWidget\n(источник)" as SourcePanel
participant "PanelWidget\n(цель)" as DestPanel
participant "S3Manager" as S3Mgr
participant "FileSystemBrowser" as FSBrowser
participant "ProgressDialog" as Progress
participant "OverwriteDialog" as Overwrite
participant "threading.Thread" as Thread
participant "boto3.client" as Boto3

group Инициализация копирования
  Пользователь -> App: Нажимает F5 (Copy)
  App -> App: get_active_panel() → SourcePanel
  App -> App: get_inactive_panel() → DestPanel
  App -> SourcePanel: get_selected_items()
  SourcePanel -> SourcePanel: Анализ выделенных элементов
  SourcePanel --> App: Возврат selected_items
  App -> App: analyze_items(selected_items, SourcePanel)
  App -> App: _show_copy_dialog()
  App -> App: show_dialog(CopyMoveDialog)
  Пользователь -> App: Вводит путь назначения → OK
  App -> App: _do_copy_with_progress()
  App -> App: show_dialog(ProgressDialog)
  App -> Progress: set_total(total_files, total_bytes)
end

group Обработка элементов
  loop Для каждого analyzed элемента
    App -> Thread: Запуск copy_thread()
    activate Thread
    
    alt Тип: FS файл → S3
      Thread -> SourcePanel: fs_browser.current_path
      SourcePanel -> FSBrowser: Получение пути
      FSBrowser --> SourcePanel: current_path
      Thread -> Thread: Формирование dest_key
      
      group Проверка существования
        Thread -> DestPanel: s3_manager.object_exists()
        DestPanel -> S3Mgr: object_exists(bucket, key)
        S3Mgr -> Boto3: head_object()
        Boto3 --> S3Mgr: Результат или исключение
        S3Mgr --> DestPanel: existing_info или None
        DestPanel --> Thread: Существует? (True/False)
        
        alt Файл существует
          Thread -> App: Показ OverwriteDialog
          App -> App: show_dialog(OverwriteDialog)
          Пользователь -> Overwrite: Выбор действия
          Overwrite -> Thread: user_choice['value'] = выбор
          Thread -> Thread: Обновление флагов (overwrite_all и т.д.)
        end
      end
      
      Thread -> Progress: update(filename, size)
      Thread -> DestPanel: s3_manager.upload_file()
      DestPanel -> S3Mgr: upload_file(source_path, bucket, dest_key)
      S3Mgr -> Boto3: upload_file()
      Boto3 --> S3Mgr: Результат
      S3Mgr -> S3Mgr: invalidate_cache(bucket)
      S3Mgr -> S3Mgr: mark_s3_for_refresh()
      S3Mgr --> DestPanel: True/False
      DestPanel --> Thread: Результат операции
      
      Thread -> Progress: add_success() или add_failure()
      
    else Тип: S3 файл → FS
      Thread -> SourcePanel: s3_manager.download_object()
      SourcePanel -> S3Mgr: download_object(bucket, key, dest_path)
      S3Mgr -> Boto3: download_file()
      Boto3 --> S3Mgr: Результат
      S3Mgr --> SourcePanel: True/False
      SourcePanel --> Thread: Результат операции
      
    else Тип: S3 → S3
      Thread -> SourcePanel: s3_manager.copy_object()
      SourcePanel -> S3Mgr: copy_object(src_bucket, src_key, dst_bucket, dst_key)
      S3Mgr -> Boto3: copy_object()
      Boto3 --> S3Mgr: Результат
      S3Mgr -> S3Mgr: invalidate_cache(dst_bucket)
      S3Mgr -> S3Mgr: mark_s3_for_refresh()
      S3Mgr --> SourcePanel: True/False
      SourcePanel --> Thread: Результат операции
    end
    
    Thread --> App: Возврат через event loop
    deactivate Thread
  end
end

group Завершение операции
  Thread -> App: Завершение всех операций
  App -> Progress: Закрытие
  App -> App: close_dialog()
  App -> DestPanel: refresh() для обновления вида
  App -> SourcePanel: refresh() если нужно
  App -> App: show_result() со статистикой
end

@enduml
```

### 5. Диаграмма внутренней структуры данных

```plantuml
@startuml
title Внутренняя структура данных и кеширование

package "Структуры данных PanelWidget" {
  class PanelWidget {
    - walker: SimpleFocusListWalker
    - items_data: List[Dict]
    - sort_mode: str
    - sort_reverse: bool
  }
  
  class "Walker Item" as WalkerItem {
    + widget: SelectableText
    + data: Dict
    + selected: bool
  }
  
  class "Item Data Structure" as ItemData {
    + type: str ('fs_file', 'fs_dir', 's3_file', 's3_dir', 'bucket', 'endpoint')
    + name: str
    + key: str (для S3)
    + size: int
    + mtime: datetime
    + version_count: int (для S3)
    + versioning_enabled: bool (для S3)
    + can_select: bool
    + path: str (для FS)
  }
}

package "Кеши S3Manager" {
  class LRUCache {
    - cache: OrderedDict
    + get(key)
    + put(key, value)
    + invalidate(pattern)
  }
  
  class "Cache Keys" as CacheKey {
    + count:{bucket}:{prefix}
    + list:{bucket}:{prefix}
    + objects:{bucket}:{prefix}
  }
  
  class "Cache Values" as CacheValue {
    + Для count: (total_objects, total_size)
    + Для list: (folders, files)
    + Для objects: List[ObjectDict]
  }
  
  class S3Manager {
    - object_cache: LRUCache (maxsize=100)
    - bucket_cache: LRUCache (maxsize=10)
    - versioning_status_cache: Dict[str, str]
  }
}

package "Конфигурационные данные" {
  class S3Config {
    - endpoints: List[EndpointConfig]
  }
  
  class "Endpoint Config" as EndpointConfig {
    + name: str
    + url: str
    + access_key: str
    + secret_key: str
  }
}

package "Временные данные операций" {
  class DualPaneApp {
    - overwrite_all: bool
    - version_all: bool
    - skip_all: bool
  }
  
  class "Progress Data" as ProgressData {
    + total_files: int
    + processed_files: int
    + total_bytes: int
    + processed_bytes: int
    + success_count: int
    + fail_count: int
    + start_time: float
  }
}

' Связи
PanelWidget "1" *-- "*" WalkerItem : содержит
WalkerItem "1" *-- "1" ItemData : ссылается

S3Manager "1" *-- "1" LRUCache : object_cache
S3Manager "1" *-- "1" LRUCache : bucket_cache
S3Manager "1" *-- "1" Dict : versioning_status_cache

LRUCache "1" *-- "*" CacheKey : индексирует
CacheKey "1" *-- "1" CacheValue : ссылается

S3Config "1" *-- "*" EndpointConfig : содержит

DualPaneApp "1" *-- "1" ProgressData : создает при операциях

' Потоки данных
ItemData ..> CacheValue : может быть закешировано
EndpointConfig ..> S3Manager : используется для подключения
ProgressData ..> ProgressDialog : отображается

@enduml
```

### 6. Диаграмма потока данных для ленивой загрузки

```plantuml
@startuml
title Поток данных при ленивой загрузке S3 объектов

participant "UI Thread" as UI
participant "PanelWidget" as Panel
participant "Background Thread" as BGThread
participant "S3Manager" as S3Mgr
participant "boto3 Paginator" as Paginator
participant "S3 Endpoint" as S3

group Инициализация ленивой загрузки
  UI -> Panel: refresh() при входе в бакет
  Panel -> Panel: _refresh_s3()
  Panel -> Panel: _refresh_s3_objects_lazy()
  Panel -> Panel: Добавление "[Loading...]" в walker
  Panel -> UI: Принудительная перерисовка
  Panel -> BGThread: Запуск load_s3_objects_background()
  activate BGThread
end

group Фоновая загрузка данных
  BGThread -> Panel: Обновление статуса "Loading..."
  BGThread -> S3Mgr: list_objects_lazy(bucket, prefix)
  S3Mgr -> S3Mgr: Проверка версионирования бакета
  S3Mgr -> Paginator: get_paginator('list_objects_v2' или 'list_object_versions')
  Paginator -> S3: Запрос страницы (PageSize=1000)
  S3 --> Paginator: Возврат страницы данных
  
  loop Для каждой страницы
    Paginator --> S3Mgr: (folders, files) страницы
    S3Mgr --> BGThread: yield (folders, files)
    BGThread -> BGThread: Агрегация данных
    
    group Инкрементальное обновление UI
      BGThread -> UI: set_alarm_in(0, _update_display_incremental)
      UI -> Panel: _update_display_incremental(current_folders, current_files)
      Panel -> Panel: Обновление walker (сохранение навигации)
      Panel -> UI: Перерисовка экрана
    end
    
    BGThread -> UI: set_alarm_in(0, update status)
    UI -> UI: show_result(f"Loading... {count} items")
  end
end

group Финальная обработка
  BGThread -> UI: set_alarm_in(0, _finalize_loading)
  UI -> Panel: _finalize_loading(all_folders, all_files)
  Panel -> Panel: Применение сортировки если sort_mode != 'none'
  Panel -> Panel: Перестроение walker с сортировкой
  Panel -> UI: Финальная перерисовка
  UI -> UI: show_result(f"Loaded: X folders, Y files")
  BGThread --> UI: Завершение потока
  deactivate BGThread
end

group Обработка ошибок
  alt Ошибка подключения
    S3 --> Paginator: Exception
    Paginator --> S3Mgr: Exception
    S3Mgr --> BGThread: Exception
    BGThread -> UI: set_alarm_in(0, show error)
    UI -> UI: show_result("Error loading objects: ...", is_error=True)
  end
end

@enduml
```

### 7. Диаграмма системы кеширования

```plantuml
@startuml
title Система кеширования и инвалидации

package "Уровни кеширования" {
  database "S3 Endpoint" as S3 {
    folder "Бакеты"
    folder "Объекты"
    folder "Версии"
  }
  
  component "LRU Cache\n(памяти)" as MemoryCache {
    folder "object_cache\n(maxsize=100)"
    folder "bucket_cache\n(maxsize=10)"
    folder "versioning_status_cache"
  }
  
  component "Кеш UI\n(walker)" as UICache {
    folder "Текущее состояние"
    folder "Выделенные элементы"
    folder "Сортировка"
  }
  
  component "Кеш сортировки" as SortCache {
    folder "Сортированные списки"
    folder "Индексы"
  }
}

package "Операции чтения" {
  actor "PanelWidget" as Panel
  actor "S3Manager" as S3Mgr
  
  Panel -> S3Mgr: list_objects(bucket, prefix)
  S3Mgr -> MemoryCache: get("list:{bucket}:{prefix}")
  
  alt Кеш попадание
    MemoryCache --> S3Mgr: Возврат кешированных данных
    S3Mgr --> Panel: Быстрый возврат
  else Кеш промах
    S3Mgr -> S3: list_objects_v2 API call
    S3 --> S3Mgr: Данные
    S3Mgr -> MemoryCache: put("list:{bucket}:{prefix}", data)
    S3Mgr -> MemoryCache: put("count:{bucket}:{prefix}", (count, size))
    S3Mgr --> Panel: Возврат данных
  end
  
  Panel -> UICache: Обновление walker
  Panel -> SortCache: Применение сортировки если нужно
}

package "Операции записи" {
  actor "Операции записи" as WriteOps {
    + upload_file()
    + copy_object()
    + delete_object()
    + create_bucket()
    + delete_bucket()
  }
  
  WriteOps -> S3: API вызов
  S3 --> WriteOps: Подтверждение
  
  WriteOps -> MemoryCache: invalidate(pattern)
  
  alt Изменение в бакете
    WriteOps -> MemoryCache: invalidate("{bucket}:*")
    WriteOps -> MemoryCache: Удаление versioning_status_cache[bucket]
  else Изменение в префиксе
    WriteOps -> MemoryCache: invalidate("{bucket}:{prefix}*")
  end
  
  WriteOps -> Panel: mark_s3_for_refresh()
  Panel -> UICache: Сброс состояния
  Panel -> SortCache: Сброс сортировки
}

package "Стратегии инвалидации" {
  note top of MemoryCache
    Инвалидация по паттерну:
    - bucket:* - все объекты бакета
    - bucket:prefix* - объекты префикса
    - count:bucket:* - счетчики бакета
    Полная инвалидация при:
    - Смене endpoint
    - Ошибках подключения
  end note
  
  note top of UICache
    Инвалидация при:
    - refresh() вызове
    - Смене режима панели
    - Ошибках отображения
    Ручная инвалидация:
    - После операций записи
    - При явном обновлении
  end note
}

S3 -[hidden]-> MemoryCache
MemoryCache -[hidden]-> UICache
UICache -[hidden]-> SortCache

@enduml
```

### 8. Диаграмма системы диалогов

```plantuml
@startuml
title Иерархия и взаимодействие диалоговых окон

package "Базовый класс" {
  abstract class DialogBase {
    {abstract} + keypress(size, key)
    {abstract} + render(size, focus)
    # callback: Callable
    # on_confirm()
    # on_cancel()
  }
  
  DialogBase <|-- CommonDialog
}

package "Информационные диалоги" {
  class CommonDialog {
    + buttons: List[urwid.Button]
    + title: str
    + message: str
    + keypress() : Обработка ESC/Enter
  }
  
  class FileInfoDialog {
    - info_dict: OrderedDict
    + _format_info()
    + _create_info_widgets()
  }
  
  class FileViewerDialog {
    - content: str
    - title: str
    + _wrap_text()
  }
  
  class VersionSelectDialog {
    - versions: List[Dict]
    - file_data: Dict
    - radio_group: List
    + _create_version_list()
    + _on_version_action()
  }
}

package "Диалоги ввода" {
  class InputDialog {
    - edit: urwid.Edit
    - prompt: str
    + on_ok()
    + on_cancel()
  }
  
  class CopyMoveDialog {
    - dest_edit: urwid.Edit
    - source_desc: str
    + _validate_path()
  }
  
  class SortDialog {
    - radio_group: List
    - reverse_checkbox: urwid.CheckBox
    + _get_current_sort()
    + _apply_sort()
  }
}

package "Диалоги действий" {
  class ConfirmDialog {
    - items_info: List[str]
    + _format_items()
  }
  
  class OverwriteDialog {
    - show_version_options: bool
    - source_info: Dict
    - dest_info: Dict
    + _create_comparison()
  }
  
  class ProgressDialog {
    - progress_data: ProgressData
    - cancelled: bool
    + update()
    + set_total()
    + get_speed_str()
    + on_cancel()
  }
}

package "Управление диалогами" {
  class DualPaneApp {
    - loop: urwid.MainLoop
    + show_dialog(dialog, width, height)
    + close_dialog()
    - _create_overlay()
  }
  
  class "Overlay System" as OverlaySys {
    + create_overlay()
    + center_dialog()
    + handle_focus()
    + esc_to_close()
  }
}

' Взаимодействия
DualPaneApp *--> OverlaySys : использует
OverlaySys *--> DialogBase : управляет

CommonDialog <|-- InputDialog
CommonDialog <|-- ConfirmDialog
CommonDialog <|-- FileViewerDialog
CommonDialog <|-- FileInfoDialog
CommonDialog <|-- VersionSelectDialog
CommonDialog <|-- OverwriteDialog
CommonDialog <|-- SortDialog
CommonDialog <|-- CopyMoveDialog
CommonDialog <|-- ProgressDialog

' Поток вызова диалогов
DualPaneApp -> ConfirmDialog : Для подтверждения удаления
DualPaneApp -> InputDialog : Для ввода имени/паттерна
DualPaneApp -> ProgressDialog : Для длительных операций
DualPaneApp -> OverwriteDialog : Для конфликтов копирования
PanelWidget -> SortDialog : Для изменения сортировки
PanelWidget -> VersionSelectDialog : Для выбора версий файла
PanelWidget -> FileInfoDialog : Для информации F4

' События
ConfirmDialog -> DualPaneApp : callback(confirmed)
InputDialog -> DualPaneApp : callback(confirmed, text)
ProgressDialog -> DualPaneApp : callback() при отмене
OverwriteDialog -> DualPaneApp : callback(choice)
SortDialog -> PanelWidget : callback(confirmed, mode, reverse)

@enduml
```

### 9. Диаграмма многопоточной архитектуры

```plantuml
@startuml
title Многопоточная архитектура и синхронизация

package "Основной поток (UI)" {
  component "urwid.MainLoop" as MainLoop {
    - event_queue
    - screen_updates
    - input_handling
  }
  
  component "DualPaneApp" as App {
    - left_panel
    - right_panel
    - dialog_stack
    - pipe_r / pipe_w (wakeup)
  }
  
  component "PanelWidget UI" as PanelUI {
    - walker updates
    - focus management
    - redraw requests
  }
}

package "Фоновые потоки" {
  component "Ленивая загрузка" as LazyLoad {
    - loading_thread
    - page_iterator
    - data_aggregator
  }
  
  component "Операции файлов" as FileOps {
    - copy_thread
    - move_thread
    - delete_thread
  }
  
  component "Подсчет размеров" as SizeCalc {
    - size_thread
    - recursive_walker
    - size_aggregator
  }
  
  component "S3 API вызовы" as S3Calls {
    - boto3 clients
    - paginators
    - retry logic
  }
}

package "Механизмы синхронизации" {
  database "Thread-safe данные" as ThreadSafe {
    + ProgressData (atomic updates)
    + LRU Cache (thread-safe OrderedDict)
    + Status flags (atomic)
  }
  
  component "Event Loop интеграция" as Events {
    + set_alarm_in()
    + draw_screen()
    + wakeup() через pipe
  }
  
  component "Callback система" as Callbacks {
    + UI обновления
    + Диалог завершения
    + Ошибки обработки
  }
}

' Потоки и связи
MainLoop -> App : Обработка ввода
App -> PanelUI : Обновление интерфейса

LazyLoad -[#blue]-> S3Calls : Асинхронные запросы
FileOps -[#blue]-> S3Calls : Операции записи
SizeCalc -[#blue]-> S3Calls : Запросы метаданных

LazyLoad -> Events : set_alarm_in() для UI updates
FileOps -> Events : Прогресс операций
SizeCalc -> Events : Результаты подсчета

LazyLoad -> ThreadSafe : Агрегация данных
FileOps -> ThreadSafe : Прогресс операций

Events -> Callbacks : Вызов колбэков в UI потоке
Callbacks -> PanelUI : Обновление интерфейса
Callbacks -> App : Закрытие диалогов

' Критические секции
note right of ThreadSafe
  Атомарные операции:
  - progress.success_count += 1
  - cache.put(key, value)
  - loading_in_progress = False
  
  Синхронизация через:
  - threading.Event
  - set_alarm_in()
  - Главный цикл urwid
end note

' Пробуждение главного цикла
App -> Events : wakeup() из фонового потока
Events -> MainLoop : Чтение из pipe
MainLoop -> App : Вызов обработчиков

' Обработка ошибок в потоках
S3Calls -> Callbacks : Исключения S3
LazyLoad -> Callbacks : Ошибки загрузки
