"""Offline checks for the versioned, budget-bounded Core repair workflow."""
import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from altered_riddles.gate import load_items
from altered_riddles.llm import Reply
from altered_riddles.probe import load_sources

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('repair_execution', ROOT / 'results/audit/adjudication-v2/execute.py')
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


class RepairWorkflowTests(unittest.TestCase):
    def test_eight_replacements_are_isolated_and_aliases_disjoint(self):
        candidates = ROOT / 'data/revisions/core-approved-v1.yaml'
        raw = yaml.safe_load(candidates.read_text())
        sources = {s['id']: s for s in load_sources(ROOT / 'data/sources.yaml')}
        validated = load_items(str(candidates), sources)
        active = {r['id'] for r in map(json.loads, (ROOT / 'data/gated.jsonl').read_text().splitlines())}
        self.assertEqual(len(validated), 8)
        self.assertFalse({r['id'] for r in validated} & active)
        for r in raw:
            self.assertIn(r['replaces'], active)
            self.assertEqual(r['id'], r['replaces'] + '-r1')
        self.assertNotIn('last-brick-2-r1', {r['id'] for r in raw})

    def test_label_provenance_is_not_claimed_as_human_agreement(self):
        audit = json.loads((ROOT / 'results/audit/adjudication-v2/label_audit.json').read_text())
        self.assertEqual(audit['ai_blind_labels'], 43)
        self.assertEqual(audit['independent_owner_labels_remaining'], 1)
        self.assertEqual(audit['owner_approved_ai_correction'], 1)
        self.assertEqual(len(audit['rows']), 45)
        self.assertEqual(sum(not r['agrees_with_new_judge'] for r in audit['rows']), 13)

    def test_budget_rejects_before_reservation_and_retains_unknown_usage(self):
        with tempfile.TemporaryDirectory() as td, patch.object(workflow, 'ROOT', Path(td)):
            budget = workflow.Budget()
            entry, prices = budget.reserve('jalapeno', 'DeepSeek-V4-Flash-0731', [], 200)
            reply = Reply('DeepSeek-V4-Flash-0731', '', None, None, None, None, None, 0, 1, 'timeout')
            budget.settle(entry, prices, reply)
            self.assertEqual(entry['charged_bound_usd'], entry['ceiling_usd'])
            budget.data['limit_usd'] = .05
            n = len(budget.data['calls'])
            with self.assertRaises(RuntimeError):
                budget.reserve('jalapeno', 'DeepSeek-V4-Flash-0731', [], 200)
            self.assertEqual(len(budget.data['calls']), n)

    def test_only_dispatch_slots_reserve_budget(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as td, patch.object(workflow, 'ROOT', Path(td)):
                budget = workflow.Budget()
                peak = 0

                async def fake_chat(client, model, messages, **kwargs):
                    nonlocal peak
                    peak = max(peak, sum(c['status'] == 'reserved' for c in budget.data['calls']))
                    await asyncio.sleep(.001)
                    return Reply(model, 'Answer: right', None, 10, 3, 0, 'stop', .001, 1)

                client = object.__new__(workflow.BoundedClient)
                client.provider = 'jalapeno'
                client._budget_sem = asyncio.Semaphore(2)
                with patch.object(workflow, 'BUDGET', budget), patch.object(workflow.Client, 'chat', fake_chat):
                    await asyncio.gather(*(client.chat('DeepSeek-V4-Flash-0731', [], max_tokens=200) for _ in range(10)))
                self.assertEqual(peak, 2)
                self.assertEqual(len(budget.data['calls']), 10)
                self.assertTrue(all(c['status'] == 'usage_estimated' for c in budget.data['calls']))
        asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
