# Архитектура on-premise LLM решения для ИТ-инфраструктуры

## 1. Общая архитектура системы

### Компоненты системы:
- **LLM Engine** - основная языковая модель
- **Knowledge Base** - база знаний с документацией и контекстом инфраструктуры
- **Context Manager** - управление контекстом запросов
- **Data Ingestion Pipeline** - система загрузки и обновления данных
- **Feedback System** - система обратной связи и обучения
- **API Gateway** - интерфейс взаимодействия

## 2. Выбор LLM модели

### Рекомендуемые модели для CPU-only инфраструктуры:

**Первый выбор: Llama 2/3 70B (квантизованная)**
- Модель: `llama-2-70b-chat.Q4_K_M.gguf` или `llama-3-70b-instruct.Q4_K_M.gguf`
- Требования: 48-64 GB RAM
- Производительность: высокое качество ответов для технических задач
- Инструмент: llama.cpp с поддержкой CPU

**Альтернатива: CodeLlama 34B**
- Модель: `codellama-34b-instruct.Q4_K_M.gguf`
- Требования: 24-32 GB RAM
- Специализация: лучше для генерации кода и скриптов

**Легковесная опция: Mistral 7B**
- Модель: `mistral-7b-instruct-v0.2.Q8_0.gguf`
- Требования: 8-12 GB RAM
- Применение: для менее критичных задач или при ограниченных ресурсах

## 3. Предварительная загрузка документации

### 3.1 Структура системы загрузки

```
knowledge_base/
├── products/
│   ├── ceph/
│   │   ├── v16.2.10/
│   │   │   ├── docs/
│   │   │   ├── troubleshooting/
│   │   │   └── examples/
│   │   └── v17.2.5/
│   ├── kafka/
│   │   ├── v2.8.0/
│   │   └── v3.4.0/
│   └── kubernetes/
├── stackoverflow/
│   ├── ceph/
│   ├── kafka/
│   └── kubernetes/
└── infrastructure/
    ├── ansible_inventory/
    ├── version_db.csv
    └── logs/
```

### 3.2 Скрипт для загрузки документации

```python
# documentation_crawler.py
import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from urllib.parse import urljoin, urlparse
import time

class DocumentationCrawler:
    def __init__(self, version_db_path, output_dir):
        self.version_db = pd.read_csv(version_db_path)
        self.output_dir = output_dir
        self.product_configs = {
            'ceph': {
                'base_url': 'https://docs.ceph.com/en/',
                'version_pattern': 'stable-{version}/',
                'sections': ['rados', 'rbd', 'cephfs', 'troubleshooting']
            },
            'kafka': {
                'base_url': 'https://kafka.apache.org/',
                'version_pattern': '{version}/documentation.html',
                'sections': ['quickstart', 'configuration', 'operations']
            },
            'kubernetes': {
                'base_url': 'https://kubernetes.io/docs/',
                'version_pattern': 'v{version}/',
                'sections': ['concepts', 'tasks', 'troubleshooting']
            }
        }
    
    def crawl_all_versions(self):
        for product in self.version_db['product'].unique():
            versions = self.version_db[
                self.version_db['product'] == product
            ]['version'].unique()
            
            for version in versions:
                self.crawl_product_version(product, version)
    
    def crawl_product_version(self, product, version):
        if product not in self.product_configs:
            return
        
        config = self.product_configs[product]
        version_dir = os.path.join(
            self.output_dir, 'products', product, f'v{version}'
        )
        os.makedirs(version_dir, exist_ok=True)
        
        # Crawl official documentation
        for section in config['sections']:
            self.crawl_section(product, version, section, version_dir)
        
        # Crawl StackOverflow
        self.crawl_stackoverflow(product, version)
    
    def crawl_stackoverflow(self, product, version_range=None):
        # Implement StackOverflow API integration
        pass
```

### 3.3 Обновление базы знаний

```python
# knowledge_updater.py
class KnowledgeUpdater:
    def __init__(self, knowledge_base_path):
        self.kb_path = knowledge_base_path
        
    def update_from_version_changes(self, old_csv, new_csv):
        old_df = pd.read_csv(old_csv)
        new_df = pd.read_csv(new_csv)
        
        # Найти новые версии
        new_versions = self.find_version_differences(old_df, new_df)
        
        # Загрузить документацию для новых версий
        for product, version in new_versions:
            self.download_product_docs(product, version)
    
    def update_stackoverflow_content(self, products):
        # Еженедельное обновление StackOverflow контента
        for product in products:
            recent_questions = self.fetch_recent_stackoverflow(
                product, days=7
            )
            self.store_stackoverflow_content(product, recent_questions)
```

## 4. Система управления контекстом

### 4.1 Context Manager

```python
class ContextManager:
    def __init__(self, ansible_inventory, version_db):
        self.inventory = self.load_ansible_inventory(ansible_inventory)
        self.versions = pd.read_csv(version_db)
        self.conversation_context = {}
    
    def build_context_for_query(self, query, conversation_id):
        # Определить релевантные продукты из запроса
        relevant_products = self.extract_products_from_query(query)
        
        context = {
            'products': {},
            'infrastructure': {},
            'conversation_history': self.get_conversation_history(conversation_id)
        }
        
        for product in relevant_products:
            # Получить информацию о серверах с этим продуктом
            servers = self.get_servers_by_product(product)
            versions = self.get_product_versions(product, servers)
            
            context['products'][product] = {
                'servers': servers,
                'versions': versions,
                'documentation_paths': self.get_doc_paths(product, versions)
            }
        
        return context
    
    def get_servers_by_product(self, product):
        # Анализ Ansible inventory для поиска серверов с продуктом
        servers = []
        for group, hosts in self.inventory.items():
            if product.lower() in group.lower():
                servers.extend(hosts)
        return servers
```

## 5. Система векторного поиска

### 5.1 Embedding и индексация

```python
# Используем sentence-transformers для CPU
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

class KnowledgeSearchEngine:
    def __init__(self, knowledge_base_path):
        # Используем многоязычную модель для русского и английского
        self.embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.indexes = {}
        self.documents = {}
        
    def build_indexes(self):
        for product_dir in os.listdir(self.knowledge_base_path):
            self.build_product_index(product_dir)
    
    def build_product_index(self, product):
        documents = self.load_product_documents(product)
        embeddings = self.embedder.encode(documents)
        
        # Создаем FAISS index
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings.astype('float32'))
        
        self.indexes[product] = index
        self.documents[product] = documents
    
    def search_relevant_docs(self, query, products, top_k=5):
        query_embedding = self.embedder.encode([query])
        results = {}
        
        for product in products:
            if product in self.indexes:
                scores, indices = self.indexes[product].search(
                    query_embedding.astype('float32'), top_k
                )
                results[product] = [
                    self.documents[product][idx] for idx in indices[0]
                ]
        
        return results
```

## 6. Основной LLM Engine

### 6.1 Интеграция с llama.cpp

```python
from llama_cpp import Llama

class InfrastructureLLM:
    def __init__(self, model_path, context_manager, search_engine):
        self.llm = Llama(
            model_path=model_path,
            n_ctx=4096,  # Размер контекста
            n_threads=8,  # Количество CPU потоков
            verbose=False
        )
        self.context_manager = context_manager
        self.search_engine = search_engine
        
    def generate_response(self, query, conversation_id):
        # Построить контекст
        context = self.context_manager.build_context_for_query(
            query, conversation_id
        )
        
        # Найти релевантную документацию
        relevant_docs = self.search_engine.search_relevant_docs(
            query, list(context['products'].keys())
        )
        
        # Построить промпт
        prompt = self.build_prompt(query, context, relevant_docs)
        
        # Генерация ответа
        response = self.llm(
            prompt,
            max_tokens=1024,
            temperature=0.3,
            top_p=0.9
        )
        
        return response['choices'][0]['text']
    
    def build_prompt(self, query, context, relevant_docs):
        prompt = f"""Ты - эксперт по администрированию ИТ-инфраструктуры.

КОНТЕКСТ ИНФРАСТРУКТУРЫ:
"""
        
        # Добавить информацию о серверах и версиях
        for product, info in context['products'].items():
            prompt += f"\n{product.upper()}:\n"
            for server in info['servers']:
                version = info['versions'].get(server, 'unknown')
                prompt += f"  - {server}: версия {version}\n"
        
        # Добавить релевантную документацию
        prompt += "\nРЕЛЕВАНТНАЯ ДОКУМЕНТАЦИЯ:\n"
        for product, docs in relevant_docs.items():
            prompt += f"\n{product}:\n"
            for doc in docs[:3]:  # Ограничить количество документов
                prompt += f"- {doc[:200]}...\n"
        
        prompt += f"\nВОПРОС: {query}\n\nОТВЕТ:"
        
        return prompt
```

## 7. Система обратной связи

### 7.1 Feedback Collection

```python
class FeedbackSystem:
    def __init__(self, feedback_db_path):
        self.feedback_db = feedback_db_path
        
    def collect_feedback(self, query, response, user_feedback, correct_solution=None):
        feedback_entry = {
            'timestamp': datetime.now(),
            'query': query,
            'response': response,
            'feedback': user_feedback,  # positive/negative
            'correct_solution': correct_solution,
            'embedding': self.get_query_embedding(query)
        }
        
        self.store_feedback(feedback_entry)
    
    def get_similar_feedback(self, query, threshold=0.8):
        # Найти похожие запросы с обратной связью
        query_embedding = self.get_query_embedding(query)
        similar_cases = self.search_similar_feedback(query_embedding, threshold)
        return similar_cases
    
    def update_response_quality(self, query, context):
        # Учесть обратную связь при формировании ответа
        similar_feedback = self.get_similar_feedback(query)
        
        if similar_feedback:
            # Добавить информацию о предыдущих ошибках
            return self.build_feedback_context(similar_feedback)
        
        return ""
```

## 8. Требования к оборудованию

### 8.1 Минимальная конфигурация (Mistral 7B):
- **CPU**: 8+ ядер (Intel Xeon или AMD EPYC)
- **RAM**: 16 GB (12 GB для модели + 4 GB для системы)
- **Storage**: 50 GB SSD для модели и индексов
- **Bandwidth**: 1 Gbps для обновления документации

### 8.2 Рекомендуемая конфигурация (Llama 70B):
- **CPU**: 16+ ядер с высокой частотой
- **RAM**: 80 GB (64 GB для модели + 16 GB для системы и кэша)
- **Storage**: 200 GB NVMe SSD
- **Bandwidth**: 10 Gbps

### 8.3 Оптимальная конфигурация:
- **Несколько VM** с распределенной нагрузкой
- **VM1**: LLM Engine (80 GB RAM, 16 CPU)
- **VM2**: Knowledge Base + Search (32 GB RAM, 8 CPU)
- **VM3**: Context Manager + API (16 GB RAM, 4 CPU)

## 9. Развертывание и обслуживание

### 9.1 Docker Compose конфигурация

```yaml
version: '3.8'
services:
  llm-engine:
    build: ./llm-engine
    volumes:
      - ./models:/models
      - ./knowledge_base:/knowledge_base
    environment:
      - MODEL_PATH=/models/llama-2-70b-chat.Q4_K_M.gguf
    ports:
      - "8000:8000"
    deploy:
      resources:
        limits:
          memory: 64G
          cpus: '16'

  knowledge-base:
    build: ./knowledge-base
    volumes:
      - ./knowledge_base:/data
      - ./ansible_inventory:/inventory
    ports:
      - "8001:8001"

  context-manager:
    build: ./context-manager
    depends_on:
      - knowledge-base
    ports:
      - "8002:8002"
```

### 9.2 Скрипты автоматизации

```bash
#!/bin/bash
# update-knowledge.sh

# Обновление базы версий
python3 /opt/llm-system/scripts/update_versions.py

# Проверка новых версий продуктов
python3 /opt/llm-system/scripts/check_new_versions.py

# Загрузка новой документации
if [ -f "/tmp/new_versions.txt" ]; then
    python3 /opt/llm-system/scripts/download_docs.py --versions-file /tmp/new_versions.txt
fi

# Обновление индексов
python3 /opt/llm-system/scripts/rebuild_indexes.py

# Перезапуск сервисов
docker-compose restart llm-engine
```

## 10. Мониторинг и метрики

### 10.1 Ключевые метрики:
- Время ответа LLM
- Точность ответов (на основе feedback)
- Использование ресурсов
- Актуальность документации
- Количество успешных решений

### 10.2 Алерты:
- Высокое использование RAM (>90%)
- Медленные ответы (>30 сек)
- Негативный feedback (>30%)
- Устаревшая документация (>30 дней)

## 11. Этапы внедрения

### Фаза 1 (2-3 недели):
1. Развертывание базовой LLM (Mistral 7B)
2. Загрузка документации для текущих версий
3. Создание простого интерфейса

### Фаза 2 (2-3 недели):
1. Интеграция с Ansible inventory
2. Автоматическое определение контекста
3. Система обратной связи

### Фаза 3 (3-4 недели):
1. Обновление до более мощной модели
2. Автоматическое обновление документации
3. Продвинутая аналитика и мониторинг

### Фаза 4 (2-3 недели):
1. Fine-tuning на специфических данных инфраструктуры
2. Интеграция с системами логирования
3. Автоматизация DevOps процессов