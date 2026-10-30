from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, time as datetime_time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


class StudyError(Exception):
    pass


def is_lab_subject(name):
    return str(name).strip().casefold().endswith('lab')


def quota_reset_ist(now=None):
    pacific = ZoneInfo('America/Los_Angeles')
    now = (now or datetime.now(pacific)).astimezone(pacific)
    reset = datetime.combine(now.date() + timedelta(days=1), datetime_time.min, tzinfo=pacific)
    return reset.astimezone(ZoneInfo('Asia/Kolkata'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:120] or 'untitled'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}:
        name = '_' + name
    return name


def private_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.chmod(0o600)
    # Windows may temporarily deny replacement while the UI/antivirus reads it.
    for attempt in range(5):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 4: raise
            time.sleep(0.025 * 2 ** attempt)


class App:
    def __init__(self, config=None, data=None):
        self.config_path = Path(config or os.environ.get('MUJ_CONFIG', ROOT / 'config.json')).resolve()
        defaults = json.loads((ROOT / 'config.example.json').read_text(encoding='utf-8'))
        if self.config_path.exists():
            user = json.loads(self.config_path.read_text(encoding='utf-8'))
            defaults['lms'].update(user.pop('lms', {}))
            defaults.update(user)
        self.cfg = defaults
        self.data = Path(data or os.environ.get('MUJ_DATA_DIR', ROOT / 'data')).resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.private = Path(os.environ.get('MUJ_PRIVATE_DIR', Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'MUJStudyAssistant')).resolve()
        self.session = self.private / 'session.json'
        self.secrets = self.private / 'keys.json'
        # Use a dedicated logger: HTTP libraries may log URLs containing API keys.
        self.logger = logging.getLogger('muj_study')
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.log_handler = logging.FileHandler(self.data / 'activity.log', encoding='utf-8')
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.logger.addHandler(self.log_handler)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        self.db = sqlite3.connect(self.data / 'study.sqlite3', timeout=30)
        self.db.row_factory = sqlite3.Row
        if self.db.execute('PRAGMA user_version').fetchone()[0] < 1:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, expires REAL, value TEXT);
            CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, course TEXT, unit TEXT, path TEXT, hash TEXT, analysis TEXT);
            CREATE TABLE IF NOT EXISTS files(url TEXT PRIMARY KEY, etag TEXT, modified TEXT, hash TEXT, path TEXT);
            CREATE TABLE IF NOT EXISTS links(url TEXT PRIMARY KEY, course TEXT, unit TEXT, title TEXT);
            CREATE TABLE IF NOT EXISTS feedback(video TEXT PRIMARY KEY, channel TEXT, status TEXT, rating TEXT, reason TEXT);
            CREATE TABLE IF NOT EXISTS topics(key TEXT PRIMARY KEY, weak INTEGER DEFAULT 0, covered INTEGER DEFAULT 0, reviewed REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS quota(day TEXT, bucket TEXT, used INTEGER, PRIMARY KEY(day,bucket));
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, created REAL, note TEXT, result TEXT);
            CREATE TABLE IF NOT EXISTS pending(key TEXT PRIMARY KEY, payload TEXT);
            CREATE TABLE IF NOT EXISTS courses(url TEXT PRIMARY KEY, name TEXT, course_id TEXT, tracked INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS library(url TEXT PRIMARY KEY, course TEXT, unit TEXT, title TEXT, path TEXT, kind TEXT, hash TEXT, checked REAL);
            CREATE TABLE IF NOT EXISTS note_semesters(note TEXT PRIMARY KEY, semester INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS library_semesters(url TEXT PRIMARY KEY, semester INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS library_courses(url TEXT PRIMARY KEY, course_url TEXT NOT NULL);
            ''')
            if 'semester' not in {r['name'] for r in self.db.execute('PRAGMA table_info(courses)')}:
                self.db.execute('ALTER TABLE courses ADD COLUMN semester INTEGER')
            # Existing manual imports belong to the selected semester at upgrade time.
            self.db.execute('INSERT OR IGNORE INTO note_semesters SELECT id,? FROM notes', (self.cfg['semester'],))
            self.db.commit()

            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS analysis_agents_state(id TEXT PRIMARY KEY, project TEXT, last_used REAL DEFAULT 0, busy_until REAL DEFAULT 0, cooldown_until REAL DEFAULT 0, error TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS token_usage(id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, agent TEXT, model TEXT, input_tokens INTEGER, output_tokens INTEGER, thinking_tokens INTEGER, cached_tokens INTEGER);
            ''')
            self.db.executescript('''
            CREATE INDEX IF NOT EXISTS idx_history_note_id ON history(note,id DESC);
            CREATE INDEX IF NOT EXISTS idx_note_semester ON note_semesters(semester,note);
            CREATE INDEX IF NOT EXISTS idx_library_semester ON library_semesters(semester,url);
            CREATE INDEX IF NOT EXISTS idx_courses_semester ON courses(semester,name);
            PRAGMA user_version=1;
            ''')
            self.db.commit()

    def close(self):
        self.db.close()
        self.logger.removeHandler(self.log_handler)
        self.log_handler.close()

    def save_config(self):
        private_write(self.config_path, self.cfg)

    def key(self, name):
        keys = json.loads(self.secrets.read_text()) if self.secrets.exists() else {}
        value = os.environ.get(name) or keys.get(name)
        if not value:
            raise StudyError(f'{name} is missing. Run: python -m muj_study setup')
        return value

    def cached(self, key, stale=False):
        row = self.db.execute('SELECT * FROM cache WHERE key=?', (key,)).fetchone()
        if row and (stale or row['expires'] > time.time()):
            self.logger.debug('Cache hit %s', key[:80])
            return json.loads(row['value'])
        return None

    def cache(self, key, value, days=14):
        self.db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)', (key, time.time() + days * 86400, json.dumps(value)))
        self.db.commit()
        return value

    def budget_remaining(self, bucket, limit):
        if int(limit) == 0: return float('inf')
        day = datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat()
        row = self.db.execute('SELECT used FROM quota WHERE day=? AND bucket=?', (day, bucket)).fetchone()
        return max(0, int(limit) - (row['used'] if row else 0))

    def reserve(self, bucket, limit):
        day = datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat()
        # Atomic reservation, including failed requests. Local meter cannot see other apps.
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO quota VALUES(?,?,0)', (day, bucket))
            changed = self.db.execute('UPDATE quota SET used=used+1 WHERE day=? AND bucket=? AND (?=0 OR used<?)', (day, bucket, limit, limit)).rowcount
            if not changed:
                raise StudyError(f'Local {bucket} daily budget reached; cached results remain available. Retry after Pacific midnight.')

    def feedback(self, video, channel='', status='', rating='', reason=''):
        old = self.db.execute('SELECT * FROM feedback WHERE video=?', (video,)).fetchone()
        self.db.execute('INSERT OR REPLACE INTO feedback VALUES(?,?,?,?,?)', (video, channel or (old['channel'] if old else ''), status or (old['status'] if old else ''), rating or (old['rating'] if old else ''), reason or (old['reason'] if old else '')))
        self.db.commit()
        if status == 'watched' or rating == 'helpful':
            for row in self.db.execute('SELECT result FROM history ORDER BY id DESC LIMIT 100'):
                learned = False
                for topic in json.loads(row['result']):
                    for candidate in topic['videos']:
                        if candidate['id'] == video and candidate.get('queries'):
                            key = 'query-learning:' + digest([self.cfg['subject'], topic['topic'].casefold(), self.cfg['languages']])
                            previous = self.cached(key) or []
                            self.cache(key, list(dict.fromkeys(candidate['queries'] + previous))[:2], 180)
                            learned = True
                if learned:
                    break

    def topic(self, name, weak=None, covered=None):
        key = name.casefold().strip()
        self.db.execute('INSERT OR IGNORE INTO topics(key) VALUES(?)', (key,))
        if weak is not None:
            self.db.execute('UPDATE topics SET weak=? WHERE key=?', (int(weak), key))
        if covered is not None:
            self.db.execute('UPDATE topics SET covered=?,reviewed=? WHERE key=?', (int(covered), time.time(), key))
        self.db.commit()


def retry(action):
    for attempt in range(3):
        try:
            return action()
        except StudyError:
            raise
        except Exception as exc:
            code = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
            if code in {400, 401, 403}:
                raise StudyError(f'API rejected the request (HTTP {code}). Check the API key, enabled API, selected model and access restrictions.') from None
            if attempt == 2:
                # Do not print SDK/HTTP exception URLs, which can contain secrets.
                logging.getLogger('muj_study').error('Request failed: %s', type(exc).__name__)
                if code == 429:
                    raise StudyError('API quota/rate limit reached. Reduce the budget, wait for reset, or check provider billing/limits.') from None
                if isinstance(code, int) and code >= 500:
                    raise StudyError(f'API service unavailable (HTTP {code}). Saved notes remain available; retry analysis later.') from None
                label = type(exc).__name__
                if any(word in label for word in ['Connect', 'Network', 'DNS']):
                    raise StudyError('Cannot reach the API. Check your internet connection, DNS or proxy.') from None
                raise StudyError(f'Request failed ({label}). Check connection, API access and quota.') from None
            time.sleep(2 ** attempt)
