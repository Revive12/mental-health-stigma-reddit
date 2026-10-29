#!/usr/bin/env python3
"""Fit an explicitly selected exploratory k and display within-cluster LSA.

Clusters are restricted to nonzero selected profiles. Nominal LSA thresholds in
these visualizations are descriptive and do not replace corrected main tests.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from main_analysis import lsa_of, validate_edges, file_sha256

LAB = list('ABCDEFGH')
LIX = {c: i for i, c in enumerate(LAB)}
SEED = 42
POS = {k: (np.cos(2*np.pi*i/8+np.pi/8), np.sin(2*np.pi*i/8+np.pi/8)) for i,k in enumerate(LAB)}


def network_fig(z, title, destination, n_posts, n_pairs):
    fig, ax = plt.subplots(figsize=(7, 6.5))
    n_edges = 0
    for a in range(7):
        for b in range(7):
            value = z[a,b]
            if a == b or not np.isfinite(value) or value <= 1.96:
                continue
            n_edges += 1
            width = 1.0 if value <= 2.58 else 2.2 if value <= 3.29 else 3.8
            ax.add_patch(FancyArrowPatch(POS[LAB[a]], POS[LAB[b]], connectionstyle='arc3,rad=0.25',
                arrowstyle='-|>', mutation_scale=13, lw=width, color='#444444', alpha=.85))
    for label, (x, y) in POS.items():
        ax.scatter([x], [y], s=1500, color='#0072B2', zorder=3)
        ax.text(x, y, label, ha='center', va='center', color='white', fontweight='bold', zorder=4)
    ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.55, 1.55); ax.set_axis_off()
    ax.set_title(f'{title}\n{n_posts:,} posts; {n_pairs:,} reply pairs; {n_edges} cross-attribution edges\n'
        'Positive Z > 1.96; nominal, uncorrected; widths at 2.58 and 3.29')
    for extension in ('png', 'pdf'):
        fig.savefig(str(destination) + '.' + extension, dpi=300, bbox_inches='tight')
    plt.close(fig)
    return n_edges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edges', required=True)
    parser.add_argument('--out', required=True, help='Directory created by lsa_cluster.py')
    parser.add_argument('--k', required=True, type=int, help='Explicit exploratory cluster number; not a confirmed elbow')
    args = parser.parse_args()
    out = Path(args.out); (out / 'figures').mkdir(parents=True, exist_ok=True)
    edges = pd.read_csv(args.edges, dtype=str, keep_default_na=False); validate_edges(edges)
    metadata = json.loads((out / 'cluster_metadata.json').read_text())
    if metadata['edges_sha256'] != file_sha256(args.edges):
        parser.error('The edge file differs from the feature-generation input; rerun lsa_cluster.py')
    frame = pd.read_csv(out / 'post_features.csv')
    feature_cols = [c for c in frame.columns if '->' in c and not c.startswith('n_')]
    if not feature_cols:
        parser.error('No transition features passed the exploratory selection threshold')
    if set(frame.post_id) != set(edges.post_id):
        parser.error('The feature file and edge file contain different posts; rerun stage 1')
    selected = frame[frame[feature_cols].sum(axis=1) > 0].copy()
    matrix = selected[feature_cols].to_numpy()
    if args.k < 2 or args.k > min(len(matrix), len(np.unique(matrix, axis=0))):
        parser.error('k must be at least two and cannot exceed the number of distinct nonzero profiles')
    labels = KMeans(n_clusters=args.k, random_state=SEED, n_init=10, max_iter=300).fit_predict(matrix)
    pd.DataFrame({'post_id': selected.post_id, 'cluster': labels}).to_csv(out / f'cluster_labels_k{args.k}.csv', index=False)
    indexed = edges.post_id.map(dict(zip(selected.post_id, labels)))
    results = []
    for cluster in range(args.k):
        subset = edges[indexed == cluster]
        counts = np.zeros((8, 8), dtype=np.int64)
        np.add.at(counts, (subset.p_label.map(LIX).to_numpy(), subset.c_label.map(LIX).to_numpy()), 1)
        probability, expected, z = lsa_of(counts)
        pd.DataFrame([{'parent': a, 'child': b, 'N': counts[i,j], 'P': probability[i,j], 'E': expected[i,j], 'Z': z[i,j]}
            for i,a in enumerate(LAB) for j,b in enumerate(LAB)]).to_csv(out / f'cluster{args.k}_c{cluster}_lsa.csv', index=False)
        n_posts = subset.post_id.nunique()
        displayed = network_fig(z, f'Exploratory cluster {cluster} (k={args.k})',
            out / 'figures' / f'cluster{args.k}_c{cluster}_network', n_posts, len(subset))
        subreddits = subset.drop_duplicates('post_id').subreddit.value_counts().head(3)
        results.append({'k': args.k, 'cluster': cluster, 'posts': n_posts, 'edges': len(subset),
            'top_subreddits': ', '.join(f'{s}({n})' for s,n in subreddits.items()), 'nominal_positive_AG_cross_edges': displayed})
    pd.DataFrame(results).to_csv(out / 'cluster_summary.csv', index=False)
    print(f'Exploratory clustering written to {out}; no confirmatory cluster-number claim is made.')

if __name__ == '__main__':
    main()
