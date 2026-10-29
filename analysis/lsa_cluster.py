#!/usr/bin/env python3
"""Exploratory clustering of nonzero stigma-transition profiles.

The source of edges is the full corpus, but clustering excludes posts whose
selected features are all zero. This is NOT an all-discussion clustering result.
Feature selection uses positive, nominal uncorrected LSA Z > 1.96 among distinct
A-G attributions. This exploratory workflow is separate from main_analysis.py.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from main_analysis import lsa_of, validate_edges, file_sha256

LAB = list('ABCDEFGH')
LIX = {c: i for i, c in enumerate(LAB)}
SEED = 42


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edges', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out); (out / 'figures').mkdir(parents=True, exist_ok=True)
    edges = pd.read_csv(args.edges, dtype=str, keep_default_na=False)
    (out / 'cluster_metadata.json').write_text(json.dumps({'edges_sha256': file_sha256(args.edges),
        'seed': SEED, 'feature_threshold': 'positive nominal LSA Z > 1.96; A-G cross-attribution only',
        'excluded': 'posts with all-zero selected features; posts without reply edges are absent'}, indent=2) + '\n')
    validate_edges(edges)
    total = np.zeros((8, 8), dtype=np.int64)
    np.add.at(total, (edges.p_label.map(LIX).to_numpy(), edges.c_label.map(LIX).to_numpy()), 1)
    probability, expected, z = lsa_of(total)
    pd.DataFrame([{'parent': a, 'child': b, 'count': total[i,j], 'P': probability[i,j],
        'E': expected[i,j], 'Z': z[i,j]} for i,a in enumerate(LAB) for j,b in enumerate(LAB)]).to_csv(out / 'all_lsa.csv', index=False)
    features = [(LAB[a], LAB[b], z[a,b]) for a in range(7) for b in range(7)
                if a != b and np.isfinite(z[a,b]) and z[a,b] > 1.96]
    pd.DataFrame(features, columns=['parent', 'child', 'Z_all']).to_csv(out / 'feature_list.csv', index=False)
    posts = edges.post_id.unique()
    positions = {p:i for i,p in enumerate(posts)}
    feature_index = {(a,b):i for i,(a,b,_) in enumerate(features)}
    raw = np.zeros((len(posts), len(features)))
    for post, parent, child in zip(edges.post_id, edges.p_label, edges.c_label):
        index = feature_index.get((parent, child))
        if index is not None:
            raw[positions[post], index] += 1
    denominators = edges.groupby('post_id').size().reindex(posts).to_numpy()
    normalized = raw / denominators[:, None]
    nonzero = raw.sum(axis=1) > 0
    frame = pd.DataFrame(normalized, columns=[f'{a}->{b}' for a,b,_ in features])
    frame.insert(0, 'post_id', posts)
    frame.insert(1, 'subreddit', edges.drop_duplicates('post_id').set_index('post_id').subreddit.reindex(posts).to_numpy())
    frame['n_edges'] = denominators
    for i,(a,b,_) in enumerate(features):
        frame[f'n_{a}->{b}'] = raw[:,i]
    frame.to_csv(out / 'post_features.csv', index=False)
    pd.DataFrame([{'total_posts_with_edges': len(posts), 'posts_all_zero_features': int((~nonzero).sum()),
        'posts_entered_kmeans': int(nonzero.sum())}]).to_csv(out / 'cluster_inclusion.csv', index=False)
    selected = normalized[nonzero]
    maximum = min(10, len(selected), len(np.unique(selected, axis=0))) if len(features) else 0
    results = []
    for k in range(2, maximum + 1):
        model = KMeans(n_clusters=k, random_state=SEED, n_init=10, max_iter=300).fit(selected)
        results.append({'k': k, 'WCSS': model.inertia_})
    pd.DataFrame(results, columns=['k', 'WCSS']).to_csv(out / 'k_wcss.csv', index=False)
    (out / 'k_wcss.json').write_text(json.dumps({'ks': [r['k'] for r in results], 'wcss': [r['WCSS'] for r in results]}, indent=2) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4))
    if results:
        ax.plot([r['k'] for r in results], [r['WCSS'] for r in results], 'o-')
    else:
        ax.text(.5, .5, 'Insufficient nonzero profiles for clustering', ha='center', transform=ax.transAxes)
    ax.set(xlabel='k', ylabel='WCSS', title='Exploratory K-means: inspect the WCSS curve')
    for ext in ('png', 'pdf'):
        fig.savefig(out / 'figures' / f'elbow.{ext}', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f'{len(edges):,} edges; {len(features)} selected transitions; {nonzero.sum():,}/{len(posts):,} posts enter clustering.')
    print('No cluster number is inferred automatically. Choose an exploratory k explicitly for lsa_cluster_step2.py.')

if __name__ == '__main__':
    main()
