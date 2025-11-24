Короткий ответ
- При переходе на Redis 7 логика кластера в вашей ситуации не меняется: вернувшийся после сбоя бывший master поднимется как replica, и чтобы вернуть ему роль master, всё так же нужен ручной/manual failover с узла‑реплики (CLUSTER FAILOVER). Автовозврата нет. 
- Ваши скрипты из Redis 6 будут работать и в Redis 7. Возможны лишь косметические правки: поддержать термин “replica” в дополнение к “slave” и при желании упростить логику, полагаясь на встроенную семантику CLUSTER FAILOVER/OPTIONS. 

Что полезно учесть в Redis 7
- Команда CLUSTER FAILOVER и её опции FORCE/TAKEOVER не изменились (она есть с Redis 3.0). Это по‑прежнему правильный способ «вернуть» мастерство узлу после его восстановления. 
- Появившаяся в 6.2 (и актуальная в 7.x) команда FAILOVER относится к некластерному режиму и здесь не нужна — в кластере используйте именно CLUSTER FAILOVER. 
- Поля INFO для репликации остались совместимыми: master_repl_offset на мастере и slave_repl_offset на реплике доступны, термин «replica» может появляться в role, но «slave» всё ещё встречается в выводах для обратной совместимости. 

Мини‑патч к скрипту (если хотите учесть обе терминологии и сделать проверку надёжнее)
- Поддержать обе формы роли и не падать на незнакомом значении.
- Оставить «graceful» failover по умолчанию и по таймауту — FORCE.

Замените в вашем скрипте фрагменты проверки роли и offset’ов на это:

```bash
# Определение роли (учитываем и "replica", и "slave")
role="$("${CLI[@]}" INFO replication | awk -F: '/^role/{gsub(/\r/,"");print $2}')"
if [[ "$role" == "master" ]]; then
  log "Узел уже master."
  exit 0
fi
if [[ "$role" != "replica" && "$role" != "slave" ]]; then
  log "Неожиданная роль: $role"; exit 1
fi

# Извлекаем offsets: на реплике и на текущем мастере
slave_off="$("${CLI[@]}" INFO replication | awk -F: '/^slave_repl_offset/{gsub(/\r/,"");print $2}')"
master_host="$("${CLI[@]}" INFO replication | awk -F: '/^master_host/{gsub(/\r/,"");print $2}')"
master_port="$("${CLI[@]}" INFO replication | awk -F: '/^master_port/{gsub(/\r/,"");print $2}')"

master_off="$(redis-cli -h "$master_host" -p "$master_port" ${AUTH:+-a "$AUTH"} INFO replication \
              | awk -F: '/^master_repl_offset/{gsub(/\r/,"");print $2}')"

# Если offsets близки — выполняем мягкий failover, иначе по таймауту пробуем FORCE
log "Выполняю CLUSTER FAILOVER (graceful)"
if ! "${CLI[@]}" CLUSTER FAILOVER >/dev/null 2>&1; then
  log "Не удалось graceful; пробую CLUSTER FAILOVER FORCE"
  "${CLI[@]}" CLUSTER FAILOVER FORCE
fi
```

Вывод
- Поведение кластера при апгрейде на Redis 7 с точки зрения «возврата мастерства» не меняется; ваш подход со скриптом ручного failover остаётся корректным. Достаточно учесть терминологию и (опционально) упростить проверки, полагаясь на CLUSTER FAILOVER. 

Если хотите, пришлю вам полностью обновлённый файл скрипта под вашу топологию (порты/хосты/аутентификация) и unit-файл systemd.
