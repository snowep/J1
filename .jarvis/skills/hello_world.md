---
name: hello_world
description: Print a greeting message. Use when the user asks to use the hello world skill or greet with a custom message.
---

# Hello World Skill

## Instructions

When invoked, greet the user with the provided message. If no message is given, use "Hello from JARVIS!".

## Parameters

- `message` (optional): The greeting message to print.

## Code

```python
def run(message="Hello from JARVIS!", **kwargs):
    """Print a greeting message."""
    return f"[GREETING] {message}"
```
