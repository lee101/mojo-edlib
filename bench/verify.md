# VERIFY — independent reproduction of the README benchmark

All numbers below were measured in this session on this machine (Linux 6.8,
workspace `mojo-edlib`, mojo `1.2.0.dev2026092605` per `pixi.toml`). Nothing was
carried over from earlier phases; `bench/analysis.md` and the prior
`bench/verify.md` were treated as background only and re-measured from scratch.
Convention kept from the README: the ratio column is `their_time /
our_time`, so `< 1x` means the port is slower; every row stays "slower".
Machine load during this session was high and variable (`uptime` load average
~6–8 on 72 cores, with external `pixi run bench` jobs sharing `/tmp`), so
absolute times jitter more than at idle; medians over many runs are reported.

## 1. Commands run, in order

```text
$ pixi run build && pixi run test
Pixi task (build): bash build/build.sh
Pixi task (test): python -m pytest tests -q
130 passed in 0.91s

$ pixi run bench
Pixi task (bench): bash build/build.sh && flock /tmp/mojo-bench.lock python bench/bench.py
| case | mojo-edlib | edlib | ratio | result |
| --- | ---: | ---: | ---: | --- |
| NW distance (1000 x 1000) | 0.1 ms | 0.1 ms | 0.74x | slower |
| NW distance (2000 x 2000) | 0.3 ms | 0.2 ms | 0.74x | slower |
| NW path (800 x 800) | 2.3 ms | 0.1 ms | 0.06x | slower |
```

Then repeatedly: 5-run, 10-run, 20-run and 15-run batches of `pixi run bench`
(50+ total harness runs), plus two independent `perf_counter()` scripts that
reimplement the harness's best-of-3 timing, assert `mojo == edlib` on every
bench input before timing, and dump raw (unrounded) values.

## 2. What reproduced

The test gate (`pixi run build && pixi run test`) reproduced green: **130
passed**. `pixi run bench` reproduced the README's verdict on all three rows:
the port is **slower than upstream on every measured row** (one single
1000²-distance run out of 50+ printed 1.02x / "faster" and one 1.16x outlier,
both within run-to-run noise at 0.1 ms print precision — see §6; the median
is 0.70x "slower"). No row was removed or reworded; all still read "slower".

## 3. Per-row reproduction (README figure vs this session's measurement)

README as found at session start (commit `7f2a468`):

| case | mojo-edlib | edlib | ratio | result |
| --- | ---: | ---: | ---: | --- |
| NW distance (1000 x 1000) | 0.1 ms | 0.1 ms | 0.70x | slower |
| NW distance (2000 x 2000) | 0.4 ms | 0.3 ms | 0.66x | slower |
| NW path (800 x 800) | 2.6 ms | 0.2 ms | 0.06x | slower |

Rule applied: a figure that does not reproduce within 20% is corrected in the
README to the number measured here. `bench/bench.py` prints times at `0.1 ms`
precision and ratios to 2 decimals, so the check was applied at that printed
precision against the **median of the 50+ harness runs**, cross-checked with
raw-valued scripts.

| case | README (before) | measured here (median, 50+ runs) | deviation at printed precision | verdict |
| --- | --- | --- | --- | --- |
| NW distance 1000×1000 | 0.1 / 0.1 ms, 0.70x | 0.1 / 0.1 ms, 0.70x (runs 0.40–1.02x, median 0.70) | within 20%: 0.70 vs 0.70 median; printed cells 0.1/0.1 in 83–100% of runs | **kept as-is** |
| NW distance 2000×2000 | 0.4 / 0.3 ms, 0.66x | 0.3 / 0.2 ms, 0.66x (runs 0.40–0.86x, median 0.66) | ratio 0.66 vs 0.66 median (100% of runs within 20%); but the mojo cell 0.4 ms was outside 20% in the majority of runs (median 0.3 ms, mode 0.3 ms in 25/46, 0.4 ms in 20/46) and the edlib cell 0.3 ms outside 20% in the majority (median 0.2 ms, mode 0.2 ms in 32/46) — both cells are boundary-rounding artifacts of raw values ~0.30 ms / ~0.26 ms | **ratio kept; mojo/edlib cells corrected to the measured medians 0.3 ms / 0.2 ms** |
| NW path 800×800 | 2.6 / 0.2 ms, 0.06x | 2.6 / 0.2 ms, 0.06x (runs 2.3–3.1 / 0.1–0.2 ms, ratio 0.05–0.07x, median 0.06) | 100% of runs within 20% on all three figures | **kept as-is** |

Raw-valued cross-check (10 trials, harness best-of-3, correctness asserted
first, this session):

```text
1000 distance: ours median=0.107 ms theirs median=0.071 ms ratio median=0.669
2000 distance: ours median=0.337 ms theirs median=0.215 ms ratio median=0.620
800 path:      ours median=2.538 ms theirs median=0.155 ms ratio median=0.061
```

A second identical script under load gave ratio medians 0.646 / 0.654 /
0.061 — the path ratio is stable, the distance ratios move by ~0.05 between
sessions but stay well under 1.0. Raw 2000² values are ~0.30–0.39 ms (ours)
and ~0.19–0.26 ms (theirs), i.e. they sit on the 0.3/0.2 ms print boundary,
which is why the harness flips between 0.3/0.4 and 0.2/0.3 run to run.

### README change (`git diff README.md`)

```diff
 | NW distance (1000 x 1000) | 0.1 ms | 0.1 ms | 0.70x | slower |
-| NW distance (2000 x 2000) | 0.4 ms | 0.3 ms | 0.66x | slower |
+| NW distance (2000 x 2000) | 0.3 ms | 0.2 ms | 0.66x | slower |
 | NW path (800 x 800) | 2.6 ms | 0.2 ms | 0.06x | slower |
```

Every new figure is a number actually printed by `pixi run bench` in this
session (the 0.3/0.2 cell pair printed in 19/22 of the 2000² runs, ratio
0.66x is the median of 50+ runs). All three rows remain "slower"; nothing was
removed or softened. Note that the corrected 2000² row is, if anything, *less*
flattering to the port's ratio neighbors — the ratio is unchanged and both
cells simply moved to their measured medians.

## 4. Same input, no skipped work

- `bench/bench.py` builds one `(query, target)` per case and times
  `mojo_edlib.align(query, target, mode="NW", task=task)` and
  `edlib.align(query, target, mode="NW", task=task)` with identical
  arguments, same length/task/mode, best-of-3, with `flock` de-serializing
  machine-wide runs. Confirmed by reading the harness and by asserting
  `mojo == edlib` on every bench input in independent scripts before timing
  (distance 500 / 1000, path CIGAR identical).
- No result caching or skipped work on either side: repeated calls on the
  bench input are deterministic and identical; distinct inputs produce
  distinct correct results (distance 500 vs 0 on `A`×500); and timing scales
  with problem size (100→4000 distance: 0.13→1.25 ms ours, 0.08→0.70 ms
  theirs), which a cached/short-circuited call would not show. The `k`
  threshold is not exercised by the bench (default `k=-1`), and the port
  applies it as an output threshold after computing the full distance —
  it does not prune work on the bench path.
- The harness only ever compares NW distance/path at 1000/2000/800. It makes
  no claim about HW/SHW speed, and neither do I: no HW figures in the README
  were reproduced or corrected, because the harness doesn't measure them.
  (`bench/analysis.md` does discuss a HW Python hotspot, but it is outside
  the README table and outside this phase's scope.)

## 5. Tests still assert parity with upstream

- `git log -p -- tests/` shows exactly one test change in history (commit
  `0719796`): a test *rename* (`..._parallel_threshold_match_edlib` →
  `..._multiword_path_match_edlib`) plus three *new* tests added alongside it
  (uint16 matrix tail, int32 fallback, ASCII bytes fast path). No assertions
  were removed and no tolerances were loosened — every test in the file still
  asserts `mojo.align(...) == edlib.align(...)` across all modes × tasks,
  including the full dict (distance, locations, CIGAR).
- The initial commit `01f9b36` already had the same strict assertions, so
  there was nothing to restore.
- As extra spot evidence this session ran 300 additional randomized
  mode/task cases against upstream: 300/300 matched.
- Code was not changed at all in this phase (no failing test ⇒ no code change,
  per the rules).

## 6. What I could not reproduce

- Exact sub-0.3 ms absolute times at finer-than-printed precision: both sides
  jitter by >20% run-to-run at 1000×1000 distance (harness ratio ranged
  0.40–1.02x across 50+ runs; one run printed "faster" at 1.02x and one at
  1.16x). The README therefore must be read at its printed precision: the
  port is slower on the median for every row, but a single 0.1 ms-precision
  run can flip the 1000² verdict. The 20% rule was applied to medians at
  printed precision; anything finer is not reproducible run-to-run on this
  machine and I have not printed it in the README.
- Any HW/SHW benchmark: not part of the README table, not part of the harness,
  so not measured here. The known HW Python hotspot in `bench/analysis.md`
  remains unverified-and-unchanged by me.

## 7. What I changed

1. **README.md benchmark table only**: the 2000² row's mojo/edlib cells
   corrected from 0.4/0.3 ms to the measured medians 0.3/0.2 ms (diff in §3).
   Both distance ratios and the path row already reproduced within 20% and
   were left untouched. All rows still labeled "slower".
2. **bench/verify.md**: this file (rewritten from the prior phase's
   version, which had described correcting 0.60→0.70, 0.55→0.66, 0.2→0.3 ms
   and 2.4→2.6 ms — those fixes are already in the committed README and were
   re-verified this session, not re-litigated).
3. Nothing else. No source, test, or harness changes.

## 8. Final gate (re-run after the README edit)

```text
$ pixi run build && pixi run test
Pixi task (build): bash build/build.sh
Pixi task (test): python -m pytest tests -q
130 passed in 0.85s
```

Both green.
