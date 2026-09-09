# Error Log

*Persistent error memory for JARVIS.*

---

## [2026-09-09 02:45 UTC] err_51163419
**Command**: `create skill in .jarvis/skills/`
**Error**: File not found workspace/.jarvis/skills/hello_world.md
**Fix**: Use direct open() instead of FileManager for .jarvis/ paths
**Lesson**: Never use FileManager for files outside workspace/ — use os.open() directly

## [2026-09-09 02:45 UTC] err_a8407e0e
**Command**: `FileManager writes to workspace/`
**Error**: path is prepended with workspace/
**Fix**: FileManager always prepends workspace_path to relative paths
**Lesson**: For .jarvis/ files, bypass FileManager and write directly

## [2026-09-09 02:45 UTC] err_17b41566
**Command**: `edit skill file hello_worlds.md`
**Error**: File not found or skill already exists error on edit
**Fix**: Edit command for skill files was routing to skill_create instead of skill_edit
**Lesson**: Add skill_edit intent category that intercepts before generic edit

## [2026-09-09 02:45 UTC] err_4646add0
**Command**: `Unicode emoji in skill code execution`
**Error**: charmap codec cannot encode character
**Fix**: Windows subprocess defaults to system encoding, not UTF-8
**Lesson**: Always set PYTHONIOENCODING=utf-8 in subprocess env

## [2026-09-09 02:45 UTC] err_788a3ae7
**Command**: `Windows file lock on temp files`
**Error**: process cannot access the file because it is being used by another process
**Fix**: NamedTemporaryFile with delete=False keeps handle open
**Lesson**: Use mkstemp() + os.fdopen() instead of NamedTemporaryFile on Windows

## [2026-09-09 02:45 UTC] err_b8b01217
**Command**: `Skill name with spaces vs underscores`
**Error**: hello world does not match hello_world
**Fix**: User types space-separated names but skill files use underscores
**Lesson**: Normalize spaces to underscores in skill name matching

## [2026-09-09 02:46 UTC] err_efd63129
**Command**: `edit skill hello_worlds.md`
**Error**: File not found
**Fix**: Use skill_edit handler
**Lesson**: Edit commands for skills need dedicated handler
