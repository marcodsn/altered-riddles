"""Offline-only scorer-v2 correction; never overwrite raw runs or earlier boards."""
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from altered_riddles import board, score

ROOT = Path('results/audit/adjudication-v2')


def save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rows(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


class OfflineClient:
    def __init__(self, *args, **kwargs):
        pass

    async def chat(self, *args, **kwargs):
        raise RuntimeError('Scorer repair must not make inference calls')


def correct(manifest_file, target_root, items_file, board_dir, manifest_name):
    if target_root.exists() or board_dir.exists():
        raise RuntimeError('Correction target already exists; use a new version')
    source_manifest = json.loads(manifest_file.read_text())
    items = score.load_items(items_file)
    runs, changes = [], []
    for source_path in source_manifest['runs']:
        source = Path(source_path)
        target = target_root / source.parent.name / source.name
        target.mkdir(parents=True)
        for name in ['raw.jsonl', 'config.json', 'summary.json', 'judge_cache.jsonl', 'lineage.json']:
            if (source / name).exists():
                shutil.copyfile(source / name, target / name)
        config = json.loads((target / 'config.json').read_text())
        config['score_only_derivative'] = True
        config['raw_source_dir'] = str(source)
        config['raw_source_sha256'] = sha(source / 'raw.jsonl')
        save(target / 'config.json', config)
        if config['condition'] == 'original':
            score.score_original(target, items, items_file)
        else:
            score.score_altered(target, items, 'jalapeno:DeepSeek-V4-Flash-0731', 4, items_file)
            before = {(r['unit_id'], r['sample']): r for r in rows(source / 'scored.jsonl')}
            for r in rows(target / 'scored.jsonl'):
                previous = before[(r['unit_id'], r['sample'])]
                assert r['label'] in score.JUDGE_LABELS
                if previous['label'] != r['label'] or previous['final'] != r['final']:
                    changes.append({'run': str(target), 'source_run': str(source), 'unit_id': r['unit_id'], 'sample': r['sample'],
                                    'old_label': previous['label'], 'new_label': r['label'],
                                    'old_final': previous['final'], 'new_final': r['final']})
        assert sha(target / 'raw.jsonl') == sha(source / 'raw.jsonl')
        runs.append(str(target))
    save(ROOT / manifest_name, {'runs': runs, 'items_file': str(items_file), 'scorer_version': score.SCORER_VERSION,
                               'source_manifest': str(manifest_file), 'inference_calls': 0})
    result = board.build(items, target_root, 2000, 0, runs)
    result.update(release_status='development candidate, not frozen or publication-approved',
                  scorer_version=score.SCORER_VERSION, label_audit=str(ROOT / 'label_audit.json'),
                  limitations=['13 mixed-provenance label-audit disagreements remain open.',
                               '14 fresh responses hit token caps; Longcat warned thinking-on had 11/40 truncations on repairs.',
                               'Reasoning-only truncated responses are abstentions, not answers. Raw samples retained.'])
    save(board_dir / 'leaderboard.json', result)
    (board_dir / 'LEADERBOARD.md').write_text('# Development candidate — scorer v2, NOT a release\n\n'
        'Open issues: 13 label-audit disagreements; 14 fresh token-cap stops, including 11/40 Longcat warned thinking-on repair replies.\n\n'
        + board.render_md(result))
    return {'n_runs': len(runs), 'n_rows': len(result['rows']), 'excluded': result['excluded'],
            'changes': changes, 'label_transitions': dict(Counter(r['old_label'] + ' -> ' + r['new_label'] for r in changes))}


def main():
    history = json.loads((ROOT / 'historical_hashes.json').read_text())
    assert all(sha(p) == h for p, h in history.items())
    score.Client = OfflineClient
    fresh = correct(ROOT / 'fresh_run_manifest.json', Path('runs/core-repairs-scored-v2'), ROOT / 'repairs.gated.jsonl',
                    ROOT / 'repairs-board-scorer-v2', 'fresh_run_manifest_scorer_v2.json')
    core = correct(ROOT / 'candidate_run_manifest.json', Path('runs/core-candidate-scored-v2'), ROOT / 'core.candidate.jsonl',
                   ROOT / 'core-board-scorer-v2', 'candidate_run_manifest_scorer_v2.json')
    assert all(sha(p) == h for p, h in history.items())
    save(ROOT / 'scorer_v2_correction.json', {'scorer_version': score.SCORER_VERSION,
         'reason': 'Empty replies must abstain without a judge; unfinished truncated reasoning is not a committed answer.',
         'fresh': fresh, 'core': core, 'inference_calls': 0, 'historical_files_unchanged': True,
         'code_sha256': {str(p): sha(p) for p in [Path(score.__file__), Path(board.__file__), Path(__file__)]}})
    save(ROOT / 'execution_status.json', {'phase': 'steps_1_to_4', 'status': 'complete',
         'at': datetime.now(timezone.utc).isoformat(), 'release_ready': False,
         'current_board': str(ROOT / 'core-board-scorer-v2/LEADERBOARD.md'),
         'superseded_boards': ['core-board', 'repairs-board'],
         'remaining': ['13 mixed-provenance label disagreements', 'token-cap sensitivity review', 'comparison policy and freeze/release checks']})
    print('Offline scorer-v2 correction complete; no inference or historical writes.')


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        save(ROOT / 'execution_status.json', {'phase': 'scorer_v2_correction', 'status': 'blocked', 'error': f'{type(exc).__name__}: {exc}'})
        raise
