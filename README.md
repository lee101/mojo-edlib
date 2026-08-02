# mojo-edlib

`mojo-edlib` is a standalone Mojo implementation of unit-cost edit-distance
alignment, with a Python API modeled on [edlib](https://github.com/Martinsos/edlib).
It is useful when alignment is a hot, predictable dynamic-programming workload
and the caller wants a small shared library with no allocator or Python in the
inner loop.

## Covered API

`mojo_edlib.align()` supports the upstream edlib modes and optional threshold
and equality arguments:

| mode | alignment |
| --- | --- |
| `NW` | global Needleman-Wunsch alignment |
| `HW` | infix alignment; target prefix and suffix are free |
| `SHW` | prefix alignment; target suffix is free |

All task levels are covered: `distance`, `locations`, and `path`.
`getNiceAlignment()` expands a path CIGAR. Inputs to `align` can be strings,
bytes, or iterables of hashable objects (up to edlib's input-symbol limit),
and `additionalEqualities` is supported.

Results for every mode and task, including locations and extended CIGAR, are
parity-tested directly against the published `edlib` package. `k` has the same
result semantics as edlib, but is an output threshold here rather than a
band-pruning optimization. This project does not expose edlib's native C/C++
API; it is a Python-compatible subset backed by a Mojo shared library.

## Install

```bash
pixi install
pixi run build
pixi run test
pixi run bench
```

The Python package is source-local, so Pixi activates `python/` on its import
path. The build places the shared library at `dist/libmojo-edlib.so`.

```python
import mojo_edlib as edlib

result = edlib.align("ACTG", "ACGT", mode="NW", task="path")
alignment = edlib.getNiceAlignment(result, "ACTG", "ACGT")
```

The result contains the edit distance, locations, and an extended CIGAR; the
second call expands that CIGAR into aligned strings.

## Benchmark

Measured by `pixi run bench`. Values are the best of the benchmark repetitions
and include Python/ctypes call overhead.

| case | mojo-edlib | edlib | ratio | result |
| --- | ---: | ---: | ---: | --- |
| NW distance (1000 x 1000) | 0.4 ms | 0.1 ms | 0.19x | slower |
| NW distance (2000 x 2000) | 1.0 ms | 0.2 ms | 0.22x | slower |
| NW path (800 x 800) | 4.1 ms | 0.2 ms | 0.04x | slower |

The distance task uses a multiword Myers bit-vector kernel. Its mask-table
clear is SIMD-vectorized and its state update carries between words, so that
update remains serial. Locations and traceback retain the full DP matrix
required for their canonical public results. Upstream remains faster,
particularly for paths, because it has a more mature bit-vector traceback
implementation.

There is no GPU path. Edit-distance bit-vector updates have low arithmetic
intensity and carry dependencies; host/device transfer and kernel launch cost
lose to the CPU on this workload.

## How it works

```text
python/mojo_edlib     input normalization, locations, CIGAR traceback
        | ctypes: contiguous integer buffers passed as addresses
src/capi.mojo         C ABI exports and Myers/full-matrix alignment kernels
dist/libmojo-edlib.so shared library built by Mojo
```

The fast `distance` task uses a caller-owned bit-mask workspace, proportional
to query length. The mask table is built directly in that NumPy allocation with no copy
across the FFI boundary.
`locations` and `path` use a caller-owned row-major matrix so Python can trace
starts and CIGAR without
allocation inside Mojo. Buffers cross the ABI as `Int` addresses and are
rebuilt as `UnsafePointer[Int, AnyOrigin[mut=True]]`, matching the Mojo nightly
FFI constraint.

## License

MIT
