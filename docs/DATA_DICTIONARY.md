# Data dictionary

All identifiers and examples in public test fixtures are synthetic. The formats
below describe private inputs and locally generated outputs; the release does
not include the original Reddit corpus or historical annotation outputs.

## Path conventions

`DATA_ROOT` below means the directory resolved from `--data-root`,
`MH_DATA_ROOT`, or `./data`, in that order. `YYYY-MM` denotes one calendar-month
partition. JSONL means one complete JSON object per line in UTF-8 encoding.

| Artifact | Path below `DATA_ROOT` | Unit |
|---|---|---|
| Submission dump | `full_data/reddit-YY/submissions/RS_YYYY-MM.zst` | Original post |
| Comment dump | `full_data/reddit-YY/comments/RC_YYYY-MM.zst` | Original comment |
| Prefiltered posts | `pipeline_data/stage4c_filter/YYYY-MM/posts_prefiltered.jsonl` | Retained post |
| Prefiltered comments | `pipeline_data/stage4c_filter/YYYY-MM/comments_prefiltered.jsonl` | Retained comment |
| AI-scored comments | `pipeline_data/stage5_bot/YYYY-MM/comments_bot_labeled.jsonl` | Scored comment |
| Clean comments | `pipeline_data/stage6_clean/YYYY-MM/comments_cleaned.jsonl` | Retained comment |
| Connected trees | `pipeline_data/stage7_trees/YYYY-MM/comment_trees.jsonl` | Nonempty post tree |
| Disconnected branches | `pipeline_data/stage7_trees/YYYY-MM/orphan_comments.jsonl` | Post with disconnected branches |
| Annotation index | `pipeline_data/stage_stigma_annotate/shuffle_index.tsv` | Comment reference |
| Index provenance | `pipeline_data/stage_stigma_annotate/shuffle_index.manifest.json` | Index build |
| Input-only batches | `pipeline_data/stage_stigma_annotate/materialized_batches/batch_NNNNNN.jsonl` | Annotation input |
| Coarse batches | `pipeline_data/stage_stigma_annotate/batches/batch_NNNNNN.jsonl` | Coarse annotation |
| Fine annotations | `pipeline_data/stage_stigma_annotate/finelabel_output.jsonl` | Fine annotation attempt |

Final export and edge-table locations are set by their respective `--out`
arguments; they are not fixed to a repository directory.

## Upstream selected-post manifest

The required `--selected-posts` argument points to a private text file prepared
by the upstream sampling procedure, whose implementation is not included here.
It contains one unique `t3_` post identifier per nonempty line, without a header
or other columns. MD5 index ordering does not perform sampling or enforce
subreddit/time quotas. The upstream manifest is the authority for membership in
the selected sample.

## Source fields used by the pipeline

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Reddit fullname: `t3_...` for posts, `t1_...` for comments |
| `id` | string, when available | Identifier without the fullname prefix; some tree code can normalize it |
| `title` | string or null | Original post title |
| `selftext` | string or null | Original post body |
| `body` | string or null | Comment text |
| `subreddit` | string | Top-level subreddit field of the source record |
| `author` | string or null | Source username, when available |
| `author_fullname` | string or null | Account identifier, when available; missing does not identify a unique user |
| `created_utc` | numeric or null | Source creation time as Unix seconds |
| `score` | numeric or null | Archived score, not a measure of exposure |
| `link_id` | string | `t3_` identifier of the original post for a comment |
| `parent_id` | string | Immediate parent: `t3_` post or `t1_` comment |

The code does not infer users' diagnoses from account identifiers. Author IDs
support conversational role interpretation and author-based sensitivity checks;
they are not public excerpt codes such as D01-C01.

## AI-content scoring

Stage 5 appends a `slop_detection` object:

| Key | Type | Meaning |
|---|---|---|
| `is_ai_generated` | boolean | Whether the model score exceeds 0.5 |
| `confidence` | number | Rounded score assigned to the model's AI-content class |
| `label` | string | `predicted_ai` or `predicted_human` |

These are model predictions, not proof of authorship. Stage 6 requires an actual
boolean `is_ai_generated` and excludes rows for which it is true. This label is
separate from stigma annotation.

## Reply-tree JSONL

A connected-tree row has the form:

```json
{
  "name": "t3_syntheticpost",
  "comments": [
    {
      "name": "t1_syntheticcomment",
      "parent_id": "t3_syntheticpost",
      "link_id": "t3_syntheticpost",
      "body": "Synthetic fixture text.",
      "replies": []
    }
  ]
}
```

Actual nodes additionally retain source author, score and timestamp fields.
`comments` contains direct responses to the post; `replies` recursively contains
children. Disconnected-branch rows use `orphan_comments` instead of `comments`.
Trees are reconstructed within monthly input partitions; the format does not
imply that later-month replies have been recovered.

## Annotation reference index

`shuffle_index.tsv` has no header and exactly seven tab-separated columns:

| Position | Field | Meaning |
|---|---|---|
| 1 | `key` | 32-character MD5 ordering key derived from seed and post ID |
| 2 | `month` | Source partition, `YYYY-MM` |
| 3 | `post_name` | Selected `t3_` post ID |
| 4 | `subreddit` | Subreddit from the retained post record |
| 5 | `comment_name` | Target `t1_` comment ID |
| 6 | `tree_offset` | Byte offset of the tree JSONL row |
| 7 | `post_offset` | Byte offset of the retained post JSONL row |

All references from one post share an ordering key. Offsets are valid only for
the source files from which the index was generated; the annotator checks that
retrieved post/tree identifiers match the reference.

The adjacent manifest includes `schema_version`, `ordering`, `selection`,
`sampling_code_included`, `seed`, `selected_posts_sha256`,
`selected_post_count`, `indexed_post_count`, `selected_without_tree_count`,
`comments_by_month` and `reference_count`. Posts without a retained tree do not
contribute comment references. The SHA256 records the selection file as supplied,
including its byte-level formatting.

## Coarse annotation record

| Field | Type | Meaning |
|---|---|---|
| `comment_name` | string | Target comment ID |
| `subreddit` | string | Post subreddit |
| `month` | string | Input partition |
| `input.post_data` | object | Post name, title, selftext, author ID, subreddit and timestamp |
| `input.context_chain` | array of objects | Ancestor comments from the post toward the target, excluding the target |
| `input.target_comment` | object | Target comment, including original `parent_id` |
| `output.label` | string | Valid coarse label `H` or `I`; failed diagnostics may contain `X` or `ERROR` |
| `output.raw` | string or null | Raw model response |
| `annotation_configuration` | object | Model/decoding settings, prompt-source hash, index signature, batch size and exclusion hash |

Input-only materialization records omit `output`. A context chain follows reply
ancestry; it is not a list of all earlier comments across a discussion.

`progress.json` stores `byte_offset`, `batches_done`, `records_done` and
`configuration`. Input-only runs use `materialize_progress.json` instead.

## Fine annotation record

| Field | Type | Meaning |
|---|---|---|
| `comment_name` | string | Target comment ID |
| `post_name` | string | Original post ID |
| `subreddit`, `month` | string | Source grouping fields |
| `coarse_label` | string | `I` |
| `finelabel.label` | string | Valid A-H attribution/non-stigmatizing label, or diagnostic `X`/`ERROR` |
| `finelabel.raw` | string | Raw model response |
| `model` | string | Explicit deployed model identifier |
| `prompt` | string | V4.4 version with a hash of the loaded template |
| `settings.temperature` | number | Requested generation temperature |
| `settings.reasoning_effort` | string or null | Optional requested reasoning effort |

Fine output is an append-only attempt log. A failed attempt followed by a valid
retry can produce multiple rows for a comment. Export uses the latest valid A-H
entry for each identifier; failed labels never become H. Resume refuses to mix
successful entries from different model/prompt/inference configurations.

## Final annotation labels

The supplied V4.4 prompt is the authoritative operational definition. The table
summarizes its labels without replacing its decision and precedence rules.

| Label | Meaning |
|---|---|
| A | Responsibility: endorsed blame or control attributed to mental illness or associated symptoms; explicit self-directed blame is included |
| B | Social distance: endorsed exclusion from ordinary relationships because of mental illness |
| C | Anger: hostility, contempt or direct pathologizing attack linked to mental illness |
| D | Helping: withholding or withdrawing support because of a stigmatizing belief; ordinary advice or reasonable boundaries alone do not qualify |
| E | Pity: operationalized here as lack of concern or sympathy, dismissal, or minimization of suffering; ordinary concern is not E |
| F | Coercive segregation: required treatment, hospitalization or confinement under the supplied scheme, including direct need/should requirements |
| G | Fear: endorsed danger, violence, unpredictability or related harm attributions linked to mental illness under the scheme |
| H | Non-stigmatizing: no clear endorsement of an A-G attribution; includes neutral, supportive and stigma-rejecting content |

A-G are seven stigma attributions. H is not an eighth stigma attribution and does
not necessarily represent an active challenge to preceding stigma. The coarse
letter I is an intermediate routing label and never appears as a valid final
annotation.

## Final comment-level export

| Field | Type | Meaning |
|---|---|---|
| `comment_name`, `post_name` | string | Comment and original-post identifiers |
| `subreddit`, `month` | string | Source grouping fields |
| `body` | string or null | Retained target text |
| `score`, `created_utc` | numeric or null | Archived source values |
| `author_fullname` | string or null | Target author ID |
| `post_author_fullname` | string or null | Original-post author ID |
| `depth` | integer | Number of ancestor comments plus one; top-level comments have depth 1 |
| `parent_id` | string | Original immediate parent identifier |
| `coarse` | string | Valid H/I coarse decision after applicable error repair |
| `fine` | string or null | A-H for coarse-I targets; null for coarse-H targets |
| `label` | string | Final A-H label; coarse H maps to H, coarse I uses its fine label |

Missing fine labels for coarse-I records are errors, not valid null final labels.
The export preserves post grouping from the reference order. Disconnected
branches are removed. A post that has no retained labeled comment is absent from
this comment-level file.

## Direct-reply edge CSV

| Column | Meaning |
|---|---|
| `post_id` | Original post identifier |
| `subreddit` | Lowercase subreddit name |
| `community_type` | `MH` or `General`, according to the code's subreddit mapping |
| `parent_comment` | Parent comment identifier |
| `comment_id` | Direct child/reply comment identifier |
| `p_label` | Parent's final A-H label |
| `c_label` | Reply's final A-H label |
| `parent_author`, `child_author` | Source account identifiers, or empty strings when missing |

A row is a direct comment-to-comment reply, not a chronological adjacency and
not a post-to-comment response. `MH` maps to `depression`, `anxiety`,
`suicidewatch`, `bpd` and `mentalhealth`; other nonempty subreddit names map to
`General`. Use this mapping only with the study's intended subreddit set.

## Post-manifest CSV for analysis

`analysis/build_edges.py --posts-out` writes:

| Column | Meaning |
|---|---|
| `post_id` | Original post identifier |
| `subreddit`, `community_type` | Group membership |
| `month` | Source partition from the labeled records |
| `n_comments` | Number of retained labeled comments in this post |
| `n_edges` | Number of direct comment-to-comment reply edges |

This includes represented posts with `n_edges = 0`. It does not include selected
posts with `n_comments = 0`; retain the external selection records to audit that
population. Post-level and comment-level denominators must be distinguished.
