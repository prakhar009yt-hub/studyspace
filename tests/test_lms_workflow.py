import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from muj_study.core import App, StudyError
from muj_study.jobs import Jobs
from muj_study.library import assign_semester, semester_courses, semester_library, semester_notes
from muj_study.lms import LMS
from muj_study.worker import execute


class LMSWorkflowTests(unittest.TestCase):
    def test_long_job_with_recent_progress_is_still_active(self):
        import time
        from muj_study.core import private_write
        jobs = Jobs(self.app)
        state = {'file': 'job-long.json', 'task': 'analyze', 'semester': 3,
                 'status': 'running', 'started': time.time() - 3600, 'updated': time.time() - 2}
        private_write(jobs.folder / state['file'], state)
        self.assertEqual(jobs.active()['status'], 'running')

    def test_temporary_network_change_recovers_with_bounded_navigation_retry(self):
        from unittest.mock import Mock
        page = Mock()
        page.goto.side_effect = [RuntimeError('net::ERR_NETWORK_CHANGED'), 'loaded']
        lms = LMS(self.app)
        with patch('muj_study.lms.time.sleep') as sleep:
            self.assertEqual(lms.navigate(page, 'https://mujlms.manipal.edu/d2l/home'), 'loaded')
        self.assertEqual(page.goto.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_persistent_network_error_stops_after_three_attempts(self):
        from unittest.mock import Mock
        page = Mock()
        page.goto.side_effect = RuntimeError('net::ERR_NETWORK_CHANGED')
        with patch('muj_study.lms.time.sleep'):
            with self.assertRaisesRegex(StudyError, 'after 3 attempts'):
                LMS(self.app).navigate(page, 'https://mujlms.manipal.edu/d2l/home')
        self.assertEqual(page.goto.call_count, 3)

    def test_security_navigation_error_is_never_retried(self):
        from unittest.mock import Mock
        page = Mock()
        page.goto.side_effect = RuntimeError('net::ERR_CERT_AUTHORITY_INVALID')
        with self.assertRaises(RuntimeError): LMS(self.app).navigate(page, 'https://mujlms.manipal.edu/d2l/home')
        self.assertEqual(page.goto.call_count, 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = App(self.root / 'config.json', self.root / 'data')
        self.app.cfg.update(semester=3, request_delay=0, lms_auto_analyze=False)

    def tearDown(self):
        self.app.close(); self.temp.cleanup()

    def courses(self):
        return [{'url': 'https://mujlms.manipal.edu/d2l/home/1', 'name': 'Mathematics', 'id': '1', 'semester': 1},
                {'url': 'https://mujlms.manipal.edu/d2l/home/3', 'name': 'Mathematics', 'id': '3', 'semester': 3},
                {'url': 'https://mujlms.manipal.edu/d2l/home/9', 'name': 'Unlabeled subject', 'id': '9'}]

    def test_browser_launch_falls_back_to_installed_edge(self):
        from unittest.mock import Mock
        playwright = Mock()
        browser = Mock()
        playwright.chromium.launch.side_effect = [RuntimeError('Chrome unavailable'), browser]
        self.assertIs(LMS(self.app).launch_browser(playwright, headless=False), browser)
        self.assertEqual(playwright.chromium.launch.call_args_list[0].kwargs['channel'], 'chrome')
        self.assertEqual(playwright.chromium.launch.call_args_list[1].kwargs['channel'], 'msedge')

    def test_explicit_semester_labels_without_year_or_course_code_guessing(self):
        for label, expected in [('Semester 3 DBMS', 3), ('Sem III - DBMS', 3), ('3rd Semester', 3), ('SEM-VIII', 8), ('BTECH-0005_Sem_III_July_Dec_2026', 3), ('BTECH-FIRST_Sem_II_Jan_May_2026', 2), ('BTECH_Sem_Ⅲ_July_2026', 3), ('SEM_12_2026', 12), ('2025-2026 DBMS', None), ('CSE2301', None)]:
            self.assertEqual(LMS.semester_number(label), expected, label)

    def test_course_inherits_semester_from_underscore_group_label(self):
        def response(_, path, params=None):
            if 'myenrollments/' in path:
                return {'Items': [{'OrgUnit': {'Id': 3, 'Name': 'DATA STRUCTURES AND ALGORITHMS', 'Code': 'BTECH-0005_CSC2101_JULY_DEC_2026'}}], 'PagingInfo': {'HasMoreItems': False}}
            if 'ancestors' in path:
                return [{'Name': 'BTECH-0005_Sem_III_July_Dec_2026', 'Code': 'BTECH-0005_Sem_III_July_Dec_2026'}]
            raise StudyError('Not available for student role')
        with patch.object(LMS, 'versions', return_value={'lp': '1.49', 'le': '1.82'}), patch.object(LMS, 'api_json', side_effect=response):
            courses = LMS(self.app).brightspace_courses(object())
        self.assertEqual(courses[0]['semester'], 3)
        self.assertEqual(courses[0]['name'], 'DATA STRUCTURES AND ALGORITHMS')

    def test_semester_parent_relationship_works_when_ancestor_api_is_denied(self):
        courses = [{'id': '3', 'name': 'DBMS', 'semester': None}, {'id': '2', 'name': 'Physics', 'semester': None}]
        data = [{'CourseOfferingId': 3, 'Semesters': [{'Name': 'BTECH-0005_Sem_III_July_Dec_2026'}]}, {'CourseOfferingId': 2, 'Semesters': [{'Name': 'BTECH-FIRST_Sem_II_Jan_May_2026'}]}]
        with patch.object(LMS, 'api_json', return_value=data) as request:
            result = LMS(self.app).resolve_course_semesters(object(), '1.64', courses)
        self.assertEqual([c['semester'] for c in result], [3, 2])
        self.assertEqual(request.call_count, 1)

    def test_discovery_preserves_manual_semester_assignment(self):
        lms = LMS(self.app); lms.remember_courses(self.courses())
        url = self.courses()[2]['url']
        assign_semester(self.app, [url], 3)
        lms.remember_courses(self.courses())
        self.assertEqual(len(semester_courses(self.app)), 2)
        self.assertEqual({c['course_id'] for c in semester_courses(self.app)}, {'3', '9'})

    def test_worker_sync_never_tracks_previous_or_unknown_semesters(self):
        with patch.object(LMS, 'courses', side_effect=lambda: LMS(self.app).remember_courses(self.courses())), patch.object(LMS, 'sync', return_value={'new': 1, 'updated': 0, 'failed': []}) as sync:
            result = execute(self.app, 'sync', 3, lambda _: None)
        self.assertEqual(result['subjects'], 1)
        self.assertEqual(result['unassigned'], 1)
        self.assertEqual([c['url'] for c in self.app.cfg['tracked_courses']], [self.courses()[1]['url']])
        self.assertEqual(sync.call_count, 1)
        self.assertIsNotNone(self.app.cached('lms-last-sync:3'))
        self.assertIsNone(self.app.cached('lms-last-sync:1'))

    def test_worker_login_automatically_discovers_and_fetches(self):
        with patch.object(LMS, 'login_from_web') as login, patch.object(LMS, 'courses', side_effect=lambda: LMS(self.app).remember_courses(self.courses())), patch.object(LMS, 'sync', return_value={'new': 0, 'failed': []}) as sync:
            execute(self.app, 'login', 3, lambda _: None)
        login.assert_called_once(); sync.assert_called_once()

    def test_unknown_subjects_do_not_get_downloaded(self):
        with patch.object(LMS, 'courses', side_effect=lambda: LMS(self.app).remember_courses(self.courses())), patch.object(LMS, 'sync') as sync:
            result = execute(self.app, 'sync', 6, lambda _: None)
        sync.assert_not_called()
        self.assertEqual(result['subjects'], 0)
        self.assertIsNotNone(self.app.cached('lms-last-sync:6'))

    def test_progress_includes_subjects_without_analyzed_notes(self):
        from muj_study.workflow import progress
        courses = [{'id': str(i), 'url': f'https://mujlms.manipal.edu/d2l/home/{i}', 'name': f'Subject {i}', 'semester': 3} for i in range(8)]
        LMS(self.app).remember_courses(courses)
        LMS(self.app).remember_courses([{'id': 'old', 'url': 'https://mujlms.manipal.edu/d2l/home/old', 'name': 'Old subject', 'semester': 2}])
        path = self.root / 'note.pdf'; path.write_bytes(b'note')
        LMS(self.app).catalog('note', 'Subject 0', 'Unit 1', 'Note', path, 'hash', 3)
        result = progress(self.app)['courses']
        self.assertEqual(len(result), 8)
        self.assertNotIn('Old subject', result)
        self.assertEqual(result['Subject 0']['pending'], 1)
        self.assertEqual(result['Subject 0']['analyzed'], 0)
        self.assertEqual(result['Subject 1']['status'], 'No downloaded notes yet')

    def test_catalog_and_analysis_stay_in_their_semester(self):
        for semester in [1, 3]:
            path = self.root / f'sem{semester}.txt'; path.write_text('note')
            LMS(self.app).catalog(f'https://mujlms.manipal.edu/n{semester}', 'Math', 'Unit 1', 'Note', path, 'hash', semester, f'course{semester}')
            self.app.db.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)', (str(semester), 'Math', 'Unit 1', str(path), 'hash', json.dumps({'topics': [], 'summary': 'Test'})))
            self.app.db.execute('INSERT INTO note_semesters VALUES(?,?)', (str(semester), semester))
        self.app.db.commit()
        self.assertEqual([n['id'] for n in semester_notes(self.app)], ['3'])
        self.assertEqual(len(semester_library(self.app)), 1)
        self.app.cfg['semester'] = 1
        self.assertEqual([n['id'] for n in semester_notes(self.app)], ['1'])
        self.assertEqual(len(semester_library(self.app)), 1)

    def test_reassigning_same_named_course_does_not_move_other_semester(self):
        LMS(self.app).remember_courses(self.courses())
        for c in self.courses()[:2]:
            path = self.root / f'{c["id"]}.txt'; path.write_text('test')
            LMS(self.app).catalog('file' + c['id'], c['name'], 'Unit 1', 'Test', path, 'hash', c['semester'], c['url'])
        assign_semester(self.app, [self.courses()[1]['url']], 5)
        self.app.cfg['semester'] = 1
        self.assertEqual([n['url'] for n in semester_library(self.app)], ['file1'])
        self.app.cfg['semester'] = 5
        self.assertEqual([n['url'] for n in semester_library(self.app)], ['file3'])

    def test_background_job_is_singleton_and_captures_semester(self):
        self.app.save_config()
        jobs = Jobs(self.app)
        with patch('muj_study.jobs.subprocess.Popen') as spawn:
            first = jobs.start('sync')
            self.app.cfg['semester'] = 1
            second = jobs.start('sync')
        self.assertEqual(first['file'], second['file'])
        self.assertEqual(first['semester'], 3)
        self.assertEqual(spawn.call_count, 1)
