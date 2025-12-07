# Глава 6: Добавляем пользовательский интерфейс RAG с помощью Gradio

## Контекст главы
- Открывает вторую часть книги "Компоненты RAG"
- Практическое руководство по созданию интерактивного RAG-приложения
- Использование Gradio как UI-фреймворка

## Цели обучения
- Настройка среды Gradio
- Интеграция RAG-модели
- Создание веб-интерфейса
- Размещение приложения в Интернете
- Быстрое прототипирование и развертывание

## Почему Gradio?
- Простота для не-веб-разработчиков
- Экономия времени на изучение веб-технологий
- Быстрая настройка UI с базовой аутентификацией
- Идеально для тестирования и демонстрации

## Преимущества Gradio
- Открытый исходный код
- Хорошая интеграция с фреймворками ML
  - TensorFlow
  - PyTorch
  - Keras
- Платформа для развертывания моделей
- Упрощение командной работы и сбора отзывов
- Интеграция с Hugging Face
  - Постоянные ссылки через Spaces
  - Бесплатный хостинг ML-моделей

## Ограничения Gradio
- Не для production-приложений с массовой нагрузкой
- Ограниченная гибкость UI
- Не подходит для сложных интерфейсов

## Лаборатория кода 6.1

### Установка пакетов
```bash
%pip install gradio
%pip uninstall uvloop -y
```

### Импорт библиотек
```python
import asyncio
import nest_asyncio
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
nest_asyncio.apply()
import gradio as gr
```

### Функция обработки вопросов
```python
def process_question(question):
    result = rag_chain_with_source.invoke(question)
    relevance_score = result['answer']['relevance_score']
    final_answer = result['answer']['final_answer']
    sources = [doc.metadata['source'] for doc in result['context']]
    source_list = ", ".join(sources)
    return relevance_score, final_answer, source_list
```

### Настройка интерфейса Gradio
```python
demo = gr.Interface(
    fn=process_question,
    inputs=gr.Textbox(label="Enter your question", 
                     value="What are the Advantages of using RAG?"),
    outputs=[
        gr.Textbox(label="Relevance Score"),
        gr.Textbox(label="Final Answer"),
        gr.Textbox(label="Sources")
    ],
    title="RAG Question Answering",
    description="Enter a question about RAG and get an answer, a relevancy score, and sources."
)
```

### Запуск интерфейса
```python
demo.launch(share=True, debug=True)
```
#### Параметры запуска:
- `share=True`: генерация публичного URL
- `debug=True`: режим отладки
- `auth={...}`: базовая аутентификация

## Работа интерфейса
- Принимает входные вопросы
- Вызывает RAG-конвейер
- Извлекает:
  - Оценку релевантности
  - Финальный ответ
  - Источники информации
- Обновляет выходные текстовые поля
- Остается активным до закрытия

## Результаты выполнения
- Локальный веб-сервер
- Публичный URL (действует 72 часа)
- Интерфейс с полями ввода/вывода
- Возможность тестирования с разными вопросами

## Рекомендации
- Изучить документацию Gradio
- Использовать Hugging Face Spaces для постоянного хостинга
- Тестировать с релевантными и нерелевантными вопросами
- Настроить безопасную аутентификацию
