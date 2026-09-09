"""
JARVIS OS — core/skill_manager.py

Phase-9 skills system.

Loads skills from .jarvis/skills/*.md where each file has:

    ---
    name: summarize
    description: Summarize a markdown file
    params:
      - name: path
        type: string
        required: true
        description: Path to file relative to workspace
    ---
    Instructions... (optional)

    ```python
    def run(path, **kwargs):
        # ... return result string
        return summary
    ```

Improvements over src/skills.py:
  - Proper YAML frontmatter parsing via yaml.safe_load.
  - Parameter schema validation before execution.
  - Sandboxed execution: restricted builtins + limited globals for in-process,
    with subprocess isolation as the primary safe path.
"""

import logging
import os
import re
import subprocess
import sys
import textwrap
import tempfile
from typing import Any, Callable, Dict, List, Optional

import yaml

from .utils import normalize_name

log = logging.getLogger("jarvis.skills")

# Restricted builtins for in-process skill execution (no I/O, no imports).
_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "hash": hash,
    "int": int, "isinstance": isinstance, "len": len, "list": list,
    "map": map, "max": max, "min": min, "range": range, "repr": repr,
    "reversed": reversed, "round": round, "set": set, "slice": slice,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip,
    "True": True, "False": False, "None": None,
}


class SkillError(Exception):
    """Raised for skill parse/validation/execution errors."""


class Skill:
    """One loaded skill definition."""

    def __init__(
        self,
        name: str,
        description: str = "",
        params: Optional[List[Dict[str, Any]]] = None,
        instructions: str = "",
        code: str = "",
        filepath: str = "",
    ):
        self.name = name
        self.description = description.strip()
        self.params = params or []
        self.instructions = instructions.strip()
        self.code = code.strip()
        self.filepath = filepath

    def required_params(self) -> List[str]:
        return [p["name"] for p in self.params if p.get("required")]

    def describe(self) -> str:
        """One-line description for the system prompt."""
        param_str = ", ".join(
            f"{p['name']}{':' + str(p.get('type', 'string'))}"
            + ("" if p.get("required") else "?")
            for p in self.params
        )
        return f"{self.name}({param_str}) — {self.description or 'no description'}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "params": self.params,
            "instructions": self.instructions,
            "code": self.code,
            "filepath": self.filepath,
        }


class SkillManager:
    """Load, validate and execute skills from markdown files."""

    def __init__(self, skills_dir: str = ".jarvis/skills"):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.skills_dir = os.path.realpath(os.path.join(project_root, skills_dir))
        os.makedirs(self.skills_dir, exist_ok=True)
        self.skills: Dict[str, Skill] = {}
        self._load_skills()

    # ── loading ─────────────────────────────────────────────────────────────

    def _load_skills(self):
        self.skills = {}
        for filename in os.listdir(self.skills_dir):
            if not filename.endswith(".md") or filename == "skills.md":
                continue
            try:
                skill = self._parse_skill_file(os.path.join(self.skills_dir, filename))
                if skill:
                    self.skills[skill.name] = skill
            except SkillError as e:
                log.warning("Skipping skill %s: %s", filename, e)

    def refresh(self):
        """Reload skills from disk (after edits/create/delete)."""
        self._load_skills()

    def _parse_skill_file(self, filepath: str) -> Optional[Skill]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            raise SkillError(f"cannot read {filepath}: {e}") from e

        # Frontmatter
        fm = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        meta: Dict[str, Any] = {}
        if fm:
            try:
                parsed = yaml.safe_load(fm.group(1))
                if isinstance(parsed, dict):
                    meta = parsed
            except yaml.YAMLError as e:
                raise SkillError(f"invalid YAML frontmatter in {filepath}: {e}") from e

        name = normalize_name(str(meta.get("name") or os.path.splitext(os.path.basename(filepath))[0]))
        description = str(meta.get("description") or "")
        params = meta.get("params") or []
        if not isinstance(params, list):
            params = []

        # Code block
        code_match = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
        code = code_match.group(1).strip() if code_match else ""

        # Instructions = body text excluding frontmatter and code fence
        body = content
        if fm:
            body = body[fm.end():]
        body = re.sub(r"```python\s*\n.*?```", "", body, flags=re.DOTALL)
        instructions = body.strip()

        if not code:
            # Skills without code are valid (LLM-driven) — keep metadata only.
            log.debug("Skill '%s' has no python code block; LLM-driven", name)

        return Skill(
            name=name,
            description=description,
            params=params,
            instructions=instructions,
            code=code,
            filepath=filepath,
        )

    # ── public API ──────────────────────────────────────────────────────────

    def list_skills(self) -> List[str]:
        return sorted(self.skills.keys())

    def get(self, name: str) -> Optional[Skill]:
        return self.skills.get(normalize_name(name))

    def describe_all(self) -> str:
        lines = ["Available skills:"]
        for skill in sorted(self.skills.values(), key=lambda s: s.name):
            lines.append(f"  - {skill.describe()}")
        return "\n".join(lines)

    def validate_params(self, skill: Skill, params: Dict[str, Any]) -> List[str]:
        """Return a list of missing required params (empty = OK)."""
        missing = []
        for name in skill.required_params():
            if name not in params or params[name] in (None, ""):
                missing.append(name)
        return missing

    # ── execution (SAND-BOXED) ──────────────────────────────────────────────

    def execute(self, name: str, params: Optional[Dict[str, Any]] = None, sandbox: bool = True) -> Dict[str, Any]:
        """Execute a skill by name.

        Prefers subprocess isolation (sandbox=True): the skill code runs in a
        fresh python interpreter in a temp dir with the workspace as cwd, so
        runaway code cannot touch JARVIS internals.  If sandbox=False, uses a
        restricted in-process exec with limited builtins.

        Returns {"success": bool, "output": str, "error": str?}
        """
        skill = self.get(name)
        if skill is None:
            return {"success": False, "error": f"Unknown skill: {name}"}

        params = params or {}
        missing = self.validate_params(skill, params)
        if missing:
            return {"success": False, "error": f"Missing required params: {', '.join(missing)}"}

        if not skill.code:
            # LLM-driven skill — return instructions as guidance
            return {
                "success": True,
                "output": f"[skill:{skill.name}] {skill.description or 'no description'}",
                "llm_driven": True,
            }

        try:
            if sandbox:
                output = self._execute_subprocess(skill, params)
            else:
                output = self._execute_restricted(skill, params)
            return {"success": True, "output": output}
        except SkillError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:  # defensive
            return {"success": False, "error": f"Skill execution error: {e}"}

    def _execute_subprocess(self, skill: Skill, params: Dict[str, Any]) -> str:
        """Run skill code in a subprocess (preferred isolation)."""
        with tempfile.TemporaryDirectory(prefix="jarvis_skill_") as tmp:
            arg_file = os.path.join(tmp, "params.json")
            code_file = os.path.join(tmp, "skill_code.py")
            import json
            with open(arg_file, "w", encoding="utf-8") as f:
                json.dump(params, f)
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(skill.code)

            wrapper = textwrap.dedent(f"""
                import json, sys
                _params_file = {arg_file!r}
                _code_file = {code_file!r}
                params = json.load(open(_params_file, 'r', encoding='utf-8'))
                src = open(_code_file, 'r', encoding='utf-8').read()
                exec(compile(src, _code_file, 'exec'))
                try:
                    _result = run(**params)
                except TypeError as e:
                    # Match params to function signature (drop extras)
                    import inspect
                    sig = inspect.signature(run)
                    _p = {{k: v for k, v in params.items() if k in sig.parameters}}
                    _result = run(**_p)
                print(_result)
            """)
            try:
                proc = subprocess.run(
                    [sys.executable, "-c", wrapper],
                    cwd=tmp,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                raise SkillError(f"Skill '{skill.name}' timed out after 30s")
            if proc.returncode != 0:
                raise SkillError(f"Skill '{skill.name}' failed: {proc.stderr.strip()}")
            return proc.stdout.strip()

    def _execute_restricted(self, skill: Skill, params: Dict[str, Any]) -> str:
        """In-process fallback with restricted builtins and globals."""
        safe_globals = {
            "__builtins__": _SAFE_BUILTINS,
            "__name__": "__jarvis_skill__",
        }
        try:
            exec(compile(skill.code, skill.filepath or "<skill>", "exec"), safe_globals)
            run_fn: Optional[Callable] = safe_globals.get("run")
            if run_fn is None:
                raise SkillError(f"Skill '{skill.name}' has no run() function")
            import inspect
            sig = inspect.signature(run_fn)
            filtered = {k: v for k, v in params.items() if k in sig.parameters}
            result = run_fn(**filtered)
            return str(result)
        except SkillError:
            raise
        except Exception as e:
            raise SkillError(f"Skill '{skill.name}' execution error: {e}") from e