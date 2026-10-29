# Public data scope and sharing rationale

The author confirmed the following policy on 29 October 2026: publish aggregate results and withhold the original record-level Reddit dataset. This repository therefore includes aggregate manuscript tables and clearly fictional software or annotation examples. It excludes original Reddit text, platform/user identifiers, source-ID mappings and individual real annotation records, including small subsets. The private alignment exports will not be published in this release.

## What the private alignment files represent

Three supplied exports contain 80, 160 and 160 annotation tasks. They include original post/context/target text, platform identifiers and annotation-system metadata. This is 400 task records, not a verified count of independent comments. Their overlap and relationship to calibration and final evaluation are not established. They must not be described as the complete study data or an independent test set.

Removing usernames alone is insufficient: verbatim text can be searched, and post/comment IDs directly link annotations to source content. Hashing an original identifier does not by itself establish anonymity. Free-text annotation reasons can also quote source text.

## Confirmed release scope

| Purpose | Public material | Interpretation |
|---|---|---|
| Show input structure and exercise code | Original fictional JSONL, schema and generator | A software example, not empirical evidence |
| Explain stigma attribution decisions | Versioned prompt, codebook and clearly labeled illustrative examples | Operational annotation definitions |
| Inspect reported results | Real aggregate source tables and plotting/statistical code | Verification of published aggregate values, not full annotation reproduction |
| Original real-data examples or alignment exports | Not included in the public release | The exclusion also applies to small subsets |
| Verify individual labels or sampling | No public record-level release | Any additional verification arrangement must be established separately; fictional examples do not provide it |

## Manuscript excerpts and verification limits

The public dataset decision does not establish that qualitative excerpts already appearing in the manuscript have been anonymized or paraphrased. Review those excerpts separately for traceability. If the manuscript also promises that no verbatim text appears anywhere, its qualitative examples must be brought into line with that promise. Do not state that all excerpts have been paraphrased unless this has actually been completed and checked.

For any paraphrased manuscript excerpt, preserve the psychological meaning, endorsement/rejection relationship and context needed to determine attribution, and have the interpretation reviewed. An altered excerpt is not the original record used to calculate historical accuracy or kappa. Internal example identifiers must not expose a public source mapping.

CSV is used for aggregate tables and JSONL for fictional nested examples. These are engineering choices, not Nature journal requirements. Public aggregates support inspection of reported estimates; they do not permit complete reannotation, resampling or qualitative verification of the underlying corpus.

## Relevant published examples

| Source | Location and practice |
|---|---|
| [Linguistic comparison of AI- and human-written responses to online mental health queries, npj Artificial Intelligence (2026)](https://www.nature.com/articles/s44387-026-00099-x) | Methods: Data and study design; Data availability. Avoids public verbatim posts/comments and reports aggregate results; access to real data is subject to safeguards and agreements. |
| [Exploring negative experiences in psychotherapy using an NLP approach on online forum data, npj Mental Health Research (2025)](https://www.nature.com/articles/s44184-025-00172-4) | Ethical considerations; Data availability. Redacts identifiers, paraphrases quotations and reviews them; shares analysis materials and ID lists without redistributing verbatim text. Its ID-sharing choice should not be copied automatically because IDs reconnect sensitive annotations to sources. |
| [Understanding phenomenological experiences of autistic inertia using online community discourse, Communications Psychology (2026)](https://www.nature.com/articles/s44271-025-00386-4) | Ethical issues; Data availability. Replaces usernames, paraphrases many quotations, and restricts the full qualitative data despite de-identification. |
| [Interaction with AI companions and psychological well-being, Nature Human Behaviour (2026)](https://www.nature.com/articles/s41562-026-02516-2) | Data availability and linked supplementary sections. Shares de-identified quantitative materials while withholding sensitive raw chat transcripts; includes processed materials and paraphrased excerpts. This is a chat study, not a Reddit-data example. |

These examples support separating public analytical materials from sensitive original text. They do not establish a universal prohibition or show that fictional data are a journal requirement. The fictional fixtures in this repository are a project-specific engineering choice.

## Policy and manuscript alignment

[Nature's reporting policy](https://www.nature.com/nature/editorial-policies/reporting-standards) requires transparent access conditions for the data needed to interpret, verify and extend a study. Restrictions must be disclosed to editors and readers. Controlled access requires concrete reasons, eligibility/conditions, a contact, response timeframe and applicable use restrictions. A generic promise of data on request is insufficient if no workable access process exists. Authors must not promise access they cannot provide.

The current [Reddit for Researchers Program rules](https://support.reddithelp.com/hc/en-us/articles/49381918834964-Reddit-for-Researchers-Program) restrict redistribution under that program. The historical corpus here was described as archive-derived; its actual governing terms must be checked separately. The current program rules should not be presented as a definitive legal conclusion about every historical archive.

The reviewed manuscript Ethics statement excludes public raw text, identifiers and individual comment annotations. The confirmed release follows that boundary. Data availability should identify the aggregate files and repository location, while Ethics should explain the restriction. Draft language is provided in [MANUSCRIPT_AVAILABILITY.md](MANUSCRIPT_AVAILABILITY.md). No controlled-access service is promised by this release, and fictional records must not be called the original study dataset.
