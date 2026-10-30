"""User-launched Windows companion; runs the complete app on loopback only."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent
PORT = 8765
URL = f'http://127.0.0.1:{PORT}/'


def install():
    if sys.version_info < (3, 11):
        raise RuntimeError('Install Python 3.11 or newer first: https://www.python.org/downloads/windows/')
    environment = ROOT / '.venv'
    if not (environment / 'Scripts/python.exe').exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = str(environment / 'Scripts/python.exe')
    subprocess.run([python, '-m', 'pip', 'install', '-e', str(ROOT)], check=True)
    subprocess.run([python, '-m', 'playwright', 'install', 'chromium'], check=True)
    print('Setup complete. Double-click Studyspace.cmd to start your local workspace.')


def healthy():
    try:
        with urllib.request.urlopen(URL + '_stcore/health', timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def owns_process(pid):
    if os.name != 'nt' or not isinstance(pid, int) or pid < 1:
        return False
    # Query this one PID only. Do not terminate or adopt unrelated processes.
    command = f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine'
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    value = result.stdout.casefold()
    return result.returncode == 0 and str(ROOT).casefold() in value and 'dashboard.py' in value and f'--server.port={PORT}' in value


def start():
    python = ROOT / '.venv/Scripts/python.exe'
    if not python.exists():
        raise RuntimeError('Run Setup.cmd first.')
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    marker = data / 'local-companion.json'
    with socket.socket() as probe:
        occupied = probe.connect_ex(('127.0.0.1', PORT)) == 0
    if occupied:
        try:
            info = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            info = {}
        if not owns_process(info.get('pid')) or not healthy():
            raise RuntimeError(f'Port {PORT} is occupied by another app or workspace. Close that app before starting Studyspace. No process was stopped.')
    else:
        command = [str(python), '-m', 'streamlit', 'run', str(ROOT / 'dashboard.py'),
                   '--server.address=127.0.0.1', f'--server.port={PORT}', '--server.headless=true']
        with (data / 'companion.log').open('a', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        marker.write_text(json.dumps({'pid': process.pid}), encoding='utf-8')
        deadline = time.monotonic() + 45
        while not healthy():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Local app did not start. Check data/companion.log; your notes were not removed.')
            time.sleep(.5)
    print(f'Studyspace runs on your computer: {URL}')
    print('Keep this computer running. Notes, downloads, keys and LMS login stay local; analysis still sends note content to Gemini.')
    webbrowser.open(URL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--install', action='store_true')
    group.add_argument('--start', action='store_true')
    args = parser.parse_args()
    try:
        install() if args.install else start()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
