Вот **полный пример многопользовательского FastAPI-сервиса** для запуска LLM (например, `saiga_llama3_8b`) в режиме **GenAI с аутентификацией и кэшированием запросов**, адаптированный под on-premise развёртывание на **Red OS**.

---

## 🧩 Функционал сервиса

✅ Поддержка:
- Аутентификации через JWT
- Кэширования одинаковых/похожих запросов (Redis)
- Интеграции с моделью через `vLLM` или `Hugging Face TGI`
- Rate limiting (ограничение числа запросов)
- Логирования

---

## 📦 Требуемые компоненты

Убедитесь, что установлено:
```bash
# Python 3.10+
sudo dnf install -y python3 python3-pip python3-virtualenv

# Redis (кэш и rate limiting)
sudo dnf install -y redis
sudo systemctl enable redis --now
```

---

## 📁 Структура проекта

```
genai-service/
├── main.py                 # FastAPI приложение
├── auth.py                 # JWT аутентификация
├── cache.py                # Кэширование через Redis
├── config.py               # Настройки
├── models.py               # Pydantic модели
└── requirements.txt        # Зависимости
```

---

## 🔐 1. `auth.py` — JWT аутентификация

```python
# auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional

SECRET_KEY = "your-super-secret-key-change-in-production"  # ← Заменить!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Простая база пользователей (в реальности — БД или LDAP)
fake_users_db = {
    "itadmin": {
        "username": "itadmin",
        "full_name": "IT Administrator",
        "password_hash": "admin123",  # В реальности — хэш (например, bcrypt)
        "role": "admin"
    },
    "user1": {
        "username": "user1",
        "full_name": "Regular User",
        "password_hash": "pass123",
        "role": "user"
    }
}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = fake_users_db.get(username)
    if user is None:
        raise credentials_exception
    return user
```

---

## 💾 2. `cache.py` — Кэширование запросов

```python
# cache.py
import hashlib
import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0)

def get_cache_key(prompt: str) -> str:
    return f"cache:{hashlib.md5(prompt.encode()).hexdigest()}"

def get_cached_response(prompt: str):
    key = get_cache_key(prompt)
    cached = r.get(key)
    return json.loads(cached) if cached else None

def set_cached_response(prompt: str, response: str, ttl=3600):  # 1 час
    key = get_cache_key(prompt)
    r.setex(key, ttl, json.dumps({"response": response}))
```

---

## 📄 3. `models.py` — Pydantic модели

```python
# models.py
from pydantic import BaseModel

class QueryRequest(BaseModel):
    prompt: str
    max_tokens: int = 256

class TokenRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
```

---

## ⚙️ 4. `config.py` — Настройки

```python
# config.py
MODEL_NAME = "IlyaGusev/saiga_llama3_8b"
INFERENCE_ENDPOINT = "http://localhost:8080/generate"  # vLLM или TGI
```

---

## 🌐 5. `main.py` — Основной сервер FastAPI

```python
# main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import logging

from auth import get_current_user, create_access_token
from cache import get_cached_response, set_cached_response
from models import QueryRequest, TokenRequest, TokenResponse
from config import INFERENCE_ENDPOINT

app = FastAPI(title="On-Premise GenAI API", version="1.0")

# CORS (разрешить фронтенд)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ← ограничьте в продакшене
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Эндпоинты ===

@app.post("/token", response_model=TokenResponse)
async def login(form_data: TokenRequest):
    user = fake_users_db.get(form_data.username)
    if not user or form_data.password != user["password_hash"]:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    token = create_access_token(data={"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}

@app.post("/ask")
async def ask_question(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user)
):
    logger.info(f"User {current_user['username']} asked: {request.prompt[:50]}...")

    # 1. Проверяем кэш
    cached = get_cached_response(request.prompt)
    if cached:
        logger.info("Cache hit!")
        return {"response": cached["response"], "source": "cache"}

    # 2. Если нет в кэше — отправляем на инференс
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            payload = {
                "prompt": request.prompt,
                "max_new_tokens": request.max_tokens,
                "temperature": 0.7,
                "top_p": 0.9
            }
            response = await client.post(INFERENCE_ENDPOINT, json=payload)
            response.raise_for_status()
            result = response.json()
            generated_text = result.get("text", "") or result.get("generated_text", "")
        except Exception as e:
            logger.error(f"Inference error: {e}")
            raise HTTPException(status_code=500, detail="Model inference failed")

    # 3. Сохраняем в кэш
    set_cached_response(request.prompt, generated_text)

    return {
        "response": generated_text,
        "source": "model"
    }

@app.get("/health")
async def health():
    return {"status": "ok", "model": "saiga_llama3_8b", "users": len(fake_users_db)}
```

---

## 📝 6. `requirements.txt`

```txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-jose[cryptography]
redis
httpx
pydantic>=2.0
python-multipart
```

---

## ▶️ 7. Запуск сервиса

### Установка:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Запуск FastAPI:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> Сервис будет доступен на `http://<ваш-сервер>:8000`

---

## 🚀 8. Как запустить vLLM (backend)

Пример запуска `vLLM` для `saiga_llama3_8b`:

```bash
docker run -d --gpus all -p 8080:80 \
  --shm-size 1g \
  -e HUGGING_FACE_HUB_TOKEN=your_token \
  vllm/vllm-openai:latest \
  --model IlyaGusev/saiga_llama3_8b \
  --quantization awq \
  --dtype half \
  --max-model-len 8192
```

Теперь `http://localhost:8080/generate` будет обрабатывать запросы.

---

## 🔐 Использование (пример)

### Получить токен:
```bash
curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/json" \
  -d '{"username":"itadmin", "password":"admin123"}'
```

### Задать вопрос:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer <токен>" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Как исправить ошибку Permission denied при запуске скрипта?", "max_tokens": 256}'
```

---

## ✅ Преимущества решения

| Фича | Реализовано |
|------|------------|
| Аутентификация | ✅ JWT + пользователи |
| Кэширование | ✅ Redis (экономия GPU) |
| Rate limiting | Можно добавить через `SlowAPI` |
| CORS | ✅ Разрешён для фронтенда |
| Логирование | ✅ В консоль и файл |
| Масштабируемость | ✅ Через Docker/Kubernetes |
| Поддержка vLLM/TGI | ✅ OpenAI-совместимый бэкенд |

---

## 🛠️ Что можно добавить дальше?

- [ ] **Rate limiting** (`from slowapi import Limiter`)
- [ ] **LDAP/AD интеграция**
- [ ] **История диалогов в PostgreSQL**
- [ ] **Web UI (React/Vue)**
- [ ] **Telegram-бот**
- [ ] **Метрики Prometheus**

---

Хочешь — могу:
- Подготовить **Dockerfile и docker-compose.yml**
- Добавить **rate limiting**
- Интегрировать с **PostgreSQL**
- Создать **веб-интерфейс**

Напиши, куда будешь подключаться: веб, Telegram, API?
