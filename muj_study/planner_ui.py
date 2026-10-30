"""Exam planner destination."""
from datetime import date, timedelta
import json
import math

import streamlit as st

from . import ui
from .core import private_write
from .library import semester_courses, semester_notes
from .planner import make_plan, export_csv


def render(app, course='All courses'):
    ui.heading('YOUR EXAM ROADMAP', 'A plan for your next exam.', 'Set your date, choose your subjects, and turn your notes into daily study sessions.')
    notes = semester_notes(app)
    courses = sorted({n['course'] for n in notes} | {c['name'] for c in semester_courses(app)})
    path = app.data / 'exam_plans' / f'semester-{app.cfg["semester"]}.json'
    plan = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    today = date.today()
    default_exam = (plan or {}).get('exam') or app.cfg.get('exam_date')
    try:
        default_exam = max(date.fromisoformat(default_exam), today + timedelta(days=1))
    except (TypeError, ValueError):
        default_exam = today + timedelta(days=14)
    with st.form('exam-planner'):
        left, right = st.columns(2)
        start = left.date_input('First study day', today, min_value=today)
        exam = right.date_input('Exam date', default_exam, min_value=today + timedelta(days=1))
        defaults = [c for c in (plan or {}).get('courses', courses if course == 'All courses' else [course]) if c in courses]
        selected = st.multiselect('Subjects to prepare', courses, default=defaults)
        a, b = st.columns(2)
        daily = a.number_input('Study minutes per day', 15, 720, int((plan or {}).get('daily_minutes', 120)), step=15)
        pace = b.number_input('Estimated minutes per topic', 10, 180, int((plan or {}).get('topic_minutes', 30)), step=5)
        st.caption('Tricky topics get extra time. Covered topics get shorter sessions. Revision follows study, and the exam day stays free. Uses your analyzed notes without spending API tokens.')
        if plan:
            st.caption('Generating a new plan replaces this semester’s saved schedule and its completion checkmarks.')
        submitted = st.form_submit_button('Generate exam plan', type='primary')
    if submitted:
        states = {r['key']: dict(r) for r in app.db.execute('SELECT * FROM topics')}
        plan = make_plan(notes, states, selected, start, exam, daily, pace)
        private_write(path, plan)
        app.cfg['exam_date'] = exam.isoformat()
        app.save_config()
        st.success('Your exam plan is saved on this computer.')
    if not plan:
        st.info('Choose your exam date and subjects above to create your plan. Subjects need analyzed notes before topics can be scheduled.')
        return
    st.subheader(f'Exam · {plan["exam"]}')
    days_left = (date.fromisoformat(plan['exam']) - today).days
    st.caption(f'Semester {app.cfg["semester"]} · {max(0, days_left)} days remaining · {plan["topic_count"]} topics · {plan["daily_minutes"]} minutes per day')
    tasks = [t for day in plan['days'] for t in day['tasks']]
    completed = set(plan['completed'])
    total = sum(t['minutes'] for t in tasks)
    done = sum(t['minutes'] for t in tasks if t['id'] in completed)
    st.progress(done / total if total else 0, text=f'{done} / {total} scheduled minutes completed')
    missing = sum(t['minutes'] for t in plan['unscheduled'])
    if missing:
        available_days = len(plan['days'])
        st.warning(f'{missing} minutes do not fit before the exam. To fit the full plan, allow about {math.ceil((total + missing) / available_days)} minutes per day, start earlier, or select fewer subjects. Unscheduled work is listed below.')
    absent = sorted(set(plan['courses']) - {n['course'] for n in notes if json.loads(n['analysis']).get('topics')})
    if absent:
        st.warning('No analyzed topics available for: ' + ', '.join(absent) + '. Fetch/analyze these subjects, then regenerate your plan.')
    st.caption('Time estimates are adjustable. Check the plan against your exam syllabus; newly analyzed notes require regenerating the plan.')
    dates = [d['date'] for d in plan['days']]
    key = 'planner-day-' + plan['id']
    selected_day = st.selectbox('Study day', dates, index=next((i for i, d in enumerate(dates) if d >= today.isoformat()), len(dates) - 1), key=key)
    day = next(d for d in plan['days'] if d['date'] == selected_day)
    st.caption(f'{day["minutes"]} planned minutes')
    if not day['tasks']:
        st.info('Buffer day: catch up, practice questions, or rest.')
    with st.form('planner-completion-' + selected_day):
        checked = set()
        for task in day['tasks']:
            if st.checkbox(f'{task["stage"]} · {task["course"]} · {task["topic"]} · {task["minutes"]} min', value=task['id'] in completed, key='plan-task-' + plan['id'] + '-' + task['id']):
                checked.add(task['id'])
        if st.form_submit_button('Save daily progress'):
            day_ids = {t['id'] for t in day['tasks']}
            plan['completed'] = sorted((completed - day_ids) | checked)
            private_write(path, plan)
            st.rerun()
    with st.expander('Full schedule'):
        st.dataframe([{'Date': d['date'], 'Minutes': d['minutes'], 'Sessions': len(d['tasks']), 'Completed': sum(t['id'] in completed for t in d['tasks'])} for d in plan['days']], hide_index=True, width='stretch')
    if missing:
        with st.expander('Work that does not fit'):
            st.dataframe([{'Subject': t['course'], 'Topic': t['topic'], 'Activity': t['stage'], 'Minutes': t['minutes']} for t in plan['unscheduled']], hide_index=True, width='stretch')
    st.download_button('Download exam plan (CSV)', export_csv(plan), 'exam-plan.csv', 'text/csv', on_click='ignore')
