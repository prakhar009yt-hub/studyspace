"""Private Gemini workers; keys sharing a project share local quota and cooldown."""
import json
import time
import uuid

from .core import StudyError, digest, private_write


def saved_agents(app):
    path = app.private / 'analysis_agents.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


def save_agent(app, name, key, project, budget):
    if not name.strip() or not key.strip() or not project.strip():
        raise StudyError('Enter an agent name, Gemini key and Google project label.')
    agents = saved_agents(app)
    if any(a['key'] == key.strip() for a in agents): raise StudyError('That key is already saved as an agent.')
    try:
        if key.strip() == app.key('GEMINI_API_KEY'): raise StudyError('That key is already your primary Gemini key.')
    except StudyError as exc:
        if 'already' in str(exc): raise
    agents.append({'id': uuid.uuid4().hex, 'name': name.strip()[:60], 'key': key.strip(),
                   'project': project.strip().casefold(), 'budget': max(1, int(budget))})
    from .lms import LMS
    LMS(app).protect_session()
    private_write(app.private / 'analysis_agents.json', agents)


class AgentPool:
    def __init__(self, app):
        self.app = app
        self.agents = saved_agents(app)
        try:
            key = app.key('GEMINI_API_KEY')
        except StudyError:
            key = None
        if key:
            self.agents = [{'id': 'primary-' + digest(key)[:12], 'name': 'Primary Gemini', 'key': key,
                            'project': 'primary', 'budget': app.cfg['gemini_daily_calls']}] + self.agents
        unique = {}
        for agent in self.agents: unique.setdefault(digest(agent['key']), agent)
        self.agents = list(unique.values())

    def bucket(self, agent):
        return 'gemini_calls' if agent['project'] == 'primary' else 'gemini_project:' + digest(agent['project'])[:16]

    def limit(self, agent):
        if self.app.cfg.get('gemini_use_provider_quota', False): return 0
        return min(int(a['budget']) for a in self.agents if a['project'] == agent['project'])

    def remaining(self):
        return sum(self.app.budget_remaining(self.bucket(a), self.limit(a)) for a in {a['project']: a for a in self.agents}.values())

    def available(self):
        now = time.time()
        for a in self.agents:
            row = self.app.db.execute('SELECT MAX(cooldown_until) FROM analysis_agents_state WHERE id=? OR (project=? AND error LIKE ?)', (a['id'], a['project'], '%quota/rate limit%')).fetchone()
            if (not row or not row[0] or row[0] <= now) and self.app.budget_remaining(self.bucket(a), self.limit(a)):
                return True
        return False

    def claim(self):
        if not self.agents: raise StudyError('Add a Gemini key or analysis agent in Settings.')
        deadline = time.monotonic() + 125
        while True:
            now = time.time()
            self.app.db.execute('BEGIN IMMEDIATE')
            try:
                for a in self.agents:
                    self.app.db.execute('INSERT OR IGNORE INTO analysis_agents_state(id,project) VALUES(?,?)', (a['id'], a['project']))
                self.app.db.execute('UPDATE analysis_agents_state SET cooldown_until=MAX(cooldown_until,COALESCE((SELECT MAX(s.cooldown_until) FROM analysis_agents_state s WHERE s.project=analysis_agents_state.project AND s.error LIKE ?),0))', ('%quota/rate limit%',))
                rows = {r['id']: dict(r) for r in self.app.db.execute('SELECT * FROM analysis_agents_state')}
                candidates = sorted(self.agents, key=lambda a: rows[a['id']]['last_used'])
                ready = [a for a in candidates if rows[a['id']]['busy_until'] <= now and rows[a['id']]['cooldown_until'] <= now and self.app.budget_remaining(self.bucket(a), self.limit(a))]
                if ready:
                    agent = ready[0]
                    self.app.db.execute('UPDATE analysis_agents_state SET last_used=?,busy_until=? WHERE id=?', (now, now + 600, agent['id']))
                    self.app.db.commit()
                    return agent
                self.app.db.commit()
            except BaseException:
                self.app.db.rollback()
                raise
            if not self.remaining(): raise StudyError('Local Gemini agent daily budget reached; retry after Pacific midnight or review agent budgets in Settings.')
            if not self.available(): raise StudyError('Gemini agents are paused after API errors. Check their status in Settings and retry after the cooldown.')
            if time.monotonic() >= deadline: raise StudyError('Gemini agents are busy; this file remains queued for a later run.')
            time.sleep(0.25)

    def release(self, agent, error=''):
        cooldown = 0
        if error:
            cooldown = time.time() + (3600 if 'API rejected' in error else 300 if 'quota/rate limit' in error else 60)
        with self.app.db:
            self.app.db.execute('UPDATE analysis_agents_state SET busy_until=0,cooldown_until=?,error=? WHERE id=?', (cooldown, error, agent['id']))
            if 'quota/rate limit' in error:
                self.app.db.execute('UPDATE analysis_agents_state SET cooldown_until=?,error=? WHERE project=?', (cooldown, error, agent['project']))
