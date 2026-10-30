import tempfile
import unittest
from pathlib import Path

from muj_study.core import App
from muj_study.lms import LMS
from muj_study.progress_ui import job_errors


class ProgressUITests(unittest.TestCase):
    def test_pacific_reset_is_shown_in_india_even_after_indian_midnight(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from muj_study.core import quota_reset_ist
        now = datetime(2026, 10, 30, 0, 45, tzinfo=ZoneInfo('Asia/Kolkata'))
        reset = quota_reset_ist(now)
        self.assertEqual((reset.day, reset.hour, reset.minute), (30, 12, 30))
    def test_old_job_reports_keep_api_errors_visible_and_deduplicate(self):
        state = {'result': {'analysis': [{'error': 'API service unavailable (HTTP 503).'}]},
                 'analysis_progress': {'errors': ['API service unavailable (HTTP 503).']}}
        self.assertEqual(job_errors(state), ['API service unavailable (HTTP 503).'])

    def test_progress_panel_shows_counts_bars_and_budget_failure(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = App(root / 'config.json', root / 'data')
            app.cfg['semester'] = 3
            app.save_config()
            LMS(app).catalog('url', 'DBMS', 'Unit', 'Note', str(root / 'note.txt'), 'hash', 3)
            app.close()
            state = {'status': 'complete', 'semester': 3,
                     'download_progress': {'total': 2, 'processed': 2, 'downloaded': 1, 'unchanged': 1},
                     'analysis_progress': {'total': 1, 'processed': 1, 'succeeded': 0, 'failed': 1,
                                           'errors': ['Local gemini_calls daily budget reached; retry after Pacific midnight.']}}
            source = f'from muj_study.core import App\nfrom muj_study.progress_ui import render_status\napp = App({str(root / "config.json")!r}, {str(root / "data")!r})\nrender_status(app, {state!r})\napp.close()'
            ui = AppTest.from_string(source).run()
            self.assertEqual(len(ui.exception), 0)
            self.assertEqual([m.value for m in ui.metric][:3], ['1', '0', '1'])
            self.assertIn('Download time remaining', [m.label for m in ui.metric])
            self.assertIn('Analysis time remaining', [m.label for m in ui.metric])
            self.assertEqual(len(ui.get('progress')), 3)
            self.assertIn('daily budget', ui.error[0].value)
            self.assertTrue(any('local daily limit' in w.value for w in ui.warning))
