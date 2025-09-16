Отлично! Ниже — **расширенная версия GenAI-сервиса** с добавлением:

✅ **Rate limiting** (ограничение запросов)  
✅ **PostgreSQL** для хранения истории диалогов  
✅ **Веб-интерфейс на HTML + JS** (легковесный, без React)  
✅ Поддержка доступа через **веб и API**

Решение подходит для on-premise развёртывания на **Red OS**, легко масштабируется.

---

## 🧩 Обновлённая архитектура

```
[ Веб-браузер ] ←→ [ FastAPI + Веб UI ]
       ↓
[ API / JWT Auth ]
       ↓
[ Rate Limit | Кэш Redis | История PostgreSQL ]
       ↓
[ vLLM / TGI (GPU) ]
```

---

## 🔧 1. Установка зависимостей (обновлённый `requirements.txt`)

```txt
# requirements.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-jose[cryptography]
redis
httpx
pydantic>=2.0
python-multipart
sqlalchemy
psycopg2-binary
jinja2
slowapi
databases[postgresql]
```

> Установка:
> ```bash
> pip install -r requirements.txt
> ```

---

## 🗄️ 2. Настройка PostgreSQL

### Установка на Red OS:
```bash
sudo dnf install -y postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl enable postgresql --now
```

### Создание БД и пользователя:
```bash
sudo -u postgres psql
```
```sql
CREATE USER genai_user WITH PASSWORD 'strongpassword';
CREATE DATABASE genai_db OWNER genai_user;
GRANT ALL PRIVILEGES ON DATABASE genai_db TO genai_user;
\q
```

---

## 📁 3. Новая структура проекта

```
genai-service/
├── main.py                 # Основной сервер
├── auth.py                 # JWT
├── cache.py                # Redis
├── database.py             # PostgreSQL ORM
├── models_db.py            # SQLAlchemy модели
├── templates/              # Веб-интерфейс
│   └── index.html
├── static/
│   └── style.css
├── config.py
└── requirements.txt
```

---

## 💾 4. `database.py` — Подключение к PostgreSQL

```python
# database.py
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import databases
import os

DATABASE_URL = "postgresql+asyncpg://genai_user:strongpassword@localhost/genai_db"

# Sync engine (для ORM)
engine = create_engine(DATABASE_URL.replace("asyncpg", "psycopg2"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async (для FastAPI)
database = databases.Database(DATABASE_URL)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    full_name = Column(String)
    role = Column(String)
    dialogs = relationship("Dialog", back_populates="user")

class Dialog(Base):
    __tablename__ = "dialogs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    source = Column(String)  # "model" или "cache"

    user = relationship("User", back_populates="dialogs")

# Создаём таблицы
Base.metadata.create_all(bind=engine)
```

---

## 🆕 5. `models_db.py` — Pydantic модели для БД

```python
# models_db.py
from pydantic import BaseModel
from datetime import datetime

class DialogBase(BaseModel):
    prompt: str
    response: str
    source: str

class DialogCreate(DialogBase):
    pass

class DialogOut(DialogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True
```

---

## ⏱️ 6. Добавляем Rate Limiting (`slowapi`)

### В `main.py` в начале:

```python
# main.py — частичное обновление
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

# Лимит: 30 запросов в минуту на пользователя
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
```

### Пример лимита на `/ask`:

```python
@app.post("/ask")
@limiter.limit("30/minute")  # ← ограничение
async def ask_question(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync)
):
    ...
```

> ⚠️ Для более точного учёта по пользователю — используйте `key_func=lambda: current_user["username"]` (нужна кастомизация).

---

## 🌐 7. Обновлённый `main.py` — с историей и вебом

```python
# main.py (обновлённый фрагмент)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Зависимость для БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_sync():
    return next(get_db())

# === Веб-интерфейс ===
@app.get("/")
async def web_interface(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "username": user["username"]})

# === Сохранение в БД при ответе ===
@app.post("/ask")
@limiter.limit("30/minute")
async def ask_question(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logger.info(f"User {current_user['username']} asked: {request.prompt[:50]}...")

    cached = get_cached_response(request.prompt)
    if cached:
        response_text = cached["response"]
        source = "cache"
    else:
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                payload = {
                    "prompt": request.prompt,
                    "max_new_tokens": request.max_tokens,
                    "temperature": 0.7,
                    "top_p": 0.9
                }
                resp = await client.post(INFERENCE_ENDPOINT, json=payload)
                resp.raise_for_status()
                result = resp.json()
                response_text = result.get("text", "") or result.get("generated_text", "")
            except Exception as e:
                logger.error(f"Inference error: {e}")
                raise HTTPException(status_code=500, detail="Model inference failed")
        set_cached_response(request.prompt, response_text)
        source = "model"

    # Сохраняем в PostgreSQL
    db_user = db.query(User).filter(User.username == current_user["username"]).first()
    if not db_user:
        db_user = User(username=current_user["username"], full_name=current_user.get("full_name", ""), role=current_user["role"])
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    dialog = Dialog(user_id=db_user.id, prompt=request.prompt, response=response_text, source=source)
    db.add(dialog)
    db.commit()

    return {"response": response_text, "source": source}
```

---

## 🖼️ 8. Веб-интерфейс: `templates/index.html`

```html
<!-- templates/index.html -->
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <title>GenAI — IT Ассистент</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <div class="container">
    <h1>Привет, {{ username }}!</h1>
    <p>Задайте вопрос IT-ассистенту:</p>

    <form id="queryForm">
      <textarea id="prompt" rows="4" placeholder="Например: Как исправить ошибку 'Permission denied'?"></textarea>
      <button type="submit">Спросить</button>
    </form>

    <div id="response" class="response"></div>
  </div>

  <script>
    const form = document.getElementById("queryForm");
    const responseDiv = document.getElementById("response");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const prompt = document.getElementById("prompt").value.trim();
      if (!prompt) return;

      responseDiv.innerHTML = "🧠 Генерация...";

      const token = localStorage.getItem("access_token");
      const res = await fetch("/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ prompt })
      });

      const data = await res.json();
      if (res.ok) {
        responseDiv.innerHTML = `
          <strong>Ответ:</strong><br>${data.response.replace(/\n/g, "<br>")}
          <small style="color: #666;">(источник: ${data.source})</small>
        `;
      } else {
        responseDiv.innerHTML = `<span style="color: red;">Ошибка: ${data.detail}</span>`;
      }
    });
  </script>
</body>
</html>
```

---

## 🎨 9. Стили: `static/style.css`

```css
/* static/style.css */
body {
  font-family: Arial, sans-serif;
  background: #f4f6f8;
  margin: 0;
  padding: 20px;
}

.container {
  max-width: 800px;
  margin: 0 auto;
  background: white;
  padding: 30px;
  border-radius: 10px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #ccc;
  border-radius: 6px;
  font-size: 16px;
  resize: vertical;
}

button {
  margin-top: 10px;
  padding: 10px 20px;
  background: #007BFF;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 16px;
}

button:hover {
  background: #0056b3;
}

.response {
  margin-top: 20px;
  padding: 15px;
  background: #f8f9fa;
  border: 1px solid #ddd;
  border-radius: 6px;
  white-space: pre-wrap;
}
```

---

## 🔐 Авторизация в вебе (JS + localStorage)

После входа через `/token`, сохраните токен:

```javascript
// После логина (можно сделать форму входа)
localStorage.setItem("access_token", "ваш_jwt_токен");
```

---

## ▶️ 10. Запуск всего стека

```bash
# 1. Запустить PostgreSQL и Redis
sudo systemctl start postgresql redis

# 2. Запустить vLLM (в Docker)
docker run -d --gpus all -p 8080:80 vllm/vllm-openai:latest \
  --model IlyaGusev/saiga_llama3_8b --dtype half --max-model-len 8192

# 3. Запустить FastAPI
uvicorn main:app --host 0.0.0.0 --port 8000
```

Теперь:
- **API**: `http://your-server:8000/ask` (с JWT)
- **Веб**: `http://your-server:8000/`

---

## ✅ Что получилось

| Функция | Готово |
|-------|--------|
| Аутентификация (JWT) | ✅ |
| Rate limiting | ✅ (30/мин) |
| Кэширование (Redis) | ✅ |
| История диалогов (PostgreSQL) | ✅ |
| Веб-интерфейс | ✅ (HTML + JS) |
| Поддержка API и веба | ✅ |
| Совместимость с Red OS | ✅ |

---

## 🛠️ Дальнейшие улучшения

Могу добавить:
- [ ] **Telegram-бот**
- [ ] **Админ-панель** (просмотр диалогов)
- [ ] **Docker-compose.yml** для всех сервисов
- [ ] **HTTPS (Let's Encrypt)** через Nginx
- [ ] **LDAP/AD интеграция**
- [ ] **Экспорт диалогов в PDF/CSV**

---

Хочешь — подготовлю **полный архив с проектом + `docker-compose.yml`** для быстрого развёртывания.

Напиши:
- Нужен ли HTTPS?
- Будет ли нагрузка высокой?
- Нужна ли резервная копия БД?

— и я адаптирую под ваш on-premise контур.
