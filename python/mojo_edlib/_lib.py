"""ctypes bridge for the Mojo alignment kernels."""

from __future__ import annotations

import ctypes
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "dist", "libmojo-edlib.so")
I = ctypes.c_int64


class BuildError(RuntimeError):
    pass


_lib: ctypes.CDLL | None = None


def lib() -> ctypes.CDLL:
    global _lib
    if _lib is None:
        if not os.path.exists(LIB):
            raise BuildError("Mojo library is missing; run `pixi run build` first")
        _lib = ctypes.CDLL(LIB)
        _lib.med_distance.argtypes = [I] * 9
        _lib.med_distance.restype = I
        _lib.med_matrix.argtypes = [I] * 8
        _lib.med_matrix.restype = I
        _lib.med_matrix16.argtypes = [I] * 8
        _lib.med_matrix16.restype = I
        _lib.med_trace.argtypes = [I] * 9
        _lib.med_trace.restype = I
        _lib.med_trace16.argtypes = [I] * 9
        _lib.med_trace16.restype = I
    return _lib
