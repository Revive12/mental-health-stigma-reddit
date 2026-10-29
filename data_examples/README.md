# Fictional annotation examples

`synthetic_annotations.jsonl` contains eight newly authored fictional examples, one for each A-H label. They are not copied or paraphrased from the private alignment exports. `schema.json` describes this nested explanatory format.

These examples demonstrate post context, previous comments, target comments, and the attribution decision. E illustrates agreement with a stigmatizing previous comment; H illustrates rejection of that judgment. Speaker and example identifiers have no correspondence to real Reddit users or records.

Labels are illustrative, not human-validated gold labels. These records were not used in the paper, cannot estimate accuracy or inter-rater agreement, and are not a substitute for the original validation sample. Do not pool them with observations.

This format is for understanding annotation. For a runnable analysis input in the flattened export format, use `examples/make_synthetic_data.py` as described in the main README. That generator assigns labels to artificial structures to test software; its text is not semantically matched to every assigned label.

The original 80/160/160-task alignment exports are excluded under the confirmed aggregate-only public-data policy. They contain post/comment text, platform identifiers, annotator metadata and potentially quoted model reasoning. They will not be included as a public real-data sample in this release. See the [data release policy](../docs/DATA_RELEASE.md). The MIT code license does not grant rights over data files.
