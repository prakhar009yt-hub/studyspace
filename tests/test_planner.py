from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from muj_study.core import App, ROOT, StudyError
from muj_study.planner import make_plan, export_csv


def note(course, names, ident='note'):
    return {'id': ident, 'course': course, 'analysis': json.dumps({'topics': [{'name': n} for n in names]})}


class PlannerTests(unittest.TestCase):
    def test_capacity_deadline_priority_dedup_and_labs(self):
        start = date(2026, 11, 1)
        notes = [note('DBMS', ['Easy', 'Hard', 'Easy']), note('COA', ['Adder']), note('DBMS LAB', ['Lab'])]
        plan = make_plan(notes, {'hard': {'weak': 1}}, ['DBMS', 'COA', 'DBMS LAB'], start, start + timedelta(days=2), 40)
        self.assertEqual(plan['topic_count'], 3)
        tasks = [t for d in plan['days'] for t in d['tasks']]
        self.assertEqual(tasks[0]['topic'], 'Hard')
        self.assertTrue(all(d['minutes'] <= 40 and date.fromisoformat(d['date']) < start + timedelta(days=2) for d in plan['days']))
        self.assertEqual(sum(t['minutes'] for t in tasks + plan['unscheduled']), 150)
        self.assertEqual(sum(t['minutes'] for t in plan['unscheduled']), 70)
        self.assertEqual(len({t['id'] for t in tasks}), len(tasks))

    def test_revision_and_export_and_invalid_dates(self):
        start = date(2026, 11, 1)
        notes = [note('DBMS', ['=SUM(A1)', 'Covered'])]
        plan = make_plan(notes, {'covered': {'covered': 1}}, ['DBMS'], start, start + timedelta(days=3), 60)
        self.assertFalse(plan['unscheduled'])
        self.assertEqual([t['stage'] for t in plan['days'][0]['tasks']], ['Study', 'Study', 'Revision'])
        self.assertIn("'=SUM(A1)", export_csv(plan))
        with self.assertRaises(StudyError): make_plan(notes, {}, ['DBMS'], start, start, 60)
        with self.assertRaises(StudyError): make_plan(notes, {}, [], start, start + timedelta(days=1), 60)

    def test_planner_page_saves_and_reloads_progress(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {'MUJ_DATA_DIR': str(base / 'data'), 'MUJ_CONFIG': str(base / 'config.json'), 'MUJ_PRIVATE_DIR': str(base / 'private')}):
                app = App()
                app.cfg['lms']['auto_sync'] = False
                app.save_config()
                entry = note('DBMS', ['Normalization'])
                app.db.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)', ('note', 'DBMS', 'Unit 1', 'note.txt', 'hash', entry['analysis']))
                app.db.commit(); app.close()
                page = AppTest.from_file(str(ROOT / 'dashboard.py'), default_timeout=60)
                page.query_params['page'] = 'Planner'; page.run()
                self.assertEqual(len(page.exception), 0)
                next(b for b in page.button if b.label == 'Generate exam plan').click().run()
                self.assertEqual(len(page.exception), 0)
                saved = base / 'data' / 'exam_plans' / 'semester-3.json'
                self.assertTrue(saved.exists())
                next(c for c in page.checkbox if 'Normalization' in c.label).check()
                next(b for b in page.button if b.label == 'Save daily progress').click().run()
                self.assertEqual(len(page.exception), 0)
                self.assertEqual(len(json.loads(saved.read_text(encoding='utf-8'))['completed']), 1)
                page.run()
                self.assertTrue(next(c for c in page.checkbox if 'Normalization' in c.label).value)
