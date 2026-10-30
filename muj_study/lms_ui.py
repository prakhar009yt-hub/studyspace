"""Website controls for manual authentication and automatic semester-aware sync."""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from .core import App, StudyError, is_lab_subject
from .jobs import Jobs
from .library import assign_semester, semester_courses, semester_library, semester_notes
from . import ui


def start(app, task):
    try:
        state = Jobs(app).start(task)
        st.session_state['_job_started'] = state['file']
        st.rerun()
    except StudyError as exc:
        st.error(str(exc))


@st.fragment(run_every='3s')
def background_status(config, data):
    app = App(config, data)
    try:
        jobs = Jobs(app)
        state = jobs.latest()
        active = jobs.active(state)
        from .progress_ui import render_status
        render_status(app, active or state)
        if active:
            # Refresh read-only dashboards as analyses arrive, without interrupting
            # key-entry/preferences forms or the note the student is studying.
            if st.session_state.get('navigation') in {'Home', 'Topics', 'Progress'}:
                signature = tuple(app.db.execute('SELECT COUNT(*),MAX(n.rowid) FROM notes n JOIN note_semesters s ON s.note=n.id WHERE s.semester=?', (app.cfg['semester'],)).fetchone())
                prior = st.session_state.get('_analysis_signature')
                if prior is None:
                    st.session_state['_analysis_signature'] = signature
                elif prior != signature and time.time() - st.session_state.get('_analysis_refreshed', 0) >= 10:
                    st.session_state['_analysis_signature'] = signature
                    st.session_state['_analysis_refreshed'] = time.time()
                    st.rerun()
            return
        if state and state['file'] != st.session_state.get('_job_reported'):
            st.session_state['_job_reported'] = state['file']
            st.rerun()
        blocked = (state or {}).get('analysis_progress', {}).get('blocked_error') or ''
        if app.cfg.get('lms_auto_analyze', True) and 'daily budget reached' in blocked:
            from .agents import AgentPool
            if AgentPool(app).available():
                jobs.start('analyze')
                st.rerun()
        if state and state['status'] == 'failed':
            if st.button('Retry interrupted task', key='retry-background-job'):
                start(app, state['task'] if state['task'] in {'sync', 'analyze', 'discover'} else 'sync')
            return  # An expired session or denied API must not cause a retry loop.
        if not app.session.exists() or not app.cfg.get('lms_auto_sync', True): return
        last = app.cached(f'lms-last-sync:{app.cfg["semester"]}')
        interval = max(5, int(app.cfg.get('lms_sync_minutes', 15))) * 60
        report = (last or {}).get('report', {})
        if report.get('deferred', 0) and report.get('new', 0): interval = 30
        if last is None or time.time() - last['at'] >= interval:
            jobs.start('sync')
            st.rerun()
    finally:
        app.close()


def render(app):
    ui.heading('YOUR CAMPUS, CONNECTED', 'Your subjects. Already organized.', f'Fetch all subjects and notes for Semester {app.cfg["semester"]}. Other semesters stay separate until you open them.')
    jobs = Jobs(app)
    busy = bool(jobs.active())
    hosted = os.environ.get('MUJ_DEPLOYED') == '1'
    if hosted:
        st.info('Hosted mode: imports, analysis, videos and planning work here. Manual MUJ sign-in needs the desktop app. LMS fetching requires a valid session provisioned privately by the server owner; see docs/DEPLOYMENT.md.')
    controls = st.columns(3)
    if controls[0].button('Connect MUJ LMS', type='primary', disabled=busy or hosted, width='stretch'):
        start(app, 'login')
    if controls[1].button('Fetch this semester', disabled=busy or not app.session.exists(), width='stretch'):
        start(app, 'sync')
    if controls[2].button('Discover subjects', disabled=busy or not app.session.exists(), width='stretch'):
        start(app, 'discover')
    st.caption('Sign in yourself in the browser window, including SSO/OTP. Successful login is detected automatically, then subject discovery and syncing begin. Your password stays with MUJ.')
    if not app.session.exists():
        st.info('Connect MUJ LMS once to start automatic fetching. You don’t need to upload your notes.')
    else:
        st.caption('A login session is saved on this computer. Each fetch checks that it is still valid.')
    with st.form('lms-automatic-settings'):
        automatic = st.checkbox('Automatically sync the selected semester while this website is open', value=app.cfg.get('lms_auto_sync', True))
        analyze = st.checkbox('Analyze fetched notes with Gemini when a key is configured', value=app.cfg.get('lms_auto_analyze', True))
        minutes = st.selectbox('Check for new notes every', [5, 15, 30, 60], index=[5, 15, 30, 60].index(app.cfg.get('lms_sync_minutes', 15)) if app.cfg.get('lms_sync_minutes', 15) in [5, 15, 30, 60] else 1, format_func=lambda n: f'{n} minutes')
        if st.form_submit_button('Save sync preferences'):
            app.cfg.update(lms_auto_sync=automatic, lms_auto_analyze=analyze, lms_sync_minutes=minutes)
            app.save_config(); st.success('Sync preferences saved.')
    current = semester_courses(app)
    cols = st.columns(3)
    cols[0].metric('Subjects in this semester', len(current))
    cols[1].metric('Downloaded files', len(semester_library(app)))
    cols[2].metric('Analyzed notes', len(semester_notes(app)))
    if current:
        st.subheader(f'Semester {app.cfg["semester"]} subjects')
        for course in current:
            st.write('• ' + course['name'] + (' · Downloads and analysis excluded' if is_lab_subject(course['name']) else ''))
    with st.expander('Subject semesters · organize detected subjects', expanded=not current):
        st.caption('We use explicit semester labels from MUJ. Subjects without a clear semester stay unassigned and are not downloaded until you place them. Your assignments are remembered.')
        courses = [dict(r) for r in app.db.execute('SELECT * FROM courses ORDER BY semester,name') if not is_lab_subject(r['name'])]
        if not courses:
            st.write('Your subjects will appear here after you connect to MUJ.')
        else:
            labels = {c['url']: f'{c["name"]} · {"Semester " + str(c["semester"]) if c["semester"] else "Unassigned"}' for c in courses}
            with st.form('semester-assignments'):
                selected = st.multiselect('Subjects to assign', list(labels), format_func=lambda url: labels[url])
                semester = st.selectbox('Place in semester', range(1, 13), index=int(app.cfg['semester']) - 1)
                if st.form_submit_button('Save subject semesters', disabled=busy):
                    assign_semester(app, selected, semester)
                    app.cache(f'lms-last-sync:{semester}', {'at': 0, 'report': {}}, 365)
                    st.rerun()
            st.dataframe([{'Subject': c['name'], 'Semester': str(c['semester']) if c['semester'] else 'Unassigned'} for c in courses], width='stretch', hide_index=True)
    last = app.cached(f'lms-last-sync:{app.cfg["semester"]}')
    if last:
        st.subheader('Latest fetch')
        st.caption(datetime.fromtimestamp(last['at']).strftime('%d %b %Y, %H:%M') if last['at'] else 'Ready to fetch')
        report = last['report']
        if report.get('skipped_labs'): st.caption('Lab subjects skipped: ' + ', '.join(report['skipped_labs']))
        if report.get('message'): st.info(report['message'])
        else:
            st.write(f'{report.get("new", 0)} new · {report.get("updated", 0)} updated · {report.get("unchanged", 0)} unchanged · {len(report.get("failed", []))} issues')
        if report.get('deferred'): st.caption(f'{report["deferred"]} remaining checks. New files are fetched in paced batches; automatic sync continues while this page is open.')
        if report.get('analysis_message'): st.info(report['analysis_message'])
        for failure in report.get('failed', []): st.warning(failure.get('title', failure.get('course', 'Note')) + ': ' + failure['reason'])
        errors = [n for n in report.get('analysis', []) if n.get('error')]
        if errors: st.warning(f'{len(errors)} notes could not be analyzed. Their downloaded files are still available in Notes.')
    with st.expander('Disconnect this computer'):
        st.caption('Deletes the saved LMS session. Your downloaded notes remain available.')
        if st.button('Disconnect MUJ', disabled=busy):
            from .lms import LMS
            LMS(app).protect_session()
            app.session.unlink(missing_ok=True)
            st.rerun()


def render_library(app, course='All courses'):
    files = [f for f in semester_library(app) if course == 'All courses' or f['course'] == course]
    links = [dict(r) for r in app.db.execute('SELECT l.* FROM links l JOIN library_semesters s ON s.url=l.url WHERE s.semester=?', (app.cfg['semester'],)) if not is_lab_subject(r['course']) and (course == 'All courses' or r['course'] == course)]
    if not files and not links: return
    analyzed = {n['path']: n for n in semester_notes(app)}
    with st.expander(f'Downloaded from MUJ · {len(files)} files', expanded=not analyzed):
        st.caption('Organized automatically as Semester → Subject → Module → File. Files are available before Gemini analysis.')
        if st.button('Analyze downloaded notes', disabled=bool(Jobs(app).active())):
            start(app, 'analyze')
        search = st.text_input('Find a downloaded file', placeholder='Search title, subject or module', key='library-file-search')
        matches = [f for f in files if search.casefold() in (f['title'] + ' ' + f['course'] + ' ' + f['unit']).casefold()]
        page_count = max(1, (len(matches) + 11) // 12)
        page = st.selectbox('File page', range(1, page_count + 1), key='library-file-page') if page_count > 1 else 1
        visible = matches[(page - 1) * 12:page * 12]
        st.caption(f'{len(matches)} matching files · showing {(page - 1) * 12 + 1 if matches else 0}–{min(page * 12, len(matches))}. File contents load only when you click download.')
        groups = {}
        for item in visible: groups.setdefault((item['course'], item['unit']), []).append(item)
        for (subject, unit), items in groups.items():
            st.markdown(f'**{subject} / {unit}**')
            for item in items:
                note = analyzed.get(item['path'])
                state = 'Lab subject · analysis excluded' if is_lab_subject(subject) else 'Analyzed' if note and note['hash'] == item['hash'] else 'Ready for analysis'
                st.write(f'{item["title"]} · {item["kind"].upper()} · {state}')
                path = Path(item['path'])
                if path.exists():
                    st.download_button('Open / download file', data=path.read_bytes, file_name=path.name, key='download-' + item['url'], on_click='ignore')
        if links:
            st.markdown('**Links and videos posted by your teachers**')
            from urllib.parse import urlparse
            for item in links:
                if urlparse(item['url']).scheme in {'https', 'http'}:
                    st.link_button(f'{item["course"]} / {item["unit"]} · {item["title"]}', item['url'])
