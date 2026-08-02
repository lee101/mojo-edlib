"""Run with `pixi run bench`; the Pixi task serializes machine-wide runs."""

from __future__ import annotations

import math
import os
import sys
import time

import edlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import mojo_edlib  # noqa: E402


def best_time(fn, repeats: int = 3) -> float:
    best = math.inf
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def sequences(length: int) -> tuple[str, str]:
    alphabet = "ACGT"
    query = "".join(alphabet[(17 * i + 3) % 4] for i in range(length))
    target = "".join(alphabet[(11 * i + 1) % 4] for i in range(length))
    return query, target


def main() -> None:
    print("| case | mojo-edlib | edlib | ratio | result |")
    print("| --- | ---: | ---: | ---: | --- |")
    for length, task in ((1_000, "distance"), (2_000, "distance"), (800, "path")):
        query, target = sequences(length)
        ours = lambda: mojo_edlib.align(query, target, mode="NW", task=task)
        theirs = lambda: edlib.align(query, target, mode="NW", task=task)
        ours()
        our_time, their_time = best_time(ours), best_time(theirs)
        state = "faster" if our_time < their_time else "slower"
        print(
            f"| NW {task} ({length} x {length}) | {our_time * 1e3:.1f} ms | "
            f"{their_time * 1e3:.1f} ms | {their_time / our_time:.2f}x | {state} |"
        )


if __name__ == "__main__":
    main()
