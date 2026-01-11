
plantuml_mindmap = """@startmindmap
* OpenTelemetry\\nИнструментация
** eBPF\\n(Beyla/OBI)
*** Преимущества
**** Платформенная функция\\n(DaemonSet)
**** Видит запросы\\nглазами клиента
**** Встроенные метрики\\nсервис-графов
**** Универсальные функции\\nдля всех языков
*** Что предоставляет
**** Базовые метрики\\n(RED metrics)
**** Метрики сервис-графов
**** Сетевые метрики
**** Метрики процессов
**** Ограниченный трейсинг
*** Ограничения
**** Только Linux
**** Не полный трейсинг\\nдля Java/reactive
**** Нет контекста\\nв логах
** SDK\\n(Java agent и др.)
*** Преимущества
**** Полноценный\\nдистрибутированный трейсинг
**** Глубокая детализация\\n(исключения, стэктрейсы)
**** Обогащение логов\\nтrace ID
**** Runtime-метрики\\n(heap, GC)
*** Что предоставляет
**** Детальные spans\\n(внутренние слои)
**** События (Exceptions)
**** Кастомные метрики
**** Инструментация\\nбизнес-логики
*** Недостатки
**** Привязка к runtime
**** Не видит queue time
**** Overhead при 100%\\nsampling
** Гибридный\\nподход
*** eBPF для baseline
**** Все сервисы
**** Без дубликатов
*** SDK для insights
**** Детальный трейсинг
**** Sampled traces
*** Конфигурация
**** span.metrics.skip=true
**** Автоопределение SDK
@endmindmap"""

with open('otel_mindmap.puml', 'w') as f:
    f.write(plantuml_mindmap)

print("Mindmap создан: otel_mindmap.puml")

# Создаем диаграмму архитектуры
plantuml_architecture = """@startuml
!define RECTANGLE class

skinparam backgroundColor #FEFEFE
skinparam component {
  BackgroundColor<<eBPF>> LightBlue
  BackgroundColor<<SDK>> LightGreen
  BackgroundColor<<App>> LightYellow
  BorderColor Black
}

package "Kubernetes Cluster" {
  
  component "eBPF Agent\\n(Beyla/OBI)\\nDaemonSet" <<eBPF>> as ebpf {
    [Network Level\\nObservation]
    [Kernel Hooks]
  }
  
  node "Application Pod" {
    component "Application" <<App>> as app
    component "OpenTelemetry\\nSDK Agent" <<SDK>> as sdk
  }
  
}

component "OTLP Endpoint" as otlp

database "Grafana Cloud" as grafana {
  [Tempo (Traces)]
  [Mimir (Metrics)]
  [Loki (Logs)]
}

' Connections from eBPF
ebpf --> otlp : "Baseline Metrics:\\n- Request Rate\\n- Error Rate\\n- Latency\\n- Service Graphs\\n- Network Metrics\\n- Process Metrics"

' Connections from SDK
sdk --> otlp : "Deep Insights:\\n- Detailed Traces\\n- Runtime Metrics\\n- Log Context\\n- Custom Metrics\\n+ span.metrics.skip=true"

' Application connections
app <--> sdk : "Instrumented"
ebpf ..> app : "Observes\\nnetwork calls"

' OTLP to Grafana
otlp --> grafana

note right of ebpf
  **eBPF видит:**
  • Что видит клиент
  • Queue time
  • Все языки/runtime
  • Без изменений в приложении
end note

note left of sdk
  **SDK видит:**
  • Внутренние слои
  • Exceptions + stack traces
  • Runtime состояние (heap, GC)
  • Бизнес-логику
end note

note bottom of otlp
  eBPF автоматически отключает
  дублирующие метрики при
  обнаружении SDK
end note

@enduml"""

with open('otel_architecture.puml', 'w') as f:
    f.write(plantuml_architecture)

print("Архитектурная диаграмма создана: otel_architecture.puml")

# Создаем диаграмму сравнения
comparison_diagram = """@startuml
!define RECTANGLE class

skinparam backgroundColor #FEFEFE

package "Сравнение eBPF vs SDK" {
  
  card "**Запрос с очередью**" as scenario {
    
    rectangle "Client" as client
    
    rectangle "Network Layer\\n(eBPF наблюдает здесь)" as network #LightBlue {
      rectangle "Queue\\n(ожидание)" as queue #Orange
      rectangle "Processing\\n(обработка)" as processing #LightGreen
    }
    
    rectangle "Application Layer\\n(SDK наблюдает здесь)" as appLayer #LightGreen {
      rectangle "Handler\\nExecution" as handler
    }
    
  }
  
}

client -down-> network : "Request Start"
network -down-> appLayer : "Handler Called"
appLayer -up-> network : "Response"
network -up-> client : "Request End"

note right of queue
  **eBPF измеряет:**
  Queue Time + Processing Time
  = Полное время запроса
  (что видит клиент)
end note

note left of handler
  **SDK измеряет:**
  Только Processing Time
  (время активной обработки)
  
  Не включает Queue Time!
end note

legend right
  |<#LightBlue> eBPF |
  |<#LightGreen> SDK |
  |<#Orange> Критическая разница |
endlegend

@enduml"""

with open('ebpf_vs_sdk_timing.puml', 'w') as f:
    f.write(comparison_diagram)

print("Диаграмма сравнения создана: ebpf_vs_sdk_timing.puml")
