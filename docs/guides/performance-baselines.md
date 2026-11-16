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
| Tooling | Install a verified local release archive | 64 MiB; download, hash, and extract counts | Buffering |
| Auth | JWT verification against local JWKS server, including one key rotation | 100 verifications; JWKS requests; first, refresh and median cached verification seconds | I/O |
| Auth | Fill empty in-memory replay, transaction and session stores with live records | 1,000, 4,000 and 16,000 records; 1 hour TTL; operation count | CPU |
| SQLAlchemy | SQLite upsert of initial and mixed rows | 33,000 initial rows and 33,000 mixed rows; SQL statement count | I/O |
| Django | Export and batch get/create/update/delete over the transfer mixins | 100 to 9,000 rows; SQL query count, response bytes | I/O |
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
0.13.8.

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

### S22.9.3 transfer queries and memory

Collected on 2026-11-16 at checkout `c85de6ebcbb77d2ac7219413533e27448b867cf9`,
with the measurement tests uncommitted and production source unchanged.
Environment: Mac mini (Mac14,12), Apple M2 Pro, 10 CPU cores (6 performance and
4 efficiency), 16 GB RAM; macOS 27.2.1 (26B131), arm64; Python 3.14.2; uv
0.13.8. No concurrent jobs were launched by this agent during the single
measurement run. Process inspection was denied by the sandbox, so machine idle
status could not be verified. Raw records: `/tmp/S22.9.3-measure/results.jsonl`.

The dialect is SQLite. Wall times are seconds; peaks are traced Python
allocation bytes, not process RSS. Seeding is outside the measurement, and SQL
queries are counted with `connection.execute_wrapper`, without retaining SQL
strings. These are observations, with no memory or timing thresholds.

| Operation | Rows | wall_s | peak_bytes | queries | response_bytes |
| -- | -: | -: | -: | -: | -: |
| export | 1,000 | 0.057230 | 564,408 | 2 | 15,902 |
| export | 9,000 | 0.443740 | 3,580,505 | 2 | 151,902 |
| batch_get | 100 | 0.007705 | 91,932 | 1 | 2,300 |
| batch_get | 900 | 0.047507 | 708,616 | 1 | 22,300 |
| batch_create | 100 | 0.066071 | 223,712 | 202 | 4,592 |
| batch_create | 900 | 0.512092 | 1,534,374 | 1,802 | 43,901 |
| batch_update | 100 | 0.103678 | 1,177,539 | 103 | 2,110 |
| batch_update | 900 | 0.971890 | 8,608,042 | 903 | 19,710 |
| batch_delete | 100 | 0.026588 | 129,231 | 103 | 0 |
| batch_delete | 900 | 0.210383 | 817,316 | 903 | 0 |

All query counts match the brief's Current behaviour figures. All traced peaks
differ from its approximate figures; the largest difference is batch update at
900 rows: 8,608,042 bytes here versus about 6,218,092 bytes in the brief. No
source was changed to match those figures.

Writes cost queries per row by design: create 2, update 1, delete 1. Read query
counts do not grow with rows. Export is constant only for a viewset that shapes
its queryset; this measurement uses `select_related("team")` and related team
rows.

PostgreSQL slope guards also passed in `task ci:integration -- rn-forge-django`:
824 passed, 5 measurement cases skipped, 1 deselected. Resource measurements
above remain SQLite-only.

### d709103 before and after S22.11.2

Measurements were collected on 2026-11-15. The checkout was HEAD
`d709103f84c6ba50c0cf8b690ec3fd93991da8a7`; after measurements, the S22.11.2
upsert change was uncommitted. Both runs used a Mac mini (Mac14,12), Apple M2
Pro, 10 CPU cores (6 performance and 4 efficiency), 16 GB RAM; macOS 27.2.1
(26B131), arm64; Python 3.14.2; uv 0.13.8; SQLite 3.50.4. Five sequential task
test runs were collected before and after, with no other agent-launched jobs
during measurement. Machine idle status was not verified. Raw records:
`/tmp/S22.11.2-before/results.jsonl` and `/tmp/S22.11.2-after/results.jsonl` (20
records each).

Each case used 33,000 rows. Wall times are the median of five runs; peak memory
is the maximum observed traced Python allocation peak across five runs. These
measurements are evidence, not test thresholds. S22.11.1 set the all-new target
at 16 MiB; on 2026-11-16 the owner revised it to at most 27 MiB (28,311,552
bytes), because the remaining peak is the single write list and batching the
write would break the statement targets. The mostly unchanged target is at most
12 MiB (12,582,912 bytes), and the statement targets are 38 for single keys and
75 for composite keys.

| Workload | Before median wall (s) | After median wall (s) | Before peak (bytes) | After peak (bytes) | Statements before / after |
| -- | -: | -: | -: | -: | -: |
| Created, single key | 1.317372292 | 1.405893709 | 30,586,048 | 24,642,134 | 38 / 38 |
| Created, composite key | 2.182281083 | 1.929263417 | 31,005,526 | 26,804,635 | 75 / 75 |
| Mixed, single key | 0.636553333 | 0.706001833 | 14,826,115 | 3,835,424 | 38 / 38 |
| Mixed, composite key | 1.018990833 | 1.133083750 | 16,420,648 | 4,163,304 | 75 / 75 |

After the change, both all-new peaks (23.5 and 25.6 MiB) meet the revised target
and both mixed peaks meet 12 MiB; all statement targets were met before and
after. Median wall time changed by +6.72% for created single-key, -11.59% for
created composite-key, +10.91% for mixed single-key, and +11.20% for mixed
composite-key; the owner accepted these in place of the no-median-regression
target. The chunk-only trial peaked at 27,543,664 bytes for single keys and
29,455,034 bytes for composite keys, so audit values were bound once with
`insert.values(stamps)`.

PostgreSQL parity was checked separately with the integration service
(`task ci:integration -- rn-forge-sqlalchemy`): 167 passed, 2 expected failures
(the documented snapshot race), and only measurement cases skipped.

### 3027d9d S22.3.3 setup audit — 2026-11-16

Reviewer audit at `3027d9d`; environment recorded by the audit: macOS arm64,
Python 3.14, warm uv cache. Other jobs may have shared the machine, so wall
times are noisy. The audit did not record more specific hardware or version
details.

`task ci:suites` with `SUITE_ARGS='-q -m scaffold -c pyproject.toml'` ran one
pytest session: 7 scaffold cases passed in 78–85 s, with 2 skipped and 4,533
deselected. The skipped cases were the CLI measurement without
`PYKIT_MEASURE_OUT` and the Redis test without a Redis URL. The unchanged run
performed 10 wheel builds, 7 venv creations, and 7 installs. The 10 builds took
0.20 s total. The 7 venv creations and installs each took 0.09–0.37 s, 0.97 s
total. Case durations were 59.95 s for the Django conformance driver, 7.49 s for
FastAPI conformance, 2.55 s for FastAPI SSE, 1.50 s for tooling lifecycle, and
0.77, 0.74, and 0.58 s for the three CLI cases. These durations are served
application runtime, not setup.

The unchanged large-input SQL regression writes 33,000 rows, exceeding SQLite's
32,766 parameter limit, in 0.35 s. The new guards leave its input and chunk size
unchanged (900).

After adding the three guards, the targeted CLI scaffold run passed 6 cases in
3.40 s. It added 2 venv creations and 2 installs, about 0.8 s; the wheel-set
guard installs nothing. The full scaffold run therefore has 10 cases, 10 builds,
9 venv creations, and 9 installs; it passed 10 cases with 2 skipped.

Third-party requirements resolve through the package index using the warm uv
cache; workspace wheels are served locally. Build and install setup account for
about 1.2 s of about 80 s, and the wall times are noisy. No setup was reduced.

### 6e0572f before and after S22.8.3

Collected on 2026-11-16 at checkout `6e0572fb99e82033345229fc8f20e111ae115e6a`,
before and after the uncommitted S22.8.3 source changes. Environment: Mac mini
(Mac14,12), Apple M2 Pro, 10 CPU cores (6 performance and 4 efficiency), 16 GB
RAM; macOS 27.2.1 (26B131), arm64; Python 3.14.2; uv 0.13.8 from its Homebrew
installation symlink. Five sequential runs per phase used the same machine, with
no other agent-launched jobs during measurement. Machine idle status was not
verified. Raw records: `/tmp/S22.8.3-before/results.jsonl` and
`/tmp/S22.8.3-after/results.jsonl` (50 records each).

Wall times are medians of five runs; peaks are the maximum traced Python
allocation bytes. Each store starts empty and receives distinct live records
with a one-hour TTL. Counts are observations, not test thresholds.

| Workload | Records | Before wall (s) | After wall (s) | Before peak (bytes) | After peak (bytes) | Operations |
| -- | -- | -- | -- | -- | -- | -- |
| Replay | 1,000 | 0.021692666 | 0.002485500 | 131,530 | 92,582 | 1,000 |
| Replay | 4,000 | 0.286680333 | 0.009467375 | 533,314 | 377,406 | 4,000 |
| Replay | 16,000 | 4.587994875 | 0.038046667 | 2,144,914 | 1,524,358 | 16,000 |
| Transaction | 1,000 | 0.027857125 | 0.007170250 | 403,266 | 304,693 | 1,000 |
| Transaction | 4,000 | 0.342122208 | 0.037973042 | 1,622,402 | 1,467,197 | 4,000 |
| Transaction | 16,000 | 5.207494334 | 0.142185834 | 6,428,874 | 5,748,549 | 16,000 |
| Session | 1,000 | 0.032801917 | 0.007477584 | 430,620 | 391,820 | 1,000 |
| Session | 4,000 | 0.404766500 | 0.035189916 | 1,589,308 | 1,433,772 | 4,000 |
| Session | 16,000 | 6.104716000 | 0.155544375 | 6,797,244 | 6,238,828 | 16,000 |

Key refresh performs 100 verifications and one rotation. Single-call latencies
below are medians across five runs; cached latency is the median across runs of
each run's median of the other 98 verifications. Both phases made exactly two
JWKS requests in every run.

| Phase | Wall (s) | Peak (bytes) | First verify (s) | Refresh verify (s) | Cached verify median (s) | Requests |
| -- | -- | -- | -- | -- | -- | -- |
| Before | 0.101847458 | 302,546 | 0.010706542 | 0.005855458 | 0.000133480 | 2 |
| After | 0.092315791 | 300,106 | 0.010232708 | 0.005510708 | 0.000129167 | 2 |
