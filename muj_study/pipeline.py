"""Bounded AI consumers that overlap the LMS download producer."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
import threading
import json
import time

from .core import App, StudyError, is_lab_subject
from .gemini import Gemini
from .library import semester_library, semester_notes
from .agents import AgentPool


class AnalysisPipeline:
    def __init__(self, app, update):
        self.config = app.config_path
        self.data = app.data
        self.settings = deepcopy(app.cfg)
        self.update = update
        count = max(1, len(AgentPool(app).agents))
        self.pool = ThreadPoolExecutor(max_workers=max(1, min(8, count, int(app.cfg.get('analysis_workers', 2)))))
        self.seen = set()
        self.ready = {(n['path'], n['hash']) for n in semester_notes(app) if json.loads(n['analysis']).get('topics')}
        self.futures = []
        self.lock = threading.Lock()
        self.completed = 0
        self.failed = 0
        self.deferred = 0
        self.path_locks = {}
        self.content_locks = {}
        self.blocked_error = None
        self.active_files = {}
        self.errors = []
        self.started_at = None

    def publish(self):
        with self.lock:
            snapshot = {'total': len(self.seen), 'processed': self.completed,
                        'succeeded': self.completed - self.failed - self.deferred, 'failed': self.failed, 'deferred': self.deferred,
                        'active': list(self.active_files.values()), 'errors': list(self.errors),
                        'blocked_error': self.blocked_error, 'started_at': self.started_at or time.time(), 'measured_at': time.time()}
        self.update({'analysis_progress': snapshot})

    def submit(self, item):
        if is_lab_subject(item['course']): return
        if Path(item['path']).suffix.lower() not in {'.pdf', '.pptx', '.docx', '.txt', '.md'}: return
        identity = (item['path'], item['hash'])
        with self.lock:
            if identity in self.ready: return
            if identity in self.seen: return
            if self.started_at is None: self.started_at = time.time()
            self.seen.add(identity)
            self.path_locks.setdefault(item['path'], threading.Lock())
            self.content_locks.setdefault((item['hash'], item['course'], item['unit']), threading.Lock())
            self.futures.append(self.pool.submit(self.analyze, dict(item)))
        self.publish()

    def analyze(self, item):
        with self.path_locks[item['path']]:
            # Identical content in the same course/unit shares its cached analysis,
            # even when the LMS supplied different URLs or filenames.
            with self.content_locks[(item['hash'], item['course'], item['unit'])]:
                return self.analyze_version(item)

    def analyze_version(self, item):
        with self.lock:
            self.active_files[item['path']] = f'{item["course"]} / {Path(item["path"]).name}'
        self.publish()
        app = App(self.config, self.data)
        app.cfg = deepcopy(self.settings)
        already_blocked = bool(self.blocked_error)
        try:
            if self.blocked_error: raise StudyError(self.blocked_error)
            result = Gemini(app).analyze(item['path'], item['course'], item['unit'], expected_hash=item['hash'])
            result = {'path': item['path'], **result}
        except Exception as exc:
            result = {'path': item['path'], 'error': str(exc) if isinstance(exc, StudyError) else type(exc).__name__}
            if already_blocked or (isinstance(exc, StudyError) and any(s in str(exc) for s in ['daily budget reached', 'agents are paused', 'agents are busy'])):
                result['deferred'] = True
            if isinstance(exc, StudyError) and any(s in str(exc) for s in ['API rejected', 'quota/rate limit', 'daily budget reached', 'service unavailable', 'agents are paused', 'agents are busy']):
                if not AgentPool(app).available(): self.blocked_error = str(exc)
        finally:
            app.close()
        with self.lock:
            self.completed += 1
            self.failed += bool(result.get('error') and not result.get('deferred'))
            self.deferred += bool(result.get('deferred'))
            if not result.get('error'): self.ready.add((item['path'], item['hash']))
            self.active_files.pop(item['path'], None)
            if result.get('error') and result['error'] not in self.errors:
                self.errors = (self.errors + [result['error']])[-5:]
        self.publish()
        return result

    def seed(self, app):
        # Pending notes from earlier runs begin analysis before today's downloads.
        for item in semester_library(app):
            old = app.db.execute('SELECT hash,analysis FROM notes WHERE path=?', (item['path'],)).fetchone()
            import json
            if not old or old['hash'] != item['hash'] or not json.loads(old['analysis'])['topics']: self.submit(item)

    def finish(self):
        try:
            results = []
            for future in as_completed(list(self.futures)):
                results.append(future.result())
                self.publish()
            return results
        finally:
            self.pool.shutdown(wait=True)


class RequestPacer:
    """One request-start rate limit shared by all download workers."""
    def __init__(self, delay):
        self.delay = max(0.25, float(delay))
        self.lock = threading.Lock()
        self.next_start = 0

    def wait(self):
        import time
        with self.lock:
            now = time.monotonic()
            wait = max(0, self.next_start - now)
            self.next_start = max(now, self.next_start) + self.delay
        if wait: time.sleep(wait)
