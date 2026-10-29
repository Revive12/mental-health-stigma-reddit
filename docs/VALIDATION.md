# Release validation

Validation performed on 29 October 2026 using Python 3.10.11 on macOS arm64. `requirements-tested-cpu.txt` records the installed CPU packages. This environment is a release-check environment, not the historical production environment.

## Completed checks

| Check | Result |
|---|---|
| Offline regression suite | 34 tests passed: 11 preprocessing, 13 annotation/export, 10 analysis |
| Command-line entry points | All 18 pipeline/analysis CLI `--help` commands completed successfully without GPU dependencies |
| Preprocessing fixture | Stages 1-7 exercised on fictional local inputs; stage 5 predictions supplied as a fixture, not inferred by a model |
| Annotation fixture | Selection, index and materialization integration; mocked fine API run/resume; strict export/failure handling |
| Documented synthetic analysis route | 48 fictional discussions, 4,480 comments and 4,096 edges; distributions and 2,000 whole-post bootstrap replicates with both sensitivities completed |
| Additional analysis fixture | Stratified whole-post resampling with 2,000 replicates and both sensitivities completed |
| Exploratory clustering | Both CLI stages completed on a positive-feature fixture; empty features and unsupported k handled explicitly |
| Frozen data checks | Input hashes, corpus totals, edge totals, seven positive same-attribution associations, 38 of 41 eligible positive cross-attribution associations, and inference-family sizes checked |
| Aggregate recalculation | P and D within 1e-16, expected counts within 2e-12, LSA Z within 2e-14, BH values within 3e-16 of archived tables |
| Figure rendering | All three renderers completed: two main figures and five supplementary figures; reported canvas checks had no outside text |
| Source audit | Python syntax, non-English CJK text, personal filesystem paths and common embedded-key patterns checked |

The source audit is heuristic and does not establish the safety of arbitrary additional files. Fictional example labels are illustrative and have not undergone human annotation validation.

## Not performed or not established

- No full raw-corpus rerun, GPU detector execution, live LLM requests or new annotation-accuracy evaluation.
- No verification of the actual historical proportional-sampling implementation or its allocations.
- No exact reconstruction of the original bootstrap strata, seed, post frame or confidence intervals.
- No Windows runtime claim; annotation/indexing use POSIX features.
- The checks above were performed locally before publication. The included GitHub Actions workflow is configured for Python 3.10 and 3.12 on Ubuntu; consult the repository's Actions page for current remote results.
- No claim that qualitative thematic analysis is reproducible from the released fictional examples.

The aggregate and synthetic checks validate specific software behavior and supplied tables. They do not establish historical execution provenance, scientific validity of every annotation, or unrestricted rights to redistribute private data.
