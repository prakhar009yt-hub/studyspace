import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from muj_study.agents import AgentPool, save_agent
from muj_study.core import App, StudyError, private_write
from muj_study.gemini import Gemini, document_parts
from muj_study.schemas import Analysis, LeanAnalysis, LeanTopic


class AgentTests(unittest.TestCase):
    def test_provider_mode_ignores_local_cap_but_keeps_counts_and_cooldown(self):
        self.app.cfg.update(gemini_daily_calls=1, gemini_use_provider_quota=True)
        self.app.reserve('gemini_calls', 1)
        pool = AgentPool(self.app)
        agent = pool.claim()
        self.assertEqual(pool.limit(agent), 0)
        self.app.reserve(pool.bucket(agent), pool.limit(agent))
        self.assertEqual(self.app.db.execute('SELECT used FROM quota WHERE bucket=?', ('gemini_calls',)).fetchone()[0], 2)
        self.assertTrue(pool.remaining() > 0)
        pool.release(agent, 'API quota/rate limit reached.')
        self.assertFalse(pool.available())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'MUJ_PRIVATE_DIR': str(self.root / 'private')})
        self.env.start()
        self.app = App(self.root / 'config.json', self.root / 'data')
        private_write(self.app.secrets, {'GEMINI_API_KEY': 'fake-primary'})

    def tearDown(self):
        self.app.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_two_keys_claim_different_slots_without_duplicate_assignment(self):
        save_agent(self.app, 'Second worker', 'fake-second', 'project-two', 20)
        first_pool = AgentPool(self.app)
        first = first_pool.claim()
        other = App(self.app.config_path, self.app.data)
        try:
            second_pool = AgentPool(other)
            second = second_pool.claim()
            self.assertNotEqual(first['id'], second['id'])
            first_pool.release(first)
            second_pool.release(second)
        finally: other.close()

    def test_keys_in_same_project_share_budget_and_cooldown(self):
        self.app.cfg['gemini_daily_calls'] = 1
        save_agent(self.app, 'Same project', 'fake-second', 'primary', 10)
        pool = AgentPool(self.app)
        agent = pool.claim()
        pool.release(agent, 'API quota/rate limit reached.')
        self.assertFalse(pool.available())
        self.app.reserve('gemini_calls', 1)
        self.assertEqual(pool.remaining(), 0)
        with self.assertRaisesRegex(StudyError, 'daily budget reached'): pool.claim()

    def test_exhausted_primary_does_not_block_another_configured_project(self):
        self.app.cfg['gemini_daily_calls'] = 1
        self.app.reserve('gemini_calls', 1)
        save_agent(self.app, 'Second worker', 'fake-second', 'project-two', 20)
        pool = AgentPool(self.app)
        agent = pool.claim()
        self.assertEqual(agent['name'], 'Second worker')
        self.assertEqual(pool.remaining(), 20)
        pool.release(agent)

    def test_bad_key_pauses_only_its_agent(self):
        save_agent(self.app, 'Second worker', 'fake-second', 'project-two', 20)
        pool = AgentPool(self.app)
        agent = pool.claim()
        pool.release(agent, 'API rejected the request (HTTP 403).')
        self.assertTrue(pool.available())
        next_agent = pool.claim()
        self.assertNotEqual(agent['id'], next_agent['id'])
        pool.release(next_agent)

    def test_token_usage_is_recorded_once_and_cache_uses_no_request(self):
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.models.generate_content.return_value = SimpleNamespace(
            text=Analysis(summary='Example', topics=[]).model_dump_json(), candidates=[],
            usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=25, thoughts_token_count=5, cached_content_token_count=0))
        with patch('google.genai.Client', return_value=client):
            Gemini(self.app).generate('Explain', Analysis, ['Source'])
            Gemini(self.app).generate('Explain', Analysis, ['Source'])
        self.assertEqual(client.models.generate_content.call_count, 1)
        row = self.app.db.execute('SELECT * FROM token_usage').fetchone()
        self.assertEqual((row['input_tokens'], row['output_tokens'], row['thinking_tokens']), (120, 25, 5))
        self.assertEqual(self.app.db.execute('SELECT busy_until FROM analysis_agents_state').fetchone()[0], 0)

    def test_lean_analysis_builds_queries_locally_and_merges_duplicate_topics(self):
        path = self.root / 'notes.txt'; path.write_text('Notes about arrays')
        topic = dict(name='Arrays', concepts=['Index'], definitions=['Indexed collection'], difficulty='foundational', prerequisites=[], source_pages=[])
        second = {**topic, 'name': 'arrays', 'concepts': ['Traversal']}
        response = LeanAnalysis(summary='Arrays', topics=[LeanTopic(**topic), LeanTopic(**second)])
        with patch.object(Gemini, 'generate', return_value=response) as generate:
            result = Gemini(self.app).analyze(path, 'DSA')
        self.assertIs(generate.call_args.args[1], LeanAnalysis)
        self.assertEqual(len(result['topics']), 1)
        self.assertEqual(result['topics'][0]['concepts'], ['Index', 'Traversal'])
        self.assertEqual(len(result['topics'][0]['queries']), 3)

    def test_text_only_pdf_uses_text_while_vector_diagrams_keep_pdf(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
        for drawing in [False, True]:
            writer = PdfWriter()
            page = writer.add_blank_page(width=600, height=800)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            stream = DecodedStreamObject()
            data = b'BT /F1 12 Tf 40 700 Td (' + b'Arrays use indexes to store and retrieve elements. ' * 5 + b') Tj ET'
            stream.set_data(data + (b' 10 10 80 40 re S' if drawing else b''))
            page[NameObject('/Contents')] = stream
            path = self.root / f'notes-{drawing}.pdf'; writer.write(path)
            parts = list(document_parts(path, efficient=True))
            if drawing: self.assertEqual(parts[0][0].inline_data.mime_type, 'application/pdf')
            else:
                self.assertIsInstance(parts[0][0], str)
                self.assertIn('Original page 1', parts[0][0])
