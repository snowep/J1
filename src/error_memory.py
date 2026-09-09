"""
JARVIS Error Memory — Persistent memory for errors, fixes, and lessons learned.
When JARVIS encounters an error, it logs the pattern, cause, and fix.
Before executing actions, it checks for known error patterns to avoid repeating mistakes.
"""
import os
import re
import json
from datetime import datetime


class ErrorMemory:
    """Manages persistent error memory — logs errors, recalls fixes, prevents repeats."""

    def __init__(self, memory_dir='.jarvis/memory'):
        self.memory_dir = memory_dir
        self.errors_file = os.path.join(memory_dir, 'error_log.md')
        self.lessons_file = os.path.join(memory_dir, 'lessons_learned.md')
        self.patterns_file = os.path.join(memory_dir, 'error_patterns.json')
        os.makedirs(memory_dir, exist_ok=True)
        self.patterns = self._load_patterns()

    def _load_patterns(self):
        """Load known error patterns from JSON."""
        if os.path.exists(self.patterns_file):
            try:
                with open(self.patterns_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_patterns(self):
        """Save error patterns to JSON for fast lookup."""
        with open(self.patterns_file, 'w', encoding='utf-8') as f:
            json.dump(self.patterns, f, indent=2, ensure_ascii=False)

    def _now(self):
        return datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    # ── RECORDING ERRORS ──────────────────────────────────────

    def record_error(self, command, error_msg, fix=None, lesson=None):
        """Record an error with its cause, fix, and lesson learned.

        Args:
            command: The command or action that triggered the error
            error_msg: The error message or description
            fix: What was changed to resolve it (if known)
            lesson: The general lesson to remember (if known)
        """
        timestamp = self._now()
        error_id = self._generate_id(command, error_msg)

        # Store as structured pattern
        self.patterns[error_id] = {
            'command_pattern': self._normalize_command(command),
            'error_pattern': self._normalize_error(error_msg),
            'original_command': command,
            'original_error': error_msg,
            'fix': fix or 'pending',
            'lesson': lesson or 'pending',
            'first_seen': timestamp,
            'last_seen': timestamp,
            'occurrences': 1
        }
        self._save_patterns()

        # Append to human-readable log
        entry = (
            f"\n## [{timestamp}] {error_id}\n"
            f"**Command**: `{command}`\n"
            f"**Error**: {error_msg}\n"
        )
        if fix:
            entry += f"**Fix**: {fix}\n"
        if lesson:
            entry += f"**Lesson**: {lesson}\n"
        self._append_to_file(self.errors_file, entry, title="Error Log")

        # Append to lessons learned
        if fix or lesson:
            lesson_entry = (
                f"\n## [{timestamp}] {error_id}\n"
                f"**Error**: {error_msg}\n"
                f"**Fix**: {fix or 'pending'}\n"
                f"**Lesson**: {lesson or 'pending'}\n"
            )
            self._append_to_file(self.lessons_file, lesson_entry, title="Lessons Learned")

        return error_id

    def record_fix(self, error_id, fix, lesson):
        """Update an existing error with its fix and lesson."""
        if error_id in self.patterns:
            self.patterns[error_id]['fix'] = fix
            self.patterns[error_id]['lesson'] = lesson
            self.patterns[error_id]['last_seen'] = self._now()
            self._save_patterns()

            entry = (
                f"\n## FIX APPLIED [{self._now()}] {error_id}\n"
                f"**Fix**: {fix}\n"
                f"**Lesson**: {lesson}\n"
            )
            self._append_to_file(self.errors_file, entry, title="Error Log")
            self._append_to_file(self.lessons_file, entry, title="Lessons Learned")

    # ── RECALLING ERRORS ──────────────────────────────────────

    def check_before_action(self, command):
        """Check if a command matches a known error pattern.

        Returns:
            dict with 'match' (bool), 'error_id', 'fix', 'lesson', 'occurrences'
        """
        normalized = self._normalize_command(command)
        best_match = None
        best_score = 0

        for error_id, pattern in self.patterns.items():
            score = self._similarity(normalized, pattern['command_pattern'])
            if score > best_score and score >= 0.6:
                best_score = score
                best_match = pattern.copy()
                best_match['error_id'] = error_id

        if best_match:
            # Update last seen
            best_match['last_seen'] = self._now()
            self.patterns[best_match['error_id']]['occurrences'] += 1
            self.patterns[best_match['error_id']]['last_seen'] = self._now()
            self._save_patterns()
            return {
                'match': True,
                'error_id': best_match['error_id'],
                'fix': best_match.get('fix', ''),
                'lesson': best_match.get('lesson', ''),
                'occurrences': self.patterns[best_match['error_id']]['occurrences'],
                'original_error': best_match.get('original_error', '')
            }

        return {'match': False}

    def search_errors(self, query):
        """Search error memory for matching entries."""
        query_l = query.lower()
        results = []
        for error_id, pattern in self.patterns.items():
            searchable = f"{pattern.get('original_command', '')} {pattern.get('original_error', '')} {pattern.get('lesson', '')}".lower()
            if query_l in searchable:
                results.append({'id': error_id, **pattern})
        return results

    def get_all_lessons(self):
        """Return all lessons learned."""
        return {eid: p.get('lesson', '') for eid, p in self.patterns.items() if p.get('lesson')}

    def get_recent_errors(self, count=5):
        """Get the most recent errors."""
        sorted_patterns = sorted(
            self.patterns.items(),
            key=lambda x: x[1].get('last_seen', ''),
            reverse=True
        )
        return [{'id': eid, **p} for eid, p in sorted_patterns[:count]]

    # ── HELPERS ───────────────────────────────────────────────

    def _normalize_command(self, cmd):
        """Normalize a command for pattern matching."""
        cmd = cmd.lower().strip()
        # Remove specific filenames but keep structure
        cmd = re.sub(r'[/\\][\w.-]+\.md', '/FILE.md', cmd)
        cmd = re.sub(r'\b[\w-]+\.(md|txt|py|json)\b', 'FILE.md', cmd)
        # Normalize paths
        cmd = re.sub(r'workspace[/\\]', 'WORKSPACE/', cmd)
        cmd = re.sub(r'\.jarvis[/\\]', 'JARVIS/', cmd)
        return cmd

    def _normalize_error(self, error):
        """Normalize an error message for pattern matching."""
        error = error.lower().strip()
        # Normalize file paths in errors
        error = re.sub(r'[a-z]:[/\\][^\s"\']+', 'PATH', error)
        error = re.sub(r'no such file or directory', 'FILE_NOT_FOUND', error)
        error = re.sub(r'permission denied', 'PERMISSION_DENIED', error)
        error = re.sub(r'file not found', 'FILE_NOT_FOUND', error)
        return error

    def _generate_id(self, command, error):
        """Generate a stable ID from command + error."""
        combined = f"{self._normalize_command(command)}:{self._normalize_error(error)}"
        # Simple hash
        h = 0
        for c in combined:
            h = (h * 31 + ord(c)) & 0xFFFFFFFF
        return f"err_{h:08x}"

    def _similarity(self, a, b):
        """Simple token overlap similarity."""
        tokens_a = set(a.split())
        tokens_b = set(b.split())
        if not tokens_a or not tokens_b:
            return 0
        overlap = tokens_a & tokens_b
        return len(overlap) / max(len(tokens_a), len(tokens_b))

    def _append_to_file(self, filepath, content, title=""):
        """Append content to a markdown file, creating it if needed."""
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n\n*Persistent error memory for JARVIS.*\n\n---\n")
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content)
