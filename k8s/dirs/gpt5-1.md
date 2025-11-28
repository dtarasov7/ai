Ниже — практический конспект по каталогам на Linux‑ноде Kubernetes (worker и control‑plane) и что выносить на отдельные тома/разделы, чтобы не словить переполнения.

Основные каталоги на ноде
- /var/lib/containerd (или /var/lib/docker, /var/lib/containers для CRI‑O)
  - Хранит образы, слои overlay, RW‑слои контейнеров, метаданные рантайма.
- /var/lib/kubelet
  - Рабочая директория kubelet: pods, volumes (emptyDir и т. п.), CSI sockets (plugins, plugins_registry), device-plugins, cpu_manager_state/memory_manager_state.
- /var/log/containers и /var/log/pods (+ системный /var/log/journal при journald)
  - Логи контейнеров и подов (symlink’и в /var/log/containers указывают на файлы в /var/log/pods).
- /etc/kubernetes
  - Конфиги kubelet/kube-proxy, kubeconfig’и, pki (на control‑plane).
- /etc/cni/net.d и /opt/cni/bin (+ иногда /var/lib/cni)
  - Конфиги и бинарники CNI. Обычно небольшие.
- /run/containerd/containerd.sock, /var/run/kubelet/kubelet.sock
  - Сокеты CRI и kubelet (в tmpfs).
- Каталоги сетевых плагинов (если есть): /var/lib/calico, /var/lib/flannel, и т. п.
- Только на control‑plane:
  - /var/lib/etcd — данные etcd (критично важные).
  - /etc/kubernetes/manifests — статические Pod-манифесты apiserver/controller/scheduler.
  - /etc/kubernetes/pki — сертификаты.

Что выносить на отдельные тома/разделы (приоритеты)
1) Критично (почти всегда выносить)
- /var/lib/etcd (только control‑plane)
  - Причина: единственное хранилище состояния кластера; высокие требования к IOPS и надежности. Отдельный SSD, ext4 или XFS, отключить atime (noatime), регулярный snapshot/backup и defrag/compaction.
- Хранилище образов контейнеров:
  - /var/lib/containerd (или /var/lib/docker, /var/lib/containers)
  - Причина: скачанные образы и RW‑слои быстро «съедают» диск. Отделив от корня, вы изолируете «imagefs» от «nodefs» — kubelet сможет независимо эвакуировать по imagefs/nodefs.
  - Рекомендации: XFS с ftype=1; для квот — pquota. SSD предпочтителен.
- /var/lib/kubelet
  - Причина: там лежат emptyDir и прочие локальные тома подов; именно они часто переполняются при нагрузке.
  - Важная заметка: kubelet считает «nodefs» тем файловым разделом, где находится его rootDir (обычно /var/lib/kubelet). Если вынесете его на отдельный том, пороги eviction для nodefs будут применяться к ЭТОМУ тому. Это удобно, но учитывайте размер и алерты.

2) Очень полезно выносить
- /var/log
  - Причина: контейнерные и системные логи могут расти непредсказуемо. Выделив отдельный раздел, не «убьете» корневую ФС.
  - Но: kubelet отслеживает доступное место на nodefs (ФС с /var/lib/kubelet). Если /var/log вынесен на другой раздел, заполнение /var/log не вызовет kubelet‑eviction. Значит обязательно настраивайте ротацию journald и CRI‑логов плюс мониторинг этого раздела.

3) По ситуации
- Каталоги для локальных PersistentVolume’ов (local PV): например /mnt/disks/*, /local-pv/*
  - Лучше всегда на отдельных дисках/томах с нужными гарантиями (RAID/SSD/XFS/ext4), чтобы не конкурировать с системой и runtime.
- /etc/kubernetes (малый объем) — выносить не обязательно; достаточно бэкапа.
- /etc/cni/net.d, /opt/cni/bin — маленькие, обычно не выносят.

Практические настройки для защиты от переполнения
- Eviction/GC в kubelet:
  - Настройте evictionHard/Soft для nodefs и imagefs (например: imagefs.available<15%, nodefs.available<10%, nodefs.inodesFree<5%). Задайте разумные пороги под ваши размеры томов.
  - Включите/подкрутите GC образов (image GC thresholds), чтобы не копились старые слои.
- Ограничение ephemeral storage на уровне подов:
  - Ставьте requests/limits по ресурсу ephemeral-storage.
  - Для emptyDir используйте sizeLimit. Чтобы sizeLimit реально применялся к «наземному» диску, используйте XFS с project quotas (pquota) и включенную изоляцию локального хранилища (в современных k8s это обычно включено).
- Ротация логов:
  - kubelet: container-log-max-size и container-log-max-files.
  - journald: SystemMaxUse/RuntimeMaxUse, SystemMaxFileSize и регулярная вакуумация (journalctl --vacuum-size/--vacuum-time).
  - Если /var/log на отдельном разделе — отдельные алерты по заполнению именно этого тома.
- Мониторинг и алерты:
  - Следите за nodefs.available, imagefs.available, inode’ами, скоростью роста /var/log и /var/lib/kubelet.
  - Алерты на EvictionThresholds, рост количества Evicted/Failed подов, частые перезапуски.
- Файловая система:
  - Для контейнерных слоев рекомендуются XFS (ftype=1) или ext4 с d_type. Для квот на каталоги — XFS+pquota.
- Операционные практики:
  - Не держите «вечные» образы — периодически чистите ненужные теги/кеши.
  - Локальные PV — строго на отдельных дисках/томах.
  - Продумайте резерв на случай «бурста» логов (инциденты, verbose‑режимы).

Пример схемы разбиения (worker‑нода)
- / — 30–50 ГБ (система, бинарники).
- /var/lib/containerd — 100–400 ГБ, XFS (ftype=1, pquota) — imagefs.
- /var/lib/kubelet — 100–400 ГБ, XFS (pquota) — nodefs (emptyDir/тома подов).
- /var/log — 20–40 ГБ (или больше, если много логов). Обязательная ротация и алерты.
- (опционально) /mnt/disks/local-pv-* — под локальные PV (размер по потребности, отдельные диски).

Пример схемы (control‑plane)
- Всё как для worker + отдельный быстрый том под /var/lib/etcd (например 50–200+ ГБ SSD, ext4/XFS, noatime, бэкапы/снапшоты).

Частые вопросы и тонкости
- containerd vs docker vs CRI‑O: ориентируйтесь на свой CRI и выносите именно его корень (/var/lib/containerd или /var/lib/docker или /var/lib/containers).
- Разнос /var/log и /var/lib/kubelet по разным томам: так делать можно, но тогда kubelet не «увидит» заполнение /var/log для eviction — компенсируйте это строгой ротацией и мониторингом /var/log.
- Inodes: следите не только за байтами, но и за количеством свободных inode (особенно при мелких лог‑файлах и кэше образов).

Если расскажете:
- какой CRI используете (containerd/docker/CRI‑O),
- есть ли локальные PV,
- тип нагрузки (много логов? много emptyDir? большие образы?),
- размеры доступных дисков,

я предложу точные размеры томов, рекомендации по ФС и пример kubelet‑конфига (eviction, GC, ротация логов) под вашу ситуацию.
