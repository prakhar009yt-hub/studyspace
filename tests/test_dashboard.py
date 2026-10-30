import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from muj_study.core import App, ROOT


class DashboardTests(unittest.TestCase):
    def test_completed_analysis_without_blocker_keeps_progress_refresh_working(self):
        from streamlit.testing.v1 import AppTest
        from muj_study.core import private_write
        import time
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App(); app.save_config()
                private_write(app.data / 'jobs' / 'job-complete.json', {
                    'file': 'job-complete.json', 'task': 'analyze', 'semester': 3, 'status': 'complete', 'started': time.time(),
                    'analysis_progress': {'total': 0, 'processed': 0, 'succeeded': 0, 'failed': 0, 'blocked_error': None}})
                app.close()
                ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60).run()
                self.assertEqual(len(ui.exception), 0)
                self.assertEqual(len(ui.error), 0)

    def test_light_mode_switch_persists_and_returns_to_dark(self):
        from streamlit.testing.v1 import AppTest
        import tomllib
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App(); app.save_config(); app.close()
                ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60).run()
                self.assertEqual(ui.button(key='appearance-toggle').label, '☀')
                ui.button(key='appearance-toggle').click().run()
                self.assertEqual(len(ui.exception), 0)
                self.assertEqual(json.loads((base / 'config.json').read_text())['appearance'], 'light')
                self.assertEqual(tomllib.loads((base / '.streamlit/config.toml').read_text())['theme']['base'], 'light')
                self.assertTrue(any('Light mode keeps cerulean' in m.value for m in ui.markdown))
                ui.sidebar.radio[0].set_value('Settings').run()
                self.assertEqual(ui.button(key='appearance-toggle').label, '☾')
                ui.button(key='appearance-toggle').click().run()
                self.assertEqual(json.loads((base / 'config.json').read_text())['appearance'], 'dark')
                self.assertEqual(len(ui.exception), 0)

    def test_navigation_with_saved_files_shows_distinct_pages_and_collapses_progress(self):
        from streamlit.testing.v1 import AppTest
        from muj_study.lms import LMS
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App(); app.save_config()
                LMS(app).catalog('url', 'DBMS', 'Unit 1', 'Note', str(base / 'note.txt'), 'hash', app.cfg['semester'])
                app.close()
                ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60).run()
                for page, title in [('Home', 'Less overwhelm.'), ('Settings', 'A workspace that gets you.'), ('Notes', 'Everything you’re learning.'), ('Progress', 'A little progress, every day.')]:
                    ui.sidebar.radio[0].set_value(page).run()
                    selected = ui.query_params['page']
                    self.assertEqual(selected[0] if isinstance(selected, list) else selected, page)
                    self.assertEqual(len(ui.exception), 0)
                    self.assertTrue(any(title in value for value in [t.value for t in ui.title] + [h.value for h in ui.markdown]), page)
                    panels = [e for e in ui.expander if e.label.startswith('Study progress')]
                    if page == 'Progress': self.assertEqual(panels, [])
                    else:
                        self.assertEqual(len(panels), 1)
                        self.assertFalse(panels[0].proto.expanded)

    def test_home_tiles_navigate_and_filter(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App(); app.save_config(); app.close()
                ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60).run()
                for tile, destination in [('notes', 'Notes'), ('topics', 'Topics'), ('covered', 'Topics'), ('watched', 'Videos')]:
                    ui.sidebar.radio[0].set_value('Home').run()
                    ui.button(key='home-open-' + tile).click().run()
                    self.assertEqual(ui.sidebar.radio[0].value, destination)
                    self.assertEqual(len(ui.error), 0)
                    if tile == 'covered': self.assertEqual(ui.selectbox(key='topic-view').value, 'Covered topics')

    def test_semester_menu_saves_profile_and_opens_preferences(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App(); app.save_config(); app.close()
                ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60).run()
                ui.selectbox(key='profile-semester-choice').set_value(5)
                next(b for b in ui.button if b.label == 'Save semester').click().run()
                self.assertEqual(len(ui.exception), 0)
                self.assertEqual(json.loads((base / 'config.json').read_text())['semester'], 5)
                self.assertEqual(ui.selectbox(key='profile-semester-choice').value, 5)
                ui.button(key='profile-preferences').click().run()
                self.assertEqual(ui.sidebar.radio[0].value, 'Settings')
                self.assertEqual(next(n for n in ui.number_input if n.label == 'Semester').value, 5)

    def test_dashboard_pages_without_live_apis(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App()
                app.save_config()
                app.close()
                ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60).run()
                self.assertEqual(len(ui.exception), 0)
                for page in ['Home', 'LMS', 'Import', 'Progress', 'Settings', 'Notes', 'Topics', 'Videos']:
                    ui.sidebar.radio[0].set_value(page).run()
                    self.assertEqual(len(ui.exception), 0, page)
                    self.assertEqual(len(ui.error), 0, page)

    def test_note_page_with_topics_and_video_card(self):
        from streamlit.testing.v1 import AppTest
        from muj_study.core import digest
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App()
                app.save_config()
                note = base / 'note.txt'; note.write_text('SQL joins')
                analysis = {'summary': 'Test fixture summary', 'topics': [{'name': 'SQL joins', 'difficulty': 'foundational', 'concepts': ['Inner joins'], 'definitions': ['Matches rows by key.'], 'prerequisites': ['Tables'], 'queries': ['SQL joins example', 'SQL join intro', 'SQL join exam'], 'source_pages': []}], 'readability_warning': ''}
                app.db.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)', ('test', 'DBMS', 'Unit 1', str(note), hashlib.sha256(note.read_bytes()).hexdigest(), json.dumps(analysis)))
                result = [{'topic': 'SQL joins', 'no_strong_match': False, 'estimated_minutes': 10, 'cache_hits': 1, 'videos': [{'id': 'fixture', 'title': 'Fixture lecture', 'channelId': 'teacher', 'channelTitle': 'Teacher', 'duration_seconds': 600, 'views': 1000, 'role': 'quick intro', 'reason': 'Fixture metadata match', 'score': 8, 'language': 'en', 'confidence': 'medium', 'url': 'https://www.youtube.com/watch?v=fixture'}]}]
                app.db.execute('INSERT INTO history(created,note,result) VALUES(?,?,?)', (1, 'test', json.dumps(result)))
                app.db.commit(); app.close()
                ui = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60).run()
                ui.sidebar.radio[0].set_value('Notes').run()
                self.assertEqual(len(ui.exception), 0)
                self.assertEqual(len(ui.error), 0)
                self.assertTrue(any('Test fixture summary' in element.value for element in ui.markdown))
                self.assertTrue(any('Fixture lecture' in element.value for element in ui.markdown))
                ui.sidebar.radio[0].set_value('Videos').run()
                self.assertEqual(ui.radio(key='video-view').value, 'Recommended')
                self.assertTrue(any(b.label == 'Fixture lecture' for b in ui.get('link_button')))
                self.assertEqual(len(ui.error), 0)
