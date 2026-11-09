# mojo-edlib — ANALYZE-phase hotspot map

Measured, not estimated: every number below comes from a run in this session
(best-of-N `perf_counter()` loops, 3–10 reps, first-run warm-up included in the
rep count used by `bench/bench.py`). No algorithms were touched; this file is
the only addition.

## Method and fixtures

- First step was `pixi run bench` (flock-wrapped, run alone). Output:

  ```text
  | NW distance (1000 x 1000) | 0.1 ms | 0.1 ms | 0.68x | slower |
  | NW distance (2000 x 2000) | 0.4 ms | 0.3 ms | 0.66x | slower |
  | NW path (800 x 800) | 2.9 ms | 0.2 ms | 0.07x | slower |
  ```

- Sequences are generated exactly as in `bench/bench.py` (seeded `ACGT`
  patterns, query and target of equal length). Sizes below are square unless
  noted. Machine: Intel Xeon E5-2697 v4, 72 threads visible; every timed call
  here is single-threaded, matching what real callers issue.
- Baselines: upstream `edlib` (importable from the pixi env) and a plain
  row-wise NumPy DP (`numpy`, 1 000 Python row iterations each allocating
  ~6 temporaries of 1 KB).
- Sizes follow the additional probe in README: 100 / 800 / 1 000 / 2 000, plus
  the HW blow-up at 100 / 200 / 400.

## Ranked hotspot table

Rank is by measured wall time at the largest realistic size. "SLOWER" marks
rows where the port loses to upstream `edlib` on the same input (kept, per
instructions, not dropped). Flops/bytes are derived from the measured
footprint (matrix size, workspace words, op counts in `src/capi.mojo`).

| # | function (entry) | input size | time (measured) | bytes touched | flops | flops/byte | bound | glue vs kernel | vs upstream | next phase |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `_hw_starts` (via `align(mode="HW", task="locations"/"path")`) — `python/mojo_edlib/__init__.py:131` | 1000×1000 (cells = 1 002 001) | **1 945 ms** (single call; 1 238 ms @ 800, 19 ms @ 100, 17 ms isolated @ 100², 289 ms @ 400²) | matrix read 2 MB + `starts` int64 write 8 MB | ~5×10⁷ nominal | ~5 | glue-bound | **100% Python** | SLOWER — upstream HW path 0.37 ms vs 1 948 ms (**~5 300×**) | **none** |
| 2 | `fill_matrix16` kernel (`med_matrix16`, `src/capi.mojo:179`) | 1000×1000 (1 002 001 cells, uint16) | **3.02 ms** (1.99 ms @ 800, 12.0 ms @ 2000) | matrix write 2 MB + ~3 row re-reads ≈ 6–8 MB touch | ~1×10⁷ (≈10/cell) | ~1.3 | dependency-bound | kernel | SLOWER — inside NW path 3.88 ms vs upstream 0.19 ms | **none** |
| 3 | `_native_trace` + CIGAR build (`__init__.py:202`) | path ~2 000 ops @ 1000 | **0.57 ms** (0.46 ms @ 800) | strided matrix reads ~4 KB + ops buffer ~2 KB | ~2×10⁴ | ~3 | latency-bound | mixed (kernel + Python `groupby`/f-string CIGAR) | SLOWER (upstream path totals 0.19 ms) | **none** |
| 4 | Myers `distance_myers` kernel (`med_distance`, `capi.mojo:64`) | 1000×1000 (16 blocks × 1000 target rows) | **0.073 ms** (0.055 ms @ 800, 0.29 ms @ 2000) | q+t 16 KB + workspace (85+2)×16×8 B ≈ 11 KB touched per column ≈ 0.3 MB | ≈3.2×10⁵ (≈20 u64 ops × 16 000 block-steps) | ≈1 | compute-bound (carry chain) | kernel | SLOWER — total NW distance 0.13 ms vs upstream 0.07 ms (kernel alone 0.073 ms ≈ parity) | **none** |
| 5 | `align` Python glue: `_encode_inputs` + allocations + ctypes (`__init__.py:85`, `_lib.py`) | 1000×1000, and 10×10 | **~25 µs encode + ~8–17 µs ctypes** per call (0.40 ms total for list inputs @ 1000) | q+t int64 copies 16 KB; workspace/matrix alloc per call | negligible | <0.1 | glue-bound | Python/ctypes | SLOWER — small-input floor ~20–25 µs vs upstream ~4 µs | **none** |
| 6 | `getNiceAlignment` (`__init__.py:299`) | CIGAR ~2 000 symbols @ 1000 | **0.65 ms** | input strings only | ~10⁴ | n/a | glue-bound | Python per-symbol loop | **NOT slower** — upstream 0.73 ms | **none** |
| 7 | NumPy row-DP baseline (not shipped; comparison only) | 1000×1000 | **16.1 ms** (43.4 ms @ 2000) | 1 000 rows × 6 temporaries × 1 KB | ~5×10⁶ | ~0.3 | overhead-bound | Python loop over vector ops | 220× slower than Myers kernel, 5× slower than matrix kernel | n/a |

## Where the time actually sits

**Row 1 is the whole story for HW.** `_hw_starts` is a double Python loop
over every matrix cell. Measured isolated scaling confirms quadratic growth
(17 ms → 72 ms → 289 ms at 100/200/400, consistent with ~1.9 s at 1000).
Per cell it performs 3 `int()` conversions, calls `_equal` (which reshapes
the `pairs` array **per cell**, `__init__.py:125`), appends to a candidate
list, and takes `min()`. That alone makes HW `path`/`locations` ~5 300×
slower than upstream, and it dwarfs every other hotspot combined: at
1 000×1 000 the matrix kernel is 3.0 ms while `_hw_starts` is 1 945 ms
(99.8% of the HW total). It also runs for `locations`, not just `path`, so
the slowdown is not confined to traceback.

**Rows 2–4 are the NW story.** NW `path` (3.88 ms @ 1000) decomposes as
matrix fill 3.02 ms + native trace/CIGAR 0.57 ms + ~40 µs glue. The full
DP matrix is algorithmically required for canonical locations/path, but the
fill kernel is dependency-bound: each cell takes `min(diag+cost, up+1,
left+1)` with a carried left-edge value, so measured throughput is
~0.33 Gflop/s / ~2.6 GB/s equivalent — far below what streaming 2 MB would
achieve, i.e. latency-chain-bound, not DRAM-bound. Upstream's bit-vector
traceback is why it wins paths by ~20×; per README this is a known,
deliberate trade for canonical results.

**Row 4 is close to parity and is not the problem.** The Myers kernel alone
(0.073 ms @ 1000) is within noise of upstream's total-call time (0.072 ms).
The NW-distance gap (0.13 vs 0.07 ms) lives in the glue row, not the
kernel: ~25 µs of `_encode_inputs` (see below) plus a ~8–17 µs ctypes call
plus a fresh workspace allocation per call. At 10×10 the whole `align`
call floors at ~20 µs where upstream answers in ~4 µs.

**Row 5 — glue details, all per-call:**

- `_encode_inputs` for ASCII calls `sorted(set(query_bytes).union(...))`
  then does two `np.frombuffer(...).astype(np.int64)` full copies (16 KB
  at n=1000, ~25 µs). This runs on every call, including `bytes` inputs
  that are already in the right form.
- Workspace `np.empty((mask_count+2) * blocks, dtype=np.uint64)` and matrix
  `np.empty((n+1, n+1))` are allocated per call (matrix alloc itself is
  cheap, ~1 µs, but it is a fresh 2 MB page-in for path/locations).
- One ctypes call per `align` (plus one more for `_native_trace`); each is
  ~8–17 µs measured end-to-end for a 1×1 call, i.e. ~15% of the NW-distance
  total at n=1000 and ~100% at small n.
- `mask_count` is `max_byte + 1` = **85** for `ACGT`, not the alphabet size 4,
  so the Myers workspace is (85+2)×16×8 B ≈ 11 KB instead of ~0.8 KB. It
  costs ~11 KB more traffic per call — small, but it inflates every
  `clear_words` and every mask lookup by 21×.

**Row 6 is fine.** `getNiceAlignment` re-enters Python per symbol
(`for _ in range(count)` appends, `__init__.py:318`) yet measures 0.65 ms
vs upstream 0.73 ms at n=1000 — not a hotspot, not slower. It is the only
public entry point that beats upstream.

**Other measured ratios (same sequences):** list inputs @1000 — port 0.40 ms
vs upstream 0.21 ms (the `_values` + dict-encode path, `__init__.py:36`,
is O(n) Python); `bytes` inputs @1000 — port 0.11 ms vs 0.08 ms;
`k=5` — upstream drops to 0.014 ms (band pruning) while the port stays at
0.11 ms, because `k` is an output threshold here, not a pruning hint
(README § API, already documented).

## Verdicts for the next phases

No hotspot clears the bar for its suggested phase, and every verdict is
backed by the flops-per-byte column:

- **GPU — no, everywhere.** All kernels sit at ~1–1.3 flops/byte (Myers ≈1,
  matrix ≈1.3, HW-starts ≈5 nominal but in Python). The MOJO_NOTES rule of
  thumb (< ~2 flops/byte ⇒ CPU wins once launch + transfer cost is counted)
  applies to all of them; the Myers kernel additionally has a serial carry
  between words and the matrix fill has a serial carry between cells, so
  there is no data-parallel wavefront to move to a GPU without changing the
  algorithm. No GPU phase should act on this port.
- **Parallel — no.** The only parallelisable structure is the matrix fill's
  anti-diagonal frontier, which would restructure the DP (i.e. change the
  algorithm, explicitly out of scope for the accel phases) and whose
  callers pass 800–2000 length inputs already completing in 2–3 ms
  single-threaded. Myers state updates carry between words
  (`capi.mojo:97–133`), so there is nothing independent to fan out. A
  `parallelize` on the clear-words / mask-build prologue would save
  microseconds of a 70 µs kernel.
- **SIMD — no further gains available in the hot kernels.** The remaining
  vectorisable spots (`clear_words`, matrix first-row fill) already use
  `load[width=W]`/`unsafe_store` (`capi.mojo:46`, `:151`, `:191`); the hot
  loops (Myers word update, cell-min) are carry-chained scalar recurrences
  that cannot be widened without changing the algorithm. Unrolling the
  cell-min chain would likewise require changing the recurrence.
- **Unroll — no.** Same argument: no hot loop in `src/` is a strided,
  dependency-free stream that unrolling would accelerate; the two
  dependency chains (Myers carry, DP cell) dominate and are explicitly
  documented as serial in README.
- **`none` therefore applies to every row.** The one action with measured
  headroom is not an accel phase at all: `_hw_starts` (row 1) plus the
  small-input glue floor in row 5 are Python-side costs that an accel phase
  cannot touch. Fixing them means moving `_hw_starts` into the Mojo
  library and trimming `_encode_inputs`/allocation — a correctness-preserving
  refactor, not unroll/simd/parallel/gpu. Upstream's advantage on `path` is
  a mature bit-vector traceback, which is an algorithm change and out of
  scope for all four accel phases.

## One-line summary

Measured time lives in a Python per-cell loop (`_hw_starts`, HW only) and
in the inherently serial full-matrix fill (NW path/locations); the Myers
distance kernel is at parity with upstream and the 2× NW-distance gap is
Python/ctypes glue. Every kernel is ~1 flop/byte with carried dependencies,
so no GPU verdict is defensible and no unroll/simd/parallel phase has a
target — the next-phase assignment for all hotspots is **none**, with the
HW Python loop named as the only change worth doing next.
