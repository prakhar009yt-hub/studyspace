"""Live transfer and analysis counters shared by every dashboard page."""
import json
import time
from pathlib import Path

import streamlit as st

from .library import semester_library, semester_note_versions
from .core import quota_reset_ist


def job_errors(state):
    state = state or {}
    result = state.get('result', {})
    errors = list(state.get('analysis_progress', {}).get('errors', []))
    errors += state.get('download_progress', {}).get('errors', [])
    errors += [n['error'] for n in result.get('analysis', []) if n.get('error')]
    errors += [n['reason'] for n in result.get('failed', []) if n.get('reason')]
    if state.get('status') == 'failed': errors.append(state.get('message', 'Task failed.'))
    return [e for e in dict.fromkeys(errors) if not e.startswith('Linked HTML page recorded;')][-5:]


def render_status(app, state):
    files = semester_library(app)
    if not files and not state: return
    active = bool(state and state.get('status') in {'running', 'queued'})
    versions = semester_note_versions(app)
    eligible = [f for f in files if Path(f['path']).suffix.lower() in {'.pdf', '.pptx', '.docx', '.txt', '.md'}]
    analyzed = sum((f['path'], f['hash']) in versions for f in eligible)
    label = f'Study progress · {len(files)} files downloaded · {analyzed} analyzed'
    if active: label += ' · Working'
    elif job_errors(state): label += ' · View latest issues'
    panel = st.container(border=True) if st.session_state.get('navigation') == 'Progress' else st.expander(label, expanded=False)
    with panel:
        st.markdown(f'**Semester {app.cfg["semester"]} · File progress**')
        cols = st.columns(3)
        cols[0].metric('Files downloaded in total', len(files))
        cols[1].metric('Files analyzed', analyzed)
        cols[2].metric('Files awaiting analysis', len(eligible) - analyzed)
        st.progress(analyzed / len(eligible) if eligible else 0,
                    text=f'Saved files analyzed: {analyzed} / {len(eligible)} supported files')
        unsupported = [f for f in files if f not in eligible]
        if unsupported:
            with st.expander(f'{len(unsupported)} files need conversion before analysis'):
                st.caption('Older .ppt files must be saved as .pptx or PDF in PowerPoint or LibreOffice, then imported into the matching subject. Existing originals are preserved.')
                for item in unsupported: st.write(f'{item["course"]} / {Path(item["path"]).name}')
        from .agents import AgentPool
        agents = AgentPool(app)
        gemini_left = agents.remaining()
        youtube_left = app.budget_remaining('youtube_searches', app.cfg['daily_search_limit'])
        reset = quota_reset_ist().strftime('%d %b %Y, %I:%M %p IST')
        gemini_label = 'No local cap · Google quota applies' if app.cfg.get('gemini_use_provider_quota', False) else str(gemini_left)
        youtube_label = 'No local cap · Google quota applies' if app.cfg.get('youtube_use_provider_quota', False) else f'{youtube_left} / {app.cfg["daily_search_limit"]}'
        st.caption(f'Local requests remaining: Gemini {gemini_label} across {len(agents.agents)} agents · YouTube search {youtube_label}. Local counters reset: {reset}. One long file can require multiple API requests.')
        if len(eligible) > analyzed and not gemini_left:
            st.warning(f'Analysis is paused: the local request budget is exhausted. Reset: {reset}. Downloads can continue. Add configured agents or review budgets in Settings to change available capacity.')
        elif len(eligible) > analyzed:
            if st.button('Analyze pending files now', key='progress-analyze-pending', disabled=active):
                from .jobs import Jobs
                Jobs(app).start('analyze')
                st.rerun()
        if state:
            transfer = state.get('download_progress', {})
            ai = state.get('analysis_progress', {})
            from .estimates import estimate
            timers = st.columns(2)
            started = state.get('started', time.time())
            transfer_snapshot = {**transfer, 'measured_at': transfer.get('measured_at', state.get('updated', time.time()))}
            transfer_snapshot.pop('deferred', None)  # Other download batches are outside this batch's ETA.
            analysis_snapshot = {**ai, 'measured_at': ai.get('measured_at', state.get('updated', time.time()))}
            timers[0].metric('Download time remaining', estimate(transfer_snapshot, started, status=state.get('status', 'running')) if transfer else 'No downloads running')
            timers[1].metric('Analysis time remaining', estimate(analysis_snapshot, started, status=state.get('status', 'running')) if ai else 'Waiting for analysis queue')
            st.caption('Approximate times for the current batch and queued analyses, based on measured speed. Estimates update every 3 seconds and can change with file size, API delays, retries, or new files. Waiting for enough completed files is normal.')
            if transfer.get('total') is not None:
                total = transfer['total']; done = transfer.get('processed', 0)
                st.progress(min(1.0, done / total) if total else 1.0,
                            text=f'Download batch: {done} / {total} files checked · {transfer.get("downloaded", 0)} downloaded · {transfer.get("unchanged", 0)} unchanged · {transfer.get("linked", 0)} web pages saved as links · {transfer.get("failed", 0)} issues')
                st.caption(f'{transfer.get("discovered", total)} attachments found on MUJ · {transfer.get("deferred", 0)} checks left for later batches. Unchanged files do not need downloading again.')
            if ai:
                total = ai['total']; done = ai['processed']
                st.progress(min(1.0, done / total) if total else 0,
                            text=f'Analysis queue: {done} / {total} processed · {ai["succeeded"]} successful · {ai["failed"]} issues · {ai.get("deferred", 0)} deferred')
                if active and ai.get('active') and not ai.get('blocked_error'):
                    st.caption('Preparing document chunks / waiting for Gemini: ' + '; '.join(ai['active']))
            if active:
                elapsed = max(0, int(time.time() - state['started']))
                quiet = max(0, int(time.time() - state.get('updated', state['started'])))
                st.caption(f'Current job: Semester {state["semester"]} · {elapsed // 60}m {elapsed % 60}s elapsed · last update {quiet}s ago')
                st.info(state.get('message', 'Starting…'))
                stage_elapsed = max(0, int(time.time() - state.get('stage_started', state['started'])))
                st.caption(f'Current stage: {state.get("stage", "starting").title()} · {stage_elapsed // 60}m {stage_elapsed % 60}s')
                if state.get('stage') == 'downloading':
                    if transfer.get('active'): st.caption('Waiting for MUJ attachments: ' + '; '.join(transfer['active']))
                    st.caption('MUJ requests are paced and use up to three download workers. Each attachment request can wait up to 60 seconds, with retries for transient errors. Gemini analysis runs alongside downloads when enabled.')
                if state.get('stage') == 'analyzing' and not ai.get('blocked_error'):
                    st.caption('Long or scanned documents take longer because Gemini processes their pages and images. Each API request can wait up to 120 seconds; transient failures can trigger retries. The queue can grow while files are still downloading.')
            elif state.get('status') == 'complete':
                st.caption('Latest job finished. Issues below identify files that could not complete.')
            for error in job_errors(state):
                st.error(error)
            if any('daily budget reached' in e for e in job_errors(state)):
                st.warning('Analysis or video search has reached the app’s local daily limit. Pending files stay saved. This is a local limit, not an invalid API key; retry after Pacific midnight or review the limit in Settings.')
