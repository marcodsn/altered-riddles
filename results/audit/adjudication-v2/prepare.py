"""Reproduce the owner/AI adjudication snapshot and eight repair candidates (offline)."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path('results/audit/adjudication-v2')
CANDIDATES = Path('data/revisions/core-approved-v1.yaml')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def save(name, obj):
    (ROOT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


def main():
    if (ROOT / 'decisions.json').exists() or CANDIDATES.exists():
        raise SystemExit('Snapshot already exists; use a new version rather than overwrite.')
    now = datetime.now(timezone.utc).isoformat()
    sheet_path = Path('results/audit/adjudication-v1/human_review.yaml')
    label_path = Path('results/audit/rescore-v1/label_changes_sheet.yaml')
    sheet = yaml.safe_load(sheet_path.read_text())
    drafts = {r['replaces']: r for r in yaml.safe_load(Path('data/revisions/core-hard-pilot.yaml').read_text())}
    old = {r['id']: r for r in map(json.loads, Path('data/gated.jsonl').read_text().splitlines())}
    assistant_amended = {'months-28-days-1', 'hiccups-1', 'parachute-1', 'rooster-egg-2'}
    custom = {
        'parachute-1': {
            'text': 'A man is found dead in a desert beside an unopened package of sandwiches. An autopsy establishes that he died of dehydration, not an injury. What killed him?',
            'answer': 'dehydration',
            'aliases': old['parachute-1']['aliases'],
            'why_original_fails': 'The autopsy explicitly establishes dehydration, not injury, as the cause of death. A failed parachute is not the stated cause.'},
        'rooster-egg-2': {
            'text': 'A hen lays an egg on a sloping barn roof. The egg begins rolling freely under gravity, with nothing pushing it or blocking its path. Does it roll uphill or downhill?',
            'answer': 'downhill', 'aliases': ['down the slope', 'down the roof', 'down'],
            'why_original_fails': 'The egg is laid by a hen, and the question asks the direction of its free rolling under gravity. Roosters not laying eggs does not answer that question.'},
    }
    decisions, candidates = [], []
    for row in sheet:
        iid = row['id']
        assert text_sha(old[iid]['text']) == row['text_sha16']
        assert row['disposition'] in {'keep', 'r1', 'other'}
        revise = row['disposition'] != 'keep'
        decision = {
            'id': iid, 'text_sha16': row['text_sha16'],
            'disposition': 'revise-and-rerun' if revise else 'keep',
            'replacement': iid + '-r1' if revise else None,
            'reason': row['reason'],
            'reviewer': 'owner (chat user)',
            'recorded_at': now,
            'review_date': None,
            'review_date_note': 'Exact original review time unavailable; recorded_at is snapshot creation, not a fabricated review date.',
            'provenance': ('AI-recommended amendment, accepted by owner in chat (alright fix them; do 1-4)' if iid in assistant_amended
                           else 'Owner-authored adjudication sheet, retained'),
            'independent_human_review_of_rewrite': False if iid in assistant_amended else None,
        }
        if revise:
            d = custom.get(iid) or drafts[iid]
            candidate = {
                'id': iid + '-r1', 'replaces': iid, 'source': old[iid]['source'],
                'type': old[iid]['type'], 'status': 'owner_approved_pending_validation',
                'human_review': 'owner_approved_ai_authored_rewrite',
                'text': d['text'], 'answer': d['answer'], 'aliases': d['aliases'],
                'why_original_fails': d['why_original_fails'],
                'note': 'Prospective Core repair; not assumed Hard. New text requires fresh runs.',
            }
            candidates.append(candidate)
            decision['replacement_text_sha16'] = text_sha(candidate['text'])
        decisions.append(decision)
    d = yaml.safe_load(Path('data/revisions/cat-fur-v1.yaml').read_text())[0]
    candidates.append({
        'id': d['id'], 'replaces': d['replaces'], 'source': d['source'],
        'type': old[d['replaces']]['type'], 'status': 'owner_approved_pending_validation',
        'human_review': d['human_review'], 'text': d['text'], 'answer': d['answer'],
        'aliases': d['aliases'], 'why_original_fails': d['why_original_fails'],
        'note': d['tradeoff'],
    })
    decisions.append({
        'id': d['replaces'], 'text_sha16': text_sha(old[d['replaces']]['text']),
        'disposition': 'revise-and-rerun', 'replacement': d['id'],
        'replacement_text_sha16': text_sha(d['text']), 'reason': d['why_original_fails'],
        'reviewer': 'owner (chat user)', 'recorded_at': now, 'review_date': None,
        'provenance': 'AI-authored explicit left/right rewrite approved by owner in chat (do it)',
        'independent_human_review_of_rewrite': False,
    })
    assert len(candidates) == 8 and len(decisions) == 12
    CANDIDATES.write_text('# Owner-approved AI-authored repairs; validation and fresh runs required. NOT active Core.\n' + yaml.safe_dump(candidates, sort_keys=False, allow_unicode=True, width=100))
    save('decisions.json', {
        'status': 'Owner decisions consolidated; replacement validation and runs pending',
        'recorded_at': now, 'standard': 'Strict entailment under ordinary readings; original wrong as an answer',
        'historical_data_changed': False,
        'inputs': {str(p): sha(p) for p in [sheet_path, CANDIDATES, Path('data/gated.jsonl')]},
        'decisions': decisions,
        'remaining_core': {'count': 252, 'reviewer': 'AI coding assistant, not human',
                           'evidence': 'results/audit/validity-pass-v1/dispositions.jsonl'},
    })
    labels = yaml.safe_load(label_path.read_text())
    machine = list(map(json.loads, Path('results/audit/rescore-v1/label_changes.jsonl').read_text().splitlines()))
    assert len(labels) == len(machine) == 45
    audit = []
    for row, m in zip(labels, machine):
        assert row['item'] == m['unit_id'] and row['model_answer'] == m['final']
        assert row['human_label'] in {'correct', 'original', 'other', 'abstain'}
        provenance = ('owner initial judgment, later changed to AI recommendation with explicit owner approval' if row['n'] == 0
                      else 'owner initial judgment, unchanged' if row['n'] == 1
                      else 'AI blind judgment; NOT an independent human label')
        audit.append({**m, 'n': row['n'], 'review_label': row['human_label'],
                      'label_provenance': provenance, 'agrees_with_new_judge': row['human_label'] == m['new_label']})
    save('label_audit.json', {
        'recorded_at': now, 'sheet_sha256': sha(label_path),
        'notice': 'Legacy field human_label contains mixed provenance. This is not a 45-row independent human audit and must not be reported as judge-human agreement.',
        'independent_owner_labels_remaining': 1,
        'ai_blind_labels': 43, 'owner_approved_ai_correction': 1,
        'descriptive_mixed_provenance_agreement': sum(r['agrees_with_new_judge'] for r in audit) / len(audit),
        'counts': dict(Counter(r['review_label'] for r in audit)),
        'rows': audit,
    })
    print(f'Staged {len(candidates)} repairs; consolidated {len(decisions)} decisions and {len(audit)} labels.')


if __name__ == '__main__':
    main()
