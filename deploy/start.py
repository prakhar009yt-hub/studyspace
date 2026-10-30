"""Container entrypoint; keep mutable preferences and theme on a persistent volume."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def prepare(config_path):
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        defaults = json.loads((ROOT / 'config.example.json').read_text(encoding='utf-8'))
        # A clean server starts without unattended network work or a saved login.
        defaults.update(lms_auto_sync=False, lms_auto_analyze=False)
        config_path.write_text(json.dumps(defaults, indent=2), encoding='utf-8')
        config_path.chmod(0o600)
    config = json.loads(config_path.read_text(encoding='utf-8'))
    theme_folder = config_path.parent / '.streamlit'
    theme_folder.mkdir(exist_ok=True)
    theme_file = theme_folder / 'config.toml'
    if not theme_file.exists():
        # Import only after creating the config; ROOT assets remain in the image.
        from muj_study.appearance import PALETTES
        palette = PALETTES.get(config.get('appearance'), PALETTES['dark'])
        theme_file.write_text('[theme]\n' + ''.join(f'{k} = "{v}"\n' for k, v in palette.items()), encoding='utf-8')
    return config_path.parent


def main():
    port = int(os.environ.get('PORT', '8501'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535.')
    folder = prepare(os.environ.get('MUJ_CONFIG', '/state/config/config.json'))
    os.chdir(folder)
    os.execv(sys.executable, [sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'dashboard.py'),
                            '--server.address=0.0.0.0', f'--server.port={port}',
                            '--server.headless=true', '--server.enableXsrfProtection=true',
                            '--server.enableCORS=true', '--server.maxUploadSize=100',
                            '--browser.gatherUsageStats=false'])


if __name__ == '__main__':
    main()
