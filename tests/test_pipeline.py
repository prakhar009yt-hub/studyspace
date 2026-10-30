import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from muj_study.core import App
from muj_study.lms import LMS
from muj_study.worker import execute


class PipelineTests(unittest.TestCase):
    def test_unchanged_analyzed_download_is_not_requeued(self):
        import json
        from muj_study.pipeline import AnalysisPipeline
        item = {'path': str(self.base / 'note.txt'), 'hash': 'hash', 'course': 'DBMS', 'unit': 'Unit 1'}
        self.app.db.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)', ('ready', item['course'], item['unit'], item['path'], item['hash'], json.dumps({'topics': [{'name': 'Arrays'}]})))
        self.app.db.execute('INSERT INTO note_semesters VALUES(?,?)', ('ready', 3))
        self.app.db.commit()
        with patch('muj_study.gemini.Gemini.analyze') as analyze:
            pipeline = AnalysisPipeline(self.app, lambda _: None)
            pipeline.submit(item)
            self.assertEqual(pipeline.finish(), [])
            analyze.assert_not_called()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.app = App(self.base / 'config.json', self.base / 'data')
        self.app.cfg.update(semester=3, request_delay=0, lms_auto_analyze=True)
        self.app.save_config()

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def test_analysis_starts_before_downloads_finish(self):
        path = self.base / 'note.txt'; path.write_text('A note')
        hashed = hashlib.sha256(path.read_bytes()).hexdigest()
        started, release = threading.Event(), threading.Event()
        def analyze(*args, **kwargs):
            started.set()
            if not release.wait(5): raise RuntimeError('download producer never released analysis')
            return {'id': 'test', 'summary': 'Read', 'topics': []}
        def discover():
            LMS(self.app).remember_courses([{'id': '3', 'url': 'https://mujlms.manipal.edu/d2l/home/3', 'name': 'DBMS', 'semester': 3}])
        def download(on_download=None, on_progress=None):
            on_download({'path': str(path), 'hash': hashed, 'course': 'DBMS', 'unit': 'Unit 1'})
            try:
                self.assertTrue(started.wait(5), 'AI must begin before sync returns')
            finally:
                release.set()
            return {'new': 1, 'updated': 0, 'unchanged': 0, 'failed': []}
        with patch.object(LMS, 'courses', side_effect=discover), patch.object(LMS, 'sync', side_effect=download), patch.object(self.app, 'key', return_value='fake'), patch('muj_study.gemini.Gemini.analyze', side_effect=analyze):
            report = execute(self.app, 'sync', 3, lambda _: None)
        self.assertEqual(len(report['analysis']), 1)
        self.assertNotIn('error', report['analysis'][0])

    def test_three_download_workers_overlap_with_private_contexts(self):
        barrier = threading.Barrier(3)
        thread_ids, guard = set(), threading.Lock()
        selected = [(f'https://mujlms.manipal.edu/{i}.txt', 'DBMS', 'Unit 1', str(i), 3, 'course') for i in range(3)]
        def download(lms, context, url, *args, **kwargs):
            with guard: thread_ids.add(threading.get_ident())
            barrier.wait(timeout=8)
            return 'new'
        runtime = Mock()
        manager = Mock(); manager.__enter__ = Mock(return_value=runtime); manager.__exit__ = Mock(return_value=False)
        report = {'new': 0, 'updated': 0, 'unchanged': 0, 'failed': []}
        with patch('playwright.sync_api.sync_playwright', return_value=manager), patch.object(LMS, 'download', new=download):
            LMS(self.app).download_parallel(selected, {'cookies': [], 'origins': []}, 3, report, None, None)
        self.assertEqual(report['new'], 3)
        self.assertEqual(len(thread_ids), 3)
        self.assertEqual(runtime.request.new_context.call_count, 3)

    def test_analysis_errors_and_live_counts_are_published_before_finish(self):
        from muj_study.core import StudyError
        from muj_study.pipeline import AnalysisPipeline
        updates = []
        notified = threading.Event()
        def update(value):
            updates.append(value)
            if value['analysis_progress']['failed']: notified.set()
        item = {'path': str(self.base / 'note.txt'), 'hash': 'hash', 'course': 'DBMS', 'unit': 'Unit 1'}
        with patch('muj_study.gemini.Gemini.analyze', side_effect=StudyError('API service unavailable (HTTP 503).')):
            pipeline = AnalysisPipeline(self.app, update)
            pipeline.submit(item)
            self.assertTrue(notified.wait(5), 'Error must be visible while downloads are still running')
            result = pipeline.finish()
        snapshot = updates[-1]['analysis_progress']
        self.assertEqual(snapshot['total'], 1)
        self.assertEqual(snapshot['processed'], 1)
        self.assertEqual(snapshot['succeeded'], 0)
        self.assertEqual(snapshot['failed'], 1)
        self.assertIn('503', snapshot['errors'][0])
        self.assertEqual(snapshot['active'], [])
        self.assertIn('error', result[0])

    def test_budget_pauses_analysis_without_stopping_downloads(self):
        self.app.cfg['gemini_daily_calls'] = 1
        self.app.reserve('gemini_calls', 1)
        LMS(self.app).remember_courses([{'url': 'https://mujlms.manipal.edu/d2l/home/3', 'name': 'DBMS', 'semester': 3}])
        with patch.object(LMS, 'courses'), patch.object(self.app, 'key', return_value='fake'), patch.object(LMS, 'sync', return_value={'new': 0}) as sync, patch('muj_study.pipeline.AnalysisPipeline') as pipeline:
            result = execute(self.app, 'sync', 3, lambda _: None)
        sync.assert_called_once()
        pipeline.assert_not_called()
        self.assertIn('analysis paused', result['analysis_message'])
