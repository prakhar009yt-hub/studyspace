"""Approximate wall-clock ETAs for the currently discovered queue."""
import math
import time


def duration(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    return f'{minutes} min' if minutes < 60 else f'{minutes // 60}h {minutes % 60:02d}m'


def estimate(progress, fallback_start, now=None, status='running', blocked=False):
    now = time.time() if now is None else now
    if blocked or progress.get('blocked_error'): return 'Paused — no estimate'
    if status == 'failed': return 'Stopped — retry needed'
    total = progress.get('total')
    if total is None: return 'Discovering files…'
    done = progress.get('processed', 0)
    if progress.get('deferred', 0) and done >= total: return 'Paused — files deferred'
    if total == 0: return 'No files queued'
    if done >= total: return 'Finished with issues' if progress.get('failed') else 'Complete'
    if status not in {'running', 'queued'}: return 'Not running'
    start = progress.get('started_at', fallback_start)
    measured = progress.get('measured_at', now)
    elapsed = max(0, measured - start)
    if done < 2 or elapsed < 2: return 'Measuring processing speed…'
    remaining = elapsed / done * (total - done) - max(0, now - measured)
    if remaining <= 0: return 'Taking longer — recalculating…'
    return f'~{duration(remaining * .7)}–{duration(remaining * 1.5)} left'
