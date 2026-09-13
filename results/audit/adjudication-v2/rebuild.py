"""Offline-only candidate-board rebuild from explicitly selected old + fresh runs.

Historical rows are reused ONLY for unchanged text. Eight new IDs use fresh raw
outputs, and familiarity for their eight sources is replaced with fresh probes.
Everything is written into new derived directories; nothing is promoted/frozen.
"""
import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from altered_riddles import board, run, score

ROOT = Path('results/audit/adjudication-v2')
DERIVED = Path('runs/core-candidate-v1')


def rows(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


class OfflineClient:
    def __init__(self, *args, **kwargs):
        pass

    async def chat(self, *args, **kwargs):
        raise RuntimeError('Offline rebuild requested an uncached call; stop rather than incur inference')


def render(items_path, manifest, out):
    items = score.load_items(items_path)
    result = board.build(items, DERIVED, 2000, 0, manifest)
    result['release_status'] = 'development candidate; not frozen or publication-approved'
    result['label_audit'] = str(ROOT / 'label_audit.json')
    result['label_audit_warning'] = '13 mixed-provenance review/judge disagreements remain; no independent 45-row human agreement claim.'
    save(out / 'leaderboard.json', result)
    (out / 'LEADERBOARD.md').write_text('# Development candidate — NOT a release\n\n' + board.render_md(result))
    return result


def main():
    if DERIVED.exists() or (ROOT / 'core.candidate.jsonl').exists():
        raise SystemExit('Derived version exists; use a new version instead of overwriting.')
    historical_hashes = json.loads((ROOT / 'historical_hashes.json').read_text())
    assert all(sha(p) == h for p, h in historical_hashes.items()), 'Historical files changed before rebuild'
    fresh_doc = json.loads((ROOT / 'fresh_run_manifest.json').read_text())
    repairs_path = ROOT / 'repairs.gated.jsonl'
    repairs = rows(repairs_path)
    assert len(repairs) == 8 and all(r['gate']['passed'] for r in repairs)
    replaced = {r['replaces'] for r in repairs}
    repaired_sources = {r['source'] for r in repairs}
    originals = rows('data/gated.jsonl')
    old_passed = [r for r in originals if r.get('gate', {}).get('passed', True)]
    core = [r for r in old_passed if r['id'] not in replaced] + repairs
    assert len(core) == len(old_passed) == 264
    items_path = ROOT / 'core.candidate.jsonl'
    items_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in core))
    items = {r['id']: r for r in core}
    current_originals = {r['source']: r['original_text'] for r in core}
    manifests, lineage = [], []
    run.Client = score.Client = OfflineClient
    for fresh_dir, historical_dir in zip(fresh_doc['runs'], fresh_doc['historical_settings_from']):
        fresh, historical = Path(fresh_dir), Path(historical_dir)
        cfg = json.loads((fresh / 'config.json').read_text())
        hist_cfg = json.loads((historical / 'config.json').read_text())
        for k in ['provider', 'model', 'thinking', 'condition', 'samples', 'temperature', 'max_tokens', 'prompt']:
            assert cfg[k] == hist_cfg[k], (fresh, k)
        fresh_rows = score.latest_rows(fresh / 'raw.jsonl')
        expected_new = repaired_sources if cfg['condition'] == 'original' else {r['id'] for r in repairs}
        assert {(r['unit_id'], r['sample']) for r in fresh_rows} == {(u, s) for u in expected_new for s in range(cfg['samples'])}
        assert all(not r['reply'].get('error') for r in fresh_rows)
        old_rows = score.latest_rows(historical / 'raw.jsonl')
        if cfg['condition'] == 'original':
            kept = [r for r in old_rows if r['unit_id'] in current_originals and r['unit_id'] not in repaired_sources]
            texts = current_originals
        else:
            kept = [r for r in old_rows if r['unit_id'] in items and r['unit_id'] not in expected_new]
            texts = {u: it['text'] for u, it in items.items()}
        merged = kept + fresh_rows
        assert len(merged) == len(texts) * cfg['samples']
        assert len({(r['unit_id'], r['sample']) for r in merged}) == len(merged)
        for r in merged:
            assert r['text_sha'] == hashlib.sha256(texts[r['unit_id']].encode()).hexdigest()[:16]
        target = DERIVED / fresh.parent.name / fresh.name
        target.mkdir(parents=True)
        (target / 'raw.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in merged))
        # Reuse only exact prompt-hash judge cache entries; score.judge_rows verifies its keys.
        cache_lines = []
        for parent in [historical, fresh]:
            p = parent / 'judge_cache.jsonl'
            if p.exists():
                cache_lines.extend(p.read_text().splitlines())
        if cache_lines:
            (target / 'judge_cache.jsonl').write_text('\n'.join(cache_lines) + '\n')
        args = argparse.Namespace(model=f"{cfg['provider']}:{cfg['model']}", items=str(items_path),
            passed_only=True, limit=0, thinking=cfg['thinking'], condition=cfg['condition'],
            samples=cfg['samples'], runs_dir=str(DERIVED), temperature=cfg['temperature'],
            concurrency=4, retries=1, rpm=60, timeout=1800)
        # Every expected raw row is present. OfflineClient is a hard no-inference guard.
        asyncio.run(run.run(args))
        composed_cfg = json.loads((target / 'config.json').read_text())
        composed_cfg['derived_run'] = True
        composed_cfg['derivation_note'] = 'started_at is composition time, not a claim that old replies were generated anew; consult lineage.json for original timestamps.'
        composed_cfg['raw_lineage'] = str(target / 'lineage.json')
        save(target / 'config.json', composed_cfg)
        ancestry = {
            'historical': {'run': str(historical), 'raw_sha256': sha(historical / 'raw.jsonl'),
                           'config_sha256': sha(historical / 'config.json'), 'retained_samples': len(kept)},
            'fresh': {'run': str(fresh), 'raw_sha256': sha(fresh / 'raw.jsonl'),
                      'config_sha256': sha(fresh / 'config.json'), 'retained_samples': len(fresh_rows)},
            'sample_origin': [{'unit_id': r['unit_id'], 'sample': r['sample'], 'run': str(origin)}
                              for origin, rr in [(historical, kept), (fresh, fresh_rows)] for r in rr],
            'historical_texts_unchanged': True,
        }
        save(target / 'lineage.json', ancestry)
        if cfg['condition'] == 'original':
            score.score_original(target, items, items_path)
        else:
            score.score_altered(target, items, 'jalapeno:DeepSeek-V4-Flash-0731', 4, items_path)
            assert all(r['label'] in score.JUDGE_LABELS for r in rows(target / 'scored.jsonl'))
        manifests.append(str(target))
        lineage.append({'derived': str(target), 'historical': str(historical), 'fresh': str(fresh)})
    save(ROOT / 'candidate_run_manifest.json', {'runs': manifests, 'items_file': str(items_path), 'lineage': lineage})
    render(repairs_path, fresh_doc['runs'], ROOT / 'repairs-board')
    result = render(items_path, manifests, ROOT / 'core-board')
    save(ROOT / 'rebuild_summary.json', {
        'n_items': len(core), 'n_repaired_items': len(repairs), 'n_runs': len(manifests),
        'historical_raw_outputs_unchanged': True,
        'n_board_rows': len(result.get('rows', [])), 'excluded': result.get('excluded', []),
        'publication_approved': False,
    })
    assert all(sha(p) == h for p, h in historical_hashes.items()), 'Historical files changed during rebuild'
    print('Built versioned development candidate; historical data and results/v2 unchanged.')


if __name__ == '__main__':
    from datetime import datetime, timezone
    try:
        save(ROOT / 'execution_status.json', {'phase': 'rebuild', 'status': 'running', 'at': datetime.now(timezone.utc).isoformat()})
        main()
    except BaseException as exc:
        save(ROOT / 'execution_status.json', {'phase': 'rebuild', 'status': 'blocked', 'at': datetime.now(timezone.utc).isoformat(), 'error': f'{type(exc).__name__}: {exc}'})
        raise
    else:
        save(ROOT / 'execution_status.json', {'phase': 'steps_1_to_4', 'status': 'complete', 'at': datetime.now(timezone.utc).isoformat(), 'release_ready': False, 'remaining': ['13 mixed-provenance label disagreements', 'comparison policy and final freeze/release checks']})
