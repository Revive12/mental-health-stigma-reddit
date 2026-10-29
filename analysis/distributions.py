#!/usr/bin/env python3
"""Report preprocessing counts, subreddit coverage, and labeled-corpus distributions.

The labels report includes post-level stigma prevalence, pooled comment-level
prevalence, seven-attribution composition, and descriptive Pearson tests.
The comment-level composition test does not account for within-post dependence.
"""
from __future__ import annotations
import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path
from build_edges import LABELS, community_type, iter_posts, edges_for_post

MONTH_RE = re.compile(r'^\d{4}-\d{2}$')
META_FILES = {'stage3_length': 'length_filter_metadata.json', 'stage4_top16': 'top16_filter_metadata.json',
    'stage4c_filter': 'prefilter_metadata.json', 'stage5_bot': 'bot_detection_metadata.json',
    'stage6_clean': 'cleaning_metadata.json', 'stage7_trees': 'trees_metadata.json'}


def data_root(argument):
    return Path(argument or os.environ.get('MH_DATA_ROOT', './data')).resolve()


def months_under(root, stage):
    parent = root / 'pipeline_data' / stage
    return sorted(p.name for p in parent.iterdir() if p.is_dir() and MONTH_RE.fullmatch(p.name)) if parent.is_dir() else []


def mode_funnel(root):
    results = {}
    for stage, filename in META_FILES.items():
        totals, missing, found = Counter(), [], 0
        for month in months_under(root, stage):
            path = root / 'pipeline_data' / stage / month / filename
            if not path.exists():
                missing.append(month); continue
            record = json.loads(path.read_text())
            # Report only numeric counts; elapsed times and settings are not additive counts.
            for key, value in record.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    totals[key] += value
            found += 1
        results[stage] = {'metadata_files_found': found, 'months_missing_metadata': missing,
            'summed_integer_fields': dict(totals) if found else None}
    return results


def iter_sub_events(path):
    """Parse the top-level JSON field; nested crossposts and whitespace are irrelevant."""
    with path.open(encoding='utf-8') as handle:
        for number, line in enumerate(handle, 1):
            value = json.loads(line).get('subreddit')
            if not isinstance(value, str) or not value:
                raise ValueError(f'{path.name}, line {number}: missing subreddit')
            yield value.lower()


def mode_subreddit(root, stage):
    folder = 'stage4c_filter' if stage == '4c' else 'stage4_top16'
    post_file = 'posts_prefiltered.jsonl' if stage == '4c' else 'posts_top16.jsonl'
    comment_file = 'comments_prefiltered.jsonl' if stage == '4c' else 'comments_top16.jsonl'
    months = months_under(root, folder)
    if not months:
        raise ValueError(f'No month directories under {root / "pipeline_data" / folder}')
    posts, comments = Counter(), Counter()
    for month in months:
        base = root / 'pipeline_data' / folder / month
        posts.update(iter_sub_events(base / post_file))
        comments.update(iter_sub_events(base / comment_file))
    return [{'subreddit': sub, 'posts': posts[sub], 'comments': comments[sub],
        'comments_per_post': comments[sub] / posts[sub] if posts[sub] else None}
        for sub in sorted(posts.keys() | comments.keys())]


def pearson_test(table):
    import numpy as np
    from scipy.stats import chi2_contingency
    table = np.asarray(table, dtype=int)
    table = table[:, table.sum(axis=0) > 0]
    if table.shape[1] < 2 or (table.sum(axis=1) == 0).any():
        return {'status': 'not_estimable', 'reason': 'fewer than two nonempty groups or outcomes'}
    statistic, p, df, expected = chi2_contingency(table, correction=False)
    v = np.sqrt(statistic / (table.sum() * min(table.shape[0]-1, table.shape[1]-1)))
    return {'status': 'estimated', 'chi_square': statistic, 'p_value': p, 'df': int(df),
            'cramers_v': v, 'minimum_expected_count': float(expected.min()),
            'yates_correction': False}


def label_report(path):
    groups = {name: {'posts': 0, 'posts_with_stigma': 0, 'comments': 0,
        'stigmatizing_comments': 0, 'labels': Counter({lab: 0 for lab in LABELS})}
        for name in ['ALL', 'MH', 'General']}
    subreddit_stats = {}
    for post, rows in iter_posts(path):
        # Also checks invalid graph structure and duplicate comments within a post.
        list(edges_for_post(post, rows))
        subreddit = rows[0]['subreddit'].lower()
        group = community_type(subreddit)
        labels = Counter(row['label'] for row in rows)
        stigma = sum(labels[label] for label in LABELS[:7])
        for name in ['ALL', group]:
            values = groups[name]
            values['posts'] += 1; values['comments'] += len(rows)
            values['posts_with_stigma'] += int(stigma > 0)
            values['stigmatizing_comments'] += stigma
            values['labels'].update(labels)
        stats = subreddit_stats.setdefault(subreddit, {'posts': 0, 'posts_with_stigma': 0, 'comments': 0,
            'stigmatizing_comments': 0, 'labels': Counter({lab: 0 for lab in LABELS})})
        stats['posts'] += 1; stats['posts_with_stigma'] += int(stigma > 0)
        stats['comments'] += len(rows); stats['stigmatizing_comments'] += stigma; stats['labels'].update(labels)
    for values in list(groups.values()) + list(subreddit_stats.values()):
        values['post_stigma_proportion'] = values['posts_with_stigma'] / values['posts'] if values['posts'] else None
        values['comment_stigma_proportion'] = values['stigmatizing_comments'] / values['comments'] if values['comments'] else None
        values['attribution_composition'] = {lab: values['labels'][lab] / values['stigmatizing_comments']
            if values['stigmatizing_comments'] else None for lab in LABELS[:7]}
    mh, general = groups['MH'], groups['General']
    return {'groups': groups, 'subreddits': subreddit_stats,
        'post_presence_pearson': pearson_test([[g['posts_with_stigma'], g['posts'] - g['posts_with_stigma']] for g in [mh, general]]),
        'stigma_composition_pearson': pearson_test([[g['labels'][lab] for lab in LABELS[:7]] for g in [mh, general]]),
        'note': 'Pearson composition test pools comments and does not model within-discussion dependence. H is non-stigmatizing, not a stigma attribution.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=['funnel', 'subreddit', 'labels'])
    parser.add_argument('--data-root')
    parser.add_argument('--stage', default='4', choices=['4', '4c'])
    parser.add_argument('--labeled')
    parser.add_argument('--out', help='Optional JSON destination; the report is also printed')
    args = parser.parse_args()
    if args.mode == 'funnel':
        report = mode_funnel(data_root(args.data_root))
    elif args.mode == 'subreddit':
        report = mode_subreddit(data_root(args.data_root), args.stage)
    else:
        if not args.labeled:
            parser.error('--mode labels requires --labeled')
        report = label_report(args.labeled)
    text = json.dumps(report, indent=2, allow_nan=False)
    if args.out:
        destination = Path(args.out); destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text + '\n')
    print(text)

if __name__ == '__main__':
    main()
