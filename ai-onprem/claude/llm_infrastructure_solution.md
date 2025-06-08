# Архитектура LLM-решения для управления ИТ-инфраструктурой

## 1. Выбор оптимальной LLM модели

### Рекомендуемые модели для CPU-инференса:

**Приоритетный выбор: Llama 3.1 8B-Instruct**
- Размер: ~4.7GB в GGUF формате (Q4_K_M квантизация)
- RAM требования: 6-8GB
- Контекст: до 128K токенов
- Отличная производительность на технических задачах

**Альтернативы:**
- **Mistral 7B-Instruct v0.3**: 4.1GB, хорошая производительность
- **Code Llama 7B-Instruct**: специализация на коде
- **Phi-3-medium-4k-instruct**: компактная модель от Microsoft

## 2. Архитектура системы

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Frontend  │───→│   API Gateway    │───→│   LLM Service   │
│   (Streamlit)   │    │   (FastAPI)      │    │   (llama.cpp)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  Context Manager │
                       │  + Session Store │
                       └──────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
    ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
    │   RAG System     │ │ Infrastructure   │ │  Feedback        │
    │   (ChromaDB)     │ │ Context Engine   │ │  Learning System │
    │ + Version Index  │ │                  │ │                  │
    └──────────────────┘ └──────────────────┘ └──────────────────┘
             │                    │                    │
             ▼                    ▼                    ▼
    ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
    │ Versioned Docs   │ │ Ansible Inventory│ │ Feedback DB      │
    │ Knowledge Base   │ │ + Versions CSV   │ │ + Learning Rules │
    └──────────────────┘ └──────────────────┘ └──────────────────┘
```

## 3. Система версионного управления документацией

### 3.1 Структура хранения документации

```
knowledge_base/
├── products/
│   ├── ceph/
│   │   ├── 16.2.10/
│   │   │   ├── installation/
│   │   │   ├── configuration/
│   │   │   ├── troubleshooting/
│   │   │   └── api/
│   │   ├── 17.2.5/
│   │   └── 18.1.0/
│   ├── kafka/
│   │   ├── 2.8.1/
│   │   ├── 3.0.0/
│   │   └── 3.4.0/
│   └── kubernetes/
│       ├── 1.25.8/
│       ├── 1.26.3/
│       └── 1.27.1/
├── stackoverflow/
│   ├── ceph/
│   │   ├── version_agnostic/
│   │   └── version_specific/
│   └── kafka/
└── metadata/
    ├── version_index.json
    └── content_fingerprints.json
```

### 3.2 Система индексации версий

```python
class VersionedKnowledgeManager:
    def __init__(self, base_path="./knowledge_base"):
        self.base_path = base_path
        self.version_index = self._load_version_index()
        self.embeddings_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.vector_db = chromadb.PersistentClient(path="./vector_db")
        
    def _load_version_index(self):
        """

## 8. Основной API сервис

### 8.1 FastAPI приложение

```python
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, List
import asyncio

app = FastAPI(title="Infrastructure LLM Assistant")

# Модели данных
class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    context: Dict = {}

class QueryResponse(BaseModel):
    response: str
    session_id: str
    infrastructure_context: Dict
    sources: List[Dict]

class FeedbackRequest(BaseModel):
    session_id: str
    query: str
    response: str
    rating: int
    feedback_text: str = ""

# Инициализация компонентов
llm_service = LLMService()
knowledge_manager = VersionedKnowledgeManager()
context_engine = InfrastructureContextEngine("./inventory.yml", "./versions.csv")
session_manager = SessionManager()
feedback_system = FeedbackSystem()
learning_engine = LearningEngine(feedback_system, knowledge_manager)

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    try:
        # Создаем или получаем сессию
        session_id = request.session_id or session_manager.create_session()
        session_context = session_manager.get_session_context(session_id)
        
        # Получаем контекст инфраструктуры
        infra_context = context_engine.get_context_for_query(
            request.query, session_context
        )
        
        # Поиск релевантной документации с учетом версий
        relevant_docs = await search_versioned_documentation(
            request.query, infra_context
        )
        
        # Формируем промпт с учетом правил обучения
        system_prompt = learning_engine._update_system_prompts()
        prompt = build_contextual_prompt(
            request.query, infra_context, relevant_docs, 
            session_context, system_prompt
        )
        
        # Генерируем ответ
        response = llm_service.generate_response(prompt)
        
        # Сохраняем в контекст сессии
        session_manager.add_to_context(
            session_id, request.query, response, infra_context
        )
        
        return QueryResponse(
            response=response,
            session_id=session_id,
            infrastructure_context=infra_context,
            sources=relevant_docs
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest, background_tasks: BackgroundTasks):
    try:
        feedback_entry = FeedbackEntry(
            query=request.query,
            response=request.response,
            rating=request.rating,
            feedback_text=request.feedback_text,
            context=session_manager.get_session_context(request.session_id),
            timestamp=datetime.now(),
            session_id=request.session_id
        )
        
        feedback_system.store_feedback(feedback_entry)
        
        # Асинхронная обработка обратной связи
        background_tasks.add_task(learning_engine.process_feedback)
        
        return {"status": "success", "message": "Feedback recorded"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-knowledge")
async def trigger_knowledge_update(background_tasks: BackgroundTasks):
    """Запускает обновление базы знаний"""
    background_tasks.add_task(update_knowledge_base)
    return {"status": "update_started"}

async def search_versioned_documentation(query: str, infra_context: Dict) -> List[Dict]:
    """Поиск в документации с учетом версий продуктов"""
    relevant_docs = []
    
    # Для каждого сервера в контексте
    for server_info in infra_context.get('servers', []):
        for software in server_info.get('software_stack', []):
            product = software['product']
            version = software['version']
            
            # Поиск в документации конкретной версии
            docs = knowledge_manager.search_versioned_docs(
                query, product, version
            )
            
            if docs:
                relevant_docs.extend([{
                    'product': product,
                    'version': version,
                    'content': doc,
                    'source': 'official_docs'
                } for doc in docs['documents']])
    
    # Также ищем в общих продуктах, упомянутых в запросе
    for product_info in infra_context.get('products', []):
        product = product_info['name']
        
        # Берем все версии этого продукта
        for version in product_info.get('versions', []):
            docs = knowledge_manager.search_versioned_docs(
                query, product, version
            )
            
            if docs:
                relevant_docs.extend([{
                    'product': product,
                    'version': version,
                    'content': doc,
                    'source': 'official_docs'
                } for doc in docs['documents']])
    
    return relevant_docs[:10]  # Ограничиваем количество

def build_contextual_prompt(query: str, infra_context: Dict, 
                          relevant_docs: List[Dict], session_context: List[Dict],
                          system_prompt: str) -> str:
    """Строит контекстуальный промпт"""
    
    # Форматируем контекст инфраструктуры
    infra_text = format_infrastructure_context(infra_context)
    
    # Форматируем документацию
    docs_text = format_documentation_context(relevant_docs)
    
    # Форматируем контекст сессии
    session_text = format_session_context(session_context)
    
    prompt = f"""{system_prompt}

CURRENT INFRASTRUCTURE CONTEXT:
{infra_text}

RELEVANT DOCUMENTATION:
{docs_text}

CONVERSATION HISTORY:
{session_text}

USER QUERY: {query}

Provide a detailed response that:
1. Uses the exact versions and configurations from the infrastructure
2. References specific servers when applicable
3. Includes step-by-step instructions if providing commands
4. Explains any risks or prerequisites
5. Cites the relevant documentation versions used

Response:"""

    return prompt

def format_infrastructure_context(infra_context: Dict) -> str:
    """Форматирует контекст инфраструктуры для промпта"""
    lines = []
    
    # Серверы
    for server in infra_context.get('servers', []):
        lines.append(f"Server: {server['name']}")
        lines.append(f"  Group: {server['info'].get('group', 'unknown')}")
        
        for software in server.get('software_stack', []):
            lines.append(f"  - {software['product']} v{software['version']}")
        lines.append("")
    
    # Продукты
    for product in infra_context.get('products', []):
        lines.append(f"Product: {product['name']}")
        lines.append(f"  Servers: {', '.join(product['servers'])}")
        lines.append(f"  Versions: {', '.join(product['versions'])}")
        lines.append("")
    
    return "\n".join(lines)

def format_documentation_context(relevant_docs: List[Dict]) -> str:
    """Форматирует документацию для промпта"""
    lines = []
    
    for doc in relevant_docs:
        lines.append(f"[{doc['product']} v{doc['version']}] {doc['content'][:500]}...")
        lines.append("")
    
    return "\n".join(lines)

def format_session_context(session_context: List[Dict]) -> str:
    """Форматирует контекст сессии для промпта"""
    if not session_context:
        return "No previous conversation."
    
    lines = []
    for item in session_context[-3:]:  # Последние 3 обмена
        lines.append(f"Previous Query: {item['query']}")
        lines.append(f"Previous Response: {item['response'][:200]}...")
        lines.append("---")
    
    return "\n".join(lines)

async def update_knowledge_base():
    """Фоновая задача обновления базы знаний"""
    try:
        # Проверяем изменения в инфраструктуре
        monitor = InfrastructureMonitor("./versions.csv", "./inventory.yml")
        changes = monitor.check_for_changes()
        
        if changes:
            # Определяем новые версии
            version_analyzer = VersionAnalyzer("./versions.csv")
            current_versions = version_analyzer.get_unique_versions()
            
            # Загружаем документацию для новых версий
            async with DocumentationScraper() as scraper:
                updater = KnowledgeUpdater(knowledge_manager, scraper)
                await updater.update_for_new_versions(current_versions)
                
        print("Knowledge base update completed")
        
    except Exception as e:
        print(f"Error updating knowledge base: {e}")
```

## 9. LLM Сервис

### 9.1 Оптимизированный инференс

```python
from llama_cpp import Llama
import threading
from queue import Queue
import time

class LLMService:
    def __init__(self, model_path: str = "./models/llama-3.1-8b-instruct.Q4_K_M.gguf"):
        self.model_path = model_path
        self.llm = None
        self.request_queue = Queue()
        self.response_cache = {}
        self.cache_max_size = 100
        self.load_model()
        
    def load_model(self):
        """Загружает модель с оптимизированными параметрами"""
        try:
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=32768,  # Контекст для длинных промптов
                n_threads=8,  # Количество CPU потоков
                n_gpu_layers=0,  # CPU-only
                n_batch=512,  # Размер батча
                verbose=False,
                use_mmap=True,  # Использование memory mapping
                use_mlock=True,  # Блокировка в памяти
                n_parts=1
            )
            print("Model loaded successfully")
        except Exception as e:
            print(f"Error loading model: {e}")
            raise
    
    def generate_response(self, prompt: str, max_tokens: int = 2048, 
                         temperature: float = 0.1) -> str:
        """Генерирует ответ с кэшированием"""
        
        # Проверяем кэш
        prompt_hash = hash(prompt)
        if prompt_hash in self.response_cache:
            return self.response_cache[prompt_hash]
        
        try:
            response = self.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
                top_k=40,
                repeat_penalty=1.1,
                stop=["<|im_end|>", "Human:", "User:"],
                echo=False
            )
            
            generated_text = response['choices'][0]['text'].strip()
            
            # Кэшируем ответ
            self._cache_response(prompt_hash, generated_text)
            
            return generated_text
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return "I apologize, but I encountered an error processing your request."
    
    def _cache_response(self, prompt_hash: int, response: str):
        """Кэширует ответ с ограничением размера"""
        if len(self.response_cache) >= self.cache_max_size:
            # Удаляем самый старый элемент
            oldest_key = next(iter(self.response_cache))
            del self.response_cache[oldest_key]
            
        self.response_cache[prompt_hash] = response
    
    def health_check(self) -> bool:
        """Проверяет работоспособность модели"""
        try:
            test_response = self.llm("Test", max_tokens=10)
            return bool(test_response['choices'][0]['text'])
        except:
            return False

## 10. Web интерфейс

### 10.1 Streamlit приложение

```python
import streamlit as st
import requests
import json
from datetime import datetime

# Конфигурация
API_BASE_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Infrastructure LLM Assistant",
    page_icon="🖥️",
    layout="wide"
)

# Инициализация состояния сессии
if 'session_id' not in st.session_state:
    st.session_state.session_id = None
if 'conversation_history' not in st.session_state:
    st.session_state.conversation_history = []

def send_query(query: str):
    """Отправляет запрос к API"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/query",
            json={
                "query": query,
                "session_id": st.session_state.session_id
            },
            timeout=120
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        st.error(f"Connection error: {e}")
        return None

def send_feedback(query: str, response: str, rating: int, feedback_text: str):
    """Отправляет обратную связь"""
    try:
        requests.post(
            f"{API_BASE_URL}/feedback",
            json={
                "session_id": st.session_state.session_id,
                "query": query,
                "response": response,
                "rating": rating,
                "feedback_text": feedback_text
            }
        )
        st.success("Feedback submitted successfully!")
        
    except requests.exceptions.RequestException as e:
        st.error(f"Error submitting feedback: {e}")

# Заголовок
st.title("🖥️ Infrastructure LLM Assistant")
st.markdown("AI-powered assistant for managing your IT infrastructure")

# Основной интерфейс
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Chat Interface")
    
    # Область для отображения истории разговора
    chat_container = st.container()
    
    # Поле ввода запроса
    query = st.text_area(
        "Enter your infrastructure query:",
        placeholder="e.g., How to troubleshoot Ceph cluster issues on server-01?",
        height=100
    )
    
    col_send, col_clear = st.columns([1, 1])
    
    with col_send:
        if st.button("Send Query", type="primary"):
            if query.strip():
                with st.spinner("Processing your query..."):
                    result = send_query(query)
                    
                if result:
                    st.session_state.session_id = result['session_id']
                    
                    # Добавляем в историю
                    st.session_state.conversation_history.append({
                        'timestamp': datetime.now(),
                        'query': query,
                        'response': result['response'],
                        'infrastructure_context': result['infrastructure_context'],
                        'sources': result['sources']
                    })
                    
                    st.rerun()
    
    with col_clear:
        if st.button("Clear Conversation"):
            st.session_state.conversation_history = []
            st.session_state.session_id = None
            st.rerun()

with col2:
    st.subheader("Infrastructure Context")
    
    if st.session_state.conversation_history:
        latest_context = st.session_state.conversation_history[-1]['infrastructure_context']
        
        # Отображаем серверы
        if latest_context.get('servers'):
            st.write("**Active Servers:**")
            for server in latest_context['servers']:
                st.write(f"• {server['name']}")
                for software in server.get('software_stack', []):
                    st.write(f"  - {software['product']} v{software['version']}")
        
        # Отображаем продукты
        if latest_context.get('products'):
            st.write("**Products:**")
            for product in latest_context['products']:
                st.write(f"• {product['name']}")
                st.write(f"  Versions: {', '.join(product['versions'])}")

# Отображение истории разговора
with chat_container:
    for i, conversation in enumerate(st.session_state.conversation_history):
        # Запрос пользователя
        st.markdown(f"**🧑‍💻 You ({conversation['timestamp'].strftime('%H:%M:%S')}):**")
        st.markdown(conversation['query'])
        
        # Ответ ассистента
        st.markdown("**🤖 Assistant:**")
        st.markdown(conversation['response'])
        
        # Источники
        if conversation.get('sources'):
            with st.expander("📚 Sources Used"):
                for source in conversation['sources']:
                    st.write(f"• {source['product']} v{source['version']}")
        
        # Кнопки обратной связи
        feedback_col1, feedback_col2, feedback_col3 = st.columns([1, 1, 2])
        
        with feedback_col1:
            rating = st.selectbox(
                "Rating:", 
                options=[1, 2, 3, 4, 5],
                index=4,
                key=f"rating_{i}"
            )
        
        with feedback_col2:
            if st.button("Submit Feedback", key=f"feedback_btn_{i}"):
                feedback_text = st.text_input(
                    "Additional feedback:", 
                    key=f"feedback_text_{i}"
                )
                send_feedback(
                    conversation['query'],
                    conversation['response'],
                    rating,
                    feedback_text
                )
        
        st.divider()

# Боковая панель с дополнительными функциями
with st.sidebar:
    st.subheader("System Information")
    
    # Кнопка обновления знаний
    if st.button("Update Knowledge Base"):
        with st.spinner("Updating knowledge base..."):
            try:
                response = requests.post(f"{API_BASE_URL}/update-knowledge")
                if response.status_code == 200:
                    st.success("Knowledge base update started!")
                else:
                    st.error("Failed to start update")
            except:
                st.error("Connection error")
    
    # Статистика сессии
    if st.session_state.conversation_history:
        st.metric("Queries in Session", len(st.session_state.conversation_history))
        
        # Последние продукты
        recent_products = set()
        for conv in st.session_state.conversation_history[-5:]:
            for product in conv.get('infrastructure_context', {}).get('products', []):
                recent_products.add(product['name'])
        
        if recent_products:
            st.write("**Recent Products:**")
            for product in recent_products:
                st.write(f"• {product}")
    
    st.subheader("Quick Actions")
    
    quick_queries = [
        "Show Ceph cluster status",
        "List Kafka topics and partitions", 
        "Check Prometheus targets",
        "Grafana dashboard issues",
        "Kubernetes pod troubleshooting"
    ]
    
    for quick_query in quick_queries:
        if st.button(quick_query):
            # Автоматически заполняем поле запроса
            st.session_state.quick_query = quick_query
```

## 11. Требования к оборудованию и развертывание

### 11.1 Системные требования

**Минимальная конфигурация:**
- **CPU**: 8 ядер (Intel Xeon E5-2670 или эквивалент)
- **RAM**: 16GB DDR4
- **Диск**: 100GB SSD
- **ОС**: Ubuntu 20.04+ или CentOS 8+

**Рекомендуемая конфигурация:**
- **CPU**: 16 ядер (Intel Xeon Gold 6230 или AMD EPYC 7302)
- **RAM**: 32GB DDR4
- **Диск**: 200GB NVMe SSD
- **Сеть**: Gigabit Ethernet

**Распределение ресурсов по компонентам:**

| Компонент | CPU | RAM | Диск | Назначение |
|-----------|-----|-----|------|------------|
| LLM Service | 8 ядер | 12GB | 20GB | Инференс модели |
| RAG System | 4 ядра | 8GB | 50GB | Векторная БД |
| API Service | 2 ядра | 4GB | 10GB | FastAPI + логика |
| Web Interface | 2 ядра | 4GB | 10GB | Streamlit |
| Knowledge Base | - | 4GB | 100GB | Документация |

### 11.2 Развертывание в виртуальных машинах

**Архитектура развертывания:**

```
┌─────────────────────────────────────────────────────────────┐
│                    Load Balancer VM                         │
│                  (nginx, 2 CPU, 4GB RAM)                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  LLM VM     │ │  RAG VM     │ │  API VM     │
│ 8 CPU       │ │ 4 CPU       │ │ 4 CPU       │
│ 12GB RAM    │ │ 8GB RAM     │ │ 8GB RAM     │
│ 50GB Disk   │ │ 100GB Disk  │ │ 50GB Disk   │
└─────────────┘ └─────────────┘ └─────────────┘
```

### 11.3 Скрипт автоматического развертывания

```bash
#!/bin/bash
# deploy_infrastructure_llm.sh

set -e

echo "=== Infrastructure LLM Assistant Deployment ==="

# Проверка системных требований
check_requirements() {
    echo "Checking system requirements..."
    
    # Проверка CPU
    cpu_cores=$(nproc)
    if [ "$cpu_cores" -lt 8 ]; then
        echo "Warning: Minimum 8 CPU cores recommended, found $cpu_cores"
    fi
    
    # Проверка RAM
    ram_gb=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$ram_gb" -lt 16 ]; then
        echo "Warning: Minimum 16GB RAM recommended, found ${ram_gb}GB"
    fi
    
    # Проверка диска
    disk_space=$(df -BG / | awk 'NR==2{print $4}' | sed 's/G//')
    if [ "$disk_space" -lt 100 ]; then
        echo "Warning: Minimum 100GB free space recommended, found ${disk_space}GB"
    fi
}

# Установка зависимостей
install_dependencies() {
    echo "Installing dependencies..."
    
    # Обновление системы
    sudo apt update && sudo apt upgrade -y
    
    # Python и pip
    sudo apt install -y python3 python3-pip python3-venv
    
    # Системные библиотеки
    sudo apt install -y build-essential cmake pkg-config
    sudo apt install -y libopenblas-dev liblapack-dev gfortran
    
    # Git
    sudo apt install -y git
    
    # Docker (опционально)
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
}

# Создание виртуального окружения
setup_python_environment() {
    echo "Setting up Python environment..."
    
    python3 -m venv venv
    source venv/bin/activate
    
    # Обновление pip
    pip install --upgrade pip
    
    # Установка основных зависимостей
    pip install fastapi uvicorn streamlit
    pip install llama-cpp-python --force-reinstall --no-cache-dir
    pip install sentence-transformers chromadb
    pip install pandas pyyaml requests aiohttp
    pip install beautifulsoup4 stackapi
    pip install python-multipart
}

# Загрузка модели
download_model() {
    echo "Downloading LLM model..."
    
    mkdir -p models
    cd models
    
    # Llama 3.1 8B Instruct GGUF
    wget -c "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf" \
         -O "llama-3.1-8b-instruct.Q4_K_M.gguf"
    
    cd ..
}

# Создание структуры проекта
create_project_structure() {
    echo "Creating project structure..."
    
    mkdir -p {knowledge_base/products,knowledge_base/stackoverflow,knowledge_base/metadata}
    mkdir -p {vector_db,logs,config}
    mkdir -p scripts
    
    # Создание конфигурационных файлов
    cat >Загружает индекс версий продуктов"""
        index_path = os.path.join(self.base_path, "metadata", "version_index.json")
        if os.path.exists(index_path):
            with open(index_path, 'r') as f:
                return json.load(f)
        return {}
    
    def get_docs_for_version(self, product, version):
        """Получает документацию для конкретной версии продукта"""
        collection_name = f"{product}_{version.replace('.', '_')}"
        try:
            collection = self.vector_db.get_collection(collection_name)
            return collection
        except:
            return None
    
    def search_versioned_docs(self, query, product, version, n_results=5):
        """Поиск в документации конкретной версии"""
        collection = self.get_docs_for_version(product, version)
        if not collection:
            # Fallback на ближайшую версию
            collection = self._find_closest_version_docs(product, version)
        
        if collection:
            query_embedding = self.embeddings_model.encode([query])
            results = collection.query(
                query_embeddings=query_embedding.tolist(),
                n_results=n_results
            )
            return results
        return None
```

## 4. Система предварительной загрузки документации

### 4.1 Анализ версий в инфраструктуре

```python
class VersionAnalyzer:
    def __init__(self, versions_csv_path):
        self.versions_df = pd.read_csv(versions_csv_path)
        
    def get_unique_versions(self):
        """Извлекает уникальные версии всех продуктов"""
        versions_map = {}
        
        # Предполагаем структуру CSV:
        # server,product,version,os_version
        for _, row in self.versions_df.iterrows():
            product = row['product']
            version = row['version']
            
            if product not in versions_map:
                versions_map[product] = set()
            versions_map[product].add(version)
            
        # Конвертируем в список и сортируем
        for product in versions_map:
            versions_map[product] = sorted(list(versions_map[product]))
            
        return versions_map
    
    def get_server_stack(self, server_name):
        """Получает полный стек ПО для конкретного сервера"""
        server_data = self.versions_df[
            self.versions_df['server'] == server_name
        ]
        return server_data.to_dict('records')
```

### 4.2 Система загрузки документации

```python
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import time
from urllib.parse import urljoin, urlparse

class DocumentationScraper:
    def __init__(self):
        self.session = None
        self.rate_limit = 1  # секунд между запросами
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={'User-Agent': 'Infrastructure-LLM-Bot/1.0'}
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def scrape_product_versions(self, product_config, versions):
        """Загружает документацию для всех версий продукта"""
        all_docs = []
        
        for version in versions:
            print(f"Scraping {product_config['name']} v{version}...")
            version_docs = await self._scrape_version_docs(
                product_config, version
            )
            
            for doc in version_docs:
                doc['version'] = version
                doc['product'] = product_config['name']
                
            all_docs.extend(version_docs)
            await asyncio.sleep(self.rate_limit)
            
        return all_docs
    
    async def _scrape_version_docs(self, config, version):
        """Загружает документацию для конкретной версии"""
        docs = []
        base_url = config['url_template'].format(version=version)
        
        for section in config['sections']:
            section_url = urljoin(base_url, section['path'])
            
            try:
                async with self.session.get(section_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        soup = BeautifulSoup(content, 'html.parser')
                        
                        # Очистка контента
                        text = self._clean_html_content(soup)
                        
                        docs.append({
                            'section': section['name'],
                            'url': section_url,
                            'content': text,
                            'scraped_at': time.time()
                        })
                        
            except Exception as e:
                print(f"Error scraping {section_url}: {e}")
                
        return docs
    
    def _clean_html_content(self, soup):
        """Очистка HTML контента"""
        # Удаляем скрипты, стили, навигацию
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()
            
        # Извлекаем текст
        text = soup.get_text()
        
        # Очистка текста
        lines = [line.strip() for line in text.splitlines()]
        text = '\n'.join([line for line in lines if line])
        
        return text

# Конфигурация для различных продуктов
PRODUCT_CONFIGS = {
    'ceph': {
        'name': 'ceph',
        'url_template': 'https://docs.ceph.com/en/{version}',
        'sections': [
            {'name': 'installation', 'path': 'install/'},
            {'name': 'configuration', 'path': 'rados/configuration/'},
            {'name': 'troubleshooting', 'path': 'troubleshooting/'},
            {'name': 'cephadm', 'path': 'cephadm/'},
            {'name': 'monitoring', 'path': 'mgr/'}
        ]
    },
    'kafka': {
        'name': 'kafka',
        'url_template': 'https://kafka.apache.org/{version}/documentation.html',
        'sections': [
            {'name': 'quickstart', 'path': '#quickstart'},
            {'name': 'configuration', 'path': '#configuration'},
            {'name': 'operations', 'path': '#operations'},
            {'name': 'security', 'path': '#security'},
            {'name': 'connect', 'path': '#connect'}
        ]
    },
    'prometheus': {
        'name': 'prometheus',
        'url_template': 'https://prometheus.io/docs/prometheus/{version}',
        'sections': [
            {'name': 'installation', 'path': 'installation/'},
            {'name': 'configuration', 'path': 'configuration/'},
            {'name': 'querying', 'path': 'querying/'},
            {'name': 'alerting', 'path': 'alerting/'}
        ]
    },
    'kubernetes': {
        'name': 'kubernetes',
        'url_template': 'https://kubernetes.io/docs/concepts/',
        'version_path_map': {
            # Kubernetes использует другую структуру URL
            'default': 'https://kubernetes.io/docs'
        },
        'sections': [
            {'name': 'concepts', 'path': 'concepts/'},
            {'name': 'tasks', 'path': 'tasks/'},
            {'name': 'troubleshooting', 'path': 'tasks/debug-application-cluster/'},
            {'name': 'reference', 'path': 'reference/'}
        ]
    }
}
```

### 4.3 Загрузка StackOverflow данных

```python
import stackapi
from datetime import datetime, timedelta

class StackOverflowVersionedScraper:
    def __init__(self):
        self.so = stackapi.StackAPI('stackoverflow')
        
    def scrape_by_product_versions(self, product_versions_map):
        """Загружает вопросы/ответы с SO для каждого продукта"""
        all_questions = {}
        
        for product, versions in product_versions_map.items():
            print(f"Scraping StackOverflow for {product}...")
            
            # Общие вопросы по продукту
            general_questions = self._get_questions_by_tag(product)
            
            # Вопросы для конкретных версий
            version_specific = {}
            for version in versions:
                version_questions = self._get_version_specific_questions(
                    product, version
                )
                if version_questions:
                    version_specific[version] = version_questions
                    
            all_questions[product] = {
                'general': general_questions,
                'version_specific': version_specific
            }
            
            time.sleep(2)  # Rate limiting
            
        return all_questions
    
    def _get_questions_by_tag(self, tag, max_questions=500):
        """Получает вопросы по тегу"""
        try:
            questions = self.so.fetch('questions',
                                    tagged=tag,
                                    sort='votes',
                                    order='desc',
                                    pagesize=100,
                                    max_pages=max_questions//100,
                                    filter='withbody')
            
            result = []
            for question in questions['items']:
                # Получаем ответы
                answers = self.so.fetch('answers',
                                      ids=[question['question_id']],
                                      sort='votes',
                                      order='desc',
                                      filter='withbody')
                
                result.append({
                    'title': question['title'],
                    'question': question.get('body', ''),
                    'answers': [
                        {
                            'body': a.get('body', ''),
                            'score': a.get('score', 0),
                            'accepted': a.get('is_accepted', False)
                        }
                        for a in answers.get('items', [])
                    ],
                    'tags': question['tags'],
                    'score': question['score'],
                    'creation_date': question['creation_date']
                })
                
            return result
            
        except Exception as e:
            print(f"Error fetching questions for {tag}: {e}")
            return []
            
    def _get_version_specific_questions(self, product, version):
        """Поиск вопросов для конкретной версии"""
        # Пробуем различные варианты поиска версии
        search_terms = [
            f"{product} {version}",
            f"{product}-{version}",
            f"{product} version {version}"
        ]
        
        all_results = []
        for term in search_terms:
            try:
                results = self.so.fetch('search/advanced',
                                      q=term,
                                      tagged=product,
                                      sort='votes',
                                      order='desc',
                                      pagesize=50)
                
                if results.get('items'):
                    all_results.extend(results['items'])
                    
            except Exception as e:
                print(f"Error searching for {term}: {e}")
                
        return all_results[:100]  # Ограничиваем количество
```

## 5. Система обновления знаний

### 5.1 Мониторинг изменений в инфраструктуре

```python
import hashlib
from datetime import datetime

class InfrastructureMonitor:
    def __init__(self, versions_csv_path, inventory_path):
        self.versions_csv_path = versions_csv_path
        self.inventory_path = inventory_path
        self.last_checksums = self._calculate_checksums()
        
    def _calculate_checksums(self):
        """Вычисляет контрольные суммы файлов"""
        checksums = {}
        
        for file_path in [self.versions_csv_path, self.inventory_path]:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    checksums[file_path] = hashlib.md5(f.read()).hexdigest()
                    
        return checksums
    
    def check_for_changes(self):
        """Проверяет изменения в файлах конфигурации"""
        current_checksums = self._calculate_checksums()
        changes = {}
        
        for file_path, current_checksum in current_checksums.items():
            old_checksum = self.last_checksums.get(file_path)
            if old_checksum != current_checksum:
                changes[file_path] = {
                    'old_checksum': old_checksum,
                    'new_checksum': current_checksum,
                    'changed_at': datetime.now()
                }
                
        if changes:
            self.last_checksums = current_checksums
            
        return changes
    
    def get_new_versions(self, old_versions_map):
        """Определяет новые версии продуктов"""
        current_analyzer = VersionAnalyzer(self.versions_csv_path)
        current_versions = current_analyzer.get_unique_versions()
        
        new_versions = {}
        for product, versions in current_versions.items():
            old_product_versions = set(old_versions_map.get(product, []))
            current_product_versions = set(versions)
            
            new_product_versions = current_product_versions - old_product_versions
            if new_product_versions:
                new_versions[product] = list(new_product_versions)
                
        return new_versions

class KnowledgeUpdater:
    def __init__(self, knowledge_manager, scraper):
        self.knowledge_manager = knowledge_manager
        self.scraper = scraper
        
    async def update_for_new_versions(self, new_versions_map):
        """Обновляет знания для новых версий"""
        for product, versions in new_versions_map.items():
            if product in PRODUCT_CONFIGS:
                config = PRODUCT_CONFIGS[product]
                
                print(f"Updating documentation for {product} versions: {versions}")
                
                # Загружаем документацию для новых версий
                new_docs = await self.scraper.scrape_product_versions(
                    config, versions
                )
                
                # Добавляем в базу знаний
                await self.knowledge_manager.add_versioned_docs(
                    product, new_docs
                )
                
                # Обновляем StackOverflow данные
                await self._update_stackoverflow_data(product, versions)
                
    async def _update_stackoverflow_data(self, product, versions):
        """Обновляет данные StackOverflow для новых версий"""
        so_scraper = StackOverflowVersionedScraper()
        
        for version in versions:
            version_questions = so_scraper._get_version_specific_questions(
                product, version
            )
            
            if version_questions:
                await self.knowledge_manager.add_stackoverflow_data(
                    product, version, version_questions
                )
```

## 6. Контекстный движок

### 6.1 Управление сессиями и контекстом

```python
import uuid
from typing import Dict, List, Any

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        self.max_context_length = 10  # Максимум сообщений в контексте
        
    def create_session(self) -> str:
        """Создает новую сессию"""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            'created_at': datetime.now(),
            'context': [],
            'infrastructure_context': {},
            'last_activity': datetime.now()
        }
        return session_id
    
    def add_to_context(self, session_id: str, query: str, response: str, 
                      infrastructure_context: Dict):
        """Добавляет запрос и ответ в контекст сессии"""
        if session_id not in self.sessions:
            session_id = self.create_session()
            
        session = self.sessions[session_id]
        session['context'].append({
            'timestamp': datetime.now(),
            'query': query,
            'response': response,
            'infrastructure_context': infrastructure_context
        })
        
        # Ограничиваем размер контекста
        if len(session['context']) > self.max_context_length:
            session['context'] = session['context'][-self.max_context_length:]
            
        session['last_activity'] = datetime.now()
        
    def get_session_context(self, session_id: str) -> List[Dict]:
        """Получает контекст сессии"""
        return self.sessions.get(session_id, {}).get('context', [])
        
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Очищает старые сессии"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        sessions_to_remove = [
            sid for sid, session in self.sessions.items()
            if session['last_activity'] < cutoff_time
        ]
        
        for sid in sessions_to_remove:
            del self.sessions[sid]

class InfrastructureContextEngine:
    def __init__(self, inventory_path, versions_csv_path):
        self.inventory_parser = AnsibleInventoryParser(inventory_path)
        self.version_analyzer = VersionAnalyzer(versions_csv_path)
        
    def get_context_for_query(self, query: str, session_context: List[Dict] = None):
        """Определяет релевантный контекст инфраструктуры для запроса"""
        context = {
            'servers': [],
            'products': [],
            'versions': {},
            'related_infrastructure': []
        }
        
        # Анализируем запрос на упоминание серверов/продуктов
        mentioned_servers = self._extract_server_names(query)
        mentioned_products = self._extract_product_names(query)
        
        # Если серверы упомянуты явно
        if mentioned_servers:
            for server in mentioned_servers:
                server_info = self.inventory_parser.get_server_info(server)
                server_versions = self.version_analyzer.get_server_stack(server)
                
                context['servers'].append({
                    'name': server,
                    'info': server_info,
                    'software_stack': server_versions
                })
                
        # Если упомянуты продукты
        if mentioned_products:
            for product in mentioned_products:
                product_servers = self.inventory_parser.get_servers_by_product(product)
                product_versions = self._get_product_versions(product)
                
                context['products'].append({
                    'name': product,
                    'servers': product_servers,
                    'versions': product_versions
                })
                
        # Используем контекст сессии для дополнительной информации
        if session_context:
            previous_context = self._extract_session_infrastructure_context(
                session_context
            )
            context['related_infrastructure'].extend(previous_context)
            
        return context
    
    def _extract_server_names(self, query: str) -> List[str]:
        """Извлекает имена серверов из запроса"""
        # Получаем все известные имена серверов
        known_servers = self.inventory_parser.get_all_server_names()
        
        mentioned = []
        query_lower = query.lower()
        
        for server in known_servers:
            if server.lower() in query_lower:
                mentioned.append(server)
                
        return mentioned
    
    def _extract_product_names(self, query: str) -> List[str]:
        """Извлекает названия продуктов из запроса"""
        known_products = ['ceph', 'kafka', 'prometheus', 'grafana', 
                         'opensearch', 'nginx', 'kubernetes']
        
        mentioned = []
        query_lower = query.lower()
        
        for product in known_products:
            if product in query_lower:
                mentioned.append(product)
                
        return mentioned

class AnsibleInventoryParser:
    def __init__(self, inventory_path):
        self.inventory_path = inventory_path
        self.inventory = self._load_inventory()
        
    def _load_inventory(self):
        """Загружает Ansible inventory"""
        if self.inventory_path.endswith('.yml') or self.inventory_path.endswith('.yaml'):
            with open(self.inventory_path, 'r') as f:
                return yaml.safe_load(f)
        else:
            # Парсинг INI формата
            import configparser
            config = configparser.ConfigParser(allow_no_value=True)
            config.read(self.inventory_path)
            return dict(config)
    
    def get_server_info(self, server_name: str) -> Dict:
        """Получает информацию о сервере из inventory"""
        # Логика зависит от формата inventory
        # Пример для YAML формата
        for group_name, group_data in self.inventory.get('all', {}).get('children', {}).items():
            if 'hosts' in group_data:
                if server_name in group_data['hosts']:
                    return {
                        'group': group_name,
                        'host_vars': group_data['hosts'][server_name],
                        'group_vars': group_data.get('vars', {})
                    }
        return {}
    
    def get_servers_by_product(self, product: str) -> List[str]:
        """Получает список серверов, на которых установлен продукт"""
        servers = []
        
        # Ищем группы, связанные с продуктом
        for group_name, group_data in self.inventory.get('all', {}).get('children', {}).items():
            if product.lower() in group_name.lower():
                if 'hosts' in group_data:
                    servers.extend(group_data['hosts'].keys())
                    
        return servers
    
    def get_all_server_names(self) -> List[str]:
        """Получает все имена серверов из inventory"""
        servers = []
        
        for group_name, group_data in self.inventory.get('all', {}).get('children', {}).items():
            if 'hosts' in group_data:
                servers.extend(group_data['hosts'].keys())
                
        return list(set(servers))  # Убираем дубликаты
```

## 7. Система обратной связи и обучения

### 7.1 Сбор и анализ обратной связи

```python
import sqlite3
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime

@dataclass
class FeedbackEntry:
    query: str
    response: str
    rating: int  # 1-5
    feedback_text: str
    context: Dict
    timestamp: datetime
    session_id: str

class FeedbackSystem:
    def __init__(self, db_path: str = "./feedback.db"):
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        """Инициализирует базу данных для обратной связи"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                query TEXT NOT NULL,
                response TEXT NOT NULL,
                rating INTEGER NOT NULL,
                feedback_text TEXT,
                context_json TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed BOOLEAN DEFAULT FALSE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT,
                pattern_description TEXT,
                correction_rule TEXT,
                confidence REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def store_feedback(self, feedback: FeedbackEntry):
        """Сохраняет обратную связь"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO feedback 
            (session_id, query, response, rating, feedback_text, context_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            feedback.session_id,
            feedback.query,
            feedback.response, 
            feedback.rating,
            feedback.feedback_text,
            json.dumps(feedback.context),
            feedback.timestamp
        ))
        
        conn.commit()
        conn.close()
        
    def get_negative_feedback(self, min_rating: int = 2) -> List[Dict]:
        """Получает негативную обратную связь для анализа"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM feedback 
            WHERE rating <= ? AND processed = FALSE
            ORDER BY timestamp DESC
        ''', (min_rating,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(zip([col[0] for col in cursor.description], row)) for row in rows]
        
    def analyze_feedback_patterns(self):
        """Анализирует паттерны в обратной связи"""
        negative_feedback = self.get_negative_feedback()
        
        patterns = {
            'incorrect_commands': [],
            'wrong_versions': [],
            'missing_context': [],
            'configuration_errors': []
        }
        
        for feedback in negative_feedback:
            # Анализируем типы ошибок
            feedback_text = feedback['feedback_text'].lower()
            
            if any(word in feedback_text for word in ['command', 'script', 'wrong']):
                patterns['incorrect_commands'].append(feedback)
            elif any(word in feedback_text for word in ['version', 'outdated']):
                patterns['wrong_versions'].append(feedback)
            elif any(word in feedback_text for word in ['context', 'server', 'missing']):
                patterns['missing_context'].append(feedback)
            elif any(word in feedback_text for word in ['config', 'parameter']):
                patterns['configuration_errors'].append(feedback)
                
        return patterns
        
    def create_learning_rules(self, patterns: Dict):
        """Создает правила обучения на основе паттернов"""
        rules = []
        
        # Правила для неправильных команд
        if patterns['incorrect_commands']:
            rules.append({
                'type': 'command_validation',
                'description': 'Validate commands against infrastructure context',
                'action': 'cross_reference_with_inventory'
            })
            
        # Правила для неправильных версий
        if patterns['wrong_versions']:
            rules.append({
                'type': 'version_matching',
                'description': 'Always use exact version from infrastructure',
                'action': 'strict_version_lookup'
            })
            
        return rules

class LearningEngine:
    def __init__(self, feedback_system: FeedbackSystem, knowledge_manager):
        self.feedback_system = feedback_system
        self.knowledge_manager = knowledge_manager
        self.learning_rules = []
        
    def process_feedback(self):
        """Обрабатывает накопленную обратную связь"""
        patterns = self.feedback_system.analyze_feedback_patterns()
        new_rules = self.feedback_system.create_learning_rules(patterns)
        
        self.learning_rules.extend(new_rules)
        
        # Обновляем промпты на основе правил
        self._update_system_prompts()
        
    def _update_system_prompts(self):
        """Обновляет системные промпты на основе правил обучения"""
        base_prompt = self._get_base_system_prompt()
        
        # Добавляем правила из обратной связи
        learning_additions = []
        
        for rule in self.learning_rules:
            if rule['type'] == 'command_validation':
                learning_additions.append(
                    "CRITICAL: Always cross-reference generated commands with the actual infrastructure inventory before providing them."
                )
            elif rule['type'] == 'version_matching':
                learning_additions.append(
                    "CRITICAL: Use ONLY the exact software versions specified in the infrastructure version database."
                )
                
        if learning_additions:
            updated_prompt = base_prompt + "\n\nLEARNING RULES:\n" + "\n".join(learning_additions)
            return updated_prompt
            
        return base_prompt
    
    def _get_base_system_prompt(self):
        return """
You are an expert infrastructure management assistant with deep knowledge of open-source technologies.

CORE PRINCIPLES:
1. Always use the specific versions of software deployed in the infrastructure
2. Reference the exact server configurations from the Ansible inventory
3. Provide commands and scripts specific to the actual environment
4. Explain potential risks and prerequisites for any suggested actions
5. When analyzing logs, consider the specific product versions and configurations

INFRASTRUCTURE CONTEXT USAGE:
- Server information comes from Ansible inventory
- Software versions come from the versions database
- Always match documentation to the deployed versions
- Consider dependencies between different components
"""