import argparse
import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from altered_riddles import run, score
from altered_riddles.llm import Reply


class RunCapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.items = self.root / 'items.jsonl'
        self.items.write_text(json.dumps({'id': 'x', 'source': 's', 'text': 'Question?',
                                         'original_text': 'Original?'}) + '\n')
        self.args = argparse.Namespace(model='jalapeno:DeepSeek-V4-Flash-0731',
            items=str(self.items), passed_only=False, limit=0, thinking='on',
            condition='warned', samples=1, runs_dir=str(self.root / 'runs'),
            temperature=None, concurrency=1, retries=1, rpm=None, timeout=10,
            max_tokens=None, user_tag=None)
        self.reply = Reply('test', 'Answer: yes', None, 10, 110, 100, 'stop', 0, 1)

    def execute(self):
        with patch.object(run, 'Client') as client, patch.object(run, 'git_commit', return_value='test'):
            client.return_value.chat = AsyncMock(return_value=self.reply)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                asyncio.run(run.run(self.args))
            return client.return_value.chat

    def test_cap_creates_separate_run_and_preserves_original(self):
        self.execute()
        old = next((self.root / 'runs').glob('*/*/raw.jsonl'))
        before = old.read_bytes()
        self.args.max_tokens = 64000
        chat = self.execute()
        self.assertEqual(chat.call_args.kwargs['max_tokens'], 64000)
        self.assertEqual(old.read_bytes(), before)
        new = next((self.root / 'runs').glob('*/*-cap64000/config.json'))
        self.assertEqual(json.loads(new.read_text())['max_tokens'], 64000)
        self.assertEqual(self.execute().await_count, 0)

    def test_uncounted_reasoning_text_satisfies_the_thinking_guardrail(self):
        self.reply = Reply('test', 'Answer: yes', 'word ' * 200, 10, 210, 0, 'stop', 0, 1)
        self.execute()
        path = next((self.root / 'runs').glob('*/*/summary.json'))
        summary = json.loads(path.read_text())
        self.assertEqual(summary['guardrail'], 'PASS')
        self.assertEqual(summary['median_reasoning_tokens'], 200)
        self.assertEqual(summary['reasoning_tokens_estimated_rows'], 1)
        raw = path.with_name('raw.jsonl')
        self.assertEqual(json.loads(raw.read_text())['reply']['reasoning_tokens'], 0)
        before = raw.read_bytes()
        self.assertEqual(self.execute().await_count, 0)
        self.assertEqual(raw.read_bytes(), before)
        self.assertEqual(json.loads(path.read_text())['guardrail'], 'PASS')

    def test_near_empty_reasoning_text_is_not_thinking(self):
        self.reply = Reply('test', 'Answer: yes', 'Hmm, yes.', 10, 110, 0, 'stop', 0, 1)
        self.execute()
        summary = json.loads(next((self.root / 'runs').glob('*/*/summary.json')).read_text())
        self.assertEqual(summary['guardrail'], 'FAIL')
        self.assertEqual(summary['median_reasoning_tokens'], 0)
        self.assertEqual(summary['reasoning_tokens_estimated_rows'], 0)

    def test_changed_settings_fail_before_mutation(self):
        self.execute()
        raw = next((self.root / 'runs').glob('*/*/raw.jsonl'))
        cfg = raw.with_name('config.json')
        before = (raw.read_bytes(), cfg.read_bytes())
        self.args.temperature = 0.7
        with self.assertRaisesRegex(ValueError, 'run settings changed'):
            self.execute()
        self.assertEqual((raw.read_bytes(), cfg.read_bytes()), before)

    def test_invalid_cap_rejected_without_inference(self):
        self.args.max_tokens = 0
        with self.assertRaisesRegex(ValueError, 'positive'):
            self.execute()
        self.assertFalse((self.root / 'runs').exists())

    def test_scoring_with_capped_familiarity_directory(self):
        item = {'id': 'x', 'source': 's', 'text': 'Question?', 'original_text': 'Original?',
                'answer': 'yes', 'aliases': [], 'original_answer': 'no',
                'original_aliases': [], 'type': 'stated', 'family': 'riddle'}
        self.items.write_text(json.dumps(item) + '\n')
        self.args.max_tokens = 64000
        self.execute()
        directory = next((self.root / 'runs').glob('*/*-cap64000'))
        original = directory.parent / 'original-thinkoff-k5-cap64'
        original.mkdir()
        (original / 'scored.json').write_text(json.dumps({'familiar': {'s': 1.0}}))
        with contextlib.redirect_stdout(io.StringIO()):
            score.score_altered(directory, {'x': item}, None, 1, self.items)
        summary = json.loads((directory / 'scored_summary.json').read_text())
        self.assertEqual(summary['conditioned_on_familiar']['n'], 1)

    def test_missing_config_rejected(self):
        self.execute()
        cfg = next((self.root / 'runs').glob('*/*/config.json'))
        cfg.unlink()
        with self.assertRaisesRegex(ValueError, 'without config'):
            self.execute()
