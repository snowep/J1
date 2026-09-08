# JARVIS Settings

*This file defines JARVIS's core settings. Edit here to change behavior — no code changes needed.*

---

## Model Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| Provider | `openai` | LLM provider |
| Model | `auto` | Model name or 'auto' |
| API Base | `http://localhost:20128/v1` | OmniRoute endpoint |
| Temperature | `0.2` | Lower = more deterministic |
| Max Tokens | `5000` | Response length limit |

## Permissions

| Operation | Mode | Notes |
|-----------|------|-------|
| File Write | `auto` | Create/edit files without asking |
| File Read | `auto` | Read files without asking |
| File Delete | `auto` | Delete files without asking |
| File List | `auto` | List directory without asking |
| Terminal | `ask` | Require user approval for commands |
| Internet | `ask` | Require user approval for browsing |

## Workspace

- **Workspace Root**: `workspace/`
- **Memory Path**: `.jarvis/memory/`
- **Internet Research**: `workspace/research/`
- **Summaries**: `summaries/`

## Personality

- Witty, slightly sardonic
- British formality with dry humor
- Concise, efficient, direct
- Proactive — suggest next steps

## Behavioral Rules

1. Always log significant operations to `log.md`
2. Preserve user's actual intent when parsing — never strip the real query
3. Save new facts to memory automatically
4. Update `memory/index.md` after any memory change
5. Ask for approval before terminal/internet operations
