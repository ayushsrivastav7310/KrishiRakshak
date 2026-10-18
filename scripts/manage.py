"""Start, build or test the local app without activating a PowerShell script."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
VENV_PYTHON = BACKEND / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def ensure_env():
    target = BACKEND / '.env'
    if not target.exists():
        target.write_text((BACKEND / '.env.example').read_text().replace(
            'replace-with-a-random-secret-at-least-32-characters', secrets.token_hex(48)), encoding='utf-8')


def node_command():
    executable = shutil.which('node')
    bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    if not executable and bundled.is_file():
        executable = str(bundled)
    if not executable:
        raise RuntimeError('Node.js is needed for the React frontend. Install Node.js LTS and reopen the terminal.')
    return executable


def python_command():
    if not VENV_PYTHON.is_file():
        raise RuntimeError('Python dependencies are missing. Run .\\run-local.cmd setup first.')
    return str(VENV_PYTHON)


def run_setup():
    if not VENV_PYTHON.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(BACKEND / '.venv')], check=True)
    subprocess.run([str(VENV_PYTHON), '-m', 'pip', 'install', '-r', str(BACKEND / 'requirements.txt')], check=True)
    ensure_env()
    print('Python backend is ready. Run .\\run-local.cmd to start both apps.')


def backend_command():
    return [python_command(), '-m', 'uvicorn', 'main:app', '--app-dir', str(BACKEND),
            '--host', '127.0.0.1', '--port', '8000', '--reload', '--reload-dir', str(BACKEND)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', default='dev', choices=['dev', 'frontend', 'backend', 'build', 'test', 'test-frontend', 'setup'])
    mode = parser.parse_args().mode
    os.chdir(ROOT)
    if mode == 'setup':
        run_setup()
        return 0
    if mode in ('dev', 'backend'):
        ensure_env()
    if mode == 'build':
        return subprocess.call([node_command(), str(ROOT / 'scripts/vite.mjs'), 'build'])
    if mode == 'test':
        return subprocess.call([python_command(), '-m', 'pytest', '-c', 'backend/pytest.ini', 'backend/tests'])
    if mode == 'test-frontend':
        return subprocess.call([node_command(), str(ROOT / 'frontend/node_modules/vitest/vitest.mjs'), 'run'], cwd=ROOT / 'frontend')
    if mode == 'frontend':
        return subprocess.call([node_command(), str(ROOT / 'scripts/vite.mjs'), '--host', '127.0.0.1'])
    if mode == 'backend':
        return subprocess.call(backend_command())

    # Start two processes and stop the other if either fails or the user presses Ctrl+C.
    children = []
    windows = os.name == 'nt'
    try:
        for command in [backend_command(), [node_command(), str(ROOT / 'scripts/vite.mjs'), '--host', '127.0.0.1']]:
            children.append(subprocess.Popen(command, cwd=ROOT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0,
                start_new_session=not windows))
        while True:
            for child in children:
                if child.poll() is not None:
                    return child.returncode
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                if windows:
                    subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True)
                else:
                    os.killpg(child.pid, signal.SIGTERM)
                child.wait()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

