# Release Checklist (v0.4.2)

> 本清单分三部分：通用/质量 gate（所有版本）、历史 post2/post3 保留 gate（v0.4.0
> 系列，原样保留）、v0.4.2 release gates（按 v0.4.2 实际 provenance 与产物验收）。
> 历史 gate 不因 v0.4.2 发布而回填勾选；v0.4.2 只勾选实际执行并验证的项。

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
- [ ] The complete pytest count matches the README release baseline (v0.4.2: 462).
- [ ] `python -m compileall -q scripts tests`
- [ ] `mypy scripts/run_spec.py scripts/experiment_config.py scripts/provenance.py`
- [ ] GitHub Actions `python-quality` succeeds.
- [ ] GitHub Actions `sumo-smoke` succeeds with `data_quality=ok`.

## v0.4.0.post2 preservation gates（历史保留，不因 v0.4.2 回填）

- [ ] `configs/v0.4.0.json` and its resolved 10,080 run IDs match the engineering baseline.
- [ ] Model parameters, networks, vehicle placement and SUMO command hashes are unchanged.
- [ ] `pipeline_version` remains `v0.4.0.post1` and `schema_version` remains `1`.
- [ ] `results/aggregated_results.csv` metric values and published figures are unchanged.
- [ ] The aggregated CSV has unique column names; the duplicate count header is renamed only.
- [ ] Requested/realized pCAV differences, duplicate treatments and assignment-seed limits are disclosed.
- [ ] `python -m scripts.experiment_audit` reports 10,080 / 2,400 / 400 / 768 for the frozen v0.4.0 grid.
- [ ] Interpretive claims inconsistent with the preserved numeric results are corrected rather than retained for textual compatibility.
- [ ] No historical run is deleted, relabelled or presented as a new independent treatment.

## v0.4.0.post3 correction gates（历史保留，不因 v0.4.2 回填）

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

## v0.4.2 release gates

- [ ] **网格与配置**：`configs/v0.4.2/main.json`（3,888）与 `safety.json`（84）
      dry-run 通过；主配置 SHA `a293545f…`、Safety `84df0e53…` 记录于
      grid-design 冻结附录；端点 assignment 失活、cav_count 全整数。
- [ ] **数据闭包**：main 3,888 + safety 84 simulation/parse 全 SUCCESS；
      聚合 main 528 / safety 84 组；writer 两份 `complete=true`、零排除；
      `raw_status_inventory.jsonl`（3,972 条目）与 `result_handover.json`
      的 15 文件 SHA 与外部 raw/CSV 匹配。
- [ ] **provenance（如实记录，不声称 clean）**：main simulation manifest
      记录 `git_dirty=true`，不得表述为 runtime clean（porcelain 证据不能
      证明零 tracked diff）；parsing/writer 在未提交工作树修复后分别提交为
      `a21e05e`/`6637519`，caveat 已在 handover 披露。
- [ ] **正式输入字节锚点**：`net/scenario_{1,2,3}/net.json` 的 `-text` 豁免生效，
      HEAD blob 与正式运行字节 SHA 一致。
- [ ] **归档边界**：Git 内 = 2 份 aggregated CSV + handover + inventory +
      analysis + 5 图（main 3 + safety 2，safety 图位于 `graph/v0.4.2/safety/`）；
      raw_v0.4.2/ 与 run-level/subgroup/failed CSV、
      writer report 由 `.gitignore` 覆盖（外部保留）。
- [ ] **main/Safety 配对静态验收**：`scripts.results.pairing_checker --main-root raw_v0.4.2/main --safety-root raw_v0.4.2/safety` 输出 `all_match=true`（84 共享键四类输入 SHA + 非 SSM 规范化命令一致）；`results/v0.4.2/pairing_report.json` SHA 记录于 handover。
- [ ] **文档一致性**：README/report 的 v0.4.2 数值可定位到 tracked
      aggregate/result_analysis；`--v4-2`/`--safety`/`--outDir` 与 CLI 一致；
      Markdown 相对链接有效；禁止性措辞扫描通过。
- [ ] **审查冻结**：当前 SHA 获正式 Reviewer 背书（阶段一独立复算 + delta +
      阶段二对账）；打 tag 前无未背书新 commit；tag 精确指向背书 SHA。
- [ ] **发布动作（实际执行后勾选）**：`git tag v0.4.2 <背书 SHA>`、push
      main + tag、GitHub release 创建、README 引用图可用性复核。

## Full experiment rerun only（通用未来 rerun guidance；不是 v0.4.2 事后验收结论）

- [ ] The rerun is a new versioned experiment and does not overwrite v0.4.0/post3.
- [ ] A small-scale correctness check and resource estimate precede the full rerun; resource behaviour is not a veto on the study publication.
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
