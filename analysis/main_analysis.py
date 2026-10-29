#!/usr/bin/env python3
"""Reference implementation of the manuscript's reply-transition analyses.

This release implementation was reconstructed from the reported methods; it is
not the original production analysis script. Counts and test families are
computed from supplied data, never forced to match manuscript totals.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
from build_edges import LABELS, community_type

LABEL_INDEX = {label: i for i, label in enumerate(LABELS)}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def lsa_of(counts):
    counts = np.asarray(counts, dtype=float)
    if counts.shape != (8, 8) or np.any(~np.isfinite(counts)) or np.any(counts < 0):
        raise ValueError('LSA requires a finite, nonnegative 8-by-8 matrix')
    total = counts.sum()
    rows, cols = counts.sum(axis=1), counts.sum(axis=0)
    probability = np.divide(counts, rows[:, None], out=np.full((8, 8), np.nan), where=rows[:, None] > 0)
    if total == 0:
        return probability, np.zeros((8, 8)), np.full((8, 8), np.nan)
    expected = np.outer(rows, cols) / total
    variance = expected * (1 - rows[:, None] / total) * (1 - cols[None, :] / total)
    z = np.divide(counts - expected, np.sqrt(variance), out=np.full((8, 8), np.nan), where=variance > 0)
    return probability, expected, z


def bh_adjust(p_values):
    """Benjamini-Hochberg correction over finite values only."""
    values = np.asarray(p_values, dtype=float)
    out = np.full(values.shape, np.nan)
    valid = np.flatnonzero(np.isfinite(values))
    if not len(valid):
        return out
    order = valid[np.argsort(values[valid], kind='stable')]
    ranked = values[order] * len(order) / np.arange(1, len(order) + 1)
    out[order] = np.clip(np.minimum.accumulate(ranked[::-1])[::-1], 0, 1)
    return out


def transition_values(counts):
    counts = np.asarray(counts, float)
    rows = counts.sum(axis=-1, keepdims=True)
    probability = np.divide(counts, rows, out=np.full_like(counts, np.nan), where=rows > 0)
    total = counts.sum(axis=(-2, -1), keepdims=True)
    marginal = np.divide(counts.sum(axis=-2, keepdims=True), total,
                         out=np.full_like(counts.sum(axis=-2, keepdims=True), np.nan), where=total > 0)
    return probability, probability - marginal


def validate_edges(edges):
    required = {'post_id', 'subreddit', 'community_type', 'parent_comment', 'comment_id', 'p_label', 'c_label'}
    if not required.issubset(edges.columns):
        raise ValueError(f'Missing edge columns: {sorted(required - set(edges.columns))}')
    if edges.empty:
        raise ValueError('No eligible reply edges')
    if edges[list(required)].isna().any().any():
        raise ValueError('Missing values in required edge fields')
    if not edges.p_label.isin(LABELS).all() or not edges.c_label.isin(LABELS).all():
        raise ValueError('All labels must be exactly A-H')
    if edges.duplicated(['post_id', 'comment_id']).any():
        raise ValueError('A reply comment must have exactly one parent edge')
    if (edges.parent_comment == edges.comment_id).any():
        raise ValueError('Self-reply edges are invalid')
    expected = edges.subreddit.map(community_type)
    if not (expected == edges.community_type).all():
        raise ValueError('community_type does not match the five configured mental health subreddits')
    if (edges.groupby('post_id').community_type.nunique() > 1).any():
        raise ValueError('Inconsistent group membership within a discussion')
    entities = pd.concat([
        edges[['post_id', 'parent_comment', 'p_label']].rename(columns={'parent_comment': 'name', 'p_label': 'label'}),
        edges[['post_id', 'comment_id', 'c_label']].rename(columns={'comment_id': 'name', 'c_label': 'label'})])
    if (entities.groupby('name').post_id.nunique() > 1).any() or (entities.groupby('name').label.nunique() > 1).any():
        raise ValueError('A comment has inconsistent post membership or labels')


def load_manifest(edges, path=None):
    if path:
        posts = pd.read_csv(path, dtype={'post_id': str, 'subreddit': str, 'community_type': str})
        if not {'post_id', 'subreddit', 'community_type'}.issubset(posts.columns):
            raise ValueError('Post manifest requires post_id, subreddit, community_type')
    else:
        posts = edges[['post_id', 'subreddit', 'community_type']].drop_duplicates('post_id')
    if posts.post_id.isna().any() or posts.post_id.duplicated().any():
        raise ValueError('Post identifiers in the manifest must be nonmissing and unique')
    if not (posts.subreddit.map(community_type) == posts.community_type).all():
        raise ValueError('Invalid community type in post manifest')
    joined = edges[['post_id', 'community_type']].drop_duplicates().merge(
        posts[['post_id', 'community_type']], on='post_id', how='left', suffixes=('_edge', '_post'))
    if not (joined.community_type_edge == joined.community_type_post).all():
        raise ValueError('Every edge must match a discussion in the manifest')
    return posts.reset_index(drop=True)


def post_matrices(edges, posts, equal_parent=False):
    """One 8-by-8 table per post; every parent contributes one unit if requested."""
    result = np.zeros((len(posts), 8, 8), dtype=float)
    if edges.empty:
        return result
    positions = pd.Series(np.arange(len(posts)), index=posts.post_id)
    weights = (1 / edges.groupby(['post_id', 'parent_comment']).comment_id.transform('size')).to_numpy() if equal_parent else np.ones(len(edges))
    np.add.at(result, (edges.post_id.map(positions).to_numpy(), edges.p_label.map(LABEL_INDEX).to_numpy(),
                      edges.c_label.map(LABEL_INDEX).to_numpy()), weights)
    return result


def bootstrap_tables(matrices, n_boot, rng, strata=None):
    """Ordinary whole-post bootstrap, compressed to exact repeated table types.

Multinomial sampling of identical post tables is distributionally equivalent to
sampling individual posts with replacement, including zero-edge discussions.
"""
    if not len(matrices):
        return np.zeros((n_boot, 8, 8))
    if strata is not None:
        out = np.zeros((n_boot, 8, 8))
        for indices in strata:
            out += bootstrap_tables(matrices[indices], n_boot, rng)
        return out
    unique, counts = np.unique(matrices.reshape(len(matrices), 64), axis=0, return_counts=True)
    out = np.empty((n_boot, 64))
    probs = counts / counts.sum()
    for i in range(n_boot):
        frequencies = rng.multinomial(len(matrices), probs)
        out[i] = frequencies @ unique
    return out.reshape(n_boot, 8, 8)


def summarize_statistics(estimate, draws, source_support, pair_support, minimum_source, minimum_pair):
    """Pointwise percentile intervals; two-sided Wald p values use bootstrap SE."""
    finite = np.isfinite(draws)
    n_valid = finite.sum(axis=0)
    # Require all replicates to define a cell; sparse/undefined cells are not tested.
    valid_boot = n_valid == len(draws)
    se = np.full((8, 8), np.nan)
    lower, upper = np.full((8, 8), np.nan), np.full((8, 8), np.nan)
    if valid_boot.any():
        se[valid_boot] = draws[:, valid_boot].std(axis=0, ddof=1)
        lower[valid_boot], upper[valid_boot] = np.quantile(draws[:, valid_boot], [.025, .975], axis=0)
    eligible = (source_support[:, None] >= minimum_source) & (pair_support >= minimum_pair) & (se > 0) & valid_boot & np.isfinite(estimate)
    p = np.full((8, 8), np.nan)
    p[eligible] = 2 * norm.sf(np.abs(estimate[eligible] / se[eligible]))
    return se, lower, upper, p, eligible, n_valid


def analyze(edges, posts, out_dir, n_boot=2000, seed=42, minimum_source=20, minimum_pair=5, equal_parent=False, bootstrap_strata=None):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    groups, transition_rows, binary = {}, [], []
    for name in ('ALL', 'MH', 'General'):
        group_posts = posts if name == 'ALL' else posts[posts.community_type == name]
        group_edges = edges if name == 'ALL' else edges[edges.community_type == name]
        matrices = post_matrices(group_edges, group_posts, equal_parent)
        counts = matrices.sum(axis=0)
        probability, expected, z = lsa_of(counts)
        _, excess = transition_values(counts)
        strata = None
        if bootstrap_strata:
            missing = set(bootstrap_strata) - set(group_posts.columns)
            if missing:
                raise ValueError(f'Missing bootstrap stratum columns: {sorted(missing)}')
            if group_posts[bootstrap_strata].isna().any().any() or (group_posts[bootstrap_strata] == '').any().any():
                raise ValueError('Bootstrap stratum values must be nonempty for every discussion')
            strata = list(group_posts.groupby(bootstrap_strata, sort=False, dropna=False).indices.values())
        draws = bootstrap_tables(matrices, n_boot, rng, strata)
        draw_p, draw_excess = transition_values(draws)
        source_support = (matrices.sum(axis=2) > 0).sum(axis=0)
        pair_support = (matrices > 0).sum(axis=0)
        se, low, high, pvals, eligible, valid = summarize_statistics(excess, draw_excess, source_support,
            pair_support, minimum_source, minimum_pair)
        groups[name] = {'p': probability, 'draws': draw_p, 'sources': source_support, 'pairs': pair_support}
        for a, parent in enumerate(LABELS):
            for b, reply in enumerate(LABELS):
                transition_rows.append(dict(group=name, parent=parent, reply=reply, count=counts[a,b],
                    probability=probability[a,b], expected=expected[a,b], lsa_z=z[a,b],
                    excess_probability=excess[a,b], bootstrap_se=se[a,b], ci_low=low[a,b], ci_high=high[a,b],
                    source_posts=source_support[a], pair_posts=pair_support[a,b], valid_bootstrap_draws=valid[a,b],
                    eligible=eligible[a,b], p_value=pvals[a,b]))
        for label, subset in [('stigmatizing', counts[:7]), ('non_stigmatizing', counts[7:])]:
            denominator = subset.sum()
            numerator = subset[:, :7].sum()
            binary.append(dict(group=name, parent_stigma=label, stigmatizing_replies=numerator,
                replies=denominator, probability=numerator / denominator if denominator else np.nan))
    table = pd.DataFrame(transition_rows)
    table['p_bh'] = bh_adjust(table.p_value.to_numpy())
    table.to_csv(out_dir / 'transition_statistics.csv', index=False)
    pd.DataFrame(binary).to_csv(out_dir / 'binary_continuity.csv', index=False)
    mh, general = groups['MH'], groups['General']
    difference = mh['p'] - general['p']
    draws = mh['draws'] - general['draws']
    source_support = np.minimum(mh['sources'], general['sources'])
    pair_support = np.minimum(mh['pairs'], general['pairs'])
    se, low, high, pvals, eligible, valid = summarize_statistics(difference, draws, source_support,
        pair_support, minimum_source, minimum_pair)
    rows = []
    for a, parent in enumerate(LABELS):
        for b, reply in enumerate(LABELS):
            rows.append(dict(parent=parent, reply=reply, mh_probability=mh['p'][a,b],
                general_probability=general['p'][a,b], difference=difference[a,b], bootstrap_se=se[a,b],
                ci_low=low[a,b], ci_high=high[a,b], minimum_group_source_posts=source_support[a],
                minimum_group_pair_posts=pair_support[a,b], valid_bootstrap_draws=valid[a,b],
                eligible=eligible[a,b], p_value=pvals[a,b]))
    comparison = pd.DataFrame(rows)
    comparison['p_bh'] = bh_adjust(comparison.p_value.to_numpy())
    comparison.to_csv(out_dir / 'group_differences.csv', index=False)
    metadata = dict(implementation='Reconstructed reference implementation; not the original production script',
        bootstrap='stratified whole-post resampling with replacement' if bootstrap_strata else 'ordinary whole-post resampling with replacement',
        bootstrap_strata=bootstrap_strata or [], n_boot=n_boot, seed=seed,
        interval='pointwise percentile 95%; not simultaneous or selection-adjusted',
        minimum_source_posts=minimum_source, minimum_pair_posts=minimum_pair,
        group_eligibility='minimum source and pair thresholds must be met in both groups',
        extra_validity_rule='all bootstrap replicates must define a transition probability',
        excess_bh_tests=int(table.eligible.sum()), group_bh_tests=int(comparison.eligible.sum()),
        proportions='All probabilities and intervals use 0-1 units, not percentage points',
        equal_parent_weight=equal_parent, posts=len(posts), edges=len(edges))
    (out_dir / 'analysis_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return table, comparison


def cross_author_edges(edges):
    if not {'parent_author', 'child_author'}.issubset(edges.columns):
        raise ValueError('Cross-author sensitivity requires parent_author and child_author; rebuild the edge table')
    known = edges.parent_author.fillna('').str.startswith('t2_') & edges.child_author.fillna('').str.startswith('t2_')
    return edges[known & (edges.parent_author != edges.child_author)].copy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edges', required=True)
    parser.add_argument('--posts', help='Post manifest from build_edges.py --posts-out; includes zero-edge posts')
    parser.add_argument('--out', required=True)
    parser.add_argument('--bootstrap', type=int, default=2000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--bootstrap-strata', nargs='+', help='Post-manifest columns defining resampling strata, for example subreddit month. Historical strata are not known; do not infer them from this option.')
    parser.add_argument('--min-source-posts', type=int, default=20)
    parser.add_argument('--min-pair-posts', type=int, default=5)
    parser.add_argument('--sensitivities', action='store_true', help='Also run cross-author and equal-parent-weight analyses')
    args = parser.parse_args()
    if args.bootstrap < 2 or args.min_source_posts < 1 or args.min_pair_posts < 1:
        parser.error('At least two bootstrap replicates and positive eligibility thresholds are required')
    edges = pd.read_csv(args.edges, dtype=str, keep_default_na=False)
    validate_edges(edges)
    posts = load_manifest(edges, args.posts)
    options = dict(n_boot=args.bootstrap, seed=args.seed, minimum_source=args.min_source_posts, minimum_pair=args.min_pair_posts, bootstrap_strata=args.bootstrap_strata)
    analyze(edges, posts, args.out, **options)
    if args.sensitivities:
        analyze(cross_author_edges(edges), posts, Path(args.out) / 'cross_author', **options)
        analyze(edges, posts, Path(args.out) / 'equal_parent_weight', equal_parent=True, **options)
    provenance = {'edges_sha256': file_sha256(args.edges),
                  'manifest': 'provided, including zero-edge posts' if args.posts else 'inferred from posts contributing at least one edge',
                  'numpy': np.__version__, 'pandas': pd.__version__}
    (Path(args.out) / 'input_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(f'Analysis written to {args.out}')

if __name__ == '__main__':
    main()
