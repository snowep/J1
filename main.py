"""JARVIS OS — new entry point for Phase 10 architecture.

Runs the full stack: policy-gated tools, memory, agent loop.
"""
import sys
sys.path.insert(0, ".")

from jarvis.config.loader import Config
from jarvis.tools.registry import create_default_registry
from jarvis.policy.engine import PolicyEngine
from jarvis.tools.executor import ToolExecutor
from jarvis.memory.store import MemoryStore
from jarvis.audit.events import AuditLogger
from jarvis.agent.loop import AgentLoop


def main():
    print("JARVIS OS 1.0 — Type 'exit' to quit.")

    # Load config
    try:
        config = Config.load("config.yaml")
    except Exception as e:
        print(f"Config error: {e}; using defaults")
        config = Config.load()

    # Build the stack
    registry = create_default_registry()
    policy = PolicyEngine(permissions=config.permissions, tool_registry=registry)

    from jarvis.tools.filesystem import FilesystemTool
    from jarvis.tools.terminal import TerminalTool
    from jarvis.tools.internet import InternetTool
    from jarvis.self.model import SelfModelStore
    from jarvis.skills.manager import SkillManager

    fs = FilesystemTool(workspace=config.paths.get("workspace", "workspace"))
    term = TerminalTool(workspace=config.paths.get("workspace", "workspace"))
    net = InternetTool()
    mem = MemoryStore(memory_dir=config.paths.get("memory", "memory"))
    audit = AuditLogger(audit_dir=config.paths.get("audit", "memory/audit"))
    self_store = SelfModelStore(
        memory_dir=config.paths.get("memory", "memory/self-model"))
    skill_mgr = SkillManager(skills_dir=".jarvis/skills")

    executor = ToolExecutor(registry=registry, policy=policy)
    for name, handler in [
        ("fs.list", fs.list), ("fs.read", fs.read), ("fs.write", fs.write),
        ("fs.delete", fs.delete), ("fs.mkdir", fs.mkdir), ("fs.move", fs.move),
        ("fs.copy", fs.copy), ("fs.search", fs.search),
        ("terminal.run", term.execute),
    ]:
        executor.register_handler(name, handler)

    agent = AgentLoop(config=config, tool_registry=registry,
                     executor=executor, memory=mem, audit=audit)

    # simple REPL
    while True:
        try:
            user_input = input("\nJARVIS> ").strip()
        except EOFError:
            break
        if not user_input or user_input.lower() in ("exit", "quit"):
            break

        out = agent.run(user_input)
        print(f"\n{out}")

        self_store.update_from_action("chat", True, [])

    print("\nGoodbye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())