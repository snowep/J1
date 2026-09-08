import json, os, re, requests
from src.file_manager import FileManager
from src.terminal_executor import TerminalExecutor


class Agent:
    """JARVIS Agent — Natural language file and terminal operations."""

    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.fm = FileManager()
        self.te = TerminalExecutor(
            workspace_path=self.config.get('workspace', 'workspace'),
            require_approval=self.config.get('permissions', {}).get('terminal', 'ask') == 'auto',
            log_path='workspace/terminal_log.json'
        )
        self.history = []
        self.max_history = self.config.get('conversation', {}).get('max_history', 10)
        self.llm = self.config.get('llm', {})

    def _call_llm(self, prompt):
        """Send prompt to LLM and return response."""
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

    def _extract_filename(self, text):
        """Extract filename from natural language."""
        m = re.search(r'["\']([^"\']+\.(md|txt|json|xml|csv|html|css|js|py|yaml|yml))["\']', text, re.I)
        if m:
            return m.group(1)
        m = re.search(r'\b([a-zA-Z0-9_\-]+\.(md|txt|json|xml|csv|html|css|js|py|yaml|yml))\b', text, re.I)
        return m.group(1) if m else None

    def _extract_name(self, text):
        """Extract folder or general name from text."""
        # Look for quoted names first
        m = re.search(r'["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
        # Remove common words
        words = re.findall(r'\b[\w-]+\b', text)
        stopwords = {'a', 'an', 'the', 'new', 'folder', 'directory', 'file', 'named', 'called', 'my', 'to', 'for', 'in'}
        for w in words:
            if w.lower() not in stopwords and len(w) > 1:
                return w
        return None

    def _translate_to_command(self, text):
        """Translate natural language to terminal commands."""
        text_l = text.lower()

        # === GIT COMMANDS ===
        if re.search(r'\b(commit|save)\s+(current\s+)?change', text_l):
            return 'git add -A && git commit -m "Update"'
        if re.search(r'\bpush\s+(to|my|the)\s+repo', text_l):
            return 'git push'
        if re.search(r'\bpull\s+(from|my|the)\s+repo', text_l):
            return 'git pull'
        if re.search(r'\b(git\s+)?status', text_l):
            return 'git status'
        if re.search(r'\b(git\s+)?log', text_l):
            return 'git log --oneline -10'
        if re.search(r'\b(git\s+)?checkout\s+(\w+)', text_l):
            m = re.search(r'checkout\s+(\w+)', text_l)
            return f'git checkout {m.group(1)}'
        if re.search(r'\b(git\s+)?branch', text_l):
            return 'git branch'

        # === FOLDER COMMANDS ===
        if re.search(r'\b(make|create|new)\s+(a\s+)?folder', text_l):
            name = self._extract_name(text)
            return f'mkdir "{name}"' if name else 'mkdir new_folder'
        if re.search(r'\b(remove|delete|rm)\s+(a\s+)?folder', text_l):
            name = self._extract_name(text)
            return f'rmdir "{name}"' if name else 'rmdir new_folder'

        # === FILE COMMANDS ===
        if re.search(r'\b(make|create|new)\s+(a\s+)?file', text_l):
            name = self._extract_name(text)
            return f'touch "{name}"' if name else 'touch new_file.txt'
        if re.search(r'\b(remove|delete|rm)\s+(a\s+)?file', text_l):
            name = self._extract_filename(text)
            return f'del "{name}"' if name else 'del file.txt'

        # === LISTING ===
        if re.search(r'\blist\s+(all\s+)?files', text_l):
            return 'dir'
        if re.search(r'\blist\s+(all\s+)?folders', text_l):
            return 'dir /ad'

        # === CLEAR/RESET ===
        if re.search(r'\b(clear|clean)\s+(the\s+)?screen', text_l):
            return 'cls'
        if re.search(r'\bclear\s+(the\s+)?log', text_l):
            return 'del terminal_log.json'

        # === PROCESS ===
        if re.search(r'\b(show|list)\s+(all\s+)?processes?', text_l):
            return 'tasklist'
        if re.search(r'\bkill\s+(the\s+)?(\w+)', text_l):
            m = re.search(r'kill\s+(?:the\s+)?(\w+)', text_l)
            return f'taskkill /IM {m.group(1)}.exe /F' if m else 'taskkill'

        # === NETWORK ===
        if re.search(r'\b(what.?s?\s+)?my\s+ip', text_l):
            return 'ipconfig | findstr "IPv4"'
        if re.search(r'\bping\s+(the\s+)?(\w+)', text_l):
            m = re.search(r'ping\s+(?:the\s+)?(\w+)', text_l)
            return f'ping {m.group(1)}' if m else 'ping google.com'

        # === PYTHON ===
        if re.search(r'\blist\s+(all\s+)?python\s+modules?', text_l):
            return 'pip list'
        if re.search(r'\bcheck\s+(the\s+)?python\s+version', text_l):
            return 'python --version'

        # === SYSTEM ===
        if re.search(r'\b(show|check)\s+(the\s+)?date', text_l):
            return 'date /t'
        if re.search(r'\b(show|check)\s+(the\s+)?time', text_l):
            return 'time /t'

        return None

    # === Command Detection ===
    def _detect_command(self, text):
        """Detect intent and return (operation, target, params)."""
        text_l = text.lower()

        # NL-to-command translation BEFORE generic patterns
        # (folder/file creation is handled here, not in translate_to_command)
        if re.search(r'\b(make|create|new)\s+(a\s+)?folder', text_l):
            name = self._extract_name(text)
            cmd = f'mkdir "{name}"' if name else 'mkdir new_folder'
            return ('terminal', cmd, {'translated': True})

        if re.search(r'\b(remove|delete|rm)\s+(a\s+)?folder', text_l):
            name = self._extract_name(text)
            cmd = f'rmdir "{name}"' if name else 'rmdir folder'
            return ('terminal', cmd, {'translated': True})

        # Other NL translations
        cmd = self._translate_to_command(text)
        if cmd:
            return ('terminal', cmd, {'translated': True})

        # Direct terminal command patterns
        direct_patterns = [
            r'^python\s+', r'^pip\s+', r'^npm\s+', r'^git\s+', r'^docker\s+',
            r'^ls\s+', r'^dir\s+', r'^cd\s+', r'^rm\s+', r'^mkdir\s+',
            r'^touch\s+', r'^cat\s+', r'^echo\s+', r'^grep\s+', r'^find\s+',
            r'^cls\s*', r'^clear\s+', r'^tasklist\s+',
        ]
        for pattern in direct_patterns:
            if re.search(pattern, text_l):
                return ('terminal', text, {})

        # Run/Execute commands
        if re.search(r'\b(run|execute|start)\s+(python\s+|[a-zA-Z_][\w]*\.py)', text_l):
            return ('terminal', text, {})

        # List files
        if any(k in text_l for k in ['list', 'ls', 'dir', 'files']) and not any(k in text_l for k in ['delete', 'remove']):
            return ('list', None, {})

        # Read commands
        if any(k in text_l for k in ['read', 'show', 'view', 'cat', 'get']):
            m = self._extract_filename(text)
            return ('read', m if m else text.split()[-1], {})

        # Delete commands
        if any(k in text_l for k in ['delete', 'remove', 'rm', 'del']):
            m = self._extract_filename(text) or self._extract_name(text)
            return ('delete', m if m else text.split()[-1], {})

        # Edit commands
        if any(k in text_l for k in ['edit', 'modify', 'change', 'replace', 'update']):
            m = self._extract_filename(text)
            return ('edit', m, {})

        # Create/Write commands
        if any(k in text_l for k in ['create', 'make', 'write', 'generate', 'new']):
            m = self._extract_filename(text)
            return ('create', m, {})

        return ('chat', None, {})

    # === CRUD Handlers ===
    def _handle_create(self, text, filename):
        """Handle file creation with LLM-generated content."""
        if not filename:
            topic = self._extract_name(text) or "New File"
            filename = re.sub(r'[^\w\s-]', '', topic).replace(' ', '-') + '.md'
        if not filename.endswith(('.md', '.txt', '.json', '.txt')):
            filename += '.md'
        content = self._call_llm(f"Write markdown content for: {filename}. Request: {text}")
        if content.startswith("Error"):
            content = f"# {filename.title()}\n\nDocument content."
        result = self.fm.write(filename, content, overwrite=True)
        return f"✅ {result['message']}" if result['success'] else f"❌ {result['error']}"

    def _handle_read(self, filename):
        """Handle file reading."""
        if not filename or filename.lower() in ['files', 'all', 'list']:
            result = self.fm.list()
            items = '\n'.join(f"  [{i['type'][0]}] {i['name']}" for i in result.get('items', []))
            return f"📁 Files in workspace:\n{items}" if items else "📁 Empty workspace"
        result = self.fm.read(filename)
        if result['success']:
            return f"📄 {filename}:\n\n{result['content']}"
        return f"❌ {result['error']}"

    def _handle_edit(self, text, filename):
        """Handle text replacement in file."""
        if not filename:
            return "❌ Specify file to edit"
        m = self._extract_filename(text)
        if m:
            filename = m
        m = re.search(r'\b(change|replace|to)\s+["\']([^"\']+)["\']?\s+(?:to|with)\s+["\']([^"\']+)["\']', text, re.I)
        if not m:
            return "❌ Format: 'edit \"file.md\" change \"old\" to \"new\"'"
        old_text, new_text = m.group(2), m.group(3)
        result = self.fm.edit(filename, old_text, new_text)
        return result['message'] if result['success'] else f"❌ {result['error']}"

    def _handle_delete(self, filename):
        """Handle file deletion."""
        if not filename:
            return "❌ Specify file to delete"
        result = self.fm.delete(filename)
        return result['message'] if result['success'] else f"❌ {result['error']}"

    def _handle_list(self):
        """Handle directory listing."""
        result = self.fm.list()
        if result['success']:
            items = '\n'.join(f"  [{i['type'][0]}] {i['name']}" for i in result.get('items', []))
            return f"📁 Files:\n{items}" if items else "📁 Empty"
        return f"❌ {result['error']}"

    def _handle_terminal(self, command, translated=False):
        """Handle terminal command execution."""
        cmd = command.strip()

        result = self.te.execute(cmd)

        output = ""
        if result.get('cwd'):
            output += f"📁 CWD: {result['cwd']}\n"
        output += f"📟 Status: {result['status']} (exit: {result['exit_code']})\n"
        output += f"⏱️ Duration: {result['duration_ms']}ms\n"
        if translated:
            output += f"🔄 Translated: `{command}`\n"
        output += f"\n{'='*40}\n"
        if result['stdout']:
            output += result['stdout']
        if result['stderr']:
            output += f"\n⚠️ STDERR:\n{result['stderr']}"
        output += f"{'='*40}"

        return output

    def _handle_chat(self, text):
        """Handle regular chat."""
        response = self._call_llm(text)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": response})
        return f"JARVIS: {response}"

    def process(self, user_input):
        """Main entry point — route to appropriate handler."""
        user_input = user_input.strip()
        if not user_input:
            return "Enter a command or question."
        op, target, params = self._detect_command(user_input)
        return {
            'create': lambda: self._handle_create(user_input, target),
            'read': lambda: self._handle_read(target),
            'edit': lambda: self._handle_edit(user_input, target),
            'delete': lambda: self._handle_delete(target),
            'list': self._handle_list,
            'terminal': lambda: self._handle_terminal(target, params.get('translated', False)),
            'chat': lambda: self._handle_chat(user_input)
        }[op]()


if __name__ == "__main__":
    print("JARVIS: Type commands like:")
    print("  'Create notes.md about my goals'")
    print("  'Make new folder called images'")
    print("  'Remove folder temp'")
    print("  'Commit current change'")
    print("  'Show my ip'")
    print("  'List all files'")
    while (cmd := input("\nYou: ")) and cmd.lower() not in ['exit', 'quit']:
        print(Agent().process(cmd))