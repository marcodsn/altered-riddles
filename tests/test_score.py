import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from altered_riddles.score import SCORER_VERSION, answer_text, score_altered


class ScoreTests(unittest.TestCase):
    def test_truncated_reasoning_is_not_a_committed_answer(self):
        for reasoning in ['Answer: dehydration', 'I recall the classic riddle. Answer: a parachute. But here...', 'Still thinking']:
            self.assertEqual(answer_text({'text': '', 'reasoning': reasoning, 'finish_reason': 'length'}), '')

    def test_fallback_requires_terminal_standalone_answer(self):
        self.assertEqual(answer_text({'text': '', 'reasoning': 'Thinking\nAnswer: dehydration', 'finish_reason': 'stop'}), 'dehydration')
        self.assertEqual(answer_text({'text': '', 'reasoning': 'Classic riddle: Answer: his parachute failed', 'finish_reason': 'stop'}), '')
        self.assertEqual(answer_text({'text': '', 'reasoning': 'Answer: a parachute\nBut that was the old riddle.', 'finish_reason': 'stop'}), '')

    def test_visible_answer_remains_scorable_even_at_token_cap(self):
        self.assertEqual(answer_text({'text': 'Answer: dehydration', 'reasoning': 'irrelevant', 'finish_reason': 'length'}), 'Answer: dehydration')

    def test_empty_answers_abstain_without_judge_and_errors_stay_errors(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / 'model' / 'unwarned'
            run.mkdir(parents=True)
            item = {'id': 'x', 'text': 'An autopsy says dehydration. What killed him?', 'source': 's',
                    'answer': 'dehydration', 'aliases': [], 'original_answer': 'a parachute', 'original_aliases': [], 'type': 'stated'}
            items = {'x': item}
            path = Path(td) / 'items.jsonl'
            path.write_text(json.dumps(item) + '\n')
            replies = [
                {'text': '', 'reasoning': None, 'finish_reason': 'length', 'error': None},
                {'text': '   ', 'reasoning': None, 'finish_reason': 'stop', 'error': None},
                {'text': '', 'reasoning': None, 'finish_reason': None, 'error': 'timeout'},
            ]
            rows = [{'unit_id': 'x', 'sample': n, 'text_sha': hashlib.sha256(item['text'].encode()).hexdigest()[:16], 'reply': r} for n, r in enumerate(replies)]
            (run / 'raw.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            with patch('altered_riddles.score.judge_rows', side_effect=AssertionError('No judge calls allowed')):
                score_altered(run, items, 'jalapeno:DeepSeek-V4-Flash-0731', 1, path)
            scored = [json.loads(l) for l in (run / 'scored.jsonl').read_text().splitlines()]
            self.assertEqual([r['label'] for r in scored], ['abstain', 'abstain', 'error'])
            summary = json.loads((run / 'scored_summary.json').read_text())
            self.assertEqual(summary['overall']['correct'], 0)
            self.assertEqual(summary['overall']['abstain'], 1)
            self.assertEqual(summary['scoring']['scorer_version'], SCORER_VERSION)


if __name__ == '__main__':
    unittest.main()
