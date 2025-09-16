Отличный и точный вопрос – давайте сразу пойдём к делу 🚀.  

В **Keycloak Admin REST API** данные о пароле пользователя лежат в массиве **credentials**. Конкретно поле `createdDate` — это и есть дата, когда был создан текущий пароль (в миллисекундах с эпохи UNIX). Это фактически и есть "дата последней смены пароля".  

---

### Как это получить через REST API:
1. Сначала получите **admin access token**:
```bash
curl -X POST \
  "http://<KEYCLOAK_HOST>/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin" \
  -d "password=XXXXXXXX" \
  -d "grant_type=password" \
  -d "client_id=admin-cli"
```
Ответом будет JSON с токеном (`access_token`). Его мы используем дальше.  

---

2. Запросите пользователя (по `userId`):  
```bash
curl -X GET \
  "http://<KEYCLOAK_HOST>/admin/realms/<REALM>/users/<USER_ID>" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

3. В ответе будет массив `credentials` (если разрешена их загрузка). Примерно так:
```json
{
  "id": "f1b2c3d4-5678-...-...",
  "username": "vasya",
  "enabled": true,
  "credentials": [
    {
      "id": "6a0f6d17-xxxx-xxxx-xxxx",
      "type": "password",
      "createdDate": 1680701234567,
      "temporary": false
    }
  ]
}
```

👉 Поле `createdDate` — это и есть искомая дата. Значение хранится в **миллисекундах** от 1970‑01‑01 (Unix epoch).  

---

### Уточнение:
Иногда, в свежих версиях Keycloak (особенно 20+), по умолчанию `GET /users/{id}` **не возвращает массив credentials** (он может быть опущен).  
Тогда надо вызывать эндпоинт **explicit**:  
```bash
GET /admin/realms/<REALM>/users/<USER_ID>/credentials
```
и там уже смотреть `createdDate`.  

---

### Пример:
```bash
curl -X GET \
  "http://<KEYCLOAK_HOST>/admin/realms/<REALM>/users/<USER_ID>/credentials" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Ответ:
```json
[
  {
    "id": "6a0f6d17-xxxx-xxxx-xxxx",
    "type": "password",
    "createdDate": 1680701234567,
    "temporary": false
  }
]
```

Тут `createdDate` → 1680701234567 → март 2023 г.  

---

Таким образом, дата смены пароля = поле `createdDate` у `type: "password"` в **/users/{id}/credentials**.  

Хотите я покажу короткий пример на `jq`, чтобы сразу выводить эту дату в читаемом виде (например "2023-04-05 14:33:54") из ответа API?
