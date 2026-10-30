"""Reject sensitive files and obvious credentials; never print matched values."""
from pathlib import PurePosixPath
import re
import subprocess
import sys

PATTERNS = [
    re.compile(rb'AIza[0-9A-Za-z_-]{30,}'),
    re.compile(rb'AQ\.[0-9A-Za-z_-]{25,}'),
    re.compile(rb'(?:gh[pousr]_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{30,})'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]


def check():
    staged = '--staged' in sys.argv
    command = ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'] if staged else ['git', 'ls-files', '-z']
    names = subprocess.check_output(command).decode('utf-8').split('\0')
    failures = []
    for name in filter(None, names):
        path = PurePosixPath(name)
        if path.name in {'config.json', 'keys.json', 'analysis_agents.json', 'secrets.toml'} or path.suffix in {'.sqlite', '.sqlite3', '.pem', '.pfx', '.key'} or path.parts[0] in {'data', 'private', 'secrets', '.venv'} or name.startswith('docs/screenshots/') or path.name.startswith('session') and path.suffix == '.json' or path.name.startswith('.env') and path.name != '.env.example':
            failures.append(f'{name}: private runtime file')
            continue
        data = subprocess.check_output(['git', 'show', ':' + name]) if staged else open(name, 'rb').read()
        if len(data) > 2_000_000:
            failures.append(f'{name}: unexpectedly large source file')
        if any(pattern.search(data) for pattern in PATTERNS):
            failures.append(f'{name}: credential pattern detected')
    if failures:
        print('\n'.join(failures))
        return 1
    print(f'Publish check passed: {sum(bool(n) for n in names)} source files; no private runtime files or recognized credential patterns.')
    return 0


if __name__ == '__main__':
    sys.exit(check())
