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
      （smoke 配置 ssm_enabled=false / capture TTC=5.0 与 main（true / 3.0）不同——
      **仅冒烟用，勿作比照**；dry-run 不校验该口径）
- [ ] The complete pytest count matches the README release baseline (v0.4.2: 492).
- [ ] free-flow artifact 门禁（收敛审核 P2）：`runner.py` 对 `sumo_version` 多行字节精确匹配——**升级/重编译 SUMO 会整批解析失败，需重生成 free-flow artifact**（fail-closed 设计，防跨版本错误复用参考；勿强行绕过）。
- [ ] `python -m compileall -q scripts tests`
- [ ] `mypy scripts/run_spec.py scripts/experiment_config.py scripts/provenance.py`
- [ ] GitHub Actions `python-quality` succeeds.
- [ ] GitHub Actions `sumo-smoke` succeeds with `data_quality=ok`.

> **v0.4.0 数据状态（2026-08 更新）**：v0.4.0 本地数据与图表已移除（用户拍板，
> 外部备份保留）——不再存在 v0.4.0.post2/post3 preservation gates 的核验对象；
> 历史复现需 checkout `v0.4.0.post3` tag（该 tag 保留完整工具链与数据）。

## v0.4.2 release gates

- [ ] **网格与配置**：`configs/v0.4.2/main.json`（**7,524**，U55 统一密度轴；SSM 全开——合并设计）dry-run 通过；端点 assignment 失活、cav_count
      全整数。（旧独立 safety.json 已随合并设计删除；旧 7,524/3,888 网格为历史）
- [ ] **数据闭包**：main 7,524 simulation/parse 全 SUCCESS（U55 正式重跑后）；
      聚合 main **924 组**（4 场景 × 11 vehN × 21 组/vehN：cav=0 单模型 + 10 档 ×
      2 模型；interior n=9 / endpoint n=3）；writer `complete=true`、零排除；
      `raw_status_inventory.jsonl`（7,524 条目）与 `result_handover.json` 的产物
      SHA 与外部 raw/CSV 匹配。（旧 7,524/3,888 + safety 84 历史数据已清空）
- [ ] **provenance（如实记录，不声称 clean）**：main simulation manifest
      记录 `git_dirty=true`，不得表述为 runtime clean（porcelain 证据不能
      证明零 tracked diff）；parsing/writer 在未提交工作树修复后分别提交为
      `a21e05e`/`6637519`，caveat 已在 handover 披露。
- [ ] **正式输入字节锚点**：`net/scenario_{1,2,3}/net.json` 的 `-text` 豁免生效，
      HEAD blob 与正式运行字节 SHA 一致。
- [ ] **数据与归档边界（2026-08 正式网格）**：Git 内 = 工具链 + 正式网格结果
      （`results/v0.4.2/main/aggregated_results.csv` 已 ship、`graph/v0.4.2/` 6 图
      （5 main-grid + 1 analysis）、
      `configs/v0.4.2/main.json`、net/、artifacts/free_flow/ 解析依赖）；
      raw 76 GB / run-level / subgroup 留外部备份；历史旧网格数据已清空。
- [ ] **文档一致性**：README/report 的 v0.4.2 数值为 U55 正式数字（924 组、
      492 tests）；`--v4-2`/`--outDir` 与 CLI 一致；Markdown 相对链接有效
      （含 report 双链与 graph/v0.4.2/ 图引用）；禁止性措辞扫描通过。
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
