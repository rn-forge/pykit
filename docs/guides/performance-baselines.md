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
| Auth | Authorization-context cache churn with an injected clock | 1,000 to 16,000 distinct accounts, plus a hot-set case; entries retained, lock hold | CPU |
| Auth | Fill empty in-memory replay, transaction and session stores with live records | 1,000, 4,000 and 16,000 records; 1 hour TTL; operation count | CPU |
| SQLAlchemy | SQLite upsert of initial and mixed rows | 33,000 initial rows and 33,000 mixed rows; SQL statement count | I/O |
| Django | Export and batch get/create/update/delete over the transfer mixins | 100 to 9,000 rows; SQL query count, response bytes | I/O |
| FastAPI | Transfer export, import and batch create driven through the ASGI app | 10,000 and 100,000 rows × 10 columns; response bytes, event-loop lag | I/O |
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

### S22.8.4 authorization-context churn baseline

Five sequential runs were collected on 2026-11-16 with production source
unchanged, including `context_cache.py` (also unchanged from the brief's
`01a8985`). The measurement tests were uncommitted. No concurrent jobs were
launched by this agent during measurement; machine idle status was not verified.

| Checkout commit | CPU and hardware | OS | Python | uv |
| -- | -- | -- | -- | -- |
| `d0a1a8085dd01d7db871d9a7413b4ad91269f0fd` | Mac mini (Mac14,12), Apple M2 Pro, 10 cores (6 performance, 4 efficiency), 16 GB RAM | macOS 27.2.1 (26B131), arm64 | 3.14.2 | 0.13.8 (Homebrew installation symlink) |

Raw records: `/tmp/S22.8.4-baseline-five/run-{1,2,3,4,5}/results.jsonl`, five
records per run. Earlier exploratory records under `/tmp/S22.8.4-baseline` are
excluded. Each step advances the injected clock by one second and resolves a
fresh account, with a fresh context on each provider call and a 60 s TTL. The
invalidated case also invalidates that account after resolving it. The hot case
additionally resolves one of 20 recurring accounts per step. A hit does not
refresh `stored_at`.

Wall times and counts below are medians across five runs; peak memory is the
maximum across runs. Memory is traced Python allocation bytes, not process RSS.
Lock holds run under `tracemalloc`, so their absolute durations are inflated and
comparable only within this harness. Only the cache's entry lock is timed, not
its version-counter lock. These figures are observations, not thresholds.

| Case | Accounts / steps | Wall (s) | Peak bytes (max) | Retained bytes (median) |
| -- | -: | -: | -: | -: |
| Plain | 1,000 | 0.008551709 | 437,212 | 436,878 |
| Plain | 4,000 | 0.030114625 | 1,732,990 | 1,598,550 |
| Plain | 16,000 | 0.137117000 | 6,846,758 | 6,787,846 |
| Invalidated | 16,000 | 0.140850084 | 7,261,894 | 7,202,870 |
| Hot (20 accounts) | 16,000 | 0.219739542 | 6,927,852 | 6,797,548 |

| Case | Accounts / steps | Entries q1 / q2 / q3 / q4 | Entries end | TTL-live end | Version accounts | Provider calls |
| -- | -: | -- | -: | -: | -: | -: |
| Plain | 1,000 | 250 / 500 / 750 / 1,000 | 1,000 | 60 | — | — |
| Plain | 4,000 | 1,000 / 2,000 / 3,000 / 4,000 | 4,000 | 60 | — | — |
| Plain | 16,000 | 4,000 / 8,000 / 12,000 / 16,000 | 16,000 | 60 | — | — |
| Invalidated | 16,000 | 4,000 / 8,000 / 12,000 / 16,000 | 16,000 | 60 | 16,000 | — |
| Hot (20 accounts) | 16,000 | 4,020 / 8,020 / 12,020 / 16,020 | 16,020 | 80 | — | 21,340 |

| Case | Accounts / steps | Lock acquisitions | Hold total (s, median) | Hold max (s, median) | Hold max (s, maximum) |
| -- | -: | -: | -: | -: | -: |
| Plain | 1,000 | 2,000 | 0.001504556 | 0.000009916 | 0.000020708 |
| Plain | 4,000 | 8,000 | 0.004812193 | 0.000014916 | 0.000023375 |
| Plain | 16,000 | 32,000 | 0.021412113 | 0.000050791 | 0.000076292 |
| Invalidated | 16,000 | 32,000 | 0.022043150 | 0.000044458 | 0.000055959 |
| Hot (20 accounts) | 16,000 | 53,340 | 0.034928622 | 0.000049667 | 0.000076541 |

Entries grow with distinct accounts ever requested, despite only 60 plain
entries remaining younger than the TTL. The hot case makes 16,000 cold calls and
5,340 hot calls: a hot account recurs every 20 s but still expires every 60 s.
Invalidation leaves 16,000 entries and 16,000 version counters; its TTL-live
count measures age only, not version validity. Its memory figures include both
entries and counters and do not isolate counter allocation.

### S22.8.1 authorization-context churn after the change

Five sequential runs were collected on 2026-11-16 at checkout
`25cbb473093df3d6f0ec4a4d5435d20424971689`, with the S22.8.1 changes
uncommitted. Environment: Mac mini (Mac14,12), Apple M2 Pro, 10 CPU cores (6
performance and 4 efficiency), 16 GB RAM; macOS 27.2.1 (26B131), arm64; Python
3.14.2; uv 0.13.8 (reported by the validation build). No other jobs were
launched by this agent during measurement; machine idle status was not verified.

Each run used
`unset VIRTUAL_ENV; PYKIT_MEASURE_OUT=/tmp/S22.8.1-after/run-$n PYTEST_ADDOPTS='tests/measure/test_context_churn.py' task test PACKAGE_DIRS=packages/rn-forge-auth`
for `n=1,2,3,4,5`. Each exited 0 with five passed cases and five records. Raw
records: `/tmp/S22.8.1-after/run-{1,2,3,4,5}/results.jsonl` (25 total).

The workload and harness are unchanged from S22.8.4: a 60 s TTL, one second per
fresh account, with invalidation or 20 recurring accounts where indicated.
Paired cells below show S22.8.4 baseline → S22.8.1 after; single values are
unchanged. Wall times and counts are medians of five runs; peak bytes and the
last lock column are maxima across runs. Memory is traced Python allocation, not
process RSS. Lock holds are inflated by `tracemalloc` and compare only within
this harness; only the entry lock is timed, not the version-counter lock. These
observations are not thresholds.

| Case | Accounts / steps | Wall (s) | Peak bytes (max) | Retained bytes (median) |
| -- | -: | -: | -: | -: |
| Plain | 1,000 | 0.008551709 → 0.008212417 | 437,212 → 33,877 | 436,878 → 25,152 |
| Plain | 4,000 | 0.030114625 → 0.033203375 | 1,732,990 → 33,937 | 1,598,550 → 25,212 |
| Plain | 16,000 | 0.137117000 → 0.127250125 | 6,846,758 → 28,277 | 6,787,846 → 25,272 |
| Invalidated | 16,000 | 0.140850084 → 0.137095542 | 7,261,894 → 1,185,100 | 7,202,870 → 1,178,366 |
| Hot (20 accounts) | 16,000 | 0.219739542 → 0.205115709 | 6,927,852 → 41,459 | 6,797,548 → 31,518 |

| Case | Accounts / steps | Entries q1 / q2 / q3 / q4 | Entries end | TTL-live end | Version accounts | Provider calls |
| -- | -: | -- | -: | -: | -: | -: |
| Plain | 1,000 | 250 / 500 / 750 / 1,000 → 60 / 60 / 60 / 60 | 1,000 → 60 | 60 | — | — |
| Plain | 4,000 | 1,000 / 2,000 / 3,000 / 4,000 → 60 / 60 / 60 / 60 | 4,000 → 60 | 60 | — | — |
| Plain | 16,000 | 4,000 / 8,000 / 12,000 / 16,000 → 60 / 60 / 60 / 60 | 16,000 → 60 | 60 | — | — |
| Invalidated | 16,000 | 4,000 / 8,000 / 12,000 / 16,000 → 60 / 60 / 60 / 60 | 16,000 → 60 | 60 | 16,000 | — |
| Hot (20 accounts) | 16,000 | 4,020 / 8,020 / 12,020 / 16,020 → 80 / 80 / 80 / 80 | 16,020 → 80 | 80 | — | 21,340 |

| Case | Accounts / steps | Lock acquisitions | Hold total (s, median) | Hold max (s, median) | Hold max (s, maximum) |
| -- | -: | -: | -: | -: | -: |
| Plain | 1,000 | 2,000 | 0.001504556 → 0.002909271 | 0.000009916 → 0.000016958 | 0.000020708 → 0.000023250 |
| Plain | 4,000 | 8,000 | 0.004812193 → 0.012166388 | 0.000014916 → 0.000027333 | 0.000023375 → 0.000043417 |
| Plain | 16,000 | 32,000 | 0.021412113 → 0.046389403 | 0.000050791 → 0.000041458 | 0.000076292 → 0.000077416 |
| Invalidated | 16,000 | 32,000 | 0.022043150 → 0.046045244 | 0.000044458 → 0.000043042 | 0.000055959 → 0.000648375 |
| Hot (20 accounts) | 16,000 | 53,340 | 0.034928622 → 0.066478913 | 0.000049667 → 0.000056542 | 0.000076541 → 0.000070542 |

Median lock hold totals are higher in every case: plain 1,000 by 0.001404715 s
(93.4%), plain 4,000 by 0.007354195 s (152.8%), plain 16,000 by 0.024977290 s
(116.7%), invalidated by 0.024002094 s (108.9%), and hot by 0.031550291 s
(90.3%). The sweep adds work under the existing lock. Median maximum holds are
higher for plain 1,000 by 0.000007042 s (71.0%), plain 4,000 by 0.000012417 s
(83.2%), and hot by 0.000006875 s (13.8%); they are lower for plain 16,000 by
0.000009333 s (18.4%) and invalidated by 0.000001416 s (3.2%). Acquisitions are
unchanged in all five cases.

After a miss, entries are bounded by the accounts resolved within one TTL: plain
churn retains 60 entries, all TTL-live; hot churn retains 80, all TTL-live. An
idle cache keeps its last entries until the next miss, and hits do not refresh
`stored_at`. A burst of N distinct accounts inside one TTL retains N entries;
there is no hard cap. Concurrent inserts can leave an expired entry behind a
live front entry until a later sweep reaches it.

Version counters are not pruned: invalidated churn still retains 16,000 counters
and 1,178,366 B (about 1.18 MB), despite only 60 entries. TTL-live counts
measure age, not version validity; retained memory includes both entries and
counters and does not isolate counter allocation.

Single-flight was not added: there is no measured need. Hot churn still makes
21,340 provider calls (16,000 cold and 5,340 hot), and the sweep adds neither
provider calls nor lock acquisitions. Concurrent misses for the same account
still each call the provider.

### 9bcf9b0 S22.10.3 FastAPI transfer baseline

Collected on 2026-11-16 at commit `9bcf9b0e6b4b6bb4a4c7ad2ec409e30a7f62d17a`,
with the measurement tests uncommitted and production source unchanged.
Environment: Mac mini (Mac14,12), Apple M2 Pro, 10 cores (6 performance and 4
efficiency), 16 GB RAM; macOS 27.2.1 (26B131), arm64; Python 3.14.2; uv 0.13.8.
No other jobs were launched by this agent during the three sequential runs.
Machine-wide idle status could not be verified: process inspection was denied by
the sandbox.

The harness runs under `tracemalloc`, which inflates the XLSX cases: S25.2.1
found 100,000-row XLSX export about 5× and import about 2.5× slower than
untraced (about 6.5 s and 8 s untraced, on 2026-11-18).

Exact first command; repeated with output directories `/tmp/S22.10.3-run-2` and
`/tmp/S22.10.3-run-3`:

```bash
unset VIRTUAL_ENV
PYKIT_MEASURE_OUT=/tmp/S22.10.3-run-1 \
PYTEST_ADDOPTS='tests/measure/test_contract.py tests/measure/test_transfer.py -p no:randomly' \
  task test PACKAGE_DIRS=packages/rn-forge-fastapi
```

Raw records: `/tmp/S22.10.3-run-{1,2,3}/results.jsonl` (11 each).

| Case | Format / rows / dry-run | Wall median / max (s) | Peak max (bytes) | Lag max median / max (s) | p99 median (s) | Heartbeats range | Response bytes range |
| -- | -- | -: | -: | -: | -: | -: | -: |
| `fastapi_export` | csv / 10,000 / — | 1.249249 / 1.255332 | 235,123 | 0.010022 / 0.011498 | 0.000131 | 246–248 | 687,837 |
| `fastapi_export` | csv / 100,000 / — | 12.141380 / 12.163089 | 264,607 | 0.009431 / 0.009930 | 0.000099 | 2,396–2,402 | 7,077,837 |
| `fastapi_export` | xlsx / 10,000 / — | 3.462552 / 3.491984 | 3,471,279 | 0.016410 / 0.016427 | 0.016373 | 187–190 | 378,148–378,149 |
| `fastapi_export` | xlsx / 100,000 / — | 30.915327 / 31.064210 | 29,350,992 | 0.021964 / 0.037788 | 0.016390 | 1,625–1,632 | 3,742,582–3,742,583 |
| `fastapi_import` | csv / 10,000 / false | 0.147006 / 0.147787 | 23,681,025 | 0.018863 / 0.020379 | 0.016368† | 8† | 62 |
| `fastapi_import` | csv / 100,000 / false | 1.466050 / 1.529704 | 229,128,617 | 0.131530 / 0.131557 | 0.047659† | 63–67† | 63 |
| `fastapi_import` | xlsx / 10,000 / false | 1.952598 / 1.963844 | 20,929,404 | 0.107315 / 0.123496 | 0.090906† | 42–56† | 62 |
| `fastapi_import` | xlsx / 100,000 / false | 19.168049 / 19.180899 | 204,092,667 | 0.300066 / 0.300617 | 0.136018 | 406–411 | 63 |
| `fastapi_import` | csv / 100,000 / true | 1.527289 / 1.535227 | 229,131,627 | 0.118767 / 0.120848 | 0.072601† | 65† | 62 |
| `fastapi_batch_create` | json / 10,000 / — | 0.263132 / 0.267298 | 35,500,680 | 0.151127 / 0.152035 | 0.121079† | 2† | 1,577,790 |
| `fastapi_batch_create` | json / 100,000 / — | 2.603145 / 2.612255 | 354,722,482 | 1.337377 / 1.338772 | 1.272576† | 2† | 15,977,790 |

All cases have `columns=10` and `kind="io"`; all 33 request statuses were 200.
Wall times and p99 are medians of three runs; peaks and the second maximum lag
figure are maxima across runs. Heartbeats and response sizes show observed
ranges. Tracing starts after building the app, source rows and request body; the
ASGI send callback counts and discards response chunks without buffering.

† Fewer than 100 heartbeats: p99 is not meaningful; use the maximum lag. The
heartbeat sleeps 5 ms on the app's own loop, settles for three intervals, and
records oversleep until completion. Worker-thread GIL contention remains
visible, including the roughly 16 ms p99 floor on XLSX export.

Request sizes (`inputs.request_bytes`, including multipart framing) were: CSV
import 687,973 / 7,077,973 bytes for 10,000 / 100,000 rows, with the same
7,077,973 for dry-run; XLSX import 378,582–378,586 / 3,742,998 bytes; batch
create 1,577,794 / 15,977,794 bytes. XLSX ZIP metadata can change file sizes
between runs. Input rows are deterministic: sequential ID and SKU, Widget,
Standard item, North, Ops, quantity 3, price 12.5, due 2026-01-02, active true.

### cd0b069 S22.10.2 FastAPI transfer after the change

Collected on 2026-11-16 on commit `cd0b06958c72c0b4dd20ed200e9d8085b297429d`
with the S22.10.2 change uncommitted. Environment: Mac mini (Mac14,12), Apple M2
Pro, 10 cores, 16 GB RAM; macOS 27.2.1, arm64; Python 3.14.2; uv 0.13.8. No
other jobs were launched by this agent during the three sequential runs.
Machine-wide idle status could not be verified.

Exact first command; repeated with output directories `/tmp/S22.10.2-run-2` and
`/tmp/S22.10.2-run-3`:

```bash
unset VIRTUAL_ENV
PYKIT_MEASURE_OUT=/tmp/S22.10.2-run-1 \
PYTEST_ADDOPTS='tests/measure/test_contract.py tests/measure/test_transfer.py -p no:randomly' \
  task test PACKAGE_DIRS=packages/rn-forge-fastapi
```

Raw records: `/tmp/S22.10.2-run-{1,2,3}/results.jsonl` (11 each). Each run was
`12 passed`; all 33 request statuses were 200. Response sizes are unchanged from
the S22.10.3 baseline: 7,077,837 bytes for CSV export and 15,977,790 for batch
create at 100,000 rows. Before and After are medians of three runs; Peak after
is the maximum. Bounds are the metrics judged: wall for CSV export, peak for CSV
export, CSV import and dry-run and batch create, and lag for batch create; every
other case is judged at 1.25 x its baseline median wall and lag (lag never below
0.016 s).

| Case | Format / rows / dry-run | Bound | Before | After | Peak after (bytes) | Met |
| -- | -- | -- | -: | -: | -: | -- |
| `fastapi_export` | csv / 10,000 / — | wall at most 0.30 s; peak at most 1,048,576 | wall 1.249249 s; peak 235,123 | wall 0.088818 s | 646,969 | yes |
| `fastapi_export` | csv / 100,000 / — | wall at most 3.0 s; peak at most 1,048,576 | wall 12.141380 s; peak 264,607 | wall 0.793433 s | 626,730 | yes |
| `fastapi_export` | xlsx / 10,000 / — | no bound set; wall at most 4.328 s, lag at most 0.0205 s | wall 3.462552 s; lag 0.016410 s | wall 3.442899 s; lag 0.016441 s | 3,470,227 | yes |
| `fastapi_export` | xlsx / 100,000 / — | no bound set; wall at most 38.644 s, lag at most 0.0275 s | wall 30.915327 s; lag 0.021964 s | wall 31.331633 s; lag 0.020656 s | 29,352,061 | yes |
| `fastapi_import` | csv / 10,000 / false | peak at most 26,214,400; wall at most 0.184 s, lag at most 0.0236 s | wall 0.147006 s; lag 0.018863 s; peak 23,681,025 | wall 0.140319 s; lag 0.022520 s | 23,669,863 | yes |
| `fastapi_import` | csv / 100,000 / false | peak at most 241,172,480; wall at most 1.833 s, lag at most 0.1644 s | wall 1.466050 s; lag 0.131530 s; peak 229,128,617 | wall 1.480388 s; lag 0.140263 s | 229,128,185 | yes |
| `fastapi_import` | xlsx / 10,000 / false | no bound set; wall at most 2.441 s, lag at most 0.1341 s | wall 1.952598 s; lag 0.107315 s | wall 1.894994 s; lag 0.123968 s | 20,928,497 | yes |
| `fastapi_import` | xlsx / 100,000 / false | no bound set; wall at most 23.960 s, lag at most 0.3751 s | wall 19.168049 s; lag 0.300066 s | wall 18.165460 s; lag 0.291586 s | 204,089,659 | yes |
| `fastapi_import` | csv / 100,000 / true | peak at most 241,172,480; wall at most 1.909 s, lag at most 0.1485 s | wall 1.527289 s; lag 0.118767 s; peak 229,131,627 | wall 1.439095 s; lag 0.109699 s | 229,131,220 | yes |
| `fastapi_batch_create` | json / 10,000 / — | peak at most 37,748,736; lag at most 0.075 s | lag 0.151127 s; peak 35,500,680 | lag 0.044876 s; wall 0.095824 s | 22,492,295 | yes |
| `fastapi_batch_create` | json / 100,000 / — | peak at most 367,001,600; lag at most 0.750 s | lag 1.337377 s; peak 354,722,482 | lag 0.504502 s; wall 0.972012 s | 224,796,916 | yes |

Every case met its bound. The batch create lag of 0.5045 s at 100,000 rows is
the thread parse of the 15,977,794-byte body. The CSV import lag at 10,000 rows
(0.0225 s against 0.0236 s) is the closest to a bound among the cases judged at
1.25 x baseline.

### b1949212 S25.2.2 faster XLSX path

Collected on 2026-11-18 at commit `b1949212`, with the S25.2.2 change
uncommitted. Environment: Mac mini (Mac14,12), Apple M2 Pro, 10 cores, 16 GB
RAM; macOS 27.2.1, arm64; Python 3.14.2. Other processes were running (an editor
and a macOS background scan were among the top CPU users), and machine-wide idle
status could not be verified.

Method, untraced: one temporary `task test` runner built 100,000 rows × 10
columns of the S22.10.3 row shape, then in one process ran, back to back and
three times each, the unchanged `write_xlsx` (copied from `b1949212`) and the
new one, each followed by `tablib.Dataset().load(bytes, format="xlsx")` of its
output. The runner was deleted afterwards. Harness cases ran as in the procedure
above, with `PYKIT_MEASURE_OUT` set, once before and once after the change,
under `tracemalloc`.

| Operation (100,000 × 10, untraced) | Before median (range) s | After median (range) s | Output bytes |
| -- | -: | -: | -: |
| `write_xlsx` | 6.019 (6.013–6.030) | 4.398 (4.379–4.423) | 3,742,582 / 3,742,603 |
| `tablib` xlsx load | 7.055 (7.034–7.075) | 4.752 (4.746–4.814) | — |

| Harness case | Wall before / after (s) | Peak before / after (bytes) |
| -- | -: | -: |
| `excel_write` (50,000 rows) | 15.258 / 11.493 | 2,134,607 / 2,133,747 |
| `excel_roundtrip` (50,000 rows) | 23.119 / 18.803 | 225,329,169 / 225,329,638 |
| `fastapi_export` xlsx 10,000 | 3.211 / 2.933 | 3,504,436 / 3,522,166 |
| `fastapi_export` xlsx 100,000 | 31.534 / 25.253 | 29,354,558 / 29,370,898 |
| `fastapi_import` xlsx 10,000 | 1.831 / 1.783 | 20,995,131 / 20,996,764 |
| `fastapi_import` xlsx 100,000 | 18.532 / 18.407 | 204,120,189 / 204,120,455 |

Harness wall times are single runs under `tracemalloc` and are inflated. Peak
allocation did not fall in four cases; the largest rise is 17,730 bytes (0.5%)
on the 10,000-row export. The `fastapi_import` cases build their upload with
tablib's own XLSX export, not `write_xlsx`, so they carry no `<dimension>` and
show no import gain; only files `write_xlsx` writes load faster.
