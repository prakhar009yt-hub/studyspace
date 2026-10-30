"""Build the deterministic, credential-free browser test extension and shared viewer assets."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
FILES = ['manifest.json', 'background.mjs', 'app.html', 'app.mjs', 'core.mjs', 'lms.mjs', 'google.mjs', 'media.mjs', 'workspace.css', 'privacy.html', 'READ-ME-FIRST.txt']


def package():
    output = ROOT / 'web/downloads/Studyspace-Extension-Test.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name in FILES:
            info = zipfile.ZipInfo('Studyspace-Extension/' + name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, (ROOT / 'extension' / name).read_bytes().replace(b'\r\n', b'\n'))
    for source, target in [('core.mjs', 'study-core.mjs'), ('workspace.css', 'workspace.css'), ('privacy.html', 'privacy.html')]:
        data = (ROOT / 'extension' / source).read_bytes().replace(b'\r\n', b'\n')
        if source == 'privacy.html':
            data = data.replace(b'href="app.html"', b'href="/"')
        (ROOT / 'web' / target).write_bytes(data)
    print(f'Packaged {len(FILES)} extension files; no user keys, sessions or notes included.')


if __name__ == '__main__':
    package()
