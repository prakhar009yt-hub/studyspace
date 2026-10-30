"""Create a deterministic, source-only Windows companion ZIP. Never bundle user data."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'web/downloads/Studyspace-Windows.zip'


def source_files():
    files = [(ROOT / name, name) for name in ['dashboard.py', 'pyproject.toml', 'requirements.txt', 'config.example.json', 'README.md']]
    for folder, pattern in [('muj_study', '*.py'), ('assets', '*.css')]:
        files.extend((path, path.relative_to(ROOT).as_posix()) for path in sorted((ROOT / folder).glob(pattern)))
    files.extend((ROOT / 'docs' / name, 'docs/' + name) for name in ['API_KEYS.md', 'LMS.md', 'ANALYSIS_AGENTS.md', 'FEATURE_STATUS.md'])
    files.extend((ROOT / 'companion' / name, name) for name in ['Setup.cmd', 'Studyspace.cmd', 'local_companion.py', 'READ-ME-FIRST.txt'])
    return sorted(files, key=lambda entry: entry[1])


def package(output=OUTPUT):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for path, name in source_files():
            info = zipfile.ZipInfo('Studyspace/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            content = path.read_bytes().replace(b'\r\n', b'\n')
            if name.endswith('.cmd'):
                content = content.replace(b'\n', b'\r\n')
            archive.writestr(info, content)
    print(f'Companion packaged: {len(source_files())} source files, {output.stat().st_size} bytes. No local data, keys, sessions or virtual environment included.')


if __name__ == '__main__':
    package()
