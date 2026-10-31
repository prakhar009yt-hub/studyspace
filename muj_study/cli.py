from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from .core import App, ROOT, StudyError, private_write


def parser():
    p = argparse.ArgumentParser(description='MUJ LMS + Gemini personal study assistant')
    p.add_argument('--config', type=Path)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('setup', help='Create config and privately save API keys')
    sub.add_parser('doctor', help='Check configuration without printing secrets')
    sub.add_parser('login', help='Open LMS for manual login')
    sub.add_parser('logout', help='Delete saved LMS session')
    sub.add_parser('courses', help='Discover enrolled courses')
    t = sub.add_parser('track'); t.add_argument('url'); t.add_argument('name')
    t = sub.add_parser('untrack'); t.add_argument('url')
    s = sub.add_parser('sync'); s.add_argument('--course')
    a = sub.add_parser('analyze'); a.add_argument('file', nargs='?', type=Path); a.add_argument('--course', default='Local'); a.add_argument('--unit', default='Imported'); a.add_argument('--refresh', action='store_true')
    sub.add_parser('notes')
    r = sub.add_parser('recommend'); r.add_argument('note_id'); r.add_argument('--refresh', action='store_true'); r.add_argument('--playlists', action='store_true')
    h = sub.add_parser('history'); h.add_argument('--note')
    f = sub.add_parser('feedback'); f.add_argument('video_id'); f.add_argument('--channel', default=''); f.add_argument('--status', choices=['watched', 'skipped', 'blocked', 'unwatched'], default=''); f.add_argument('--rating', choices=['helpful', 'okay', 'bad'], default=''); f.add_argument('--reason', default='')
    t = sub.add_parser('topic'); t.add_argument('name'); t.add_argument('--weak', choices=['yes', 'no']); t.add_argument('--covered', choices=['yes', 'no'])
    b = sub.add_parser('block-channel'); b.add_argument('channel')
    for cmd in ['aids', 'export']:
        s = sub.add_parser(cmd); s.add_argument('note_id')
    exp_study = sub.add_parser('export-study', help='Export workspace to browser study JSON (studyspace.study.v1)')
    exp_study.add_argument('--semester', type=int)
    exp_study.add_argument('--output', type=Path)
    q = sub.add_parser('ask'); q.add_argument('note_id'); q.add_argument('question')
    g = sub.add_parser('gaps'); g.add_argument('course'); g.add_argument('syllabus', type=Path)
    v = sub.add_parser('verify'); v.add_argument('note_id'); v.add_argument('topic'); v.add_argument('video_id'); v.add_argument('transcript', type=Path)
    e = sub.add_parser('exam'); e.add_argument('date', help='YYYY-MM-DD or off')
    sub.add_parser('progress'); sub.add_parser('quota'); sub.add_parser('retry-queue')
    n = sub.add_parser('notification-setup', help='Configure Telegram for your own chat')
    n.add_argument('--chat-id')
    run = sub.add_parser('run', help='Sync, analyze, recommend and export'); run.add_argument('--course'); run.add_argument('--notify', action='store_true'); run.add_argument('--no-videos', action='store_true')
    watch = sub.add_parser('watch', help='Run daily while this terminal stays open'); watch.add_argument('--at', default='08:00'); watch.add_argument('--notify', action='store_true')
    sub.add_parser('web', help='Launch the local dashboard')
    return p


def execute(app, args):
    from .gemini import Gemini
    from .lms import LMS
    from .workflow import analyze_downloads, export_plan, progress, run_pipeline, send_digest
    from .youtube import YouTube
    command = args.command
    if command == 'setup':
        if not app.config_path.exists():
            app.save_config()
        LMS(app).protect_session()
        keys = json.loads(app.secrets.read_text()) if app.secrets.exists() else {}
        for key in ['GEMINI_API_KEY', 'YOUTUBE_API_KEY']:
            value = getpass.getpass(f'{key} (hidden; Enter keeps existing): ').strip()
            if value:
                keys[key] = value
        private_write(app.secrets, keys)
        return {'config': str(app.config_path), 'private_keys': str(app.secrets), 'next': 'python -m muj_study doctor'}
    if command == 'doctor':
        import importlib.util
        return {'config': str(app.config_path), 'config_exists': app.config_path.exists(), 'private_keys_file_exists': app.secrets.exists(),
                'gemini_key_set': bool(os.environ.get('GEMINI_API_KEY') or (json.loads(app.secrets.read_text()).get('GEMINI_API_KEY') if app.secrets.exists() else None)),
                'youtube_key_set': bool(os.environ.get('YOUTUBE_API_KEY') or (json.loads(app.secrets.read_text()).get('YOUTUBE_API_KEY') if app.secrets.exists() else None)),
                'session_exists': app.session.exists(), 'session_path': str(app.session), 'lms_adapter': app.cfg['lms'].get('adapter'),
                'dependencies': {m: bool(importlib.util.find_spec(m)) for m in ['google.genai', 'playwright', 'pypdf', 'streamlit']},
                'note': 'Checks presence only; use analyze and courses to verify live API/LMS access.'}
    if command == 'login':
        LMS(app).login(); return 'Session saved outside the project.'
    if command == 'logout':
        LMS(app).protect_session(); app.session.unlink(missing_ok=True); return 'Saved session deleted.'
    if command == 'courses':
        return LMS(app).courses()
    if command in {'track', 'untrack'}:
        if not LMS(app).allowed(args.url):
            raise StudyError('Course URL must be on the configured LMS host.')
        tracked = [c for c in app.cfg.get('tracked_courses', []) if c['url'] != args.url]
        if command == 'track': tracked.append({'url': args.url, 'name': args.name})
        app.cfg['tracked_courses'] = tracked; app.save_config(); return tracked
    if command == 'sync':
        return LMS(app).sync(args.course)
    if command == 'analyze':
        return Gemini(app).analyze(args.file, args.course, args.unit, args.refresh) if args.file else analyze_downloads(app, None if args.course == 'Local' else args.course)
    if command == 'notes':
        return [dict(r) for r in app.db.execute('SELECT id,course,unit,path FROM notes ORDER BY course,unit')]
    if command == 'recommend':
        return YouTube(app).note(args.note_id, args.refresh, args.playlists)
    if command == 'history':
        rows = app.db.execute('SELECT * FROM history WHERE note=? ORDER BY id DESC LIMIT 20', (args.note,)) if args.note else app.db.execute('SELECT * FROM history ORDER BY id DESC LIMIT 20')
        return [{**dict(r), 'result': json.loads(r['result'])} for r in rows]
    if command == 'feedback':
        if not args.channel:
            # Recover channel from stored recommendations so one-ID feedback affects channel ranking.
            for row in app.db.execute('SELECT result FROM history ORDER BY id DESC'):
                match = next((v for t in json.loads(row['result']) for v in t['videos'] if v['id'] == args.video_id), None)
                if match:
                    args.channel = match['channelId']; break
        app.feedback(args.video_id, args.channel, args.status, args.rating, args.reason); return 'Feedback saved.'
    if command == 'block-channel':
        app.cfg['blocked_channels'] = list(set(app.cfg['blocked_channels'] + [args.channel])); app.save_config(); return 'Channel blocked.'
    if command == 'topic':
        app.topic(args.name, None if args.weak is None else args.weak == 'yes', None if args.covered is None else args.covered == 'yes'); return 'Topic progress saved.'
    if command == 'aids':
        result = Gemini(app).aids(args.note_id); app.cache('aids:' + args.note_id, result, 365); return result
    if command == 'ask':
        return Gemini(app).ask(args.note_id, args.question)
    if command == 'gaps':
        return Gemini(app).gaps(args.course, args.syllabus)
    if command == 'verify':
        note = Gemini(app).note(args.note_id)
        topic = next((t for t in json.loads(note['analysis'])['topics'] if t['name'].casefold() == args.topic.casefold()), None)
        if not topic:
            raise StudyError('Topic not found in this note. Use its exact topic name.')
        result = Gemini(app).verify(topic, args.transcript)
        app.cache('verification:' + args.video_id + ':' + args.topic.casefold(), result, 365)
        return {**result, 'url': f'https://www.youtube.com/watch?v={args.video_id}&t={result["start_seconds"]}s'}
    if command == 'exam':
        if args.date != 'off': datetime.strptime(args.date, '%Y-%m-%d')
        app.cfg['exam_date'] = None if args.date == 'off' else args.date; app.save_config(); return progress(app)
    if command == 'progress': return progress(app)
    if command == 'quota':
        return {'local_requests': [dict(r) for r in app.db.execute('SELECT * FROM quota ORDER BY day DESC')], 'queued': app.db.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 'note': 'Local request counts only; Cloud Console is authoritative. Reset: Pacific midnight. Search and metadata budgets are separate.'}
    if command == 'retry-queue': return {'completed': YouTube(app).drain_queue()}
    if command == 'export': return str(export_plan(app, args.note_id))
    if command == 'export-study':
        from .study_export import export_study_to_file
        return str(export_study_to_file(app, semester=args.semester, destination=args.output))
    if command == 'notification-setup':
        keys = json.loads(app.secrets.read_text()) if app.secrets.exists() else {}
        keys['TELEGRAM_BOT_TOKEN'] = getpass.getpass('Telegram bot token (hidden): ').strip()
        keys['TELEGRAM_CHAT_ID'] = args.chat_id or input('Your own Telegram chat ID: ').strip()
        private_write(app.secrets, keys); return 'Telegram configured; delivery requires run --notify or watch --notify.'
    if command == 'run':
        result = run_pipeline(app, args.course, not args.no_videos)
        if args.notify: result['delivery'] = send_digest(app, result)
        return result
    if command == 'watch':
        datetime.strptime(args.at, '%H:%M')
        print(f'Daily checks at {args.at} in this computer’s local timezone. Keep terminal open; Ctrl+C stops.')
        last_day = None
        while True:
            now = datetime.now()
            if now.strftime('%H:%M') >= args.at and last_day != now.date():
                last_day = now.date()
                try:
                    result = run_pipeline(app)
                    print(json.dumps(result, ensure_ascii=False))
                    if args.notify: print(send_digest(app, result))
                except StudyError as exc:
                    print(f'Check failed: {exc}', file=sys.stderr)
            time.sleep(20)
    if command == 'web':
        import subprocess
        # Bind to loopback; the app exposes private notes and uses server-side keys.
        env = {**os.environ, 'MUJ_CONFIG': str(app.config_path)}
        return subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'dashboard.py'), '--server.address', '127.0.0.1'], env=env)


def main():
    args = parser().parse_args()
    app = None
    try:
        app = App(args.config)
        value = execute(app, args)
        if value is not None: print(json.dumps(value, ensure_ascii=False, indent=2))
    except (StudyError, FileNotFoundError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr); return 1
    except KeyboardInterrupt:
        print('Stopped.'); return 130
    except Exception as exc:
        print(f'Error: {type(exc).__name__}. Check configuration and dependencies; see data/activity.log.', file=sys.stderr); return 1
    finally:
        if app: app.close()
    return 0
