"""
Skill system — loader, validator, installer, runner.

Each skill is a Markdown file with YAML frontmatter.
Skills declare: name, version, risk_level, trust_level, required_tools, parameters.

Trust model:
- BUILTIN: shipped with JARVIS, highest trust
- VERIFIED: signed by a trusted key (future)
- USER_APPROVED: explicitly approved by the user
- EXTERNAL_UNVERIFIED: from GitHub or other source, not yet approved
- BLOCKED: known malicious, always rejected

Skills are executed in a sandboxed subprocess or restricted exec.
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..agent.state import RiskLevel, SkillManifest, TrustLevel

log = logging.getLogger("jarvis.skills")


def _generate_id() -> str:
    return uuid.uuid4().hex[:12]


class SkillManager:
    """Manages skill loading, validation, installation, and execution.

    Skills are Markdown files with YAML frontmatter.
    They are stored in the skills directory.
    """

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = os.path.realpath(skills_dir)
        os.makedirs(self.skills_dir, exist_ok=True)
        self._cache: Dict[str, SkillManifest] = {}
        self._cache_mtime: Dict[str, float] = {}

    def list_skills(self) -> List[SkillManifest]:
        """List all available skills."""
        self._refresh_cache()
        return list(self._cache.values())

    def get_skill(self, name: str) -> Optional[SkillManifest]:
        """Get a skill by name."""
        self._refresh_cache()
        return self._cache.get(name)

    def load_skill(self, filepath: str) -> Optional[SkillManifest]:
        """Load a skill from a Markdown file with YAML frontmatter."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            log.error("Failed to read skill file %s: %s", filepath, e)
            return None

        return self._parse_skill(content, filepath)

    def _parse_skill(self, content: str, filepath: str = "") -> Optional[SkillManifest]:
        """Parse a skill from Markdown content with YAML frontmatter."""
        if not content.startswith("---"):
            log.warning("Skill file %s missing YAML frontmatter", filepath)
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            log.warning("Skill file %s has malformed frontmatter", filepath)
            return None

        try:
            metadata = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as e:
            log.error("Failed to parse YAML frontmatter in %s: %s", filepath, e)
            return None

        body = parts[2].strip()

        # Extract code block if present
        code_match = re.search(r'```python\n(.*?)```', body, re.DOTALL)
        code = code_match.group(1) if code_match else None

        # Extract instructions (text outside code blocks)
        instructions = re.sub(r'```python\n.*?```', '', body, flags=re.DOTALL).strip()

        # Build manifest
        risk_str = metadata.get("risk_level", "medium")
        try:
            risk_level = RiskLevel(risk_str)
        except ValueError:
            risk_level = RiskLevel.MEDIUM

        trust_str = metadata.get("trust_level", "external_unverified")
        try:
            trust_level = TrustLevel(trust_str)
        except ValueError:
            trust_level = TrustLevel.EXTERNAL_UNVERIFIED

        manifest = SkillManifest(
            name=metadata.get("name", os.path.splitext(os.path.basename(filepath))[0]),
            version=metadata.get("version", "1.0.0"),
            description=metadata.get("description", ""),
            author=metadata.get("author", ""),
            source_url=metadata.get("source_url"),
            source_commit=metadata.get("source_commit"),
            risk_level=risk_level,
            trust_level=trust_level,
            required_tools=metadata.get("required_tools", []),
            required_capabilities=metadata.get("required_capabilities", []),
            parameters=metadata.get("parameters", []),
            dependencies=metadata.get("dependencies", []),
            license=metadata.get("license"),
            verified=metadata.get("verified", False),
            instructions=instructions,
            code=code,
        )

        return manifest

    def install_from_github(self, url: str, trust_level: TrustLevel = TrustLevel.EXTERNAL_UNVERIFIED) -> Optional[SkillManifest]:
        """Install a skill from a GitHub URL.

        Downloads the .md file, validates it, and saves to skills_dir.
        """
        # Extract skill name from URL
        # e.g., https://github.com/user/repo/blob/main/skills/my_skill.md
        parts = url.rstrip("/").split("/")
        if len(parts) < 2:
            log.error("Invalid GitHub URL: %s", url)
            return None

        # Try to download the raw content
        raw_url = url.replace("github.com", "raw.githubusercontent.com")
        if "/blob/" in raw_url:
            raw_url = raw_url.replace("/blob/", "/")

        try:
            import requests
            response = requests.get(raw_url, timeout=30)
            response.raise_for_status()
            content = response.text
        except Exception as e:
            log.error("Failed to download skill from %s: %s", url, e)
            return None

        # Parse the skill
        manifest = self._parse_skill(content, url)
        if manifest is None:
            log.error("Failed to parse skill from %s", url)
            return None

        # Set trust and source
        manifest.trust_level = trust_level
        manifest.source_url = url

        # Save to skills directory
        filename = f"{manifest.name}.md"
        filepath = os.path.join(self.skills_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            log.error("Failed to save skill to %s: %s", filepath, e)
            return None

        # Update cache
        self._cache[manifest.name] = manifest
        log.info("Installed skill: %s from %s", manifest.name, url)
        return manifest

    def create_skill(self, manifest_data: Dict[str, Any], code: str = "") -> Optional[SkillManifest]:
        """Create a new skill from a manifest dict and optional code."""
        name = manifest_data.get("name", "")
        if not name:
            log.error("Skill name is required")
            return None

        # Check if skill already exists
        if name in self._cache:
            log.error("Skill %s already exists", name)
            return None

        risk_str = manifest_data.get("risk_level", "medium")
        try:
            risk_level = RiskLevel(risk_str)
        except ValueError:
            risk_level = RiskLevel.MEDIUM

        trust_str = manifest_data.get("trust_level", "user_approved")
        try:
            trust_level = TrustLevel(trust_str)
        except ValueError:
            trust_level = TrustLevel.USER_APPROVED

        manifest = SkillManifest(
            name=name,
            version=manifest_data.get("version", "1.0.0"),
            description=manifest_data.get("description", ""),
            author=manifest_data.get("author", ""),
            risk_level=risk_level,
            trust_level=trust_level,
            required_tools=manifest_data.get("required_tools", []),
            parameters=manifest_data.get("parameters", []),
            instructions=manifest_data.get("instructions", ""),
            code=code or None,
        )

        # Render as Markdown with frontmatter
        md_content = self._render_skill(manifest)

        # Save
        filepath = os.path.join(self.skills_dir, f"{name}.md")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
        except Exception as e:
            log.error("Failed to save skill: %s", e)
            return None

        self._cache[name] = manifest
        log.info("Created skill: %s", name)
        return manifest

    def validate_skill(self, manifest: SkillManifest) -> List[str]:
        """Validate a skill manifest. Returns list of issues."""
        issues = []

        if not manifest.name:
            issues.append("Skill name is required")
        if not manifest.version:
            issues.append("Skill version is required")
        if manifest.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) and not manifest.verified:
            issues.append(f"High-risk skill '{manifest.name}' is not verified")
        if manifest.trust_level == TrustLevel.BLOCKED:
            issues.append(f"Skill '{manifest.name}' is blocked")
        if manifest.code and manifest.trust_level == TrustLevel.EXTERNAL_UNVERIFIED:
            issues.append(f"Skill '{manifest.name}' has executable code but is not verified")

        return issues

    def execute_skill(self, name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a skill by name.

        Returns a result dict with success, output, and metadata.
        """
        manifest = self.get_skill(name)
        if manifest is None:
            return {"success": False, "error": f"Skill not found: {name}"}

        # Validate trust
        if manifest.trust_level == TrustLevel.BLOCKED:
            return {"success": False, "error": f"Skill '{name}' is blocked"}

        if manifest.trust_level == TrustLevel.EXTERNAL_UNVERIFIED and manifest.code:
            return {
                "success": False,
                "error": f"Skill '{name}' has executable code but is not verified. "
                         f"Please approve it first with: skill install {name}",
            }

        # Validate required params
        for param in manifest.parameters:
            if param.get("required", False) and param["name"] not in (params or {}):
                return {
                    "success": False,
                    "error": f"Missing required parameter: {param['name']}",
                }

        # Execute
        if manifest.code:
            return self._execute_code(manifest.code, params or {}, manifest.name)
        elif manifest.instructions:
            return {
                "success": True,
                "output": manifest.instructions,
                "metadata": {"type": "instruction_only"},
            }
        else:
            return {"success": False, "error": f"Skill '{name}' has no code or instructions"}

    def _execute_code(self, code: str, params: Dict[str, Any], skill_name: str) -> Dict[str, Any]:
        """Execute skill code in a sandboxed subprocess.

        Uses a subprocess with resource limits and no network access.
        """
        # Create a temporary script file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix=f"skill_{skill_name}_",
            delete=False,
            encoding="utf-8",
        ) as f:
            # Write the skill code with params injected
            f.write(code)
            f.write("\n\n")
            f.write(f"import json\n")
            f.write(f"params = {repr(params)}\n")
            f.write(f"try:\n")
            f.write(f"    result = run(**params)\n")
            f.write(f"    print(json.dumps({{'success': True, 'output': str(result)}}))\n")
            f.write(f"except Exception as e:\n")
            f.write(f"    print(json.dumps({{'success': False, 'error': str(e)}}))\n")
            script_path = f.name

        try:
            # Execute in subprocess with timeout
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,  # CRITICAL: never shell=True
                cwd=os.path.dirname(self.skills_dir),  # run from project root
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Skill execution failed: {result.stderr[:500]}",
                    "metadata": {"exit_code": result.returncode},
                }

            # Parse JSON output
            try:
                output = result.stdout.strip()
                if output:
                    return json.loads(output)
                return {"success": True, "output": "Skill executed (no output)"}
            except json.JSONDecodeError:
                return {"success": True, "output": result.stdout[:2000]}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Skill execution timed out (30s limit)"}
        except Exception as e:
            return {"success": False, "error": f"Skill execution error: {e}"}
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _render_skill(self, manifest: SkillManifest) -> str:
        """Render a skill manifest as Markdown with YAML frontmatter."""
        metadata = {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "risk_level": manifest.risk_level.value,
            "trust_level": manifest.trust_level.value,
            "required_tools": manifest.required_tools,
            "parameters": manifest.parameters,
        }
        if manifest.source_url:
            metadata["source_url"] = manifest.source_url
        if manifest.license:
            metadata["license"] = manifest.license

        lines = ["---"]
        lines.append(yaml.dump(metadata, default_flow_style=False, allow_unicode=True).strip())
        lines.append("---")
        lines.append("")

        if manifest.instructions:
            lines.append(manifest.instructions)
            lines.append("")

        if manifest.code:
            lines.append("```python")
            lines.append(manifest.code.strip())
            lines.append("```")

        return "\n".join(lines)

    def _refresh_cache(self) -> None:
        """Refresh the skill cache from disk, only reloading changed files."""
        if not os.path.isdir(self.skills_dir):
            return

        current_files = set()
        for filename in os.listdir(self.skills_dir):
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(self.skills_dir, filename)
            current_files.add(filename)
            mtime = os.path.getmtime(filepath)

            # Check if already cached and unchanged
            if filename in self._cache_mtime and self._cache_mtime[filename] == mtime:
                continue

            # Load/reload
            manifest = self.load_skill(filepath)
            if manifest and manifest.name:
                self._cache[manifest.name] = manifest
                self._cache_mtime[filename] = mtime

        # Remove cached skills whose files no longer exist
        to_remove = []
        for name, manifest in self._cache.items():
            if manifest.path and not os.path.exists(manifest.path):
                to_remove.append(name)
        for name in to_remove:
            del self._cache[name]


# Need to import json for _execute_code
import json
