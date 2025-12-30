
# Создаю архитектурные диаграммы в формате PlantUML

# 1. Диаграмма классов
class_diagram = '''@startuml json_tui_viewer_classes
!theme plain
skinparam classAttributeIconSize 0
skinparam backgroundColor white

title Диаграмма классов - JSON TUI Viewer

class JsonNode {
  - key: str
  - value: any
  - parent: JsonNode
  - depth: int
  - index: int
  - expanded: bool
  - children: List[JsonNode]
  --
  + is_leaf(): bool
  + build_children(): void
  + toggle(): void
  + get_root_object(): JsonNode
  + get_relative_path_with_state(): List[Tuple]
  + expand_all(): void
  + collapse_all(): void
  + collect_leaf_fields(): Set[str]
}

class LazyJsonFile {
  - filepath: str
  - _offsets: List[int]
  - _count: int
  - _cache: Dict[int, dict]
  - _cache_size: int
  - _is_single: bool
  --
  - _build_index(): void
  + __len__(): int
  + __getitem__(index: int): dict
  + search_by_field(field_name, pattern, max): List
  + search_all_fields(pattern, max): Tuple[List, Set]
}

class "Main Application" as Main {
  + root: JsonNode
  + loaded_objects: Set[int]
  + cursor_idx: int
  + top_idx: int
  + filter_fields: Set[str]
  + search_results: List[JsonNode]
  --
  + main(stdscr, json_file, filename): void
  + draw(...): int
  + load_object_into_tree(...): JsonNode
  + ensure_next_objects_loaded(...): void
}

package "UI Functions" {
  class ViewFunctions {
    + format_node_line(...): str
    + show_full_value_viewer(...): void
    + show_field_selector(...): Set[str]
    + input_string(...): str
  }
  
  class NavigationFunctions {
    + navigate_by_path_with_state(...): JsonNode
    + expand_path_to_node(...): void
    + find_node_by_path(...): JsonNode
  }
  
  class FilterFunctions {
    + should_show_node(...): bool
    + build_visible_list(...): List[JsonNode]
  }
}

LazyJsonFile "1" -- "1..*" "dict" : загружает >
JsonNode "1" o-- "0..*" JsonNode : parent/children
Main "1" --> "1" LazyJsonFile : использует >
Main "1" --> "1" JsonNode : корневой узел >
Main ..> ViewFunctions : использует >
Main ..> NavigationFunctions : использует >
Main ..> FilterFunctions : использует >

note right of JsonNode
  Узел дерева JSON структуры.
  Поддерживает ленивое создание
  дочерних узлов.
end note

note right of LazyJsonFile
  Ленивая загрузка объектов
  с LRU-кэшированием.
  Индексирует позиции без
  загрузки содержимого.
end note

note bottom of Main
  Главный контроллер приложения.
  Управляет состоянием и
  обрабатывает пользовательский ввод.
end note

@enduml
'''

# 2. Диаграмма компонентов
component_diagram = '''@startuml json_tui_viewer_components
!theme plain
skinparam backgroundColor white

title Диаграмма компонентов - JSON TUI Viewer

[JSON/JSONL File] as File

package "Data Layer" {
  [LazyJsonFile] as Loader
  database "LRU Cache" as Cache
  [File Index] as Index
}

package "Domain Layer" {
  [JsonNode Tree] as Tree
  [Path Navigator] as PathNav
}

package "Presentation Layer" {
  [Main Event Loop] as EventLoop
  [Screen Renderer] as Renderer
  [Field Filter] as Filter
  [Search Engine] as Search
}

package "UI Components" {
  [Value Viewer] as Viewer
  [Field Selector] as Selector
  [Input Dialog] as Input
}

interface "curses" as Curses

File --> Loader : читает
Loader --> Cache : кэширует
Loader --> Index : индексирует
Loader --> Tree : создает узлы
Tree --> PathNav : навигация
EventLoop --> Tree : управляет
EventLoop --> Renderer : отрисовка
EventLoop --> Filter : фильтрация
EventLoop --> Search : поиск
Renderer --> Curses : вывод
Viewer --> Curses : вывод
Selector --> Curses : вывод
Input --> Curses : ввод
EventLoop ..> Viewer : использует
EventLoop ..> Selector : использует
EventLoop ..> Input : использует
Search --> Loader : запросы
Filter --> Tree : обход

note right of Loader
  Загружает объекты по индексу.
  Поддерживает до 200 объектов в кэше.
  Память: ~8 байт на объект (индекс).
end note

note right of Tree
  Дерево создается лениво.
  Узлы разворачиваются
  только при обращении.
end note

note bottom of EventLoop
  Обрабатывает клавиши:
  - Навигация (↑↓←→)
  - Поиск (s, F)
  - Фильтрация (f)
  - Expand/Collapse (a, z, A, Z)
end note

@enduml
'''

# 3. Диаграмма последовательности - загрузка и навигация
sequence_diagram = '''@startuml json_tui_viewer_sequence
!theme plain
skinparam backgroundColor white

title Последовательность: Загрузка и навигация

actor User
participant "Main" as Main
participant "LazyJsonFile" as Loader
participant "JsonNode" as Node
participant "Renderer" as Render
database "File" as File

== Инициализация ==
User -> Main : запуск программы
Main -> Loader : __init__(filepath)
Loader -> File : открыть файл
Loader -> Loader : _build_index()
note right
  Сканирует файл,
  запоминает позиции
  всех объектов
end note
Loader --> Main : готов (N объектов)

Main -> Main : предзагрузка 20 объектов
loop для каждого объекта
  Main -> Loader : __getitem__(i)
  Loader -> File : seek(offset)
  Loader -> File : readline()
  File --> Loader : JSON строка
  Loader -> Loader : json.loads()
  Loader -> Loader : добавить в cache
  Loader --> Main : dict
  Main -> Node : new JsonNode(data)
  Node --> Main : узел создан
end

== Навигация ==
User -> Main : нажатие ↓
Main -> Main : cursor_idx++
Main -> Main : build_visible_list()
Main -> Node : обход дерева
Node --> Main : список видимых узлов
Main -> Render : draw(visible_nodes)
Render --> User : обновление экрана

== Разворачивание узла ==
User -> Main : нажатие →
Main -> Node : toggle()
Node -> Node : build_children()
note right
  Ленивое создание
  дочерних узлов
end note
Node --> Main : развернут
Main -> Main : build_visible_list()
Main -> Render : draw(visible_nodes)
Render --> User : обновление экрана

== Ленивая загрузка при скроллинге ==
User -> Main : скроллинг вниз
Main -> Main : cursor близко к концу?
alt нужна загрузка
  Main -> Main : ensure_next_objects_loaded()
  loop 5 объектов
    Main -> Loader : __getitem__(next_idx)
    Loader -> File : seek + readline
    Loader --> Main : dict
    Main -> Node : new JsonNode(data)
  end
end
Main -> Render : draw(visible_nodes)
Render --> User : обновление экрана

@enduml
'''

# 4. Диаграмма последовательности - поиск
search_sequence = '''@startuml json_tui_viewer_search
!theme plain
skinparam backgroundColor white

title Последовательность: Глобальный поиск (F)

actor User
participant "Main" as Main
participant "LazyJsonFile" as Loader
participant "JsonNode" as Node
participant "Renderer" as Render
database "File" as File

User -> Main : нажатие F
Main -> Main : input_string("поиск")
Main <-- Main : pattern = "192.168"

Main -> Render : "Поиск по всем полям..."
Render --> User : статус

Main -> Loader : search_all_fields(pattern, 1000)
note right
  Поиск по ВСЕМ
  листовым полям
  во всех объектах
end note

loop для каждого объекта
  Loader -> Loader : __getitem__(i)
  alt объект в cache
    Loader -> Loader : взять из cache
  else объект не в cache
    Loader -> File : seek + readline
    File --> Loader : JSON строка
    Loader -> Loader : json.loads()
    Loader -> Loader : cache[i] = obj
  end
  
  Loader -> Loader : search_recursive(obj)
  note right
    Рекурсивный обход
    всех листовых значений
  end note
  
  alt значение совпадает
    Loader -> Loader : matches.append(...)
    Loader -> Loader : matched_fields.add(field_name)
  end
end

Loader --> Main : (matches, matched_fields)

Main -> Main : filter_fields = matched_fields
note right
  Автоматическая фильтрация
  на поля с результатами
end note

loop для каждого результата
  Main -> Loader : load_object_into_tree(obj_idx)
  Main -> Node : find_node_by_path(path)
  Node --> Main : target_node
  Main -> Main : search_results.append(node)
end

Main -> Node : expand_path_to_node(first_result)
Main -> Main : build_visible_list(filter_fields)
note right
  Видимы только
  отфильтрованные поля
end note

Main -> Render : draw(visible_nodes)
Render --> User : "Найдено 15, фильтр: 3 полей"

User -> Main : нажатие n
Main -> Main : search_idx++
Main -> Node : expand_path_to_node(next_result)
Main -> Main : build_visible_list()
Main -> Render : draw(visible_nodes)
Render --> User : переход к след. результату

@enduml
'''

# 5. Диаграмма состояний
state_diagram = '''@startuml json_tui_viewer_states
!theme plain
skinparam backgroundColor white

title Диаграмма состояний - Узел JsonNode

[*] --> Created : new JsonNode()

state Created {
  [*] --> Collapsed
  Collapsed : expanded = False
  Collapsed : children = None
}

Created --> Collapsed

state "Операции с узлом" as Operations {
  Collapsed --> Expanding : toggle() / is_leaf() == False
  Expanding --> Expanded : build_children()
  Expanded --> Collapsed : toggle()
  
  Expanded : expanded = True
  Expanded : children = List[JsonNode]
  
  state Expanded {
    [*] --> Visible
    Visible --> Hidden : filter applied
    Hidden --> Visible : filter removed
  }
  
  Expanding : создание дочерних узлов
  
  note right of Expanded
    Дочерние узлы видны
    в списке visible_nodes
  end note
}

Operations --> ExpandingAll : expand_all()
ExpandingAll --> AllExpanded : рекурсивно для всех детей

AllExpanded --> Collapsed : collapse_all()

note top of Operations
  Листовые узлы (is_leaf() == True)
  не имеют состояний Expanded/Collapsed
end note

state "Специальные операции" as Special {
  state "В результатах поиска" as InSearch
  state "Отфильтрован" as Filtered
  state "Под курсором" as Focused
}

Operations --> Special : контекстные состояния

note right of Special
  Эти состояния не хранятся в узле,
  а определяются контекстом:
  - search_results
  - filter_fields
  - cursor_idx
end note

@enduml
'''

# 6. Диаграмма развертывания
deployment_diagram = '''@startuml json_tui_viewer_deployment
!theme plain
skinparam backgroundColor white

title Диаграмма развертывания

node "Терминал" {
  artifact "python3" as Python
  
  component "json_tui_viewer.py" as App {
    [Main Loop]
    [Event Handler]
    [Renderer]
  }
  
  component "curses library" as Curses {
    [Screen Management]
    [Keyboard Input]
  }
  
  Python --> App : запускает
  App --> Curses : использует
}

node "Файловая система" {
  database "data.jsonl" as DataFile {
    Объект 1
    Объект 2
    ...
    Объект N
  }
  
  file "LRU Cache" as Cache {
    до 200 объектов
    в памяти
  }
  
  file "File Index" as Index {
    позиции объектов
    (8 байт × N)
  }
}

App --> DataFile : читает
App --> Cache : кэширует
App --> Index : индексирует

note right of DataFile
  Формат: JSON или JSONL
  Размер: до миллионов объектов
  Доступ: sequential read
end note

note right of Cache
  LRU кэш в RAM
  Eviction: FIFO при переполнении
  Потребление: ~6 МБ (200 × 30 КБ)
end note

note right of Index
  Индекс в RAM
  Для 1M объектов: ~8 МБ
  Строится при запуске
end note

node "Пользователь" {
  actor User
  interface "Keyboard" as KB
  interface "Display" as Display
}

User --> KB
KB --> Curses : клавиши
Curses --> Display : отрисовка
Display --> User : визуализация

@enduml
'''

# 7. Диаграмма активности - обработка клавиши
activity_diagram = '''@startuml json_tui_viewer_activity
!theme plain
skinparam backgroundColor white

title Диаграмма активности: Обработка клавиши PgDn

start

:Пользователь нажимает PgDn;

:Получить текущий узел под курсором;
:Найти корневой объект (depth=0);

if (Есть следующий объект?) then (да)
  :Получить относительный путь\nк текущему узлу;
  note right
    get_relative_path_with_state()
    Возвращает: [(key, depth, expanded), ...]
  end note
  
  :next_obj_idx = current_obj_idx + 1;
  
  if (Объект загружен?) then (нет)
    :Загрузить объект из файла;
    :json_file[next_obj_idx];
    :Добавить в cache;
    :Создать JsonNode;
    :Добавить в дерево;
  endif
  
  :Попытка навигации по пути\nв новом объекте;
  :navigate_by_path_with_state();
  
  note right
    Разворачивает узлы по пути,
    восстанавливает состояние expanded
  end note
  
  if (Путь найден?) then (да)
    :Позиционировать курсор\nна найденный узел;
  else (нет)
    :Позиционировать курсор\nна корень объекта;
  endif
  
  :Пересчитать список видимых узлов;
  :build_visible_list(filter_fields);
  
  if (Применен фильтр?) then (да)
    :Фильтровать узлы по именам полей;
    :should_show_node() для каждого узла;
  endif
  
  :Перерисовать экран;
  :draw(visible_nodes);
  
else (нет)
  :Вывести сообщение\n"Это последний объект";
endif

stop

@enduml
'''

# Сохраняем все диаграммы
diagrams = {
    'class_diagram.puml': class_diagram,
    'component_diagram.puml': component_diagram,
    'sequence_diagram.puml': sequence_diagram,
    'search_sequence.puml': search_sequence,
    'state_diagram.puml': state_diagram,
    'deployment_diagram.puml': deployment_diagram,
    'activity_diagram.puml': activity_diagram
}

for filename, content in diagrams.items():
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

print("Создано архитектурных диаграмм:", len(diagrams))
print("\nСписок файлов:")
for filename in diagrams.keys():
    print(f"  - {filename}")

print("\n✅ Все диаграммы сохранены в формате PlantUML")
print("\nДля просмотра используйте:")
print("  - Online: https://www.plantuml.com/plantuml/")
print("  - VS Code: расширение 'PlantUML'")
print("  - CLI: java -jar plantuml.jar *.puml")
