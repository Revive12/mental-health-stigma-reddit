# Release preparation changes

## Processing and annotation

- Replaced Chinese source comments, messages and documentation with English.
- Fixed data-root resolution, month validation, required-input checks and nested subreddit handling.
- Corrected tree-root checks; reject duplicate, cyclic and cross-post graph records.
- Kept GPU dependencies optional and recorded detector settings for resume validation.
- Required an externally selected post manifest; hashing now only orders that selection.
- Preserved whole posts within annotation batches; separated dry-run materialization state from annotation state.
- Required explicit model configuration; fixed fine-annotation output and endpoint handling.
- Added strict label checks, retryable failures, configuration-aware resume and output locking.
- Export now fails on missing labels instead of treating failures as non-stigmatizing.
- Preserved the supplied fine prompt byte-for-byte.

## Analysis and reproducibility

- Corrected reply-edge reconstruction when a child precedes its parent in the file.
- Added post manifests, structured distribution reports, and a primary statistical reference implementation.
- Documented unknown historical bootstrap settings and preprocessing differences.
- Marked clustering as exploratory; require explicit k and handle empty feature profiles.
- Included frozen aggregate tables, portable figure renderers, checksums and reported-value checks.
- Added synthetic fixtures, regression tests, dependency specifications and a CI workflow.

## Public release

- Added MIT licensing for original code and documentation, with data excluded from the grant.
- Added a separate data-examples directory with fictional records and an explicit schema.
- Excluded original Reddit text, IDs, private annotation exports, credentials and generated caches.

The release fixes are prospective. They do not establish that historical execution used the repaired code or that every original estimate has been regenerated.
