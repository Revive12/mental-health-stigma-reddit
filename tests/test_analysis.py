"""Synthetic tests for graph integrity, statistics, and resampling units."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'analysis'))
from build_edges import build_edges, edges_for_post, community_type
from distributions import label_report, iter_sub_events
from main_analysis import (bh_adjust, lsa_of, transition_values, post_matrices,
    bootstrap_tables, analyze, cross_author_edges, validate_edges)


def comment(name, parent, label='H', post='t3_example', subreddit='anxiety'):
    return dict(comment_name=name, parent_id=parent, label=label, post_name=post,
        subreddit=subreddit, author_fullname='t2_' + name)


class EdgeTests(unittest.TestCase):
    def test_child_before_parent_is_preserved(self):
        rows = [comment('t1_child', 't1_parent', 'A'), comment('t1_parent', 't3_example')]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            source = path / 'labeled.jsonl'
            source.write_text('\n'.join(json.dumps(row) for row in rows))
            result = build_edges(source, path / 'edges.csv', path / 'posts.csv')
            self.assertEqual(result, {'posts': 1, 'edges': 1})
            with (path / 'edges.csv').open() as handle:
                edge = next(csv.DictReader(handle))
            self.assertEqual((edge['p_label'], edge['c_label']), ('H', 'A'))
            self.assertEqual(edge['parent_author'], 't2_t1_parent')
            report = label_report(source)
            self.assertEqual(report['groups']['ALL']['post_stigma_proportion'], 1)
            self.assertIsNone(report['groups']['General']['comment_stigma_proportion'])

    def test_missing_parent_and_cycles_fail(self):
        for rows in [[comment('t1_a', 't1_missing')],
                     [comment('t1_a', 't1_b'), comment('t1_b', 't1_a')]]:
            with self.assertRaises(ValueError):
                list(edges_for_post('t3_example', rows))

    def test_nested_subreddit_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'data.jsonl'
            path.write_text(json.dumps({'subreddit': 'anxiety', 'nested': {'subreddit': 'wrong'}}))
            self.assertEqual(list(iter_sub_events(path)), ['anxiety'])
        with self.assertRaises(ValueError):
            community_type('')

    def test_invalid_label_fails_without_replacing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary); source = path / 'data.jsonl'; output = path / 'edges.csv'
            source.write_text(json.dumps(comment('t1_a', 't3_example', None)))
            output.write_text('existing output')
            with self.assertRaises(ValueError):
                build_edges(source, output)
            self.assertEqual(output.read_text(), 'existing output')


class StatisticsTests(unittest.TestCase):
    def test_bh_known_values_and_missing(self):
        np.testing.assert_allclose(bh_adjust([.01, .04, .03, .002, np.nan]), [.02, .04, .04, .008, np.nan], equal_nan=True)

    def test_full_eight_label_denominator(self):
        counts = np.zeros((8, 8)); counts[0,0]=1; counts[0,7]=9; counts[7,0]=9; counts[7,7]=81
        probability, excess = transition_values(counts)
        self.assertAlmostEqual(probability[0,0], .1)
        self.assertAlmostEqual(excess[0,0], 0)
        _, expected, z = lsa_of(counts)
        self.assertAlmostEqual(expected[0,0], 1)
        self.assertAlmostEqual(z[0,0], 0)
        self.assertTrue(np.isnan(lsa_of(np.zeros((8,8)))[2]).all())

    def test_equal_parent_weight_and_cross_author(self):
        edges = pd.DataFrame([dict(post_id='p', parent_comment='x', comment_id=f'c{i}',
            p_label='A', c_label='H', parent_author='t2_a', child_author=author)
            for i,author in enumerate(['t2_a','t2_b',''])] + [dict(post_id='p', parent_comment='y',
            comment_id='d', p_label='A', c_label='A', parent_author='t2_c', child_author='t2_d')])
        posts = pd.DataFrame({'post_id': ['p', 'zero']})
        matrix = post_matrices(edges, posts, True)
        self.assertAlmostEqual(matrix[0,0,7], 1)
        self.assertAlmostEqual(matrix[0,0,0], 1)
        self.assertEqual(matrix[1].sum(), 0)
        self.assertEqual(len(cross_author_edges(edges)), 2)

    def test_post_bootstrap_keeps_linked_counts_together(self):
        matrices = np.zeros((3,8,8)); matrices[0,0,0]=1; matrices[0,0,1]=2
        draws = bootstrap_tables(matrices, 100, np.random.default_rng(1))
        np.testing.assert_array_equal(draws[:,0,1], draws[:,0,0]*2)
        self.assertTrue((draws[:,0,0] == 0).any())

    def test_stratified_resampling_preserves_stratum_sizes(self):
        matrices = np.zeros((3,8,8)); matrices[0,0,0]=1; matrices[1:,1,1]=1
        draws=bootstrap_tables(matrices, 20, np.random.default_rng(2), [np.array([0]), np.array([1,2])])
        np.testing.assert_array_equal(draws[:,0,0], np.ones(20))
        np.testing.assert_array_equal(draws[:,1,1], np.full(20,2))

    def test_full_analysis_writes_all_cells_and_dynamic_families(self):
        rows=[]
        for group,sub in [('MH','anxiety'), ('General','example')]:
            for i in range(25):
                post=f'{group}{i}'
                for j, (a,b) in enumerate([('A','A' if i%2 else 'H'), ('H','H' if i%3 else 'A')]):
                    rows.append(dict(post_id=post, subreddit=sub, community_type=group,
                        parent_comment=post+'parent'+str(j), comment_id=post+'child'+str(j), p_label=a, c_label=b))
        edges=pd.DataFrame(rows); validate_edges(edges)
        posts=edges[['post_id','subreddit','community_type']].drop_duplicates()
        with tempfile.TemporaryDirectory() as temporary:
            table, comparison=analyze(edges, posts, temporary, n_boot=40, seed=5)
            self.assertEqual(len(table),192); self.assertEqual(len(comparison),64)
            self.assertTrue((table.loc[table.eligible,'p_bh'] >= table.loc[table.eligible,'p_value']-1e-12).all())
            self.assertEqual(int(table.eligible.sum()),12)
            self.assertEqual(int(comparison.eligible.sum()),4)
            self.assertTrue((Path(temporary)/'analysis_metadata.json').exists())

if __name__ == '__main__':
    unittest.main()
