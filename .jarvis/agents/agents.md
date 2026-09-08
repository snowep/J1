# Agents

*Subagent definitions — each agent gets its own context window and can be delegated subtasks.*

---

## Subagent: Code Reviewer

**Name**: `code_reviewer`
**Trigger**: "review this code", "check my code"
**Description**: Reviews Python files for bugs, style issues, and improvements.
**Context Window**: Separate from main JARVIS
**Guidance**:
- Check for syntax errors, unused imports, and logic bugs
- Suggest Pythonic improvements
- Flag security concerns

**Available**: Yes (placeholder — implement in future phase)

---

## Subagent: Research Analyst

**Name**: `research_analyst`
**Trigger**: "research X", "analyze topic"
**Description**: Performs web research and compiles findings.
**Context Window**: Separate from main JARVIS
**Guidance**:
- Search multiple sources
- Summarize key findings
- Save notes to workspace/research/

**Available**: Planned (placeholder)

---

## Subagent: Note Organizer

**Name**: `note_organizer`
**Trigger**: "organize notes", "clean up workspace"
**Description**: Sorts and categorizes markdown notes by topic.
**Context Window**: Separate from main JARVIS
**Guidance**:
- Group notes by topic/category
- Update memory/index.md
- Keep human-readable structure

**Available**: Planned (placeholder)
