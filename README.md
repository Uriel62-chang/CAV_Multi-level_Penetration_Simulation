# CAV Multi-level Penetration Simulation

> A reproducible SUMO experiment platform for evaluating how CAV penetration and car-following control affect **capacity, safety, emissions, and delay** under different road constraints.

`SUMO 1.27.1` · `Python 3.10+` · `10,080 simulations` · `5 random seeds` · `v0.4.0.post1`

[Key Findings](#key-findings) ·
[Scenario Design](#scenario-design) ·
[Core Results](#core-results) ·
[Quick Start](#quick-start) ·
[Experiment Report](REPORT.md) ·
[Engineering Audit](ENGINEERING_AUDIT.md) ·
[Migration](MIGRATION.md) ·
[Release Checklist](RELEASE_CHECKLIST.md)

---

## Research Question

> **Do the capacity gains of CAV car-following control come with safety, emission, or travel-time costs?**

The project compares **IDM** and **CACC** across four progressively constrained road structures. Rather than asking which model is universally better, it asks:

> **Which control strategy performs better under which road structure and traffic density?**

---

## Scenario Design

The four scenarios support three controlled comparisons:

- `s0 → s1`: geometry smoothing;
- `s1 → s2`: added lateral freedom;
- `s2 → s3`: introduction of a 125 m `2→1→2` merge bottleneck.

![Four controlled road scenarios](graph/v0.4.0/scenario_overview.png)

*From left to right, the scenarios isolate geometry smoothing, added lateral freedom, and the effect of a merge bottleneck.*

---

## Key Findings

### 1. CACC releases capacity in an unconstrained dual-lane network

In scenario **s2** at `pCAV = 1.0`, CACC reaches a peak flow of **7,128 veh/h**, compared with **6,276 veh/h** for IDM—a **13.6% increase**.

Mean lap delay at this operating point is close to zero for both models.

> This benefit is scenario-dependent and does not persist under the merge constraint in s3.

### 2. The advantage reverses at a high-density merge bottleneck

In scenario **s3** at `vehN = 120` and `pCAV = 1.0`:

| Model | Flow | Mean lap delay | CO₂ intensity |
|---|---:|---:|---:|
| IDM | **3,204 veh/h** | **74.2 s** | 228 g/veh-km |
| CACC | 1,536 veh/h | 215.8 s | 345 g/veh-km |

At this fixed high-density operating point, IDM carries approximately **2.1 times** the flow of CACC while producing much lower delay and CO₂ intensity.

> These values describe one fixed operating point, not the absolute peak capacities of s3. The s3 peak capacities are 3,902 veh/h for IDM and 3,564 veh/h for CACC.

### 3. TTC conflicts concentrate around geometric and topological constraints

Under the current `TTC < 3.0 s` SSM configuration:

- s0 contains frequent conflicts associated with periodic sharp-turn braking;
- s1 contains relatively few conflicts;
- s2 contains no detected TTC conflicts within the tested parameter grid;
- s3 contains dense conflict activity around forced merging.

The observed distribution is consistent with road geometry and loss of lateral freedom being major contributors to conflict formation.

> This interpretation is limited to the current SSM threshold, model parameters, and experiment grid. Trajectory-level validation and threshold sensitivity analysis are planned for v0.4.1.

---

## Core Trade-off

![Safety versus flow trade-off](graph/v0.4.0/chart_safety_flow.png)

*CACC achieves high throughput in smooth, unconstrained networks, but the same advantage does not transfer directly to a dense merge bottleneck.*

---

## Why This Matters

Earlier versions of the project primarily evaluated CAV performance through **traffic capacity**. Capacity alone, however, cannot determine whether a traffic state is also safe, energy-efficient, or time-efficient.

v0.4.0 therefore extends the evaluation framework to four dimensions:

| Dimension | Primary metric | Supporting metrics |
|---|---|---|
| Capacity | Traffic flow and peak capacity | Mean speed and temporal speed variance |
| Safety | TTC conflicts per 1,000 veh-km | Minimum TTC, DRAC, emergency braking and lane-change gaps |
| Emissions | CO₂ g/veh-km | NOx, PMx and fuel consumption |
| Efficiency | Mean lap delay | P95 delay, lap-time variation and time loss |

All safety and emission intensity metrics use `total_vehicle_km` as the common normalization denominator.

The results indicate that **no single car-following model is globally optimal across road structures**. CACC performs strongly in smooth and unconstrained environments, while its high-throughput regime can deteriorate under forced merging.

---

## Core Results

All plots are generated from five-seed aggregated data. Means and variability are retained in `aggregated_results.csv`.

### Capacity

CACC outperforms IDM in s1 and s2 under high CAV penetration. The global peak of **7,128 veh/h** occurs in s2 with CACC at `pCAV = 1.0`.

The s3 bottleneck reduces peak capacity by approximately 45–50% relative to s2, and IDM performs better than CACC at the highest tested density.

![Capacity response across four scenarios](graph/v0.4.0/chart_capacity.png)

### Safety–Flow Trade-off

The main safety metric is:

```text
TTC conflict events / 1,000 vehicle-km
```

This normalized rate is used instead of raw TTC totals because total travelled distance differs across traffic densities and congestion states.

The principal trade-off is shown in the overview figure above:

- s0 conflicts are associated with periodic braking at 90° corners;
- s3 conflicts concentrate around the merge bottleneck;
- s1 contains few conflicts;
- s2 contains no detected conflicts under the current configuration.

### CO₂–Flow Trade-off

In unconstrained scenarios, differences between IDM and CACC are relatively small and are largely associated with traffic density.

Under the high-density s3 bottleneck, CACC's flow reduction, delay increase, and CO₂ deterioration occur simultaneously.

![CO2 intensity versus traffic flow](graph/v0.4.0/chart_co2_flow.png)

### Lap Delay

Scenarios s1 and s2 remain close to free-flow operation under most tested conditions. Delay in s0 accumulates through repeated braking at the four sharp corners.

Scenario s3 produces the largest delays. At `pCAV = 1.0` and `vehN = 120`, mean CACC lap delay reaches **215.8 s**, compared with **74.2 s** for IDM.

![Mean lap delay across CAV penetration levels](graph/v0.4.0/chart_delay.png)

### Scenario-Dependent Summary

| Scenario | CACC relative to IDM | Primary interpretation |
|---|---|---|
| s0 — sharp geometry | Small capacity gain; conflicts persist | Sharp corners repeatedly disturb longitudinal flow |
| s1 — smooth single lane | Clear capacity advantage; few conflicts | Smooth geometry supports stable dense following |
| s2 — smooth dual lane | **Largest capacity advantage**; no detected TTC | Dual lanes reduce longitudinal constraints and permit lane-changing |
| s3 — merge bottleneck | **Advantage reverses** at high density | Forced merging disrupts the high-throughput regime observed in s2 |

> **Main result:** under the current experimental configuration, CACC is highly effective in smooth, unconstrained networks, but its capacity advantage can diminish or reverse under a dense merge bottleneck.

This is an experimental observation rather than a claim that either model is universally superior. Full causal verification requires vehicle-level trajectory analysis.

---

## Experiment Design

```text
4 scenarios
× 2 car-following models
× 21 CAV penetration levels
× 12 vehicle-count levels
× 5 random seeds
= 10,080 SUMO simulations
```

| Parameter | Value |
|---|---|
| Scenarios | s0, s1, s2, s3 |
| CAV models | IDM, CACC |
| CAV penetration | 0.00–1.00 in increments of 0.05 |
| Vehicle count | 10–120 in increments of 10 |
| Vehicle-type assignment seeds | 1–5 |
| Simulation duration | 3,600 s |
| Warm-up period | 600 s |
| Simulation step | 0.1 s |
| Detector period | 120 s |
| SSM TTC threshold | 3.0 s |
| SSM DRAC threshold | 3.0 m/s² |
| Emission class | HBEFA3/PC_G_EU4 for both HV and CAV |

`--seed` only shuffles the Python-generated CAV/HV type assignment across fixed
initial positions. It is not a SUMO random seed; the pipeline does not pass
`--seed` or `--random` to SUMO. Run metadata records this scope as
`seed_scope="vehicle_type_assignment"`.

The formal experiment grid is defined in
[`configs/v0.4.0.json`](configs/v0.4.0.json). Batch runs load this versioned
configuration by default:

```bash
python3 -m scripts.simulation.batch_run \
  --config configs/v0.4.0.json \
  --dry-run
```

CLI grid options are explicit overrides. The resolved configuration and its
stable SHA-256 are written to `manifest.json`, so an overridden run remains
auditable. Invalid penetration levels, duplicate/empty lists, inconsistent
network mappings, non-positive frequencies, and `warmup >= simulation_end` are
rejected before any run directory is created.

Each prepared run contains `run_spec.json` with the complete simulation
parameters and derived penetration metadata (`requested_pcav`, `cav_count`,
`hv_count`, and `realized_pcav`). `simulation_status.json` references its
SHA-256; the parser refuses a missing or modified RunSpec instead of rebuilding
parameters from the run directory name.

For small vehicle populations, `realized_pcav` can differ from
`requested_pcav` because the CAV count follows Python's existing
`round(vehicle_count * requested_pcav)` rule. The existing CSV `pCAV` field
continues to mean the requested value for v0.4.0 compatibility.

The experiment-level `manifest.json` is created before SUMO starts. It records
the full planned grid, Git state, Python/SUMO/netconvert versions, platform,
launch command, resolved configuration hash, and SHA-256 values for every
network and `net.json`. Interrupted runs therefore remain distinguishable from
tasks that were never started.

Simulation, parsing, and writing form a verified metadata chain. Resume checks
the RunSpec, configuration, network, experiment and summary hashes; changing a
summary or input prevents a stale result from being silently reused. The parser
reads the pipeline version from `manifest.json` by default.

The 120-second detector period covers approximately two free-flow laps in the smooth scenarios and avoids the sampling resonance previously observed with a 60-second period.

Full configuration details, vehicle parameters, result tables, discussion and references are available in the [Experiment Report](REPORT.md).

---

## Metric Methodology

### Why use SUMO SSM for TTC?

SUMO already knows the road topology, lane relationships and conflict participants. Using SSM avoids reconstructing leader–follower relationships from global Cartesian coordinates on curved and merging roads.

### Why normalize by vehicle-kilometres?

Different vehicle counts and congestion states produce different total travelled distances. Raw event or emission totals are therefore not directly comparable.

```text
TTC event rate
= TTC conflict count / total vehicle-km × 1,000
```

```text
CO₂ intensity
= total CO₂ / total vehicle-km
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

## Data Quality

```text
10,080 / 10,080  simulations completed
2,016 / 2,016    aggregated groups with n_valid = 5
67 / 67          automated tests passed
0                duplicate run IDs
0                parser failures
0                invariant violations
```

The testing strategy contains three levels:

1. parser fixture unit tests;
2. short SUMO smoke and positive-event tests;
3. representative multi-scenario integration tests and full-grid closure checks.

During the original batch, 74 runs failed because of memory pressure. They were rerun with one concurrent SUMO process and all were recovered before aggregation.

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
67 passed
```

### Run one simulation

```bash
python3 -m scripts.simulation.single_run \
  --vehN 60 \
  --pCAV 0.5 \
  --model IDM \
  --net net/scenario_2/loop.net.xml
```

### Regenerate the v0.4.0 figures

```bash
python3 -m scripts.results.visualization \
  --aggregated results/aggregated_results.csv \
  --v4
```

<details>
<summary><strong>Full 10,080-run reproduction workflow</strong></summary>

```bash
# Stage 1: parallel SUMO simulation
python3 -m scripts.simulation.batch_run \
  --config configs/v0.4.0.json \
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
  --output /path/to/results/aggregated_results.csv

# Generate the four trade-off figures
python3 -m scripts.results.visualization \
  --aggregated /path/to/results/aggregated_results.csv \
  --v4
```

</details>

**Hardware guidance for `--sumo-processes`.** SUMO processes are CPU-bound and memory-hungry—each loads the network independently and writes raw XML output. RAM is the binding constraint; s3 at vehN=120 is the worst case per process. Before launching a full grid, check your machine:

| Resource | Rule of thumb | Check |
|---|---|---|
| RAM | Budget **2 GB per SUMO process** for headroom (s3 vehN=120 can spike); total SUMO memory must fit within *available* RAM | `free -h` (look at the `available` column) |
| CPU | `--sumo-processes ≤ nproc − 2` (reserve at least two logical cores for the OS and the Python parent) | `nproc` |
| Disk | ~6 GB per 1,000 runs with SSM compact mode; **~600 GB** if `--device.ssm.trajectories` is `true` (the default) | `df -h <output-root>` |
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

## Data Availability

The repository includes:

- `results/aggregated_results.csv`  
  2,016 scenario–model–penetration–vehicle-count groups aggregated across five random seeds;

- experiment manifest and plotting scripts;

- the four v0.4.0 result figures under `graph/v0.4.0/`;

- parser fixtures and unit tests.

All published figures can be regenerated from `aggregated_results.csv`.

The following files are not included because of storage size:

- raw SUMO XML outputs;
- per-run `summary.json` files;
- the full run-level dataset, unless published separately.

After SSM compaction, the retained raw experiment directory is approximately 58 GB. The complete dataset can be regenerated through the pipeline above.

> Update this section if `run_level_results.csv` is also included or released through an external archive.

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

results/
└── aggregated_results.csv

graph/v0.4.0/
├── scenario_overview.png
├── chart_capacity.png
├── chart_safety_flow.png
├── chart_co2_flow.png
└── chart_delay.png
```

---

## Limitations

- Emission and safety metrics are not yet separated into HV and CAV sub-populations.
- The absence of detected TTC conflicts in s2 applies only to the current `TTC < 3.0 s` threshold and tested parameter grid.
- ACC is supported by earlier project versions but is not part of the formal v0.4.0 comparison.
- TTC events have not yet been independently reproduced using FCD or TraCI trajectories.
- Five random seeds describe observed variability but should not automatically be interpreted as formal statistical significance.
- The free-flow lap baseline should be extended with an additional CACC single-vehicle comparison.
- Current unit tests focus on four parser modules and do not yet fully cover the scheduler and orchestration layers.

---

## Roadmap

| Version | Focus |
|---|---|
| v0.4.1 | HV/CAV subgroup metrics, physical THW, FCD/TraCI TTC validation and threshold sensitivity |
| v0.5.0 | Real-trajectory-driven car-following model calibration and simulation validation |
| v0.6.0 | TraCI-based dynamic traffic control |
| v0.7.0 | CACC communication degradation, including packet loss and latency |

---

## Documentation

| Document | Purpose |
|---|---|
| [Experiment Report](REPORT.md) | Complete experimental design, result tables, discussion and conclusions |
| `scripts/` source | Inline docstrings; see § Repository Structure below for module map |

---

## Citation

When using this project, please cite the repository and release version:

```bibtex
@software{cav_multi_level_penetration_simulation_2026,
  author  = {Uriel62-chang},
  title   = {CAV Multi-level Penetration Simulation},
  version = {v0.4.0.post1},
  year    = {2026},
  url     = {https://github.com/Uriel62-chang/CAV_Multi-level_Penetration_Simulation}
}
```

---

## License

This project is released under the [MIT License](LICENSE).
