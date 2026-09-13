"""Prospective all-eight-repair cap diagnostic. Free Nous only; no paid fallback.
Run from the repository root. First invocation only: refuses existing run data.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from altered_riddles import run, score

ROOT = Path('results/audit/cap-sensitivity-v1')
RUNS = Path('runs/cap-sensitivity-v1')
ITEMS = Path('results/audit/adjudication-v2/repairs.gated.jsonl')
MODEL = 'meituan/longcat-2.0:free'
DRIVER = Path('results/audit/adjudication-v2/execute.py')


def save(name, data):
    (ROOT / name).write_text(json.dumps(data, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def main():
    if RUNS.exists() or (ROOT / 'specification.json').exists():
        raise SystemExit('Existing experiment; inspect evidence before an explicit resume/new version')
    # Authentication is used only in memory; persist only public catalog metadata.
    request = urllib.request.Request('https://inference-api.nousresearch.com/v1/models',
        headers={'Authorization': 'Bearer ' + os.environ['NOUS_API_KEY']})
    with urllib.request.urlopen(request, timeout=30) as response:
        models = json.load(response)['data']
    route = next(m for m in models if m['id'] == MODEL)
    assert float(route['pricing']['prompt']) == float(route['pricing']['completion']) == 0
    save('routes.json', {'checked_at': datetime.now(timezone.utc).isoformat(),
        'providers': {'nous': {'selected': {MODEL: route}}}})
    # Reuse the already regression-tested one-attempt transport and budget ledger.
    spec = importlib.util.spec_from_file_location('cap_bounded_driver', DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    driver.ROOT = ROOT
    driver.BUDGET = driver.Budget()
    driver.BUDGET.data.update(limit_usd=0.0, prior_phase_reserve_usd=0.0,
        price_evidence='routes.json: exact Nous :free route verified at zero input/output price',
        accounting='Zero-dollar route only; every request reserved and recorded. No paid fallback.')
    driver.PRICES = {}  # fail closed on every Jalapeno/paid dispatch
    run.Client = driver.BoundedClient
    items = [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]
    assert len(items) == 8
    save('specification.json', {
        'recorded_before_inference': datetime.now(timezone.utc).isoformat(),
        'status': 'development cap sensitivity, not replacement leaderboard results',
        'model': 'nous:' + MODEL, 'items': [it['id'] for it in items],
        'items_sha256': sha(ITEMS), 'baseline_cap': 16000, 'new_cap': 64000,
        'conditions': ['unwarned', 'warned'], 'samples': 5, 'planned_responses': 80,
        'thinking': 'on', 'temperature': None, 'attempts_per_request': 1,
        'selection': 'all eight approved repairs, not only prior truncations',
        'policy': 'docs/CORE_RELEASE_POLICY.md', 'policy_sha256': sha('docs/CORE_RELEASE_POLICY.md'),
        'driver_sha256': sha(DRIVER), 'run_code_sha256': sha('altered_riddles/run.py'),
        'script_sha256': sha(__file__), 'limit_usd': 0,
    })
    directories = []
    for condition in ['unwarned', 'warned']:
        save('status.json', {'status': 'running', 'condition': condition})
        args = argparse.Namespace(model='nous:' + MODEL, thinking='on', condition=condition,
            samples=5, temperature=None, max_tokens=64000, items=str(ITEMS),
            passed_only=True, limit=0, concurrency=4, rpm=60, timeout=1800,
            retries=1, runs_dir=str(RUNS))
        await run.run(args)
        directory = RUNS / run.sanitize('nous_' + MODEL) / f'{condition}-thinkon-k5-cap64000'
        directories.append(str(directory))
        # No judge provided: ambiguous answers stay pending, never guessed as correct.
        score.score_altered(directory, score.load_items(ITEMS), None, 1, ITEMS)
    save('run_manifest.json', {'runs': directories})
    save('status.json', {'status': 'complete', 'runs': directories,
        'notice': 'Deterministic scoring only. Judge-pending answers are unresolved; no board replacement.'})


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        save('status.json', {'status': 'blocked', 'error_type': type(exc).__name__,
                            'notice': 'Inspect local execution log; no automatic fallback or restart.'})
        raise
