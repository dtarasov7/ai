# Легковесные заглушки для замены OpenSearch

## Вариант 1: HTTP Mock Server (Node.js) - Самый простой

Создайте файл `mock-opensearch.js`:

```javascript
const http = require('http');

const server = http.createServer((req, res) => {
    const timestamp = new Date().toISOString();
    
    // Логируем все запросы
    console.log(`[${timestamp}] ${req.method} ${req.url}`);
    console.log('Headers:', JSON.stringify(req.headers, null, 2));
    
    // Читаем тело запроса
    let body = '';
    req.on('data', chunk => {
        body += chunk.toString();
    });
    
    req.on('end', () => {
        if (body) {
            console.log('Body:', body);
            console.log('---');
        }
        
        // Отвечаем успехом на все запросы
        res.writeHead(200, { 
            'Content-Type': 'application/json',
            'X-Mock-Server': 'true'
        });
        
        // Имитируем ответ OpenSearch
        res.end(JSON.stringify({
            took: 1,
            errors: false,
            items: []
        }));
    });
});

const PORT = 9200;
server.listen(PORT, () => {
    console.log(`Mock OpenSearch server running on http://localhost:${PORT}`);
    console.log('Accepting all requests and logging them...');
});
```

Запуск:
```bash
node mock-opensearch.js
```

## Вариант 2: Python HTTP Server - Еще проще

Создайте файл `mock_opensearch.py`:

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime

class MockOpenSearchHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        timestamp = datetime.now().isoformat()
        print(f"\n[{timestamp}] {self.command} {self.path}")
        print(f"Headers: {dict(self.headers)}")
        print(f"Body: {body}")
        print("-" * 80)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        response = json.dumps({
            "took": 1,
            "errors": False,
            "items": []
        })
        self.wfile.write(response.encode())
    
    def do_PUT(self):
        self.do_POST()
    
    def do_GET(self):
        print(f"\n[{datetime.now().isoformat()}] {self.command} {self.path}")
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        response = json.dumps({
            "cluster_name": "mock-opensearch",
            "version": {"number": "2.0.0"}
        })
        self.wfile.write(response.encode())
    
    def log_message(self, format, *args):
        pass  # Отключаем стандартное логирование

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 9200), MockOpenSearchHandler)
    print('Mock OpenSearch server running on http://localhost:9200')
    print('Press Ctrl+C to stop')
    server.serve_forever()
```

Запуск:
```bash
python3 mock_opensearch.py
```

## Вариант 3: Docker с httpbin - Без кода

Используйте готовый HTTP mock сервис:

```bash
docker run -d --name mock-opensearch \
  -p 9200:80 \
  kennethreitz/httpbin
```

Проверка:
```bash
curl http://localhost:9200/post
```

## Вариант 4: Docker с Mockoon - Продвинутый

```bash
docker run -d --name mock-opensearch \
  -p 9200:3000 \
  -v $(pwd)/mockoon-data:/data \
  mockoon/cli:latest \
  --data /data --port 3000
```

## Вариант 5: netcat - Минималистичный (Linux/Mac)

Просто слушает порт и выводит все запросы:

```bash
while true; do 
  nc -l 9200 | tee -a opensearch-requests.log | \
  (echo -e "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}" && cat > /dev/null)
done
```

## Рекомендация для вашей задачи

**Используйте Вариант 2 (Python)** - он:
- ✅ Не требует установки зависимостей (только Python 3)
- ✅ Показывает все данные, которые приходят от Data Prepper
- ✅ Отвечает корректными HTTP статусами
- ✅ Поддерживает все HTTP методы
- ✅ Легко модифицировать под ваши нужды

## Интеграция с Data Prepper

В конфигурации Data Prepper (`data-prepper-config.yaml`) укажите:

```yaml
sink:
  - opensearch:
      hosts: ["http://localhost:9200"]
      index: "otel-logs-%{yyyy.MM.dd}"
      # Другие настройки...
```

Mock сервер будет принимать все запросы и логировать их в консоль, что позволит вам видеть, какие данные Data Prepper пытается отправить в OpenSearch.

## Сохранение данных в файл (опция для Python mock)

Если хотите сохранять все запросы в файл, добавьте в Python скрипт:

```python
# В начале файла
log_file = open('opensearch-requests.log', 'a')

# В методе do_POST после print("-" * 80)
log_file.write(f"\n[{timestamp}] {self.command} {self.path}\n")
log_file.write(f"Body: {body}\n")
log_file.write("-" * 80 + "\n")
log_file.flush()
```

Это даст вам полную историю всех данных, отправленных в "OpenSearch".