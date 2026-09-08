---
name: file_crud
description: Create, read, edit, delete, and list files in the workspace. Use when the user asks to create a file, read a file, edit a file, delete a file, or list files.
---

# File CRUD Skill

## Instructions

Manage files in the workspace:
- `create`: Write a new file with content
- `read`: Display file contents
- `edit`: Replace text in an existing file
- `delete`: Remove a file
- `list`: Show directory contents

## Parameters

- `action` (required): One of: create, read, edit, delete, list
- `filename` (required): Target file path (relative to workspace/)
- `content` (optional): File content (for create)
- `old` (optional): Text to find (for edit)
- `new` (optional): Replacement text (for edit)

## Code

```python
def run(action, filename="", content="", old="", new="", **kwargs):
    """Execute a file operation."""
    import os
    workspace = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workspace')
    filepath = os.path.join(workspace, filename)
    
    if action == 'create':
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"✅ Created {filename}"
    elif action == 'read':
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    elif action == 'edit':
        with open(filepath, 'r', encoding='utf-8') as f:
            data = f.read()
        data = data.replace(old, new, 1)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(data)
        return f"✅ Edited {filename}"
    elif action == 'delete':
        os.remove(filepath)
        return f"✅ Deleted {filename}"
    elif action == 'list':
        files = os.listdir(workspace)
        return '\\n'.join(files) if files else "No files"
    else:
        return f"❌ Unknown action: {action}"
```
