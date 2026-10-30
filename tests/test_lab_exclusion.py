import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from muj_study.core import App, StudyError, is_lab_subject
from muj_study.gemini import Gemini
from muj_study.library import analyze_catalog, semester_courses, semester_library, semester_notes
from muj_study.lms import LMS
from muj_study.pipeline import AnalysisPipeline
from muj_study.worker import execute
from muj_study.workflow import progress


class LabExclusionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app = App(root / 'config.json', root / 'data')
        self.app.cfg.update(semester=3, lms_auto_analyze=False)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def test_suffix_is_case_insensitive_and_ignores_trailing_spaces(self):
        for name in ['DBMS LAB', 'DSA Lab', 'Programming lab  ', 'DBMS_LAB']:
            self.assertTrue(is_lab_subject(name))
        for name in ['DBMS', 'Lab Management', 'LAB Theory']:
            self.assertFalse(is_lab_subject(name))

    def test_direct_download_and_analysis_stop_before_io(self):
        with patch.object(LMS, 'browser') as browser, patch.object(Gemini, 'generate') as generate:
            with self.assertRaisesRegex(StudyError, 'excluded'):
                LMS(self.app).download(None, 'https://example.com/note.pdf', 'DBMS LAB', 'Unit', 'Title')
            with self.assertRaisesRegex(StudyError, 'excluded'):
                Gemini(self.app).analyze('nonexistent.pdf', 'DBMS lab')
            self.assertEqual(LMS(self.app).brightspace_sync([{'name': 'DSA LAB'}])['new'], 0)
            browser.assert_not_called()
            generate.assert_not_called()

    def test_worker_tracks_theory_only_and_reports_skipped_labs(self):
        courses = [{'url': 'https://mujlms.manipal.edu/d2l/home/1', 'name': 'DBMS', 'semester': 3},
                   {'url': 'https://mujlms.manipal.edu/d2l/home/2', 'name': 'DBMS LAB', 'semester': 3}]
        LMS(self.app).remember_courses(courses)
        with patch.object(LMS, 'courses'), patch.object(LMS, 'sync', return_value={'new': 0}) as sync:
            result = execute(self.app, 'sync', 3, lambda _: None)
        sync.assert_called_once()
        self.assertEqual([c['name'] for c in self.app.cfg['tracked_courses']], ['DBMS'])
        self.assertEqual(result['skipped_labs'], ['DBMS LAB'])
        self.assertEqual(self.app.db.execute('SELECT COUNT(*) FROM courses').fetchone()[0], 2)
        self.assertEqual([c['name'] for c in semester_courses(self.app)], ['DBMS'])

    def test_existing_lab_files_are_preserved_but_never_queued(self):
        path = self.app.data / 'lab.txt'
        path.write_text('Lab note')
        LMS(self.app).catalog('url', 'DBMS LAB', 'Unit', 'Title', str(path), 'hash', 3)
        with patch.object(Gemini, 'analyze') as analyze:
            pipeline = AnalysisPipeline(self.app, lambda _: None)
            pipeline.seed(self.app)
            self.assertEqual(pipeline.finish(), [])
            self.assertEqual(analyze_catalog(self.app), [])
            analyze.assert_not_called()
        self.assertNotIn('DBMS LAB', progress(self.app)['courses'])
        self.assertEqual(semester_library(self.app), [])
        self.assertEqual(len(semester_library(self.app, include_labs=True)), 1)
        self.assertTrue(path.exists())
