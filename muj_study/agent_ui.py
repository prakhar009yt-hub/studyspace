import time

import streamlit as st

from .agents import AgentPool, save_agent, saved_agents
from .core import StudyError, private_write


def render(app):
    st.subheader('Analysis agents and efficiency')
    st.caption('Agents split files from one queue. Each file is analyzed once. Keys are saved privately on this computer and are never displayed here.')
    st.caption('Use the same Google project label for keys belonging to the same project. They share a local budget and provider cooldown. Additional keys do not increase that project’s Google quota.')
    with st.form('add-analysis-agent', clear_on_submit=True):
        name = st.text_input('Agent name', placeholder='Study worker 2')
        key = st.text_input('Agent Gemini API key', type='password')
        project = st.text_input('Google project label', value='primary', help='Use primary for your existing key’s project, or the actual project ID for another authorized project. Enter identical labels for identical projects.')
        budget = st.number_input('Project daily request budget', 1, 10000, 100)
        if st.form_submit_button('Add analysis agent'):
            try: save_agent(app, name, key, project, budget)
            except StudyError as exc: st.error(str(exc))
            else: st.success('Agent saved. It will join the next analysis job.')
    pool = AgentPool(app)
    rows = []
    for a in pool.agents:
        state = app.db.execute('SELECT * FROM analysis_agents_state WHERE id=?', (a['id'],)).fetchone()
        remaining = app.budget_remaining(pool.bucket(a), pool.limit(a))
        status = 'Budget exhausted' if not remaining else 'Ready'
        if state and state['cooldown_until'] > time.time(): status = 'Paused after API error'
        elif state and state['busy_until'] > time.time(): status = 'Analyzing'
        rows.append({'Agent': a['name'], 'Project': a['project'], 'Requests left': 'Provider managed' if not pool.limit(a) else str(remaining),
                     'Shared project budget': str(pool.limit(a)) if pool.limit(a) else 'No local cap', 'Status': status,
                     'Last error': state['error'] if state else ''})
    if rows: st.dataframe(rows, hide_index=True, width='stretch')
    if app.cfg.get('gemini_use_provider_quota', False): st.info('No local Gemini cap is enabled for all agents. Google quota errors still pause the affected project; request counts remain recorded.')
    extras = saved_agents(app)
    if extras:
        options = {a['id']: a['name'] for a in extras}
        remove = st.selectbox('Extra agent to remove', list(options), format_func=options.get)
        if st.button('Remove selected agent'):
            private_write(app.private / 'analysis_agents.json', [a for a in extras if a['id'] != remove])
            st.rerun()
    with st.form('analysis-efficiency'):
        efficient = st.checkbox('Efficient analysis', value=app.cfg.get('efficient_analysis', True), help='Send extracted text for text-only PDFs; preserve original PDFs for scans and diagrams. Generate video search phrases locally.')
        workers = st.slider('Parallel analysis workers', 1, 8, int(app.cfg.get('analysis_workers', 2)))
        output_limit = st.number_input('Maximum output tokens per request', 1024, 32768, int(app.cfg.get('analysis_output_tokens', 8192)), step=1024)
        st.caption('More workers help when several agents are available. Each key handles one request at a time. More detailed output uses more output tokens; efficiency targets unnecessary input and repeated work.')
        if st.form_submit_button('Save analysis settings'):
            app.cfg.update(efficient_analysis=efficient, analysis_workers=workers, analysis_output_tokens=output_limit)
            app.save_config()
            st.success('Saved. Applies to the next analysis job.')
    usage = app.db.execute('SELECT COUNT(*) calls,COALESCE(SUM(input_tokens),0) input,COALESCE(SUM(output_tokens),0) output,COALESCE(SUM(thinking_tokens),0) thinking FROM token_usage').fetchone()
    st.caption('Token counts below are provider-reported totals recorded since this update. They do not estimate savings against earlier runs.')
    cols = st.columns(3)
    cols[0].metric('Input tokens recorded', usage['input'])
    cols[1].metric('Output tokens recorded', usage['output'])
    cols[2].metric('Thinking tokens recorded', usage['thinking'])
    if usage['calls']:
        st.dataframe([dict(r) for r in app.db.execute('SELECT agent,model,COUNT(*) requests,SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,SUM(thinking_tokens) thinking_tokens FROM token_usage GROUP BY agent,model')], hide_index=True, width='stretch')
