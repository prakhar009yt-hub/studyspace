"""Topic and watched-video destinations for the Home dashboard tiles."""
import json

import streamlit as st

from .library import semester_notes


def watched_videos(app):
    ids = {n['id'] for n in semester_notes(app)}
    watched = {r['video']: dict(r) for r in app.db.execute("SELECT * FROM feedback WHERE status='watched'")}
    videos = {}
    for row in app.db.execute('SELECT note,result FROM history ORDER BY id DESC'):
        if row['note'] not in ids: continue
        for topic in json.loads(row['result']):
            for video in topic['videos']:
                if video['id'] in watched and video['id'] not in videos:
                    videos[video['id']] = {**video, 'feedback': watched[video['id']], 'topic': topic['topic']}
    return list(videos.values())


def render_topics(app, course):
    from . import ui
    ui.heading('YOUR CONCEPT MAP', 'One topic at a time.', 'Explore discovered concepts, revisit tricky topics, or see what you’ve already covered.')
    choices = ['All topics', 'Covered topics', 'Needs review']
    view = st.selectbox('Topic view', choices, key='topic-view')
    search = st.text_input('Find a topic', placeholder='Search concepts or subjects')
    states = {r['key']: dict(r) for r in app.db.execute('SELECT * FROM topics')}
    matches = []
    for note in semester_notes(app):
        if course != 'All courses' and note['course'] != course: continue
        for index, topic in enumerate(json.loads(note['analysis'])['topics']):
            state = states.get(topic['name'].casefold(), {})
            if view == 'Covered topics' and not state.get('covered'): continue
            if view == 'Needs review' and not (state.get('weak') or not state.get('covered')): continue
            if search.casefold() not in (topic['name'] + ' ' + note['course']).casefold(): continue
            matches.append((note, index, topic, state))
    pages = max(1, (len(matches) + 19) // 20)
    page = st.selectbox('Topic results page', range(1, pages + 1), key='all-topics-page') if pages > 1 else 1
    if matches: st.caption(f'{len(matches)} matching topics · showing {(page - 1) * 20 + 1}–{min(page * 20, len(matches))}')
    for note, index, topic, state in matches[(page - 1) * 20:page * 20]:
        with st.container(key=f'note-card-topic-{note["id"]}-{index}'):
            st.caption(f'{note["course"]} / {note["unit"]} · {topic["difficulty"]}')
            st.markdown('**' + topic['name'] + '**')
            st.write(' · '.join(topic.get('concepts', [])))
            st.caption('Covered' if state.get('covered') else 'Needs review')
            def open_note(note_id=note['id'], name=topic['name']):
                st.session_state['_focus_topic'] = name
                ui.navigate('Notes', note_id)
            st.button('Open topic in notes →', key=f'open-topic-{note["id"]}-{index}', on_click=open_note)
    if not matches:
        ui.empty('No matching topics yet', 'Analyze your fetched notes to discover topics, or change the topic filter.')
        st.button('Go to your notes →', on_click=ui.navigate, args=('Notes',))


@st.fragment(run_every='2s')
def video_status(config, data):
    from .core import App
    from .jobs import Jobs
    current = App(config, data)
    try:
        jobs = Jobs(current, channel='videos')
        state = jobs.latest()
        if not state: return
        if jobs.active(state):
            st.info(state['message'])
            return
        if st.session_state.get('_reported_video_job') != state['file']:
            st.session_state['_reported_video_job'] = state['file']
            st.rerun()
        if state['status'] == 'failed': st.warning(state['message'])
    finally:
        current.close()


def find_topic_videos(app, note_id, topic_index, refresh=False, playlists=False):
    from .jobs import Jobs
    Jobs(app, channel='videos').start('videos', note_id=note_id, topic_index=topic_index, refresh=refresh, playlists=playlists)
    st.rerun()


def render_videos(app, course='All courses'):
    from . import ui
    from .jobs import Jobs
    from .youtube import YouTube
    ui.heading('LEARN FROM A DIFFERENT VOICE', 'Videos that help it click.', 'Topic recommendations from your notes, plus your watched history.')
    view = st.radio('Video view', ['Recommended', 'Watched'], key='video-view', horizontal=True)
    if view == 'Watched':
        render_watched(app)
        return
    notes = [n for n in semester_notes(app) if (course == 'All courses' or n['course'] == course) and json.loads(n['analysis'])['topics']]
    if not notes:
        ui.empty('Your topics will lead the way', 'Analyze a fetched note first, then find videos for any of its topics.')
        st.button('Open notes →', on_click=ui.navigate, args=('Notes',))
        return
    histories = {r['note'] for r in app.db.execute('SELECT DISTINCT note FROM history')}
    default = next((i for i, n in enumerate(notes) if n['id'] in histories), 0)
    note_map = {n['id']: n for n in notes}
    chosen_id = st.selectbox('Choose a note', list(note_map), index=default, format_func=lambda key: f'{note_map[key]["course"]} / {note_map[key]["unit"]}')
    selected = note_map[chosen_id]
    topics = json.loads(selected['analysis'])['topics']
    row = app.db.execute('SELECT result FROM history WHERE note=? ORDER BY id DESC LIMIT 1', (selected['id'],)).fetchone()
    results = {r['topic']: r for r in json.loads(row['result'])} if row else {}
    default_topic = next((i for i, t in enumerate(topics) if results.get(t['name'], {}).get('videos')), 0)
    index = st.selectbox('Topic', list(range(len(topics))), index=default_topic, format_func=lambda i: topics[i]['name'])
    video_status(str(app.config_path), str(app.data))
    busy = bool(Jobs(app, channel='videos').active())
    left, right = st.columns(2)
    if left.button('Find videos for this topic', type='primary', disabled=busy, width='stretch'):
        find_topic_videos(app, selected['id'], index)
    if right.button('Refresh this topic', disabled=busy, width='stretch'):
        find_topic_videos(app, selected['id'], index, refresh=True)
    st.caption('Get the strongest 2–3 matches for one topic, ranked by exact topic relevance, student level, explanations and examples. Popularity is a small supporting signal; teaching quality is estimated from metadata.')
    result = results.get(topics[index]['name'])
    if not result:
        st.info('No recommendations saved for this topic yet. Use Find videos above.')
        return
    if result.get('ranking_version') != 'ai-topic-v3':
        st.info('Refresh this topic to let AI plan a precise search and rank new matches against your notes.')
    for warning in result.get('warnings', []): st.warning(warning)
    videos = [v for v in result['videos'] if YouTube(app).allowed(v)][:3]
    if videos: st.caption(f'{len(videos)} recommended video' + ('s' if len(videos) != 1 else '') + ' for this topic')
    if not videos:
        st.info('No available matches for this topic. Check the quota messages above or try another topic. Watched videos are in the Watched view.')
    for rank, video in enumerate(videos, 1):
        with st.container(key='note-card-recommended-' + video['id']):
            st.caption(f'#{rank} · Topic recommendation')
            if video.get('thumbnail'): st.image(video['thumbnail'], width=320)
            st.link_button(video['title'], video['url'])
            st.caption(f'{video["channelTitle"]} · {video["duration_seconds"] // 60} min · {video.get("role", "Study video")}')
            st.write(video.get('reason', ''))
            if video.get('language') == 'unknown': st.caption('Language unverified: check before watching.')
            if video.get('ranking_method') == 'metadata fallback': st.caption('Metadata match · AI ranking unavailable · low confidence')
            if st.button('Mark watched', key='watch-' + video['id']):
                app.feedback(video['id'], video['channelId'], status='watched')
                st.rerun()


def render_watched(app):
    from . import ui
    videos = watched_videos(app)
    if not videos:
        ui.empty('Your watch history starts here', 'Mark a recommended video as watched and it will appear here.')
        st.button('Explore study videos →', on_click=ui.navigate, args=('Notes',))
    for video in videos:
        with st.container(key='note-card-watched-' + video['id']):
            st.link_button(video['title'], video['url'])
            st.caption(f'{video["channelTitle"]} · {video["topic"]} · {video["duration_seconds"] // 60} min')
            st.write(video.get('reason', ''))
            if st.button('Mark unwatched', key='unwatch-' + video['id']):
                app.feedback(video['id'], status='unwatched')
                st.rerun()
