import os
import json
import re
from datetime import datetime
from pathlib import Path


class Memory:
    """JARVIS Persistent Memory — With auto-indexing and self-learning."""

    def __init__(self, memory_path='memory'):
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
        """
        Plan and execute a high-level goal with error recovery.
        
        Returns:
            Dict with goal, plan, actions, errors, and recovery info
        """
        plan = self._generate_plan(high_level_goal)
        
        actions_taken = []
        errors = []
        recovered = []
        
        for i, action in enumerate(plan):
            result = self._execute_with_recovery(action, high_level_goal)
            
            actions_taken.append({
                'action': action,
                'result': result,
                'success': result.get('success', False)
            })
            
            if not result.get('success'):
                errors.append({'action': action, 'error': result.get('error', 'Unknown')})
            elif result.get('recovered'):
                recovered.append({'action': action, 'strategy': result.get('recovery_strategy')})
            
            self.memory.save_decision(action, high_level_goal, result.get('summary', 'Completed'))
            
            # Abort if configured and this was a major failure
            if self.abort_on_major_failure and not result.get('success') and result.get('critical'):
                actions_taken.append({
                    'action': 'ABORT',
                    'result': {'summary': f'Aborted after critical failure: {result.get("error")}', 'success': False}
                })
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
        """Generate a plan with retry on malformed output."""
        plan_prompt = f"""Break down this goal into concrete steps. Respond with ONLY a numbered list.

Goal: {high_level_goal}

Steps (one per line, action verb first):
1."""
        
        for attempt in range(self.max_retries + 1):
            plan_text = self.agent._call_llm(plan_prompt)
            steps = self._parse_plan(plan_text)
            if steps:
                return steps
            # Retry with stronger instruction if failed to parse
            plan_prompt = f"""You did not provide a valid numbered list. Again, break down this goal.
Respond with ONLY numbered lines starting with numbers:

Goal: {high_level_goal}"""
        
        # Fallback: return empty plan rather than crash
        return []

    def _parse_plan(self, plan_text):
        """Parse plan, tolerant of malformed output."""
        if not plan_text:
            return []
        steps = []
        for line in plan_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^\d+[\.\)]\s*(.+)', line)
            if m:
                steps.append(m.group(1).strip())
        return steps

    def _execute_with_recovery(self, action, goal):
        """Execute an action with retry and fallback strategies."""
        # Primary attempt
        result = self._execute_action(action)
        
        # If succeeded, return
        if result.get('success'):
            return result
        
        # If failed, try alternative approaches
        error = result.get('error', 'Unknown error')
        strategies = self._generate_alternatives(action, error)
        
        for strategy in strategies:
            result = self._execute_action(strategy)
            if result.get('success'):
                result['recovered'] = True
                result['recovery_strategy'] = f"'{action}' → '{strategy}'"
                return result
        
        # Add final failure result
        return {
            'action': action,
            'success': False,
            'error': error,
            'critical': result.get('critical', False),
            'summary': f'Failed: {action}'
        }

    def _generate_alternatives(self, action, error):
        """Generate alternative approaches when an action fails."""
        alternatives = []
        action_l = action.lower()
        
        if 'not found' in error.lower() or 'no such file' in error.lower():
            # Try different filename patterns
            if action_l.startswith('read '):
                filename = self._extract_filename(action)
                if filename:
                    # Try with .md extension if missing
                    if not filename.endswith('.md'):
                        alternatives.append(f"read {filename}.md")
                    # Try lowercase
                    alternatives.append(f"read {filename.lower()}")
        
        elif 'permission' in error.lower() or 'access denied' in error.lower():
            alternatives.append(f"list files")
        
        elif 'timed out' in error.lower() or 'timeout' in error.lower():
            alternatives.append(action.replace('search', 'browse'))
        
        elif action_l.startswith('write ') or action_l.startswith('create '):
            # Alternative: retry with simpler content
            filename = self._extract_filename(action)
            if filename:
                alternatives.append(f"write {filename} with basic content")
        
        # Always try removing excessive phrasing
        cleaned = re.sub(r'\b(please|kindly|now|quickly|carefully)\b', '', action, flags=re.I).strip()
        if cleaned != action:
            alternatives.append(cleaned)
        
        return alternatives

    def _execute_action(self, action):
        """Execute a single action with error capture."""
        action_l = action.lower()
        
        try:
            if action_l.startswith('read ') or action_l.startswith('open '):
                filename = self._extract_filename(action)
                if filename:
                    result = self.fm.read(filename)
                    if result['success']:
                        return {'action': action, 'summary': f'Read {filename}', 'content': result['content'][:200], 'success': True}
                    return {'action': action, 'success': False, 'error': result['error']}
            
            elif action_l.startswith('write ') or action_l.startswith('create '):
                filename = self._extract_filename(action)
                if filename:
                    # Extract content hint from after filename
                    content_hint = re.sub(r'^(write|create)\s+\S+\s*', action, '', flags=re.I).strip()
                    content = self.agent._call_llm_with_memory(
                        f"Write content for: {filename}. Action: {action}. Context hint: {content_hint}"
                    )
                    if content.startswith('Error'):
                        return {'action': action, 'success': False, 'error': 'LLM content generation failed'}
                    result = self.fm.write(filename, content, overwrite=True)
                    if result['success']:
                        return {'action': action, 'summary': f'Created {filename}', 'success': True}
                    return {'action': action, 'success': False, 'error': result['error']}
            
            elif action_l.startswith('run ') or action_l.startswith('execute '):
                cmd = re.sub(r'^(run|execute)\s+', '', action, flags=re.I).strip()
                if cmd:
                    result = self.te.execute(cmd)
                    if result['status'] == 'success':
                        return {'action': action, 'summary': f'Ran: {cmd[:30]}', 'output': result.get('stdout', '')[:100], 'success': True}
                    return {'action': action, 'success': False, 'error': result.get('stderr', 'Command failed'), 'critical': True}
            
            elif action_l.startswith('search ') or action_l.startswith('browse '):
                query = re.sub(r'^(search|browse)\s+', '', action, flags=re.I).strip()
                if query:
                    return {'action': action, 'summary': f'Searched: {query}', 'success': True}
            
            elif action_l.startswith('mkdir ') or action_l.startswith('make folder'):
                name = self._extract_filename(action) or 'new_folder'
                result = self.fm.write(f'{name}/index.md', '# Folder\n', overwrite=True)
                if result['success']:
                    return {'action': action, 'summary': f'Created folder {name}', 'success': True}
            
            elif action_l.startswith('copy ') or action_l.startswith('move '):
                # Attempt file copy via terminal
                parts = re.sub(r'^(copy|move)\s+', '', action, flags=re.I).split()
                if len(parts) >= 2:
                    result = self.te.execute(f'copy {parts[0]} {parts[1]}')
                    return {'action': action, 'summary': f'Copied {parts[0]} → {parts[1]}', 'success': True}
            
        except Exception as e:
            return {'action': action, 'success': False, 'error': str(e), 'critical': True}
        
        # Acknowledge if we don't understand the action
        return {'action': action, 'success': True, 'summary': 'Acknowledged'}

    def _build_summary(self, actions, errors, recovered):
        """Build a human-readable summary."""
        total = len(actions)
        success = len(errors) == 0
        parts = [f"Completed {total} actions"]
        if errors:
            parts.append(f"with {len(errors)} error(s)")
        if recovered:
            parts.append(f"({len(recovered)} recovered via alternative approach)")
        return ' '.join(parts)

    def _extract_filename(self, text):
        """Extract filename from action text."""
        m = re.search(r'["\']([^"\']+\.(md|txt|py|json))["\']', text, re.I)
        if m:
            return m.group(1)
        m = re.search(r'(?:file|note|script)\s+named?\s+(\S+\.(?:md|txt|py|json))', text, re.I)
        if m:
            return m.group(1)
        m = re.search(r'\b([a-zA-Z0-9_\-]+\.(md|txt|py|json))\b', text, re.I)
        if m:
            return m.group(1)
        return None