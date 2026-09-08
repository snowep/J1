import os
from pathlib import Path


class FileManager:
    """JARVIS FileManager — CRUD operations within workspace."""

    def __init__(self, workspace_path='workspace'):
        self.workspace_dir = os.path.normpath(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), workspace_path)
        )
        os.makedirs(self.workspace_dir, exist_ok=True)

    def _validate(self, path):
        """Ensure path stays within workspace."""
        abs_path = os.path.normpath(
            path if os.path.isabs(path) else os.path.join(self.workspace_dir, path)
        )
        if not abs_path.startswith(self.workspace_dir + os.sep):
            return None
        if os.path.isdir(abs_path):
            abs_path = os.path.join(abs_path, 'index.md')
        return abs_path

    def write(self, file_name, content, overwrite=False):
        """Write content to a file."""
        abs_path = self._validate(file_name)
        if not abs_path:
            return {'success': False, 'error': 'Invalid path'}
        if os.path.exists(abs_path) and not overwrite:
            return {'success': False, 'error': f'File exists: {file_name}'}
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {'success': True, 'message': f'Written: {file_name}', 'path': abs_path}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def read(self, file_path, start=1, end=None):
        """Read file content with optional line range."""
        abs_path = self._validate(file_path)
        if not abs_path or not os.path.exists(abs_path):
            return {'success': False, 'error': 'File not found'}
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            total = len(lines)
            start_idx = max(0, start - 1)
            end_idx = total if end is None else min(total, end)
            content = ''.join(lines[start_idx:end_idx]).rstrip('\n')
            return {'success': True, 'content': content, 'lines': total}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def edit(self, file_path, old_text, new_text, all_occurrences=False):
        """Replace text in a file."""
        abs_path = self._validate(file_path)
        if not abs_path or not os.path.exists(abs_path):
            return {'success': False, 'error': 'File not found'}
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if old_text not in content:
                return {'success': False, 'error': 'Text not found'}
            new_content = content.replace(old_text, new_text) if all_occurrences \
                else content.replace(old_text, new_text, 1)
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return {'success': True, 'message': f'Edited: {file_path}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete(self, file_path):
        """Delete a file."""
        abs_path = self._validate(file_path)
        if not abs_path or not os.path.exists(abs_path):
            return {'success': False, 'error': 'File not found'}
        try:
            os.remove(abs_path)
            return {'success': True, 'message': f'Deleted: {file_path}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def list(self, directory=None):
        """List files and directories."""
        abs_dir = self._validate(directory) if directory else self.workspace_dir
        if not os.path.isdir(abs_dir):
            return {'success': False, 'error': 'Directory not found'}
        items = []
        for name in sorted(os.listdir(abs_dir)):
            path = os.path.join(abs_dir, name)
            items.append({'name': name, 'type': 'dir' if os.path.isdir(path) else 'file'})
        return {'success': True, 'items': items, 'path': abs_dir}