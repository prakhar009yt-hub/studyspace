"""Semester-aware subject and local-note catalog."""
import json
from pathlib import Path

from .gemini import Gemini
from .core import is_lab_subject


def semester_notes(app, include_labs=False):
    return [dict(r) for r in app.db.execute('SELECT n.* FROM notes n LEFT JOIN note_semesters s ON s.note=n.id WHERE COALESCE(s.semester,?)=? ORDER BY n.course,n.unit', (app.cfg['semester'], app.cfg['semester'])) if include_labs or not is_lab_subject(r['course'])]


def semester_courses(app, semester=None, include_labs=False):
    return [dict(r) for r in app.db.execute('SELECT * FROM courses WHERE semester=? ORDER BY name', (semester or app.cfg['semester'],)) if include_labs or not is_lab_subject(r['name'])]


def semester_library(app, include_labs=False):
    return [dict(r) for r in app.db.execute('SELECT l.* FROM library l JOIN library_semesters s ON s.url=l.url WHERE s.semester=? ORDER BY l.course,l.unit,l.title', (app.cfg['semester'],)) if include_labs or not is_lab_subject(r['course'])]


def semester_note_versions(app):
    """Small progress snapshot; avoid loading full analyses on every timer tick."""
    return {(r['path'], r['hash']) for r in app.db.execute(
        "SELECT n.path,n.hash,n.course FROM notes n LEFT JOIN note_semesters s ON s.note=n.id WHERE COALESCE(s.semester,?)=? AND json_array_length(n.analysis,'$.topics')>0",
        (app.cfg['semester'], app.cfg['semester'])) if not is_lab_subject(r['course'])}


def analyze_catalog(app, course=None):
    results = []
    for item in semester_library(app):
        if is_lab_subject(item['course']): continue
        if course and item['course'] != course: continue
        if Path(item['path']).suffix.lower() not in {'.pdf', '.pptx', '.docx', '.txt', '.md'}: continue
        try:
            result = Gemini(app).analyze(item['path'], item['course'], item['unit'])
            results.append({'path': item['path'], **result})
        except Exception as exc:
            from .core import StudyError
            results.append({'path': item['path'], 'error': str(exc) if isinstance(exc, StudyError) else type(exc).__name__})
    return results


def assign_semester(app, urls, semester):
    if not 1 <= int(semester) <= 12: raise ValueError('Semester must be between 1 and 12.')
    for url in urls:
        app.db.execute('UPDATE courses SET semester=? WHERE url=?', (semester, url))
        # Move visibility with the course without deleting files or analyses.
        paths = [r['path'] for r in app.db.execute('SELECT l.path FROM library l JOIN library_courses c ON c.url=l.url WHERE c.course_url=?', (url,))]
        app.db.execute('UPDATE library_semesters SET semester=? WHERE url IN (SELECT url FROM library_courses WHERE course_url=?)', (semester, url))
        for path in paths:
            app.db.execute('UPDATE library_semesters SET semester=? WHERE url IN (SELECT url FROM library WHERE path=?)', (semester, path))
            app.db.execute('INSERT OR REPLACE INTO note_semesters SELECT id,? FROM notes WHERE path=?', (semester, path))
    app.db.commit()
