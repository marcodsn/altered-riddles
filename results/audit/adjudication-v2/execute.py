"""Bounded, versioned repair workflow. Run from repository root with .venv/bin/python.

No provider fallback. One attempt per request (including no stream-options retry).
Existing prompts, temperatures, token caps, sample counts and gate models retained.
Budget reserves each in-flight call's conservative token ceiling before dispatch;
unknown/failed usage retains that full reservation. Prior phase reserve: USD .05.
"""
import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Permit direct execution of this audit-local script from the repository root.
sys.path.insert(0, str(Path.cwd()))
from altered_riddles import gate, run, score, board
from altered_riddles.llm import Client
from altered_riddles.probe import load_sources

ROOT = Path('results/audit/adjudication-v2')
RUNS = Path('runs/core-repairs-v1')
ITEMS = ROOT / 'repairs.gated.jsonl'
CANDIDATES = Path('data/revisions/core-approved-v1.yaml')
PRICES = {
    'DeepSeek-V4-Flash-0731': (0.088, 0.264),
    'GLM-5.3-Flash': (0.075, 0.250),
    'Qwen3-Next-80B-A3B-Thinking': (0.150, 1.500),
    'Qwen3.5-35B-A3B': (0.250, 2.000),
}


def read_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


def log_state(phase, status, **kw):
    save(ROOT / 'execution_status.json', {'phase': phase, 'status': status,
         'at': datetime.now(timezone.utc).isoformat(), **kw})


class Budget:
    def __init__(self):
        self.path = ROOT / 'budget.json'
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {
            'limit_usd': 1.0, 'prior_phase_reserve_usd': 0.05, 'calls': [],
            'price_evidence': 'PLAN.md section 6, owner-supplied Jalapeno prices 2026-09-04; routes.json confirms availability but Jalapeno exposes no live prices.',
            'accounting': 'Conservative estimate, not billing receipt. Reserve UTF-8 message bytes + 4096 input tokens and twice max_tokens output tokens. Settle prompt + completion + reasoning (may double-count reasoning). Unknown usage/error retains full ceiling.',
            'attempts_per_call': 1, 'no_provider_fallback': True,
        }

    def reserve(self, provider, model, messages, max_tokens):
        if provider == 'nous':
            routes = json.loads((ROOT / 'routes.json').read_text())
            detail = routes['providers']['nous']['selected'][model]
            assert model.endswith(':free')
            assert float(detail['pricing']['prompt']) == float(detail['pricing']['completion']) == 0
            prices = (0, 0)
        else:
            assert provider == 'jalapeno' and model in PRICES
            prices = PRICES[model]
        input_bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 4096
        ceiling = (input_bound * prices[0] + 2 * max_tokens * prices[1]) / 1e6
        used = self.data['prior_phase_reserve_usd'] + sum(c['charged_bound_usd'] for c in self.data['calls'])
        if len(self.data['calls']) >= 1200 or used + ceiling > self.data['limit_usd']:
            raise RuntimeError(f'Budget blocked before dispatch: used/reserved={used:.6f}, next ceiling={ceiling:.6f}')
        entry = {'n': len(self.data['calls']), 'provider': provider, 'model': model,
                 'prompt_sha256': hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
                 'input_token_bound': input_bound, 'max_tokens': max_tokens,
                 'ceiling_usd': ceiling, 'charged_bound_usd': ceiling, 'status': 'reserved'}
        self.data['calls'].append(entry)
        save(self.path, self.data)
        return entry, prices

    def settle(self, entry, prices, reply):
        d = reply.as_dict()
        entry.update({k: d[k] for k in ['prompt_tokens', 'completion_tokens', 'reasoning_tokens', 'attempts', 'finish_reason', 'error']})
        reliable = not reply.error and reply.prompt_tokens is not None and reply.completion_tokens is not None
        cost = ((reply.prompt_tokens or 0) * prices[0] +
                ((reply.completion_tokens or 0) + (reply.reasoning_tokens or 0)) * prices[1]) / 1e6
        if reliable and cost <= entry['ceiling_usd']:
            entry['charged_bound_usd'] = cost
            entry['status'] = 'usage_estimated'
        else:
            entry['status'] = 'full_ceiling_retained'
        save(self.path, self.data)
        if cost > entry['ceiling_usd']:
            raise RuntimeError('Provider usage exceeds conservative ceiling; stop for budget review')


BUDGET = None


class BoundedClient(Client):
    def __init__(self, provider, **kw):
        kw.update(retries=1, timeout=1800, idle_timeout=300)
        super().__init__(provider, **kw)
        self._budget_sem = asyncio.Semaphore(kw.get('concurrency', 4))

    async def _stream_once(self, kwargs):
        # Request usage, but unlike the shared client do NOT retry without stream_options.
        stream = await self._client.chat.completions.create(
            **dict(kwargs, stream=True, stream_options={'include_usage': True}))
        text, reasoning, usage, finish = [], [], None, None
        iterator = stream.__aiter__()
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(iterator.__anext__(), self.idle_timeout)
                except StopAsyncIteration:
                    break
                if getattr(chunk, 'usage', None):
                    usage = chunk.usage
                if chunk.choices:
                    choice = chunk.choices[0]
                    delta = getattr(choice, 'delta', None)
                    if delta is not None:
                        if getattr(delta, 'content', None):
                            text.append(delta.content)
                        r = getattr(delta, 'reasoning_content', None) or getattr(delta, 'reasoning', None)
                        if r is None and getattr(delta, 'model_extra', None):
                            r = delta.model_extra.get('reasoning_content') or delta.model_extra.get('reasoning')
                        if r:
                            reasoning.append(r)
                    finish = getattr(choice, 'finish_reason', None) or finish
        finally:
            await stream.close()
        return ''.join(text), (''.join(reasoning) or None), usage, finish

    async def chat(self, model, messages, **kw):
        # Reserve only calls that have a dispatch slot, not the entire queued workload.
        async with self._budget_sem:
            entry, prices = BUDGET.reserve(self.provider, model, messages, kw['max_tokens'])
            if self.provider == 'nous':
                kw['extra_body'] = {**kw.get('extra_body', {}), 'tags': ['user=marcodsn']}
            reply = await super().chat(model, messages, **kw)
            BUDGET.settle(entry, prices, reply)
            print(f"call {entry['n']}: {self.provider}:{model} {entry['status']} error={bool(reply.error)}", flush=True)
            return reply


def offline():
    sources = {s['id']: s for s in load_sources(Path('data/sources.yaml'))}
    items = gate.load_items(str(CANDIDATES), sources)
    import yaml
    authored = {i['id']: i for i in yaml.safe_load(CANDIDATES.read_text())}
    for it in items:
        it['replaces'] = authored[it['id']]['replaces']
    # load_items rejects duplicate IDs, missing fields, invalid types and normalized alias overlap.
    assert len(items) == 8
    save(ROOT / 'offline_validation.json', {
        'reviewer': 'AI coding assistant; not an independent human review',
        'candidate_sha256': sha(CANDIDATES),
        'checks': ['8 unique new IDs', 'known sources/types', 'required fields present',
                   'no normalized accepted/original alias overlap', 'replaces links retained'],
        'items': [{
            'id': it['id'], 'text_sha16': hashlib.sha256(it['text'].encode()).hexdigest()[:16],
            'premises_consistent_under_ordinary_readings': True,
            'accepted_answer_entailed_under_ordinary_readings': True,
            'original_excluded_as_answer': True,
            'reason': it['why_original_fails'],
            'limitations': ('Gravity-driven rolling assumes an ordinary roof and no initial uphill impulse; direction choice is explicit.' if it['id'] == 'rooster-egg-2-r1'
                            else 'Explicit cause-of-death statement relies on the stated autopsy finding.' if it['id'] == 'parachute-1-r1'
                            else 'Validity repair/Core control; no Hard-difficulty claim.'),
        } for it in items],
    })
    (ROOT / 'repairs.input.jsonl').write_text(''.join(json.dumps(it, ensure_ascii=False) + '\n' for it in items))
    return items


def do_gate():
    offline()
    args = argparse.Namespace(
        sources='data/sources.yaml', crawsome=None, items=str(CANDIDATES), limit=0,
        models=list(PRICES), provider='jalapeno', concurrency=4, rpm=60, timeout=1800,
        cache=str(ROOT / 'gate_cache.jsonl'), invalidation=True, cached_only=False,
        min_pass=3, out=str(ITEMS))
    asyncio.run(gate.run(args))
    rows = read_jsonl(ITEMS)
    inputs = {it['id']: it for it in read_jsonl(ROOT / 'repairs.input.jsonl')}
    for row in rows:
        row['replaces'] = inputs[row['id']]['replaces']
    ITEMS.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    errors = [r for r in read_jsonl(ROOT / 'gate_cache.jsonl')
              if r['reply'].get('error') or r['reply'].get('finish_reason') == 'length']
    failures = [r['id'] for r in rows if not r['gate']['passed']]
    if errors or failures:
        raise RuntimeError(f'Gate unresolved: {len(errors)} error/truncated replies; failed items={failures}. Review before evaluation.')
    log_state('gate', 'awaiting_AI_reasoning_review', passed=len(rows))


def run_args(cfg, items=ITEMS, runs_dir=RUNS):
    return argparse.Namespace(model=f"{cfg['provider']}:{cfg['model']}", items=str(items),
        passed_only=True, limit=0, thinking=cfg['thinking'], condition=cfg['condition'],
        samples=cfg['samples'], runs_dir=str(runs_dir), temperature=cfg['temperature'],
        concurrency=4, retries=1, rpm=60, timeout=1800)


def fresh_manifest():
    history = json.loads(Path('results/v2/leaderboard.json').read_text())['run_manifest']
    # The historical board repeats shared familiarity dirs; explicit input must deduplicate them.
    return list(dict.fromkeys(history))


def do_evaluate():
    approval = ROOT / 'gate_reasoning_review.json'
    if not approval.exists() or not json.loads(approval.read_text()).get('proceed_to_evaluation'):
        raise RuntimeError('Inspect gate reasoning and record AI review before evaluation; votes are not adjudication.')
    if not all(r['gate']['passed'] for r in read_jsonl(ITEMS)):
        raise RuntimeError('Not all eight repairs passed; no silent item filtering')
    jobs = []
    for historical in fresh_manifest():
        cfg = json.loads((Path(historical) / 'config.json').read_text())
        args = run_args(cfg)
        out = RUNS / run.sanitize(f"{cfg['provider']}_{cfg['model']}") / f"{cfg['condition']}-think{cfg['thinking']}-k{cfg['samples']}"
        jobs.append((cfg, args, out, historical))
    save(ROOT / 'fresh_run_manifest.json', {'runs': [str(x[2]) for x in jobs],
         'historical_settings_from': [x[3] for x in jobs], 'items_file': str(ITEMS),
         'deviations': ['One attempt per call, not eight; concurrency 4, RPM 60; Nous owner tag included.',
                        'Fresh original/familiarity for all eight repaired sources; original source-admission probe is unchanged.'],
         'no_historical_answers_for_new_text': True})
    for cfg, args, out, historical in jobs:
        log_state('evaluate', 'running', current_run=str(out))
        asyncio.run(run.run(args))
        summ = json.loads((out / 'summary.json').read_text())
        if summ['errors'] or summ['n_rows'] != summ['n_expected']:
            raise RuntimeError(f'Unresolved fresh run {out}; no automatic retry or provider substitution')
        items = score.load_items(ITEMS)
        if cfg['condition'] == 'original':
            score.score_original(out, items, ITEMS)
        else:
            score.score_altered(out, items, 'jalapeno:DeepSeek-V4-Flash-0731', 4, ITEMS)
            if any(r['label'] not in score.JUDGE_LABELS for r in read_jsonl(out / 'scored.jsonl')):
                raise RuntimeError(f'Unresolved score labels in {out}')
    log_state('evaluate', 'complete', n_runs=len(jobs))


def main():
    global BUDGET
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['offline', 'gate', 'evaluate'])
    args = parser.parse_args()
    BUDGET = Budget()
    gate.Client = run.Client = score.Client = BoundedClient
    try:
        log_state(args.phase, 'running')
        {'offline': offline, 'gate': do_gate, 'evaluate': do_evaluate}[args.phase]()
    except BaseException as exc:
        log_state(args.phase, 'blocked', error=f'{type(exc).__name__}: {exc}')
        raise


if __name__ == '__main__':
    main()
