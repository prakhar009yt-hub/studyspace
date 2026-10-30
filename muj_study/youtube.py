from __future__ import annotations

import json
import logging
import re
import time
import math
from datetime import datetime, timezone

import httpx

from .core import StudyError, digest, retry, quota_reset_ist
from .gemini import Gemini
from .schemas import Scores, PlaylistRange, VideoSearchPlan


def duration_seconds(value):
    match = re.fullmatch(r'P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', value)
    if not match:
        return 0
    d, h, m, s = (int(v or 0) for v in match.groups())
    return d * 86400 + h * 3600 + m * 60 + s


def chapters(description):
    result = []
    for stamp, title in re.findall(r'(?m)^\s*((?:\d+:)?\d{1,2}:\d{2})\s*[-–—]?\s+(.+)$', description):
        parts = [int(p) for p in stamp.split(':')]
        seconds = sum(p * 60 ** i for i, p in enumerate(reversed(parts)))
        result.append({'seconds': seconds, 'title': title.strip()})
    return result


class YouTube:
    def __init__(self, app):
        self.app = app
        self.warnings = []
        self.cache_hits = 0

    @staticmethod
    def metadata_score(candidate, topic, languages):
        """Honest low-confidence fallback when model ranking is unavailable."""
        words = set(re.findall(r'[a-z0-9]+', topic['name'].casefold())) - {'and', 'the', 'of', 'to', 'in'}
        text = (candidate['title'] + ' ' + candidate['description']).casefold()
        relevance = min(8, 3 + 5 * sum(word in text for word in words) / max(1, len(words)))
        lang = candidate.get('audio_language') or 'unknown'
        if lang == 'unknown' and re.search(r'hindi|[\u0900-\u097f]', text): lang = 'hi'
        if lang not in languages: lang = 'unknown'
        return {'video_id': candidate['id'], 'relevance': relevance, 'clarity': 5, 'level_match': 5, 'depth': 5, 'examples': 7 if re.search(r'example|solved|problem', text) else 4,
                'role': 'solved problems' if re.search(r'example|solved|problem', text) else 'quick intro' if candidate['duration_seconds'] <= 900 else 'deep dive',
                'reason': 'Matches the note’s topic in the title/description. AI ranking is unavailable; check the lesson yourself.', 'confidence': 'low', 'language': lang, 'ranking_method': 'metadata fallback'}

    def request(self, endpoint, params, refresh=False, days=14):
        key = 'youtube:' + digest([endpoint, params])
        cached = None if refresh else self.app.cached(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        api_key = self.app.key('YOUTUBE_API_KEY')
        bucket = 'youtube_searches' if endpoint == 'search' else 'youtube_metadata'
        limit = self.app.cfg['daily_search_limit' if endpoint == 'search' else 'daily_metadata_limit']
        if self.app.cfg.get('youtube_use_provider_quota', False): limit = 0
        quota_key = 'youtube-provider-quota:' + digest(api_key)

        def call():
            blocked = self.app.cached(quota_key)
            if blocked:
                raise StudyError(f'YouTube API: {blocked}. Searches are paused until the daily reset; cached videos remain available.')
            self.app.reserve(bucket, limit)
            time.sleep(self.app.cfg['request_delay'])
            with httpx.Client(timeout=30) as client:
                response = client.get(f'https://www.googleapis.com/youtube/v3/{endpoint}', params={**params, 'key': api_key})
            if response.status_code in {400, 401, 403}:
                error = response.json().get('error', {})
                reason = error.get('errors', [{}])[0].get('reason', 'accessDenied')
                if reason in {'quotaExceeded', 'dailyLimitExceeded', 'dailyLimitExceededUnreg'}:
                    seconds = max(1, quota_reset_ist().timestamp() - time.time())
                    self.app.cache(quota_key, reason, seconds / 86400)
                raise StudyError(f'YouTube API: {reason}. Check API enablement, key restrictions and project quota.')
            response.raise_for_status()
            return response.json()

        try:
            result = self.app.cache(key, retry(call), days)
            self.app.db.execute('DELETE FROM pending WHERE key=?', (key,))
            self.app.db.commit()
            return result
        except StudyError as exc:
            self.app.db.execute('INSERT OR REPLACE INTO pending VALUES(?,?)', (key, json.dumps({'endpoint': endpoint, 'params': params})))
            self.app.db.commit()
            stale = self.app.cached(key, stale=True)
            if stale is not None:
                self.warnings.append(f'{exc} Reused expired cached metadata.')
                self.cache_hits += 1
                return stale
            raise

    def search(self, query, language, kind='video', refresh=False, order='relevance'):
        return self.request('search', {'part': 'snippet', 'q': query, 'type': kind, 'relevanceLanguage': language, 'order': order, 'maxResults': 8, 'safeSearch': 'strict'}, refresh).get('items', [])

    def details(self, ids, refresh=False):
        results = []
        for start in range(0, len(ids), 50):
            results.extend(self.request('videos', {'part': 'snippet,contentDetails,statistics', 'id': ','.join(sorted(ids[start:start + 50]))}, refresh, 7).get('items', []))
        return results

    def channel_details(self, ids, refresh=False):
        result = {}
        for start in range(0, len(ids), 50):
            data = self.request('channels', {'part': 'snippet,statistics', 'id': ','.join(sorted(ids[start:start + 50]))}, refresh, 14)
            result.update({item['id']: {'subscribers': item.get('statistics', {}).get('subscriberCount'), 'created': item['snippet'].get('publishedAt'), 'description': item['snippet'].get('description', '')[:1500]} for item in data.get('items', [])})
        return result

    def playlist_range(self, playlist, topic, refresh=False):
        pid = playlist['id']['playlistId']
        lessons, page = [], None
        for _ in range(4):
            params = {'part': 'snippet,contentDetails', 'playlistId': pid, 'maxResults': 50}
            if page: params['pageToken'] = page
            data = self.request('playlistItems', params, refresh, 14)
            lessons.extend({'position': i['snippet']['position'] + 1, 'title': i['snippet']['title'], 'video_id': i.get('contentDetails', {}).get('videoId', '')} for i in data.get('items', []))
            page = data.get('nextPageToken')
            if not page: break
        result = {'title': playlist['snippet']['title'], 'url': 'https://www.youtube.com/playlist?list=' + pid,
                  'coverage': 'metadata only; lesson contents unverified', 'inspected_lessons': len(lessons), 'truncated': bool(page)}
        if not lessons: return result
        selection = Gemini(self.app).generate('Given these playlist lesson titles, identify a contiguous lesson range most relevant to the note topic. Use actual position numbers from the data. If no good match set relevant=false. Do not claim transcript verification. Topic: ' + json.dumps(topic) + '\nLessons: ' + json.dumps(lessons), PlaylistRange, strong=True, refresh=refresh)
        positions = {l['position'] for l in lessons}
        if selection.relevant and selection.first_lesson in positions and selection.last_lesson in positions and selection.first_lesson <= selection.last_lesson:
            result.update(selection.model_dump())
            first = next(l for l in lessons if l['position'] == selection.first_lesson)
            result['url'] = f'https://www.youtube.com/watch?v={first["video_id"]}&list={pid}&index={selection.first_lesson}'
        return result

    def allowed(self, video):
        feedback = self.app.db.execute('SELECT * FROM feedback WHERE video=?', (video['id'],)).fetchone()
        blocked = {x.casefold() for x in self.app.cfg['blocked_channels']}
        snippet = video.get('snippet', video)
        if feedback and feedback['status'] in {'watched', 'skipped', 'blocked'}:
            return False
        return not ({snippet.get('channelId', '').casefold(), snippet.get('channelTitle', '').casefold()} & blocked)

    def filter(self, video, topic):
        snippet, stats = video['snippet'], video.get('statistics', {})
        seconds = duration_seconds(video['contentDetails']['duration'])
        reasons = []
        if not self.allowed(video):
            reasons.append('watched/skipped/blocked')
        low, high = (300, 1200) if topic.get('scope') != 'chapter' else (1800, 5400)
        if not low <= seconds <= high:
            reasons.append('duration outside topic range')
        views = int(stats.get('viewCount', 0))
        if views < self.app.cfg['minimum_views']:
            reasons.append('too few views')
        if stats.get('likeCount') is not None and views and int(stats['likeCount']) / views < self.app.cfg['minimum_like_ratio']:
            reasons.append('low likes/views')
        title = snippet['title']
        if re.search(r'\b(secret trick|in (?:1|one) minute|guaranteed marks)\b', title, re.I):
            reasons.append('clickbait title')
        if len(title) > 18 and sum(c.isupper() for c in title) / max(1, sum(c.isalpha() for c in title)) > .8:
            reasons.append('excessive capitals')
        lang = snippet.get('defaultAudioLanguage', '').split('-')[0]
        if lang and lang not in self.app.cfg['languages']:
            reasons.append('language mismatch')
        self.app.logger.info('Video %s %s', video['id'], ', '.join(reasons) if reasons else 'passed metadata filters')
        return not reasons

    def recommend(self, topic, refresh=False, playlists=False, quick=False):
        context = {k: self.app.cfg[k] for k in ['subject', 'level', 'languages', 'preferred_channels', 'model', 'ranking_model', 'minimum_views', 'minimum_like_ratio']}
        context['ranking_version'] = 'ai-topic-v3'
        key = 'recommend:' + digest([topic, context, playlists])
        result = None if refresh else self.app.cached(key)
        if result is None:
            found = {}
            learned_key = 'query-learning:' + digest([self.app.cfg['subject'], topic['name'].casefold(), self.app.cfg['languages']])
            learned = self.app.cached(learned_key) or []
            queries = list(dict.fromkeys([*learned, *topic['queries']]))[:2 if quick else 4]
            try:
                plan = Gemini(self.app).generate(
                    'Write 2-3 precise YouTube search queries for this exact university note topic. '
                    'Use the course and concepts to disambiguate acronyms and names. Spell out the topic and subject domain; '
                    'do not search only generic complexity, mathematics, or prerequisite concepts when the actual topic is a hardware circuit. '
                    'Include an explanation query and a worked-example query. Return queries only, never invent video IDs or URLs. '
                    'Note topic: ' + json.dumps(topic), VideoSearchPlan)
                queries = list(dict.fromkeys(q.strip() for q in plan.queries if q.strip()))
            except StudyError as exc:
                self.warnings.append(f'AI search planning unavailable: {exc} Using saved topic queries.')
            if topic.get('weak'):
                queries[-1] = f'{self.app.cfg["subject"]} {topic["name"]} step by step solved problems'
            origins = {}
            for language in self.app.cfg['languages']:
                for index, query in enumerate(queries):
                    try:
                        for item in self.search(f'{query} {"Hindi" if language == "hi" else "English"}', language, refresh=refresh, order='viewCount' if index == 1 else 'relevance'):
                            vid = item['id'].get('videoId')
                            if vid:
                                found[vid] = item
                                origins.setdefault(vid, []).append(query)
                    except StudyError as exc:
                        self.warnings.append(str(exc))
                        break
            if len(found) < 3:
                try:
                    for item in self.search(f'{self.app.cfg["subject"]} {topic["name"]} lecture', self.app.cfg['languages'][0], refresh=refresh):
                        if 'videoId' in item['id']:
                            found[item['id']['videoId']] = item
                except StudyError as exc:
                    self.warnings.append(str(exc))
            videos = []
            if found:
                try:
                    videos = [v for v in self.details(list(found), refresh) if self.filter(v, topic)]
                except StudyError as exc:
                    self.warnings.append(str(exc))
            if len(videos) < 3:
                try:
                    fallback = self.search(f'{self.app.cfg["subject"]} {topic["name"]} tutorial examples', self.app.cfg['languages'][0], refresh=refresh)
                    fallback_ids = [i['id']['videoId'] for i in fallback if 'videoId' in i['id']]
                    extra = [v for v in self.details(fallback_ids, refresh) if self.filter(v, topic)]
                    videos = list({v['id']: v for v in [*videos, *extra]}.values())
                except StudyError as exc:
                    self.warnings.append(str(exc))
            channels = {}
            if videos:
                try:
                    channels = self.channel_details(list({v['snippet']['channelId'] for v in videos}), refresh)
                except StudyError as exc:
                    self.warnings.append(str(exc))
            candidates = []
            for v in videos:
                s = v['snippet']
                candidates.append({'id': v['id'], 'title': s['title'], 'channelId': s['channelId'], 'channelTitle': s['channelTitle'],
                                   'description': s['description'][:4000], 'duration_seconds': duration_seconds(v['contentDetails']['duration']),
                                   'published': s['publishedAt'], 'captions': v['contentDetails'].get('caption') == 'true',
                                   'views': int(v.get('statistics', {}).get('viewCount', 0)),
                                   'thumbnail': s.get('thumbnails', {}).get('medium', {}).get('url', ''),
                                   'url': f'https://www.youtube.com/watch?v={v["id"]}', 'queries': origins.get(v['id'], []),
                                   'channel_metadata': channels.get(s['channelId'], {}), 'chapters': chapters(s['description'])})
                candidates[-1]['audio_language'] = s.get('defaultAudioLanguage', '').split('-')[0]
            picks = []
            if candidates:
                pair_keys = {c['id']: 'score-pair:' + digest([topic, context, c]) for c in candidates}
                by_id = {vid: self.app.cached(k) for vid, k in pair_keys.items()} if not refresh else {}
                missing = [c for c in candidates if not by_id.get(c['id'])]
                if missing:
                    try:
                        scores = Gemini(self.app).generate('Score every candidate 0-10 for relevance to the exact note concepts, estimated clarity, student level match, depth and worked examples. Penalize tangential material even from popular channels. '
                        'You have ONLY metadata: do not claim verified teaching quality or coverage. Infer language conservatively as en, hi or unknown. '
                        'Consider the channel description/age and subscriber count as weak quality signals, never guarantees. '
                        'Assign learning roles and one-line reasons, and confidence. Topic: ' + json.dumps(topic) + '\nStudent: ' + json.dumps(context) + '\nCandidates: ' + json.dumps(missing), Scores, strong=True, refresh=refresh)
                        for score in scores.scores:
                            if score.video_id in pair_keys:
                                by_id[score.video_id] = self.app.cache(pair_keys[score.video_id], {**score.model_dump(), 'ranking_method': 'AI metadata ranking'}, 30)
                    except StudyError as exc:
                        self.warnings.append(f'{exc} Showing metadata-ranked matches instead.')
                        for candidate in missing:
                            by_id[candidate['id']] = self.metadata_score(candidate, topic, self.app.cfg['languages'])
                for candidate in candidates:
                    score = by_id.get(candidate['id'])
                    if not score or (score['language'] not in self.app.cfg['languages'] and score.get('ranking_method') != 'metadata fallback'):
                        continue
                    total = .5 * score['relevance'] + .15 * score['clarity'] + .15 * score['level_match'] + .1 * score['depth'] + .1 * score['examples']
                    if topic.get('fast_changing'):
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(candidate['published'].replace('Z', '+00:00'))).days
                        total -= min(2, max(0, age - 730) / 730)
                    total += .2 if candidate['captions'] else 0
                    picks.append({**candidate, **score, 'score': round(total, 2), 'verification': 'metadata only'})
            playlist_results = []
            if playlists:
                try:
                    playlist_results = [self.playlist_range(i, topic, refresh) for i in self.search(f'{self.app.cfg["subject"]} {topic["name"]}', self.app.cfg['languages'][0], 'playlist', refresh)[:2]]
                except StudyError as exc:
                    self.warnings.append(str(exc))
            result = {'topic': topic['name'], 'videos': picks, 'playlists': playlist_results}
            # Do not persist an empty quota failure as a successful two-week cache entry.
            if picks and not any(v.get('ranking_method') == 'metadata fallback' for v in picks):
                self.app.cache(key, result)
        else:
            self.cache_hits += 1
        # Apply current feedback at display time, including cached results.
        feedback = list(self.app.db.execute('SELECT * FROM feedback'))
        boosts = {}
        for f in feedback:
            boosts[f['channel']] = boosts.get(f['channel'], 0) + {'helpful': .3, 'okay': 0, 'bad': -.5}.get(f['rating'], 0)
        videos = []
        preferred = {x.casefold() for x in self.app.cfg['preferred_channels']}
        for v in result['videos']:
            if not self.allowed(v):
                continue
            if v.get('relevance', v['score']) < 6: continue
            bonus = .5 if {v['channelId'].casefold(), v['channelTitle'].casefold()} & preferred else 0
            verification = self.app.cached('verification:' + v['id'] + ':' + topic['name'].casefold())
            coverage = len(verification['covered_concepts']) / max(1, len(verification['covered_concepts']) + len(verification['missing_concepts'])) if verification else 0
            popularity = min(.25, math.log10(max(1, v.get('views', 0))) / 8 * .25)
            videos.append({**v, 'adjusted_score': round(v['score'] + bonus + coverage + popularity + max(-1, min(1, boosts.get(v['channelId'], 0))), 2),
                           'verification': 'supplied transcript compared' if verification else 'metadata only', 'coverage': verification})
        videos.sort(key=lambda v: v['adjusted_score'], reverse=True)
        selected = videos[:3]
        if len(selected) < 2:
            self.warnings.append(f'Only {len(selected)} suitable video matches are available for this topic. Two or three are recommended when enough matches pass your filters and API searches are available.')
        return {**result, 'ranking_version': 'ai-topic-v3', 'ai_ranked': bool(selected) and all(v.get('ranking_method') == 'AI metadata ranking' for v in selected), 'videos': selected, 'no_strong_match': not selected or max(v['adjusted_score'] for v in selected) < 6,
                'estimated_minutes': round(sum(v['duration_seconds'] for v in selected) / 60), 'cache_hits': self.cache_hits, 'warnings': list(dict.fromkeys(self.warnings))}

    def note_topic(self, note_id, topic_index, refresh=False, playlists=False):
        note = Gemini(self.app).note(note_id)
        topics = json.loads(note['analysis'])['topics']
        if not 0 <= topic_index < len(topics): raise StudyError('This topic is no longer in the note. Reload the page.')
        result = self.recommend({**topics[topic_index], 'course': note.get('course', self.app.cfg['subject'])}, refresh=refresh, playlists=playlists, quick=True)
        previous = self.app.db.execute('SELECT result FROM history WHERE note=? ORDER BY id DESC LIMIT 1', (note_id,)).fetchone()
        old = {r['topic']: r for r in json.loads(previous['result'])} if previous else {}
        # Preserve usable cached results if a refresh fails or quota is exhausted.
        if not result['videos'] and old.get(result['topic'], {}).get('videos'):
            result = {**old[result['topic']], 'warnings': result['warnings'] + ['Showing saved recommendations because fresh search was unavailable.']}
            result['videos'] = [v for v in result['videos'] if self.allowed(v)]
        old[result['topic']] = result
        ordered = [old[t['name']] for t in topics if t['name'] in old]
        self.app.db.execute('INSERT INTO history(created,note,result) VALUES(?,?,?)', (time.time(), note_id, json.dumps(ordered)))
        self.app.db.commit()
        return result

    def note(self, note_id, refresh=False, playlists=False):
        note = Gemini(self.app).note(note_id)
        topics = json.loads(note['analysis'])['topics']
        states = {r['key']: dict(r) for r in self.app.db.execute('SELECT * FROM topics')}
        topics = [{**t, 'weak': bool(states.get(t['name'].casefold(), {}).get('weak'))} for t in topics]
        # Preserve source order normally; exam mode prioritizes weak and least-reviewed topics.
        if self.app.cfg.get('exam_date'):
            topics.sort(key=lambda t: (-states.get(t['name'].casefold(), {}).get('weak', 0), states.get(t['name'].casefold(), {}).get('covered', 0), states.get(t['name'].casefold(), {}).get('reviewed', 0)))
        results = [self.recommend(t, refresh, playlists) for t in topics]
        self.app.db.execute('INSERT INTO history(created,note,result) VALUES(?,?,?)', (time.time(), note_id, json.dumps(results)))
        self.app.db.commit()
        return results

    def drain_queue(self):
        completed = 0
        for row in list(self.app.db.execute('SELECT * FROM pending')):
            item = json.loads(row['payload'])
            try:
                self.request(item['endpoint'], item['params'], refresh=True)
            except StudyError:
                break
            self.app.db.execute('DELETE FROM pending WHERE key=?', (row['key'],))
            self.app.db.commit()
            completed += 1
        return completed
