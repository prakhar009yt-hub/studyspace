"""Local dashboard: run with python -m muj_study web."""
import json
from pathlib import Path

import streamlit as st

from muj_study.core import App, StudyError, safe_name, private_write
from muj_study.gemini import Gemini
from muj_study.workflow import export_plan, progress
from muj_study.youtube import YouTube
from muj_study import ui
from muj_study.library import semester_notes, semester_courses
from muj_study import lms_ui

st.set_page_config(page_title='studyspace · MUJ Study Assistant', page_icon='✦', layout='wide')


def main():
    app = App()
    try:
        render(app)
    except StudyError as exc:
        st.error(str(exc))
    except Exception as exc:
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)
        app.logger.error('Unexpected %s: %s', type(exc).__name__, ' -> '.join(f'{Path(f.filename).name}:{f.lineno} ({f.name})' for f in frames))
        st.error(f'{type(exc).__name__}: operation failed. Check configuration, file readability and API access.')
    finally:
        app.close()


def render(app):
    if st.session_state.pop('_theme_changed', False): st.rerun()
    ui.style(app)
    pages = list(ui.NAV_ICONS)
    selected = st.query_params.get('page')
    if selected in pages and selected != st.session_state.get('navigation'):
        st.session_state['navigation'] = selected
    with st.sidebar:
        ui.sidebar_brand()
        from muj_study.appearance import toggle as toggle_appearance
        light = app.cfg.get('appearance', 'dark') == 'light'
        with st.container(key='theme-control'):
            st.button('☾' if light else '☀', key='appearance-toggle', help='Switch to dark mode' if light else 'Switch to light mode', on_click=toggle_appearance, args=(str(app.config_path), str(app.data)), width='stretch')
        ui.html('<div class="nav-label">EXPLORE YOUR WORKSPACE</div>')
        page = st.radio('Open', pages, key='navigation', on_change=ui.sync_navigation, label_visibility='collapsed', width='stretch')
        if st.query_params.get('page') != page: ui.sync_navigation()
        courses = sorted({c['name'] for c in semester_courses(app)} | {n['course'] for n in semester_notes(app)})
        st.divider()
        st.caption(f'Semester {app.cfg["semester"]} subjects')
        course = st.selectbox('Course', ['All courses', *courses])
        ui.sidebar_footer()
    ui.topbar(page, app)
    lms_ui.background_status(str(app.config_path), str(app.data))
    if page == 'LMS':
        lms_ui.render(app)
        return
    if page == 'Topics':
        from muj_study.activity_ui import render_topics
        render_topics(app, course)
        return
    if page == 'Videos':
        from muj_study.activity_ui import render_videos
        render_videos(app, course)
        return
    if page == 'Home':
        ui.home(app)
        return
    if page == 'Planner':
        from muj_study.planner_ui import render as render_planner
        render_planner(app, course)
        return
    if page == 'Import':
        ui.heading('GROW YOUR LIBRARY', 'Good notes. A great starting point.', 'Bring your course material. Leave with a little more clarity.')
        st.write('')
        name = st.text_input('Course name', app.cfg['subject'])
        unit = st.text_input('Unit / module', 'Unit 1')
        upload = st.file_uploader('PDF, PowerPoint, Word or text', type=['pdf', 'pptx', 'docx', 'txt', 'md'])
        st.caption('PDF keeps diagrams and scanned pages intact. Word and PowerPoint use extracted text. Your note content is sent to Gemini when you analyze it.')
        if st.button('Analyze notes', type='primary', disabled=upload is None):
            import hashlib
            target = app.data / 'imports' / safe_name(name) / safe_name(unit) / (hashlib.sha256(upload.getvalue()).hexdigest()[:8] + '-' + safe_name(upload.name))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(upload.getvalue())
            with st.spinner('Reading notes with Gemini…'):
                result = Gemini(app).analyze(target, name, unit)
            st.success('Analysis saved. Open Notes to study.')
            st.json(result)
        return
    if page == 'Settings':
        ui.heading('MAKE IT YOURS', 'A workspace that gets you.', 'Choose your subjects, languages, favourite teachers, and study pace.')
        with st.expander('API keys · connect your study tools', expanded=not app.secrets.exists()):
            st.caption('Keys are saved privately on this computer. Leave a field blank to keep its existing key.')
            with st.form('api-keys', clear_on_submit=True):
                gemini_key = st.text_input('Gemini API key', type='password', placeholder='Paste your Gemini key')
                youtube_key = st.text_input('YouTube Data API v3 key', type='password', placeholder='Paste your YouTube key')
                if st.form_submit_button('Save API keys', type='primary'):
                    from muj_study.lms import LMS
                    LMS(app).protect_session()
                    keys = json.loads(app.secrets.read_text()) if app.secrets.exists() else {}
                    if gemini_key.strip(): keys['GEMINI_API_KEY'] = gemini_key.strip()
                    if youtube_key.strip(): keys['YOUTUBE_API_KEY'] = youtube_key.strip()
                    if not gemini_key.strip() and not youtube_key.strip():
                        st.info('Enter a key to save it.')
                    else:
                        private_write(app.secrets, keys)
                        st.success('Your keys are saved. You’re ready to import notes.')
            link_a, link_b = st.columns(2)
            link_a.link_button('Get a Gemini key ↗', 'https://aistudio.google.com/api-keys')
            link_b.link_button('YouTube API credentials ↗', 'https://console.cloud.google.com/apis/credentials')
        st.write('')
        from muj_study.agent_ui import render as render_agents
        render_agents(app)
        with st.form('preferences'):
            subject = st.text_input('Subject', app.cfg['subject'])
            semester = st.number_input('Semester', 1, 12, int(app.cfg['semester']))
            level = st.text_input('Level', app.cfg['level'])
            languages = st.multiselect('Languages', ['en', 'hi'], default=app.cfg['languages'])
            preferred = st.text_area('Preferred channel names or IDs, one per line', '\n'.join(app.cfg['preferred_channels']))
            blocked = st.text_area('Blocked channel names or IDs, one per line', '\n'.join(app.cfg['blocked_channels']))
            exam = st.text_input('Exam date (YYYY-MM-DD, blank disables)', app.cfg.get('exam_date') or '')
            model = st.text_input('Analysis model', app.cfg['model'])
            ranking = st.text_input('Ranking model', app.cfg['ranking_model'])
            youtube_quota = st.checkbox('Use Google quota directly (no local YouTube cap)', value=app.cfg.get('youtube_use_provider_quota', False))
            search_limit = st.number_input('Daily YouTube search request budget', 1, 10000, app.cfg['daily_search_limit'], disabled=youtube_quota)
            provider_quota = st.checkbox('Use Google quota directly (no local Gemini cap)', value=app.cfg.get('gemini_use_provider_quota', False))
            gemini_limit = st.number_input('Daily Gemini request budget', 1, 10000, app.cfg['gemini_daily_calls'], disabled=provider_quota)
            st.caption('With no local Gemini cap, requests continue until Google rejects them or the queue finishes. Provider quotas and billing still apply; Google does not report remaining quota through this local counter.')
            st.caption('Local limits count API attempts, including retries. Changing a limit may increase provider usage or costs; it does not change your provider quota.')
            if st.form_submit_button('Save preferences'):
                from datetime import date
                if not languages: raise StudyError('Select at least one language.')
                if exam: date.fromisoformat(exam)
                app.cfg.update(subject=subject, semester=int(semester), level=level, languages=languages, preferred_channels=preferred.splitlines(), blocked_channels=blocked.splitlines(), exam_date=exam or None, model=model, ranking_model=ranking, daily_search_limit=int(search_limit), gemini_daily_calls=int(gemini_limit), gemini_use_provider_quota=provider_quota, youtube_use_provider_quota=youtube_quota)
                app.save_config(); st.success('Saved.')
        st.subheader('API usage on this computer')
        st.dataframe([dict(r) for r in app.db.execute('SELECT * FROM quota ORDER BY day DESC')], width='stretch')
        st.caption('Cloud Console is authoritative. Local counts cannot include other applications. Budgets reset at Pacific midnight.')
        return
    if page == 'Progress':
        ui.heading('SEE HOW FAR YOU’VE COME', 'A little progress, every day.', 'Keep track of what clicks and what deserves a second look.')
        data = progress(app)
        if data['exam_date']: st.info(f'Exam: {data["exam_date"]} · {data["days_to_exam"]} days remaining')
        if not data['courses']:
            ui.empty('Your progress starts with one note', 'Import your course material, then mark topics as covered as you study.', '◈')
            st.button('Add some notes →', type='primary', on_click=ui.navigate, args=('Import',))
        for name, entry in data['courses'].items():
            if course != 'All courses' and name != course: continue
            st.subheader(name)
            st.caption(f'{entry["downloaded"]} files downloaded · {entry["analyzed"]} notes analyzed · {entry["pending"]} pending · {entry["links"]} links')
            if entry['total']:
                st.progress(entry['covered'] / entry['total'], text=f'{entry["covered"]} / {entry["total"]} topics covered')
                st.dataframe(entry['topics'], width='stretch')
            else:
                st.info(entry['status'] + ('.' if 'excluded' in entry['status'] else '. Topic progress appears when note analysis completes.'))
        return
    notes = [r for r in semester_notes(app) if course == 'All courses' or r['course'] == course]
    ui.heading('YOUR KNOWLEDGE, CONNECTED', 'Everything you’re learning.', 'Your notes, clear explanations, and the next step forward.')
    lms_ui.render_library(app, course)
    if not notes:
        st.write('')
        ui.empty('Your semester, ready to explore', 'Connect MUJ to fetch your subjects and notes automatically. Downloaded files appear above; summaries and study aids appear after analysis.')
        st.button('Connect / fetch from MUJ →', type='primary', on_click=ui.navigate, args=('LMS',))
        return
    units = sorted({n['unit'] for n in notes})
    selected_unit = st.selectbox('Unit / module', ['All modules', *units])
    if selected_unit != 'All modules': notes = [n for n in notes if n['unit'] == selected_unit]
    default_index = next((i for i, n in enumerate(notes) if n['id'] == st.session_state.get('open_note_id')), 0)
    note_map = {n['id']: n for n in notes}
    selected_id = st.selectbox('Note', list(note_map), index=default_index, format_func=lambda key: f'{note_map[key]["course"]} / {note_map[key]["unit"]} / {Path(note_map[key]["path"]).name}')
    selected = note_map[selected_id]
    analysis = json.loads(selected['analysis'])
    st.subheader(Path(selected['path']).name)
    st.write(analysis['summary'])
    if analysis.get('readability_warning'): st.warning(analysis['readability_warning'])
    tabs = st.tabs(['Topics & videos', 'Quiz & flashcards', 'Ask these notes', 'Syllabus gaps', 'History'], key='note-study-tabs-' + selected['id'], on_change='rerun')
    with tabs[0]:
        if tabs[0].open:
            left, right = st.columns(2)
            playlists = left.checkbox('Include playlist search (uses extra quota)')
            refresh = right.checkbox('Refresh searches and scoring')
            from muj_study.activity_ui import video_status, find_topic_videos
            from muj_study.jobs import Jobs
            topic_options = json.loads(selected['analysis'])['topics']
            if topic_options:
                topic_index = st.selectbox('Find videos for topic', list(range(len(topic_options))), format_func=lambda i: topic_options[i]['name'])
                video_status(str(app.config_path), str(app.data))
                if st.button('Find study videos', type='primary', disabled=bool(Jobs(app, channel='videos').active())):
                    find_topic_videos(app, selected['id'], topic_index, refresh, playlists)
            row = app.db.execute('SELECT result FROM history WHERE note=? ORDER BY id DESC LIMIT 1', (selected['id'],)).fetchone()
            recommendations = {t['topic']: t for t in json.loads(row['result'])} if row else {}
            video_busy = bool(Jobs(app, channel='videos').active())
            topic_search = st.text_input('Search topics in this note', key='topic-search-' + selected['id'])
            matches = [(i, t) for i, t in enumerate(analysis['topics']) if topic_search.casefold() in (t['name'] + ' ' + ' '.join(t['concepts'])).casefold()]
            pages = max(1, (len(matches) + 7) // 8)
            focus = next((i for i, (_, t) in enumerate(matches) if t['name'] == st.session_state.get('_focus_topic')), 0)
            topic_page = st.selectbox('Topic page', range(1, pages + 1), index=focus // 8, key='topic-page-' + selected['id'] + '-' + str(len(matches))) if pages > 1 else 1
            st.caption(f'{len(matches)} matching topics · showing {(topic_page - 1) * 8 + 1 if matches else 0}–{min(topic_page * 8, len(matches))}')
            topic_states = {r['key']: dict(r) for r in app.db.execute('SELECT * FROM topics')}
            for index, topic in matches[(topic_page - 1) * 8:topic_page * 8]:
                with st.expander(f'{index + 1}. {topic["name"]} · {topic["difficulty"]}', expanded=topic['name'] == st.session_state.get('_focus_topic') if st.session_state.get('_focus_topic') else index == 0):
                    st.write(' · '.join(topic['concepts']))
                    st.caption('Prerequisites: ' + ', '.join(topic['prerequisites']))
                    for definition in topic['definitions']: st.write(definition)
                    state = topic_states.get(topic['name'].casefold())
                    c1, c2 = st.columns(2)
                    weak = c1.checkbox('This topic is confusing', value=bool(state and state['weak']), key=f'weak-{selected["id"]}-{index}')
                    covered = c2.checkbox('Reviewed / covered', value=bool(state and state['covered']), key=f'covered-{selected["id"]}-{index}')
                    if st.button('Save topic progress', key=f'save-{index}'):
                        app.topic(topic['name'], weak, covered); st.success('Saved.')
                    rec = recommendations.get(topic['name'])
                    if not rec: continue
                    if rec.get('no_strong_match') or rec.get('ranking_version') != 'ai-topic-v3':
                        st.info('These saved results need a better topic search. Let AI search using this course and the note concepts.')
                        if st.button('Find better videos with AI', key=f'ai-video-retry-{selected["id"]}-{index}', disabled=video_busy):
                            find_topic_videos(app, selected['id'], index, True, playlists)
                    elif rec.get('ai_ranked'):
                        st.caption('AI-ranked matches against your note concepts · video content has not been transcript-verified')
                    if rec.get('no_strong_match') and rec.get('ranking_version') == 'ai-topic-v3':
                        st.warning('AI has not found a sufficiently relevant match yet. Check the API messages below or try the AI search again.')
                    st.caption(f'Estimated watch time: {rec["estimated_minutes"]} min · cache hits: {rec["cache_hits"]}')
                    for warning in rec.get('warnings', []): st.warning(warning)
                    for video in rec['videos']:
                        if not YouTube(app).allowed(video): continue
                        with st.container(key=f'note-card-video-{index}-{video["id"]}'):
                            image_col, text_col = st.columns([1, 3])
                            if video.get('thumbnail'): image_col.image(video['thumbnail'], width='stretch')
                            text_col.markdown(f'**[{video["title"]}]({video["url"]})**')
                            text_col.caption(f'{video["channelTitle"]} · {video["duration_seconds"] // 60} min · {video["views"]:,} views · {video["role"]}')
                            text_col.write(video['reason'])
                            text_col.caption(f'Score {video["score"]:.1f}/10 · confidence {video["confidence"]} · language {video["language"]} · metadata only')
                        verification = app.cached('verification:' + video['id'] + ':' + topic['name'].casefold())
                        if verification:
                            st.write(verification)
                            st.link_button('Jump to transcript match', video['url'] + f'&t={verification["start_seconds"]}s')
                        if video.get('chapters'):
                            with st.expander('Video chapters (from description)'):
                                for chapter in video['chapters']:
                                    st.link_button(chapter['title'], video['url'] + f'&t={chapter["seconds"]}s')
                        key = f'{index}-{video["id"]}'
                        with st.form('feedback-' + key):
                            status = st.selectbox('Watch status', ['unwatched', 'watched', 'skipped', 'blocked'])
                            rating = st.selectbox('Rating', ['okay', 'helpful', 'bad'])
                            reason = st.selectbox('Reason / teaching preference', ['', 'too fast', 'too basic', 'bad audio', 'wrong topic', 'too long', 'clear accent', 'good solved examples'])
                            if st.form_submit_button('Save video feedback'):
                                app.feedback(video['id'], video['channelId'], status, rating, reason); st.rerun()
                    for playlist in rec.get('playlists', []):
                        st.link_button(playlist['title'], playlist['url']); st.caption(playlist['coverage'])
                        if playlist.get('first_lesson'):
                            st.write(f'Lessons {playlist["first_lesson"]}–{playlist["last_lesson"]}: {playlist["reason"]}')
            if st.button('Export offline study plan'):
                path = export_plan(app, selected['id'])
                st.download_button('Download Markdown', path.read_text(encoding='utf-8'), path.name, 'text/markdown')
    with tabs[1]:
        if tabs[1].open:
            if st.button('Generate quiz, flashcards and cheat sheet'):
                with st.spinner('Building study aids…'):
                    app.cache('aids:' + selected['id'], Gemini(app).aids(selected['id']), 365)
            aids = app.cached('aids:' + selected['id']) or []
            for section in aids:
                for question in section['quiz']:
                    st.write(question['question'])
                    if question['options']: st.radio('Choose an answer', question['options'], key=selected['id'] + question['question'])
                    with st.expander('Answer and explanation'): st.write(question['answer']); st.write(question['explanation'])
                for card in section['flashcards']:
                    with st.expander(card['front']): st.write(card['back'])
                st.markdown(section['cheat_sheet'])
    with tabs[2]:
        if tabs[2].open:
            question = st.text_input('Ask a question, e.g. explain slide 12 in simpler words')
            if st.button('Ask Gemini', disabled=not question):
                with st.spinner('Checking the original note…'):
                    answer = Gemini(app).ask(selected['id'], question)
                st.write(answer['answer']); st.caption('Source pages/slides: ' + str(answer['source_pages']))
                if answer['insufficient_evidence']: st.warning('The note does not provide enough evidence for a complete answer.')
    with tabs[3]:
        if tabs[3].open:
            syllabus = st.file_uploader('Syllabus', type=['pdf', 'docx', 'txt', 'md'])
            if st.button('Compare syllabus', disabled=syllabus is None):
                target = app.data / 'syllabi' / safe_name(syllabus.name)
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(syllabus.getvalue())
                with st.spinner('Comparing all analyzed notes for this course…'):
                    st.json(Gemini(app).gaps(selected['course'], target))
    with tabs[4]:
        if tabs[4].open:
            for row in app.db.execute('SELECT created,result FROM history WHERE note=? ORDER BY id DESC LIMIT 10', (selected['id'],)):
                from datetime import datetime
                with st.expander(datetime.fromtimestamp(row['created']).isoformat(timespec='minutes')): st.json(json.loads(row['result']))


if __name__ == '__main__':
    main()
