
    def _refresh_s3(self):
        if self.current_bucket is None:
            self.mode_text.set_text(f'[S3 Mode - {self.current_endpoint}] Sort: {self.sort_mode}')
            self.path_text.set_text(f'S3: /{self.current_endpoint}/')

            data = {'type': 'to_root_menu', 'can_select': False}
            text = SelectableText('  [..] Back to root menu', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

            buckets = self.s3_manager.list_buckets()

            if not buckets and self.s3_manager.connection_error:
                error_msg = f'[ERROR] Connection failed: {self.s3_manager.connection_error[:60]}'
                data = {'type': 'error', 'can_select': False}
                text = SelectableText(f'  {error_msg}', data, self)
                self.walker.append(urwid.AttrMap(text, 'error'))
                self.app.show_result(f'Cannot connect to {self.current_endpoint}: {self.s3_manager.connection_error[:80]}')
                return

            bucket_items = []
            for bucket in buckets:
                bucket_items.append({
                    'name': bucket['Name'],
                    'type': 'bucket',
                    'CreationDate': bucket.get('CreationDate'),
                    'mtime': bucket.get('CreationDate'),
                    'size': 0,
                    'can_select': True
                })

            bucket_items = self.sort_items(bucket_items)

            for bucket in bucket_items:
                creation_date = bucket.get('CreationDate')
                date_str = creation_date.strftime('%Y-%m-%d %H:%M:%S') if creation_date else ' ' * 19

                label = f'[BUCKET] {bucket["name"]:40} {date_str}'
                data = {'type': 'bucket', 'name': bucket['name'], 'can_select': True}
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))
        else:
            self.mode_text.set_text(f'[S3 Mode - {self.current_endpoint}] Sort: {self.sort_mode}')
            self.path_text.set_text(f'S3: /{self.current_endpoint}/{self.current_bucket}/{self.current_prefix}')

            if self.current_prefix:
                data = {'type': 's3_parent', 'can_select': False}
                text = SelectableText('  [..] Parent', data, self)
            else:
                data = {'type': 's3_back', 'can_select': False}
                text = SelectableText('  [..] Back to buckets', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

            folders, files = self.s3_manager.list_objects(self.current_bucket, self.current_prefix)

            if not folders and not files and self.s3_manager.connection_error:
                error_msg = f'[ERROR] Cannot list objects: {self.s3_manager.connection_error[:60]}'
                data = {'type': 'error', 'can_select': False}
                text = SelectableText(f'  {error_msg}', data, self)
                self.walker.append(urwid.AttrMap(text, 'error'))
                return

            folder_items = []
            for folder in folders:
                folder_name = folder['Key'][len(self.current_prefix):].rstrip('/')
                folder_items.append({
                    'name': folder_name,
                    'key': folder['Key'],
                    'type': 's3_dir',
                    'size': 0,
                    'mtime': datetime.min,
                    'can_select': True
                })

            file_items = []
            for file_obj in files:
                key = file_obj['Key']
                file_name = key[len(self.current_prefix):]

                versions = self.s3_manager.list_object_versions(self.current_bucket, key)
                version_info = ''
                if len(versions) > 1:
                    version_info = f' [v:{len(versions)}]'

                file_items.append({
                    'name': file_name,
                    'key': key,
                    'type': 's3_file',
                    'size': file_obj['Size'],
                    'Size': file_obj['Size'],
                    'mtime': file_obj.get('LastModified', datetime.min),
                    'LastModified': file_obj.get('LastModified'),
                    'version_count': len(versions),
                    'version_info': version_info,
                    'can_select': True
                })

            folder_items = self.sort_items(folder_items)
            file_items = self.sort_items(file_items)

            for folder_item in folder_items:
                label = f'[DIR ] {folder_item["name"]:40}  <DIR>           ' + ' ' * 19
                data = {'type': 's3_dir', 'key': folder_item['key'], 'name': folder_item['name'], 'can_select': True}
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

            for file_item in file_items:
                mtime = file_item['LastModified'].strftime('%Y-%m-%d %H:%M:%S') if file_item.get('LastModified') else ' ' * 19
                size_str = self.format_size(file_item['size'])
                version_str = file_item['version_info']

                label = f'[FILE] {file_item["name"]:40} {size_str:>10}{version_str:8} {mtime}'
                data = {
                    'type': 's3_file',
                    'key': file_item['key'],
                    'name': file_item['name'],
                    'size': file_item['size'],
                    'version_count': file_item['version_count'],
                    'can_select': True
                }
                text = SelectableText(f'  {label}', data, self)
                self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

    def _refresh_fs(self):
        self.mode_text.set_text(f'[FS Mode] Sort: {self.sort_mode}')
        self.path_text.set_text(f'FS: {self.fs_browser.current_path}')

        if self.is_fs_root():
            data = {'type': 'to_root_menu', 'can_select': False}
            text = SelectableText('  [..] Back to root menu', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

        items = self.fs_browser.list_directory()

        dirs = [item for item in items if item['is_dir'] and item['name'] != '..']
        files = [item for item in items if not item['is_dir']]
        parent = [item for item in items if item['name'] == '..']

        dirs = self.sort_items(dirs)
        files = self.sort_items(files)

        for item_data in parent:
            label = '[..  ] Parent'
            data = {
                'type': 'fs_dir',
                'name': item_data['name'],
                'size': item_data['size'],
                'can_select': False
            }
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

        for item_data in dirs:
            mtime = item_data['mtime'].strftime('%Y-%m-%d %H:%M:%S') if item_data['mtime'] else ' ' * 19
            label = f'[DIR ] {item_data["name"]:40}  <DIR>           {mtime}'
            data = {
                'type': 'fs_dir',
                'name': item_data['name'],
                'size': item_data['size'],
                'mtime': item_data['mtime'],
                'can_select': True
            }
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

        for item_data in files:
            mtime = item_data['mtime'].strftime('%Y-%m-%d %H:%M:%S') if item_data['mtime'] else ' ' * 19
            label = f'[FILE] {item_data["name"]:40} {self.format_size(item_data["size"]):>10}         {mtime}'
            data = {
                'type': 'fs_file',
                'name': item_data['name'],
                'size': item_data['size'],
                'mtime': item_data['mtime'],
                'can_select': True
            }
            text = SelectableText(f'  {label}', data, self)
            self.walker.append(urwid.AttrMap(text, None, focus_map='selected'))

    def format_size(self, size):
        for unit in ['B  ', 'KB ', 'MB ', 'GB ']:
            if size < 1024.0:
                return f'{size:.1f}{unit}'
            size /= 1024.0
        return f'{size:.1f}TB'
