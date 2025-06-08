# Система векторного поиска для технической документации

## 1. Архитектура системы векторного поиска

### 1.1 Общая схема компонентов

```
┌─────────────────────────────────────────────────────────────┐
│                    Vector Search System                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │  Text Processor │  │  Embedding      │  │  Vector      │ │
│  │  & Chunker      │  │  Generator      │  │  Database    │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│           │                     │                   │       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │  Metadata       │  │  Query          │  │  Search      │ │
│  │  Manager        │  │  Processor      │  │  Engine      │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Выбор embedding модели

Для CPU-only инфраструктуры рекомендуются следующие модели:

```python
# Варианты embedding моделей по приоритету:

# 1. Многоязычная (русский + английский)
MODEL_MULTILINGUAL = "paraphrase-multilingual-MiniLM-L12-v2"
# Размер: 470MB, Языки: 50+, Производительность: отличная

# 2. Специализированная для кода
MODEL_CODE = "microsoft/codebert-base"
# Размер: 500MB, Специализация: код и техническая документация

# 3. Универсальная английская (высокое качество)
MODEL_ENGLISH = "all-MiniLM-L6-v2"
# Размер: 90MB, Скорость: высокая, Качество: хорошее

# 4. Русскоязычная
MODEL_RUSSIAN = "cointegrated/rubert-tiny2"
# Размер: 111MB, Специализация: русский язык
```

## 2. Детальная реализация компонентов

### 2.1 Продвинутый Text Processor & Chunker

```python
import re
import spacy
from typing import List, Dict, Tuple
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
import tiktoken

@dataclass
class DocumentChunk:
    text: str
    metadata: Dict
    chunk_id: str
    product: str
    version: str
    section: str
    subsection: str
    doc_type: str  # 'official_doc', 'stackoverflow', 'troubleshooting'
    language: str
    code_blocks: List[str]
    commands: List[str]
    error_patterns: List[str]

class AdvancedTextProcessor:
    def __init__(self):
        # Загружаем языковые модели
        try:
            self.nlp_en = spacy.load("en_core_web_sm")
            self.nlp_ru = spacy.load("ru_core_news_sm")
        except OSError:
            print("Downloading spacy models...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
            subprocess.run(["python", "-m", "spacy", "download", "ru_core_news_sm"])
            self.nlp_en = spacy.load("en_core_web_sm")
            self.nlp_ru = spacy.load("ru_core_news_sm")
        
        # Паттерны для извлечения технической информации
        self.code_patterns = [
            r'```[\s\S]*?```',  # Markdown code blocks
            r'`[^`\n]+`',       # Inline code
            r'^\s*\$\s+.+$',    # Shell commands
            r'^\s*#\s+.+$',     # Comments
        ]
        
        self.error_patterns = [
            r'Error:\s+(.+)',
            r'Exception:\s+(.+)',
            r'Failed:\s+(.+)',
            r'ERROR\s+(.+)',
            r'\[ERROR\]\s+(.+)',
        ]
        
        self.command_patterns = [
            r'sudo\s+\S+.*',
            r'systemctl\s+\S+.*',
            r'kubectl\s+\S+.*',
            r'docker\s+\S+.*',
            r'ansible\s+\S+.*',
        ]
        
        # Токенизатор для подсчета токенов
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def detect_language(self, text: str) -> str:
        """Определение языка текста"""
        # Простая эвристика на основе символов
        cyrillic_chars = len(re.findall(r'[а-яё]', text.lower()))
        latin_chars = len(re.findall(r'[a-z]', text.lower()))
        
        if cyrillic_chars > latin_chars:
            return 'ru'
        else:
            return 'en'
    
    def extract_code_blocks(self, text: str) -> List[str]:
        """Извлечение блоков кода"""
        code_blocks = []
        for pattern in self.code_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            code_blocks.extend(matches)
        return code_blocks
    
    def extract_commands(self, text: str) -> List[str]:
        """Извлечение команд"""
        commands = []
        for pattern in self.command_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            commands.extend(matches)
        return commands
    
    def extract_errors(self, text: str) -> List[str]:
        """Извлечение ошибок"""
        errors = []
        for pattern in self.error_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            errors.extend(matches)
        return errors
    
    def smart_chunk_text(self, text: str, max_tokens: int = 512, 
                        overlap_tokens: int = 50) -> List[str]:
        """Умное разбиение текста на чанки"""
        
        # Разбиваем по заголовкам и параграфам
        paragraphs = self.split_by_structure(text)
        
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for paragraph in paragraphs:
            paragraph_tokens = len(self.tokenizer.encode(paragraph))
            
            # Если параграф слишком большой, разбиваем по предложениям
            if paragraph_tokens > max_tokens:
                sentences = self.split_by_sentences(paragraph)
                for sentence in sentences:
                    sentence_tokens = len(self.tokenizer.encode(sentence))
                    
                    if current_tokens + sentence_tokens > max_tokens:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            # Добавляем overlap
                            overlap_text = self.get_overlap_text(current_chunk, overlap_tokens)
                            current_chunk = overlap_text + " " + sentence
                            current_tokens = len(self.tokenizer.encode(current_chunk))
                        else:
                            current_chunk = sentence
                            current_tokens = sentence_tokens
                    else:
                        current_chunk += " " + sentence
                        current_tokens += sentence_tokens
            else:
                if current_tokens + paragraph_tokens > max_tokens:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        overlap_text = self.get_overlap_text(current_chunk, overlap_tokens)
                        current_chunk = overlap_text + " " + paragraph
                        current_tokens = len(self.tokenizer.encode(current_chunk))
                    else:
                        current_chunk = paragraph
                        current_tokens = paragraph_tokens
                else:
                    current_chunk += " " + paragraph
                    current_tokens += paragraph_tokens
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def split_by_structure(self, text: str) -> List[str]:
        """Разбиение по структурным элементам"""
        # Разбиваем по заголовкам Markdown
        sections = re.split(r'\n#+\s+', text)
        
        paragraphs = []
        for section in sections:
            # Разбиваем каждую секцию по параграфам
            section_paragraphs = re.split(r'\n\s*\n', section)
            paragraphs.extend([p.strip() for p in section_paragraphs if p.strip()])
        
        return paragraphs
    
    def split_by_sentences(self, text: str) -> List[str]:
        """Разбиение по предложениям с учетом языка"""
        language = self.detect_language(text)
        
        if language == 'ru':
            doc = self.nlp_ru(text)
        else:
            doc = self.nlp_en(text)
        
        sentences = [sent.text.strip() for sent in doc.sents]
        return sentences
    
    def get_overlap_text(self, text: str, overlap_tokens: int) -> str:
        """Получение текста для overlap между чанками"""
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= overlap_tokens:
            return text
        
        overlap_tokens_list = tokens[-overlap_tokens:]
        overlap_text = self.tokenizer.decode(overlap_tokens_list)
        return overlap_text
    
    def process_document(self, text: str, metadata: Dict) -> List[DocumentChunk]:
        """Обработка документа и создание чанков"""
        
        # Определяем язык
        language = self.detect_language(text)
        
        # Извлекаем техническую информацию
        code_blocks = self.extract_code_blocks(text)
        commands = self.extract_commands(text)
        errors = self.extract_errors(text)
        
        # Разбиваем на чанки
        chunks = self.smart_chunk_text(text)
        
        # Создаем объекты DocumentChunk
        document_chunks = []
        for i, chunk_text in enumerate(chunks):
            chunk = DocumentChunk(
                text=chunk_text,
                metadata=metadata,
                chunk_id=f"{metadata.get('doc_id', 'unknown')}_{i}",
                product=metadata.get('product', 'unknown'),
                version=metadata.get('version', 'unknown'),
                section=metadata.get('section', 'unknown'),
                subsection=metadata.get('subsection', ''),
                doc_type=metadata.get('doc_type', 'official_doc'),
                language=language,
                code_blocks=[cb for cb in code_blocks if cb in chunk_text],
                commands=[cmd for cmd in commands if cmd in chunk_text],
                error_patterns=[err for err in errors if err in chunk_text]
            )
            document_chunks.append(chunk)
        
        return document_chunks
```

### 2.2 Продвинутый Embedding Generator

```python
import numpy as np
from sentence_transformers import SentenceTransformer
import torch
from typing import List, Dict
import logging

class MultiModalEmbeddingGenerator:
    def __init__(self, models_config: Dict):
        self.models = {}
        self.weights = {}
        
        # Загружаем multiple embedding models
        for model_name, config in models_config.items():
            try:
                self.models[model_name] = SentenceTransformer(config['model_path'])
                self.weights[model_name] = config.get('weight', 1.0)
            except Exception as e:
                logging.error(f"Failed to load model {model_name}: {e}")
        
        # Кэш для embeddings
        self.embedding_cache = {}
        
    def generate_embedding(self, chunk: DocumentChunk) -> np.ndarray:
        """Генерация embedding для чанка документа"""
        
        # Подготавливаем текст для embedding
        processed_text = self.prepare_text_for_embedding(chunk)
        
        # Проверяем кэш
        cache_key = hash(processed_text)
        if cache_key in self.embedding_cache:
            return self.embedding_cache[cache_key]
        
        # Генерируем embeddings с помощью разных моделей
        embeddings = []
        
        for model_name, model in self.models.items():
            try:
                embedding = model.encode(processed_text, convert_to_tensor=False)
                embeddings.append(embedding * self.weights[model_name])
            except Exception as e:
                logging.error(f"Error generating embedding with {model_name}: {e}")
                continue
        
        if not embeddings:
            raise ValueError("No embeddings generated")
        
        # Комбинируем embeddings (weighted average)
        final_embedding = np.mean(embeddings, axis=0)
        
        # Нормализуем
        final_embedding = final_embedding / np.linalg.norm(final_embedding)
        
        # Кэшируем
        self.embedding_cache[cache_key] = final_embedding
        
        return final_embedding
    
    def prepare_text_for_embedding(self, chunk: DocumentChunk) -> str:
        """Подготовка текста для создания embedding"""
        
        # Базовый текст
        text_parts = [chunk.text]
        
        # Добавляем контекстную информацию
        context_parts = [
            f"Product: {chunk.product}",
            f"Version: {chunk.version}",
            f"Section: {chunk.section}",
            f"Type: {chunk.doc_type}"
        ]
        
        # Добавляем команды (они важны для поиска)
        if chunk.commands:
            context_parts.append("Commands: " + " ".join(chunk.commands[:3]))
        
        # Добавляем ошибки (важны для troubleshooting)
        if chunk.error_patterns:
            context_parts.append("Errors: " + " ".join(chunk.error_patterns[:2]))
        
        # Объединяем все части
        full_text = " ".join(text_parts + context_parts)
        
        return full_text
    
    def generate_query_embedding(self, query: str, context: Dict = None) -> np.ndarray:
        """Генерация embedding для поискового запроса"""
        
        # Расширяем запрос контекстом
        if context:
            query_parts = [query]
            
            # Добавляем контекст продуктов
            if 'products' in context:
                products = " ".join(context['products'])
                query_parts.append(f"Products: {products}")
            
            # Добавляем контекст версий
            if 'versions' in context:
                versions = " ".join(context['versions'])
                query_parts.append(f"Versions: {versions}")
            
            enhanced_query = " ".join(query_parts)
        else:
            enhanced_query = query
        
        # Генерируем embedding
        embeddings = []
        for model_name, model in self.models.items():
            try:
                embedding = model.encode(enhanced_query, convert_to_tensor=False)
                embeddings.append(embedding * self.weights[model_name])
            except Exception as e:
                logging.error(f"Error generating query embedding with {model_name}: {e}")
                continue
        
        if not embeddings:
            raise ValueError("No embeddings generated for query")
        
        final_embedding = np.mean(embeddings, axis=0)
        final_embedding = final_embedding / np.linalg.norm(final_embedding)
        
        return final_embedding
```

### 2.3 Продвинутая Vector Database

```python
import faiss
import pickle
import sqlite3
import json
from typing import List, Dict, Tuple, Optional
import numpy as np
from datetime import datetime
import threading

class AdvancedVectorDatabase:
    def __init__(self, db_path: str, embedding_dim: int = 384):
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        
        # FAISS индексы для разных типов контента
        self.indexes = {
            'documentation': None,
            'troubleshooting': None,
            'code_examples': None,
            'stackoverflow': None
        }
        
        # Метаданные chunks
        self.metadata_db = sqlite3.connect(f"{db_path}/metadata.db", check_same_thread=False)
        self.metadata_lock = threading.Lock()
        
        # Инициализация
        self.initialize_database()
        self.load_indexes()
    
    def initialize_database(self):
        """Инициализация БД метаданных"""
        with self.metadata_lock:
            cursor = self.metadata_db.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id TEXT UNIQUE,
                    product TEXT,
                    version TEXT,
                    section TEXT,
                    subsection TEXT,
                    doc_type TEXT,
                    language TEXT,
                    text TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT,
                    results_count INTEGER,
                    avg_similarity REAL,
                    execution_time REAL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_product_version 
                ON chunks(product, version)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_doc_type 
                ON chunks(doc_type)
            """)
            
            self.metadata_db.commit()
    
    def create_index(self, index_type: str, dimension: int):
        """Создание FAISS индекса"""
        if index_type in ['documentation', 'troubleshooting']:
            # Для документации используем более точный поиск
            index = faiss.IndexHNSWFlat(dimension, 32)
            index.hnsw.efConstruction = 200
            index.hnsw.efSearch = 128
        else:
            # Для code и stackoverflow используем быстрый поиск
            index = faiss.IndexFlatIP(dimension)
        
        return index
    
    def add_chunks(self, chunks: List[DocumentChunk], embeddings: List[np.ndarray]):
        """Добавление chunks в индекс"""
        
        # Группируем по типу документа
        grouped_chunks = {}
        grouped_embeddings = {}
        
        for chunk, embedding in zip(chunks, embeddings):
            doc_type = chunk.doc_type
            if doc_type not in grouped_chunks:
                grouped_chunks[doc_type] = []
                grouped_embeddings[doc_type] = []
            
            grouped_chunks[doc_type].append(chunk)
            grouped_embeddings[doc_type].append(embedding)
        
        # Добавляем в соответствующие индексы
        for doc_type, type_chunks in grouped_chunks.items():
            if doc_type not in self.indexes:
                continue
                
            type_embeddings = np.array(grouped_embeddings[doc_type]).astype('float32')
            
            # Создаем индекс если не существует
            if self.indexes[doc_type] is None:
                self.indexes[doc_type] = self.create_index(doc_type, self.embedding_dim)
            
            # Добавляем embeddings
            start_id = self.indexes[doc_type].ntotal
            self.indexes[doc_type].add(type_embeddings)
            
            # Сохраняем метаданные
            self.save_chunks_metadata(type_chunks, start_id)
    
    def save_chunks_metadata(self, chunks: List[DocumentChunk], start_id: int):
        """Сохранение метаданных chunks"""
        with self.metadata_lock:
            cursor = self.metadata_db.cursor()
            
            for i, chunk in enumerate(chunks):
                cursor.execute("""
                    INSERT OR REPLACE INTO chunks 
                    (chunk_id, product, version, section, subsection, doc_type, 
                     language, text, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chunk.chunk_id,
                    chunk.product,
                    chunk.version,
                    chunk.section,
                    chunk.subsection,
                    chunk.doc_type,
                    chunk.language,
                    chunk.text,
                    json.dumps(chunk.metadata),
                    datetime.now()
                ))
            
            self.metadata_db.commit()
    
    def hybrid_search(self, query_embedding: np.ndarray, query_text: str,
                     filters: Dict = None, top_k: int = 10) -> List[Dict]:
        """Гибридный поиск с фильтрацией"""
        
        start_time = datetime.now()
        all_results = []
        
        # Поиск по всем индексам
        for index_type, index in self.indexes.items():
            if index is None or index.ntotal == 0:
                continue
            
            # Векторный поиск
            k = min(top_k * 2, index.ntotal)  # Берем больше для фильтрации
            similarities, indices = index.search(
                query_embedding.reshape(1, -1).astype('float32'), k
            )
            
            # Получаем метаданные
            for i, (similarity, idx) in enumerate(zip(similarities[0], indices[0])):
                if idx == -1:  # FAISS возвращает -1 для несуществующих
                    continue
                
                metadata = self.get_chunk_metadata_by_index(idx, index_type)
                if metadata and self.apply_filters(metadata, filters):
                    
                    # Вычисляем гибридный score
                    hybrid_score = self.calculate_hybrid_score(
                        similarity, metadata, query_text, index_type
                    )
                    
                    result = {
                        'chunk_id': metadata['chunk_id'],
                        'text': metadata['text'],
                        'product': metadata['product'],
                        'version': metadata['version'],
                        'section': metadata['section'],
                        'doc_type': metadata['doc_type'],
                        'vector_similarity': float(similarity),
                        'hybrid_score': hybrid_score,
                        'index_type': index_type
                    }
                    
                    all_results.append(result)
        
        # Сортируем по гибридному score
        all_results.sort(key=lambda x: x['hybrid_score'], reverse=True)
        
        # Убираем дубликаты
        unique_results = self.remove_duplicates(all_results)
        
        # Логируем статистику
        execution_time = (datetime.now() - start_time).total_seconds()
        self.log_search_stats(query_text, len(unique_results), 
                             np.mean([r['vector_similarity'] for r in unique_results[:top_k]]),
                             execution_time)
        
        return unique_results[:top_k]
    
    def calculate_hybrid_score(self, vector_similarity: float, metadata: Dict, 
                              query_text: str, index_type: str) -> float:
        """Вычисление гибридного score"""
        
        # Базовый score от векторного поиска
        score = vector_similarity
        
        # Бонус за точное совпадение терминов
        text_lower = metadata['text'].lower()
        query_lower = query_text.lower()
        
        # Проверяем точные совпадения ключевых слов
        query_words = set(query_lower.split())
        text_words = set(text_lower.split())
        
        # Jaccard similarity для текста
        intersection = len(query_words.intersection(text_words))
        union = len(query_words.union(text_words))
        jaccard_score = intersection / union if union > 0 else 0
        
        # BM25-подобный бонус
        tf_bonus = intersection / len(text_words) if len(text_words) > 0 else 0
        
        # Бонусы за тип документа
        doc_type_bonus = {
            'troubleshooting': 0.2,  # Troubleshooting важнее
            'code_examples': 0.15,
            'documentation': 0.1,
            'stackoverflow': 0.05
        }.get(index_type, 0)
        
        # Финальный score
        final_score = (
            score * 0.7 +  # Векторная схожесть
            jaccard_score * 0.2 +  # Точные совпадения
            tf_bonus * 0.05 +  # Частота терминов
            doc_type_bonus  # Бонус за тип
        )
        
        return final_score
    
    def apply_filters(self, metadata: Dict, filters: Dict) -> bool:
        """Применение фильтров к результатам"""
        if not filters:
            return True
        
        # Фильтр по продукту
        if 'products' in filters:
            if metadata['product'] not in filters['products']:
                return False
        
        # Фильтр по версии
        if 'versions' in filters:
            if metadata['version'] not in filters['versions']:
                return False
        
        # Фильтр по типу документа
        if 'doc_types' in filters:
            if metadata['doc_type'] not in filters['doc_types']:
                return False
        
        # Фильтр по языку
        if 'language' in filters:
            if metadata.get('language') != filters['language']:
                return False
        
        return True
    
    def get_chunk_metadata_by_index(self, faiss_index: int, index_type: str) -> Optional[Dict]:
        """Получение метаданных chunk по FAISS индексу"""
        with self.metadata_lock:
            cursor = self.metadata_db.cursor()
            cursor.execute("""
                SELECT chunk_id, product, version, section, subsection, 
                       doc_type, language, text, metadata
                FROM chunks 
                WHERE doc_type = ?
                ORDER BY id
                LIMIT 1 OFFSET ?
            """, (index_type, faiss_index))
            
            result = cursor.fetchone()
            if result:
                return {
                    'chunk_id': result[0],
                    'product': result[1],
                    'version': result[2],
                    'section': result[3],
                    'subsection': result[4],
                    'doc_type': result[5],
                    'language': result[6],
                    'text': result[7],
                    'metadata': json.loads(result[8])
                }
        return None
    
    def remove_duplicates(self, results: List[Dict]) -> List[Dict]:
        """Удаление дубликатов из результатов"""
        seen_chunks = set()
        unique_results = []
        
        for result in results:
            chunk_id = result['chunk_id']
            if chunk_id not in seen_chunks:
                seen_chunks.add(chunk_id)
                unique_results.append(result)
        
        return unique_results
    
    def log_search_stats(self, query: str, results_count: int, 
                        avg_similarity: float, execution_time: float):
        """Логирование статистики поиска"""
        with self.metadata_lock:
            cursor = self.metadata_db.cursor()
            cursor.execute("""
                INSERT INTO search_stats 
                (query, results_count, avg_similarity, execution_time)
                VALUES (?, ?, ?, ?)
            """, (query, results_count, avg_similarity, execution_time))
            self.metadata_db.commit()
    
    def save_indexes(self):
        """Сохранение FAISS индексов"""
        for index_type, index in self.indexes.items():
            if index is not None:
                faiss.write_index(index, f"{self.db_path}/{index_type}.faiss")
    
    def load_indexes(self):
        """Загрузка FAISS индексов"""
        import os
        for index_type in self.indexes.keys():
            index_path = f"{self.db_path}/{index_type}.faiss"
            if os.path.exists(index_path):
                self.indexes[index_type] = faiss.read_index(index_path)
    
    def get_statistics(self) -> Dict:
        """Получение статистики использования"""
        with self.metadata_lock:
            cursor = self.metadata_db.cursor()
            
            # Общая статистика chunks
            cursor.execute("""
                SELECT 
                    product,
                    doc_type,
                    COUNT(*) as count
                FROM chunks 
                GROUP BY product, doc_type
            """)
            chunks_stats = cursor.fetchall()
            
            # Статистика поиска
            cursor.execute("""
                SELECT 
                    AVG(execution_time) as avg_time,
                    AVG(results_count) as avg_results,
                    COUNT(*) as total_searches
                FROM search_stats 
                WHERE timestamp > datetime('now', '-7 days')
            """)
            search_stats = cursor.fetchone()
            
            return {
                'chunks_by_product_type': chunks_stats,
                'search_performance': {
                    'avg_execution_time': search_stats[0] or 0,
                    'avg_results_count': search_stats[1] or 0,
                    'total_searches_week': search_stats[2] or 0
                },
                'total_chunks': sum(idx.ntotal if idx else 0 for idx in self.indexes.values())
            }
```

### 2.4 Интеллектуальный Query Processor

```python
import re
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass
import spacy
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import SnowballStemmer

@dataclass
class QueryAnalysis:
    original_query: str
    cleaned_query: str
    detected_products: List[str]
    detected_commands: List[str]
    detected_errors: List[str]
    query_type: str  # 'troubleshooting', 'how_to', 'configuration', 'general'
    language: str
    priority_terms: List[str]
    context_filters: Dict

class IntelligentQueryProcessor:
    def __init__(self):
        # Загружаем языковые модели
        try:
            self.nlp_en = spacy.load("en_core_web_sm")
            self.nlp_ru = spacy.load("ru_core_news_sm")
        except OSError:
            print("Please install spacy models: python -m spacy download en_core_web_sm ru_core_news_sm")
        
        # Стеммеры для разных языков
        self.stemmer_en = SnowballStemmer("english")
        self.stemmer_ru = SnowballStemmer("russian")
        
        # Стоп-слова
        try:
            self.stop_words_en = set(stopwords.words('english'))
            self.stop_words_ru = set(stopwords.words('russian'))
        except:
            self.stop_words_en = set()
            self.stop_words_ru = set()
        
        # Паттерны для определения типа запроса
        self.query_patterns = {
            'troubleshooting': [
                r'(error|ошибка|проблема|не работает|problem|issue|fail|failed)',
                r'(fix|исправить|решить|solve)',
                r'(broken|сломан|не запускается)',
                r'(debug|отладка|диагностика)'
            ],
            'how_to': [
                r'(how to|как|how do|каким образом)',
                r'(install|установить|настроить|configure)',
                r'(create|создать|setup|deploy)'
            ],
            'configuration': [
                r'(config|конфиг|настройка|setting)',
                r'(parameter|параметр|option|опция)',
                r'(tune|тюнинг|optimize|оптимизировать)'
            ]
        }
        
        # Словарь продуктов и их синонимов
        self.product_synonyms = {
            'kubernetes': ['k8s', 'kube', 'kubernetes', 'кубернетес'],
            'ceph': ['ceph', 'цеф'],
            'kafka': ['kafka', 'кафка'],
            'prometheus': ['prometheus', 'прометеус'],
            'grafana': ['grafana', 'графана'],
            'opensearch': ['opensearch', 'elastic', 'elasticsearch'],
            'nginx': ['nginx', 'энжинкс']
        }
        
        # Техническе термины с весами важности
        self.technical_terms = {
            # Kubernetes
            'pod': 2.0, 'deployment': 2.0, 'service': 2.0, 'ingress': 2.0,
            'configmap': 1.5, 'secret': 1.5, 'namespace': 1.5,
            
            # Ceph
            'osd': 2.0, 'mon': 2.0, 'mgr': 2.0, 'mds': 1.5,
            'pool': 1.5, 'rbd': 1.5, 'cephfs': 1.5,
            
            # Kafka
            'topic': 2.0, 'partition': 2.0, 'consumer': 1.5, 'producer': 1.5,
            'broker': 1.5, 'zookeeper': 1.5,
            
            # Общие термины
            'cluster': 1.5, 'node': 1.5, 'replica': 1.5,
            'backup': 1.5, 'restore': 1.5, 'scale': 1.5
        }
    
    def analyze_query(self, query: str, context: Dict = None) -> QueryAnalysis:
        """Полный анализ поискового запроса"""
        
        # Определяем язык
        language = self.detect_language(query)
        
        # Очищаем запрос
        cleaned_query = self.clean_query(query, language)
        
        # Извлекаем сущности
        detected_products = self.extract_products(query)
        detected_commands = self.extract_commands(query)
        detected_errors = self.extract_errors(query)
        
        # Определяем тип запроса
        query_type = self.classify_query_type(query)
        
        # Извлекаем приоритетные термины
        priority_terms = self.extract_priority_terms(cleaned_query, language)
        
        # Создаем контекстные фильтры
        context_filters = self.build_context_filters(
            detected_products, context, query_type
        )
        
        return QueryAnalysis(
            original_query=query,
            cleaned_query=cleaned_query,
            detected_products=detected_products,
            detected_commands=detected_commands,
            detected_errors=detected_errors,
            query_type=query_type,
            language=language,
            priority_terms=priority_terms,
            context_filters=context_filters
        )
    
    def detect_language(self, text: str) -> str:
        """Определение языка запроса"""
        cyrillic_count = len(re.findall(r'[а-яё]', text.lower()))
        latin_count = len(re.findall(r'[a-z]', text.lower()))
        
        return 'ru' if cyrillic_count > latin_count else 'en'
    
    def clean_query(self, query: str, language: str) -> str:
        """Очистка запроса от шума"""
        
        # Убираем специальные символы, оставляя важные
        cleaned = re.sub(r'[^\w\s\-\.]', ' ', query)
        
        # Убираем множественные пробелы
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Убираем стоп-слова
        stop_words = self.stop_words_ru if language == 'ru' else self.stop_words_en
        
        words = word_tokenize(cleaned.lower())
        filtered_words = [word for word in words if word not in stop_words and len(word) > 2]
        
        return ' '.join(filtered_words)
    
    def extract_products(self, query: str) -> List[str]:
        """Извлечение упоминаний продуктов"""
        detected_products = []
        query_lower = query.lower()
        
        for product, synonyms in self.product_synonyms.items():
            for synonym in synonyms:
                if synonym in query_lower:
                    detected_products.append(product)
                    break
        
        return list(set(detected_products))
    
    def extract_commands(self, query: str) -> List[str]:
        """Извлечение команд из запроса"""
        command_patterns = [
            r'kubectl\s+\w+.*',
            r'ceph\s+\w+.*',
            r'systemctl\s+\w+.*',
            r'docker\s+\w+.*',
            r'ansible\s+\w+.*',
            r'sudo\s+\w+.*'
        ]
        
        commands = []
        for pattern in command_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            commands.extend(matches)
        
        return commands
    
    def extract_errors(self, query: str) -> List[str]:
        """Извлечение ошибок из запроса"""
        error_patterns = [
            r'error:\s*(.+?)(?:\s|$)',
            r'ошибка:\s*(.+?)(?:\s|$)',
            r'failed:\s*(.+?)(?:\s|$)',
            r'exception:\s*(.+?)(?:\s|$)',
            r'\[ERROR\]\s*(.+?)(?:\s|$)'
        ]
        
        errors = []
        for pattern in error_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            errors.extend(matches)
        
        return errors
    
    def classify_query_type(self, query: str) -> str:
        """Классификация типа запроса"""
        query_lower = query.lower()
        
        type_scores = {}
        
        for query_type, patterns in self.query_patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, query_lower))
                score += matches
            type_scores[query_type] = score
        
        if max(type_scores.values()) == 0:
            return 'general'
        
        return max(type_scores.items(), key=lambda x: x[1])[0]
    
    def extract_priority_terms(self, cleaned_query: str, language: str) -> List[str]:
        """Извлечение приоритетных терминов с весами"""
        
        words = word_tokenize(cleaned_query.lower())
        
        # Применяем стемминг
        stemmer = self.stemmer_ru if language == 'ru' else self.stemmer_en
        stemmed_words = [stemmer.stem(word) for word in words]
        
        # Находим технические термины
        priority_terms = []
        
        for word in words:
            if word in self.technical_terms:
                priority_terms.append((word, self.technical_terms[word]))
        
        # Добавляем NER entities
        if language == 'ru':
            doc = self.nlp_ru(cleaned_query)
        else:
            doc = self.nlp_en(cleaned_query)
        
        for ent in doc.ents:
            if ent.label_ in ['PRODUCT', 'ORG', 'PERSON']:
                priority_terms.append((ent.text.lower(), 1.5))
        
        # Сортируем по важности
        priority_terms.sort(key=lambda x: x[1], reverse=True)
        
        return [term for term, weight in priority_terms]
    
    def build_context_filters(self, detected_products: List[str], 
                            context: Dict, query_type: str) -> Dict:
        """Построение контекстных фильтров"""
        
        filters = {}
        
        # Фильтр по продуктам
        if detected_products:
            filters['products'] = detected_products
        elif context and 'current_products' in context:
            filters['products'] = context['current_products']
        
        # Фильтр по типу документа в зависимости от типа запроса
        doc_type_mapping = {
            'troubleshooting': ['troubleshooting', 'stackoverflow'],
            'how_to': ['documentation', 'code_examples'],
            'configuration': ['documentation', 'code_examples'],
            'general': ['documentation', 'troubleshooting', 'stackoverflow']
        }
        
        filters['doc_types'] = doc_type_mapping.get(query_type, ['documentation'])
        
        # Фильтр по версиям из контекста
        if context and 'current_versions' in context:
            filters['versions'] = context['current_versions']
        
        return filters

class SearchOrchestrator:
    def __init__(self, vector_db: AdvancedVectorDatabase, 
                 embedding_generator: MultiModalEmbeddingGenerator,
                 query_processor: IntelligentQueryProcessor):
        self.vector_db = vector_db
        self.embedding_generator = embedding_generator
        self.query_processor = query_processor
        
        # Кэш для часто используемых запросов
        self.query_cache = {}
        self.cache_size_limit = 1000
    
    def search(self, query: str, context: Dict = None, top_k: int = 10) -> Dict:
        """Главный метод поиска"""
        
        # Проверяем кэш
        cache_key = hash(f"{query}_{str(context)}_{top_k}")
        if cache_key in self.query_cache:
            return self.query_cache[cache_key]
        
        # Анализируем запрос
        query_analysis = self.query_processor.analyze_query(query, context)
        
        # Генерируем embedding для запроса
        query_context = {
            'products': query_analysis.detected_products,
            'type': query_analysis.query_type
        }
        
        query_embedding = self.embedding_generator.generate_query_embedding(
            query_analysis.cleaned_query, query_context
        )
        
        # Выполняем векторный поиск
        search_results = self.vector_db.hybrid_search(
            query_embedding=query_embedding,
            query_text=query_analysis.cleaned_query,
            filters=query_analysis.context_filters,
            top_k=top_k
        )
        
        # Post-processing результатов
        processed_results = self.post_process_results(
            search_results, query_analysis
        )
        
        # Формируем финальный ответ
        final_result = {
            'query_analysis': query_analysis,
            'results': processed_results,
            'total_found': len(search_results),
            'search_metadata': {
                'execution_time': 0,  # TODO: измерить реальное время
                'used_filters': query_analysis.context_filters,
                'detected_entities': {
                    'products': query_analysis.detected_products,
                    'commands': query_analysis.detected_commands,
                    'errors': query_analysis.detected_errors
                }
            }
        }
        
        # Кэшируем результат
        if len(self.query_cache) < self.cache_size_limit:
            self.query_cache[cache_key] = final_result
        
        return final_result
    
    def post_process_results(self, results: List[Dict], 
                           query_analysis: QueryAnalysis) -> List[Dict]:
        """Пост-обработка результатов поиска"""
        
        processed_results = []
        
        for result in results:
            # Добавляем relevance score
            relevance_score = self.calculate_relevance_score(result, query_analysis)
            
            # Извлекаем ключевые фрагменты
            key_snippets = self.extract_key_snippets(
                result['text'], query_analysis.priority_terms
            )
            
            processed_result = {
                **result,
                'relevance_score': relevance_score,
                'key_snippets': key_snippets,
                'explanation': self.generate_relevance_explanation(result, query_analysis)
            }
            
            processed_results.append(processed_result)
        
        # Пересортировка по итоговому relevance score
        processed_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return processed_results
    
    def calculate_relevance_score(self, result: Dict, 
                                query_analysis: QueryAnalysis) -> float:
        """Расчет итогового relevance score"""
        
        base_score = result['hybrid_score']
        
        # Бонус за точное совпадение продукта
        product_bonus = 0
        if query_analysis.detected_products:
            if result['product'] in query_analysis.detected_products:
                product_bonus = 0.2
        
        # Бонус за тип запроса
        type_bonus = 0
        type_bonuses = {
            'troubleshooting': 0.3 if result['doc_type'] == 'troubleshooting' else 0,
            'how_to': 0.2 if result['doc_type'] in ['documentation', 'code_examples'] else 0,
            'configuration': 0.2 if result['doc_type'] == 'documentation' else 0
        }
        type_bonus = type_bonuses.get(query_analysis.query_type, 0)
        
        # Штраф за устаревшие версии (если известны текущие версии)
        version_penalty = 0
        # TODO: реализовать логику определения устаревших версий
        
        final_score = base_score + product_bonus + type_bonus - version_penalty
        
        return max(0, min(1, final_score))  # Нормализуем в диапазон [0, 1]
    
    def extract_key_snippets(self, text: str, priority_terms: List[str]) -> List[str]:
        """Извлечение ключевых фрагментов текста"""
        
        sentences = re.split(r'[.!?]+', text)
        snippets = []
        
        for sentence in sentences[:5]:  # Берем первые 5 предложений
            sentence = sentence.strip()
            if len(sentence) < 20:  # Пропускаем слишком короткие
                continue
                
            # Проверяем наличие приоритетных терминов
            sentence_lower = sentence.lower()
            for term in priority_terms[:3]:  # Проверяем топ-3 термина
                if term.lower() in sentence_lower:
                    snippets.append(sentence)
                    break
        
        return snippets[:3]  # Возвращаем топ-3 сниппета
    
    def generate_relevance_explanation(self, result: Dict, 
                                     query_analysis: QueryAnalysis) -> str:
        """Генерация объяснения релевантности"""
        
        explanations = []
        
        # Объяснение по продукту
        if result['product'] in query_analysis.detected_products:
            explanations.append(f"Точное совпадение продукта: {result['product']}")
        
        # Объяснение по типу документа
        if query_analysis.query_type == 'troubleshooting' and result['doc_type'] == 'troubleshooting':
            explanations.append("Документ по устранению неполадок")
        
        # Объяснение по векторной схожести
        if result['vector_similarity'] > 0.8:
            explanations.append("Высокая семантическая схожесть")
        elif result['vector_similarity'] > 0.6:
            explanations.append("Средняя семантическая схожесть")
        
        return "; ".join(explanations) if explanations else "Общая релевантность"
```

## 3. Интеграция компонентов и конфигурация

### 3.1 Главный конфигурационный файл

```python
# config.py
import os
from typing import Dict, Any

class VectorSearchConfig:
    def __init__(self):
        self.base_dir = os.getenv('VECTOR_SEARCH_BASE_DIR', '/opt/vector-search')
        
        # Embedding модели
        self.embedding_models = {
            'multilingual': {
                'model_path': 'paraphrase-multilingual-MiniLM-L12-v2',
                'weight': 0.6,
                'cache_dir': f'{self.base_dir}/models/multilingual'
            },
            'code': {
                'model_path': 'microsoft/codebert-base',
                'weight': 0.4,
                'cache_dir': f'{self.base_dir}/models/code'
            }
        }
        
        # Конфигурация векторной БД
        self.vector_db_config = {
            'db_path': f'{self.base_dir}/vector_db',
            'embedding_dim': 384,
            'backup_interval': 3600,  # секунды
            'cache_size': 10000
        }
        
        # Параметры chunking
        self.chunking_config = {
            'max_tokens': 512,
            'overlap_tokens': 50,
            'min_chunk_length': 100,
            'preserve_code_blocks': True
        }
        
        # Параметры поиска
        self.search_config = {
            'default_top_k': 10,
            'max_top_k': 50,
            'similarity_threshold': 0.3,
            'enable_hybrid_search': True,
            'cache_query_results': True
        }

# Пример использования всей системы
def create_vector_search_system():
    config = VectorSearchConfig()
    
    # Инициализируем компоненты
    text_processor = AdvancedTextProcessor()
    
    embedding_generator = MultiModalEmbeddingGenerator(
        config.embedding_models
    )
    
    vector_db = AdvancedVectorDatabase(
        config.vector_db_config['db_path'],
        config.vector_db_config['embedding_dim']
    )
    
    query_processor = IntelligentQueryProcessor()
    
    search_orchestrator = SearchOrchestrator(
        vector_db, embedding_generator, query_processor
    )
    
    return {
        'text_processor': text_processor,
        'embedding_generator': embedding_generator,
        'vector_db': vector_db,
        'query_processor': query_processor,
        'search_orchestrator': search_orchestrator
    }
```

## 4. Производительность и оптимизация

### 4.1 Рекомендации по производительности

**Аппаратные требования по компонентам:**

```
Text Processing: 2-4 CPU cores, 4GB RAM
Embedding Generation: 4-8 CPU cores, 8-16GB RAM  
Vector Database: 2-4 CPU cores, 16-32GB RAM (для индексов)
Query Processing: 1-2 CPU cores, 2GB RAM
```

**Оптимизации:**

1. **Батчевая обработка embeddings** - обрабатывать документы группами по 32-64 штуки
2. **Кэширование embeddings** - сохранять уже вычисленные embeddings
3. **Индексы в памяти** - держать FAISS индексы в RAM для скорости
4. **Асинхронная обработка** - использовать asyncio для I/O операций
5. **Компрессия индексов** - использовать PQ (Product Quantization) для больших объемов

### 4.2 Мониторинг и метрики

```python
# Ключевые метрики для мониторинга:
metrics = {
    'search_latency_p95': '<100ms',  # 95 процентиль времени поиска
    'embedding_generation_time': '<500ms',  # Время генерации embedding
    'index_memory_usage': '<80%',  # Использование памяти индексами
    'cache_hit_rate': '>70%',  # Процент попаданий в кэш
    'relevance_score_avg': '>0.7'  # Средний score релевантности
}
```

Эта система векторного поиска обеспечивает:

- **Высокую точность** за счет гибридного поиска и мультимодальных embeddings
- **Контекстную осведомленность** через интеллектуальную обработку запросов  
- **Масштабируемость** благодаря эффективным FAISS индексам
- **Мониторинг** для контроля производительности и качества
- **Гибкость** в настройке под разные типы технической документации

Хотите, чтобы я детальнее разобрал какой-то конкретный компонент или аспект реализации?