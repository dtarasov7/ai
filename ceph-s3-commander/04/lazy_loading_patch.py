
# ============================================================================
# ИЗМЕНЕНИЯ ДЛЯ ЛЕНИВОГО ЧТЕНИЯ (LAZY LOADING)
# ============================================================================

# 1. Добавить в класс PanelWidget инициализацию:
    def __init__(self, title, panel_type='fs', s3_config=None, app=None):
        # ... существующий код ...
        self.loading_in_progress = False
        self.loading_thread = None
        self.temp_items = []  # Временное хранилище для постепенной загрузки

# 2. Заменить метод _refresh_s3_objects для ленивой загрузки:
    def _refresh_s3_objects_lazy(self):
        """Ленивая загрузка объектов S3 с постепенным отображением"""
        prefix = self.current_prefix

        # Добавляем индикатор загрузки
        loading_text = SelectableText(' [Loading...]', {'type': 'loading', 'can_select': False}, self)
        self.walker.append(urwid.AttrMap(loading_text, 'info'))

        # Запускаем фоновую загрузку
        if self.loading_thread and self.loading_thread.is_alive():
            return

        self.loading_in_progress = True
        self.loading_thread = threading.Thread(
            target=self._load_s3_objects_background,
            args=(self.current_bucket, prefix),
            daemon=True
        )
        self.loading_thread.start()

    def _load_s3_objects_background(self, bucket_name, prefix):
        """Фоновая загрузка объектов с использованием генератора"""
        try:
            all_folders = []
            all_files = []

            # Используем ленивый генератор
            for folders, files in self.s3_manager.list_objects_lazy(bucket_name, prefix, page_size=1000):
                all_folders.extend(folders)
                all_files.extend(files)

                # После каждой страницы обновляем UI
                self.app.loop.set_alarm_in(0, lambda loop, user_data: self._update_display_incremental(
                    list(all_folders), list(all_files)
                ))

                # Небольшая пауза для обработки UI
                time.sleep(0.01)

            # Финальное обновление
            self.app.loop.set_alarm_in(0, lambda loop, user_data: self._finalize_loading(
                all_folders, all_files
            ))

        except Exception as e:
            self.app.loop.set_alarm_in(0, lambda loop, user_data: self.app.show_result(
                f"Error loading objects: {str(e)}"
            ))
        finally:
            self.loading_in_progress = False

    def _update_display_incremental(self, folders, files):
        """Инкрементальное обновление отображения по мере загрузки"""
        # Удаляем индикатор загрузки
        for i, widget in enumerate(self.walker):
            w = widget.original_widget
            if isinstance(w, SelectableText) and w.data.get('type') == 'loading':
                del self.walker[i]
                break

        # Создаем элементы для отображения
        items = self._create_display_items(folders, files)

        # Обновляем walker (удаляем старые объекты, добавляем новые)
        # Сохраняем заголовок "[..]"
        keep_count = 0
        for widget in self.walker:
            w = widget.original_widget
            if isinstance(w, SelectableText):
                if w.data.get('type') in ['to_root_menu', 'parent']:
                    keep_count += 1
                else:
                    break

        # Удаляем старые элементы
        del self.walker[keep_count:]

        # Добавляем новые
        for item_widget in items:
            self.walker.append(item_widget)

        # Добавляем индикатор продолжающейся загрузки
        if self.loading_in_progress:
            loading_text = SelectableText(
                f' [Loaded: {len(folders)} folders, {len(files)} files...]',
                {'type': 'loading', 'can_select': False},
                self
            )
            self.walker.append(urwid.AttrMap(loading_text, 'info'))

    def _finalize_loading(self, folders, files):
        """Завершение загрузки и финальное обновление"""
        self.loading_in_progress = False

        # Удаляем индикатор загрузки
        for i in range(len(self.walker) - 1, -1, -1):
            widget = self.walker[i]
            w = widget.original_widget
            if isinstance(w, SelectableText) and w.data.get('type') == 'loading':
                del self.walker[i]

        # Показываем статистику
        self.app.show_result(
            f"Loaded: {len(folders)} folders, {len(files)} files"
        )

    def _create_display_items(self, folders, files):
        """Создать виджеты для отображения папок и файлов"""
        items = []

        # Сортируем если нужно
        combined = []

        for folder in folders:
            key = folder['Key']
            folder_name = key.rstrip('/').split('/')[-1]
            combined.append({
                'type': 'folder',
                'name': folder_name,
                'key': key,
                'size': 0,
                'mtime': None
            })

        for file in files:
            key = file['Key']
            file_name = key.split('/')[-1]
            combined.append({
                'type': 'file',
                'name': file_name,
                'key': key,
                'size': file.get('Size', 0),
                'mtime': file.get('LastModified')
            })

        # Применяем сортировку
        combined = self.sort_items(combined)

        # Создаем виджеты
        for item in combined:
            if item['type'] == 'folder':
                label = f"[DIR]  {item['name']}"
                data = {
                    'type': 'folder',
                    'name': item['name'],
                    'key': item['key'],
                    'can_select': False
                }
            else:
                size_str = format_size(item['size'])
                time_str = item['mtime'].strftime('%Y-%m-%d %H:%M') if item['mtime'] else ''
                label = f"{item['name']:50} {size_str:>10} {time_str}"
                data = {
                    'type': 'file',
                    'name': item['name'],
                    'key': item['key'],
                    'size': item['size'],
                    'mtime': item['mtime'],
                    'can_select': True
                }

            text = SelectableText(f'  {label}', data, self)
            items.append(urwid.AttrMap(text, None, focus_map='selected'))

        return items

# 3. ЗАМЕНИТЬ ВЫЗОВ В МЕТОДЕ _refresh_s3:
    def _refresh_s3(self):
        if self.current_bucket is None:
            # ... код для списка бакетов остается без изменений ...
            pass
        else:
            # ИЗМЕНЕНИЕ: используем ленивую загрузку вместо обычной
            self.update_header(f'[S3 Mode - {self.current_endpoint}/{self.current_bucket}] Sort: {self.sort_mode}')

            display_prefix = self.current_prefix if self.current_prefix else '/'
            self.path_text.set_text(f'S3: /{self.current_endpoint}/{self.current_bucket}{display_prefix}')

            # Кнопка "назад"
            data = {'type': 'parent', 'can_select': False}
            if self.current_prefix:
                text = SelectableText('  [..] Parent Directory', data, self)
            else:
                text = SelectableText('  [..] Back to buckets', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

            # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: вызываем ленивую загрузку
            self._refresh_s3_objects_lazy()

# 4. АЛЬТЕРНАТИВНЫЙ ПОДХОД: Синхронная ленивая загрузка с пагинацией
    def _refresh_s3_objects_paginated(self, page_limit=5):
        """Загрузка первых N страниц, остальное по требованию"""
        prefix = self.current_prefix

        folders_total = []
        files_total = []
        page_count = 0

        # Загружаем первые несколько страниц
        for folders, files in self.s3_manager.list_objects_lazy(
            self.current_bucket, prefix, page_size=500
        ):
            folders_total.extend(folders)
            files_total.extend(files)
            page_count += 1

            if page_count >= page_limit:
                break

        # Отображаем загруженные данные
        items = self._create_display_items(folders_total, files_total)
        for item_widget in items:
            self.walker.append(item_widget)

        # Если есть еще данные, добавляем кнопку "Load More"
        # (требует дополнительной логики для продолжения итерации)
        if page_count >= page_limit:
            load_more_text = SelectableText(
                ' [Load More...]',
                {'type': 'load_more', 'can_select': True},
                self
            )
            self.walker.append(urwid.AttrMap(load_more_text, 'info', focus_map='selected'))



# 5. Оптимизация для больших директорий:
    def list_objects_lazy_optimized(self, bucket_name, prefix='', page_size=1000):
        """
        Оптимизированная ленивая загрузка с минимальной задержкой первого ответа
        """
        if self.s3_client is None:
            yield [], []
            return

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')

            # Оптимизация: первая страница маленькая для быстрого отклика
            first_page_config = {'MaxItems': 100, 'PageSize': 100}
            page_iterator = paginator.paginate(
                Bucket=bucket_name, 
                Prefix=prefix, 
                Delimiter='/',
                PaginationConfig=first_page_config
            )

            first_page = True
            for page in page_iterator:
                folders = []
                files = []

                if 'CommonPrefixes' in page:
                    for obj in page['CommonPrefixes']:
                        folders.append({'Key': obj['Prefix']})

                if 'Contents' in page:
                    for obj in page['Contents']:
                        if not obj['Key'].endswith('/') and obj['Key'] != prefix:
                            files.append(obj)

                yield folders, files

                # После первой страницы переключаемся на обычный размер
                if first_page:
                    first_page = False
                    # Создаем новый итератор с обычным размером страницы
                    page_iterator = paginator.paginate(
                        Bucket=bucket_name, 
                        Prefix=prefix, 
                        Delimiter='/',
                        PaginationConfig={'PageSize': page_size},
                        StartingToken=page.get('NextToken')
                    )

        except (ClientError, Exception) as e:
            yield [], []

# 6. Кеширование с учетом ленивой загрузки:
    def list_objects_lazy_cached(self, bucket_name, prefix='', page_size=1000):
        """Ленивая загрузка с кешированием"""
        cache_key = f"lazy:{bucket_name}:{prefix}"

        # Проверяем кеш
        cached = self.object_cache.get(cache_key)
        if cached is not None:
            # Возвращаем из кеша как единую страницу
            yield cached[0], cached[1]
            return

        # Загружаем и кешируем
        all_folders = []
        all_files = []

        for folders, files in self.list_objects_lazy(bucket_name, prefix, page_size):
            all_folders.extend(folders)
            all_files.extend(files)
            yield folders, files

        # Сохраняем в кеш
        self.object_cache.put(cache_key, (all_folders, all_files))
