# Preprocessing private data

Run all commands from the repository root. Source archives must be obtained separately under their applicable access conditions. Upstream proportional stratified sampling is outside this release.

## Execution

The commands below explicitly select January 2021 through December 2025. Stage 5 requires a CUDA GPU and the configured detector; synthetic predictions must not replace actual inference in a scientific analysis. The array syntax works in Bash and Zsh. Stop if any stage fails.

```bash
set -e
export MH_DATA_ROOT=./private_data
months=()
for year in 2021 2022 2023 2024 2025; do
  for month in 01 02 03 04 05 06 07 08 09 10 11 12; do
    months+=("$year-$month")
    python pipeline/stage1_keyword_search.py --month "$year-$month"
    python pipeline/stage2_recover_context.py --month "$year-$month"
    python pipeline/stage3_length_filter.py --month "$year-$month"
  done
done

python pipeline/stage4_top16_subreddits.py --month "${months[@]}" --num 16

for month in "${months[@]}"; do
  python pipeline/stage4c_placeholder_bot_filter.py --month "$month"
  python pipeline/stage5_bot_detect.py --month "$month" --gpu 0
  python pipeline/stage6_match_and_clean.py --month "$month"
  python pipeline/stage7_construct_trees.py --month "$month"
done
```

Stage 4 requires preceding outputs for every requested month. `stage4_b_month.py` is an optional per-month filtering helper after global subreddit selection has been created; it does not replace that selection.

## Stage behavior

| Stage | Operation |
|---|---|
| 1 | Search fixed keyword patterns in post titles/bodies and comment bodies |
| 2 | Recover posts and linked comments from the same month's source archives |
| 3 | Require a post identifier and at least 10 whitespace-separated words across title and body |
| 4 | Rank subreddits by retained post count across the requested months; retain the top 16 |
| 4c | Remove placeholder posts, placeholder comments and their descendants, and bot-account comments and their descendants |
| 5 | Score comment text with an AI-text detector; truncate at 512 model tokens; flag scores strictly above 0.5 |
| 6 | Match comments to retained posts and remove comments flagged as AI-generated |
| 7 | Construct connected reply trees, rejecting invalid roots, duplicate IDs, and cycles; keep orphan output separate |

Bot-account filtering and AI-text detection are different operations. The detector is an estimated classification, not proof of authorship. Stage 3 does not test `is_self` or otherwise establish that every submission is text-only.

## Observation boundaries

Context recovery reads the matching calendar month's RS and RC archives only. It does not retrieve subsequent-month replies and may not recover an earlier-month post referenced by a later comment. These outputs are not lifetime-complete discussions.

Stage 7 emits connected, nonempty comment trees. Selected posts without a retained tree are counted in the indexing manifest but do not appear in the flattened comment file. A denominator including those posts requires the upstream selection frame and an explicit inclusion rule.

This release moves placeholder and bot filtering upstream and removes bot descendants. The historical annotation implementation treated some cases differently. A rerun is not guaranteed to preserve historical corpus counts. See [methods alignment](METHODS_ALIGNMENT.md).
