"""Export local SQLite notes and study progress to the portable browser study format (studyspace.study.v1)."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .core import is_lab_subject, safe_name


FORMAT = 'studyspace.study.v1'
_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')
_HEX64_RE = re.compile(r'^[a-f0-9]{64}$')


def build_study_export(app, semester=None):
    """Build a validated studyspace.study.v1 dictionary from SQLite."""
    target_semester = int(semester or app.cfg.get('semester', 3))
    
    # 1. Fetch relevant courses
    course_rows = app.db.execute('''
        SELECT url, name, course_id, semester
        FROM courses
        WHERE semester = ? OR semester IS NULL
    ''', (target_semester,)).fetchall()
    
    courses_map = {}
    for r in course_rows:
        name = (r['name'] or '').strip()
        if name and not is_lab_subject(name):
            cid = str(r['course_id'] or r['url'] or name)[:100]
            courses_map[name] = {
                'id': cid,
                'name': name[:500],
                'semester': target_semester if r['semester'] == target_semester else None
            }

    # 2. Fetch notes belonging to the selected semester
    note_rows = app.db.execute('''
        SELECT n.id, n.course, n.unit, n.path, n.hash, n.analysis
        FROM notes n
        JOIN note_semesters ns ON ns.note = n.id
        WHERE ns.semester = ?
        ORDER BY n.course, n.unit, n.id
    ''', (target_semester,)).fetchall()

    topic_states = {r['key']: dict(r) for r in app.db.execute('SELECT * FROM topics')}
    
    notes_list = []
    progress_dict = {}

    for nr in note_rows:
        course_name = (nr['course'] or '').strip()
        if not course_name or is_lab_subject(course_name):
            continue

        if course_name not in courses_map:
            courses_map[course_name] = {
                'id': safe_name(course_name)[:100],
                'name': course_name[:500],
                'semester': target_semester
            }

        try:
            analysis_raw = json.loads(nr['analysis'])
        except (ValueError, TypeError):
            continue

        if not isinstance(analysis_raw, dict) or not isinstance(analysis_raw.get('topics'), list):
            continue

        note_id = str(nr['id'])[:300]
        
        # Latest video recommendations from history for this note
        hist_row = app.db.execute('SELECT result FROM history WHERE note=? ORDER BY id DESC LIMIT 1', (note_id,)).fetchone()
        recs_by_topic = {}
        if hist_row:
            try:
                for entry in json.loads(hist_row['result']):
                    tname = (entry.get('topic') or '').casefold().strip()
                    if tname:
                        recs_by_topic[tname] = entry.get('videos', [])
            except Exception:
                pass

        # Study aids from cache (quiz & flashcards)
        cached_aids = app.cached('aids:' + note_id) or []
        quiz_list = []
        flashcard_list = []
        if isinstance(cached_aids, list):
            for section in cached_aids:
                if isinstance(section, dict):
                    for q in section.get('quiz', []):
                        if isinstance(q, dict) and q.get('question'):
                            quiz_list.append({
                                'question': str(q['question'])[:5000],
                                'answer': str(q.get('answer', ''))[:10000],
                                'explanation': str(q.get('explanation', ''))[:10000],
                                'options': [str(opt)[:2000] for opt in q.get('options', [])[:8]]
                            })
                    for f in section.get('flashcards', []):
                        if isinstance(f, dict) and f.get('front'):
                            flashcard_list.append({
                                'front': str(f['front'])[:4000],
                                'back': str(f.get('back', ''))[:10000]
                            })

        # Sanitize topics
        topics_list = []
        for top in analysis_raw.get('topics', []):
            if not isinstance(top, dict) or not top.get('name'):
                continue
            tname = str(top['name'])[:300].strip()
            if not tname:
                continue

            diff = str(top.get('difficulty', 'intermediate')).lower()
            if diff not in {'foundational', 'intermediate', 'tricky'}:
                diff = 'intermediate'

            pages = []
            for p in top.get('source_pages', []):
                if isinstance(p, int) and p > 0:
                    pages.append(p)

            # Match recommended videos
            matched_videos = []
            raw_vids = recs_by_topic.get(tname.casefold(), [])
            for v in raw_vids:
                vid_id = str(v.get('id', '')).strip()
                if not _VIDEO_ID_RE.match(vid_id):
                    continue
                matched_videos.append({
                    'id': vid_id,
                    'title': str(v.get('title', ''))[:500],
                    'channel': str(v.get('channelTitle') or v.get('channel', ''))[:300],
                    'reason': str(v.get('reason', ''))[:2000],
                    'score': max(0.0, min(10.0, float(v.get('score', 0)))),
                    'views': max(0, int(v.get('views', 0)))
                })

            topics_list.append({
                'name': tname,
                'concepts': [str(c)[:1000] for c in top.get('concepts', [])[:40]],
                'definitions': [str(d)[:3000] for d in top.get('definitions', [])[:40]],
                'prerequisites': [str(p)[:500] for p in top.get('prerequisites', [])[:30]],
                'difficulty': diff,
                'source_pages': pages[:100],
                'videos': matched_videos[:3]
            })

            # Record progress state for topic if marked
            state = topic_states.get(tname.casefold())
            if state and (state.get('covered') or state.get('weak')):
                pkey = f'{note_id}:{tname.lower()}'
                progress_dict[pkey] = {
                    'covered': bool(state.get('covered')),
                    'weak': bool(state.get('weak'))
                }

        # Filename from path as title
        filename = Path(nr['path']).name if nr['path'] else 'Note'
        hash_val = str(nr['hash'] or '').strip()
        valid_hash = hash_val if _HEX64_RE.match(hash_val) else ''

        notes_list.append({
            'id': note_id,
            'course': course_name[:500],
            'unit': str(nr['unit'] or '')[:1000],
            'title': filename[:1000],
            'hash': valid_hash,
            'model': str(app.cfg.get('model', 'gemini-3.1-flash-lite'))[:100],
            'analysis': {
                'summary': str(analysis_raw.get('summary', ''))[:50000],
                'warning': str(analysis_raw.get('warning') or analysis_raw.get('readability_warning') or '')[:20000],
                'topics': topics_list,
                'quiz': quiz_list[:40],
                'flashcards': flashcard_list[:100]
            }
        })

    # 3. Optional exam plan
    plan_obj = None
    plan_path = app.data / 'exam_plans' / f'semester-{target_semester}.json'
    if plan_path.exists():
        try:
            raw_plan = json.loads(plan_path.read_text(encoding='utf-8'))
            if isinstance(raw_plan, dict) and raw_plan.get('exam') and re.match(r'^\d{4}-\d{2}-\d{2}$', str(raw_plan['exam'])):
                days_list = []
                for d in raw_plan.get('days', [])[:370]:
                    tasks_list = []
                    for t in d.get('tasks', [])[:500]:
                        tasks_list.append({
                            'course': str(t.get('course', ''))[:500],
                            'topic': str(t.get('topic', ''))[:500],
                            'minutes': max(1, min(720, int(t.get('minutes', 30))))
                        })
                    days_list.append({
                        'date': str(d.get('date', ''))[:10],
                        'tasks': tasks_list
                    })
                unscheduled_minutes = sum(int(t.get('minutes', 0)) for t in raw_plan.get('unscheduled', []))
                plan_obj = {
                    'exam': str(raw_plan['exam']),
                    'daily': max(15, min(720, int(raw_plan.get('daily_minutes', 120)))),
                    'days': days_list,
                    'remaining': max(0, unscheduled_minutes)
                }
        except Exception:
            plan_obj = None

    return {
        'format': FORMAT,
        'semester': target_semester,
        'courses': list(courses_map.values()),
        'notes': notes_list,
        'progress': progress_dict,
        'plan': plan_obj
    }


def export_study_to_file(app, semester=None, destination=None):
    """Generate study JSON from SQLite and write to destination file."""
    data = build_study_export(app, semester=semester)
    target_path = Path(destination) if destination else (app.data / 'exports' / f"Studyspace-semester-{data['semester']}.json")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return target_path

