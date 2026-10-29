# Methods alignment and provenance

This release distinguishes archived study outputs, repaired processing code, and a reconstructed statistical reference implementation. It does not present an unverified new run as a reproduction of the original study.

## Items requiring manuscript or provenance confirmation

| Topic | Evidence and implications |
|---|---|
| Post selection | The authors report proportional stratified selection by subreddit and year/month. The supplied historical index globally ordered posts by MD5; the old README selected a prefix of batches. No historical stratification script or allocation log was supplied. Keep the actual sampling description in Methods and provide its verified selection manifest privately. Hash ordering is not stratification. |
| Upstream selection | Its implementation is omitted from this public release at the authors' request. This boundary must remain explicit; omission of code does not justify omission of the sampling method from the paper. A seed, per-stratum eligible/selected counts, and manifest checksum would improve reproducibility if recovered. |
| Observation window | Stage 2 reads matching-month archives only. Describe same-month observation, not lifetime-complete discussions. No quantified proportion of truncated discussions was independently verified here. |
| Submission types | Stage 3 tests identifiers and word count, not text-only submission status. Do not claim explicit link/image/video exclusion unless a separate historical step can be documented. |
| Placeholder and bot filtering | Filtering is upstream in this release and removes bot descendants. Historical record-level handling differed. Execution may yield different counts; exact equivalence is not established. |
| AI-text detector | The score threshold is strictly greater than 0.5 and the input truncation is 512 tokens. Report the checkpoint and threshold. Classification is not certain evidence of machine authorship. |
| Annotation models | Manuscript documentation names Qwen3-14B and GPT-5.5; the old README used Qwen3-8B in an example. This release requires explicit model configuration. Confirm historical model versions, endpoints, dates, decoding settings and checkpoints from actual logs. |
| Fine prompt | The supplied V4.4 prompt is byte-identical. SHA256: `49a979abb145acae3ff91538f92a3124e6a272cfa4b5a1f41bff2a3274664193`. Its operational definitions, especially E and F, must be described accurately. Preservation does not prove it was used for every historical run. |
| Denominators | Flat comment files cannot represent selected posts with no retained comments; edge tables omit posts with no comment-to-comment edges. Preserve the relevant post frame. The index counts selected posts without trees; the analysis post manifest retains comment-bearing posts with zero edges. |
| Bootstrap | Archived notes describe 2,000 stratified whole-post replicates. Original strata, seed and complete resampling frame were not supplied. `main_analysis.py` defaults explicitly to ordinary whole-post resampling and permits verified strata. Exact historical intervals are not claimed reproducible. |
| Primary analysis | The original package included exploratory clustering but not the full primary inferential pipeline. The added primary analysis is a reconstructed reference. Frozen estimates are used to render reported figures. |
| Clustering | Posts enter through nonzero selected transition profiles. This is not clustering of all sampled posts. The chosen k is a user decision, not an automatically established optimum. |
| Annotation-alignment exports | The private files contain 80, 160 and 160 tasks. Overlap and relationship to final evaluation sampling are not established. Do not describe these 400 task records as the whole analysis corpus, 400 independent observations, or an independent held-out validation set. |
| Public data | Reviewed manuscript ethics text excludes raw text, identifiers and individual comment annotations from public release. Public contents must match that statement, or the actual access plan and manuscript must be revised together. |

## Archived outputs

Aggregate tables were copied from archived figure and results directories. `manuscript_results/source_manifest.json` records their hashes. Verification recovers 104,373 posts, 6,091,206 comments, 86,247 stigmatizing comments in 20,110 posts, 2,746,063 reply pairs, 161 eligible excess-probability tests and 36 eligible group contrasts.

These checks establish consistency among supplied tables. They do not verify sampling history, recompute labels, or establish causal diffusion of stigma.

## Qualitative analysis

No original case table, private transcript archive, or complete qualitative coding audit is included. This repository does not claim to reproduce thematic interpretation. Any future paraphrased examples must be distinguished from original quotations and from quantitative validation data.
