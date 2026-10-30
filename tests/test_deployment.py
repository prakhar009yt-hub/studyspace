import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from muj_study.core import ROOT, App, StudyError
from muj_study.lms import LMS


class DeploymentTests(unittest.TestCase):
    def test_container_bootstrap_preserves_preferences_and_creates_theme(self):
        spec = importlib.util.spec_from_file_location('deploy_start', ROOT / 'deploy/start.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'persistent' / 'config.json'
            self.assertEqual(module.prepare(path), path.parent)
            config = json.loads(path.read_text(encoding='utf-8'))
            self.assertFalse(config['lms_auto_sync'])
            self.assertTrue((path.parent / '.streamlit/config.toml').exists())
            config['semester'] = 7
            path.write_text(json.dumps(config), encoding='utf-8')
            module.prepare(path)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['semester'], 7)

    def test_hosted_login_explains_desktop_requirement(self):
        with tempfile.TemporaryDirectory() as folder:
            app = App(Path(folder) / 'config.json', Path(folder) / 'data')
            try:
                with patch.dict(os.environ, {'MUJ_DEPLOYED': '1'}):
                    with self.assertRaisesRegex(StudyError, 'desktop'):
                        LMS(app).login_from_web()
                    with self.assertRaisesRegex(StudyError, 'desktop'):
                        with LMS(app).browser(login=True):
                            pass
            finally:
                app.close()
