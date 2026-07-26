# Release Checklist (v0.4.0.post3)

## All releases

- [ ] Working tree changes have been reviewed and committed.
- [ ] Package version, README, citation and changelog use the release version.
- [ ] Release, experiment config, pipeline and schema version boundaries are documented.
- [ ] README commands and all local Markdown links are valid.
- [ ] A clean clone can build all four `loop.net.xml` files with `network_generator --build-all`.
- [ ] Public documentation is tracked; `docs/internal/` remains ignored.

## Quality gates

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest -q`
- [ ] `python -m scripts.simulation.batch_run --config configs/smoke.json --dry-run`
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

## v0.4.0.post3 correction gates

- [ ] SUMO is not rerun; frozen raw XML and post2 results remain preserved.
- [ ] Reanalysis covers all 10,080 runs and records source/output SHA-256 hashes.
- [ ] The 30,240 raw XML inputs have a deterministic per-file SHA-256 inventory.
- [ ] Reanalysis reruns invariants and reports 10,080 valid / 0 invalid rows.
- [ ] Published CSVs expose requested/realized pCAV, edge scope and assignment-run count semantics.
- [ ] Across-seed ratio aggregation is documented as equal-run-weight arithmetic statistics, not a pooled ratio.
- [ ] SSM TTC/DRAC inclusion uses each metric's extreme time.
- [ ] Warmup is an exact multiple of both detector and edgeData frequencies.
- [ ] edgeData performance and emissions exclude intervals before warmup.
- [ ] All normalized metrics use the common `[600, 3600)` window.
- [ ] Historical `withInternal=false` scope and the safety numerator/denominator spatial mismatch are disclosed.
- [ ] Capacity claims are phrased as maximum observed flow within the tested grid.
- [ ] Corrected run-level and aggregated outputs are generated outside the raw archive.
- [ ] Figures and every reported normalized safety/emissions value use post3 data.
- [ ] Writer `complete` requires zero excluded runs and every written row to have `data_quality=ok`.
- [ ] Data availability states that raw XML and run-level CSV are external, so the Git repository alone cannot rerun post3.

## Full experiment rerun only

- [ ] The rerun is a new versioned experiment and does not overwrite v0.4.0/post3.
- [ ] A bounded pilot has passed predefined correctness, randomness, storage and runtime gates.
- [ ] Requested treatments map to intended `cav_count/realized_pcav` values without accidental duplicate compositions.
- [ ] Vehicle-type assignment seeds and independent SUMO random seeds are separate and documented.
- [ ] Safety-event and vehicle-km spatial scopes are matched, including an explicit internal-edge policy.
- [ ] IDM and CACC have separately verified free-flow reference runs.
- [ ] FCD/TraCI and SSM retention settings have measured storage budgets before grid expansion.
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
