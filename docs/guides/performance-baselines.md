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
| Data | `excel_write`: Excel write only, dataset built before measurement | 50,000 rows × 10 columns; bytes, rows, cells | Buffering |
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

### S22.4.4 allocation and algorithm costs

Baseline measurements used detached commit
`7f11a7caf0790ac0add12fe782896117456a7b92` with the measurement harness copied
into the checkout. Comparison measurements used
`be88ead000e59df8c1a02044863c19999da5821e` plus the uncommitted source changes.
Both runs used Python 3.14.2, macOS 27.2.1 (26B131), arm64, and uv 0.13.8 from
its Homebrew installation symlink. Hardware was a Mac mini (Mac14,12), Apple M2
Pro, 10 CPU cores (6 performance and 4 efficiency), 16 GB RAM. The machine's
idle status was not controlled.

Wall times are seconds; peak values are traced Python allocation bytes. Counts
and inputs are identical across each pair; they are observations, not test
thresholds. Raw records: `/tmp/S22.4.4-measure-baseline/results.jsonl` and
`/tmp/S22.4.4-measure-comparison/results.jsonl`.

| Workload | Inputs | Baseline wall / peak | Comparison wall / peak | Counts |
| -- | -- | -- | -- | -- |
| File digest | size_mib=8 | 0.004797 / 8,389,793 | 0.004155 / 395,368 | bytes=8,388,608 |
| File digest | size_mib=64 | 0.033831 / 67,110,053 | 0.032279 / 395,372 | bytes=67,108,864 |
| File digest | size_mib=256 | 0.135940 / 268,436,649 | 0.142800 / 395,376 | bytes=268,435,456 |
| Duplicate check | size=1,000 | 0.026543 / 1,830,392 | 0.013436 / 1,770,312 | names=1,000 |
| Duplicate check | size=4,000 | 0.153058 / 6,831,928 | 0.063503 / 6,917,500 | names=4,000 |
| Duplicate check | size=16,000 | 1.732357 / 27,293,232 | 0.280489 / 27,290,392 | names=16,000 |
| Dict merge, empty target | depth=8, fanout=4 | 0.068877 / 4,683,400 | 0.066504 / 4,683,400 | leaves=65,536 |
| Dict merge, equal target | depth=8, fanout=4 | 0.583678 / 1,670,120 | 0.073448 / 944 | leaves=65,536 |

File digests changed to streaming: traced peak stays near 395 KB for all file
sizes instead of growing with the file. Duplicate detection changed to a
single-pass count: baseline time grew 5.77× for the first 4× increase in names
and 11.32× for the second, with the largest case at 1.732 s; the larger step is
below the idealized 16× quadratic ratio because submission overhead is also
measured. Deep merge changed to copy on assignment: the equal-target workload
improved 87.42% in wall time and 99.94% in peak traced memory, exceeding the 30%
rule; the empty-target workload was essentially unchanged. No timing thresholds
were added to tests.

### 7f11a7c before and after S22.12.2

Collected on 2026-11-15 at checkout `be88ead000e59df8c1a02044863c19999da5821e`.
Before measurement, `excel.py` was unchanged from `7f11a7c`; after measurement,
only the redundant row list was removed. Both runs used the same machine with no
concurrent jobs launched by this agent. Process inspection was denied by the
sandbox, so other machine activity could not be verified.

Environment: Mac mini (Mac14,12), Apple M2 Pro, 10 CPU cores (6 performance and
4 efficiency), 16 GB RAM; macOS 27.2.1 (26B131), arm64; Python 3.14.2; uv
0.13.8, read from the Homebrew installation symlink
(`/opt/homebrew/Cellar/uv/0.13.8/bin/uv`).

Each workload uses 50,000 rows and 10 columns. Wall times are seconds; peaks are
traced Python allocation bytes. The write-only case builds the dataset before
tracing; the unchanged round-trip case includes dataset construction, writing
and loading.

| Workload | Phase | Wall (s) | Peak (bytes) | Counts |
| -- | -- | -- | -- | -- |
| `excel_write` | Before | 17.990195 | 8,679,433 | bytes=1577015, rows=50000, cells=500000 |
| `excel_write` | After | 16.409417 | 2,134,784 | bytes=1577015, rows=50000, cells=500000 |
| `excel_roundtrip` | Before | 24.422749 | 225,584,449 | bytes=1577015, rows=50000, cells=500000 |
| `excel_roundtrip` | After | 24.269110 | 225,328,754 | bytes=1577014, rows=50000, cells=500000 |

The write-phase traced peak fell by 6,544,649 bytes (75.4%); the round-trip peak
fell by 255,695 bytes (0.11%). The caller still holds the complete dataset, and
the function returns the complete workbook as bytes.

As with S22.3.2, these are observations, not thresholds or timing assertions.
Single-run timings vary with machine activity; `tracemalloc` excludes native
allocations and child processes, and these peaks are not process RSS. XLSX ZIP
metadata can vary between saves, including the resulting compressed size; byte
counts do not establish byte-for-byte identity.
