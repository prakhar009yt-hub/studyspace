"""Read-only Notes-page benchmark using an isolated copy of the local catalog."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from muj_study.core import App, private_write
from streamlit.testing.v1 import AppTest


with tempfile.TemporaryDirectory(prefix='muj-benchmark-') as folder:
    base = Path(folder)
    data = base / 'data'; data.mkdir()
    source = App()
    import sqlite3
    clone = sqlite3.connect(data / 'study.sqlite3')
    source.db.backup(clone); clone.close()
    config = {**source.cfg, 'lms_auto_sync': False, 'lms_auto_analyze': False}
    source.close()
    private_write(base / 'config.json', config)
    os.environ.update(MUJ_DATA_DIR=str(data), MUJ_CONFIG=str(base / 'config.json'), MUJ_PRIVATE_DIR=str(base / 'private'))
    tracemalloc.start()
    started = time.perf_counter()
    ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=120)
    ui.query_params['page'] = 'Notes'
    ui.run()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    result = {'seconds': round(elapsed, 2), 'peak_python_MB': round(peak / 1024**2, 1),
              'download_buttons': len(ui.get('download_button')), 'buttons': len(ui.button),
              'exceptions': len(ui.exception)}
    print(json.dumps(result))
