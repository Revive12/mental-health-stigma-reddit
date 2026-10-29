# Annotation pipeline

This document describes the runnable release, including its input contract and
failure handling. It does not assert that rerunning this release recovers the
historical annotation outputs or manuscript counts. Model outputs depend on the
deployed model, prompt, decoding settings, source data and upstream selection.

## Platform and prerequisites

Run commands from the repository root with the dependencies described in the
README. The pipeline targets macOS and Linux: index construction calls the
system `sort` command, and annotation writers use POSIX advisory file locks.
Stage 5 separately requires a CUDA GPU and its model dependencies. The coarse
and fine annotation scripts communicate with an OpenAI-compatible endpoint;
this endpoint may run on another machine.

Set the data directory before running commands:

```bash
export MH_DATA_ROOT="/path/to/private-data"
```

The precedence is `--data-root`, then `MH_DATA_ROOT`, then `./data`. Original
corpus records, derived annotation inputs, model responses and identifiers belong
in the private data directory, not in the public code repository.

## Preprocessing inputs

The preprocessing sequence is:

1. `stage1_keyword_search.py`: retrieve keyword-matching posts and comments.
2. `stage2_recover_context.py`: recover matching posts and their comments within
   each monthly dump partition.
3. `stage3_length_filter.py`: apply the post text-length and identifier criteria.
4. `stage4_top16_subreddits.py`: determine the subreddit list across the requested
   study months and filter each month. Complete stages 1-3 for the full intended
   study window before this step; selecting the top subreddits from one month is
   a different selection design.
5. `stage4c_placeholder_bot_filter.py`: apply the release's placeholder/bot
   filters before AI-content scoring.
6. `stage5_bot_detect.py`: score potential AI-generated comments, one month at a
   time, on CUDA.
7. `stage6_match_and_clean.py`: match retained posts and remove comments flagged
   by stage 5.
8. `stage7_construct_trees.py`: reconstruct connected reply trees, one month at a
   time; save disconnected branches separately.

The annotation index reads these exact files for every processed month:

```text
$MH_DATA_ROOT/pipeline_data/stage4c_filter/YYYY-MM/posts_prefiltered.jsonl
$MH_DATA_ROOT/pipeline_data/stage7_trees/YYYY-MM/comment_trees.jsonl
```

Stage 7 reads cleaned comments from:

```text
$MH_DATA_ROOT/pipeline_data/stage6_clean/YYYY-MM/comments_cleaned.jsonl
```

These are monthly partitions. The supplied recovery/tree code does not retrieve
later-month replies to an earlier-month post. Connected trees in this release
must not be described as complete lifetime conversations.

## Upstream sample selection

The proportionate selection of posts by subreddit and time is performed upstream.
The sampling implementation is intentionally not included in this repository.
Supply the selected post identifiers in an external UTF-8 text file with one
unique identifier per line, no header and no additional columns. Identifiers
must use the `t3_` prefix. Keep the original selection procedure, seed, stratum
counts and sample allocations with the private study records.

The index builder requires this file. It does not select a proportionate sample
itself. Its deterministic MD5 keys only order the posts that have already been
selected; they are neither participant pseudonyms nor an anonymization method.

## 1. Build the selected-post reference index

```bash
python pipeline/build_shuffle_index.py \
  --data-root "$MH_DATA_ROOT" \
  --selected-posts "$MH_DATA_ROOT/selected_post_ids.txt" \
  --workers 8
```

Outputs:

```text
pipeline_data/stage_stigma_annotate/shuffle_index.tsv
pipeline_data/stage_stigma_annotate/shuffle_index.manifest.json
```

The manifest records the selection-file SHA256, ordering seed, selected-post
count, indexed-post count, selected posts without a retained tree, and comment
reference counts by month. The builder stops if selected posts cannot be found
in the processed `posts_prefiltered.jsonl` files. `--month YYYY-MM` restricts the
processed files; the supplied selection file must then correspond to that month.
`--no-sort` only emits intermediate reference parts and does not produce a
usable final index.

Each retained comment contributes one reference row. Selected posts without a
retained stage-7 tree produce no rows. Their number is recorded in the manifest,
but they cannot be recovered from the final comment-level dataset alone.

## 2. Inspect annotation inputs without calling a model

```bash
python pipeline/stream_annotate.py \
  --data-root "$MH_DATA_ROOT" \
  --materialize-only \
  --max-batches 2
```

This writes `materialized_batches/batch_000000.jsonl` and subsequent input files
under `stage_stigma_annotate`, with separate `materialize_progress.json` state.
It does not advance `progress.json`, and the actual annotation run starts from
its own saved position.

`--batch-size` is a soft target, defaulting to 1,000 comments. Posts are never
split across batches, so a batch can exceed this target. `--max-batches` limits
one invocation for inspection or staged execution; it does not define the sample
or preserve upstream proportions if the selected sample is only partly run.

## 3. Run coarse H/I annotation

Use the exact model identifier exposed by the actual deployment. The script has
no inferred historical-model default.

```bash
export ANNOTATE_BASE_URL="http://127.0.0.1:8123/v1"
export ANNOTATE_MODEL="YOUR_DEPLOYED_COARSE_MODEL_ID"
export ANNOTATE_API_KEY="EMPTY"

python pipeline/stream_annotate.py \
  --data-root "$MH_DATA_ROOT" \
  --temperature 0
```

`EMPTY` is suitable only for a local endpoint that does not require a real key.
For an authenticated service, supply the real key through the environment. Use
`--no-think` only if the deployed model supports the appended `/no_think`
instruction and that setting is intended for the run.

The script formats `pipeline/prompts.py` with the original post, preceding
comments along the target's ancestor chain, and the target comment. Coarse labels
are:

- `H`: the target does not express or clearly endorse stigma.
- `I`: the target expresses or clearly endorses stigma and requires fine labeling.

Annotated batches are written to `batches/batch_NNNNNN.jsonl`. Each row includes
an input, output, comment identifier, subreddit, month and annotation
configuration. Progress is stored in `progress.json`.

A successful batch requires an exact `H` or `I` label in each parsed JSON
response. Unresolved responses are written to a `batch_NNNNNN.failed.jsonl`
diagnostic file; progress is not advanced. Rerunning retries that batch. These
diagnostic files are not treated as completed batches by the fine annotator.

Resume checks the index file's size/mtime, prompt-source hash, model identifier,
decoding settings, batch size and exclusion-list hash. Changed settings or a
rebuilt index require a separate run directory. Do not reuse historical progress
files that lack the release's configuration metadata. Locks prevent simultaneous
writers to the same coarse progress file.

The optional `--exclude` file contains one comment identifier per line. Excluding
comments changes the analyzed data, and export later removes any branches no
longer connected to the post. It must not be used as an undocumented convenience
filter.

## 4. Run fine A-H annotation

```bash
export FINELABEL_BASE_URL="https://your-endpoint.example/v1"
export FINELABEL_MODEL="YOUR_DEPLOYED_FINE_MODEL_ID"
export FINELABEL_API_KEY="YOUR_API_KEY"

python pipeline/finelabel_stigma.py \
  --data-root "$MH_DATA_ROOT" \
  --temperature 0
```

The endpoint accepts either a root URL or one ending in `/v1`. Credentials are
not written to the annotation output. API examples above are placeholders and
are not active services.

The fine annotator uses the supplied `prompts_finelabel_V4.4.txt` template. Its
scientific wording is unchanged in this release. The output records the model,
prompt version/hash and inference settings. `--effort` sends `reasoning_effort`
and should be used only when supported by the selected endpoint/model.

Only coarse-I records undergo fine annotation. Coarse H remains final H. Optional
`--min-coarse-batch` and `--max-coarse-batch` delimit an inclusive lower and
exclusive upper batch range. `--limit` limits pending records for a small run.
The default output is:

```text
pipeline_data/stage_stigma_annotate/finelabel_output.jsonl
```

Only successful exact A-H labels are considered complete. Invalid responses and
API failures are eligible for retry on the next invocation. Successful outputs
from different models, prompt versions or recorded inference settings cannot be
silently mixed by resume. Fine annotation streams inputs and bounds the number
of concurrent futures.

For parallel disjoint batch ranges, use a separate `--out` file for each process.
The default output has an exclusive writer lock. Merge the completed files into
`finelabel_output.jsonl` explicitly before export, checking that the ranges and
annotation settings agree.

The scripts can also consume an existing `err_reannotated.jsonl` containing
`comment_name` and `new_output.label` (`H` or `I`). This repair file is applied
only when the original coarse label is invalid. The repository does not include
an automatic procedure that generates such a file.

## 5. Export final comment labels

Wait for the intended coarse batch range and all of its coarse-I fine labels to
complete. Read the completed batch count from the real annotation progress:

```bash
ANNOTATION_BATCH_COUNT="$(python -c 'import json, os; from pathlib import Path; p = Path(os.environ["MH_DATA_ROOT"]) / "pipeline_data/stage_stigma_annotate/progress.json"; print(json.loads(p.read_text())["batches_done"])')"

python pipeline/export_labeled_dataset.py \
  --data-root "$MH_DATA_ROOT" \
  --lo 0 \
  --hi "$ANNOTATION_BATCH_COUNT" \
  --out "$MH_DATA_ROOT/labeled_comments.jsonl"
```

`--hi` is required and exclusive. For example, `--lo 0 --hi 3` reads batches 0,
1 and 2. A completed invocation does not imply that the entire externally
selected sample has finished: confirm that the progress byte offset equals the
index size before treating the export as the full sample.

Export stops on invalid coarse labels, unresolved coarse-I fine labels, malformed
JSON or duplicate comment identifiers. It never converts a failure into H.
The label rule is `fine_label` for coarse I and `H` for coarse H. Comments in
missing-parent, cross-post or cyclic branches are removed. The destination is
replaced only after the export has successfully completed.

## 6. Build direct comment-to-comment edges

```bash
python analysis/build_edges.py \
  --labeled "$MH_DATA_ROOT/labeled_comments.jsonl" \
  --out "$MH_DATA_ROOT/edges.csv" \
  --posts-out "$MH_DATA_ROOT/posts.csv"
```

This includes only direct comment-to-comment replies. Responses directly to an
original post do not create edges, but their discussions remain in `posts.csv`.
The post manifest includes discussions represented in the labeled dataset that
have zero comment-to-comment edges. It does not recreate selected posts with no
retained labeled comments. See [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for fields.

## Verification scope

The release includes offline regression tests for selection/index construction,
whole-post batching, input materialization, strict label parsing, a mocked fine
annotation run/resume and final export validation. These tests make no live LLM
API requests and do not load the GPU classifier. Passing them verifies software
behavior on synthetic inputs; it does not validate annotation accuracy, recreate
historical model outputs or reproduce the full-corpus manuscript estimates.
