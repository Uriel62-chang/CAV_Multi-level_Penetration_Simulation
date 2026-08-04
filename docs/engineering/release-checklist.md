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
- [ ] The complete pytest count matches the README release baseline (v0.4.2 pure branch: 458).
- [ ] `python -m compileall -q scripts tests`
- [ ] `mypy scripts/run_spec.py scripts/experiment_config.py scripts/provenance.py`
- [ ] GitHub Actions `python-quality` succeeds.
- [ ] GitHub Actions `sumo-smoke` succeeds with `data_quality=ok`.

> **v0.4.0 数据状态（2026-08 更新）**：v0.4.0 本地数据与图表已移除（用户拍板，
> 外部备份保留）——不再存在 v0.4.0.post2/post3 preservation gates 的核验对象；
> 历史复现需 checkout `v0.4.0.post3` tag（该 tag 保留完整工具链与数据）。

## v0.4.2 release gates

- [ ] **网格与配置**：`configs/v0.4.2/main.json`（3,888，含 SSM 采集——2026-08
      合并设计，安全维度并入主网格）dry-run 通过；端点 assignment 失活、
      cav_count 全整数。（旧独立 safety.json 已随合并设计删除）
- [ ] **数据闭包**：main 3,888 simulation/parse 全 SUCCESS；
      聚合 main 528 组；writer `complete=true`、零排除；
      `raw_status_inventory.jsonl`（3,888 条目）与 `result_handover.json`
      的产物 SHA 与外部 raw/CSV 匹配。（旧 safety 84 runs 已随合并设计删除）
- [ ] **provenance（如实记录，不声称 clean）**：main simulation manifest
      记录 `git_dirty=true`，不得表述为 runtime clean（porcelain 证据不能
      证明零 tracked diff）；parsing/writer 在未提交工作树修复后分别提交为
      `a21e05e`/`6637519`，caveat 已在 handover 披露。
- [ ] **正式输入字节锚点**：`net/scenario_{1,2,3}/net.json` 的 `-text` 豁免生效，
      HEAD blob 与正式运行字节 SHA 一致。
- [ ] **归档边界**：Git 内 = 1 份 aggregated CSV + handover + inventory +
      analysis + 3 图（main 3，`graph/v0.4.2/main/`）；
      raw_v0.4.2/ 与 run-level/subgroup/failed CSV、
      writer report 由 `.gitignore` 覆盖（外部保留）。
- [ ] **文档一致性**：README/report 的 v0.4.2 数值可定位到 tracked
      aggregate/result_analysis；`--v4-2`/`--outDir` 与 CLI 一致；
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
