"""Private subprocess entry point for website LMS tasks."""
import argparse
import json
import time
import threading
from pathlib import Path

from .core import App, StudyError, private_write, is_lab_subject
from .library import analyze_catalog, semester_courses
from .lms import LMS
from .agents import AgentPool


def execute(app, task, semester, update):
    lms = LMS(app)
    lms.on_status = lambda message: update({'stage': 'connecting', 'message': message})
    if task == 'login':
        update('Sign in manually in the MUJ browser window. Complete SSO/OTP; this app never enters your password.')
        lms.login_from_web()
        task = 'sync'
    if task in {'discover', 'sync'}:
        update('Discovering subjects and semester information from MUJ…')
        lms.courses(refresh=True) if task == 'discover' else lms.courses()
        unassigned = app.db.execute('SELECT COUNT(*) FROM courses WHERE semester IS NULL').fetchone()[0]
        courses = semester_courses(app, semester, include_labs=True)
        if task == 'discover': return {'subjects': len(courses), 'unassigned': unassigned}
        skipped_labs = [c['name'] for c in courses if is_lab_subject(c['name'])]
        courses = [c for c in courses if not is_lab_subject(c['name'])]
        if not courses:
            message = 'Lab subjects are excluded from downloads and analysis.' if skipped_labs else f'No subjects are assigned to Semester {semester}. Assign unidentified subjects in LMS → Subject semesters.'
            report = {'subjects': 0, 'unassigned': unassigned, 'skipped_labs': skipped_labs, 'message': message}
            app.cache(f'lms-last-sync:{semester}', {'at': time.time(), 'report': report}, 365)
            return report
        # Only this semester is eligible for content reads and downloads.
        app.cfg['tracked_courses'] = [{'url': c['url'], 'name': c['name'], 'semester': semester} for c in courses]
        app.cfg['semester'] = semester
        update(f'Fetching notes for {len(courses)} subjects in Semester {semester}…')
        pipeline = None
        analysis_message = None
        if app.cfg.get('lms_auto_analyze', True):
            agents = AgentPool(app)
            if not agents.agents:
                analysis_message = 'Notes are saved and categorized. Add a Gemini key in Settings for summaries and topics.'
            else:
                if not agents.remaining():
                    analysis_message = 'Local gemini_calls daily budget reached; analysis paused until Pacific midnight. Downloads continue and saved analyses remain available.'
                    update({'analysis_progress': {'total': 0, 'processed': 0, 'succeeded': 0, 'failed': 0, 'deferred': 0,
                            'active': [], 'errors': [analysis_message], 'blocked_error': analysis_message}})
                else:
                    from .pipeline import AnalysisPipeline
                    pipeline = AnalysisPipeline(app, update)
                    pipeline.seed(app)
        def progress(report):
            processed = report['new'] + report['updated'] + report['unchanged']
            update({'stage': report.get('stage', 'downloading'),
                    'message': report.get('detail', 'Fetching notes from MUJ.'),
                    'download_progress': {'total': report.get('total'), 'discovered': report.get('discovered'),
                        'processed': processed + len(report['failed']) + report.get('linked', 0), 'downloaded': report['new'] + report['updated'],
                        'linked': report.get('linked', 0),
                        'unchanged': report['unchanged'], 'failed': len(report['failed']),
                        'active': report.get('active_files', []),
                        'deferred': report.get('deferred', 0), 'errors': [f['reason'] for f in report['failed'][-5:]]}})
        try:
            if pipeline:
                report = lms.sync(on_download=pipeline.submit, on_progress=progress)
            else:
                report = lms.sync(on_progress=progress)
        except BaseException:
            if pipeline: pipeline.finish()
            raise
        report.update(subjects=len(courses), unassigned=unassigned, skipped_labs=skipped_labs)
        if analysis_message: report['analysis_message'] = analysis_message
        if pipeline:
            update({'stage': 'analyzing', 'message': 'Downloads finished. Waiting for remaining document processing and Gemini responses.'})
            report['analysis'] = pipeline.finish()
        app.cache(f'lms-last-sync:{semester}', {'at': time.time(), 'report': report}, 365)
        return report
    if task == 'analyze':
        app.cfg['semester'] = semester
        agents = AgentPool(app)
        if not agents.agents: raise StudyError('Add a Gemini key or analysis agent in Settings.')
        if not agents.remaining():
            raise StudyError('Local gemini_calls daily budget reached; analysis paused. Saved files are intact. Retry after Pacific midnight or review the Gemini daily budget in Settings.')
        update({'stage': 'analyzing', 'message': 'Preparing documents and waiting for Gemini to analyze downloaded notes…'})
        from .pipeline import AnalysisPipeline
        pipeline = AnalysisPipeline(app, update)
        pipeline.seed(app)
        return {'analysis': pipeline.finish()}
    raise StudyError('Unknown background task.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('job', type=Path); parser.add_argument('--config'); parser.add_argument('--data')
    args = parser.parse_args()
    app = App(args.config, args.data)
    state = json.loads(args.job.read_text(encoding='utf-8'))
    state_lock = threading.Lock()
    def update(message):
        with state_lock:
            state.update(status='running', updated=time.time())
            if isinstance(message, dict):
                download = message.get('download_progress')
                if download and download.get('total') is not None:
                    download['started_at'] = state.get('download_progress', {}).get('started_at', time.time())
                    download['measured_at'] = time.time()
                if message.get('stage') and message['stage'] != state.get('stage'):
                    state['stage_started'] = time.time()
                state.update(message)
            else: state.update(message=message)
            private_write(args.job, state)
    try:
        if state['task'] == 'videos':
            from .youtube import YouTube
            from .library import semester_notes
            app.cfg['semester'] = state['semester']
            if state['note_id'] not in {n['id'] for n in semester_notes(app)}:
                raise StudyError('This note belongs to another semester. Select the correct semester first.')
            update('Finding videos for this topic. Your notes continue processing in the background…')
            result = YouTube(app).note_topic(state['note_id'], int(state['topic_index']), bool(state.get('refresh')), bool(state.get('playlists')))
        else:
            result = execute(app, state['task'], state['semester'], update)
        state.update(status='complete', message='LMS task complete.', result=result, finished=time.time())
    except Exception as exc:
        app.logger.error('Background %s failed: %s', state['task'], type(exc).__name__)
        from playwright.sync_api import Error as BrowserError
        if isinstance(exc, BrowserError):
            import re
            # A browser's first error line identifies navigation/installation failures.
            # Remove URLs entirely so SSO query parameters cannot enter job reports.
            reason = re.sub(r'https?://\S+', '[LMS page]', str(exc).splitlines()[0])[:500]
            message = 'Browser connection failed: ' + reason
        else:
            message = str(exc) if isinstance(exc, StudyError) else f'LMS operation failed ({type(exc).__name__}). Check the connection and try again.'
        state.update(status='failed', message=message, finished=time.time())
    finally:
        private_write(args.job, state)
        (args.job.parent / 'active.json').unlink(missing_ok=True)
        app.close()


if __name__ == '__main__': main()
