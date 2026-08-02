"""A Mojo-backed compatible subset of :mod:`edlib`.

``align`` implements the upstream modes, tasks, threshold and additional
equalities.  Inputs may be strings, bytes, or iterables of hashable values.
"""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

import numpy as np

from ._lib import BuildError, lib

__version__ = "0.1.0"
__all__ = ["align", "getNiceAlignment", "BuildError"]

_MODES = {"NW": 0, "HW": 1, "SHW": 2}
_TASKS = {"distance", "locations", "path"}


def _values(value: Any, name: str) -> list[Any]:
    if isinstance(value, str):
        return list(value)
    if isinstance(value, bytes):
        return list(value)
    try:
        return list(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be a string, bytes, or iterable") from exc


def _encode(
    query: list[Any], target: list[Any], additional_equalities: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Map hashable Python values to stable int64 symbols for the C ABI."""
    codes: dict[Any, int] = {}

    def code(value: Any) -> int:
        try:
            if value not in codes:
                codes[value] = len(codes)
            return codes[value]
        except TypeError as exc:
            raise TypeError("query and target values must be hashable") from exc

    query_codes = [code(value) for value in query]
    target_codes = [code(value) for value in target]
    # edlib reports the alphabet from the two input sequences.  Equalities that
    # mention symbols absent from either sequence cannot affect an alignment, so
    # do not encode them for the fixed-size (256 entry) Mojo mask table.
    alphabet_length = len(codes)
    if alphabet_length > 256:
        raise ValueError("query and target combined must have at most 256 unique values")
    pairs: list[int] = []
    if additional_equalities is not None:
        try:
            iterator = iter(additional_equalities)
        except TypeError as exc:
            raise TypeError("additionalEqualities must be an iterable of pairs") from exc
        for pair in iterator:
            try:
                left, right = pair
            except (TypeError, ValueError) as exc:
                raise ValueError("each additional equality must contain exactly two values") from exc
            try:
                left_code = codes.get(left)
                right_code = codes.get(right)
            except TypeError as exc:
                raise TypeError("additionalEqualities values must be hashable") from exc
            if left_code is not None and right_code is not None:
                pairs.extend((left_code, right_code))
    return (
        np.asarray(query_codes, dtype=np.int64),
        np.asarray(target_codes, dtype=np.int64),
        np.asarray(pairs, dtype=np.int64),
        alphabet_length,
    )


def _end_columns(last_row: np.ndarray, mode: str, query_len: int) -> tuple[int, list[int]]:
    if query_len == 0:
        if mode == "NW":
            return int(last_row[-1]), [len(last_row) - 1]
        return int(last_row[0]), [0]
    if mode == "NW":
        return int(last_row[-1]), [len(last_row) - 1]
    distance = int(last_row.min())
    return distance, np.flatnonzero(last_row == distance).astype(int).tolist()


def _equal(a: int, b: int, pairs: np.ndarray) -> bool:
    if a == b:
        return True
    for left, right in pairs.reshape(-1, 2):
        if (a == left and b == right) or (a == right and b == left):
            return True
    return False


def _hw_starts(
    matrix: np.ndarray, query: np.ndarray, target: np.ndarray, pairs: np.ndarray,
) -> np.ndarray:
    """Earliest target start among all optimal prefixes at each DP cell."""
    starts = np.empty_like(matrix)
    starts[0] = np.arange(len(target) + 1, dtype=np.int64)
    starts[1:, 0] = 0
    for i in range(1, len(query) + 1):
        for j in range(1, len(target) + 1):
            value = int(matrix[i, j])
            candidates: list[int] = []
            if int(matrix[i - 1, j]) + 1 == value:
                candidates.append(int(starts[i - 1, j]))
            if int(matrix[i, j - 1]) + 1 == value:
                candidates.append(int(starts[i, j - 1]))
            cost = 0 if _equal(int(query[i - 1]), int(target[j - 1]), pairs) else 1
            if int(matrix[i - 1, j - 1]) + cost == value:
                candidates.append(int(starts[i - 1, j - 1]))
            starts[i, j] = min(candidates)
    return starts


def _trace(
    matrix: np.ndarray, query: np.ndarray, target: np.ndarray, pairs: np.ndarray,
    end_column: int, mode: str, starts: np.ndarray | None = None,
) -> tuple[int | None, str | None]:
    """Trace a canonical minimum path; the preference matches edlib's examples."""
    i, j = len(query), end_column
    steps: list[str] = []
    width = len(target) + 1
    while i > 0 or (j > 0 and mode != "HW"):
        here = int(matrix[i, j])
        wanted_start = int(starts[i, j]) if starts is not None else None
        if i and int(matrix[i - 1, j]) + 1 == here and (
            starts is None or int(starts[i - 1, j]) == wanted_start
        ):
            steps.append("I")
            i -= 1
            continue
        if j and int(matrix[i, j - 1]) + 1 == here and (
            starts is None or int(starts[i, j - 1]) == wanted_start
        ):
            steps.append("D")
            j -= 1
            continue
        if i and j:
            match = _equal(int(query[i - 1]), int(target[j - 1]), pairs)
            if int(matrix[i - 1, j - 1]) + (0 if match else 1) == here and (
                starts is None or int(starts[i - 1, j - 1]) == wanted_start
            ):
                steps.append("=" if match else "X")
                i -= 1
                j -= 1
                continue
        raise RuntimeError(f"invalid DP traceback at ({i}, {j}) in width {width}")
    start = j if len(query) else None
    if not steps:
        return start, None
    steps.reverse()
    encoded: list[str] = []
    previous, count = steps[0], 0
    for op in steps:
        if op == previous:
            count += 1
        else:
            encoded.append(f"{count}{previous}")
            previous, count = op, 1
    encoded.append(f"{count}{previous}")
    return start, "".join(encoded)


def align(
    query: Any,
    target: Any,
    mode: str = "NW",
    task: str = "distance",
    k: int = -1,
    additionalEqualities: Any = None,
) -> dict[str, Any]:
    """Align query with target using unit-cost Levenshtein edit distance.

    This mirrors ``edlib.align`` for modes ``NW``, ``HW`` and ``SHW`` and
    tasks ``distance``, ``locations`` and ``path``.
    """
    if mode not in _MODES:
        raise ValueError("mode must be one of 'NW', 'HW', or 'SHW'")
    if task not in _TASKS:
        raise ValueError("task must be one of 'distance', 'locations', or 'path'")
    if not isinstance(k, int) or k < -1:
        raise ValueError("k must be an integer greater than or equal to -1")
    query_values, target_values = _values(query, "query"), _values(target, "target")
    q, t, pairs, alphabet_length = _encode(query_values, target_values, additionalEqualities)
    mode_code = _MODES[mode]
    # NumPy gives zero-length arrays a valid non-null data address, as required
    # by Mojo's non-nullable UnsafePointer ABI.
    if task == "distance":
        blocks = (len(q) + 63) // 64
        # The Mojo kernel views this allocation as UInt64 bit masks.  Keep that
        # dtype explicit; query, target, pairs, and matrix are separately int64.
        work = np.empty(258 * blocks, dtype=np.uint64)
        distance = int(lib().med_distance(
            q.ctypes.data, t.ctypes.data, pairs.ctypes.data, work.ctypes.data,
            len(q), len(t), mode_code, len(pairs) // 2,
        ))
        if mode == "NW" or not len(q):
            end_columns = [len(t)] if mode == "NW" else [0]
        else:
            matrix = np.empty((len(q) + 1, len(t) + 1), dtype=np.int64)
            distance = int(lib().med_matrix(
                q.ctypes.data, t.ctypes.data, pairs.ctypes.data, matrix.ctypes.data,
                len(q), len(t), mode_code, len(pairs) // 2,
            ))
            _, end_columns = _end_columns(matrix[-1], mode, len(q))
        locations: list[tuple[int | None, int]] = [(None, col - 1) for col in end_columns]
        cigar = None
    else:
        matrix = np.empty((len(q) + 1, len(t) + 1), dtype=np.int64)
        distance = int(lib().med_matrix(
            q.ctypes.data, t.ctypes.data, pairs.ctypes.data, matrix.ctypes.data,
            len(q), len(t), mode_code, len(pairs) // 2,
        ))
        _, end_columns = _end_columns(matrix[-1], mode, len(q))
        if not len(q) or not len(t):
            locations = [(None, col - 1) for col in end_columns]
            cigar = None
        else:
            starts = _hw_starts(matrix, q, t, pairs) if mode == "HW" else None
            traced = [_trace(matrix, q, t, pairs, col, mode, starts) for col in end_columns]
            locations = [(start, col - 1) for col, (start, _) in zip(end_columns, traced)]
            cigar = traced[0][1] if task == "path" else None
    # edlib returns the direct empty-sequence result without applying k.
    if len(q) and len(t) and distance > k >= 0:
        return {"editDistance": -1, "alphabetLength": alphabet_length, "locations": [], "cigar": None}
    return {
        "editDistance": distance,
        "alphabetLength": alphabet_length,
        "locations": locations,
        "cigar": cigar,
    }


def getNiceAlignment(
    alignResult: dict[str, Any], query: Any, target: Any, gapSymbol: str = "-",
) -> dict[str, str]:
    """Expand an extended CIGAR returned by ``align(task='path')``."""
    cigar = alignResult.get("cigar")
    if not cigar:
        raise Exception(
            "The object alignResult contains an empty CIGAR string. Users must run "
            "align() with task='path'. Please check the input alignResult."
        )
    query_values, target_values = _values(query, "query"), _values(target, "target")
    if not isinstance(query, (str, bytes)) or not isinstance(target, (str, bytes)):
        raise TypeError("getNiceAlignment currently requires string or bytes inputs")
    start, _ = alignResult["locations"][0]
    qpos, tpos = 0, 0 if start is None else start
    query_aligned: list[Any] = []
    target_aligned: list[Any] = []
    matched: list[str] = []
    for count_text, operation in re.findall(r"(\d+)([=XID])", cigar):
        for _ in range(int(count_text)):
            if operation in "=XI":
                query_aligned.append(query_values[qpos])
                qpos += 1
            else:
                query_aligned.append(gapSymbol)
            if operation in "=XD":
                target_aligned.append(target_values[tpos])
                tpos += 1
            else:
                target_aligned.append(gapSymbol)
            matched.append("|" if operation == "=" else "." if operation == "X" else "-")
    if isinstance(query, bytes):
        return {
            "query_aligned": bytes(query_aligned),
            "matched_aligned": "".join(matched),
            "target_aligned": bytes(target_aligned),
        }
    return {
        "query_aligned": "".join(query_aligned),
        "matched_aligned": "".join(matched),
        "target_aligned": "".join(target_aligned),
    }
