"""Run browser/API work in a child process, away from Streamlit's UI thread."""
import json
import os
import subprocess
import sys
import time
import uuid

from .core import ROOT, StudyError, private_write


class Jobs:
    def __init__(self, app, channel='lms'):
        self.app = app
        self.folder = app.data / ('video-jobs' if channel == 'videos' else 'jobs')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = self.folder / 'active.json'

    def latest(self):
        files = sorted(self.folder.glob('job-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files: return None
        try: return json.loads(files[0].read_text(encoding='utf-8'))
        except (OSError, ValueError): return None

    def active(self, state=None):
        state = state if state is not None else self.latest()
        if state and state['status'] in {'queued', 'running'}:
            if time.time() - state.get('updated', state['started']) < 1800: return state
            state.update(status='failed', message='The background task stopped responding. Try again.')
            private_write(self.folder / state['file'], state)
        return None

    def start(self, task, semester=None, **payload):
        if task not in {'login', 'sync', 'discover', 'analyze', 'videos'}: raise ValueError('Unknown task')
        if task == 'videos' and self.folder.name != 'video-jobs': raise ValueError('Video searches need their separate job channel.')
        active = self.active()
        if active: return active
        # An exclusive file serializes all LMS work, including across browser tabs.
        try:
            if self.lock.exists() and time.time() - self.lock.stat().st_mtime > 1800:
                self.lock.unlink()
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            raise StudyError('Another LMS operation is starting. Please wait.') from None
        name = f'job-{time.time_ns()}-{uuid.uuid4().hex[:8]}.json'
        state = {'file': name, 'task': task, 'semester': int(semester or self.app.cfg['semester']), 'status': 'queued', 'started': time.time(), 'message': 'Starting…'}
        state.update({key: payload[key] for key in ['note_id', 'topic_index', 'refresh', 'playlists'] if key in payload})
        private_write(self.folder / name, state)
        command = [sys.executable, '-m', 'muj_study.worker', str(self.folder / name), '--config', str(self.app.config_path), '--data', str(self.app.data)]
        try:
            subprocess.Popen(command, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except Exception:
            state.update(status='failed', message='Could not start the LMS task. Check the Python installation.')
            private_write(self.folder / name, state)
            self.lock.unlink(missing_ok=True)
            raise StudyError(state['message']) from None
        return state
