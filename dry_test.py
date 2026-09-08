"""JARVIS Comprehensive Dry-Test — Phases 1-8."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 66)
print("JARVIS FULL DRY-TEST (Phases 1-8)")
print("=" * 66)

results = []
def check(name, passed, detail=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append((name, passed))
    print(f"  {status} | {name} {detail}")

# ───────────────────────────────────────────
# PHASE 1: File CRUD
# ───────────────────────────────────────────
print("\n[PHASE 1] File Operations")
from src.file_manager import FileManager
fm = FileManager()

r = fm.write('test.md', '# Test\n\nPhase 1 content.', overwrite=True)
check("write_file", r['success'], r.get('message', ''))

r = fm.read('test.md')
check("read_file", r['success'] and '# Test' in r.get('content', ''))

r = fm.edit('test.md', 'Phase 1', 'Updated')
check("edit_file", r['success'])

r = fm.list()
check("list_files", r['success'], f"({len(r.get('items', []))} items)")

r = fm.delete('test.md')
check("delete_file", r['success'])

# ───────────────────────────────────────────
# PHASE 2: Memory (basic) 
# ───────────────────────────────────────────
print("\n[PHASE 2] Memory System")
from src.memory import Memory
mem = Memory(memory_path='.jarvis/memory')
r = mem.save_user_preference('test_pref', 'phase2')
check("save_preference", os.path.exists(r) if r else False)
prefs = mem.get_user_preferences()
check("get_preferences", 'test_pref' in str(prefs.get('user', {})))

# ───────────────────────────────────────────
# PHASE 3: Terminal Execution
# ───────────────────────────────────────────
print("\n[PHASE 3] Terminal Execution")
from src.terminal_executor import TerminalExecutor
te = TerminalExecutor(require_approval=False)
r = te.execute('echo JARVIS-OK')
check("execute_echo", r['success'] and 'JARVIS-OK' in r.get('stdout', ''))
r = te.execute('echo HELLO')
check("command_log", len(te.get_log().get('commands', [])) >= 1)

# ───────────────────────────────────────────
# PHASE 4: Persistent Memory (.md files)
# ───────────────────────────────────────────
print("\n[PHASE 4] Persistent Memory as Markdown")
mem2 = Memory(memory_path='.jarvis/memory')
r = mem2.save_conversation("dry test", "response logged")
check("save_conversation", os.path.exists(r) if r else False)
idx = os.path.join('.jarvis', 'memory', 'index.md')
check("memory_index_exists", os.path.exists(idx))
ctx = mem2.get_context_for_llm()
check("context_for_llm", len(ctx) > 0)

# ───────────────────────────────────────────
# PHASE 5: Internet Access
# ───────────────────────────────────────────
print("\n[PHASE 5] Internet Access")
from src.internet import Internet
inet = Internet()
check("internet_enabled", inet.is_enabled())
check("toggle_disable", 'disabled' in inet.disable())
inet.enable()

# ───────────────────────────────────────────
# PHASE 6: Summarization
# ───────────────────────────────────────────
print("\n[PHASE 6] Summarization")
from src.summarizer import Summarizer
summ = Summarizer(summaries_path='workspace/summaries')
fm.write('note_for_summary.md', '# Notes\n\n## Overview\nImportant content about phases.\n\n## Key\n- Point one\n- Point two\n\n#test', overwrite=True)
r = summ.summarize_file('note_for_summary.md', style='concise')
check("summarize_file", r.get('success', False), f"→ {r.get('summary_file', '?')}")
r = summ.list_summaries()
check("list_summaries", r.get('success', False), f"({r.get('count', 0)} files)")
fm.delete('note_for_summary.md')

# ───────────────────────────────────────────
# PHASE 7: Autonomous Planner
# ───────────────────────────────────────────
print("\n[PHASE 7] Autonomous + Error Recovery")
from src.memory import AutonomousPlanner
from src.agent import Agent
agent = Agent()
planner = AutonomousPlanner(agent)
fm.write('real_file.md', 'Real content', overwrite=True)
r = planner._execute_action('read real_file.md')
check("execute_read_action", r.get('success', False))
r = planner._execute_with_recovery('read nonexistent_file.md', 'test')
check("error_detected", not r.get('success'), f"(error: {r.get('error', '?')})")
fm.delete('real_file.md')

# ───────────────────────────────────────────
# PHASE 8: Brain Directory (.jarvis/)
# ───────────────────────────────────────────
print("\n[PHASE 8] Jarvis Brain Directory")
check("agent_initializes", agent is not None)
check("brain_settings", len(agent.jarvis_brain.get('settings', {}).get('raw', '')) > 0)
check("brain_skills", len(agent.jarvis_brain.get('skills', {}).get('raw', '')) > 0)
check("brain_memory_idx", len(agent.jarvis_brain.get('memory_index', '')) > 0)
check("brain_rules", len(agent.jarvis_brain.get('rules', '')) > 0)
check("brain_agents", len(agent.jarvis_brain.get('agents', '')) > 0)
check("brain_commands", len(agent.jarvis_brain.get('commands', '')) > 0)
check("brain_hooks", len(agent.jarvis_brain.get('hooks', '')) > 0)
check("brain_styles", len(agent.jarvis_brain.get('output_styles', '')) > 0)
check("capabilities_loaded", len(agent.capabilities) > 0, f"({len(agent.capabilities)} skills)")
cap_out = agent.process("what can you do")
check("capabilities_cmd", 'Capabilities' in cap_out or 'capabilities' in cap_out.lower())

# ───────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────
passed = sum(1 for _, p in results if p)
total = len(results)
print("\n" + "=" * 66)
print(f"SUMMARY: {passed}/{total} passed")
if passed == total:
    print("🎉 ALL TESTS PASSED")
else:
    fails = [n for n, p in results if not p]
    print(f"❌ Failed: {fails}")
print("=" * 66)

# Report file
report = {
    'date': '2026-09-09',
    'total': total,
    'passed': passed,
    'failed': total - passed,
    'failed_items': [n for n, p in results if not p] if passed != total else [],
    'all_passed': passed == total
}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dry_test_report.json'), 'w') as f:
    json.dump(report, f, indent=2)
print("\n📄 dry_test_report.json written")

sys.exit(0 if passed == total else 1)