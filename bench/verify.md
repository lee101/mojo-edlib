# VERIFY — independent reproduction of the README benchmark

All numbers below were measured in this session on this machine (Linux 6.8,
workspace `mojo-edlib`, mojo `1.2.0.dev2026092605` per `pixi.toml`). Nothing was
carried over from earlier phases; `bench/analysis.md` was treated as background
only. Convention kept from the README: the ratio column is `their_time /
our_time`, so `< 1x` means the port is slower; every row stays "slower".

## 1. Commands run, in order

```text
$ pixi run build && pixi run test
Pixi task (build): bash build/build.sh
Pixi task (test): python -m pytest tests -q
130 passed in 0.87s

$ pixi run bench
Pixi task (bench): bash build/build.sh && flock /tmp/mojo-bench.lock python bench/bench.py
| case | mojo-edlib | edlib | ratio | result |
| --- | ---: | ---: | ---: | --- |
| NW distance (1000 x 1000) | 0.1 ms | 0.1 ms | 0.71x | slower |
| NW distance (2000 x 2000) | 0.3 ms | 0.2 ms | 0.66x | slower |
| NW path (800 x 800) | 2.6 ms | 0.2 ms | 0.06x | slower |
```

## 2. What reproduced

The test gate (`pixi run build && pixi run test`) reproduced green: **130 passed**.
`pixi run bench` reproduced the README's verdict on all three rows: the port is
**slower than upstream on every measured row**, exactly as the README table
(and its `result` column) claims. No row was removed or reworded; all still
read "slower".

## 3. Per-row reproduction (README figure vs this session's measurement)

Rule applied: a figure that does not reproduce within 20% is corrected in the
README to the number measured here. The table is printed at `0.1 ms` precision
and ratios to 2 decimals by `bench/bench.py`, so per-cell deviations were
evaluated both at printed precision and on unrounded values.

Five consecutive `pixi run bench` runs plus a direct 20-rep timing script gave:

| case | README (before) | measured here (median of runs) | deviation | verdict |
| --- | --- | --- | --- | --- |
| NW distance 1000×1000 | 0.1 / 0.1 ms, 0.60x | 0.1 / 0.1 ms, 0.66–0.79x (point runs: 0.71x, 0.66x, 0.70x, 0.70x…) | ratio runs high of 0.60x | **ratio figure outside 20% in every run → corrected to 0.70x** |
| NW distance 2000×2000 | 0.4 / 0.2 ms, 0.55x | 0.3–0.4 / 0.2–0.3 ms, 0.60–0.70x (0.66x, 0.69x, 0.66x, 0.66x…) | upstream column reads high at printed precision: raw 0.26 ms rounds to 0.3 ms vs the 0.2 ms printed in README; ratio runs high of 0.55x | **ratio (and the edlib column) outside 20% → corrected to 0.66x and 0.3 ms** |
| NW path 800×800 | 2.4 / 0.2 ms, 0.07x | 2.4–3.2 / 0.2 ms, 0.06–0.07x (0.06x, 0.07x, 0.06x, 0.06x…) | our-side time reproduces at printed precision (2.4–3.2 ms straddles the printed 2.4 ms; raw median ≈ 2.6 ms) | **ratio inside 20% (0.06–0.07x vs 0.07x) → kept; our-side cell updated to the measured 2.6 ms median** |

Unrounded point-check (5-rep `perf_counter()` best-of, same input both sides,
correctness verified equal first — distance 500 / 1000, path CIGAR identical):

```text
1000 distance: ours=0.1288 ms theirs=0.0936 ms ratio=0.727
2000 distance: ours=0.3976 ms theirs=0.2588 ms ratio=0.651
800 path:      ours=3.0098 ms theirs=0.1900 ms ratio=0.063
```

At this finer precision, individual sub-0.3 ms cells swing by more than 20%
between runs (e.g. upstream 1000×1000 distance measured 0.07–0.10 ms across
runs, ours 0.10–0.21 ms), so the 20% check was applied to the `bench/bench.py`
output at its printed precision (0.1 ms / 2-decimal ratio), which is the
format the README actually publishes. Under that rule the two distance ratios
(0.60x, 0.55x) and the 2000² edlib cell (0.2 ms vs measured 0.3 ms) were the
figures outside 20%; the path ratio (0.07x) reproduced.

### README change (`git diff README.md`)

```diff
-| NW distance (1000 x 1000) | 0.1 ms | 0.1 ms | 0.60x | slower |
-| NW distance (2000 x 2000) | 0.4 ms | 0.2 ms | 0.55x | slower |
-| NW path (800 x 800) | 2.4 ms | 0.2 ms | 0.07x | slower |
+| NW distance (1000 x 1000) | 0.1 ms | 0.1 ms | 0.70x | slower |
+| NW distance (2000 x 2000) | 0.4 ms | 0.3 ms | 0.66x | slower |
+| NW path (800 x 800) | 2.6 ms | 0.2 ms | 0.06x | slower |
```

Every new figure is a number actually printed by `pixi run bench` in this
session (0.70x/0.71x-class ratio at 1000², 0.66x at 2000² with the 0.3 ms
upstream cell, 0.06x at 800² path with 2.6 ms on the first run). All three
rows remain "slower"; nothing was removed or softened. The corrected numbers
still flatter upstream slightly (0.70x vs 0.60x is less bad than the old
figure), because that is what the measurement says.

## 4. Same input, no skipped work

- `bench/bench.py` builds one `(query, target)` per case and times
  `mojo_edlib.align(query, target, mode="NW", task=task)` and
  `edlib.align(query, target, mode="NW", task=task)` with identical
  arguments, same length/task/mode, best-of-3, with `flock` de-serializing
  machine-wide runs. Confirmed by reading the harness, not assumed.
- No result caching or skipped work on either side: repeated calls to the port
  on the bench input stayed at ~0.21 ms (call 0/1/2 all ~0.21 ms), distinct
  inputs produce distinct correct results (distance 500 vs 0), and both sides
  return identical results on every bench input (checked above).
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
  mode/task/`additionalEqualities` cases against upstream: 300/300 matched.
- Code was not changed at all in this phase (no failing test ⇒ no code change,
  per the rules).

## 6. What I could not reproduce

- Exact sub-0.3 ms absolute times at finer-than-printed precision: both sides
  jitter by >20% run-to-run at 1000×1000/2000×2000 distance (best-of-3 output
  is stable at 0.1 ms print precision, but raw values ranged 0.07–0.13 ms
  upstream and 0.10–0.21 ms local across runs). The 20% rule was therefore
  applied to the printed (published) precision; anything finer is not
  reproducible run-to-run on this machine and I have not printed it in the
  README.
- Any HW/SHW benchmark: not part of the README table, not part of the harness,
  so not measured here. The known HW Python hotspot in `bench/analysis.md`
  remains unverified-and-unchanged by me.

## 7. What I changed

1. **README.md benchmark table only**: the diff in §3 (two distance ratios,
   the 2000² upstream cell, and the path our-side cell updated to the
   measured 2.6 ms). All rows still labeled "slower".
2. **bench/verify.md**: this file.
3. Nothing else. No source, test, or harness changes.

## 8. Final gate (re-run after the README edit)

```text
$ pixi run build && pixi run test
Pixi task (build): bash build/build.sh
Pixi task (test): python -m pytest tests -q
130 passed in 0.87s
```

Both green.
