# JARVIS Skills Index

*Each skill is a separate `.md` file in this directory. Skills are loaded at startup by `SkillManager`.*

---

## Available Skills

| Skill | File | Description |
|-------|------|-------------|
| `hello_world` | [hello_world.md](hello_world.md) | Print a greeting message |
| `hello_worlds` | [hello_worlds.md](hello_worlds.md) | Print a greeting message (user-created) |
| `file_crud` | [file_crud.md](file_crud.md) | Create, read, edit, delete, list files |
| `summarize` | [summarize.md](summarize.md) | Summarize a file or list summaries |
| `code_writer` | [code_writer.md](code_writer.md) | Write Python code to a file |

---

## How to Add a New Skill

1. Create a new `.md` file in `.jarvis/skills/`
2. Add YAML frontmatter with `name` and `description`
3. Add instructions and a Python code block
4. Restart JARVIS — the skill is auto-detected

### Skill File Template

```markdown
---
name: my_skill
description: What this skill does
---

# My Skill

## Instructions

When to use and how it works.

## Parameters

- `param1` (required): Description
- `param2` (optional): Description

## Code

```python
def run(param1, param2="default", **kwargs):
    """Execute the skill."""
    return f"Result: {param1}"
```
```

---

*Skills are model-invokable via `{"type": "skill", "skill": "name", "params": {...}}`.*