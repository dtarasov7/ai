
    def copy_items(self):
        source_panel = self.get_active_panel()
        dest_panel = self.get_inactive_panel()

        if source_panel.is_root_menu() or source_panel.is_endpoint_list():
            self.show_result('Cannot copy from this level')
            return

        if dest_panel.is_root_menu() or dest_panel.is_endpoint_list():
            self.show_result('Select destination first')
            return

        selected_items = source_panel.get_selected_items()
        if not selected_items:
            focused = source_panel.get_focused_item()
            if focused and focused['type'] in ('fs_file', 's3_file', 'fs_dir', 's3_dir', 'bucket'):
                selected_items = [focused]

        if not selected_items:
            self.show_result('No items to copy')
            return

        if dest_panel.is_bucket_list():
            has_files = any(item['type'] in ('fs_file', 's3_file') for item in selected_items)
            if has_files:
                self.show_result('Cannot copy files directly to bucket list!')
                return

        analyzed, items_info, total_bytes = self.analyze_items(selected_items, source_panel)
        self._show_copy_dialog(analyzed, source_panel, dest_panel, is_move=False, total_bytes=total_bytes)

    def move_items(self):
        source_panel = self.get_active_panel()
        dest_panel = self.get_inactive_panel()

        if source_panel.is_root_menu() or source_panel.is_endpoint_list():
            self.show_result('Cannot move from this level')
            return

        if dest_panel.is_root_menu() or dest_panel.is_endpoint_list():
            self.show_result('Select destination first')
            return

        selected_items = source_panel.get_selected_items()
        if not selected_items:
            focused = source_panel.get_focused_item()
            if focused and focused['type'] in ('fs_file', 's3_file', 'fs_dir', 's3_dir', 'bucket'):
                selected_items = [focused]

        if not selected_items:
            self.show_result('No items to move')
            return

        if dest_panel.is_bucket_list():
            has_files = any(item['type'] in ('fs_file', 's3_file') for item in selected_items)
            if has_files:
                self.show_result('Cannot move files directly to bucket list!')
                return

        analyzed, items_info, total_bytes = self.analyze_items(selected_items, source_panel)
        self._show_copy_dialog(analyzed, source_panel, dest_panel, is_move=True, total_bytes=total_bytes)

    def _show_copy_dialog(self, analyzed, source_panel, dest_panel, is_move=False, total_bytes=0):
        operation = 'Move' if is_move else 'Copy'

        if len(analyzed) == 1:
            item = analyzed[0]['item']
            source_desc = f'{operation} "{item["name"]}"'
        else:
            source_desc = f'{operation} {len(analyzed)} items'

        if len(analyzed) == 1:
            item = analyzed[0]['item']
            if dest_panel.is_bucket_list():
                dest_path = item['name'].lower().replace('_', '-')
            else:
                dest_base = dest_panel.get_current_path()
                if dest_base:
                    dest_path = dest_base.rstrip('/') + '/' + item['name']
                else:
                    dest_path = item['name']
        else:
            dest_path = dest_panel.get_current_path()

        def callback(confirmed, target_name):
            self.close_dialog()
            if not confirmed:
                return

            if not target_name:
                target_name = dest_panel.get_current_path()

            current_item = source_panel.get_focused_item()
            focus_name = current_item.get('name') if current_item else None

            self.overwrite_all = False
            self.version_all = False
            self.skip_all = False

            self._do_copy_with_progress(analyzed, source_panel, dest_panel, target_name, focus_name, is_move=is_move, total_bytes=total_bytes)

        dialog = CopyMoveDialog(operation, source_desc, dest_path, callback)
        self.show_dialog(dialog)

    def _check_overwrite(self, filename, source_info, dest_info, callback, is_s3_dest=False):
        """Показать диалог подтверждения перезаписи"""
        dialog = OverwriteDialog(filename, source_info, dest_info, callback, show_version_options=is_s3_dest)
        self.show_dialog(dialog)
