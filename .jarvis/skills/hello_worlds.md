```markdown
---
name: hello_worlds
description: A simple skill that prints a greeting message
---

## Instructions
This skill prints a friendly "Hello, World!" message. It can optionally include a custom name to personalize the greeting.

## Parameters
- **name** (optional, string): A name to include in the greeting. Defaults to "World" if not provided.

```python
def run(name: str = "World") -> str:
    """
    Print and return a greeting message.
    
    Args:
        name: The name to greet (default: "World")
    
    Returns:
        The greeting message string
    """
    message = f"Hello, {name}! Welcome to JARVIS OS."
    print(message)
    return message
```