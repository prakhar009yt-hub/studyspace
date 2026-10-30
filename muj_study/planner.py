"""Local, capacity-aware exam schedules. No API calls required."""
from collections import deque
from datetime import date, timedelta
import csv
import io
import json
from uuid import uuid4

from .core import StudyError, digest, is_lab_subject


def make_plan(notes, states, courses, start, exam, daily_minutes, topic_minutes=30):
    if exam <= start:
        raise StudyError('Choose an exam date after your first study day.')
    if daily_minutes < 1 or topic_minutes < 1:
        raise StudyError('Study time must be greater than zero.')
    groups = {}
    for note in notes:
        course = note['course']
        if course not in courses or is_lab_subject(course):
            continue
        for topic in json.loads(note['analysis']).get('topics', []):
            name = topic['name'].strip()
            key = (course, name.casefold())
            state = states.get(name.casefold(), {})
            entry = {'id': digest(key)[:20], 'course': course, 'topic': name,
                     'note': note['id'], 'weak': bool(state.get('weak')),
                     'covered': bool(state.get('covered'))}
            groups.setdefault(course, {})[key] = entry
    queues = [deque(sorted(items.values(), key=lambda t: (not t['weak'], t['covered'], t['topic'])))
              for items in groups.values()]
    topics = []
    while any(queues):
        for queue in queues:
            if queue:
                topics.append(queue.popleft())
    if not topics:
        raise StudyError('No analyzed topics found for these subjects. Analyze your notes first.')
    tasks = []
    for stage in ('Study', 'Revision'):
        for topic in topics:
            minutes = max(10, round(topic_minutes * (0.5 if stage == 'Revision' or topic['covered'] else 1.5 if topic['weak'] else 1)))
            tasks.append({**topic, 'stage': stage, 'minutes': minutes})
    days = [{'date': (start + timedelta(days=i)).isoformat(), 'tasks': [], 'minutes': 0}
            for i in range((exam - start).days)]
    day_index = 0
    unscheduled = []
    for task in tasks:
        remaining = task['minutes']
        part = 0
        while remaining and day_index < len(days):
            day = days[day_index]
            available = daily_minutes - day['minutes']
            if available == 0:
                day_index += 1
                continue
            minutes = min(remaining, available)
            day['tasks'].append({**task, 'minutes': minutes, 'id': f'{task["id"]}-{task["stage"]}-{part}'})
            day['minutes'] += minutes
            remaining -= minutes
            part += 1
        if remaining:
            unscheduled.append({**task, 'minutes': remaining})
    return {'id': uuid4().hex, 'start': start.isoformat(), 'exam': exam.isoformat(), 'courses': list(courses),
            'daily_minutes': daily_minutes, 'topic_minutes': topic_minutes,
            'topic_count': len(topics), 'days': days, 'unscheduled': unscheduled, 'completed': []}


def export_csv(plan):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Date', 'Subject', 'Topic', 'Activity', 'Minutes', 'Completed'])
    for day in plan['days']:
        for task in day['tasks']:
            # Keep spreadsheet applications from interpreting course/topic text as formulas.
            clean = lambda text: "'" + text if str(text).startswith(('=', '+', '-', '@')) else text
            writer.writerow([day['date'], clean(task['course']), clean(task['topic']), task['stage'], task['minutes'], task['id'] in plan['completed']])
    return output.getvalue()
