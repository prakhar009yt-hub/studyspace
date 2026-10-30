import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from muj_study.core import ROOT


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompanionTests(unittest.TestCase):
    def test_bundle_is_source_only_and_complete(self):
        builder = load_module('package_companion', ROOT / 'scripts/package_companion.py')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'companion.zip'
            builder.package(path)
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                self.assertIsNone(archive.testzip())
                for name in ['Setup.cmd', 'Studyspace.cmd', 'local_companion.py', 'dashboard.py', 'config.example.json', 'pyproject.toml', 'muj_study/cli.py', 'assets/sidebar.css']:
                    self.assertIn('Studyspace/' + name, names)
                self.assertTrue(all(n.startswith('Studyspace/') and '..' not in Path(n).parts for n in names))
                self.assertFalse(any('/data/' in n or '/.venv/' in n or n.endswith(('/config.json', '/keys.json', '/session.json')) for n in names))

    def test_companion_does_not_adopt_an_unrelated_process(self):
        runner = load_module('local_companion', ROOT / 'companion/local_companion.py')
        self.assertEqual(runner.ROOT, ROOT)
        self.assertFalse(runner.owns_process(None))
        self.assertFalse(runner.owns_process(-1))
        with patch.object(runner.os, 'name', 'nt'), patch.object(runner.subprocess, 'CREATE_NO_WINDOW', 0, create=True), patch.object(runner.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = 'python some-other-app.py'
            self.assertFalse(runner.owns_process(123))
            run.return_value.stdout = f'python {runner.ROOT}/dashboard.py --server.port=8765'
            self.assertTrue(runner.owns_process(123))
