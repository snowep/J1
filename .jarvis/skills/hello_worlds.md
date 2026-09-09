```markdown
---
name: hello_worlds
description: A simple greeting skill that prints a friendly message and demonstrates basic arithmetic
---

## Instructions

This skill prints a friendly "Hello, Worlds!" message to the console and displays the result of 2+2. It's a basic demonstration skill that can be used to verify the skill system is working correctly.

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| name | string | No | "World" | The name to include in the greeting |

## Code

```python
def run(name="World"):
    """
    Print a friendly greeting message and show the result of 2+2.
    
    Args:
        name (str): The name to greet. Defaults to "World".
    
    Returns:
        dict: A result containing the greeting message and arithmetic result.
    """
    greeting = f"Hello, {name}! 👋"
    print(greeting)
    
    # Calculate and display the result of 2+2
    a = 2
    b = 2
    result = a + b
    print(f"\n--- Arithmetic Result ---")
    print(f"{a} + {b} = {result}")
    print(f"------------------------")
    
    return {
        "status": "success",
        "message": greeting,
        "arithmetic": f"{a} + {b} = {result}",
        "result": result
    }
```
```

The skill now more prominently displays the result of 2+2 (which is, of course, **4**). I've:

- Added explicit `a` and `b` variables for clarity
- Added a formatted output block with separators
- Included the full arithmetic expression in the return dictionary
- Added a `result` field for easy programmatic access

A simple but elegant calculation, if I do say so myself. 🧮