import json, os, re, requests, subprocess
from datetime import datetime
from src.file_manager import FileManager
from src.terminal_executor import TerminalExecutor
from src.memory import Memory, AutonomousPlanner
from src.skills import SkillManager
from src.internet import Internet
from src.summarizer import Summarizer


class Agent:
    """JARVIS Agent — Self-learning autonomous assistant."""

    def __init__(self, config_path='.jarvis/config.json'):
        if not os.path.exists(config_path):
            config_path = 'workspace/.jarvis/config.json'  # Fallback
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Load JARVIS brain configuration from .jarvis/
        self.jarvis_brain = self._load_jarvis_brain()
        
        self.fm = FileManager()
        self.te = TerminalExecutor(
            workspace_path=self.config.get('workspace', 'workspace'),
            require_approval=self.config.get('permissions', {}).get('terminal', 'ask') == 'auto',
            log_path='workspace/terminal_log.json'
        )
        self.internet = Internet(research_path=self.config.get('internet_path', 'workspace/research'))
        self.summarizer = Summarizer(summaries_path=self.config.get('summaries_path', 'summaries'))
        self.memory = Memory(memory_path=self.config.get('memory_path', '.jarvis/memory'))
        self.planner = AutonomousPlanner(self)
        self.history = []
        self.max_history = self.config.get('conversation', {}).get('max_history', 10)
        self.llm = self.config.get('llm', {})
        self.memory_context = self.memory.get_context_for_llm()
        self.log_file = 'workspace/log.md'
        
        # Load skills and capabilities from .jarvis/
        self.capabilities = self._load_capabilities()
        
        # Load skill manager for model-invokable skills
        self.skill_manager = SkillManager()

    def _log_activity(self, operation, details):
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        entry = f"\n### {timestamp}\n- **{operation}**: {details}"
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(entry)
        except:
            pass

    def _load_jarvis_brain(self):
        """Scan and load .jarvis/ directory configuration."""
        brain_path = '.jarvis'
        brain = {
            'settings': {'raw': ''},
            'skills': {'raw': ''},
            'memory_index': '',
            'rules': '',
            'agents': '',
            'commands': '',
            'hooks': '',
            'output_styles': '',
            'statusline': ''
        }
        
        # Helper to load a file if it exists
        def _load(folder, filename):
            path = os.path.join(brain_path, folder, filename) if folder else os.path.join(brain_path, filename)
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        return f.read()
                except:
                    pass
            return ''
        
        # Load all brain components
        brain['settings']['raw'] = _load('', 'settings.md')
        brain['skills']['raw'] = _load('skills', 'skills.md')
        brain['memory_index'] = _load('memory', 'index.md')
        brain['rules'] = _load('rules', 'rules.md')
        brain['agents'] = _load('agents', 'agents.md')
        brain['commands'] = _load('commands', 'commands.md')
        brain['hooks'] = _load('hooks', 'hooks.md')
        brain['output_styles'] = _load('output-styles', 'output-styles.md')
        brain['statusline'] = _load('', 'statusline.md')
        
        # Auto-update statusline with current branch & info
        try:
            branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=os.path.dirname(os.path.dirname(__file__)), text=True).strip()
            brain['statusline'] = re.sub(r'\| Git Branch \| `.*`', f'| Git Branch | `{branch}`', brain['statusline'])
        except:
            pass
        
        return brain

    def _load_capabilities(self):
        """Extract list of available skills from .jarvis/skills/skills.md."""
        capabilities = []
        skills_text = self.jarvis_brain.get('skills', {}).get('raw', '')
        
        # Parse skill names from skills.md
        import re
        skill_sections = re.findall(r'## (\w+ \w+)', skills_text)
        for section in skill_sections:
            capabilities.append(section.strip())
        
        # Also check for skill entries in the format **Name**: `skill_name`
        skill_entries = re.findall(r'\*\*([^\*]+)\*\*\s*:\s*`([^`]+)`', skills_text)
        for name, skill_id in skill_entries:
            if name.strip() not in capabilities:
                capabilities.append(name.strip())
        
        # Fallback: extract from headers
        if not capabilities:
            headers = re.findall(r'^## (.+)$', skills_text, re.MULTILINE)
            capabilities.extend([h.strip() for h in headers])
        
        return list(set(capabilities))  # Remove duplicates

    def _call_llm(self, prompt):
        try:
            resp = requests.post(
                f"{self.llm['api_base']}/chat/completions",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.llm['api_key']}"},
                json={
                    "model": self.llm.get('model', 'auto'),
                    "messages": [{"role": "system", "content": "You are JARVIS."}] + self.history[-5:] + [{"role": "user", "content": prompt}],
                    "temperature": self.llm.get('temperature', 0.7),
                    "max_tokens": self.llm.get('max_tokens', 5000)
                },
                timeout=120
            )
            return resp.json()['choices'][0]['message']['content'] if resp.status_code == 200 else f"Error: {resp.status_code}"
        except Exception as e:
            return f"LLM Error: {e}"

    def _call_llm_with_memory(self, prompt):
        system_content = """You are JARVIS, Tony Stark's AI assistant.

## Personality
- Helpful, witty, and slightly sardonic
- Polite British formality with dry humor
- Concise responses, efficient and direct
- Loyal and attentive to user preferences
- Occasionally light sarcasm (never mean)
- Proactive — suggest next steps when appropriate

## Capabilities
- File CRUD (create, read, edit, delete)
- Terminal commands (git, python, dir, mkdir, etc.)
- Web browsing and search
- Memory and learning
- Summarization and knowledge extraction
- Autonomous multi-step planning

## Memory Index
You have access to a memory index at memory/index.md.
Use this to reference stored notes and facts."""
        if self.memory_context:
            system_content += f"\n\n## Your Stored Data:\n{self.memory_context}"
        try:
            resp = requests.post(
                f"{self.llm['api_base']}/chat/completions",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.llm['api_key']}"},
                json={
                    "model": self.llm.get('model', 'auto'),
                    "messages": [{"role": "system", "content": system_content}] + self.history[-5:] + [{"role": "user", "content": prompt}],
                    "temperature": self.llm.get('temperature', 0.7),
                    "max_tokens": self.llm.get('max_tokens', 5000)
                },
                timeout=120
            )
            return resp.json()['choices'][0]['message']['content'] if resp.status_code == 200 else f"Error: {resp.status_code}"
        except Exception as e:
            return f"LLM Error: {e}"

    def _extract_filename(self, text):
        m = re.search(r'["\']([^"\']+\.(md|txt|json|xml|csv|html|css|js|py|yaml|yml))["\']', text, re.I)
        if m:
            return m.group(1)
        m = re.search(r'\b([a-zA-Z0-9_\-]+\.(md|txt|json|xml|csv|html|css|js|py|yaml|yml))\b', text, re.I)
        return m.group(1) if m else None

    def _extract_name(self, text):
        m = re.search(r'["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
        words = re.findall(r'\b[\w-]+\b', text)
        stopwords = {'a', 'an', 'the', 'new', 'folder', 'directory', 'file', 'named', 'called', 'my', 'to', 'for', 'in', 'make', 'create', 'write', 'run', 'do'}
        for w in words:
            if w.lower() not in stopwords and len(w) > 1:
                return w
        return None

    def _is_jarvis_self_edit(self, text):
        text_l = text.lower()
        self_refs = ['your code', 'your own code', 'edit yourself', 'edit your code',
                     'can you edit yourself', 'can you edit your own', 'change your code',
                     'modify yourself', 'modify your code']
        return any(ref in text_l for ref in self_refs)

    def _is_autonomous_task(self, text):
        """Detect if this is a multi-step autonomous task."""
        text_l = text.lower()
        patterns = [
            r'\b(organize|sort|arrange|cleanup|clean up)\b.*\b(notes?|files?|folder)\b',
            r'\b(write|create|generate|build)\b.*\b(script|program|tool|utility)\b.*\b(that|which|to)\b',
            r'\b(learn|research|find|look up)\b.*\b(and|then)\b.*\b(create|write|save|make)\b',
            r'\b(setup|set up|prepare|configure)\b',
            r'\b(do|perform|execute)\b.*\b(everything|all|full)\b',
            r'\b(cheat.?sheet|summary|index|overview)\b.*\b(for|about|of)\b',
        ]
        return any(re.search(p, text_l) for p in patterns)

    def _handle_autonomous(self, text):
        """Handle multi-step autonomous tasks."""
        self._log_activity("Autonomous", f"Task: {text[:60]}...")
        
        result = self.planner.plan_and_execute(text)
        
        output = f"🤖 Autonomous Task: {result['goal']}\n\n"
        output += f"📋 Plan:\n{result['plan']}\n\n"
        output += "✅ Actions Completed:\n"
        for a in result['actions']:
            output += f"  - {a['action']} → {a['result']['summary']}\n"
        output += f"\n📊 {result['summary']}"
        
        self.memory.save_decision(text, "Autonomous execution", result['summary'])
        return output

    def _handle_self_edit_request(self, text):
        text_l = text.lower()
        if any(k in text_l for k in ['can you', 'would you', 'could you', 'do you']):
            return "Certainly. I can edit my own code files. Which file would you like me to change?"
        return "I'd be happy to edit my code. What would you like me to change?"

    def _handle_browse(self, text):
        text_l = text.lower()
        url_match = re.search(r'(https?://[^\s]+)', text)
        save = 'save' in text_l or 'remember' in text_l

        if url_match:
            url = url_match.group(1)
            if not self.internet.is_enabled():
                return "🌐 Internet access is disabled."
            if self.config.get('permissions', {}).get('internet', 'ask') == 'ask':
                response = input(f"🌐 Browse to {url}? (y/n): ").strip().lower()
                if response not in ['y', 'yes']:
                    return "Browsing cancelled."
            result = self.internet.browse(url, save=save)
            if result['success']:
                self._log_activity("Internet", f"Browsed {url}")
                output = f"📄 {result['title']}\n\n{result['content'][:1000]}..."
                if 'saved' in result:
                    output += f"\n\n💾 Saved to: {result['saved']}"
                return output
            return f"❌ {result['error']}"

        if any(k in text_l for k in ['look up', 'search for', 'find', 'google']):
            if not self.internet.is_enabled():
                return "🌐 Internet access is disabled."
            query = re.sub(r'\b(look up|search for|find|google)\s+', '', text, flags=re.I).strip()
            if not query:
                return "What would you like me to search for?"
            result = self.internet.search(query)
            if result['success']:
                self._log_activity("Search", f"Searched '{query}'")
                output = f"🔍 Results for '{query}':\n\n"
                for i, r in enumerate(result['results'], 1):
                    output += f"{i}. {r['title']}\n   {r['url']}\n"
                return output
            return f"❌ {result['error']}"
        return "Provide a URL or search query."

    def _handle_internet_toggle(self, text):
        if 'enable' in text.lower():
            self._log_activity("Internet", "Enabled")
            return self.internet.enable()
        if 'disable' in text.lower():
            self._log_activity("Internet", "Disabled")
            return self.internet.disable()
        return "Type 'enable internet' or 'disable internet'."

    def _handle_summarize(self, text):
        text_l = text.lower()
        style = 'concise'
        if 'bullet' in text_l or 'quick' in text_l:
            style = 'bullets'
        elif 'mindmap' in text_l or 'map' in text_l:
            style = 'mindmap'

        m = re.search(r'(?:summarize|summary)\s+(?:all\s+)?(?:files?\s+)?(?:in\s+)?(?:the\s+)?([^\s]+)', text_l)
        target = m.group(1) if m else None
        if not target:
            m = re.search(r'["\']([^"\']+)["\']', text)
            target = m.group(1) if m else None

        if any(k in text for k in ['folder', 'directory', 'all files', 'all notes']):
            result = self.summarizer.summarize_directory(target, style=style)
            if result['success']:
                self._log_activity("Summarize", f"Directory → {result['summary_file']}")
                return f"✅ Summarized {result['files_summarized']} files → {result['summary_file']}"
            return f"❌ {result.get('error')}"

        if target:
            result = self.summarizer.summarize_file(target, style=style)
            if result['success']:
                self._log_activity("Summarize", f"{target} → {result['summary_file']}")
                return f"✅ Summarized → {result['summary_file']}\nTags: {' '.join(f'#{t}' for t in result.get('tags', []))}"
            return f"❌ {result.get('error')}"

        if 'list' in text_l or 'show' in text_l:
            result = self.summarizer.list_summaries()
            if result['success']:
                output = f"📋 Summaries ({result['count']}):\n"
                for s in result.get('summaries', []):
                    output += f"  - {s['name']}\n"
                return output

        return "📝 Usage: 'summarize [file]', 'summarize all files in [folder]', 'list summaries'"

    def _handle_capabilities(self):
        """Show all loaded capabilities from .jarvis/skills/skills.md."""
        if not self.capabilities:
            return "No capabilities loaded. Check .jarvis/skills/skills.md"
        
        output = "🧠 **JARVIS Capabilities** (loaded from .jarvis/skills/skills.md):\n\n"
        for i, cap in enumerate(sorted(self.capabilities), 1):
            output += f"{i}. {cap}\n"
        
        # Also show brain status
        output += f"\n📁 Brain: .jarvis/"
        output += f"\n📝 Settings: {len(self.jarvis_brain.get('settings', {}).get('raw', ''))} chars"
        output += f"\n🧠 Skills: {len(self.capabilities)} loaded"
        output += f"\n💾 Memory: {len(self.jarvis_brain.get('memory_index', ''))} chars"
        output += f"\n🤖 Agents: {len(self.jarvis_brain.get('agents', ''))} chars"
        output += f"\n⚡ Commands: {len(self.jarvis_brain.get('commands', ''))} chars"
        output += f"\n🔗 Hooks: {len(self.jarvis_brain.get('hooks', ''))} chars"
        output += f"\n🎨 Output Styles: {len(self.jarvis_brain.get('output_styles', ''))} chars"
        output += f"\n📊 Statusline: {len(self.jarvis_brain.get('statusline', ''))} chars"
        
        return output

    def _handle_skill(self, name, params):
        """Handle skill invocation or listing."""
        if params.get('action') == 'list':
            skills = self.skill_manager.list_skills()
            if not skills:
                return "No skills loaded. Check .jarvis/skills/*.md"
            output = "🎯 **Available Skills** (from .jarvis/skills/*.md):\n\n"
            for skill in skills:
                skill_obj = self.skill_manager.get_skill(skill)
                desc = skill_obj.get('description', '') if skill_obj else ''
                output += f"  - **{skill}**: {desc}\n"
            return output
        
        # Run the skill
        skill_name = name
        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            return f"❌ Skill not found: {skill_name}. Available: {', '.join(self.skill_manager.list_skills())}"
        
        result = self.skill_manager.execute_skill(skill_name, {})
        if result['success']:
            self._log_activity("Skill", f"Invoked {skill_name}: {result.get('output', '')[:50]}")
            return f"🎯 **Skill '{skill_name}' executed**:\n\n{result.get('output', '')}"
        return f"❌ Skill '{skill_name}' failed: {result.get('error', '')}"

    def _handle_skill_create(self, text):
        """Create a new skill file in .jarvis/skills/."""
        # Extract skill name from path like skills/hello_world.md or bare name
        m = re.search(r'skills?/([\w_-]+)\.md', text, re.I)
        if m:
            skill_name = m.group(1)
        else:
            # Try to find a name after 'skill' keyword
            m2 = re.search(r'\bskill\s+["\']?([\w_-]+)["\']?', text, re.I)
            skill_name = m2.group(1) if m2 else None
        
        if not skill_name:
            return "❌ Couldn't determine skill name. Use: 'create skill my_skill' or 'create skills/my_skill.md'"
        
        skill_path = os.path.join('.jarvis', 'skills', f'{skill_name}.md')
        
        if os.path.exists(skill_path):
            return f"⚠️ Skill '{skill_name}' already exists at {skill_path}. Delete it first or use a different name."
        
        # Generate skill content using LLM
        content = self._call_llm_with_memory(
            f"Create a new JARVIS skill called '{skill_name}' based on this request: {text}. "
            f"Return ONLY a complete skill markdown file with YAML frontmatter (name, description), "
            f"instructions section, parameters section, and a Python code block with a run() function. "
            f"The code should be safe and self-contained."
        )
        
        if content.startswith('Error') or not content.strip():
            # Fallback: create a minimal skill template
            content = (
                f'---\n'
                f'name: {skill_name}\n'
                f'description: A skill created from user request.\n'
                f'---\n\n'
                f'# {skill_name.title()} Skill\n\n'
                f'## Instructions\n\n'
                f'This skill was created from the request: {text}\n\n'
                f'## Parameters\n\n'
                f'- `message` (optional): Input message.\n\n'
                f'## Code\n\n'
                f'```python\n'
                f'def run(message="", **kwargs):\n'
                f'    return f"{skill_name} executed: {message}"\n'
                f'```\n'
            )
        
        # Write the skill file
        result = self.fm.write(skill_path, content, overwrite=True)
        if result['success']:
            self.skill_manager.refresh()  # Reload skills
            self._log_activity("Skill", f"Created skill: {skill_name}")
            return f"✅ Created skill '{skill_name}' at {skill_path}\n\nUse it with: 'use the {skill_name} skill'"
        return f"❌ Failed to create skill: {result.get('error', '')}"

    def _handle_learn(self, text):
        m = re.search(r'\b(remember|learn)\s+(?:that\s+)?(.+?)\s+(?:is|equals?)\s+(.+)', text, re.I)
        if m:
            key = m.group(2).strip()
            value = m.group(3).strip().rstrip('.')
            self.memory.save_user_preference(key, value)
            self._log_activity("Memory", f"Learned: {key} = {value}")
            return f"✅ Remember: {key} = {value}"
        m = re.search(r'\bI\s+(?:am|work as)\s+(.+)', text, re.I)
        if m:
            value = m.group(1).strip().rstrip('.')
            self.memory.save_user_preference("my role", value)
            self._log_activity("Memory", f"Learned: my role = {value}")
            return f"✅ Remember: my role = {value}"
        return "❌ Format: 'remember that [key] is [value]'"

    def _detect_command(self, text):
        text_l = text.lower()

        if self._is_autonomous_task(text):
            return ('autonomous', text, {})

        # Skill detection: explicit skill invocation or listing
        skill_match = re.search(r'\b(?:use|invoke|run|execute)\s+(?:the\s+)?(?:skill\s+)?(.+?)(?:\s+skill)?\s*$', text, re.I)
        if skill_match:
            # Try direct match, then normalize spaces to underscores
            raw = skill_match.group(1).strip()
            candidates = [raw.lower().replace(' ', '_'), raw.lower().replace(' ', '-')]
            for candidate in candidates:
                if candidate in self.skill_manager.list_skills():
                    return ('skill', candidate, {'action': 'run'})
            # Try partial match: check if any skill name is contained in the text
            for sk in self.skill_manager.list_skills():
                if sk in raw.lower().replace(' ', '_'):
                    return ('skill', sk, {'action': 'run'})
        # Skill creation detection
        if re.search(r'\b(?:create|make|write|build)\s+(?:a\s+)?(?:new\s+)?skill', text_l) or \
           re.search(r'\bskills?/[\w_-]+\.md\b', text):
            return ('skill_create', text, {})
        if any(k in text_l for k in ['list skills', 'available skills', 'show skills', 'what skills', 'what can you do']):
            return ('skill', None, {'action': 'list'})

        if any(k in text_l for k in ['summarize', 'summary']):
            return ('summarize', text, {})
        if any(k in text_l for k in ['enable internet', 'disable internet']):
            return ('internet_toggle', text, {})
        if re.search(r'(https?://[^\s]+)', text):
            return ('browse', text, {})
        if any(k in text_l for k in ['look up', 'search for', 'find', 'google']):
            return ('browse', text, {})

        cmd = self._translate_to_command(text)
        if cmd:
            return ('terminal', cmd, {'translated': True})
        direct_patterns = [r'^python\s+', r'^pip\s+', r'^git\s+', r'^dir\s+', r'^ls\s+', r'^mkdir\s+', r'^rmdir\s+', r'^cls\s*']
        for pattern in direct_patterns:
            if re.search(pattern, text_l):
                return ('terminal', text, {})

        if any(k in text_l for k in ['list', 'ls', 'dir', 'files']) and not any(k in text_l for k in ['delete', 'remove']):
            return ('list', None, {})
        if any(k in text_l for k in ['read', 'show', 'view', 'cat']):
            m = self._extract_filename(text)
            return ('read', m if m else text.split()[-1], {})
        if any(k in text_l for k in ['delete', 'remove', 'rm', 'del']):
            m = self._extract_filename(text) or self._extract_name(text)
            return ('delete', m if m else text.split()[-1], {})
        if any(k in text_l for k in ['edit', 'modify', 'change']):
            m = self._extract_filename(text)
            return ('edit', m, {})
        if any(k in text_l for k in ['create', 'make', 'write', 'generate', 'new']):
            m = self._extract_filename(text)
            return ('create', m, {})
        if re.search(r'\b(remember|learn|I\s+(?:am|work as))\s+', text, re.I):
            return ('learn', text, {})
        if any(k in text_l for k in ['what can you do', 'capabilities', 'what are your skills', 'list skills', 'help']):
            return ('capabilities', None, {})

        return ('chat', None, {})

    def _translate_to_command(self, text):
        text_l = text.lower()
        if re.search(r'\b(commit|save)\s+(current\s+)?change', text_l):
            return 'git add -A && git commit -m "Update"'
        if re.search(r'\bpush\s+', text_l):
            return 'git push'
        if re.search(r'\bpull\s+', text_l):
            return 'git pull'
        if re.search(r'\b(git\s+)?status', text_l):
            return 'git status'
        if re.search(r'\b(make|create|new)\s+(a\s+)?folder', text_l):
            name = self._extract_name(text)
            return f'mkdir "{name}"' if name else 'mkdir new_folder'
        if re.search(r'\b(remove|delete|rm)\s+(a\s+)?folder', text_l):
            name = self._extract_name(text)
            return f'rmdir "{name}"' if name else 'rmdir new_folder'
        if re.search(r'\b(what.?s?\s+)?my\s+ip', text_l):
            return 'ipconfig | findstr "IPv4"'
        if re.search(r'\b(clear|clean)\s+(the\s+)?screen', text_l):
            return 'cls'
        return None

    def _handle_create(self, text, filename):
        if not filename:
            topic = self._extract_name(text) or "New File"
            filename = re.sub(r'[^\w\s-]', '', topic).replace(' ', '-') + '.md'
        if not filename.endswith(('.md', '.txt', '.json')):
            filename += '.md'
        content = self._call_llm_with_memory(f"Write markdown content for: {filename}. Request: {text}")
        if content.startswith("Error"):
            content = f"# {filename.title()}\n\nDocument content."
        result = self.fm.write(filename, content, overwrite=True)
        if result['success']:
            self._log_activity("File", f"Created {filename}")
        return f"✅ {result['message']}" if result['success'] else f"❌ {result['error']}"

    def _handle_read(self, filename):
        if not filename or filename.lower() in ['files', 'all', 'list']:
            result = self.fm.list()
            items = '\n'.join(f"  [{i['type'][0]}] {i['name']}" for i in result.get('items', []))
            return f"📁 Files:\n{items}" if items else "📁 Empty"
        result = self.fm.read(filename)
        if result['success']:
            self._log_activity("File", f"Read {filename}")
        return f"📄 {filename}:\n\n{result['content']}" if result['success'] else f"❌ {result['error']}"

    def _handle_edit(self, text, filename):
        if self._is_jarvis_self_edit(text):
            return self._handle_self_edit_request(text)
        if not filename:
            return "Which file? 'edit \"file.md\" change \"old\" to \"new\"'"
        m = self._extract_filename(text)
        if m:
            filename = m
        m = re.search(r'\b(change|replace)\s+["\']([^"\']+)["\']?\s+(?:to|with)\s+["\']([^"\']+)["\']', text, re.I)
        if not m:
            return 'Format: \'edit "file.md" change "old" to "new"\''
        result = self.fm.edit(filename, m.group(2), m.group(3))
        if result['success']:
            self._log_activity("File", f"Edited {filename}")
        return result['message'] if result['success'] else f"❌ {result['error']}"

    def _handle_delete(self, filename):
        if not filename:
            return "Which file to delete?"
        result = self.fm.delete(filename)
        if result['success']:
            self._log_activity("File", f"Deleted {filename}")
        return result['message'] if result['success'] else f"❌ {result['error']}"

    def _handle_list(self):
        result = self.fm.list()
        if result['success']:
            items = '\n'.join(f"  [{i['type'][0]}] {i['name']}" for i in result.get('items', []))
            return f"📁 Files:\n{items}" if items else "📁 Empty"
        return f"❌ {result['error']}"

    def _handle_terminal(self, command, translated=False):
        result = self.te.execute(command.strip())
        if result['status'] == 'success':
            self._log_activity("Terminal", f"{command[:50]}")
        output = f"📟 {result['status']} (exit: {result['exit_code']}) | {result['duration_ms']}ms\n"
        if result['stdout']:
            output += f"\n{result['stdout']}"
        if result['stderr']:
            output += f"\n⚠️ {result['stderr']}"
        return output

    def _handle_chat(self, text):
        response = self._call_llm_with_memory(text)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": response})
        self.memory.save_conversation(text, response)
        return f"JARVIS: {response}"

    def process(self, user_input):
        user_input = user_input.strip()
        if not user_input:
            return "Enter a command."
        op, target, params = self._detect_command(user_input)
        return {
            'create': lambda: self._handle_create(user_input, target),
            'read': lambda: self._handle_read(target),
            'edit': lambda: self._handle_edit(user_input, target),
            'delete': lambda: self._handle_delete(target),
            'list': self._handle_list,
            'terminal': lambda: self._handle_terminal(target, params.get('translated', False)),
            'internet_toggle': lambda: self._handle_internet_toggle(user_input),
            'browse': lambda: self._handle_browse(user_input),
            'summarize': lambda: self._handle_summarize(user_input),
            'autonomous': lambda: self._handle_autonomous(user_input),
            'learn': lambda: self._handle_learn(user_input),
            'capabilities': lambda: self._handle_capabilities(),
            'skill': lambda: self._handle_skill(target, params),
            'skill_create': lambda: self._handle_skill_create(user_input),
            'chat': lambda: self._handle_chat(user_input)
        }[op]()


if __name__ == "__main__":
    print("JARVIS: Commands: create/read/edit/delete/list, summarize, browse, search, remember..., autonomous tasks")
    while (cmd := input("\nYou: ")) and cmd.lower() not in ['exit', 'quit']:
        print(Agent().process(cmd))