import json, os, re, requests
from src.file_manager import FileManager
from src.terminal_executor import TerminalExecutor
from src.memory import Memory
from src.internet import Internet


class Agent:
    """JARVIS Agent — Natural language file and terminal operations with persistent memory."""

    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.fm = FileManager()
        self.te = TerminalExecutor(
            workspace_path=self.config.get('workspace', 'workspace'),
            require_approval=self.config.get('permissions', {}).get('terminal', 'ask') == 'auto',
            log_path='workspace/terminal_log.json'
        )
        self.internet = Internet(research_path=self.config.get('internet_path', 'workspace/research'))
        self.memory = Memory(memory_path=self.config.get('memory_path', 'memory'))
        self.history = []
        self.max_history = self.config.get('conversation', {}).get('max_history', 10)
        self.llm = self.config.get('llm', {})
        self.memory_context = self.memory.get_context_for_llm()

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
- Use phrases like "Certainly", "Right away", "If you'd like"

## Memory
You have access to user preferences and recent conversations.
Use this context to personalize your responses.

Now, how may I assist you?"""
        if self.memory_context:
            system_content += f"\n\n## Your Stored Preferences:\n{self.memory_context}"
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
        stopwords = {'a', 'an', 'the', 'new', 'folder', 'directory', 'file', 'named', 'called', 'my', 'to', 'for', 'in'}
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

    def _handle_self_edit_request(self, text):
        text_l = text.lower()
        if any(k in text_l for k in ['can you', 'would you', 'could you', 'do you']):
            return "Certainly. I can edit my own code files. Which file would you like me to change? For example: 'edit src/agent.py change X to Y'"
        return "I'd be happy to edit my code. What would you like me to change? Please tell me which file and what to change."

    def _handle_browse(self, text):
        """Handle web browsing requests."""
        text_l = text.lower()

        # Check for URL pattern
        url_match = re.search(r'(https?://[^\s]+)', text)
        save = 'save' in text_l or 'remember' in text_l

        if url_match:
            url = url_match.group(1)
            if not self.internet.is_enabled():
                return "🌐 Internet access is disabled. Type 'enable internet' to allow browsing."
            if self.config.get('permissions', {}).get('internet', 'ask') == 'ask':
                response = input(f"🌐 Browse to {url}? (y/n): ").strip().lower()
                if response not in ['y', 'yes']:
                    return "Browsing cancelled."
            result = self.internet.browse(url, save=save)
            if result['success']:
                output = f"📄 {result['title']}\n\n{result['content'][:1000]}"
                if len(result['content']) > 1000:
                    output += "...\n(truncated)"
                if 'saved' in result:
                    output += f"\n\n💾 Saved to: {result['saved']}"
                return output
            return f"❌ {result['error']}"

        # Search pattern
        if any(k in text_l for k in ['look up', 'search for', 'find', 'google']):
            if not self.internet.is_enabled():
                return "🌐 Internet access is disabled. Type 'enable internet' to allow searching."
            query = text
            for w in ['look up', 'search for', 'find', 'google', 'what is', 'who is']:
                query = re.sub(r'\b' + w + r'\b', '', query, flags=re.I).strip()
            if not query:
                return "What would you like me to search for?"
            result = self.internet.search(query)
            if result['success']:
                output = f"🔍 Search results for '{query}':\n\n"
                for i, r in enumerate(result['results'], 1):
                    output += f"{i}. {r['title']}\n   {r['url']}\n"
                    if r['snippet']:
                        output += f"   {r['snippet'][:100]}...\n"
                return output
            return f"❌ {result['error']}"

        return "Please provide a URL to browse or a search query."

    def _handle_internet_toggle(self, text):
        """Enable or disable internet access."""
        text_l = text.lower()
        if 'enable' in text_l or 'turn on' in text_l:
            return self.internet.enable()
        if 'disable' in text_l or 'turn off' in text_l:
            return self.internet.disable()
        return "Type 'enable internet' or 'disable internet'."

    def _translate_to_command(self, text):
        text_l = text.lower()
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
        if re.search(r'\b(git\s+)?branch', text_l):
            return 'git branch'
        if re.search(r'\b(make|create|new)\s+(a\s+)?folder', text_l):
            name = self._extract_name(text)
            return f'mkdir "{name}"' if name else 'mkdir new_folder'
        if re.search(r'\b(remove|delete|rm)\s+(a\s+)?folder', text_l):
            name = self._extract_name(text)
            return f'rmdir "{name}"' if name else 'rmdir new_folder'
        if re.search(r'\blist\s+(all\s+)?files', text_l):
            return 'dir'
        if re.search(r'\blist\s+(all\s+)?folders', text_l):
            return 'dir /ad'
        if re.search(r'\b(clear|clean)\s+(the\s+)?screen', text_l):
            return 'cls'
        if re.search(r'\b(show|list)\s+(all\s+)?processes?', text_l):
            return 'tasklist'
        if re.search(r'\b(what.?s?\s+)?my\s+ip', text_l):
            return 'ipconfig | findstr "IPv4"'
        if re.search(r'\blist\s+(all\s+)?python\s+modules?', text_l):
            return 'pip list'
        return None

    def _detect_command(self, text):
        text_l = text.lower()
        cmd = self._translate_to_command(text)
        if cmd:
            return ('terminal', cmd, {'translated': True})
        direct_patterns = [r'^python\s+', r'^pip\s+', r'^git\s+', r'^dir\s+', r'^ls\s+', r'^mkdir\s+', r'^rmdir\s+', r'^cls\s*']
        for pattern in direct_patterns:
            if re.search(pattern, text_l):
                return ('terminal', text, {})
        if re.search(r'\b(run|execute)\s+(python\s+|[a-zA-Z_][\w]*\.py)', text_l):
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
        # Internet commands
        if any(k in text_l for k in ['enable internet', 'disable internet', 'turn on internet', 'turn off internet']):
            return ('internet_toggle', None, {})
        if re.search(r'(https?://[^\s]+)', text):
            return ('browse', text, {})
        if any(k in text_l for k in ['look up', 'search for', 'find', 'google', 'browse the web', 'web search']):
            return ('browse', text, {})
        return ('chat', None, {})

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
        return f"✅ {result['message']}" if result['success'] else f"❌ {result['error']}"

    def _handle_read(self, filename):
        if not filename or filename.lower() in ['files', 'all', 'list']:
            result = self.fm.list()
            items = '\n'.join(f"  [{i['type'][0]}] {i['name']}" for i in result.get('items', []))
            return f"📁 Files:\n{items}" if items else "📁 Empty"
        result = self.fm.read(filename)
        if result['success']:
            return f"📄 {filename}:\n\n{result['content']}"
        return f"❌ {result['error']}"

    def _handle_edit(self, text, filename):
        if self._is_jarvis_self_edit(text):
            return self._handle_self_edit_request(text)
        if not filename:
            return "Which file would you like me to edit? For example: 'edit src/agent.py change X to Y'"
        m = self._extract_filename(text)
        if m:
            filename = m
        m = re.search(r'\b(change|replace)\s+["\']([^"\']+)["\']?\s+(?:to|with)\s+["\']([^"\']+)["\']', text, re.I)
        if not m:
            return 'What would you like to change? Format: \'edit "file.md" change "old" to "new"\''
        old_text, new_text = m.group(2), m.group(3)
        result = self.fm.edit(filename, old_text, new_text)
        return result['message'] if result['success'] else f"❌ {result['error']}"

    def _handle_delete(self, filename):
        if not filename:
            return "Which file would you like me to delete?"
        result = self.fm.delete(filename)
        return result['message'] if result['success'] else f"❌ {result['error']}"

    def _handle_list(self):
        result = self.fm.list()
        if result['success']:
            items = '\n'.join(f"  [{i['type'][0]}] {i['name']}" for i in result.get('items', []))
            return f"📁 Files:\n{items}" if items else "📁 Empty"
        return f"❌ {result['error']}"

    def _handle_terminal(self, command, translated=False):
        cmd = command.strip()
        result = self.te.execute(cmd)
        output = ""
        if result.get('cwd'):
            output += f"📁 CWD: {result['cwd']}\n"
        output += f"📟 Status: {result['status']} (exit: {result['exit_code']})\n"
        output += f"⏱️ {result['duration_ms']}ms\n"
        if translated:
            output += f"🔄 {command}\n"
        output += f"\n{'='*40}\n"
        if result['stdout']:
            output += result['stdout']
        if result['stderr']:
            output += f"\n⚠️ {result['stderr']}"
        output += f"{'='*40}"
        return output

    def _handle_chat(self, text):
        response = self._call_llm_with_memory(text)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": response})
        self.memory.save_conversation(text, response)
        return f"JARVIS: {response}"

    def _handle_learn(self, text):
        m = re.search(r'\b(remember|learn)\s+(?:that\s+)?(.+?)\s+(?:is|equals?)\s+(.+)', text, re.I)
        if m:
            key = m.group(2).strip()
            value = m.group(3).strip().rstrip('.')
            self.memory.save_user_preference(key, value)
            return f"✅ Remember: {key} = {value}"
        m = re.search(r'\bI\s+(?:am|work as)\s+(.+)', text, re.I)
        if m:
            value = m.group(1).strip().rstrip('.')
            self.memory.save_user_preference("my role", value)
            return f"✅ Remember: my role = {value}"
        return "❌ Format: 'remember that [key] is [value]'"

    def process(self, user_input):
        user_input = user_input.strip()
        if not user_input:
            return "Enter a command or question."
        if re.search(r'\b(remember|learn|I\s+(?:am|work as))\s+', user_input, re.I):
            return self._handle_learn(user_input)
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
            'chat': lambda: self._handle_chat(user_input)
        }[op]()


if __name__ == "__main__":
    print("JARVIS: Commands: create/read/edit/delete/list, mkdir/rmdir, remember that..., browse [url], search [query]")
    while (cmd := input("\nYou: ")) and cmd.lower() not in ['exit', 'quit']:
        print(Agent().process(cmd))