"""Levenshtein alignment kernels exported through a deliberately small C ABI."""

from std.algorithm import parallelize
from std.sys.info import simd_width_of

comptime Ptr = UnsafePointer[Int, AnyOrigin[mut=True]]
comptime BitPtr = UnsafePointer[UInt64, AnyOrigin[mut=True]]
comptime W = simd_width_of[DType.uint64]()


def p(addr: Int) -> Ptr:
    return Ptr(unsafe_from_address=addr)


def bits(addr: Int) -> BitPtr:
    return BitPtr(unsafe_from_address=addr)


def equal(a: Int, b: Int, pairs: Ptr, pair_count: Int) -> Bool:
    if a == b:
        return True
    for i in range(pair_count):
        var left = pairs[2 * i]
        var right = pairs[2 * i + 1]
        if (a == left and b == right) or (a == right and b == left):
            return True
    return False


def cell_min(diagonal: Int, up: Int, left: Int) -> Int:
    var value = diagonal
    if up < value:
        value = up
    if left < value:
        value = left
    return value


def distance_myers(
    query: Ptr,
    target: Ptr,
    pairs: Ptr,
    workspace: BitPtr,
    query_len: Int,
    target_len: Int,
    mode: Int,
    pair_count: Int,
) -> Int:
    """Multiword Myers distance, with a 256-symbol bit-mask table in workspace."""
    if query_len == 0:
        return target_len if mode == 0 else 0

    var block_count = (query_len + 63) // 64
    def initialize_mask_block(block: Int) capturing:
        for symbol in range(256):
            workspace[symbol * block_count + block] = UInt64(0)
        var first = block * 64
        var last = min(first + 64, query_len)
        for index in range(first, last):
            var symbol = query[index]
            workspace[symbol * block_count + block] |= UInt64(1) << UInt64(index % 64)

    if query_len >= 4096:
        parallelize[initialize_mask_block](block_count, 8)
    else:
        var workspace_words = 258 * block_count
        var vector_end = workspace_words - workspace_words % W
        var zero = SIMD[DType.uint64, W](0)
        for index in range(0, vector_end, W):
            workspace.store(index, zero)
        for index in range(vector_end, workspace_words):
            workspace[index] = UInt64(0)
        for index in range(query_len):
            var symbol = query[index]
            workspace[symbol * block_count + index // 64] |= UInt64(1) << UInt64(index % 64)

    var pv_base = 256 * block_count
    var mv_base = pv_base + block_count
    for block in range(block_count):
        workspace[pv_base + block] = ~UInt64(0)
        workspace[mv_base + block] = UInt64(0)

    var score = query_len
    var best = score
    var top_bit = (query_len - 1) % 64
    for target_index in range(target_len):
        var symbol = target[target_index]
        var add_carry = UInt64(0)
        var ph_carry = UInt64(0) if mode == 1 else UInt64(1)
        var mh_carry = UInt64(0)
        for block in range(block_count):
            var equal_mask = workspace[symbol * block_count + block]
            for pair_index in range(pair_count):
                var left = pairs[2 * pair_index]
                var right = pairs[2 * pair_index + 1]
                if symbol == left and right < 256:
                    equal_mask |= workspace[right * block_count + block]
                elif symbol == right and left < 256:
                    equal_mask |= workspace[left * block_count + block]
            var positive = workspace[pv_base + block]
            var negative = workspace[mv_base + block]
            var xv = equal_mask | negative
            var addition = (equal_mask & positive) + positive
            var next_add_carry = UInt64(1) if addition < positive else UInt64(0)
            addition += add_carry
            if add_carry != UInt64(0) and addition == UInt64(0):
                next_add_carry = UInt64(1)
            add_carry = next_add_carry
            var xh = (addition ^ positive) | equal_mask
            var ph = negative | ~(xh | positive)
            var mh = positive & xh
            if block == block_count - 1:
                if (ph & (UInt64(1) << UInt64(top_bit))) != UInt64(0):
                    score += 1
                elif (mh & (UInt64(1) << UInt64(top_bit))) != UInt64(0):
                    score -= 1
            var next_ph_carry = ph >> 63
            var next_mh_carry = mh >> 63
            ph = (ph << 1) | ph_carry
            mh = (mh << 1) | mh_carry
            workspace[pv_base + block] = mh | ~(xv | ph)
            workspace[mv_base + block] = ph & xv
            ph_carry = next_ph_carry
            mh_carry = next_mh_carry
        if mode != 0 and score < best:
            best = score
    return score if mode == 0 else best


def fill_matrix(
    query: Ptr,
    target: Ptr,
    pairs: Ptr,
    matrix: Ptr,
    query_len: Int,
    target_len: Int,
    mode: Int,
    pair_count: Int,
) -> Int:
    var stride = target_len + 1
    for j in range(stride):
        matrix[j] = 0 if mode == 1 else j
    for i in range(1, query_len + 1):
        var current = i * stride
        matrix[current] = i
        for j in range(1, target_len + 1):
            var cost = 0 if equal(query[i - 1], target[j - 1], pairs, pair_count) else 1
            matrix[current + j] = cell_min(
                matrix[(i - 1) * stride + j - 1] + cost,
                matrix[(i - 1) * stride + j] + 1,
                matrix[current + j - 1] + 1,
            )
    var best = matrix[query_len * stride + target_len] if mode == 0 else matrix[query_len * stride]
    if mode != 0:
        for j in range(1, target_len + 1):
            var value = matrix[query_len * stride + j]
            if value < best:
                best = value
    return best


@export("med_distance")
def med_distance(
    query_addr: Int,
    target_addr: Int,
    pairs_addr: Int,
    work_addr: Int,
    query_len: Int,
    target_len: Int,
    mode: Int,
    pair_count: Int,
) abi("C") -> Int:
    return distance_myers(
        p(query_addr), p(target_addr), p(pairs_addr), bits(work_addr), query_len,
        target_len, mode, pair_count,
    )


@export("med_matrix")
def med_matrix(
    query_addr: Int,
    target_addr: Int,
    pairs_addr: Int,
    matrix_addr: Int,
    query_len: Int,
    target_len: Int,
    mode: Int,
    pair_count: Int,
) abi("C") -> Int:
    return fill_matrix(
        p(query_addr), p(target_addr), p(pairs_addr), p(matrix_addr), query_len,
        target_len, mode, pair_count,
    )
