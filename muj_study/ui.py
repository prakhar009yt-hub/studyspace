"""Presentation helpers for the local Streamlit workspace."""
from html import escape
import json
from pathlib import Path
from urllib.parse import quote

import streamlit as st

from .core import ROOT
from .workflow import progress
from .library import semester_notes, semester_library, semester_courses

# Navigation order and decorative line icons share one source.
NAV_ICONS = {
    'Home': 'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
    'LMS': 'm3 8 9-5 9 5-9 5-9-5Zm4 3v6l5 3 5-3v-6M21 8v8',
    'Notes': 'M5 3h14v18H5zM8 7h8M8 11h8M8 15h5',
    'Topics': 'M12 4v5m-7 7v-4h14v4M12 12v4M9 3h6v4H9zM2 16h6v5H2zM9 16h6v5H9zM16 16h6v5h-6z',
    'Videos': 'M4 5h16v14H4zM10 9l5 3-5 3z',
    'Planner': 'M4 5h16v16H4zM8 3v4M16 3v4M4 10h16m-12 5 3 3 5-5',
    'Import': 'M12 16V3m-5 5 5-5 5 5M4 14v7h16v-7',
    'Progress': 'M4 3v18h17M8 16v-5m5 5V7m5 9V4',
    'Settings': 'M4 7h16M4 17h16M8 4v6m8 4v6',
}


def html(value):
    st.markdown(value, unsafe_allow_html=True)


def style(app=None):
    css = (ROOT / 'assets/dashboard.css').read_text(encoding='utf-8')
    if app and app.cfg.get('appearance', 'dark') == 'light':
        css += '\n' + (ROOT / 'assets/light.css').read_text(encoding='utf-8')
    css += '\n' + (ROOT / 'assets/glass.css').read_text(encoding='utf-8')
    css += '\n' + (ROOT / 'assets/sidebar.css').read_text(encoding='utf-8')
    for index, path in enumerate(NAV_ICONS.values()):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="{path}"/></svg>'
        css += f'\n[data-testid="stSidebar"] label:has(input[value="{index}"]) {{ --nav-icon:url("data:image/svg+xml,{quote(svg, safe="")}"); }}'
    # The stable icon element rotates as its sun/moon glyph changes on rerun.
    rotation = '0deg' if app and app.cfg.get('appearance', 'dark') == 'light' else '-35deg'
    css += f'\n.st-key-theme-control [data-testid="stButton"] p {{ transform:rotate({rotation}); }}'
    mode = 'Light mode' if app and app.cfg.get('appearance', 'dark') == 'light' else 'Dark mode'
    css += f'\n[data-testid="stSidebar"] .st-key-theme-control button::after {{ content:"Appearance\\A {mode}"; }}'
    html('<style>' + css + '</style>')


def sync_navigation():
    st.query_params['page'] = st.session_state['navigation']


def navigate(page, note_id=None):
    st.session_state['navigation'] = page
    sync_navigation()
    if note_id:
        st.session_state['open_note_id'] = note_id


def open_home_tile(tile):
    if tile == 'notes': navigate('Notes')
    elif tile in {'topics', 'covered'}:
        st.session_state['topic-view'] = 'Covered topics' if tile == 'covered' else 'All topics'
        navigate('Topics')
    elif tile == 'watched':
        st.session_state['video-view'] = 'Watched'
        navigate('Videos')


def topbar(page, app):
    semester = int(app.cfg['semester'])
    if st.session_state.get('_profile_semester_seen') != semester:
        st.session_state['profile-semester-choice'] = semester
        st.session_state['_profile_semester_seen'] = semester
    with st.container(key='workspace-topbar'):
        breadcrumb, profile = st.columns([3, 2], vertical_alignment='center')
        with breadcrumb:
            html(f'<div class="breadcrumb">Workspace <span style="padding:0 10px;color:#786777">/</span> {escape(page)}</div>')
        with profile:
            with st.popover(f'MUJ · Semester {semester}', key='semester-menu', help='Change your semester or open study preferences'):
                st.markdown('**Your study profile**')
                st.caption('Choose which semester to view and sync. Only subjects assigned to that semester are loaded.')
                with st.form('profile-semester-form'):
                    selected = st.selectbox('View semester', range(1, 13), key='profile-semester-choice', format_func=lambda n: f'Semester {n}')
                    if st.form_submit_button('Save semester', type='primary', width='stretch'):
                        app.cfg['semester'] = selected
                        app.save_config()
                        st.session_state['_semester_saved'] = True
                        st.rerun()
                st.button('Study preferences →', key='profile-preferences', on_click=navigate, args=('Settings',), width='stretch')
    if st.session_state.pop('_semester_saved', False):
        st.toast('Semester selected. Subjects and notes now show only this semester.')


def sidebar_brand():
    html('<div class="brand"><div class="brand-icon">s.</div><div><div class="brand-name">studyspace<span class="brand-spark" aria-hidden="true">✦</span></div><div class="brand-sub">Your MUJ companion</div></div></div>')


def sidebar_footer():
    html('<div class="sidebar-note"><div class="star" aria-hidden="true">✧</div><strong>Find your flow.</strong><p>A little focus today. A little more clarity tomorrow.</p></div><div class="privacy-tag"><span class="status-dot"></span> Your private study workspace</div>')


def heading(kicker, title, subtitle):
    html(f'<div class="eyebrow">{escape(kicker)}</div>')
    st.title(title)
    st.caption(subtitle)


def empty(title, description, symbol='▤'):
    html(f'<div class="empty-state"><div class="empty-symbol">{symbol}</div><h3>{escape(title)}</h3><p>{escape(description)}</p></div>')


def home(app):
    notes = semester_notes(app)
    downloaded = semester_library(app)
    summary = progress(app)
    topics = sum(c['total'] for c in summary['courses'].values())
    covered = sum(c['covered'] for c in summary['courses'].values())
    from .activity_ui import watched_videos
    watched = len(watched_videos(app))
    html('''<div class="hero"><div class="hero-copy"><div class="eyebrow">A LITTLE FOCUS GOES A LONG WAY</div><h1>Less overwhelm.<br>More understanding.</h1><p>Turn your course notes into clear concepts,<br>great explanations, and a plan that works for you.</p><div class="hero-tag">✦ &nbsp; Made for the way you learn</div></div><div class="hero-art" aria-hidden="true"><div class="orbit"></div><div class="orbit small"></div><div class="spark">✧</div><div class="book"></div><div class="spark two">✦</div><div class="floating-card"><span>✓</span> One concept clearer</div></div></div>''')
    cards = [('▤', 'Notes in your library', len({n['path'] for n in notes} | {n['path'] for n in downloaded}), f'Semester {app.cfg["semester"]} · {len(semester_courses(app))} LMS subjects', ''), ('◈', 'Topics discovered', topics, 'A clearer picture of your syllabus', 'blue'), ('✓', 'Topics covered', covered, 'Every small win counts', 'mint'), ('▷', 'Videos watched', watched, 'Learning at your own pace', 'peach')]
    with st.container(key='home-stat-grid'):
        for col, tile, (icon, label, value, foot, color) in zip(st.columns(4), ['notes', 'topics', 'covered', 'watched'], cards):
            with col:
                with st.container(key='home-tile-' + tile):
                    html(f'<div class="stat-card"><div class="stat-top">{label}<span class="stat-icon {color}">{icon}</span></div><div class="stat-value">{value:02d}</div><div class="stat-foot">{foot}</div></div>')
                    st.button('Open ' + label.lower(), key='home-open-' + tile, on_click=open_home_tile, args=(tile,))
    main, rail = st.columns([2.1, 1], gap='large')
    with main:
        html('<div class="section-head"><h2>Pick up where you left off</h2><span>YOUR LIBRARY</span></div>')
        if not notes:
            if downloaded:
                empty('Your LMS notes are here', f'{len(downloaded)} files are organized by subject and module. Open Notes to browse them or generate study aids.')
                st.button('Open your notes →', type='primary', on_click=navigate, args=('Notes',), width='stretch')
            else:
                empty('Bring your subjects into focus', 'Connect MUJ once. Your subjects and notes will be fetched and organized for the selected semester.')
                st.button('Connect your MUJ LMS →', type='primary', on_click=navigate, args=('LMS',), width='stretch')
        for index, note in enumerate(notes[:3]):
            analysis = json.loads(note['analysis'])
            with st.container(key=f'note-card-home-{index}'):
                html(f'<div class="note-meta">{escape(note["course"])} &nbsp; / &nbsp; {escape(note["unit"])}</div><div class="note-title">{escape(Path(note["path"]).stem)}</div><div class="note-preview">{escape(analysis["summary"][:165])}{"…" if len(analysis["summary"]) > 165 else ""}</div><span class="badge">{len(analysis["topics"])} topics</span><span class="badge">Analyzed</span>')
                st.button('Continue studying →', key=f'open-{note["id"]}', on_click=navigate, args=('Notes', note['id']))
        st.write('')
        quick_a, quick_b = st.columns(2)
        quick_a.button('↻ Fetch from LMS', on_click=navigate, args=('LMS',), width='stretch')
        quick_b.button('View your progress ↗', on_click=navigate, args=('Progress',), width='stretch')
        st.button('Plan for an exam →', on_click=navigate, args=('Planner',), width='stretch')
    with rail:
        html('''<div class="steps-card"><div class="eyebrow">YOUR STUDY ROUTINE</div><h3>A little structure helps.</h3><div class="step"><span class="step-number">1</span><div><strong>Bring your notes</strong><p>Upload a PDF, presentation, or document.</p></div></div><div class="step"><span class="step-number">2</span><div><strong>Connect the dots</strong><p>Explore concepts and find a teacher who clicks.</p></div></div><div class="step"><span class="step-number">3</span><div><strong>Make it stick</strong><p>Practice with quizzes and quick flashcards.</p></div></div></div>''')
        weak = [t['name'] for c in summary['courses'].values() for t in c['topics'] if t['weak'] and not t['covered']]
        if weak:
            title, detail = 'A little extra attention', ', '.join(weak[:3])
        elif summary['exam_date']:
            title, detail = 'Your exam is on the horizon', f'{summary["days_to_exam"]} days to go. Focus on the concepts you find hardest.'
        else:
            title, detail = 'Make space for curiosity', 'Mark a tricky topic as confusing and come back to it with a fresh explanation.'
        html(f'<div class="focus-card"><div class="eyebrow">✦ YOUR FOCUS CORNER</div><h3>{escape(title)}</h3><p>{escape(detail)}</p></div>')
        if not app.secrets.exists():
            st.write('')
            st.button('Set up your API keys →', on_click=navigate, args=('Settings',), width='stretch')
    html('<div class="footer-note">A calmer place to learn. &nbsp; Built around your notes, your pace, your goals.</div>')
