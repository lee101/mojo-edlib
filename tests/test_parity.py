"""Behavioral parity checks against the published Python edlib package."""

from __future__ import annotations

import random

import edlib
import pytest

import mojo_edlib as mojo


CASES = [
    ("", ""), ("", "a"), ("a", ""), ("a", "a"), ("a", "ba"),
    ("a", "ab"), ("ACTG", "ACGT"), ("aaa", "a"),
]


@pytest.mark.parametrize("mode", ["NW", "HW", "SHW"])
@pytest.mark.parametrize("task", ["distance", "locations", "path"])
@pytest.mark.parametrize("query,target", CASES)
def test_documented_edge_cases_match_edlib(mode, task, query, target):
    assert mojo.align(query, target, mode=mode, task=task) == edlib.align(
        query, target, mode=mode, task=task
    )


@pytest.mark.parametrize("mode", ["NW", "HW", "SHW"])
@pytest.mark.parametrize("task", ["distance", "locations", "path"])
def test_randomized_alignments_match_edlib(mode, task):
    rng = random.Random(41)
    for _ in range(100):
        query = "".join(rng.choice("ACGT") for _ in range(rng.randrange(12)))
        target = "".join(rng.choice("ACGT") for _ in range(rng.randrange(12)))
        ours = mojo.align(query, target, mode=mode, task=task)
        theirs = edlib.align(query, target, mode=mode, task=task)
        assert ours == theirs


@pytest.mark.parametrize("mode", ["NW", "HW", "SHW"])
@pytest.mark.parametrize("task", ["distance", "locations", "path"])
def test_thresholds_match_edlib_for_every_mode_and_task(mode, task):
    for k in (-1, 0, 1, 2, 3):
        assert mojo.align("abc", "xyz", mode=mode, task=task, k=k) == edlib.align(
            "abc", "xyz", mode=mode, task=task, k=k
        )


def test_additional_equalities_match_edlib():
    pairs = [("a", "A"), ("b", "B")]
    assert mojo.align("ab", "AB", task="path", additionalEqualities=pairs) == edlib.align(
        "ab", "AB", task="path", additionalEqualities=pairs
    )


@pytest.mark.parametrize("mode", ["NW", "HW", "SHW"])
@pytest.mark.parametrize("task", ["distance", "locations", "path"])
@pytest.mark.parametrize("query,target", [("", "abc"), ("abc", "")])
def test_threshold_does_not_hide_edlib_empty_sequence_results(mode, task, query, target):
    assert mojo.align(query, target, mode=mode, task=task, k=0) == edlib.align(
        query, target, mode=mode, task=task, k=0
    )


def test_hashable_iterables_match_edlib():
    query, target = [1, 2, 3, 4], [1, 9, 3, 4]
    assert mojo.align(query, target, task="locations") == edlib.align(
        query, target, task="locations"
    )


@pytest.mark.parametrize("query_length", [63, 4096])
@pytest.mark.parametrize("mode", ["NW", "HW", "SHW"])
def test_bit_vector_simd_tail_and_multiword_path_match_edlib(query_length, mode):
    query = "ACGT" * (query_length // 4) + "ACGT"[:query_length % 4]
    target = "TGCA" * 17
    assert mojo.align(query, target, mode=mode) == edlib.align(query, target, mode=mode)


@pytest.mark.parametrize("target_length", [14, 15])
def test_uint16_matrix_simd_tail_and_native_trace_match_edlib(target_length):
    query = "ACGT" * 19
    target = "TGCA" * (target_length // 4) + "TGCA"[:target_length % 4]
    assert mojo.align(query, target, mode="NW", task="path") == edlib.align(
        query, target, mode="NW", task="path"
    )


def test_int32_matrix_fallback_matches_edlib():
    query, target = "A" * 65536, "A"
    assert mojo.align(query, target, mode="NW", task="path") == edlib.align(
        query, target, mode="NW", task="path"
    )


def test_ascii_bytes_fast_path_matches_edlib():
    query, target = b"ACTG" * 17, b"ACGT" * 19
    assert mojo.align(query, target, mode="NW", task="path") == edlib.align(
        query, target, mode="NW", task="path"
    )


def test_unused_additional_equality_symbols_match_edlib():
    pairs = [("unseen-left", "unseen-right")]
    assert mojo.align("abc", "axc", additionalEqualities=pairs) == edlib.align(
        "abc", "axc", additionalEqualities=pairs
    )


def test_additional_equalities_cannot_overflow_the_fixed_mask_table():
    # Values absent from both sequences are irrelevant to edlib and must not be
    # encoded as symbols after the 256-entry Mojo mask table has been sized.
    query = list(range(256))
    assert mojo.align(query, [], additionalEqualities=[(256, 257)]) == edlib.align(
        query, [], additionalEqualities=[(256, 257)]
    )


def test_more_than_256_input_symbols_is_rejected_before_the_ffi_call():
    with pytest.raises(ValueError, match="at most 256"):
        mojo.align(list(range(257)), [])


def test_multiword_carry_matches_edlib():
    query, target = "A" * 4096, "A" * 4095 + "C"
    assert mojo.align(query, target) == edlib.align(query, target)


@pytest.mark.parametrize("query,target,mode", [
    ("ACTG", "ACGT", "NW"), ("a", "ba", "NW"), ("a", "ba", "HW"),
    ("abc", "axc", "NW"), ("abc", "ab", "NW"),
])
def test_nice_alignment_matches_edlib_for_unambiguous_paths(query, target, mode):
    result = mojo.align(query, target, mode=mode, task="path")
    assert result["cigar"] == edlib.align(query, target, mode=mode, task="path")["cigar"]
    assert mojo.getNiceAlignment(result, query, target) == edlib.getNiceAlignment(
        result, query, target
    )


def test_invalid_options_are_rejected():
    with pytest.raises(ValueError):
        mojo.align("a", "b", mode="bad")
    with pytest.raises(ValueError):
        mojo.align("a", "b", task="bad")
    with pytest.raises(ValueError):
        mojo.align("a", "b", k=-2)
