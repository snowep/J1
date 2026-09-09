"""Create __init__.py files for all jarvis subpackages."""
import os

docs = {
    "jarvis/policy": "JARVIS policy package — permission engine, capability registry, risk.",
    "jarvis/tools": "JARVIS tools package — registry, base, and tool implementations.",
    "jarvis/sandbox": "JARVIS sandbox package — process, filesystem, network isolation.",
    "jarvis/memory": "JARVIS memory package — Markdown-first canonical store.",
    "jarvis/llm": "JARVIS LLM package — client, schemas, providers.",
    "jarvis/llm/providers": "JARVIS LLM providers package.",
    "jarvis/skills": "JARVIS skills package — loader, registry, validator, installer, runner.",
    "jarvis/audit": "JARVIS audit package — events, logger, store.",
    "jarvis/config": "JARVIS config package — loader, schema, defaults.",
    "jarvis/dashboard": "JARVIS dashboard package.",
}

for path, doc in docs.items():
    os.makedirs(path, exist_ok=True)
    init_file = os.path.join(path, "__init__.py")
    with open(init_file, "w", encoding="utf-8") as f:
        f.write(f'"""{doc}"""\n')

print("Created", len(docs), "package init files")