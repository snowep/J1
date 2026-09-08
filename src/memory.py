import os
import json
from datetime import datetime
from pathlib import Path


class Memory:
    """JARVIS Persistent Memory — Store conversation summaries and facts as markdown files."""

    def __init__(self, memory_path='memory'):
        project_root = os.path.dirname(os.path.dirname(__file__))
        self.memory_dir = os.path.normpath(os.path.join(project_root, memory_path))
        os.makedirs(self.memory_dir, exist_ok=True)

    def _now(self):
        """Get current timestamp in ISO format."""
        return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

    # === CONVERSATION MEMORY ===
    def save_conversation(self, user_input, assistant_response, conversation_id=None):
        """Save a conversation turn to daily log."""
        today = datetime.utcnow().strftime('%Y-%m-%d')
        log_file = os.path.join(self.memory_dir, f'conversation_{today}.md')
        
        timestamp = self._now()
        entry = f"### {timestamp}\n\n**You:** {user_input}\n\n**JARVIS:** {assistant_response}\n\n---\n\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        
        return log_file

    def get_recent_conversations(self, days=3):
        """Get recent conversation summaries from daily logs."""
        conversations = []
        today = datetime.utcnow()
        
        for i in range(days):
            date = (today.replace(day=1) if today.day <= 7 else today).strftime('%Y-%m-%d')
            # Simple: look at last N days
            check_date = (today.replace(day=today.day - i)).strftime('%Y-%m-%d')
            log_file = os.path.join(self.memory_dir, f'conversation_{check_date}.md')
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    conversations.append(f.read())
        
        return '\n'.join(conversations)

    # === FACT MEMORY ===
    def save_fact(self, category, key, value):
        """Save a key-value fact to a category file."""
        category_file = os.path.join(self.memory_dir, f'facts_{category}.md')
        
        # Read existing facts
        facts = self._load_facts(category)
        
        # Add/Update fact
        facts[key] = {
            'value': value,
            'updated': self._now()
        }
        
        # Save back
        content = f"# {category.title()} Facts\n\n"
        content += f"*Last updated: {self._now()}*\n\n"
        for k, v in facts.items():
            content += f"## {k}\n\n{value}\n\n"
        
        with open(category_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return category_file

    def _load_facts(self, category):
        """Load facts from a category file."""
        category_file = os.path.join(self.memory_dir, f'facts_{category}.md')
        if not os.path.exists(category_file):
            return {}
        
        facts = {}
        with open(category_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse simple markdown format
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
        """Get all facts, optionally from a specific category."""
        if category:
            return self._load_facts(category)
        
        # Get all fact files
        all_facts = {}
        for f in os.listdir(self.memory_dir):
            if f.startswith('facts_') and f.endswith('.md'):
                cat = f[6:-3]  # Remove 'facts_' and '.md'
                all_facts[cat] = self._load_facts(cat)
        return all_facts

    def save_user_preference(self, preference, value):
        """Save a user preference as a fact."""
        return self.save_fact('user', preference, value)

    def get_user_preferences(self):
        """Get all user preferences."""
        return self.get_facts('user')

    # === DECISION MEMORY ===
    def save_decision(self, decision, context, outcome=None):
        """Save a decision with context and optional outcome."""
        decision_file = os.path.join(self.memory_dir, 'decisions.md')
        
        entry = f"## {self._now()}\n\n**Decision:** {decision}\n\n**Context:** {context}\n"
        if outcome:
            entry += f"\n**Outcome:** {outcome}\n"
        entry += "\n---\n\n"
        
        with open(decision_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        
        return decision_file

    # === CONTEXT FOR LLM ===
    def get_context_for_llm(self, max_convo_lines=50):
        """Build a context string to prepend to LLM system prompt."""
        context_parts = []
        
        # User preferences
        prefs = self.get_user_preferences()
        if prefs:
            pref_lines = ["## User Preferences"]
            for k, v in prefs.items():
                if isinstance(v, dict):
                    pref_lines.append(f"- {k}: {v.get('value', '')}")
            if len(pref_lines) > 1:
                context_parts.append('\n'.join(pref_lines))
        
        # Recent conversations (truncated)
        recent = self.get_recent_conversations(days=3)
        if recent:
            lines = recent.split('\n')[-max_convo_lines:]
            context_parts.append('## Recent Conversations\n' + '\n'.join(lines))
        
        return '\n\n'.join(context_parts) if context_parts else ""


if __name__ == "__main__":
    print("Testing JARVIS Memory...")
    mem = Memory()
    
    # Save a conversation
    mem.save_conversation("Hello JARVIS!", "Hello! I'm your AI assistant.")
    
    # Save a preference
    mem.save_user_preference("favorite_color", "blue")
    
    # Save a decision
    mem.save_decision("Use markdown for memory", "Easy to read and edit", None)
    
    # Get context
    ctx = mem.get_context_for_llm()
    print(f"Context for LLM:\n{ctx}")
    
    print("\nMemory files created:")
    for f in os.listdir(mem.memory_dir):
        print(f"  - {f}")