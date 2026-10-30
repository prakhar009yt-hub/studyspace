from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .core import StudyError, safe_name, is_lab_subject
from .gemini import Gemini
from .lms import LMS
from .youtube import YouTube


def analyze_downloads(app, course=None):
    from .library import analyze_catalog
    results = analyze_catalog(app, course)
    registered = {r['path'] for r in app.db.execute('SELECT path FROM library')}
    for path in (app.data / 'downloads').rglob('*'):
        if not path.is_file() or path.suffix.lower() not in {'.pdf', '.pptx', '.docx', '.txt', '.md'}:
            continue
        if str(path.resolve()) in registered: continue
        relative = path.relative_to(app.data / 'downloads')
        name = relative.parts[0]
        if name.startswith('Semester ') and len(relative.parts) > 2: name = relative.parts[1]
        if is_lab_subject(name): continue
        if course and course.casefold() not in name.casefold():
            continue
        try:
            analysis = Gemini(app).analyze(path, name, ' / '.join(relative.parts[1:-1]))
            results.append({'path': str(path), **analysis})
        except Exception as exc:
            results.append({'path': str(path), 'error': str(exc) if isinstance(exc, StudyError) else type(exc).__name__})
    return results


def progress(app):
    from .library import semester_notes, semester_courses, semester_library
    states = {r['key']: dict(r) for r in app.db.execute('SELECT * FROM topics')}
    courses = {c['name']: {} for c in semester_courses(app)}
    notes = semester_notes(app)
    downloads = semester_library(app)
    for row in notes:
        entry = courses.setdefault(row['course'], {})
        for topic in json.loads(row['analysis'])['topics']:
            key = topic['name'].casefold()
            state = states.get(key, {})
            entry[key] = {'name': topic['name'], 'weak': bool(state.get('weak')), 'covered': bool(state.get('covered')), 'last_reviewed': state.get('reviewed', 0)}
    exam = app.cfg.get('exam_date')
    for item in downloads: courses.setdefault(item['course'], {})
    counts = {}
    for course in courses:
        course_files = [f for f in downloads if f['course'] == course]
        analyzed = [n for n in notes if n['course'] == course]
        versions = {n['path']: n['hash'] for n in analyzed}
        pending = sum(versions.get(f['path']) != f['hash'] for f in course_files)
        links = app.db.execute('SELECT COUNT(*) FROM links l JOIN library_semesters s ON s.url=l.url WHERE s.semester=? AND l.course=?', (app.cfg['semester'], course)).fetchone()[0]
        status = 'Analysis pending' if pending else 'Analyzed' if analyzed else 'Links available' if links else 'No downloaded notes yet'
        if is_lab_subject(course):
            pending = 0
            status = 'Lab subject — downloads and analysis excluded'
        counts[course] = {'downloaded': len(course_files), 'analyzed': len(analyzed), 'pending': pending, 'links': links, 'status': status}
    return {'courses': {c: {'total': len(ts), 'covered': sum(t['covered'] for t in ts.values()), 'topics': list(ts.values()), **counts[c]} for c, ts in courses.items()},
            'exam_date': exam, 'days_to_exam': (date.fromisoformat(exam) - date.today()).days if exam else None}


def export_plan(app, note_id, results=None):
    note = Gemini(app).note(note_id)
    if results is None:
        row = app.db.execute('SELECT result FROM history WHERE note=? ORDER BY id DESC LIMIT 1', (note_id,)).fetchone()
        results = json.loads(row['result']) if row else []
    yt = YouTube(app)
    analysis = json.loads(note['analysis'])
    lines = [f'# {note["course"]} — {note["unit"]}', '', analysis['summary'], '']
    minutes = 0
    for topic in results:
        lines += [f'## {topic["topic"]}', '']
        if topic.get('no_strong_match'):
            lines += ['No strong match found; inspect these candidates before studying.', '']
        for video in topic['videos']:
            if not yt.allowed(video):
                continue
            minutes += video['duration_seconds'] / 60
            lines += [f'- [{video["title"]}]({video["url"]}) — {video["channelTitle"]}, {video["duration_seconds"] // 60} min, {video["role"]}. {video["reason"]} ({video.get("verification", "metadata only")})']
        lines += ['']
    lines += [f'Estimated watch time: {round(minutes)} minutes.', '', 'Personal study only. Generated explanations and metadata-based estimates may contain errors.']
    dest = app.data / 'exports' / f'{safe_name(note["course"])}-{note_id}.md'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('\n'.join(lines), encoding='utf-8')
    return dest


def run_pipeline(app, course=None, recommend=True):
    sync_report = LMS(app).sync(course)
    # Retry requests deferred by prior budget failures before today's new work.
    completed = YouTube(app).drain_queue() if recommend else 0
    report = {'sync': sync_report, 'notes': [], 'recommendations': {}, 'errors': [], 'queued_completed': completed}
    report['notes'] = analyze_downloads(app, course)
    if recommend:
        for note in report['notes']:
            if note.get('error'):
                continue
            previous = app.db.execute('SELECT result FROM history WHERE note=? ORDER BY id DESC LIMIT 1', (note['id'],)).fetchone()
            if note.get('reused') and previous and all(t.get('videos') for t in json.loads(previous['result'])):
                continue
            try:
                report['recommendations'][note['id']] = YouTube(app).note(note['id'])
                export_plan(app, note['id'], report['recommendations'][note['id']])
            except StudyError as exc:
                report['errors'].append(str(exc))
    return report


def send_digest(app, report):
    """Only called by explicit --notify flag; sends study metadata to user's own destination."""
    import httpx
    summary = [f'MUJ study digest: {report["sync"]["new"]} new, {report["sync"]["updated"]} updated files.']
    for failure in report['sync'].get('failed', []):
        summary.append('Sync issue: ' + failure.get('reason', 'Unknown download error'))
    for note in report.get('notes', []):
        if note.get('error') or note.get('reused'):
            continue
        summary.append(note['summary'][:300])
        for topic in report.get('recommendations', {}).get(note['id'], []):
            summary.append(topic['topic'])
            summary.extend(v['url'] for v in topic['videos'])
    text = '\n'.join(summary)
    # No periodic empty messages.
    if not report['sync']['new'] and not report['sync']['updated'] and not report['sync']['failed']:
        return 'No changes; no digest sent.'
    token = app.key('TELEGRAM_BOT_TOKEN')
    chat = app.key('TELEGRAM_CHAT_ID')
    with httpx.Client(timeout=30) as client:
        for start in range(0, len(text), 3900):
            response = client.post(f'https://api.telegram.org/bot{token}/sendMessage', json={'chat_id': chat, 'text': text[start:start + 3900]})
            if response.status_code != 200:
                raise StudyError('Telegram delivery failed. Check bot token and your own chat ID.')
    return 'Digest sent.'
