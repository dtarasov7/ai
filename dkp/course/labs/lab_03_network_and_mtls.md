# Лабораторная работа 3. Минимальные сетевые требования и mTLS

## Цель

Ограничить east-west трафик `shop-demo`, ввести default deny и построить доверие между сервисами на основе ServiceAccount, а не IP-адреса.

## Исходные материалы

- `shop-demo/manifests/`
- глава 3 курса
- markmap `markmaps/chapter_03_network_mtls.mm`

## Ожидаемое время

90-120 минут

## Задание

1. Составьте матрицу допустимых соединений:
   - `frontend -> orders`;
   - `orders -> payments`;
   - что должно быть запрещено.
2. Подготовьте минимальный набор сетевых правил:
   - default deny ingress;
   - default deny egress там, где это допустимо;
   - allow only explicit dependencies.
3. Определите, где достаточно `NetworkPolicy`, а где действительно нужен язык Cilium.
4. Для цепочки `orders -> payments` спроектируйте:
   - strict mTLS;
   - доверенный ServiceAccount сервиса;
   - `AuthorizationPolicy`.
5. Подготовьте YAML-манифесты для двух способов выразить допустимую связь:
   - стандартный `NetworkPolicy`;
   - `CiliumNetworkPolicy`, если в вашем сценарии есть причина использовать возможности Cilium.
6. Опишите, как вы будете тестировать отсутствие перемещения атакующего внутри среды (lateral movement).

## Что нужно сдать

- network dependency matrix;
- набор `NetworkPolicy`/`CiliumNetworkPolicy`, `PeerAuthentication` и `AuthorizationPolicy`;
- схема доверия между сервисами (trust between services);
- план тестирования допустимых и запрещённых связей.

## Критерии завершения

- изоляция namespace не подменяется предположением “и так всё разделено”;
- отдельно рассмотрен egress;
- mTLS не используется как замена segmentation;
- есть тест на запрещённый доступ из неподходящего namespace.
