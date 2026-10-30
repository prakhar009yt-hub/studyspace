import unittest

from muj_study.estimates import estimate


class EstimateTests(unittest.TestCase):
    def test_needs_samples_before_showing_time(self):
        self.assertIn('Measuring', estimate({'total': 10, 'processed': 1}, 0, now=30))

    def test_uses_measured_throughput_and_counts_down(self):
        progress = {'total': 10, 'processed': 5, 'started_at': 100, 'measured_at': 400}
        self.assertEqual(estimate(progress, 0, now=400), '~4 min–8 min left')
        self.assertEqual(estimate(progress, 0, now=520), '~3 min–5 min left')

    def test_blocked_tasks_never_claim_a_completion_time(self):
        self.assertIn('Paused', estimate({'total': 10, 'processed': 10, 'blocked_error': 'API quota'}, 0, now=100))
        self.assertIn('Paused', estimate({'total': 10, 'processed': 10, 'deferred': 5}, 0, now=100))

    def test_overdue_estimate_waits_for_a_new_sample(self):
        self.assertIn('recalculating', estimate({'total': 10, 'processed': 5, 'started_at': 0, 'measured_at': 100}, 0, now=500))

    def test_completion_failure_and_discovery_are_distinct(self):
        self.assertEqual(estimate({'total': 10, 'processed': 10}, 0, now=100), 'Complete')
        self.assertIn('Stopped', estimate({'total': 10, 'processed': 2}, 0, now=100, status='failed'))
        self.assertIn('Discovering', estimate({}, 0, now=100))
