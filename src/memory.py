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
        """Ensure index file exists."""
        if not os.path.exists(self.index_file):
            self._update_index({})

    def _update_index(self, memory_files):
        """Update the memory index file."""
        content = f"# Memory Index\n\n*Last updated: {self._now()}*\n\n"
        content += "---\n\n"
        
        categories = {
            'conversations': [],
            'facts': [],
            'decisions': [],
            'other': []
        }
        
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
        """Save conversation to daily log and auto-update index."""
        today = datetime.utcnow().strftime('%Y-%m-%d')
        log_file = os.path.join(self.memory_dir, f'conversation_{today}.md')
        entry = f"### {self._now()}\n\n**You:** {user_input}\n\n**JARVIS:** {assistant_response}\n\n---\n\n"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        self._update_index({})
        return log_file

    def save_fact(self, category, key, value):
        """Save a fact and auto-update index."""
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
        """Get all facts with auto-index."""
        all_facts = {}
        for f in os.listdir(self.memory_dir):
            if f.startswith('facts_') and f.endswith('.md'):
                cat = f[6:-3]
                all_facts[cat] = self._load_facts(cat)
        return all_facts

    def save_user_preference(self, preference, value):
        """Save user preference with auto-index."""
        return self.save_fact('user', preference, value)

    def get_user_preferences(self):
        """Get all user preferences."""
        return self.get_facts('user')

    def save_decision(self, decision, context, outcome=None):
        """Save a decision with auto-index."""
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
        """Build context for LLM with memory index."""
        context_parts = []
        prefs = self.get_user_preferences()
        if prefs:
            pref_lines = ["## User Preferences"]
            for k, v in prefs.get('user', {}).items():
                if isinstance(v, dict):
                    pref_lines.append(f"- {k}: {v.get('value', '')}")
            if len(pref_lines) > 1:
                context_parts.append('\n'.join(pref_lines))
        
        # Include index reference
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                index_content = f.read()[:500]
            context_parts.append(f"## Memory Index\n\n{index_content}...")
        
        return '\n\n'.join(context_parts) if context_parts else ""

    def get_recent_conversations(self, days=3):
        """Get recent conversations."""
        conversations = []
        today = datetime.utcnow()
        for i in range(days):
            check_date = (today.replace(day=today.day - i)).strftime('%Y-%m-%d')
            log_file = os.path.join(self.memory_dir, f'conversation_{check_date}.md')
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    conversations.append(f.read())
        return '\n'.join(conversations)


class AutonomousPlanner:
    """JARVIS Autonomous Planner — Plans and executes multi-step actions."""

    def __init__(self, agent):
        self.agent = agent
        self.fm = agent.fm
        self.memory = agent.memory
        self.te = agent.te

    def plan_and_execute(self, high_level_goal):
        """
        Plan and execute a high-level goal autonomously.
        
        Returns:
            List of actions taken and results
        """
        # Create a plan using LLM
        plan_prompt = f"""Break down this goal into concrete steps. Respond with ONLY a numbered list:

Goal: {high_level_goal}

Steps (one per line, action verb first):
1. """
        plan = self.agent._call_llm(plan_prompt)
        
        actions_taken = []
        
        # Parse plan and execute
        lines = plan.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            
            # Remove number prefix
            action = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            
            # Execute based on action type
            result = self._execute_action(action)
            actions_taken.append({'action': action, 'result': result})
            
            # Log to memory
            self.memory.save_decision(action, high_level_goal, result.get('summary', 'Completed'))
        
        return {
            'goal': high_level_goal,
            'plan': plan,
            'actions': actions_taken,
            'summary': f"Completed {len(actions_taken)} actions"
        }

    def _execute_action(self, action):
        """Execute a single action from the plan."""
        action_l = action.lower()
        
        # Read file action
        if action_l.startswith('read ') or action_l.startswith('open '):
            filename = self._extract_filename(action)
            if filename:
                result = self.fm.read(filename)
                return {'action': action, 'summary': f'Read {filename}', 'content': result.get('content', '')[:200]}
        
        # Write file action
        if action_l.startswith('write ') or action_l.startswith('create '):
            filename = self._extract_filename(action)
            if filename:
                # Generate content using LLM
                content = self.agent._call_llm_with_memory(f"Write content for: {filename}. Action: {action}")
                result = self.fm.write(filename, content, overwrite=True)
                return {'action': action, 'summary': f'Created {filename}'}
        
        # Run code action
        if action_l.startswith('run ') or action_l.startswith('execute '):
            # Extract command
            cmd = re.sub(r'^(run|execute)\s+', '', action, flags=re.I).strip()
            if cmd:
                result = self.te.execute(cmd)
                return {'action': action, 'summary': f'Ran: {cmd[:30]}...', 'output': result.get('stdout', '')[:100]}
        
        # Search/browse action
        if action_l.startswith('search ') or action_l.startswith('browse '):
            query = re.sub(r'^(search|browse)\s+', '', action, flags=re.I).strip()
            if query:
                return {'action': action, 'summary': f'Searched: {query}'}
        
        # Default: just acknowledge the action
        return {'action': action, 'summary': 'Acknowledged'}

    def _extract_filename(self, text):
        """Extract filename from action text."""
        m = re.search(r'["\']([^"\']+\.(md|txt|py|json))["\']', text, re.I)
        if m:
            return m.group(1)
        m = re.search(r'(?:file|note|script)\s+named?\s+(\w+\.(md|txt|py|json))', text, re.I)
        if m:
            return m.group(1)
        return None


if __name__ == "__main__":
    print("Testing Enhanced Memory with Index...")
    mem = Memory()
    
    # Save some facts
    mem.save_user_preference('name', 'Tony')
    mem.save_user_preference('role', 'Developer')
    
    # Check index was created
    print(f"Index exists: {os.path.exists(mem.index_file)}")
    
    # Get context
    ctx = mem.get_context_for_llm()
    print(f"Context length: {len(ctx)} chars")