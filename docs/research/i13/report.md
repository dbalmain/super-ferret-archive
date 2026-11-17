# Item 13: stop after Phase 1

Branch i13, base 7288639f. Started 2026-11-15 04:04 UTC.
Plan and verified baseline committed as c56dac2c at 04:11 UTC, within the
first 20 minutes. No product change was made before or after measurement.

## Decision

The mandatory stop rule fired on the mostly distinct-name sensitivity
check. At 10,166,000 rows, literal one-shot find rises from 213.165 ms
(205.461-221.372) to 403.232 ms (398.004-409.244) with persisted names and
the existing postings planner. The increase is 190.067 ms against that
query's own 15.911 ms spread. Its peak RSS rises from 223,948 to 388,144
KiB, 73%. Glob and absent-name queries also regress beyond their spreads.

Even preserving the walk rather than using postings does not pass: that
literal takes 281.529 ms (269.135-286.961), 350,608 KiB. The loader omits
full semantic validation, so these are optimistic prototype costs.

The repeated-name and saved Nix-dump cases improve. The result is sensitive
to basename cardinality, not a blanket claim that persisted names are slow.
Recommendation: retain today's format, measure a cardinality-aware codec
before choosing another. Question, named options, quantified tradeoffs,
recommendation and the fact that would change it are in DECISIONS D149.
Phase 2 was not started; its build-memory and final-format retest are not
claimed. The 500-900-line product estimate was not tested by implementation;
codec redesign would be a different scope from persisting today's fields.

## Method and isolation

Release profile: opt-level 3, codegen-units 1, thin LTO, existing manifests.
Rust 1.95.0 (59807616e 2026-04-14), Ryzen 9 9955HX, 32 logical CPUs,
frequency boost disabled. Warm page cache; no eviction/cold-boot claim.
One benchmark at a time, after builds and baseline gates finished.
Host pgrep checks found no other cargo, ferret-bench or hyperfine process.
The realistic fixture's setup/indexing overlapped our own prototype build;
it is not a timed query sample. No other compilation overlapped accepted
query/open/daemon samples.

Every product invocation used TMPDIR=/tmp/i13 and XDG_STATE_HOME,
XDG_DATA_HOME, XDG_CONFIG_HOME, XDG_RUNTIME_DIR under /tmp/i13/xdg.
One-shot queries set FERRET_NO_DAEMON=1. Daemon samples use fresh copies and
unset it, with 1 ms greeting polling. No live home-directory indexing.
All targets stayed inside the worktree. /tmp free space went from about
103 to 97 GiB; it never approached the 4 GiB stop threshold. Nothing pushed.
Cargo.toml, Cargo.lock and crates/ferret/src/search.rs were untouched.

The initial Python wait4 supervisor inherited Python's peak RSS as a floor
for small children. Those query samples were discarded and repeated with
the committed C supervisor, which forks after exec and records each child.
Accepted query samples: one untimed warmup/output check, then 15 runs on
real, seven on every large corpus. Opens/daemon: warmup plus seven runs.
The large fixture's single build setup measurement predates that correction;
its 1.5 GiB peak is far above the inherited floor. Build setup figures are
single samples, not a repeat/spread claim.

Sorted output counts and SHA-256 digests match across raw, dictionary walk
and dictionary postings for all 16 corpus/query pairs. Rows per query:

| corpus | literal | glob | regex | absent |
|---|---:|---:|---:|---:|
| real | 120 | 18 | 60 | 0 |
| large | 26000 | 26000 | 52000 | 0 |
| unique | 26000 | 26000 | 52000 | 0 |
| nix | 20187 | 0 | 1707 | 0 |

## Corpora and actual file prototype

- real: tracked regular files copied from 12 checkouts of this repository,
  excluding targets and symlinks: 6,067 files, 7,486 names, 496 distinct.
- large: 26,000 directories, each holding the same 390 source basenames:
  10,166,000 names, 26,390 distinct. Favorable repeated-name distribution.
- unique: the same shape and metadata, with a directory number inserted
  before each filename extension except Cargo.toml: 10,166,000 names,
  10,140,001 distinct. A sensitivity check, not asserted typical usage.
- nix: three copies of the saved D54 Nix-store walker dump through the
  recovered D40 generator: 12,625,560 names, 356,921 distinct, 7,236,087
  synthetic documents. This is the largest measured corpus. No live
  Nix-store traversal. The dump has no stat columns; the driver supplies
  constant default stats, so its build cost is not a full-stat census.

The synthetic example is absent at this base: D144 removed it in d7105331.
prepare.py restores its last version from that commit's parent and puts
its synthetic root under /tmp/i13. No agent CLI was launched. D54 reference
results were read: historical BFS dictionary/postings builds were
114.244/27.430 ms at 459,713 rows and 1,408.187/190.915 ms at 4,206,047 rows.
Those are reference numbers from name-index-bench, not measured here.

The disposable target/i13-prototype sources persist the actual intpack
string offsets, row keys, counts, posting offsets and PFor bytes. The
reader streams a real file into the same owned ResidentNames fields,
checks BLAKE3 and basic lengths, and bypasses raw heap/offset reads. Other
sections retain their lazy production reader. It omits the old Names
checksum and full semantic validation, counting directory children for
DirNames instead. It is deliberately an optimistic trusted-fixture load,
not a shippable corruption-safe decoder. Both pure walking and the existing
resident find planner were measured; regex remains a walk in that planner.

The old checkpoint remains on disk for unrelated sections. The size table
therefore reports actual persisted-name bytes and exact replacement payload
accounting, not an implemented final-format checkpoint. Header/table changes
are unbuilt. This experiment never changes the main worktree's Rust files.
The committed preparation scripts and Rust source templates reproduce it.

## One-shot find results

Times are milliseconds: median (min-max). RSS is the maximum across
the measured repeats, in KiB. `section` below means the persisted
dictionary plus the existing postings planner. Full samples and sorted
output digests are in `docs/research/i13/measurements.json`.

### real

| query | raw ms | section ms |
|---|---:|---:|
| literal | 2.362 (2.182-2.705) | 1.433 (1.362-1.948) |
| glob | 2.344 (2.107-2.680) | 1.326 (1.287-1.585) |
| regex | 3.856 (3.382-4.416) | 3.741 (3.263-4.050) |
| absent | 2.169 (2.029-2.287) | 1.322 (1.243-1.480) |

| query | raw KiB | walk KiB | section KiB |
|---|---:|---:|---:|
| literal | 5928 | 5968 | 6312 |
| glob | 5752 | 5848 | 6012 |
| regex | 7028 | 6944 | 6796 |
| absent | 5900 | 6004 | 5760 |

Dictionary walk alone, without the postings planner:

| query | walk ms |
|---|---:|
| literal | 2.303 (2.019-3.412) |
| glob | 2.397 (2.266-2.651) |
| regex | 3.802 (3.421-4.122) |
| absent | 2.129 (1.952-2.285) |

### large

| query | raw ms | section ms |
|---|---:|---:|
| literal | 165.252 (162.330-171.853) | 107.216 (103.319-109.186) |
| glob | 207.465 (203.808-210.935) | 107.189 (104.158-111.442) |
| regex | 657.929 (640.217-714.718) | 631.234 (571.303-683.229) |
| absent | 168.971 (164.060-171.637) | 90.095 (89.336-92.130) |

| query | raw KiB | walk KiB | section KiB |
|---|---:|---:|---:|
| literal | 153784 | 53456 | 52268 |
| glob | 153964 | 53072 | 52268 |
| regex | 154832 | 54404 | 54000 |
| absent | 153236 | 52224 | 47680 |

Dictionary walk alone, without the postings planner:

| query | walk ms |
|---|---:|
| literal | 101.906 (101.083-106.513) |
| glob | 140.437 (139.611-141.543) |
| regex | 602.903 (577.527-610.792) |
| absent | 101.845 (100.968-104.921) |

### unique

| query | raw ms | section ms |
|---|---:|---:|
| literal | 213.165 (205.461-221.372) | 403.232 (398.004-409.244) |
| glob | 275.249 (273.696-282.489) | 717.016 (707.552-725.839) |
| regex | 688.059 (665.265-779.591) | 840.223 (787.285-871.801) |
| absent | 209.597 (202.146-214.313) | 373.877 (370.016-377.144) |

| query | raw KiB | walk KiB | section KiB |
|---|---:|---:|---:|
| literal | 223948 | 350608 | 388144 |
| glob | 223848 | 350568 | 387836 |
| regex | 225300 | 351540 | 351864 |
| absent | 222804 | 349520 | 384076 |

Dictionary walk alone, without the postings planner:

| query | walk ms |
|---|---:|
| literal | 281.529 (269.135-286.961) |
| glob | 335.914 (332.704-341.335) |
| regex | 788.918 (769.488-851.866) |
| absent | 287.373 (280.334-292.921) |

### nix

| query | raw ms | section ms |
|---|---:|---:|
| literal | 572.609 (559.204-592.717) | 436.271 (430.249-448.548) |
| glob | 640.183 (615.307-646.217) | 437.414 (434.878-452.112) |
| regex | 1319.560 (1272.748-1349.371) | 1275.025 (1261.737-1308.107) |
| absent | 771.504 (726.155-820.808) | 413.319 (407.261-417.007) |

| query | raw KiB | walk KiB | section KiB |
|---|---:|---:|---:|
| literal | 308276 | 160800 | 162104 |
| glob | 307728 | 159360 | 158596 |
| regex | 347136 | 196672 | 197440 |
| absent | 307740 | 160236 | 158824 |

Dictionary walk alone, without the postings planner:

| query | walk ms |
|---|---:|
| literal | 683.514 (640.190-705.002) |
| glob | 755.803 (685.434-784.651) |
| regex | 1267.083 (1246.609-1379.282) |
| absent | 498.785 (459.176-502.309) |

## Resident open and daemon readiness

One warmup then seven runs. Load includes open and load_all;
projection measures into_resident after load_all. Its parallel
name build and checked-source conversion are the production code.
These isolated phases do not model their overlap in a real daemon.
Daemon readiness is separately measured from spawn to a greeting
whose state is ready, polling every 1 ms. Each run uses a fresh
catalog copy, preventing its watch from changing later samples.

### real

| phase | ms |
|---|---:|
| raw load | 0.446 (0.411-0.477) |
| into_resident | 0.643 (0.610-0.729) |
| raw full open | 1.089 (1.028-1.182) |
| section full open | 0.350 (0.332-0.372) |
| daemon ready, raw | 8.045 (7.121-9.174) |

Full-open peak RSS: raw 3,408 KiB;
section 3,072 KiB.

### large

| phase | ms |
|---|---:|
| raw load | 116.386 (113.321-118.704) |
| into_resident | 197.515 (193.145-202.926) |
| raw full open | 315.446 (306.467-319.756) |
| section full open | 58.198 (57.039-59.655) |
| daemon ready, raw | 854.800 (839.699-858.221) |

Full-open peak RSS: raw 304,284 KiB;
section 67,600 KiB.

### unique

| phase | ms |
|---|---:|
| raw load | 150.823 (148.822-155.981) |
| into_resident | 1436.817 (1419.891-1489.875) |
| raw full open | 1589.091 (1570.714-1640.364) |
| section full open | 213.701 (211.854-219.239) |
| daemon ready, raw | 2587.693 (2560.207-2625.841) |

Full-open peak RSS: raw 1,226,400 KiB;
section 364,224 KiB.

### nix

| phase | ms |
|---|---:|
| raw load | 253.614 (251.241-258.313) |
| into_resident | 308.740 (305.828-320.507) |
| raw full open | 562.354 (557.326-574.643) |
| section full open | 208.320 (204.565-212.383) |
| daemon ready, raw | 3631.532 (3608.557-3671.631) |

Full-open peak RSS: raw 716,548 KiB;
section 349,456 KiB.

## Checkpoint payload accounting

Bytes, from actual file metadata and the checkpoint's encoded descriptors.
Replacement = old file - raw heap - raw offsets + persisted names file.
Final-format header/table overhead is not included or claimed measured.

| corpus | old file | persisted names | replacement payload |
|---|---:|---:|---:|
| real | 240311 | 27581 | 178314 |
| large | 169271809 | 31175337 | 66430136 |
| unique | 241343809 | 335576834 | 370838145 |
| nix | 477324238 | 68284977 | 326371795 |

| corpus | removed heap | removed offsets |
|---|---:|---:|
| real | 78340 | 11238 |
| large | 118768000 | 15249010 |
| unique | 189566000 | 16516498 |
| nix | 199855689 | 19381731 |

Baseline build/setup, single samples through today's transaction/builder:

| corpus | build wall ms | peak RSS KiB |
|---|---:|---:|
| large | 4424.316 | 1508872 |
| unique | 6676.718 | 1577420 |
| nix | 15996.231 | 2673840 |

The recovered driver builds documents; the two name-sensitivity generators
use unindexed files and constant stats. Their build peaks must not be
compared as identical workloads. No new-format build was attempted because
the reader already fails Phase 1's stop condition.

## Commands and retained artifacts

Full commands and executable source templates: docs/research/i13/README.md.
Accepted raw samples: docs/research/i13/measurements.json. Query commands
include exact operands and patterns. The literal is -name Cargo.toml, glob
-name '*checkpoint*.rs', regex -regex '.*/read[^/]*[.]rs', absent
-name i13-no-such-basename-8f0329. All discard stdout when timing.

Release builds:

```sh
nix develop --command cargo build --release -p ferret -p ferret-bench
python3 docs/research/i13/prepare.py
export CARGO_TARGET_DIR="$PWD/target/i13-build"
nix develop --command cargo build \
  --manifest-path target/i13-prototype/Cargo.toml --release \
  -p ferret -p ferret-bench --examples --bins
unset CARGO_TARGET_DIR
```

Runner commands, after the README's isolated env/corpus/section setup:

```sh
corpus=unique # also real, large, nix
for mode in raw walk postings; do
  python3 docs/research/i13/measure.py query "$corpus" 7 "$mode"
done
for mode in raw section; do
  python3 docs/research/i13/open.py "$corpus" "$mode"
done
python3 docs/research/i13/daemon.py "$corpus" raw
```

real uses 15 query samples, all others seven. The benchmark-only env vars
are confined to the disposable copy; no product ENV.md contract was added.
The first sandbox format invocation failed on Nix daemon socket access;
this was reported, then rerun through approved escalation. No cargo fmt
fallback. Daemon timing also needed escalation for Unix socket connections;
its initial sandbox attempt failed and supplied no accepted sample.

## Corrections, product scope and validation

- Item 13's raw/resident diagnosis is correct. Engine's call site has moved
  to engine.rs around line 190; symbols, not old line numbers, were used.
- Item 14 was already built at 7288639f. checkpoint.rs is the shared Source
  encoder; build/write.rs and compact.rs are adapters. Its existing Done
  paragraph already records this. The initial plan called its opening
  diagnosis stale before reading that paragraph; that was an incomplete
  reading, not a newly discovered product/spec error. Item 14 is unchanged.
- IMPROVEMENTS' How to work baseline referred to another commit. Updated to
  this verified 7288639f baseline: 2,182 passed, 0 failed, 11 ignored.
- Deleted product code: none. New tests: none; correctness checked with
  existing gates and identical real product query outputs. No test dropped.
- No format bump, migration diagnostic or golden-digest update: Phase 2
  was intentionally not started. All accessors and search paths remain.
- .gitignore has one explicit done-note exception, avoiding git add -f for
  any ignored .ai file. Other .ai artifacts remain ignored.

Baseline gates: fmt, clippy -D warnings, workspace tests and private docs
passed. First baseline test attempt hit Timeout in unchanged integration
case
a_query_paused_on_its_first_row_survives_append_and_dense_checkpoint_remapping;
a full retry passed with 2,182 passed / 0 failed / 11 ignored.
Logs are /tmp/i13/baseline-{fmt,clippy,doc}.log and baseline-test{-retry}.log.

Final four gates passed, zero compiler/Clippy/rustdoc warnings. Tests:
2,182 passed / 0 failed / 11 ignored, unchanged from baseline. An expected
runtime diagnostic from an invalid-settings fixture appears in the test
log; it is not a compiler warning. Final logs: /tmp/i13/final-*.log.
Nix's dirty-tree notice appeared in the baseline doc log; the final gates
set NIX_CONFIG='warn-dirty = false' without suppressing any code warnings.
The benchmark source templates also passed the pinned formatter inside
the disposable copy. Extended gate passed all 10 checks:
EXTENDED count=10 failed=0 tests_wall=103.455 s total_wall=288.431 s.
Its log is /tmp/i13/extended.log. All four exact gate commands and the
extended command were run through nix with the isolated environment.

Requested Rust shortstats against base (product and tests separately):

```sh
git diff --shortstat 7288639f..HEAD -- '*.rs' \
  ':(exclude)**/tests/**' ':(exclude)**/tests.rs' \
  ':(exclude)**/test.rs'
git diff --shortstat 7288639f..HEAD -- '**/tests/*.rs' \
  '**/tests/**/*.rs' '**/tests.rs' '**/test.rs'
git diff --shortstat 7288639f..HEAD -- '*.rs'
```

All print no output: **0 Rust files changed**, product 0 and tests 0.
Rust templates live under docs as .rs.txt, not in the product or test tree.
