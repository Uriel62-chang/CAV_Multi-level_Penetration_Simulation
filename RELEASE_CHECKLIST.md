# Release Checklist

## Code and configuration

- [ ] Working tree changes have been reviewed and committed.
- [ ] `configs/v0.4.0.json` resolves to 10,080 unique runs.
- [ ] No experimental model parameters or SUMO seed behaviour changed.
- [ ] Network and `net.json` hashes are recorded in the manifest.
- [ ] Pipeline and schema versions are consistent.

## Quality gates

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest -q`
- [ ] `python -m compileall -q scripts tests`
- [ ] `mypy scripts/run_spec.py scripts/experiment_config.py scripts/provenance.py`
- [ ] GitHub Actions `python-quality` succeeds.
- [ ] GitHub Actions `sumo-smoke` succeeds with `data_quality=ok`.

## Reproducibility

- [ ] The release uses `requirements-lock.txt`.
- [ ] Python, SUMO and netconvert versions appear in the manifest.
- [ ] The Git commit is recorded and the formal run uses a clean worktree.
- [ ] A dry run is reviewed before the full grid starts.
- [ ] Resume is tested against an unchanged run and rejects modified inputs.

## Results and documentation

- [ ] Simulation, parsing and writer manifests cover the planned grid.
- [ ] `failed_runs.csv` is empty or every exclusion is explained.
- [ ] Writer report is complete and contains no duplicate/missing run IDs.
- [ ] README commands match the released CLI.
- [ ] Historical data is handled according to `MIGRATION.md`.
- [ ] Release notes state the exact configuration and schema versions.
