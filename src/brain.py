"""
JARVIS Brain - Handles loading and managing the .jarvis directory structure.
"""

import os
import re
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import hashlib
import time


class JarvisBrain:
    """Manages the JARVIS brain (.jarvis directory) including settings, skills, memory, etc."""
    
    def __init__(self, jarvis_path: str = '.jarvis'):
        self.jarvis_path = Path(jarvis_path).resolve()
        self.workspace_root = None  # Will be set by Agent
        self.cache_file = self.jarvis_path / '.cache.json'
        self.cache = self._load_cache()
        self.settings = {}
        self.manifest = {
            'skills': [],
            'agents': [],
            'commands': [],
            'hooks': [],
            'rules': [],
            'output_styles': [],
            'memory_summary': []
        }
        self.last_scan = 0
        
        # Ensure .jarvis directory structure exists
        self._ensure_structure()
        
        # Load settings and manifest on init
        self.reload()
    
    def _ensure_structure(self):
        """Ensure the .jarvis directory structure exists with placeholder files."""
        directories = [
            'skills', 'agents', 'commands', 'hooks', 'rules', 
            'output-styles', 'memory'
        ]
        
        for dir_name in directories:
            dir_path = self.jarvis_path / dir_name
            dir_path.mkdir(exist_ok=True)
            
            # Add a .gitkeep file to ensure the directory is tracked by git
            gitkeep = dir_path / '.gitkeep'
            if not gitkeep.exists():
                gitkeep.write_text('')
        
        # Ensure essential files exist
        essential_files = {
            'settings.md': self._default_settings(),
            'skills/skills.md': '# Available Skills\n\n*Skills will appear here as they are created.*\n',
            'memory/index.md': '# Memory Index\n\n*Memory entries will be indexed here.*\n',
            'index.md': '# JARVIS Capabilities Index\n\n*This file is auto-generated to show available capabilities.*\n',
            'statusline.md': '| Component | Status |\n|-----------|--------|\n| Git Branch | `unknown` |\n| Last Scan | `never` |\n',
        }
        
        for file_path, default_content in essential_files.items():
            full_path = self.jarvis_path / file_path
            if not full_path.exists():
                full_path.write_text(default_content, encoding='utf-8')
    
    def _default_settings(self) -> str:
        """Return default settings as YAML front matter."""
        return '''---
model:
  provider: openai
  name: auto
  api_base: http://localhost:20128/v1
  temperature: 0.2
  max_tokens: 5000
permissions:
  file_write: auto
  file_read: auto
  file_delete: auto
  file_list: auto
  terminal: ask
  internet: ask
workspace:
  root: workspace/
  memory_path: .jarvis/memory/
  internet_research: workspace/research/
  summaries: summaries/
personality:
  - Witty, slightly sardonic
  - British formality with dry humor
  - Concise, efficient, direct
  - Proactive — suggest next steps
behavioral_rules:
  - Always log significant operations to `log.md`
  - Preserve user's actual intent when parsing — never strip the real query
  - Save new facts to memory automatically
  - Update `memory/index.md` after any memory change
  - Ask for approval before terminal/internet operations
---

# JARVIS Settings

*This file defines JARVIS's core settings. Edit here to change behavior — no code changes needed.*

## Model Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| Provider | `openai` | LLM provider |
| Model | `auto` | Model name or 'auto' |
| API Base | `http://localhost:20128/v1` | OmniRoute endpoint |
| Temperature | `0.2` | Lower = more deterministic |
| Max Tokens | `5000` | Response length limit |

## Permissions

| Operation | Mode | Notes |
|-----------|------|-------|
| File Write | `auto` | Create/edit files without asking |
| File Read | `auto` | Read files without asking |
| File Delete | `auto` | Delete files without asking |
| File List | `auto` | List directory without asking |
| Terminal | `ask` | Require user approval for commands |
| Internet | `ask` | Require user approval for browsing |

## Workspace

- **Workspace Root**: `workspace/`
- **Memory Path**: `.jarvis/memory/`
- **Internet Research**: `workspace/research/`
- **Summaries**: `summaries/`

## Personality

- Witty, slightly sardonic
- British formality with dry humor
- Concise, efficient, direct
- Proactive — suggest next steps

## Behavioral Rules

1. Always log significant operations to `log.md`
2. Preserve user's actual intent when parsing — never strip the real query
3. Save new facts to memory automatically
4. Update `memory/index.md` after any memory change
5. Ask for approval before terminal/internet operations
'''
    
    def _load_cache(self) -> Dict:
        """Load cache from JSON file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_cache(self):
        """Save cache to JSON file."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception:
            pass  # Non-critical
    
    def _is_cached_and_fresh(self, file_path: Path) -> bool:
        """Check if file is in cache and hasn't changed."""
        str_path = str(file_path)
        if str_path not in self.cache:
            return False
        
        try:
            current_mtime = file_path.stat().st_mtime
            cached_mtime = self.cache[str_path].get('mtime', 0)
            return current_mtime == cached_mtime
        except Exception:
            return False
    
    def _update_cache(self, file_path: Path, data: Any):
        """Update cache for a file."""
        str_path = str(file_path)
        try:
            mtime = file_path.stat().st_mtime
            self.cache[str_path] = {
                'mtime': mtime,
                'data': data,
                'cached_at': time.time()
            }
        except Exception:
            pass
    
    def _get_cached_data(self, file_path: Path) -> Optional[Any]:
        """Get cached data for a file if fresh."""
        str_path = str(file_path)
        if str_path in self.cache:
            try:
                current_mtime = file_path.stat().st_mtime
                cached_mtime = self.cache[str_path].get('mtime', 0)
                if current_mtime == cached_mtime:
                    return self.cache[str_path].get('data')
            except Exception:
                pass
        return None
    
    def _parse_yaml_front_matter(self, content: str) -> Tuple[Dict, str]:
        """Parse YAML front matter from markdown content.
        
        Returns:
            Tuple of (front_matter_dict, content_without_front_matter)
        """
        # Match YAML front matter between --- lines
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)
        
        if match:
            yaml_str = match.group(1)
            remaining_content = match.group(2)
            try:
                front_matter = yaml.safe_load(yaml_str) or {}
                return front_matter, remaining_content
            except yaml.YAMLError:
                # If YAML parsing fails, return empty front matter and full content
                return {}, content
        else:
            # No front matter found
            return {}, content
    
    def _extract_skill_metadata(self, skill_content: str, file_path: Path) -> Dict:
        """Extract metadata from a skill file."""
        # Try to parse YAML front matter
        front_matter, content = self._parse_yaml_front_matter(skill_content)
        
        # Extract name and description from front matter or content
        name = front_matter.get('name', file_path.stem.replace('_', ' ').title())
        description = front_matter.get('description', '')
        
        # If no description in front matter, try to extract from first heading or first paragraph
        if not description:
            # Look for first heading
            heading_match = re.search(r'^#+\s+(.+)$', content, re.MULTILINE)
            if heading_match:
                description = heading_match.group(1).strip()
            else:
                # Take first non-empty line that's not a heading
                lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
                if lines:
                    description = lines[0][:100]  # First 100 chars
        
        return {
            'name': name,
            'description': description.strip(),
            'file_path': str(file_path.relative_to(self.jarvis_path)),
            'front_matter': front_matter
        }
    
    def _scan_skills(self) -> List[Dict]:
        """Scan for skill files in .jarvis/skills/."""
        skills_dir = self.jarvis_path / 'skills'
        if not skills_dir.exists():
            return []
        
        skills = []
        for skill_file in skills_dir.glob('*.md'):
            # Skip the skills.md index file
            if skill_file.name == 'skills.md':
                continue
            
            # Check cache
            cached = self._get_cached_data(skill_file)
            if cached is not None:
                skills.append(cached)
                continue
            
            try:
                content = skill_file.read_text(encoding='utf-8')
                metadata = self._extract_skill_metadata(content, skill_file)
                self._update_cache(skill_file, metadata)
                skills.append(metadata)
            except Exception as e:
                # Log error but continue
                print(f"Warning: Could not read skill file {skill_file}: {e}")
        
        return skills
    
    def _scan_agents(self) -> List[Dict]:
        """Scan for agent files in .jarvis/agents/."""
        agents_dir = self.jarvis_path / 'agents'
        if not agents_dir.exists():
            return []
        
        agents = []
        for agent_file in agents_dir.glob('*.md'):
            cached = self._get_cached_data(agent_file)
            if cached is not None:
                agents.append(cached)
                continue
            
            try:
                content = agent_file.read_text(encoding='utf-8')
                # For agents, we might want different metadata extraction
                front_matter, content = self._parse_yaml_front_matter(content)
                name = front_matter.get('name', agent_file.stem.replace('_', ' ').title())
                description = front_matter.get('description', '')
                
                if not description:
                    heading_match = re.search(r'^#+\s+(.+)$', content, re.MULTILINE)
                    if heading_match:
                        description = heading_match.group(1).strip()
                    else:
                        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
                        if lines:
                            description = lines[0][:100]
                
                metadata = {
                    'name': name,
                    'description': description.strip(),
                    'file_path': str(agent_file.relative_to(self.jarvis_path)),
                    'front_matter': front_matter
                }
                self._update_cache(agent_file, metadata)
                agents.append(metadata)
            except Exception as e:
                print(f"Warning: Could not read agent file {agent_file}: {e}")
        
        return agents
    
    def _scan_commands(self) -> List[Dict]:
        """Scan for command files in .jarvis/commands/."""
        commands_dir = self.jarvis_path / 'commands'
        if not commands_dir.exists():
            return []
        
        commands = []
        for command_file in commands_dir.glob('*.md'):
            cached = self._get_cached_data(command_file)
            if cached is not None:
                commands.append(cached)
                continue
            
            try:
                content = command_file.read_text(encoding='utf-8')
                front_matter, content = self._parse_yaml_front_matter(content)
                name = front_matter.get('name', command_file.stem.replace('_', ' ').title())
                description = front_matter.get('description', '')
                
                if not description:
                    heading_match = re.search(r'^#+\s+(.+)$', content, re.MULTILINE)
                    if heading_match:
                        description = heading_match.group(1).strip()
                    else:
                        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
                        if lines:
                            description = lines[0][:100]
                
                metadata = {
                    'name': name,
                    'description': description.strip(),
                    'file_path': str(command_file.relative_to(self.jarvis_path)),
                    'front_matter': front_matter
                }
                self._update_cache(command_file, metadata)
                commands.append(metadata)
            except Exception as e:
                print(f"Warning: Could not read command file {command_file}: {e}")
        
        return commands
    
    def _scan_hooks(self) -> List[Dict]:
        """Scan for hook files in .jarvis/hooks/."""
        hooks_dir = self.jarvis_path / 'hooks'
        if not hooks_dir.exists():
            return []
        
        hooks = []
        for hook_file in hooks_dir.glob('*.md'):
            cached = self._get_cached_data(hook_file)
            if cached is not None:
                hooks.append(cached)
                continue
            
            try:
                content = hook_file.read_text(encoding='utf-8')
                front_matter, content = self._parse_yaml_front_matter(content)
                name = front_matter.get('name', hook_file.stem.replace('_', ' ').title())
                description = front_matter.get('description', '')
                
                if not description:
                    heading_match = re.search(r'^#+\s+(.+)$', content, re.MULTILINE)
                    if heading_match:
                        description = heading_match.group(1).strip()
                    else:
                        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
                        if lines:
                            description = lines[0][:100]
                
                metadata = {
                    'name': name,
                    'description': description.strip(),
                    'file_path': str(hook_file.relative_to(self.jarvis_path)),
                    'front_matter': front_matter
                }
                self._update_cache(hook_file, metadata)
                hooks.append(metadata)
            except Exception as e:
                print(f"Warning: Could not read hook file {hook_file}: {e}")
        
        return hooks
    
    def _scan_rules(self) -> List[Dict]:
        """Scan for rule files in .jarvis/rules/."""
        rules_dir = self.jarvis_path / 'rules'
        if not rules_dir.exists():
            return []
        
        rules = []
        for rule_file in rules_dir.glob('*.md'):
            cached = self._get_cached_data(rule_file)
            if cached is not None:
                rules.append(cached)
                continue
            
            try:
                content = rule_file.read_text(encoding='utf-8')
                front_matter, content = self._parse_yaml_front_matter(content)
                name = front_matter.get('name', rule_file.stem.replace('_', ' ').title())
                description = front_matter.get('description', '')
                
                if not description:
                    heading_match = re.search(r'^#+\s+(.+)$', content, re.MULTILINE)
                    if heading_match:
                        description = heading_match.group(1).strip()
                    else:
                        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
                        if lines:
                            description = lines[0][:100]
                
                metadata = {
                    'name': name,
                    'description': description.strip(),
                    'file_path': str(rule_file.relative_to(self.jarvis_path)),
                    'front_matter': front_matter
                }
                self._update_cache(rule_file, metadata)
                rules.append(metadata)
            except Exception as e:
                print(f"Warning: Could not read rule file {rule_file}: {e}")
        
        return rules
    
    def _scan_output_styles(self) -> List[Dict]:
        """Scan for output style files in .jarvis/output-styles/."""
        styles_dir = self.jarvis_path / 'output-styles'
        if not styles_dir.exists():
            return []
        
        styles = []
        for style_file in styles_dir.glob('*.md'):
            cached = self._get_cached_data(style_file)
            if cached is not None:
                styles.append(cached)
                continue
            
            try:
                content = style_file.read_text(encoding='utf-8')
                front_matter, content = self._parse_yaml_front_matter(content)
                name = front_matter.get('name', style_file.stem.replace('_', ' ').title())
                description = front_matter.get('description', '')
                
                if not description:
                    heading_match = re.search(r'^#+\s+(.+)$', content, re.MULTILINE)
                    if heading_match:
                        description = heading_match.group(1).strip()
                    else:
                        lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
                        if lines:
                            description = lines[0][:100]
                
                metadata = {
                    'name': name,
                    'description': description.strip(),
                    'file_path': str(style_file.relative_to(self.jarvis_path)),
                    'front_matter': front_matter
                }
                self._update_cache(style_file, metadata)
                styles.append(metadata)
            except Exception as e:
                print(f"Warning: Could not read output style file {style_file}: {e}")
        
        return styles
    
    def _load_memory_summaries(self, limit: int = 5) -> List[Dict]:
        """Load recent memory summaries from .jarvis/memory/."""
        memory_dir = self.jarvis_path / 'memory'
        if not memory_dir.exists():
            return []
        
        # Get all markdown files in memory directory, excluding index.md and README.md
        memory_files = []
        for ext in ('*.md',):
            memory_files.extend(memory_dir.glob(ext))
        
        # Filter out index and README
        memory_files = [f for f in memory_files if f.name not in ('index.md', 'README.md', 'decisions.md', 'error_log.md', 'lessons_learned.md', 'facts_user.md', 'error_patterns.json')]
        
        # Sort by modification time, newest first
        memory_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Take the most recent ones
        recent_files = memory_files[:limit]
        
        summaries = []
        for memory_file in recent_files:
            cached = self._get_cached_data(memory_file)
            if cached is not None:
                summaries.append(cached)
                continue
            
            try:
                content = memory_file.read_text(encoding='utf-8')
                # For memory files, we want to extract a summary
                front_matter, content = self._parse_yaml_front_matter(content)
                
                # Try to find a summary section
                summary = ''
                # Look for ## Summary or similar
                summary_match = re.search(r'^##\s+Summary\s*\n(.+?)(?:\n#|\n##|\Z)', content, re.DOTALL | re.IGNORECASE)
                if summary_match:
                    summary = summary_match.group(1).strip()
                else:
                    # Take first paragraph or first 200 characters
                    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
                    if paragraphs:
                        summary = paragraphs[0][:200] + ('...' if len(paragraphs[0]) > 200 else '')
                    else:
                        summary = content[:200] + ('...' if len(content) > 200 else '')
                
                metadata = {
                    'name': memory_file.stem.replace('_', ' ').title(),
                    'summary': summary,
                    'file_path': str(memory_file.relative_to(self.jarvis_path)),
                    'front_matter': front_matter,
                    'modified': datetime.fromtimestamp(memory_file.stat().st_mtime).isoformat()
                }
                self._update_cache(memory_file, metadata)
                summaries.append(metadata)
            except Exception as e:
                print(f"Warning: Could not read memory file {memory_file}: {e}")
        
        return summaries
    
    def _generate_index_md(self):
        """Generate or update .jarvis/index.md with the current manifest."""
        index_path = self.jarvis_path / 'index.md'
        
        # Build the index content
        lines = [
            '# JARVIS Capabilities Index\n',
            f'*Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*\n',
        ]
        
        # Skills section
        if self.manifest['skills']:
            lines.extend([
                '## Skills\n',
                'Available skills that can be invoked.\n',
            ])
            for skill in self.manifest['skills']:
                lines.append(f"- **{skill['name']}**: {skill['description']} (`{skill['file_path']}`)\n")
            lines.append('')
        
        # Agents section
        if self.manifest['agents']:
            lines.extend([
                '## Agents\n',
                'Specialized agents for specific tasks.\n',
            ])
            for agent in self.manifest['agents']:
                lines.append(f"- **{agent['name']}**: {agent['description']} (`{agent['file_path']}`)\n")
            lines.append('')
        
        # Commands section
        if self.manifest['commands']:
            lines.extend([
                '## Commands\n',
                'Predefined command templates.\n',
            ])
            for command in self.manifest['commands']:
                lines.append(f"- **{command['name']}**: {command['description']} (`{command['file_path']}`)\n")
            lines.append('')
        
        # Other sections (hooks, rules, output_styles) can be added similarly if needed
        # For brevity, we'll skip them in the index but they're in the manifest
        
        # Memory summary
        if self.manifest['memory_summary']:
            lines.extend([
                '## Recent Memory\n',
                'Recently accessed memory items.\n',
            ])
            for mem in self.manifest['memory_summary']:
                lines.append(f"- **{mem['name']}**: {mem['summary']} (`{mem['file_path']}`)\n")
            lines.append('')
        
        # Write the index file
        try:
            index_path.write_text('\n'.join(lines), encoding='utf-8')
            # Update cache for index.md
            self._update_cache(index_path, {'generated': True})
        except Exception as e:
            print(f"Warning: Could not write index.md: {e}")
    
    def _load_settings(self) -> Dict:
        """Load settings from .jarvis/settings.md with YAML front matter."""
        settings_path = self.jarvis_path / 'settings.md'
        cached = self._get_cached_data(settings_path)
        if cached is not None:
            return cached
        
        try:
            content = settings_path.read_text(encoding='utf-8')
            front_matter, _ = self._parse_yaml_front_matter(content)
            
            # If front matter is empty, try to parse the old table format as fallback
            if not front_matter:
                front_matter = self._parse_old_settings_format(content)
            
            self._update_cache(settings_path, front_matter)
            return front_matter
        except Exception as e:
            print(f"Warning: Could not load settings: {e}")
            return {}
    
    def _parse_old_settings_format(self, content: str) -> Dict:
        """Parse the old table-based settings format as fallback."""
        settings = {}
        # This is a simplified parser for the old format
        # In a real implementation, we would parse the markdown tables
        # For now, we'll return empty and rely on defaults
        return {}
    
    def scan_and_update(self, force: bool = False):
        """Scan the .jarvis directory and update manifest and settings.
        
        Args:
            force: If True, rescan everything ignoring cache.
        """
        # Check if we need to rescan based on cache timing
        if not force and (time.time() - self.last_scan) < 5:  # 5 seconds cache
            return
        
        # Reset manifest
        self.manifest = {
            'skills': [],
            'agents': [],
            'commands': [],
            'hooks': [],
            'rules': [],
            'output_styles': [],
            'memory_summary': []
        }
        
        # Scan each category
        self.manifest['skills'] = self._scan_skills()
        self.manifest['agents'] = self._scan_agents()
        self.manifest['commands'] = self._scan_commands()
        self.manifest['hooks'] = self._scan_hooks()
        self.manifest['rules'] = self._scan_rules()
        self.manifest['output_styles'] = self._scan_output_styles()
        self.manifest['memory_summary'] = self._load_memory_summaries(limit=5)
        
        # Load settings
        self.settings = self._load_settings()
        
        # Update last scan time
        self.last_scan = time.time()
        
        # Generate index.md
        self._generate_index_md()
        
        # Save cache
        self._save_cache()
    
    def get_capability_prompt(self) -> str:
        """Generate a prompt section describing available capabilities for the LLM."""
        lines = [
            "## Available Capabilities\n",
            "You have access to the following capabilities:\n",
        ]
        
        # Skills
        if self.manifest['skills']:
            lines.append("### Skills\n")
            for skill in self.manifest['skills']:
                lines.append(f"- {skill['name']}: {skill['description']}\n")
            lines.append("")
        
        # Agents
        if self.manifest['agents']:
            lines.append("### Agents\n")
            for agent in self.manifest['agents']:
                lines.append(f"- {agent['name']}: {agent['description']}\n")
            lines.append("")
        
        # Commands
        if self.manifest['commands']:
            lines.append("### Commands\n")
            for command in self.manifest['commands']:
                lines.append(f"- {command['name']}: {command['description']}\n")
            lines.append("")
        
        return "\n".join(lines)
    
    def get_memory_context(self, limit: int = 3) -> str:
        """Get a formatted string of recent memory summaries for the LLM context."""
        # Take the most recent memory summaries
        recent = self.manifest['memory_summary'][:limit]
        if not recent:
            return ""
        
        lines = ["## Recent Memory Context\n"]
        for mem in recent:
            lines.append(f"- {mem['name']}: {mem['summary']}\n")
        
        return "\n".join(lines)
    
    def get_settings(self) -> Dict:
        """Get the current settings."""
        return self.settings
    
    def get_permission(self, operation: str) -> str:
        """Get permission setting for an operation.
        
        Args:
            operation: The operation to check (e.g., 'terminal', 'internet')
            
        Returns:
            The permission mode ('ask', 'auto', etc.)
        """
        permissions = self.settings.get('permissions', {})
        return permissions.get(operation, 'ask')  # Default to 'ask' for safety
    
    def is_workspace_path_safe(self, path: str) -> bool:
        """Check if a path is within the workspace root.
        
        Args:
            path: The path to check (can be relative or absolute)
            
        Returns:
            True if the path is safe, False otherwise
        """
        if self.workspace_root is None:
            # If workspace root not set, use .jarvis parent as fallback
            self.workspace_root = self.jarvis_path.parent.resolve()
        
        try:
            # Resolve the path
            target_path = Path(path).resolve()
            
            # Check if it's within workspace root
            return self.workspace_root in target_path.parents or target_path == self.workspace_root
        except Exception:
            # If we can't resolve, consider it unsafe
            return False


# Global brain instance (will be initialized by Agent)
_brain_instance = None


def get_brain() -> JarvisBrain:
    """Get the global brain instance."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = JarvisBrain()
    return _brain_instance


def initialize_brain(jarvis_path: str = '.jarvis', workspace_root: str = None):
    """Initialize the global brain instance.
    
    Args:
        jarvis_path: Path to the .jarvis directory
        workspace_root: Path to the workspace root (for path safety checks)
    """
    global _brain_instance
    _brain_instance = JarvisBrain(jarvis_path)
    if workspace_root:
        _brain_instance.workspace_root = Path(workspace_root).resolve()
    return _brain_instance