# Hooks

*Shell scripts or actions triggered on JARVIS lifecycle events.*

---

## on_startup
**When**: JARVIS initializes
**What**: 
- Scan `.jarvis/` directory
- Load settings, skills, rules, memory index into context
- Log startup to log.md

## on_exit
**When**: JARVIS shuts down
**What**:
- Log session end to log.md
- Flush any pending memory writes

## on_learn
**When**: JARVIS saves a new fact or preference
**What**:
- Update `memory/facts_user.md`
- Update `memory/index.md`

## on_file_change
**When**: JARVIS creates, edits, or deletes a workspace file
**What**:
- Log operation to log.md
- (Future) Update knowledge index if markdown file

## before_terminal
**When**: Before executing a terminal command
**What**:
- Request user approval (per settings)
- Log command to terminal_log.json

---

*Hooks are placeholder definitions. Implementation planned for future phases.*