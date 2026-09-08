"""
JARVIS Skill Manager — Loads and executes skills from .jarvis/skills/*.md files.
Each skill is a markdown file with YAML frontmatter containing name, description,
instructions, and an optional Python code block.
"""
import os
import re
import json
import tempfile
import subprocess
import sys


class SkillManager:
    """Manages skill loading, listing, and execution from markdown files."""
    
    def __init__(self, skills_dir='.jarvis/skills'):
        self.skills_dir = skills_dir
        self.skills = {}
        self._load_skills()
    
    def _load_skills(self):
        """Load all .md skill files from the skills directory."""
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir, exist_ok=True)
            return
        
        for filename in os.listdir(self.skills_dir):
            if filename.endswith('.md') and filename != 'skills.md':
                filepath = os.path.join(self.skills_dir, filename)
                skill = self._parse_skill_file(filepath)
                if skill:
                    self.skills[skill['name']] = skill
    
    def _parse_skill_file(self, filepath):
        """Parse a skill markdown file into a skill dict."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return None
        
        # Parse YAML frontmatter
        skill = {
            'name': os.path.splitext(os.path.basename(filepath))[0],
            'description': '',
            'instructions': '',
            'code': '',
            'file': filepath
        }
        
        # Extract frontmatter (between --- markers)
        fm_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        if fm_match:
            frontmatter = fm_match.group(1)
            for line in frontmatter.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    skill[key.strip()] = value.strip()
            content = content[fm_match.end():]
        
        # Extract instructions (everything before first code block)
        code_match = re.search(r'```python(.*?)```', content, re.DOTALL)
        if code_match:
            instructions = content[:code_match.start()]
            skill['code'] = code_match.group(1).strip()
        else:
            instructions = content
        
        # Clean up instructions
        instructions = re.sub(r'^#+\s+Instructions?\s*\n', '', instructions, flags=re.IGNORECASE)
        skill['instructions'] = instructions.strip()
        
        return skill
    
    def list_skills(self):
        """List all available skills."""
        return list(self.skills.keys())
    
    def get_skill(self, name):
        """Get a skill by name."""
        return self.skills.get(name)
    
    def execute_skill(self, name, params=None):
        """Execute a skill by name with optional parameters."""
        skill = self.skills.get(name)
        if not skill:
            return {'success': False, 'error': f'Skill not found: {name}'}
        
        if not skill['code']:
            return {'success': False, 'error': f'Skill has no code: {name}'}
        
        if params is None:
            params = {}
        
        # Execute the skill's code in a subprocess
        try:
            result = self._execute_code(skill['code'], params)
            return {'success': True, 'output': result, 'skill': name}
        except Exception as e:
            return {'success': False, 'error': str(e), 'skill': name}
    
    def _execute_code(self, code, params):
        """Execute a skill's Python code safely."""
        # Create a temporary file with the skill code
        fd, tmp_path = tempfile.mkstemp(suffix='.py', prefix='skill_')
        try:
            # Wrap the code in a function call
            wrapper = f"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

{code}

# Execute with params
params = {json.dumps(params)}
print(run(**params))
"""
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(wrapper)
            
            # Execute the temporary file with UTF-8 encoding
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                timeout=10,
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
            )
            output = result.stdout.decode('utf-8') if result.stdout else ''
            stderr = result.stderr.decode('utf-8') if result.stderr else ''
            return output.strip() if result.returncode == 0 else f"Error: {stderr}"
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    def refresh(self):
        """Reload all skills from disk."""
        self.skills.clear()
        self._load_skills()
