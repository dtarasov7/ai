Коротко: отдельного поля “last password change” в REST нет. Но через Admin REST можно получить дату из метаданных пароля (createdDate) или из журнала событий (UPDATE_PASSWORD).

Способ 1 — по метаданным пароля (рекомендовано)
- Что даёт: точную дату последней установки пароля (кем угодно — пользователем или админом).
- Эндпоинт: GET /admin/realms/{realm}/users/{userId}/credentials
- Ищите запись с type == "password" и берите createdDate (миллисекунды с эпохи).

Пример (curl + jq):
1) Получить userId по username:
  curl -s -H "Authorization: Bearer $TOKEN" \
    "$KC/admin/realms/$REALM/users?username=j.doe&exact=true" | jq -r '.[0].id'
2) Достать дату:
  curl -s -H "Authorization: Bearer $TOKEN" \
    "$KC/admin/realms/$REALM/users/$USER_ID/credentials" \
    | jq -r '.[] | select(.type=="password") | .createdDate'
3) Преобразовать в ISO (Linux):
  ms=1713946218123
  date -u -d "@$((ms/1000))" +"%Y-%m-%dT%H:%M:%SZ"

Права: сервис-клиенту нужны роли realm-management: view-users (или manage-users).

Способ 2 — по событиям (если включено сохранение событий)
- Что даёт: время последнего события смены пароля самим пользователем.
- Эндпоинт: GET /admin/realms/{realm}/events?user={userId}&type=UPDATE_PASSWORD&max=1
- Вернётся объект с полем time (миллисекунды с эпохи).

Пример:
  curl -s -H "Authorization: Bearer $TOKEN" \
    "$KC/admin/realms/$REALM/events?user=$USER_ID&type=UPDATE_PASSWORD&max=1" \
    | jq -r '.[0].time'

Важно:
- Должно быть включено “Save Events” в Realm Settings → Events; есть срок хранения (Expiration).
- Если пароль сбросил админ, пользовательского события может не быть; тогда смотрите admin-events или используйте способ 1 (createdDate).

Если нужна дата, доступная самому пользователю
- Из коробки пользовательские REST/Account API не выдают дату смены пароля.
- Варианты:
  - сохранять её в user attribute (например, password_last_changed) при событии UPDATE_PASSWORD (Event Listener SPI) и отдать через /userinfo с protocol mapper;
  - или показывать её в кастомном эндпоинте/странице Account Console.

Нужны примеры для конкретной версии Keycloak или помочь с jq/скриптом под вашу среду? Скажите, вы хотите получать дату с правами админа или чтобы сам пользователь видел её.
