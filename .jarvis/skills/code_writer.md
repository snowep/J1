---
name: code_writer
description: Write Python code to a file in the workspace. Use when the user asks to write a script, create a Python file, or generate code.
---

# Code Writer Skill

## Instructions

Write Python code to a specified file in the workspace. The skill will create or overwrite the file with the provided code content.

## Parameters

- `filename` (required): The target file name (relative to workspace/)
- `code` (required): The Python code content to write

## Code

```python
def run(filename, code, **kwargs):
    """Write Python code to a file."""
    import os
    workspace = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workspace')
    filepath = os.path.join(workspace, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)
    
    return f"✅ Created {filename} ({len(code)} bytes)"
```
