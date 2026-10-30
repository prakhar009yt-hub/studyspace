import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from muj_study.core import App, ROOT
from muj_study.lms import LMS


class PerformanceTests(unittest.TestCase):
    def test_notes_downloads_are_deferred_paginated_and_tabs_are_lazy(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App(); app.save_config()
                path = base / 'note.txt'; path.write_text('Fixture')
                for i in range(30): LMS(app).catalog(f'url-{i}', 'DBMS', 'Unit', f'File {i:02}', str(path), 'hash', app.cfg['semester'])
                topics = [{'name': f'Topic {i:02}', 'concepts': ['Concept'], 'definitions': [], 'prerequisites': [], 'difficulty': 'foundational'} for i in range(25)]
                app.db.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)', ('fixture', 'DBMS', 'Unit', str(path), 'hash', json.dumps({'summary': 'Fixture', 'topics': topics})))
                app.db.commit(); app.close()
                ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60)
                ui.query_params['page'] = 'Notes'; ui.run()
                self.assertEqual(len(ui.exception), 0)
                downloads = ui.get('download_button')
                self.assertEqual(len(downloads), 12)
                self.assertTrue(all(d.proto.deferred_file_id for d in downloads))
                self.assertEqual(len([c for c in ui.checkbox if c.label == 'This topic is confusing']), 8)
                ui.selectbox(key='library-file-page').set_value(3).run()
                self.assertEqual(len(ui.get('download_button')), 6)
                ui.text_input(key='library-file-search').set_value('File 29').run()
                self.assertEqual(len(ui.get('download_button')), 1)
                ui.session_state['note-study-tabs-fixture'] = 'History'
                ui.run()
                self.assertEqual(len(ui.exception), 0)
                self.assertFalse(any(b.label == 'Find study videos' for b in ui.button))
                self.assertFalse(any(c.label == 'This topic is confusing' for c in ui.checkbox))

    def test_opening_initialized_database_does_not_repeat_schema_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            app = App(base / 'config.json', base / 'data'); app.close()
            original = sqlite3.connect
            statements = []
            def connect(*args, **kwargs):
                connection = original(*args, **kwargs)
                connection.set_trace_callback(statements.append)
                return connection
            with patch('muj_study.core.sqlite3.connect', side_effect=connect):
                app = App(base / 'config.json', base / 'data'); app.close()
            self.assertFalse(any(s.lstrip().upper().startswith(('CREATE', 'INSERT', 'ALTER')) for s in statements))
