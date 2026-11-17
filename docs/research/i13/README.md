# Item 13: persisted names experiment

Result: stop after Phase 1. The repeated-name and saved Nix-dump corpora
benefit; the 10M-row distinct-name stress case exceeds both the one-shot
latency spread and the memory bar. See [D149](../../DECISIONS.md)
and the [report](report.md).

`measurements.json` contains every accepted sample, output count and sorted
output digest. Earlier samples using Python's inherited RSS high-water
mark were discarded. The C supervisor forks after exec, so its child's
peak reflects the product rather than the Python interpreter. All measured
query runs use warm files, stdout discarded, and one process per sample.

The three modes are:

- `raw`: the base release binary and its normal lazy catalog walk.
- `walk`: load the persisted dictionary, keys and postings, then walk.
- `postings`: the same bytes, with the existing resident find planner.
  Regex still walks because that planner accelerates only `-name`.

The loader copies actual packed fields into the same `ResidentNames`
struct used by the product. It reads and hashes a real file. Other catalog
sections remain lazy; raw NameHeap and NameOffset bytes are never read.
The prototype retains the old checkpoint on disk to supply its other
sections. It skips the old Names checksum and full semantic validation,
counting directory children for DirNames validation instead. The new file
has a BLAKE3 checksum and basic length checks. It is a trusted-fixture,
optimistic load experiment, not a proposed safe checkpoint decoder.

The size comparison accounts for actual encoded payload bytes: old file,
minus raw heap and offset bytes, plus the persisted names file. It is not
a measured final-format checkpoint. Header/table changes remain unbuilt.
The sidecar's actual measured length is also recorded, so this distinction
is visible. No product format or golden digest changed.

## Reproducing

Run from the worktree root, with at least 4 GiB free on `/tmp`. All target
directories stay inside this worktree. `prepare.py` makes a disposable copy
of tracked sources at `target/i13-prototype`; it refuses to overwrite one.
It patches that copy only. Do not time concurrent builds or benchmarks.

```sh
export TMPDIR=/tmp/i13
export XDG_STATE_HOME=/tmp/i13/xdg/state
export XDG_DATA_HOME=/tmp/i13/xdg/data
export XDG_CONFIG_HOME=/tmp/i13/xdg/config
export XDG_RUNTIME_DIR=/tmp/i13/xdg/run
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR" "$XDG_STATE_HOME" "$XDG_DATA_HOME"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
nix develop --command cargo build --release -p ferret -p ferret-bench
cc -O2 -Wall -Wextra -Werror docs/research/i13/measure.c \
  -o target/i13-measure
python3 docs/research/i13/copy-tree.py
FERRET_NO_DAEMON=1 target/release/ferret --index /tmp/i13/real-catalog \
  index /tmp/i13/tree
python3 docs/research/i13/prepare.py
nix run .#fmt -- --manifest-path "$PWD/target/i13-prototype/Cargo.toml"
export CARGO_TARGET_DIR="$PWD/target/i13-build"
nix develop --command cargo build \
  --manifest-path target/i13-prototype/Cargo.toml --release \
  -p ferret -p ferret-bench --examples --bins
unset CARGO_TARGET_DIR
```

`copy-tree.py` copies tracked regular files from each existing checkout,
excluding build artifacts and symlinks. This run copied 6,067 files from 12
checkouts, producing 7,486 catalog names. Source checkouts can drift; the
committed output digests identify the exact measured result sets.

Make `names.txt` from the sorted distinct basenames of that copied tree:

```sh
python3 - <<'PY'
from pathlib import Path
names = {p.name for p in Path('/tmp/i13/tree').rglob('*') if p.is_file()}
names.update(['Cargo.toml', 'checkpoint.rs', 'read.rs', 'names.rs'])
Path('/tmp/i13/names.txt').write_text('\n'.join(sorted(names)) + '\n')
Path('/tmp/i13/synthetic-tree').mkdir(exist_ok=True)
PY
```

There were 390 basenames. The two 26,000-directory catalogs each contain
10,166,000 rows. `unique` inserts a directory number before each filename's
extension, retaining `Cargo.toml` unchanged to keep a useful literal query.
It has 10,140,001 distinct names; the repeated case has 26,390. These are
sensitivity checks, not claims about the usual distribution of names.
They use constant synthetic stats and unindexed files.

```sh
python3 docs/research/i13/measure.py once \
  target/i13-build/release/examples/i13-synthetic \
  /tmp/i13/large-catalog /tmp/i13/names.txt 26000
python3 docs/research/i13/measure.py once \
  target/i13-build/release/examples/i13-synthetic \
  /tmp/i13/unique-catalog /tmp/i13/names.txt 26000 unique
python3 docs/research/i13/measure.py once \
  target/i13-build/release/examples/i13-dump \
  ~/w/name-index-bench/data/nix.tsv /tmp/i13/nix-catalog 3
```

`i13-dump` restores the D40 driver from the parent of `d7105331`, where it
was removed. It replaces its synthetic root with the isolated temp root,
avoids resetting `/proc/self/clear_refs`, and uses an eager fallback in its
RSS display. It never crawls the saved dump's source paths. Three copies
produce 12,625,560 names and 7,236,087 synthetic documents. This saved dump
has no stat columns, so the driver supplies constant default stats; its
build figures must not be mistaken for a full-stat production census.
The saved input and source filenames are not committed.

For each corpus `real`, `large`, `unique`, `nix`, run these serially:

```sh
export FERRET_NO_DAEMON=1
corpus=large
sample_count=7 # 15 for real
# Persist the actual packed fields; the default mode has no prototype env.
target/i13-build/release/examples/i13-section \
  "/tmp/i13/$corpus-catalog" "/tmp/i13/$corpus-names.bin"
target/release/ferret-bench sections "/tmp/i13/$corpus-catalog"
for mode in raw walk postings; do
  python3 docs/research/i13/measure.py query \
    "$corpus" "$sample_count" "$mode"
done
for mode in raw section; do
  python3 docs/research/i13/open.py "$corpus" "$mode"
done
python3 docs/research/i13/daemon.py "$corpus" raw
```

The scripts set all four XDG homes and TMPDIR for every product invocation.
Daemon measurement removes FERRET_NO_DAEMON and uses a fresh catalog copy
per sample. Connecting to its Unix socket requires access outside the
restricted sandbox. It measures only the unmodified daemon; the prototype
hook is in Catalog::open and does not cover the retained writer's open.
`open.py` reports raw and optimistic section-based catalog opens separately.
Warmup is sample 0 for opens and daemon starts; query warmups record the
output digest and are excluded from timing samples.

The prototype-only env variables FERRET_I13_SECTION and
FERRET_I13_POSTINGS exist solely in the disposable sources and the runner.
They add no product seam or ENV.md contract.
