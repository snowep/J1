import os
import json
import re
from datetime import datetime
from pathlib import Path


class Memory:
    """JARVIS Persistent Memory — With auto-indexing and self-learning."""

    def __init__(self, memory_path='.jarvis/memory'):
        project_root = os.path.dirname(os.path.dirname(__file__))
        self.memory_dir = os.path.normpath(os.path.join(project_root, memory_path))
        self.index_file = os.path.join(self.memory_dir, 'index.md')
        os.makedirs(self.memory_dir, exist_ok=True)
        self._ensure_index()

    def _now(self):
        return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

    def _ensure_index(self):
        if not os.path.exists(self.index_file):
            self._update_index({})

    def _update_index(self, memory_files):
        content = f"# Memory Index\n\n*Last updated: {self._now()}*\n\n---\n\n"
        categories = {'conversations': [], 'facts': [], 'decisions': [], 'other': []}
        for f in os.listdir(self.memory_dir):
            if f == 'index.md':
                continue
            fpath = os.path.join(self.memory_dir, f)
            if os.path.isfile(fpath):
                if 'conversation' in f:
                    categories['conversations'].append(f)
                elif 'fact' in f:
                    categories['facts'].append(f)
                elif 'decision' in f:
                    categories['decisions'].append(f)
                else:
                    categories['other'].append(f)
        for cat, files in categories.items():
            if files:
                content += f"## {cat.title()}\n\n"
                for f in sorted(files):
                    title = f.replace('.md', '').replace('_', ' ').title()
                    content += f"- [[{f}]] - {title}\n"
                content += "\n"
        with open(self.index_file, 'w', encoding='utf-8') as f:
            f.write(content)

    def save_conversation(self, user_input, assistant_response):
        today = datetime.utcnow().strftime('%Y-%m-%d')
        log_file = os.path.join(self.memory_dir, f'conversation_{today}.md')
        entry = f"### {self._now()}\n\n**You:** {user_input}\n\n**JARVIS:** {assistant_response}\n\n---\n\n"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        self._update_index({})
        return log_file

    def save_fact(self, category, key, value):
        category_file = os.path.join(self.memory_dir, f'facts_{category}.md')
        facts = self._load_facts(category) if os.path.exists(category_file) else {}
        facts[key] = {'value': value, 'updated': self._now()}
        content = f"# {category.title()} Facts\n\n*Last updated: {self._now()}*\n\n"
        for k, v in facts.items():
            content += f"## {k}\n\n{v['value']}\n\n"
        with open(category_file, 'w', encoding='utf-8') as f:
            f.write(content)
        self._update_index({})
        return category_file

    def _load_facts(self, category):
        category_file = os.path.join(self.memory_dir, f'facts_{category}.md')
        if not os.path.exists(category_file):
            return {}
        facts = {}
        with open(category_file, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.split('\n')
        current_key = None
        for line in lines:
            if line.startswith('## '):
                current_key = line[3:].strip()
                facts[current_key] = {'value': '', 'updated': None}
            elif current_key and line.strip():
                facts[current_key]['value'] = line.strip()
        return facts

    def get_facts(self, category=None):
        all_facts = {}
        for f in os.listdir(self.memory_dir):
            if f.startswith('facts_') and f.endswith('.md'):
                cat = f[6:-3]
                all_facts[cat] = self._load_facts(cat)
        return all_facts

    def save_user_preference(self, preference, value):
        return self.save_fact('user', preference, value)

    def get_user_preferences(self):
        return self.get_facts('user')

    def save_decision(self, decision, context, outcome=None):
        decision_file = os.path.join(self.memory_dir, 'decisions.md')
        entry = f"## {self._now()}\n\n**Decision:** {decision}\n\n**Context:** {context}\n"
        if outcome:
            entry += f"\n**Outcome:** {outcome}\n"
        entry += "\n---\n\n"
        with open(decision_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        self._update_index({})
        return decision_file

    def get_context_for_llm(self, max_convo_lines=30):
        context_parts = []
        prefs = self.get_user_preferences()
        if prefs:
            pref_lines = ["## User Preferences"]
            for k, v in prefs.get('user', {}).items():
                if isinstance(v, dict):
                    pref_lines.append(f"- {k}: {v.get('value', '')}")
            if len(pref_lines) > 1:
                context_parts.append('\n'.join(pref_lines))
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                index_content = f.read()[:500]
            context_parts.append(f"## Memory Index\n\n{index_content}...")
        return '\n\n'.join(context_parts) if context_parts else ""


class AutonomousPlanner:
    """JARVIS Autonomous Planner — Plans, executes, and RECOVERS from failures."""

    def __init__(self, agent, max_retries=2, abort_on_major_failure=False):
        self.agent = agent
        self.fm = agent.fm
        self.memory = agent.memory
        self.te = agent.te
        self.max_retries = max_retries
        self.abort_on_major_failure = abort_on_major_failure

    def plan_and_execute(self, high_level_goal):
        plan = self._generate_plan(high_level_goal)
        actions_taken = []
        errors = []
        recovered = []

        for action in plan:
            result = self._execute_with_recovery(action, high_level_goal)
            actions_taken.append({'action': action, 'result': result, 'success': result.get('success', False)})
            if not result.get('success'):
                errors.append({'action': action, 'error': result.get('error', 'Unknown')})
            elif result.get('recovered'):
                recovered.append({'action': action, 'strategy': result.get('recovery_strategy')})
            self.memory.save_decision(action, high_level_goal, result.get('summary', 'Completed'))
            if self.abort_on_major_failure and not result.get('success') and result.get('critical'):
                actions_taken.append({'action': 'ABORT', 'result': {'summary': f'Aborted: {result.get("error")}', 'success': False}})
                break

        return {
            'goal': high_level_goal,
            'plan': '\n'.join(f"{i+1}. {a}" for i, a in enumerate(plan)),
            'actions': actions_taken,
            'errors': errors,
            'recovered': recovered,
            'success_count': sum(1 for a in actions_taken if a.get('success')),
            'failure_count': len(errors),
            'summary': self._build_summary(actions_taken, errors, recovered)
        }

    def _generate_plan(self, high_level_goal):
        workspace_files = self.fm.list()
        file_list = ', '.join(f['name'] for f in workspace_files.get('items', []) if f['type'] == 'file') or 'none'

        plan_prompt = f"""Break this goal into concrete, file-level actions you can execute right now.
Available files in workspace: [{file_list}]

Each step MUST start with ONE of these verbs: read, write, delete, list, run, search, remember
Each step must name a SPECIFIC filename from the list above.
Do NOT write vague phrases like "review" or "analyze". Write EXACTLY what to do.

Goal: {high_level_goal}

Steps:
1."""

        for attempt in range(self.max_retries + 1):
            plan_text = self.agent._call_llm(plan_prompt)
            steps = self._parse_plan(plan_text)
            if steps:
                # Ensure at least half the steps are concrete actions
                concrete = [s for s in steps if re.match(r'^(read|write|delete|list|run|search|remember|mkdir|rmdir)\b', s, re.I)]
                if len(concrete) >= max(1, len(steps) * 0.5):
                    return steps
            plan_prompt = f"Give me a numbered list. Each line must start with: read, write, delete, list, run, search, or remember. Use actual filenames from: [{file_list}]. No bold, no markdown.\n\nGoal: {high_level_goal}"

        # If all retries failed, return a minimal fallback: list files
        return ["list files"]

    def _parse_plan(self, plan_text):
        if not plan_text:
            return []
        steps = []
        for line in plan_text.strip().split('\n'):
            line = line.strip()
            # Strip markdown bold: **read** -> read, and stray backticks
            line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)
            line = line.replace('`', '')
            m = re.match(r'^\d+[\.\)]\s*(.+)', line)
            if m:
                steps.append(m.group(1).strip())
        return steps

    def _execute_with_recovery(self, action, goal):
        result = self._execute_action(action)
        if result.get('success'):
            return result

        error = result.get('error', 'Unknown error')
        strategies = self._generate_alternatives(action, error)
        for strategy in strategies:
            result = self._execute_action(strategy)
            if result.get('success'):
                result['recovered'] = True
                result['recovery_strategy'] = f"'{action}' → '{strategy}'"
                return result

        return {'action': action, 'success': False, 'error': error, 'critical': result.get('critical', False), 'summary': f'Failed: {action}'}

    def _generate_alternatives(self, action, error):
        alternatives = []
        action_l = action.lower()

        if 'not found' in error.lower() or 'no such file' in error.lower():
            filename = self._extract_filename(action)
            if filename:
                if not filename.endswith('.md'):
                    alternatives.append(action.replace(filename, f"{filename}.md"))
                # Try swapping a non-md extension (report.txt → report.md)
                base, ext = os.path.splitext(filename)
                if ext and ext != '.md':
                    alternatives.append(action.replace(filename, base + '.md'))
                alternatives.append(action.replace(filename, filename.lower()))
                alternatives.append(action.replace(filename, filename.title()))

        elif 'permission' in error.lower() or 'access denied' in error.lower():
            alternatives.append("list files")

        elif 'timed out' in error.lower():
            alternatives.append(action.replace('search', 'browse'))

        elif action_l.startswith('write ') or action_l.startswith('create '):
            filename = self._extract_filename(action)
            if filename:
                alternatives.append(f"write {filename} with placeholder content")

        cleaned = re.sub(r'\b(please|kindly|now|quickly|carefully|thoroughly|details|about|of|from)\b', '', action, flags=re.I).strip()
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned != action and len(cleaned.split()) >= 2:
            alternatives.append(cleaned)

        # Remove duplicates while preserving order
        seen = set()
        alternatives = [a for a in alternatives if not (a in seen or seen.add(a))]

        return alternatives

    def _execute_action(self, action):
        action_l = action.lower()

        try:
            # ── READ ──────────────────────────────────────
            if re.match(r'^(read|open|cat|view)\b', action_l):
                filename = self._extract_filename(action)
                if filename:
                    result = self.fm.read(filename)
                    if result['success']:
                        return {'action': action, 'summary': f'Read {filename}', 'content': result['content'][:200], 'success': True}
                    return {'action': action, 'success': False, 'error': result['error']}
                # No filename found — list files instead as fallback
                return self._execute_action("list files")

            # ── WRITE / CREATE ─────────────────────────────
            if re.match(r'^(write|create|save|make|generate)\b', action_l):
                filename = self._extract_filename(action)
                if not filename:
                    # Try to infer filename from context
                    m = re.search(r'\b(\w+\.md)\b', action)
                    filename = m.group(1) if m else None
                if filename:
                    content_hint = re.sub(r'^(write|create|save|make|generate)\s+(\S+)\s*', '', action, flags=re.I).strip()
                    content = self.agent._call_llm_with_memory(
                        f"Write markdown content for: {filename}. Context: {action}"
                    )
                    if content.startswith('Error'):
                        return {'action': action, 'success': False, 'error': 'LLM content generation failed'}
                    result = self.fm.write(filename, content, overwrite=True)
                    if result['success']:
                        return {'action': action, 'summary': f'Created {filename}', 'success': True}
                    return {'action': action, 'success': False, 'error': result['error']}
                return {'action': action, 'success': False, 'error': 'Could not determine filename'}

            # ── DELETE ─────────────────────────────────────
            if re.match(r'^(delete|remove|rm|del)\b', action_l):
                filename = self._extract_filename(action)
                if filename:
                    result = self.fm.delete(filename)
                    if result['success']:
                        return {'action': action, 'summary': f'Deleted {filename}', 'success': True}
                    return {'action': action, 'success': False, 'error': result['error']}
                return {'action': action, 'success': False, 'error': 'Could not determine filename to delete'}

            # ── LIST ───────────────────────────────────────
            if re.match(r'^(list|ls|dir|show files)\b', action_l):
                result = self.fm.list()
                if result['success']:
                    names = [f['name'] for f in result.get('items', [])]
                    return {'action': action, 'summary': f'Listed {len(names)} items', 'files': names, 'success': True}
                return {'action': action, 'success': False, 'error': result['error']}

            # ── RUN / EXECUTE ──────────────────────────────
            if re.match(r'^(run|execute|python|pip|git)\b', action_l):
                cmd = action
                # Prefer natural-language translation (e.g. "push changes" → "git push")
                if hasattr(self.agent, '_translate_to_command'):
                    translated = self.agent._translate_to_command(action)
                    if translated:
                        cmd = translated
                # Strip leading 'run'/'execute' verb: "run python hello.py" → "python hello.py"
                cmd = re.sub(r'^(?:run|execute)\s+', '', cmd, flags=re.I).strip() or action
                result = self.te.execute(cmd)
                if result['status'] == 'success':
                    return {'action': action, 'summary': f'Ran: {cmd[:40]}', 'output': result.get('stdout', '')[:100], 'success': True}
                return {'action': action, 'success': False, 'error': result.get('stderr', 'Command failed'), 'critical': True}

            # ── SEARCH / BROWSE ────────────────────────────
            if re.match(r'^(search|browse|look up|find|google)\b', action_l):
                query = re.sub(r'^(search|browse|look up|find|google)\s+(for\s+)?', '', action, flags=re.I).strip()
                if query:
                    result = self.agent.internet.search(query)
                    if result.get('success'):
                        return {'action': action, 'summary': f'Searched: {query} ({len(result.get("results", []))} results)', 'success': True}
                    return {'action': action, 'success': False, 'error': result.get('error', 'Search failed')}
                return {'action': action, 'success': False, 'error': 'No search query found'}

            # ── REMEMBER / LEARN ───────────────────────────
            if re.match(r'^(remember|learn|store)\b', action_l):
                m = re.search(r'\b(remember|learn|store)\s+(?:that\s+)?(.+?)\s+(?:is|=)\s+(.+)', action, re.I)
                if m:
                    key, value = m.group(2).strip(), m.group(3).strip().rstrip('.')
                    self.memory.save_user_preference(key, value)
                    return {'action': action, 'summary': f'Remembered: {key} = {value}', 'success': True}
                return {'action': action, 'success': False, 'error': 'Could not parse key-value pair'}

            # ── ACKNOWLEDGE anything else ──────────────────
            return {'action': action, 'success': True, 'summary': f'Acknowledged: {action}'}

        except Exception as e:
            return {'action': action, 'success': False, 'error': str(e), 'critical': True}

    def _build_summary(self, actions, errors, recovered):
        total = len(actions)
        parts = [f"Completed {total} actions"]
        if errors:
            parts.append(f"with {len(errors)} error(s)")
        if recovered:
            parts.append(f"({len(recovered)} recovered)")
        return ' '.join(parts)

    def _extract_filename(self, text):
        m = re.search(r'["\']([^"\']+\.(md|txt|py|json|csv|html))["\']', text, re.I)
        if m:
            return m.group(1)
        m = re.search(r'\b([a-zA-Z0-9_\-]+\.(md|txt|py|json|csv|html))\b', text, re.I)
        if m:
            return m.group(1)
        m = re.search(r'(\w+)\.(md|txt|py|json)', text, re.I)
        if m:
            return f'{m.group(1)}.{m.group(2)}'
        # Fallback: allow bare filenames like "read report" (no extension)
        m = re.search(r'([a-zA-Z0-9_][a-zA-Z0-9_\-.]*)\s*$', text.strip())
        if m:
            word = m.group(1)
            if word.lower() not in ('files', 'file', 'folder', 'directory', 'status', 'the', 'all', 'everything', 'content', 'placeholder'):
                return word
        return None
