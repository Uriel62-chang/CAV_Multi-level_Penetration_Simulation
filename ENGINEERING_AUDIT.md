# Engineering-Only Change Audit

This refactoring is constrained to code quality, project structure,
reproducibility and validation. It does not revise the published experimental
logic or reinterpret existing results.

## Behaviour preserved

The current workspace was compared directly with Git commit
`07a5952f3d34c100463d4d3f0f0b287c440c0fb2`.

Using the same representative RunSpec for all four scenarios, the following
outputs are byte-for-byte identical:

- `routes.rou.xml`;
- `additional.add.xml`;
- the normalized SUMO argument list.

All 12 SHA-256 comparisons matched. The frozen values are stored in
`tests/baselines/v0.4.0-engineering.json` and enforced by pytest.

The following were also compared with the pre-improvement code:

- default task count: 10,080 in both versions;
- sorted run ID set SHA-256:
  `03ce02d733f30cc41d370e0e62505e0a5893fa8e50a2d0b454cc904250204da3`;
- all model, vehicle, lane-change, threshold and timing constants in
  `scripts/config.py`: identical values;
- SUMO commands contain neither `--seed` nor `--random`.

## Changes intentionally permitted

- complete RunSpec persistence and hashes;
- versioned experiment configuration;
- provenance and terminal state records;
- strict resume and metadata validation;
- unified parser/writer paths;
- packaging, dependency lock, tests, lint, type checking and CI;
- explicit network metadata that describes existing geometry;
- isolated, visibly unverified legacy parsing.

## Full-grid execution

The engineering audit does not rerun all 10,080 simulations. A full rerun is
not required because the experimental inputs and command semantics are
byte-identical and both single-run and batch end-to-end SUMO smoke tests pass.
The historical published result set remains authoritative.

A full-grid rerun becomes necessary only after an explicitly approved change
to experimental models, parameters, networks, vehicle placement, SUMO command
semantics or metric definitions.
