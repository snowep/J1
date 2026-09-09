```markdown
---
name: to
description: Audit JARVIS skills — validates structure, YAML frontmatter, required sections, and Python code blocks across all installed skills.
---

# Instructions

You are auditing the JARVIS skill library. When this skill is invoked, perform a comprehensive health check on every skill file in the `skills/` directory.

## What to Check Per Skill

1. **YAML Frontmatter** — Must contain `name` and `description` fields.
2. **Required Sections** — Must include `# Instructions`, `## Parameters`, and a Python code block containing a `run()` function.
3. **Python Validity** — The embedded Python code block must parse without syntax errors.
4. **run() Signature** — The `run()` function must be present and callable.
5. **File Naming** — Skill filename should match the `name` field in frontmatter (slugified).

## Output

Return a summary table of all skills with a PASS/FAIL status per check, followed by any actionable recommendations.

---

## Parameters

| Parameter  | Type   | Required | Description                                      |
|------------|--------|----------|--------------------------------------------------|
| `verbose`  | string | No       | Set to `true` for per-skill detailed output.     |
| `fix`      | string | No       | Set to `true` to auto-generate missing stubs.    |

---

```python
import os
import re
import yaml
import ast
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent

def extract_frontmatter(text):
    """Extract YAML frontmatter from markdown."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if match:
        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None
    return None

def extract_code_blocks(text):
    """Extract all Python code blocks."""
    pattern = r"```python\s*\n(.*?)```"
    return re.findall(pattern, text, re.DOTALL)

def has_section(text, header):
    """Check if markdown contains a specific header."""
    return re.search(rf"^#+\s*{re.escape(header)}", text, re.MULTILINE) is not None

def validate_python(code):
    """Check if Python code parses and contains run()."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        issues.append(f"SyntaxError: {e}")
        return issues

    has_run = any(
        isinstance(node, ast.FunctionDef) and node.name == "run"
        for node in ast.walk(tree)
    )
    if not has_run:
        issues.append("Missing `run()` function")

    return issues

def audit_skill(filepath):
    """Audit a single skill file."""
    result = {"file": filepath.name, "checks": {}, "issues": []}

    text = filepath.read_text(encoding="utf-8")

    # Check 1: YAML Frontmatter
    fm = extract_frontmatter(text)
    if fm is None:
        result["checks"]["frontmatter"] = "FAIL — missing or malformed"
        result["issues"].append("No valid YAML frontmatter found")
    else:
        missing = [k for k in ("name", "description") if k not in fm]
        if missing:
            result["checks"]["frontmatter"] = f"FAIL — missing fields: {missing}"
            result["issues"].append(f"Frontmatter missing: {', '.join(missing)}")
        else:
            result["checks"]["frontmatter"] = "PASS"

    # Check 2: Required sections
    sections_ok = True
    missing_sections = []
    for sec in ("Instructions", "Parameters"):
        if not has_section(text, sec):
            sections_ok = False
            missing_sections.append(sec)
    if sections_ok:
        result["checks"]["sections"] = "PASS"
    else:
        result["checks"]["sections"] = f"FAIL — missing: {missing_sections}"

    # Check 3: Python code block validity
    code_blocks = extract_code_blocks(text)
    if not code_blocks:
        result["checks"]["python_code"] = "FAIL — no Python code block found"
    else:
        all_issues = []
        for block in code_blocks:
            all_issues.extend(validate_python(block))
        if all_issues:
            result["checks"]["python_code"] = f"FAIL — {'; '.join(all_issues)}"
            result["issues"].extend(all_issues)
        else:
            result["checks"]["python_code"] = "PASS"

    # Check 4: Filename matches name
    if fm and "name" in fm:
        slug = re.sub(r"[^a-z0-9]+", "_", fm["name"].lower()).strip("_")
        expected = slug + ".md"
        actual = filepath.name
        if actual == expected:
            result["checks"]["filename"] = "PASS"
        else:
            result["checks"]["filename"] = f"FAIL — expected '{expected}', got '{actual}'"

    return result

def run(verbose="false", fix="false"):
    """Audit all JARVIS skills."""
    verbose = str(verbose).lower() == "true"
    fix = str(fix).lower() == "true"

    skill_files = sorted(SKILLS_DIR.glob("*.md"))
    if not skill_files:
        return "No skill files found in skills/ directory."

    results = [audit_skill(fp) for fp in skill_files]

    # Build output
    lines = ["# 🔍 JARVIS Skill Audit Report\n"]
    lines.append(f"Scanned **{len(results)}** skill(s)\n")
    lines.append("| Skill | Frontmatter | Sections | Python Code | Filename |")
    lines.append("|-------|-------------|----------|-------------|----------|")

    passed = 0
    failed = 0

    for r in results:
        checks = r["checks"]
        row = f"| {r['file']} "
        for key in ("frontmatter", "sections", "python_code", "filename"):
            val = checks.get(key, "N/A")
            row += f"| {val} "
        row += "|"
        lines.append(row)

        if any("FAIL" in v for v in checks.values()):
            failed += 1
            if verbose and r["issues"]:
                lines.append(f"  ↳ Issues: {'; '.join(r['issues'])}")
        else:
            passed += 1

    lines.append(f"\n**Result: {passed} passed, {failed} failed**")

    if failed == 0:
        lines.append("\n✅ All skills are healthy. Carry on, boss.")
    else:
        lines.append("\n⚠️ Some skills need attention. See details above.")

    return "\n".join(lines)
```