---
name: summarize
description: Summarize a file or list the existing summaries. Use when the user asks to summarize a file or list summaries.
---

# Summarize Skill

## Instructions

Read the specified file from the workspace and produce a concise summary. Save the summary to `workspace/summaries/summary_<filename>.md`.

## Parameters

- `filename` (required): The file to summarize (relative to workspace/)
- `style` (optional): `concise` (default), `bullets`, `mindmap`

## Code

```python
def run(filename, style="concise", **kwargs):
    """Summarize a file."""
    from src.summarizer import Summarizer
    summarizer = Summarizer(summaries_path='workspace/summaries')
    result = summarizer.summarize_file(filename, style=style)
    return result.get('message', 'Summary created') if result.get('success') else f"Error: {result.get('error')}"
```