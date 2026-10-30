from __future__ import annotations

import hashlib
import logging
import os
import re
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from .core import ROOT, StudyError, private_write, safe_name, is_lab_subject


class LMS:
    """All LMS layout dependencies live here and in config.lms selectors."""
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg['lms']
        self.on_status = None

    def navigate(self, page, url):
        """Recover temporary network changes, without retrying auth/security failures."""
        for attempt in range(3):
            try:
                return page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except Exception as exc:
                temporary = any(label in str(exc) for label in (
                    'ERR_NETWORK_CHANGED', 'ERR_INTERNET_DISCONNECTED', 'ERR_CONNECTION_RESET',
                    'ERR_CONNECTION_TIMED_OUT', 'ERR_NAME_NOT_RESOLVED', 'Timeout'))
                if not temporary: raise
                if attempt == 2:
                    raise StudyError('MUJ network connection failed after 3 attempts. Saved files are intact. Check your connection, then retry the fetch; reconnect MUJ only if your session has expired.') from None
                self.app.logger.warning('Temporary MUJ navigation failure; retry %s of 2', attempt + 1)
                if self.on_status:
                    self.on_status(f'Temporary network interruption. Retrying MUJ connection ({attempt + 1}/2)…')
                time.sleep(2 ** (attempt + 1))

    def launch_browser(self, playwright, headless):
        # Prefer the machine's signed browser; bundled Chromium can be blocked by
        # Windows application controls even when its download succeeded.
        configured = self.cfg.get('browser_channel')
        channels = [configured] if configured else ['chrome', 'msedge', None]
        for channel in channels:
            try:
                options = {'headless': headless}
                if channel: options['channel'] = channel
                return playwright.chromium.launch(**options)
            except Exception as exc:
                self.app.logger.warning('Browser launch failed for %s: %s', channel or 'bundled Chromium', type(exc).__name__)
        raise StudyError('Could not start Chrome, Edge or Chromium. Install/update Chrome or Edge, then click Connect MUJ LMS again.')

    def validate(self):
        for key in ['login_url', 'home_url', 'logged_in_selector', 'course_selector']:
            if not self.cfg.get(key):
                raise StudyError(f'LMS configuration needs lms.{key}. See docs/LMS.md.')
        if urlparse(self.cfg['home_url']).scheme != 'https':
            raise StudyError('LMS home URL must use HTTPS.')

    def allowed(self, url):
        parsed = urlparse(url)
        hosts = {urlparse(self.cfg['home_url']).hostname, *self.cfg.get('allowed_hosts', [])}
        return parsed.scheme == 'https' and parsed.hostname in hosts

    def protect_session(self):
        path = self.app.session.resolve()
        if path.is_relative_to(ROOT) or any((p / '.git').exists() for p in path.parents) or any(x in str(path).casefold() for x in ['onedrive', 'dropbox', 'google drive', 'shared']):
            raise StudyError('Session location is inside a repository/shared folder. Set MUJ_PRIVATE_DIR to a private folder outside it.')

    def check(self, page):
        self.navigate(page, self.cfg['home_url'])
        if not self.allowed(page.url) or '/login' in page.url.casefold():
            raise StudyError('MUJ redirected to sign-in. Your saved session has expired; click Connect MUJ LMS and sign in manually.')
        try:
            page.locator(self.cfg['logged_in_selector']).first.wait_for(state='visible', timeout=15000)
        except Exception:
            raise StudyError('MUJ login could not be verified. Click Connect MUJ LMS to sign in again. If the browser already shows your courses, the login-detection selector may need updating.') from None

    @contextmanager
    def browser(self, login=False):
        if login and os.environ.get('MUJ_DEPLOYED') == '1':
            raise StudyError('Manual MUJ login needs the desktop app. This hosted server has no interactive sign-in window. See docs/DEPLOYMENT.md.')
        from playwright.sync_api import sync_playwright
        self.validate()
        self.protect_session()
        if not login and not self.app.session.exists():
            raise StudyError('Session expired, please log in again. Run: python -m muj_study login')
        with sync_playwright() as p:
            browser = self.launch_browser(p, headless=not login)
            context = browser.new_context(storage_state=None if login else str(self.app.session))
            try:
                page = context.new_page()
                if login:
                    self.navigate(page, self.cfg['login_url'])
                    input('Sign in manually in the browser, complete SSO/OTP, then press Enter here: ')
                self.check(page)
                if login:
                    private_write(self.app.session, context.storage_state())
                yield page, context
            finally:
                context.close()
                browser.close()

    def login(self):
        with self.browser(login=True):
            pass

    def login_from_web(self, timeout=300):
        """Visible browser; detect successful manual login without terminal input."""
        if os.environ.get('MUJ_DEPLOYED') == '1':
            raise StudyError('Manual MUJ login needs the desktop app. This hosted server has no interactive sign-in window. See docs/DEPLOYMENT.md.')
        from playwright.sync_api import sync_playwright
        self.validate()
        self.protect_session()
        with sync_playwright() as p:
            browser = self.launch_browser(p, headless=False)
            context = browser.new_context()
            try:
                page = context.new_page()
                self.navigate(page, self.cfg['login_url'])
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if not context.pages:
                        raise StudyError('Sign-in window closed. Click Connect MUJ LMS to try again.')
                    for tab in context.pages:
                        if self.allowed(tab.url) and '/d2l/' in tab.url and '/login' not in tab.url.casefold():
                            if tab.locator(self.cfg['logged_in_selector']).first.is_visible():
                                self.check(tab)
                                private_write(self.app.session, context.storage_state())
                                return {'message': 'MUJ sign-in complete. Your session was saved privately.'}
                    context.pages[0].wait_for_timeout(1000)
                raise StudyError('Sign-in timed out after five minutes. Click Connect MUJ LMS to try again.')
            finally:
                context.close()
                browser.close()

    def remember_courses(self, courses):
        for course in courses:
            self.app.db.execute('INSERT INTO courses(url,name,course_id) VALUES(?,?,?) ON CONFLICT(url) DO UPDATE SET name=excluded.name,course_id=excluded.course_id', (course['url'], course['name'], course.get('id', '')))
            if course.get('semester'):
                self.app.db.execute('UPDATE courses SET semester=COALESCE(semester,?) WHERE url=?', (course['semester'], course['url']))
        self.app.db.commit()
        return courses

    @staticmethod
    def semester_number(text):
        """Only explicit semester labels; never guess from a year or course code."""
        # Brightspace uses identifiers such as BTECH-0005_Sem_III_July_Dec_2026.
        # Underscores are regex word characters, so raw \b boundaries miss both
        # "_Sem" and "III_". Normalize identifier separators before matching.
        text = unicodedata.normalize('NFKC', text or '').replace('_', ' ')
        match = re.search(r'\b(?:sem(?:ester)?)[\s:\-]*(\d{1,2}|VIII|VII|VI|IV|III|II|IX|XII|XI|V|X|I)\b', text, re.I)
        if not match:
            match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?[\s\-]+semester\b', text, re.I)
        if not match:
            return None
        value = match.group(1).upper()
        romans = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10, 'XI': 11, 'XII': 12}
        number = int(value) if value.isdigit() else romans.get(value)
        return number if number and 1 <= number <= 12 else None

    def courses(self, refresh=False):
        if self.cfg.get('adapter') == 'brightspace':
            with self.browser() as (_, context):
                key = 'lms-courses:' + hashlib.sha256(self.app.session.read_bytes()).hexdigest()
                courses = None if refresh else self.app.cached(key)
                if courses is None:
                    courses = self.app.cache(key, self.brightspace_courses(context), 15 / 1440)
                return self.remember_courses(courses)
        with self.browser() as (page, _):
            links = page.locator(self.cfg['course_selector']).evaluate_all('(els) => els.map(e => ({name: e.innerText.trim() || e.getAttribute("aria-label"), url: e.href}))')
            valid = {x['url']: x for x in links if x.get('url') and self.allowed(x['url'])}
            if not valid:
                raise StudyError('No courses found. LMS layout may have changed; check course_selector. Brightspace course tiles may need the API adapter described in docs/LMS.md.')
            return self.remember_courses(list(valid.values()))

    def sync(self, course_filter=None, on_download=None, on_progress=None):
        tracked = [c for c in self.app.cfg.get('tracked_courses', []) if c.get('semester', self.app.cfg['semester']) == self.app.cfg['semester']]
        if course_filter:
            tracked = [c for c in tracked if course_filter.casefold() in c['name'].casefold()]
        if not tracked:
            raise StudyError('No tracked courses. Run courses, then track COURSE_URL COURSE_NAME.')
        tracked = [c for c in tracked if not is_lab_subject(c['name'])]
        if not tracked:
            return {'new': 0, 'updated': 0, 'unchanged': 0, 'failed': [], 'links': 0, 'deferred': 0}
        if self.cfg.get('adapter') == 'brightspace':
            return self.brightspace_sync(tracked, on_download, on_progress)
        if not self.cfg.get('file_selector') or not self.cfg.get('module_selector'):
            raise StudyError('Set lms.file_selector and module_selector to match your LMS content tree.')
        report = {'new': 0, 'updated': 0, 'unchanged': 0, 'failed': [], 'links': 0, 'deferred': 0}
        attempts = 0
        with self.browser() as (page, context):
            for course in tracked:
                if not self.allowed(course['url']):
                    raise StudyError('Tracked course host is not in lms.allowed_hosts.')
                queue = [(course['url'], 'Content')]
                seen = set()
                while queue and len(seen) < self.app.cfg['max_pages_per_course']:
                    url, unit = queue.pop(0)
                    if url in seen:
                        continue
                    seen.add(url)
                    time.sleep(self.app.cfg['request_delay'])
                    self.navigate(page, url)
                    if '/login' in page.url.casefold():
                        raise StudyError('Session expired, please log in again.')
                    if self.cfg.get('unit_selector') and page.locator(self.cfg['unit_selector']).count():
                        unit = page.locator(self.cfg['unit_selector']).first.inner_text().strip()
                    modules = page.locator(self.cfg['module_selector']).evaluate_all('(els) => els.map(e => ({title:e.innerText.trim(), url:e.href}))')
                    for module in modules:
                        if module.get('url') and self.allowed(module['url']) and module['url'] not in seen:
                            queue.append((module['url'], module['title'] or unit))
                    if self.cfg.get('next_selector'):
                        for href in page.locator(self.cfg['next_selector']).evaluate_all('(els) => els.map(e => e.href)'):
                            if href and self.allowed(href) and href not in seen:
                                queue.append((href, unit))
                    files = page.locator(self.cfg['file_selector']).evaluate_all('(els) => els.map(e => ({title:e.innerText.trim(),url:e.href}))')
                    if not modules and not files:
                        report['failed'].append({'course': course['name'], 'reason': 'No content links matched; check LMS selectors or an empty module.'})
                    for item in files:
                        href = item.get('url')
                        if not href:
                            continue
                        if not self.allowed(href) or any(h in (urlparse(href).hostname or '') for h in ['youtube.com', 'youtu.be', 'vimeo.com']) or re.search(r'\.(mp4|webm|mkv)(?:\?|$)', href, re.I):
                            self.app.db.execute('INSERT OR REPLACE INTO links VALUES(?,?,?,?)', (href, course['name'], unit, item['title']))
                            self.app.db.commit()
                            report['links'] += 1
                            continue
                        if attempts >= self.app.cfg['max_downloads']:
                            report['deferred'] += 1
                            continue
                        attempts += 1
                        try:
                            state = self.download(context, href, course['name'], unit, item['title'])
                            report[state] = report.get(state, 0) + 1
                            if on_download:
                                item_row = self.app.db.execute('SELECT * FROM library WHERE url=?', (href,)).fetchone()
                                if item_row: on_download(dict(item_row))
                        except StudyError as exc:
                            if 'Session expired' in str(exc):
                                raise
                            report['failed'].append({'title': item['title'], 'reason': str(exc)})
                if queue:
                    report['failed'].append({'course': course['name'], 'reason': 'Content page traversal limit reached; increase max_pages_per_course.'})
        return report

    def api_json(self, context, path, params=None):
        base = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(self.cfg['home_url']))
        url = urljoin(base, path)
        if not self.allowed(url):
            raise StudyError('Untrusted Brightspace API host.')
        time.sleep(self.app.cfg['request_delay'])
        response = context.request.get(url, params=params, max_redirects=0, timeout=30000)
        try:
            if response.status == 401 or response.status in {301, 302, 303}:
                raise StudyError('Session expired, please log in again.')
            if response.status == 403:
                raise StudyError('Brightspace API access denied. Your university may require an approved OAuth app; use the selector adapter if permitted. See docs/LMS.md.')
            if response.status != 200 or 'json' not in response.headers.get('content-type', ''):
                raise StudyError('Brightspace API unavailable or layout changed. See docs/LMS.md for selector fallback.')
            return response.json()
        finally:
            response.dispose()

    def versions(self, context):
        data = self.api_json(context, '/d2l/api/versions/')
        versions = {item['ProductCode']: item['LatestVersion'] for item in data}
        if not {'lp', 'le'} <= versions.keys():
            raise StudyError('Brightspace API did not advertise lp/le versions.')
        return versions

    def brightspace_courses(self, context):
        versions = self.versions(context)
        courses, bookmark = [], None
        for _ in range(self.app.cfg['max_pages_per_course']):
            params = {'orgUnitTypeId': 3}
            if bookmark:
                params['bookmark'] = bookmark
            data = self.api_json(context, f'/d2l/api/lp/{versions["lp"]}/enrollments/myenrollments/', params)
            for item in data.get('Items', []):
                org = item.get('OrgUnit', {})
                if org.get('Id'):
                    semester = self.semester_number(org['Name'] + ' ' + (org.get('Code') or ''))
                    courses.append({'id': str(org['Id']), 'name': org['Name'], 'url': urljoin(self.cfg['home_url'], f'/d2l/home/{org["Id"]}'), 'semester': semester})
            paging = data.get('PagingInfo', {})
            if not paging.get('HasMoreItems'):
                return self.resolve_course_semesters(context, versions['lp'], courses)
            next_bookmark = paging.get('Bookmark')
            if not next_bookmark or next_bookmark == bookmark:
                raise StudyError('Brightspace returned invalid enrollment pagination.')
            bookmark = next_bookmark
        raise StudyError('Course pagination limit reached.')

    def resolve_course_semesters(self, context, version, courses):
        """Use Brightspace's explicit semester relationship, not subject codes."""
        by_id = {c['id']: c for c in courses if not c.get('semester')}

        def detect(groups):
            numbers = {self.semester_number((g.get('Name') or '') + ' ' + (g.get('Code') or '')) for g in groups if isinstance(g, dict)}
            numbers.discard(None)
            return numbers.pop() if len(numbers) == 1 else None

        ids = list(by_id)
        for start in range(0, len(ids), 25):
            batch = ids[start:start + 25]
            # This relationship is also used by the homepage semester tabs.
            for endpoint in ['parents', 'parentorgunits']:
                try:
                    data = self.api_json(context, f'/d2l/api/lp/{version}/courses/{endpoint}', {'orgUnitIdsCSV': ','.join(batch)})
                    for item in data:
                        course = by_id.get(str(item.get('CourseOfferingId')))
                        if course is not None:
                            groups = item.get('Semesters') or [item.get('Semester')]
                            course['semester'] = detect(groups)
                    if all(by_id[c].get('semester') for c in batch): break
                except StudyError as exc:
                    if 'Session expired' in str(exc): raise
                    self.app.logger.info('Semester relationship lookup unavailable: %s', endpoint)
        for course in by_id.values():
            if course.get('semester'): continue
            course_id = course['id']
            routes = [f'/d2l/api/lp/{version}/courses/{course_id}',
                      f'/d2l/api/lp/{version}/orgstructure/{course_id}/ancestors/',
                      f'/d2l/api/lp/{version}/enrollments/myenrollments/{course_id}/parentOrgUnits']
            for route in routes:
                try:
                    data = self.api_json(context, route)
                    if isinstance(data, list): groups = data
                    elif 'Semester' in data: groups = [data.get('Semester')]
                    else: groups = [i.get('OrgUnit', i) for i in data.get('Items', [])]
                    course['semester'] = detect(groups)
                    if course['semester']: break
                except StudyError as exc:
                    if 'Session expired' in str(exc): raise
        return courses

    @staticmethod
    def flatten_modules(modules, parent=()):
        for module in modules:
            unit = (*parent, module.get('Title', 'Module'))
            for topic in module.get('Topics', []):
                yield unit, topic
            yield from LMS.flatten_modules(module.get('Modules', []), unit)

    def brightspace_sync(self, tracked, on_download=None, on_progress=None):
        report = {'new': 0, 'updated': 0, 'unchanged': 0, 'failed': [], 'links': 0, 'deferred': 0}
        tracked = [c for c in tracked if not is_lab_subject(c['name'])]
        if not tracked: return report
        attempts = 0
        with self.browser() as (_, context):
            if on_progress: on_progress({**report, 'stage': 'discovery', 'detail': 'Checking the MUJ session and content API versions.'})
            versions = self.versions(context)
            # Read all content trees first so an expired session stops before downloads.
            trees = []
            for course in tracked:
                if on_progress: on_progress({**report, 'stage': 'discovery', 'detail': 'Reading subject folders: ' + course['name']})
                match = re.search(r'/d2l/(?:home|le/content)/(\d+)', course['url'])
                if not match or not self.allowed(course['url']):
                    raise StudyError('Expected a trusted Brightspace course URL ending in /d2l/home/COURSE_ID.')
                course_id = match.group(1)
                try:
                    toc = self.api_json(context, f'/d2l/api/le/{versions["le"]}/{course_id}/content/toc')
                    trees.append((course, toc))
                except StudyError as exc:
                    if 'Session expired' in str(exc):
                        raise
                    report['failed'].append({'course': course['name'], 'reason': str(exc)})
            candidates = []
            for course, toc in trees:
                for units, topic in self.flatten_modules(toc.get('Modules', [])):
                    unit = ' / '.join(units)
                    raw_url = topic.get('Url') or topic.get('URL')
                    if not raw_url:
                        continue
                    url = urljoin(self.cfg['home_url'], raw_url)
                    title = topic.get('Title', 'Attachment')
                    if not self.allowed(url) or topic.get('Type') == 3 or re.search(r'\.(mp4|webm|mkv)(?:\?|$)', url, re.I):
                        self.app.db.execute('INSERT OR REPLACE INTO links VALUES(?,?,?,?)', (url, course['name'], unit, title))
                        self.app.db.execute('INSERT OR REPLACE INTO library_semesters VALUES(?,?)', (url, course.get('semester') or self.app.cfg['semester']))
                        self.app.db.execute('INSERT OR REPLACE INTO library_courses VALUES(?,?)', (url, course['url']))
                        self.app.db.commit()
                        report['links'] += 1
                        continue
                    candidates.append((url, course['name'], unit, title, course.get('semester'), course['url']))
            checked = {r['url']: r['checked'] for r in self.app.db.execute('SELECT url,checked FROM library')}
            # New attachments first; rotate existing checks to avoid starving later courses.
            candidates.sort(key=lambda item: checked.get(item[0], 0))
            # Deduplicate before scheduling so the same attachment is never written twice.
            candidates = list({item[0]: item for item in candidates}.values())
            limit = int(self.app.cfg['max_downloads'])
            report['deferred'] = max(0, len(candidates) - limit)
            selected = candidates[:limit]
            report.update(total=len(selected), discovered=len(candidates), stage='downloading', detail='Downloading or checking attachments from MUJ. Existing files may be unchanged.')
            if on_progress: on_progress(dict(report))
            workers = max(1, min(3, int(self.app.cfg.get('download_workers', 3))))
            if workers == 1 or len(selected) < 2:
                for item in selected:
                    report['active_files'] = [f'{item[1]} / {item[3]}']
                    if on_progress: on_progress(dict(report))
                    try:
                        outcome = self.download(context, *item)
                        report[outcome] = report.get(outcome, 0) + 1
                        row = self.app.db.execute('SELECT * FROM library WHERE url=?', (item[0],)).fetchone()
                        if row and on_download: on_download(dict(row))
                    except StudyError as exc:
                        if 'Session expired' in str(exc): raise
                        report['failed'].append({'title': item[3], 'reason': str(exc)})
                    report['active_files'] = []
                    if on_progress: on_progress(dict(report))
            elif selected:
                self.download_parallel(selected, context.storage_state(), workers, report, on_download, on_progress)
        return report

    def download_parallel(self, selected, storage_state, workers, report, on_download, on_progress):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from copy import deepcopy
        from queue import Queue, Empty
        import threading
        from types import SimpleNamespace
        from .core import App
        from .pipeline import RequestPacer
        from playwright.sync_api import sync_playwright
        queue = Queue()
        for item in selected: queue.put(item)
        lock, stopped = threading.Lock(), threading.Event()
        active_files = {}
        pacer = RequestPacer(self.app.cfg['request_delay'])
        settings = deepcopy(self.app.cfg)
        def consume():
            app = App(self.app.config_path, self.app.data)
            app.cfg = deepcopy(settings)
            lms = LMS(app)
            try:
                # Each thread owns its Playwright runtime, request context and DB.
                # Cookies stay in memory; no additional browser or manual login is needed.
                with sync_playwright() as p:
                    request = p.request.new_context(storage_state=storage_state)
                    try:
                        while not stopped.is_set():
                            try: item = queue.get_nowait()
                            except Empty: return
                            with lock:
                                active_files[item[0]] = f'{item[1]} / {item[3]}'
                                report['active_files'] = list(active_files.values())
                                if on_progress: on_progress(dict(report))
                            try:
                                state = lms.download(SimpleNamespace(request=request), *item, pacer=pacer)
                                row = app.db.execute('SELECT * FROM library WHERE url=?', (item[0],)).fetchone()
                                if row and on_download: on_download(dict(row))
                                with lock:
                                    active_files.pop(item[0], None)
                                    report['active_files'] = list(active_files.values())
                                    report[state] = report.get(state, 0) + 1
                                    if on_progress: on_progress(dict(report))
                            except StudyError as exc:
                                if 'Session expired' in str(exc):
                                    stopped.set()
                                    raise
                                with lock:
                                    active_files.pop(item[0], None)
                                    report['active_files'] = list(active_files.values())
                                    report['failed'].append({'title': item[3], 'reason': str(exc)})
                                    if on_progress: on_progress(dict(report))
                    finally:
                        request.dispose()
            finally:
                app.close()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(consume) for _ in range(workers)]):
                future.result()

    def catalog(self, url, course, unit, title, path, hashed, semester=None, course_url=None):
        self.app.db.execute('INSERT OR REPLACE INTO library VALUES(?,?,?,?,?,?,?,?)', (url, course, unit, title, str(path), Path(path).suffix.lower().lstrip('.'), hashed, time.time()))
        self.app.db.execute('INSERT OR REPLACE INTO library_semesters VALUES(?,?)', (url, semester or self.app.cfg['semester']))
        if course_url: self.app.db.execute('INSERT OR REPLACE INTO library_courses VALUES(?,?)', (url, course_url))
        self.app.db.commit()

    def download(self, context, url, course, unit, title, semester=None, course_url=None, pacer=None):
        if is_lab_subject(course):
            raise StudyError('Lab subjects are excluded from downloads.')
        old = self.app.db.execute('SELECT * FROM files WHERE url=?', (url,)).fetchone()
        headers = {}
        if old and Path(old['path']).exists():
            if old['etag']:
                headers['If-None-Match'] = old['etag']
            if old['modified']:
                headers['If-Modified-Since'] = old['modified']
        for attempt in range(3):
            if not pacer: time.sleep(self.app.cfg['request_delay'])
            response = None
            try:
                # Explicitly validate every redirect before following it.
                target = url
                for _ in range(8):
                    if not self.allowed(target):
                        raise StudyError('Download redirected outside allowed LMS hosts; record it as an external link or configure the trusted host.')
                    if pacer: pacer.wait()
                    response = context.request.get(target, headers=headers, max_redirects=0, timeout=60000)
                    if response.status not in {301, 302, 303, 307, 308}:
                        break
                    location = urljoin(target, response.headers.get('location', ''))
                    response.dispose()
                    response = None
                    if '/login' in location.casefold():
                        raise StudyError('Session expired, please log in again.')
                    target = location
                else:
                    raise StudyError('Too many download redirects.')
                if response.status == 304 and old:
                    self.catalog(url, course, unit, title, old['path'], old['hash'], semester, course_url)
                    return 'unchanged'
                if response.status in {401, 403} or '/login' in response.url.casefold():
                    raise StudyError('Session expired, please log in again.')
                if response.status in {404, 410}:
                    raise StudyError(f'Attachment unavailable (HTTP {response.status}). The teacher may have removed or replaced it; check this item in MUJ.')
                if response.status != 200:
                    raise RuntimeError(f'HTTP {response.status}')
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type:
                    body = response.text()
                    if re.search(r'type=[\"\x27]password|loginform|sign in to your account', body, re.I):
                        raise StudyError('Session expired, please log in again.')
                    self.app.db.execute('INSERT OR REPLACE INTO links VALUES(?,?,?,?)', (url, course, unit, title))
                    self.app.db.execute('INSERT OR REPLACE INTO library_semesters VALUES(?,?)', (url, semester or self.app.cfg['semester']))
                    if course_url: self.app.db.execute('INSERT OR REPLACE INTO library_courses VALUES(?,?)', (url, course_url))
                    self.app.db.commit()
                    return 'linked'
                body = response.body()
                if len(body) > 100 * 1024 * 1024:
                    raise StudyError('File exceeds 100 MB local download limit.')
                hashed = hashlib.sha256(body).hexdigest()
                disposition = response.headers.get('content-disposition', '')
                match = re.search(r'filename\*?=(?:UTF-8\x27\x27)?[\"]?([^\";]+)', disposition, re.I)
                filename = unquote(match.group(1)) if match else Path(urlparse(url).path).name
                filename = safe_name(filename or title)
                if not Path(filename).suffix:
                    extensions = {'application/pdf': '.pdf', 'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'}
                    filename += extensions.get(content_type.split(';')[0], '.bin')
                # URL hash prevents two same-title attachments overwriting one another.
                dest = self.app.data / 'downloads'
                if semester: dest = dest / f'Semester {semester}'
                dest = dest / safe_name(course)
                for segment in unit.split(' / '):
                    dest = dest / safe_name(segment)
                dest = dest / (hashlib.sha256(url.encode()).hexdigest()[:8] + '-' + filename)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not old or hashed != old['hash'] or not dest.exists():
                    tmp = dest.with_suffix(dest.suffix + '.part')
                    tmp.write_bytes(body)
                    tmp.replace(dest)
                self.app.db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)', (url, response.headers.get('etag'), response.headers.get('last-modified'), hashed, str(dest)))
                self.app.db.commit()
                self.catalog(url, course, unit, title, dest, hashed, semester, course_url)
                return 'new' if not old else 'updated' if old['hash'] != hashed else 'unchanged'
            except StudyError:
                raise
            except Exception as exc:
                if attempt == 2:
                    self.app.logger.error('Download failed: %s', type(exc).__name__)
                    code = re.search(r'HTTP \d{3}|ERR_[A-Z_]+|Timeout|timed out', str(exc), re.I)
                    reason = code.group(0) if code else type(exc).__name__
                    raise StudyError(f'Download failed after 3 attempts ({reason}). Other saved files are intact.') from None
                time.sleep(2 ** attempt)
            finally:
                if response is not None:
                    response.dispose()
        raise StudyError('Download failed.')
