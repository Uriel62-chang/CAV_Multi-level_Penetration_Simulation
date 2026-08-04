# CAV Multi-level Penetration Simulation

> A reproducible SUMO experiment platform for evaluating how CAV penetration and car-following control affect **observed flow, safety, emissions, and reference-relative lap time** under different road constraints.

`SUMO 1.27.1` · `Python 3.10+` · `3,888 simulations` · `v0.4.2`

[Formal-grid Results](#v042-formal-grid-results) ·
[Scenario Design](#scenario-design) ·
[Metric Methodology](#metric-methodology) ·
[Quick Start](#quick-start) ·
[Engineering Audit](docs/engineering/audit.md) ·
[Migration](docs/engineering/migration.md) ·
[Release Checklist](docs/engineering/release-checklist.md)

---

## Research Question

> **Do the observed-flow gains of CAV car-following control come with safety, emission, or travel-time costs?**

The project compares **IDM** and **CACC** across four progressively constrained road structures. Rather than asking which model is universally better, it asks:

> **Which control strategy performs better under which road structure and traffic density?**

---

## Scenario Design

The four scenarios support three structured scenario comparisons:

- `s0 → s1`: geometry smoothing;
- `s1 → s2`: a transition to two lanes with added lateral freedom and lower per-lane density at fixed `vehN`;
- `s2 → s3`: introduction of a 125 m `2→1→2` merge bottleneck.

![Four progressively structured road scenarios](graph/scenario_overview.png)

*From left to right, the scenarios progressively change geometry, lane count/lateral freedom, and merge constraints. These comparisons do not isolate a single causal factor.*

---

## v0.4.2 Formal-grid Results（历史观测记录）

> **2026-08 数据状态**：v0.4.0 与 v0.4.2 历史数据已全部清空（用户拍板，外部备份
> 保留）——`raw_v0.4.2/`（33 GB）、`results/v0.4.2/`、`graph/v0.4.2/`、`docs/report.md`
> 已删除；仓库为纯工具链 + 未来重跑定义。下文数值为历史观测记录，供设计参考，
> 未来重跑（main 全开 SSM 采集）后更新。

v0.4.2 (jump release) ran a formal grid independent of the v0.4.0 historical
baseline: a **3,888-run main factorial covering all four evaluation dimensions**
(flow, safety, emissions, efficiency; 4 scenarios × 12 vehN × 81 runs per
(scenario, vehN) — cav=0: 3 + interior 4 levels × 2 models × 3 assignment
seeds × 3 SUMO seeds: 72 + cav=vehN: 6 — with endpoint assignment
deactivation). **2026-08 合并设计**：安全维度并入主网格（main 全开 SSM 采集，
未来重跑生效）；旧的独立 safety experiment（84 runs）板块已取消。

### Main factorial

Key grid-observed results at the corresponding operating points:

- **s2, CACC, pCAV=1.0, vehN=120**: grid-observed maximum flow **7,128 veh/h**
  (IDM 6,276 veh/h, +13.6%);
- **s3, vehN=120, pCAV=1.0**: IDM **3,204 veh/h** / CACC 1,536 veh/h — the
  high-density merge-bottleneck reversal holds (IDM ≈ 2.1× CACC flow and
  a much smaller reference-relative lap time);
- scenario grid-observed peaks: s0 1,856.4, s1 4,178.4 (CACC, vehN=70),
  s2 7,128, s3 3,902.4 veh/h.

### Safety dimension (merged into the main grid)

- **安全维度随主网格采集**（合并设计 2026-08）；旧的独立 safety 板块（84 runs、
  单 seed pair）已取消——每格安全指标将获得与流量/排放同等的 3×3 seed 统计强度；
- **s1 and s2 show zero detected TTC events** — limited to the current
  `TTC < 3.0 s` threshold, SUMO 1.27.1, the safety grid and the configured SSM
  parameters; this is not a claim of "no conflict";
- SSM-on sampled peak RSS by scenario: s0 6.52 / s1 1.81 / s2 8.91 /
  s3 1.50 GiB (global peak 9,342,124 KiB @ s2_CACC_v120_c120) — historical
  observation context, not a hard budget;
- the subgroup table (HV/CAV) is a single-point (vehN=120, cav=96)
  descriptive summary and cannot decompose model-difference causes.

---



## Why This Matters

Earlier versions of the project primarily evaluated CAV performance through **traffic capacity**. Capacity alone, however, cannot determine whether a traffic state is also safe, energy-efficient, or time-efficient.

This project extends the evaluation framework to four dimensions:

| Dimension | Primary metric | Supporting metrics |
|---|---|---|
| Flow performance | Traffic flow and maximum observed flow within the tested grid | Mean speed and temporal speed variance |
| Safety | TTC conflicts per 1,000 non-internal-edge veh-km | Minimum TTC, DRAC, emergency braking and lane-change gaps |
| Emissions | CO₂ g/non-internal-edge veh-km | NOx, PMx and fuel consumption |
| Efficiency | Mean lap-time difference from fixed reference | P95 reference difference, lap-time variation and time loss |

All safety and emission intensity metrics use `total_vehicle_km` from edgeData over `[600, 3600)`. The historical additional file used SUMO's default `withInternal="false"`: the denominator excludes junction internal edges, while SSM events are not restricted to the same edge subset. Consequently, normalized safety values are **whole-network events divided by non-internal-edge exposure**, not fully space-matched event rates. Emission numerator and denominator are mutually matched but both represent non-internal edges.

The results indicate that **no single car-following model is globally optimal across road structures**. CACC performs strongly in smooth and unconstrained environments, while its high-throughput regime can deteriorate under forced merging.

---



## Metric Methodology

### v0.4.2 measurement scope

The v0.4.2 grid uses `withInternal="true"` edgeData, so the safety event
numerator and the vehicle-kilometre denominator share the same spatial scope
(whole network including junction internal edges). Emissions are accumulated
under two paired scopes: the primary intensity is non-internal-edge
CO₂ g / non-internal-edge veh-km (the same estimand definition as v0.4.0, so
the two versions are intended to be comparable at the definition level), and
a secondary whole-network intensity is reported alongside (`whole_network_*`
columns in the run-level and aggregated CSVs). Because the acquisition
pipeline, `withInternal` handling and seed design differ, the v0.4.0 and
v0.4.2 grids are **not numerically interchangeable**: no cross-version
numeric-consistency or change-rate inference is drawn between them.

### Why use SUMO SSM for TTC?

SUMO already knows the road topology, lane relationships and conflict participants. Using SSM avoids reconstructing leader–follower relationships from global Cartesian coordinates on curved and merging roads.

### Why normalize by vehicle-kilometres?

Different vehicle counts and congestion states produce different total travelled distances. Raw event or emission totals are therefore not directly comparable.

```text
TTC event rate
= whole-network TTC conflict count
  / non-internal-edge vehicle-km × 1,000
```

This is the historical post3 normalization label, not a fully space-matched
full-network risk rate.

```text
CO₂ intensity
= non-internal-edge CO₂ / non-internal-edge vehicle-km
```

### Why use `vehroute exitTimes` for lap time?

In a closed-loop network, unfinished trip duration represents the time a vehicle exists in the simulation, not the duration of one completed lap.

Lap times are reconstructed from successive route-edge exit times.

### Why distinguish `0` and `NaN`?

```text
0   = the source was parsed successfully and no event occurred
NaN = the source was missing, invalid, inapplicable or could not be parsed
```

Detailed definitions are documented in the source (see `scripts/schema.py` for field definitions and `scripts/parsing/runner.py` for invariant validation).

---

## Reproducible Pipeline

```text
10,080 RunSpec
        │
        ▼
6-worker parallel SUMO
        │
        ▼
independent run directories
        │
        ▼
serial seven-parser pipeline
        │
        ▼
summary.json × 10,080
        │
        ▼
single result writer
        │
        ▼
run_level_results.csv
        │
        ▼
five-seed aggregation
        │
        ▼
aggregated_results.csv
        │
        ▼
publication figures
```

| Stage | Main function | Wall time |
|---|---|---:|
| Parallel simulation | Six concurrent SUMO processes | ~17 h |
| Serial parsing | Seven parsers and invariant validation | 13.5 min |
| Result writer | 10,080 summaries → run-level CSV | ~2 s |
| Five-seed aggregation | 10,080 rows → 2,016 groups | ~1 s |

The simulation scheduler provides:

- deterministic `run_id` generation;
- isolated output directories;
- resume support;
- atomic status files;
- timeout and cancellation handling;
- heavy-task-first scheduling.

The parser pipeline provides:

- serial low-memory XML parsing;
- atomic `summary.json` and `parse_status.json`;
- resume support;
- explicit parser failure semantics;
- seven cross-metric invariant checks.

---

## Data Quality（历史观测，2026-08 数据已清空）

```text
3,888 / 3,888  main-factorial simulations completed (SUCCESS)   ← 历史观测
528 / 528      main aggregated groups                           ← 历史观测
440            automated tests passed（当前门禁基线）
0              duplicate run IDs
0              parser failures
0              invariant violations
```

> 前三行为 v0.4.2 历史数据质量记录（数据已清空）；当前仓库以 440 tests 门禁为
> 基线。未来重跑后按相同链路重新记录。

The testing strategy contains three levels:

1. parser fixture unit tests;
2. short SUMO smoke and positive-event tests;
3. representative multi-scenario integration tests and full-grid closure checks.

---

## Quick Start

### Requirements

```bash
sumo --version
python3 --version
```

Recommended versions:

```text
SUMO >= 1.27.1
Python >= 3.10
```

Create an isolated environment and install the locked development dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
```

SUMO remains a system dependency and is not part of the Python lock file.

Compile the four ignored/generated SUMO network files from the tracked
node/edge sources before running a simulation:

```bash
python3 -m scripts.simulation.network_generator --build-all
```

With SUMO/netconvert 1.27.1, this reproduces the network XML used by the
v0.4.2 experiment apart from generation metadata such as timestamp and output
path. Scenario 3 is built from its tracked bottleneck-specific edge source; it
is not reconstructed from an undocumented manual edit.

### Run the quality gates

```bash
pytest -q
ruff check .
ruff format --check .
mypy scripts/run_spec.py scripts/experiment_config.py scripts/provenance.py
python -m compileall -q scripts tests
```

Expected result:

```text
458 passed
```

### Run one simulation

```bash
python3 -m scripts.simulation.single_run \
  --vehN 60 \
  --pCAV 0.5 \
  --model IDM \
  --net net/scenario_2/loop.net.xml
```

### Regenerate the v0.4.2 figures

Two separate commands (option spelling is case-sensitive `--outDir`); output
directories are written to `/tmp` by default below so the Git-tracked figures
under `graph/v0.4.2/` are not overwritten:

```bash
# main-factorial figures (capacity / CO2-flow / delay)
python3 -m scripts.results.visualization \
  --aggregated results/v0.4.2/main/aggregated_results.csv \
  --v4-2 --outDir /tmp/v042-figs/main
```

<details>
<summary><strong>Full formal-grid reproduction workflow</strong></summary>

```bash
# Stage 1: parallel SUMO simulation
python3 -m scripts.simulation.batch_run \
  --config configs/v0.4.2/main.json \
  --sumo-processes 6 \
  --resume \
  --output-root /path/to/raw

# Stage 2: serial parsing
python3 -m scripts.parsing.batch \
  --input-root /path/to/raw \
  --resume

# Stage 3: single result writer
python3 -m scripts.results.writer \
  --input-root /path/to/raw \
  --output-dir /path/to/results \
  --manifest /path/to/raw/manifest.json

# Aggregate across seeds (mean / std / median / min / max)
python3 -m scripts.results.aggregate \
  --input /path/to/results/run_level_results.csv \
  --output /path/to/results/aggregated_results.csv \
  --schema-version 2 --manifest /path/to/raw/manifest.json
```

</details>

> 纯净分支说明：`reanalyze_post3.py`（v0.4.0.post3 重分析工具）已随
> v0.4.0~post3 兼容支持移除。历史 post3 数据的复现/重分析需 checkout
> `v0.4.0.post3` tag（该 tag 保留完整工具链）。

**Hardware guidance for `--sumo-processes`.** SUMO processes are CPU-bound and memory-hungry—each loads the network independently and writes raw XML output. RAM is the binding constraint; s3 at vehN=120 is the worst case per process. Before launching a full grid, check your machine:

| Resource | Rule of thumb | Check |
|---|---|---|
| RAM | Budget **2 GB per SUMO process** for headroom (s3 vehN=120 can spike); total SUMO memory must fit within *available* RAM | `free -h` (look at the `available` column) |
| CPU | `--sumo-processes ≤ nproc − 2` (reserve at least two logical cores for the OS and the Python parent) | `nproc` |
| Disk | ~6 GB per 1,000 runs with the default compact SSM output (`--device.ssm.trajectories=false`); the v0.4.0 experiment previously produced 423 GB in total (~42 GB per 1,000 runs) when full SSM trajectories were explicitly enabled | `df -h <output-root>` |
| I/O | Run directories are independent (no file conflicts), but a spinning disk may bottleneck at high concurrency | SSD strongly recommended |

**Pick your concurrency from available RAM** (CPU is rarely the bottleneck first):

| Available RAM | Safe `--sumo-processes` | Example machine |
|---|---|---|
| 8 GB | 1–2 | lightweight laptop |
| 12–16 GB | 2–4 | typical dev laptop / small desktop |
| 24–32 GB | 4–8 | workstation |
| 48+ GB | 8–12 | server |

Always run with `--resume` from the first launch—it costs nothing on a clean start and lets you recover from OOM kills or power loss without repeating completed work. If SUMO processes exit with non-zero codes at high vehicle counts (typically s3 vehN ≥ 100), cut `--sumo-processes` in half and resume; the offending runs will be re-attempted with less memory pressure.

---

## Data Availability（2026-08 数据已清空）

> v0.4.0 与 v0.4.2 历史数据已全部删除（用户拍板，外部备份保留）：
> `raw_v0.4.2/`（33 GB raw + 解析产物）、`results/v0.4.2/`（聚合/证据链/分析）、
> `graph/v0.4.2/`（图）、`docs/report.md`（v0.4.0 报告）、`raw/`（v0.4.1 pilot）、
> `routes/`（生成物）均已移除。仓库当前为纯工具链 + 未来重跑定义：
> `configs/v0.4.2/main.json`（3,888 runs，含 SSM 采集——2026-08 合并设计）为
> 未来重跑的实验定义；`artifacts/free_flow/` 自由流参考保留（解析输入依赖）。
> 未来重跑后，数据将按既有 writer / aggregate / handover / inventory 链路
> 重新产生并归档。


---

## Repository Structure

```text
scripts/
├── config.py
├── run_spec.py
├── schema.py
├── simulation/
│   ├── single_run.py
│   ├── batch_run.py
│   ├── flow_generator.py
│   └── network_generator.py
├── parsing/
│   ├── runner.py
│   ├── batch.py
│   ├── detector.py
│   ├── stderr.py
│   ├── ssm.py
│   ├── lanechange.py
│   ├── edge_performance.py
│   ├── edge_emissions.py
│   └── vehroute.py
└── results/
    ├── writer.py
    ├── aggregate.py
    └── visualization.py

tests/
├── fixtures/
├── test_ssm_parser.py
├── test_vehroute_parser.py
├── test_edge_performance_parser.py
├── test_edge_emissions_parser.py
└── run_tests.py

results/          （2026-08 数据清空后为空；未来重跑后由 writer/aggregate 重建）

graph/
└── scenario_overview.png

docs/
├── README.md
└── engineering/
    ├── audit.md
    ├── migration.md
    └── release-checklist.md
```

---

## Limitations

- The formal CSV carries the explicit penetration/identity columns
  (`realized_pcav`, `cav_count`, `hv_count`) and space-matched
  event-rate aliases; the historical v0.4.0~post3 legacy columns and the
  `requested_pcav` contract column are no longer produced on head (see the
  `v0.4.0.post3` tag for the archived schema; `requested_pcav` remains only
  as an internal `RunSpec` field for re-parsing archived raw runs).
- The `(assignment_seed, sumo_seed)` pairs are vehicle-type assignment and
  SUMO stochastic realizations; endpoint penetrations deactivate the
  assignment dimension (sentinel 0) and keep the SUMO seed active, so endpoint
  replication counts do not represent independent assignment realizations.
- Across-seed means and standard deviations are equal-weight descriptive
  summaries of assignment runs, not pooled exposure ratios, confidence
  intervals or significance tests.
- The v0.4.2 formal grid provides HV/CAV subgroup results (run-level subgroup
  long table + aggregated subgroup metrics, detector/edgeData/SSM/vehroute/
  lanechange/stderr + FCD physical THW).
- The absence of detected TTC conflicts in s2 applies only to the current `TTC < 3.0 s` threshold and tested parameter grid.
- ACC is supported by earlier project versions but is not part of the formal
  comparison.
- TTC events have not yet been independently reproduced from FCD or TraCI trajectories; v0.4.1 provides the trajectory-validation tooling (FCD physical THW), and the v0.4.2 grid provides SSM-based event rates (merged into the main grid), but independent FCD/TraCI reproduction is still outstanding.
- SSM mirror deduplication is an analysis heuristic: opposite-direction records
  for the same vehicle pair are matched one-to-one when their encounter
  intervals overlap by at least 80% of the shorter duration. SUMO provides no
  shared event ID for deterministic pairing, so dense consecutive encounters
  may still be over- or under-deduplicated; absolute event counts should not be
  interpreted as exact physical conflict totals.
- v0.4.1 adds model-specific free-flow references (HV/IDM/CACC) as validated
  artifacts (D-008); the reference table itself remains as published.
- Automated tests cover parsers, experiment configuration, RunSpec integrity,
  provenance, simulation state transitions, resume validation, result writing,
  aggregation, network metadata and representative SUMO pipelines. Regular CI
  does not rerun the complete formal grid (3,888 runs).

---

## Roadmap

| Version | Focus |
|---|---|
| v0.4.0.post3 | Unified observation-window reanalysis of the frozen 10,080-run grid (historical public release; head no longer ships v0.4.0~post3 code support) |
| v0.4.1 | Measurement and experimental-design upgrade: HV/CAV subgroup metrics, physical THW, compact FCD/TraCI validation, TTC threshold sensitivity, space-matched exposure, independent SUMO/assignment seeds, model-specific free-flow references, and a bounded pilot (internal milestone, **not released**; engineering outcomes folded into v0.4.2) |
| v0.4.2 | Formal grid (jump release): main factorial 3,888 runs (efficiency/emissions/FCD, SSM disabled) + independent safety experiment 84 runs |
| v0.5.0 | Real-trajectory-driven car-following model calibration and simulation validation |
| v0.6.0 | TraCI-based dynamic traffic control |
| v0.7.0 | CACC communication degradation, including packet loss and latency |

v0.4.1 delivered the measurement toolchain; its micro-pilot Level 1 (10 runs)
passed, and Level 2 bounded factorial pilot (162 runs) was completed but failed
the original resource gate (SSM memory exceeded 2 GiB at high density). The
v0.4.0 10,080-run grid was not re-run. v0.4.2 (jump release) ran the formal
grid: a 3,888-run main factorial with SSM disabled and an independent 84-run
safety experiment with space-matched exposure (see [Data Availability](#data-availability)).

---

## Documentation

| Document | Purpose |
|---|---|
| [Documentation index](docs/README.md) | Engineering audit, migration and release checklist |
| `scripts/` source | Inline docstrings; see § Repository Structure below for module map |

---

## Citation

When using this project, please cite the repository and release version:

```bibtex
@software{cav_multi_level_penetration_simulation_2026,
  author  = {Uriel62-chang},
  title   = {CAV Multi-level Penetration Simulation},
  version = {v0.4.2},
  year    = {2026},
  url     = {https://github.com/Uriel62-chang/CAV_Multi-level_Penetration_Simulation}
}
```

---

## License

This project is released under the [MIT License](LICENSE).
