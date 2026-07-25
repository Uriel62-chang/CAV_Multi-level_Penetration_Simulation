# v0.4.0 Raw Data Migration

The reproducible pipeline intentionally does not treat historical raw
directories as current-schema runs.

## Current run requirements

A current run directory must contain:

- `run_spec.json` with all simulation parameters and derived penetration data;
- `simulation_status.json` referencing the RunSpec, configuration, network and
  experiment hashes;
- the required non-empty SUMO XML outputs;
- after parsing, `parse_status.json` and a hash-verified `summary.json`.

The experiment root must contain `manifest.json` with the resolved
configuration, provenance and the complete planned run grid.

## Historical v0.4.0 raw directories

Historical directories that only encode parameters in names such as
`s3_CACC_p050_v120_seed1` do not contain enough information to prove the
simulation end time, warm-up, frequencies, input hashes or environment.
Current parsing therefore rejects them by default. Renaming a directory or
manually fabricating hashes is not a supported migration.

For read-only analysis of historical raw XML, use the explicit compatibility
entry and supply assumptions where they differ from the old defaults:

```bash
python -m scripts.parsing.batch \
  --input-root /path/to/historical/raw \
  --legacy \
  --legacy-end 3600 \
  --legacy-warmup 600 \
  --legacy-step-length 0.1 \
  --legacy-detector-frequency 120 \
  --legacy-edge-frequency 300 \
  --legacy-loops 300
```

This writes `legacy_summary.json` and `legacy_parse_status.json`; it never
writes current `summary.json` or `parse_status.json`. Legacy output carries
`quality="legacy_unverified"` and is deliberately rejected by the current
writer.

Use one of these approaches:

1. Keep previously published CSV files as historical results and retain their
   original release/tag and environment notes.
2. Re-run the experiment from `configs/v0.4.0.json` to create fully traceable
   current-schema raw data.
3. If historical XML must be re-analysed, use the original v0.4.0 code in an
   isolated checkout and label the output as legacy/unverified. Do not merge it
   into a current-schema manifest.

This conservative boundary prevents old data from silently acquiring metadata
that was never recorded.
