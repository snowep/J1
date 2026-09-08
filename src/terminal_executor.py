import os
import subprocess
import json
from datetime import datetime


class TerminalExecutor:
    """JARVIS Terminal Executor — Run commands with workspace-bound cwd and audit logging."""

    # Commands that always require confirmation (even if require_approval=False)
    DESTRUCTIVE_COMMANDS = {
        'rmdir', 'rm', 'del', 'erase', 'rd', 'deltree',
        'git push', 'git push origin', 'git push --all',
        'git commit --amend', 'git reset --hard', 'git reset --mixed',
        'git checkout -b', 'git branch -D', 'git branch -d',
        'chmod +x', 'chmod 777', 'chmod -R',
        'format', 'diskpart', 'diskpart /s',
    }

    def __init__(self, workspace_path='workspace', require_approval=True, log_path='workspace/terminal_log.json'):
        self.workspace_dir = os.path.normpath(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), workspace_path)
        )
        self.require_approval = require_approval
        self.log_path = log_path
        self.command_log = self._load_log()
        os.makedirs(self.workspace_dir, exist_ok=True)

    def _load_log(self):
        """Load command log from JSON file."""
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r') as f:
                    return json.load(f)
            except:
                return {'commands': []}
        return {'commands': []}

    def _save_log(self):
        """Save command log to JSON file."""
        try:
            with open(self.log_path, 'w') as f:
                json.dump(self.command_log, f, indent=2)
        except Exception as e:
            print(f"⚠️ Warning: Could not save command log: {e}")

    def _log_command(self, command, cwd, status, output, duration_ms):
        """Record command execution for audit."""
        self.command_log['commands'].append({
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'command': command,
            'cwd': cwd,
            'status': status,
            'output_length': len(output),
            'duration_ms': duration_ms
        })
        self._save_log()

    def _get_command_preview(self, command, cwd):
        """Get a preview of the command for approval."""
        if len(command) > 60:
            preview = command[:60] + '...'
        else:
            preview = command
        return f"📟 Command: `{preview}`\n📁 CWD: {cwd}"

    def _is_destructive(self, command):
        """Check if command is destructive and requires extra confirmation."""
        cmd_lower = command.lower().strip()
        # Check exact matches and patterns
        for destructive in self.DESTRUCTIVE_COMMANDS:
            if cmd_lower.startswith(destructive.lower()):
                return True
        return False

    def approve(self, command, cwd=None):
        """Request user approval for a command."""
        cmd_lower = command.lower().strip()
        is_destructive = self._is_destructive(command)
        
        if not self.require_approval and not is_destructive:
            return True
        
        print(f"\n{'='*50}")
        if is_destructive:
            print(f"⚠️  DESTRUCTIVE COMMAND DETECTED!")
        print(f"📟 Command: `{command[:60]}{'...' if len(command) > 60 else ''}`")
        print(f"📁 CWD: {cwd or self.workspace_dir}")
        print('='*50)
        
        if is_destructive:
            response = input("⚠️ This command may cause data loss. Continue? (type 'YES' to confirm): ").strip()
            return response == 'YES'
        else:
            response = input("Approve execution? (y/n): ").strip().lower()
            return response in ['y', 'yes']

    def execute(self, command, cwd=None, timeout=120):
        """
        Execute a terminal command with workspace-bound cwd.

        Args:
            command: Command string to execute
            cwd: Working directory (defaults to workspace)
            timeout: Command timeout in seconds

        Returns:
            Dict with success status, stdout, stderr, and metadata
        """
        work_dir = cwd if cwd else self.workspace_dir
        work_dir = os.path.normpath(os.path.abspath(work_dir))

        # Security: Ensure cwd is within workspace
        if not work_dir.startswith(self.workspace_dir + os.sep) and work_dir != self.workspace_dir:
            return {
                'success': False,
                'error': 'CWD must be within workspace directory',
                'command': command,
                'cwd': work_dir
            }

        # Request approval
        if not self.approve(command, work_dir):
            return {
                'success': False,
                'error': 'Execution denied by user',
                'command': command,
                'cwd': work_dir
            }

        import time
        start_time = time.time()
        status = 'success'

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode

            if exit_code != 0:
                status = 'failed'
                stderr = stderr or f'Exit code: {exit_code}'

        except subprocess.TimeoutExpired:
            stdout = ''
            stderr = 'Command timed out'
            status = 'timeout'
            exit_code = -1

        except Exception as e:
            stdout = ''
            stderr = str(e)
            status = 'error'
            exit_code = -1

        duration_ms = int((time.time() - start_time) * 1000)
        output = stdout + ('\n' + stderr if stderr else '')

        # Log the command
        self._log_command(command, work_dir, status, output, duration_ms)

        return {
            'success': status == 'success',
            'command': command,
            'cwd': work_dir,
            'stdout': stdout,
            'stderr': stderr,
            'exit_code': exit_code,
            'status': status,
            'duration_ms': duration_ms
        }

    def execute_python(self, script_content, script_name=None, timeout=60):
        """Execute inline Python script."""
        if script_name is None:
            script_name = f'_temp_script_{int(datetime.utcnow().timestamp())}.py'

        # Write script to workspace
        script_path = os.path.join(self.workspace_dir, script_name)
        try:
            with open(script_path, 'w') as f:
                f.write(script_content)
            command = f'python "{script_path}"'
            result = self.execute(command, timeout=timeout)
            # Clean up temp script
            try:
                os.remove(script_path)
            except:
                pass
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_log(self):
        """Get the command audit log."""
        return self.command_log

    def clear_log(self):
        """Clear the command log."""
        self.command_log = {'commands': []}
        self._save_log()


if __name__ == "__main__":
    print("Testing TerminalExecutor...")
    te = TerminalExecutor(require_approval=False)

    # Test listing files
    print("\n1. Testing 'dir' command:")
    result = te.execute('dir')
    print(f"Status: {result['status']}")
    print(f"Output preview: {result['stdout'][:200] if result['stdout'] else 'No output'}...")

    # Test python execution
    print("\n2. Testing Python script:")
    result = te.execute_python('print("Hello from JARVIS terminal!")\nprint("Current time:", __import__("datetime").datetime.now())')
    print(f"Status: {result['status']}")
    print(f"Output: {result['stdout']}")

    # Show log
    print(f"\n3. Command log entries: {len(te.get_log()['commands'])}")