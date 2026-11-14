# Performance baselines

This guide describes how to collect comparable measurements for representative
pykit workloads. Measurements are evidence for later changes; wall time is not a
test threshold.

## Procedure

Run from the repository root on an otherwise idle machine. Unset `VIRTUAL_ENV`
before running the commands below. Install the project environment with
`task setup`. Record the baseline commit, CPU, OS and version, Python version,
and uv version alongside the results. The measurement fixture records the
commit, Python version, platform, inputs, wall time, traced peak memory,
operation counts, and workload kind in JSON Lines. Record CPU and uv version
with the run; the installed uv version can be read from its package installation
metadata without invoking it directly.

Choose an absolute output directory and set `PYKIT_MEASURE_OUT` for the package
measurements:

```bash
PYKIT_MEASURE_OUT=/absolute/path/to/results task test
```

This runs all package suites; only measurement cases run when the variable is
set. The root scaffold measurement is selected separately:

```bash
PYKIT_MEASURE_OUT=/absolute/path/to/results \
SUITE_ARGS='-c pyproject.toml -q packages/rn-forge-cli/tests/measure/test_scaffold.py::test_scaffold_setup' \
task ci:suites
```

`-c pyproject.toml` selects the root configuration; the package configuration
deselects scaffold cases. The scaffold case times the session wheel build and
one clean-venv install. The build count comes from the returned wheel set.
Workspace wheels are supplied locally; third-party requirements resolve from the
package index.

Time the strict documentation build separately. On macOS, capture elapsed time
and peak resident memory with:

```bash
/usr/bin/time -l task docs:build
```

On Linux, use:

```bash
/usr/bin/time -v task docs:build
```

The command runs 11 strict builds: the root site and ten package sites. Record
the elapsed time and peak resident memory from the platform's time output.

`tracemalloc` peak memory covers Python allocations in the measured process; it
does not include child processes or native allocations. CLI subprocess cases
record child peak RSS separately. `ru_maxrss` is reported in bytes on macOS and
KiB on Linux. Keep both values as captured and annotate the units when comparing
platforms.

## Workloads

| Package | Measurement | Inputs and counts | Kind |
| -- | -- | -- | -- |
| CLI | Cold and warm `run(app, ["--help"])`, plus `python -X importtime -c "import rn_forge.cli"` | Child RSS and import count | Tool startup |
| Commons | Disabled and enabled logging to an in-memory handler | 10,000 records | CPU |
| Web | Sync readiness with eight slow checks | 8 checks at 0.2 seconds each, timeout unset and set | I/O |
| Data | Excel write then load | 50,000 rows × 10 columns; file size | Buffering |
| Auth | JWT verification against local JWKS server, including one key rotation | 100 verifications; JWKS request count | I/O |
| SQLAlchemy | SQLite upsert of initial and mixed rows | 33,000 initial rows and 33,000 mixed rows; SQL statement count | I/O |
| CLI scaffold | Built workspace wheels and one clean-venv install | Build count and duration; install duration | Tool startup |
| Docs | Strict root and package builds | 11 builds | Tool startup |

`web.transfer` contains wire-format helpers and does not call `write_xlsx`, so
there is no matching transfer export workload. The SQLAlchemy measurement
remains separate from the ordinary test suite's large-input regression.

## Baseline record

The initial baseline target is `1a8da87`. Measurements were collected on
2026-11-14 at checkout `0a388e917eac36c1cb7ec031b48dd555edefc563`, whose changes
from the target commit are confined to spec documents. The package source is
unchanged from `1a8da87`.

Environment: Mac mini (Mac14,12), Apple M2 Pro, 10 CPU cores (6 performance and
4 efficiency), 16 GB RAM; macOS 27.2 (26B123), arm64; Python 3.14.2. Installed
uv is 0.13.7, read from the Homebrew installation symlink
(`/opt/homebrew/Cellar/uv/0.13.7/bin/uv`). The machine was not idle: other agent
jobs ran concurrently. These timings are provisional; the reviewer may re-record
them on an idle machine.

### `1a8da87` baseline

Wall times are seconds; memory values are bytes. Peak memory is traced Python
allocation memory unless labelled child RSS or docs RSS. Counts are observed
values, not performance thresholds.

| Workload | Inputs | Wall (s) | Peak (bytes) | Counts |
| -- | -- | -- | -- | -- |
| Logging enabled | records=10000, enabled=True | 0.157393 | 871,754 | attempted_records=10000, records=10000 |
| Logging disabled | records=10000, enabled=False | 0.005638 | 64 | attempted_records=10000, records=0 |
| CLI warm help | calls=1, warmup_calls=1 | 0.014642 | 111,827 | calls=1, imports=861 |
| CLI import | processes=1 | 0.106406 | 341,302; child RSS 42,418,176 | imports=400 |
| CLI cold help | processes=1 | 0.131324 | 315,297; child RSS 46,809,088 | imports=500 |
| SQLite upsert | initial_rows=33000, mixed_rows=33000 | 1.903825 | 30,528,457 | statements=76 |
| Readiness, no timeout | checks=8, sleep_s=0.2, timeout_s=None | 0.210633 | 64,867 | checks=8, sum_sleeps_s=1.600000 |
| Readiness, 1 s timeout | checks=8, sleep_s=0.2, timeout_s=1.0 | 0.209087 | 56,621 | checks=8, sum_sleeps_s=1.600000 |
| Excel round trip | rows=50000, columns=10 | 22.409027 | 225,496,023 | bytes=1577014, rows=50000, cells=500000 |
| Auth key refresh | verifications=100, rotations=1 | 0.096936 | 290,111 | verifications=100, requests=2 |
| Scaffold setup | requirement=rn-forge-cli | 0.539040 | 710,899 | build_wall_s=0.242943, builds=10, install_wall_s=0.294780, installs=1 |
| Docs | 11 strict builds | 25.39 | docs RSS 146,210,816 | 11 builds |

Docs figures are from `/usr/bin/time -l task docs:build`: elapsed (`real`) and
maximum resident set size.
