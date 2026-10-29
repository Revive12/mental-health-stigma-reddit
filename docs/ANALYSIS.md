# Analysis and reproduction

Run the commands below from the repository root. Install the analysis dependencies
listed in `requirements.txt` first. Private comment-level data are not included.

## Two distinct reproduction routes

`manuscript_results/` contains frozen aggregate tables used for the manuscript
figures. Its plotting scripts render those saved estimates; they do not rerun
annotation, bootstrap resampling, or hypothesis tests. This is the route for
rebuilding the released manuscript figures and checking the reported totals.

`analysis/main_analysis.py` is a reconstructed reference implementation of the
reported statistical methods. It computes new estimates from a supplied edge
table. It is not the original production analysis script, and its bootstrap
intervals are not certified as exact reproductions of the frozen tables. The
release keeps this distinction explicit rather than substituting regenerated
values for the manuscript results.

### Render and verify frozen manuscript results

```bash
python scripts/verify_reported_results.py
python manuscript_results/fig1/scripts/plot_fig1.py
python manuscript_results/fig2/scripts/plot_annotated.py
python manuscript_results/supplements/scripts/plot_supplements.py
```

Each plotting script writes to the `figures/` directory beside its `scripts/`
directory. `manuscript_results/source_manifest.json` records checksums for the
released source tables. The verification script checks these checksums and the
reported aggregate results. A successful figure render verifies presentation of
the archived tables, not reconstruction of the underlying private data.

## Analyze a labeled corpus

### 1. Validate comments and construct reply edges

```bash
python analysis/build_edges.py \
  --labeled data/private/labeled.jsonl \
  --out outputs/edges.csv \
  --posts-out outputs/posts.csv
```

The JSONL input contains one labeled comment per line and must keep each post's
records in a contiguous block. Within a post, comments may appear in any order.
Required fields are `post_name`, `comment_name`, `parent_id`, `subreddit`, and
`label`. Post and comment names use the `t3_` and `t1_` prefixes. Labels must be
exactly A through H. A-G are the seven stigma attributions; H is non-stigmatizing.
Missing labels are errors, not implicit H labels.

Optional `author_fullname` values are carried into the edge table as
`parent_author` and `child_author`. Optional `month` values are carried into the
post manifest. Preserve these fields if cross-author or time-stratified analyses
are intended.

An edge joins a comment to its direct comment reply. Responses to the original
post do not create comment-to-comment edges. The builder rejects duplicate
comments within a post, missing or cross-post parents, cycles, and inconsistent
subreddit assignments. It resolves the full post block before creating edges so
that a reply serialized before its parent is retained.

`posts.csv` includes every discussion represented in the labeled input, including
those without comment-to-comment edges. It does not recover posts absent from
that input, such as posts containing no exported comments.

Mental health subreddits are `depression`, `anxiety`, `suicidewatch`, `bpd`, and
`mentalhealth` (case-insensitive). Other nonempty subreddit names are assigned to
General. Missing subreddit names are rejected.

### 2. Calculate corpus distributions

```bash
python analysis/distributions.py \
  --mode labels --labeled data/private/labeled.jsonl \
  --out outputs/distributions.json
```

The JSON report includes overall, group, and subreddit counts; the proportion of
posts with at least one stigmatizing comment; the proportion of comments that are
stigmatizing; and A-G composition among stigmatizing comments. It also reports
Pearson chi-square tests without Yates correction and Cramer's V for post-level
stigma presence and pooled stigma-attribution composition. The composition test
pools comments and does not model dependence within discussions. Outcomes with
zero counts in both groups are removed before this test; non-estimable tables are
reported explicitly.

Preprocessing and subreddit coverage reports are also available:

```bash
python analysis/distributions.py --mode funnel --data-root data --out outputs/funnel.json
python analysis/distributions.py --mode subreddit --stage 4 --data-root data --out outputs/subreddits.json
```

The funnel report aggregates available metadata. Missing metadata are reported
as unavailable; they are not evidence that a stage retained zero records.

### 3. Run the reference transition analysis

```bash
python analysis/main_analysis.py \
  --edges outputs/edges.csv --posts outputs/posts.csv \
  --out outputs/main --bootstrap 2000 --seed 42 --sensitivities
```

All eight labels enter the 8-by-8 tables and denominators. For parent attribution
A and reply attribution B, the script estimates:

- Conditional reply probability: the A-to-B edge count divided by all edges with
  parent label A, including replies labeled H.
- Marginal reply probability: all edges with reply label B divided by all edges.
- Excess probability: conditional probability minus marginal probability.
- LSA expected counts and adjusted standardized residuals under independence of
  parent and reply labels.

The reference script does not restrict its input to posts containing stigma or
to A-G-to-A-G edges. Such restrictions would change the denominators. LSA
residuals are exploratory, nominal statistics; they are distinct from the
bootstrap-based excess-probability tests.

The main outputs are:

| File | Content |
| --- | --- |
| `transition_statistics.csv` | All 64 transitions for ALL, MH, and General; counts, probabilities, LSA, excess probabilities, intervals, eligibility, and adjusted tests |
| `group_differences.csv` | All 64 conditional-probability contrasts, MH minus General |
| `binary_continuity.csv` | Stigmatizing-reply proportions after stigmatizing versus non-stigmatizing parent comments |
| `analysis_metadata.json` | Resampling configuration, thresholds, realized test-family sizes, and implementation status |
| `input_provenance.json` | Edge-file checksum, post-frame choice, and selected dependency versions |

**Units:** probabilities, differences, standard errors, and confidence limits in
these new output tables use 0-1 units. Multiply by 100 for percentages or
percentage points. Counts, LSA residuals, and p values are not percentage points.
The frozen figure-specific CSVs may already contain percentage-point columns,
such as `excess_pp`; follow their column names rather than multiplying twice.

## Bootstrap and inference assumptions

The default is ordinary resampling of whole posts with replacement, with 2,000
replicates and a reproducible release default seed of 42. The implementation
compresses identical per-post transition tables and draws their multiplicities
with a multinomial distribution. This is distributionally equivalent to
resampling the individual post tables, rather than resampling edges independently.

Supplying `--posts` includes represented zero-edge discussions in the resampling
frame. Without it, the frame is inferred from discussions contributing at least
one edge. The selected frame is recorded in the output provenance.

For each excess probability, the script computes a bootstrap standard error,
pointwise 2.5th and 97.5th percentile confidence limits, and a two-sided Wald test
using the estimate divided by its bootstrap standard error. Eligibility requires
at least 20 distinct posts contributing the parent label, at least five posts
contributing that transition, and a positive bootstrap standard error. This
reference implementation additionally requires every bootstrap replicate to
define the cell's probability; undefined sparse cells are not tested. Thresholds
can be changed with `--min-source-posts` and `--min-pair-posts` and are recorded in
metadata.

Benjamini-Hochberg correction is applied jointly to eligible excess-probability
tests across ALL, MH, and General. For the archived data, the published family
contains 161 eligible tests out of 192 possible cells. This count is a property
of those data, not a hard-coded target.

For group comparisons, the effect is the MH conditional reply probability minus
the General conditional reply probability. Independently generated group
bootstrap draws are paired to estimate its sampling distribution. The same
source-post and pair-post thresholds must hold in both groups. Eligible group
contrasts form a separate BH family; the archived family contains 36 eligible
tests out of 64 possible contrasts.

Intervals are pointwise. They are not simultaneous intervals and are not
adjusted for selecting the largest observed transitions. BH adjustment applies
to p values, not to the confidence limits. Sequential association does not by
itself establish causal transmission of stigma.

### Historical settings still requiring confirmation

The archived analysis notes describe stratified whole-post bootstrap, but the
original production bootstrap script, strata definitions, random seed, and
treatment of zero-edge posts were not supplied. The ordinary default above must
not be described as that verified historical configuration.

If the original resampling strata are established, they can be supplied using
columns in the post manifest. For example, the following requests subreddit by
month strata for a new run; it is not a claim about the original analysis:

```bash
python analysis/main_analysis.py \
  --edges outputs/edges.csv --posts outputs/posts.csv \
  --out outputs/main_stratified --bootstrap 2000 --seed 42 \
  --bootstrap-strata subreddit month --sensitivities
```

Every post must have nonempty values for the selected stratum columns. Resampling
then keeps each stratum's post count fixed. Corpus subsampling strata and
bootstrap strata are different methodological choices; confirmation of one does
not establish the other. Keep the frozen manuscript tables unchanged until the
historical configuration is resolved and any recomputation is reconciled.

## Sensitivity analyses

`--sensitivities` writes two additional result directories:

- `cross_author/`: includes edges only when both author identifiers are present,
  have the Reddit `t2_` form, and differ. Unknown authors are excluded. Each
  retained edge otherwise has unit weight.
- `equal_parent_weight/`: assigns each edge weight equal to one divided by its
  parent comment's number of eligible replies. Thus each parent contributes one
  total unit. Post bootstrap resampling is applied to these weighted tables.

Each sensitivity run recomputes its own estimates, eligibility, and BH families.
The supplied post frame remains fixed, so a discussion can contribute a zero
matrix after an edge restriction. The manuscript emphasizes same-attribution
excess probabilities for both sensitivity analyses and group contrasts under the
cross-author restriction. The reference script exports complete tables for
inspection; additional exported contrasts are not additional published findings.

## Exploratory clustering

```bash
python analysis/lsa_cluster.py --edges outputs/edges.csv --out outputs/clusters
python analysis/lsa_cluster_step2.py --edges outputs/edges.csv --out outputs/clusters --k 3
```

The first script calculates full-corpus LSA and selects distinct A-G transitions
with positive nominal Z greater than 1.96. Each post's feature is its number of
edges of a selected type divided by its total number of eligible edges, including
H-related edges. Features are not standardized. Posts whose selected features
are all zero are excluded from K-means; posts without reply edges are absent from
the edge input altogether. Consequently, this is clustering of nonzero selected
transition profiles, not clustering of every sampled discussion. Inspect
`cluster_inclusion.csv` before interpreting the population represented.

The WCSS curve covers feasible values of k from 2 through 10, bounded by the
number of distinct nonzero profiles. The script does not infer an optimal k.
`--k 3` above is an explicit exploratory choice, not evidence that three clusters
exist or that the curve has an elbow. K-means uses `random_state=42`, `n_init=10`,
and `max_iter=300`. Empty feature sets and impossible k values are reported
explicitly.

The second script checks the input checksum, fits the selected k, and recalculates
8-by-8 LSA within each cluster. Network plots display nominal uncorrected positive
A-G cross-attribution residuals. Because the features were selected from the same
data, these plots are descriptive and do not constitute independent confirmation
of the selected associations. Clustering does not replace the manuscript's
primary reply-transition analysis.

## Verification performed for this release

```bash
python -m unittest discover -s tests -p test_analysis.py -v
python scripts/verify_reported_results.py
```

Ten analysis tests passed, covering graph order and connectivity, invalid labels,
nested subreddit fields, known BH examples, full eight-label denominators,
parent weighting, author restrictions, whole-post and stratified resampling, and
dynamic test families. Synthetic CLI runs also passed for 2,000 bootstrap
replicates with both sensitivities and for both exploratory clustering steps.

Independent recalculation from the archived aggregate counts matched conditional
and excess probabilities within 1e-16, expected counts within 2e-12, and LSA Z
values within 2e-14. Reapplying BH to archived raw p values matched adjusted values
within 3e-16. The source-post and pair-post eligibility rules recovered exactly
161 excess-probability tests and 36 group comparisons.

These checks validate the implemented calculations and the archived summaries.
They do not validate new model annotations or recover the unavailable historical
bootstrap draws. No private-data rerun, GPU inference, or paid API call was used
for these release checks.
