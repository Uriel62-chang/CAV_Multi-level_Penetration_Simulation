# Release Checklist (v0.4.0.post2)

## All releases

- [ ] Working tree changes have been reviewed and committed.
- [ ] Package version, README, citation and changelog use the release version.
- [ ] Release, experiment config, pipeline and schema version boundaries are documented.
- [ ] README commands and all local Markdown links are valid.
- [ ] Public documentation is tracked; `docs/internal/` remains ignored.

## Quality gates

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest -q`
- [ ] The complete pytest count matches the README release baseline.
- [ ] `python -m compileall -q scripts tests`
- [ ] `mypy scripts/run_spec.py scripts/experiment_config.py scripts/provenance.py`
- [ ] GitHub Actions `python-quality` succeeds.
- [ ] GitHub Actions `sumo-smoke` succeeds with `data_quality=ok`.

## v0.4.0.post2 preservation gates

- [ ] `configs/v0.4.0.json` and its resolved 10,080 run IDs match the engineering baseline.
- [ ] Model parameters, networks, vehicle placement and SUMO command hashes are unchanged.
- [ ] `pipeline_version` remains `v0.4.0.post1` and `schema_version` remains `1`.
- [ ] `results/aggregated_results.csv` metric values and published figures are unchanged.
- [ ] The aggregated CSV has unique column names; the duplicate count header is renamed only.
- [ ] Requested/realized pCAV differences, duplicate treatments and assignment-seed limits are disclosed.
- [ ] `python -m scripts.experiment_audit` reports 10,080 / 2,400 / 400 / 768 for the frozen v0.4.0 grid.
- [ ] Interpretive claims inconsistent with the preserved numeric results are corrected rather than retained for textual compatibility.
- [ ] No historical run is deleted, relabelled or presented as a new independent treatment.

## Full experiment rerun only

- [ ] The release uses `requirements-lock.txt`.
- [ ] Python, SUMO and netconvert versions appear in the manifest.
- [ ] The Git commit is recorded and the formal run uses a clean worktree.
- [ ] A dry run is reviewed before the full grid starts.
- [ ] Network and `net.json` hashes are recorded in the manifest.
- [ ] Simulation, parsing and writer manifests cover the planned grid.
- [ ] `failed_runs.csv` is empty or every exclusion is explained.
- [ ] Writer report is complete and contains no duplicate/missing run IDs.
- [ ] Historical data is handled according to `migration.md`.
- [ ] Resume is tested against an unchanged run and rejects modified inputs.
