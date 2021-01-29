import pytest
import itertools
import numpy as np
import grblas
from grblas import Matrix, Vector, Scalar
from grblas import unary, binary, monoid, semiring
from grblas import dtypes
from grblas.exceptions import IndexOutOfBound, OutputNotEmpty, DimensionMismatch, InvalidValue


@pytest.fixture
def A():
    data = [
        [3, 0, 3, 5, 6, 0, 6, 1, 6, 2, 4, 1],
        [0, 1, 2, 2, 2, 3, 3, 4, 4, 5, 5, 6],
        [3, 2, 3, 1, 5, 3, 7, 8, 3, 1, 7, 4],
    ]
    return Matrix.from_values(*data)


@pytest.fixture
def v():
    data = [[1, 3, 4, 6], [1, 1, 2, 0]]
    return Vector.from_values(*data)


def test_new():
    u = Vector.new(dtypes.INT8, 17)
    assert u.dtype == "INT8"
    assert u.nvals == 0
    assert u.size == 17


def test_large_vector():
    u = Vector.from_values([0, 2 ** 59], [0, 1])
    assert u.size == 2 ** 59 + 1
    assert u[2 ** 59].value == 1
    with pytest.raises(InvalidValue):
        Vector.from_values([0, 2 ** 64 - 2], [0, 1])
    with pytest.raises(OverflowError):
        Vector.from_values([0, 2 ** 64], [0, 1])


def test_dup(v):
    u = v.dup()
    assert u is not v
    assert u.dtype == v.dtype
    assert u.nvals == v.nvals
    assert u.size == v.size
    # Ensure they are not the same backend object
    v[0] = 1000
    assert u[0].value != 1000
    # extended functionality
    w = Vector.from_values([0, 1], [0, 2.5], dtype=dtypes.FP64)
    x = w.dup(dtype=dtypes.INT64)
    assert x.isequal(Vector.from_values([0, 1], [0, 2], dtype=dtypes.INT64), check_dtype=True)
    x = w.dup(mask=w.V)
    assert x.isequal(Vector.from_values([1], [2.5], dtype=dtypes.FP64), check_dtype=True)
    x = w.dup(dtype=dtypes.INT64, mask=w.V)
    assert x.isequal(Vector.from_values([1], [2], dtype=dtypes.INT64), check_dtype=True)


def test_from_values():
    u = Vector.from_values([0, 1, 3], [True, False, True])
    assert u.size == 4
    assert u.nvals == 3
    assert u.dtype == bool
    u2 = Vector.from_values([0, 1, 3], [12.3, 12.4, 12.5], size=17)
    assert u2.size == 17
    assert u2.nvals == 3
    assert u2.dtype == float
    u3 = Vector.from_values([0, 1, 1], [1, 2, 3], size=10, dup_op=binary.times)
    assert u3.size == 10
    assert u3.nvals == 2  # duplicates were combined
    assert u3.dtype == int
    assert u3[1].value == 6  # 2*3
    with pytest.raises(ValueError, match="Duplicate indices found"):
        # Duplicate indices requires a dup_op
        Vector.from_values([0, 1, 1], [True, True, True])
    with pytest.raises(ValueError, match="No indices provided. Unable to infer size."):
        Vector.from_values([], [])

    # Changed: Assume empty value is float64 (like numpy)
    # with pytest.raises(ValueError, match="No values provided. Unable to determine type"):
    w = Vector.from_values([], [], size=10)
    assert w.size == 10
    assert w.nvals == 0
    assert w.dtype == dtypes.FP64

    with pytest.raises(ValueError, match="No indices provided. Unable to infer size"):
        Vector.from_values([], [], dtype=dtypes.INT64)
    u4 = Vector.from_values([], [], size=10, dtype=dtypes.INT64)
    u5 = Vector.new(dtypes.INT64, size=10)
    assert u4.isequal(u5, check_dtype=True)

    # we check index dtype if given numpy array
    with pytest.raises(ValueError, match="indices must be integers, not float64"):
        Vector.from_values(np.array([1.2, 3.4]), [1, 2])
    # but coerce index if given Python lists (we defer to numpy casting)
    u6 = Vector.from_values([1.2, 3.4], [1, 2])
    assert u6.isequal(Vector.from_values([1, 3], [1, 2]))

    # mis-matched sizes
    with pytest.raises(ValueError, match="`indices` and `values` lengths must match"):
        Vector.from_values([0], [1, 2])


def test_clear(v):
    v.clear()
    assert v.nvals == 0
    assert v.size == 7


def test_resize(v):
    assert v.size == 7
    assert v.nvals == 4
    v.resize(20)
    assert v.size == 20
    assert v.nvals == 4
    assert v[19].value is None
    v.resize(4)
    assert v.size == 4
    assert v.nvals == 2


def test_size(v):
    assert v.size == 7


def test_nvals(v):
    assert v.nvals == 4


def test_build(v):
    assert v.nvals == 4
    v.clear()
    v.build([0, 6], [1, 2])
    assert v.nvals == 2
    with pytest.raises(OutputNotEmpty):
        v.build([1, 5], [3, 4])
    assert v.nvals == 2  # should be unchanged
    # We can clear though
    v.build([1, 2, 5], [2, 3, 4], clear=True)
    assert v.nvals == 3
    v.clear()
    with pytest.raises(IndexOutOfBound):
        v.build([0, 11], [1, 1])


def test_extract_values(v):
    idx, vals = v.to_values()
    np.testing.assert_array_equal(idx, (1, 3, 4, 6))
    np.testing.assert_array_equal(vals, (1, 1, 2, 0))
    assert idx.dtype == np.uint64
    assert vals.dtype == np.int64

    idx, vals = v.to_values(dtype=int)
    np.testing.assert_array_equal(idx, (1, 3, 4, 6))
    np.testing.assert_array_equal(vals, (1, 1, 2, 0))
    assert idx.dtype == np.uint64
    assert vals.dtype == np.int64

    idx, vals = v.to_values(dtype=float)
    np.testing.assert_array_equal(idx, (1, 3, 4, 6))
    np.testing.assert_array_equal(vals, (1, 1, 2, 0))
    assert idx.dtype == np.uint64
    assert vals.dtype == np.float64


def test_extract_input_mask():
    v = Vector.from_values([0, 1, 2], [0, 1, 2])
    m = Vector.from_values([0, 2], [0, 2])
    result = v[[0, 1]].new(input_mask=m.S)
    expected = Vector.from_values([0], [0], size=2)
    assert result.isequal(expected)
    # again
    result.clear()
    result(input_mask=m.S) << v[[0, 1]]
    assert result.isequal(expected)
    with pytest.raises(ValueError, match="Size of `input_mask` does not match size of input"):
        v[[0, 2]].new(input_mask=expected.S)
    with pytest.raises(TypeError, match="`input_mask` argument may only be used for extract"):
        v(input_mask=m.S) << 1


def test_extract_element(v):
    assert v[1].value == 1
    assert v[6].new() == 0


def test_set_element(v):
    assert v[0].value is None
    assert v[1].value == 1
    v[0] = 12
    v[1] << 9
    assert v[0].value == 12
    assert v[1].new() == 9


def test_remove_element(v):
    assert v[1].value == 1
    del v[1]
    assert v[1].value is None
    assert v[4].value == 2
    with pytest.raises(TypeError, match="Remove Element only supports"):
        del v[1:3]


def test_vxm(v, A):
    w = v.vxm(A, semiring.plus_times).new()
    result = Vector.from_values([0, 2, 3, 4, 5, 6], [3, 3, 0, 8, 14, 4])
    assert w.isequal(result)


def test_vxm_transpose(v, A):
    w = v.vxm(A.T, semiring.plus_times).new()
    result = Vector.from_values([0, 1, 6], [5, 16, 13])
    assert w.isequal(result)


def test_vxm_nonsquare(v):
    A = Matrix.from_values([0, 3], [0, 1], [10, 20], nrows=7, ncols=2)
    u = Vector.new(v.dtype, size=2)
    u().update(v.vxm(A, semiring.min_plus))
    result = Vector.from_values([1], [21])
    assert u.isequal(result)
    w1 = v.vxm(A, semiring.min_plus).new()
    assert w1.isequal(u)
    # Test the transpose case
    v2 = Vector.from_values([0, 1], [1, 2])
    w2 = v2.vxm(A.T, semiring.min_plus).new()
    assert w2.size == 7


def test_vxm_mask(v, A):
    val_mask = Vector.from_values([0, 1, 2, 3, 4], [True, False, False, True, True], size=7)
    struct_mask = Vector.from_values([0, 3, 4], [False, False, False], size=7)
    u = v.dup()
    u(struct_mask.S) << v.vxm(A, semiring.plus_times)
    result = Vector.from_values([0, 1, 3, 4, 6], [3, 1, 0, 8, 0], size=7)
    assert u.isequal(result)
    u = v.dup()
    u(~~struct_mask.S) << v.vxm(A, semiring.plus_times)
    assert u.isequal(result)
    u = v.dup()
    u(~struct_mask.S) << v.vxm(A, semiring.plus_times)
    result2 = Vector.from_values([2, 3, 4, 5, 6], [3, 1, 2, 14, 4], size=7)
    assert u.isequal(result2)
    u = v.dup()
    u(replace=True, mask=val_mask.V) << v.vxm(A, semiring.plus_times)
    result3 = Vector.from_values([0, 3, 4], [3, 0, 8], size=7)
    assert u.isequal(result3)
    u = v.dup()
    u(replace=True, mask=~~val_mask.V) << v.vxm(A, semiring.plus_times)
    assert u.isequal(result3)
    w = v.vxm(A, semiring.plus_times).new(mask=val_mask.V)
    assert w.isequal(result3)


def test_vxm_accum(v, A):
    v(binary.plus) << v.vxm(A, semiring.plus_times)
    result = Vector.from_values([0, 1, 2, 3, 4, 5, 6], [3, 1, 3, 1, 10, 14, 4], size=7)
    assert v.isequal(result)


def test_ewise_mult(v):
    # Binary, Monoid, and Semiring
    v2 = Vector.from_values([0, 3, 5, 6], [2, 3, 2, 1])
    result = Vector.from_values([3, 6], [3, 0])
    w = v.ewise_mult(v2, binary.times).new()
    assert w.isequal(result)
    w << v.ewise_mult(v2, monoid.times)
    assert w.isequal(result)
    w.update(v.ewise_mult(v2, semiring.plus_times))
    assert w.isequal(result)


def test_ewise_mult_change_dtype(v):
    # We want to divide by 2, converting ints to floats
    v2 = Vector.from_values([1, 3, 4, 6], [2, 2, 2, 2])
    assert v.dtype == dtypes.INT64
    assert v2.dtype == dtypes.INT64
    result = Vector.from_values([1, 3, 4, 6], [0.5, 0.5, 1.0, 0], dtype=dtypes.FP64)
    w = v.ewise_mult(v2, binary.cdiv[dtypes.FP64]).new()
    assert w.isequal(result), w
    # Here is the potentially surprising way to do things
    # Division is still done with ints, but results are then stored as floats
    result2 = Vector.from_values([1, 3, 4, 6], [0.0, 0.0, 1.0, 0.0], dtype=dtypes.FP64)
    w2 = v.ewise_mult(v2, binary.cdiv).new(dtype=dtypes.FP64)
    assert w2.isequal(result2), w2
    # Try with boolean dtype via auto-conversion
    result3 = Vector.from_values([1, 3, 4, 6], [True, True, False, True])
    w3 = v.ewise_mult(v2, binary.lt).new()
    assert w3.isequal(result3), w3


def test_ewise_add(v):
    # Binary, Monoid, and Semiring
    v2 = Vector.from_values([0, 3, 5, 6], [2, 3, 2, 1])
    result = Vector.from_values([0, 1, 3, 4, 5, 6], [2, 1, 3, 2, 2, 1])
    with pytest.raises(TypeError, match="require_monoid"):
        v.ewise_add(v2, binary.max)
    w = v.ewise_add(v2, binary.max, require_monoid=False).new()
    assert w.isequal(result)
    w.update(v.ewise_add(v2, monoid.max))
    assert w.isequal(result)
    w << v.ewise_add(v2, semiring.max_times)
    assert w.isequal(result)
    # default is plus
    w = v.ewise_add(v2).new()
    result = v.ewise_add(v2, monoid.plus).new()
    assert w.isequal(result)
    # what about default for bool?
    b1 = Vector.from_values([0, 1, 2, 3], [True, False, True, False])
    b2 = Vector.from_values([0, 1, 2, 3], [True, True, False, False])
    with pytest.raises(KeyError, match="plus does not work"):
        b1.ewise_add(b2).new()


def test_extract(v):
    w = Vector.new(v.dtype, 3)
    result = Vector.from_values([0, 1], [1, 1], size=3)
    w << v[[1, 3, 5]]
    assert w.isequal(result)
    w() << v[1::2]
    assert w.isequal(result)
    w2 = v[1::2].new()
    assert w2.isequal(w)


def test_extract_array(v):
    w = Vector.new(v.dtype, 3)
    result = Vector.from_values(np.array([0, 1]), np.array([1, 1]), size=3)
    w << v[np.array([1, 3, 5])]
    assert w.isequal(result)


def test_extract_fancy_scalars(v):
    assert v.dtype == dtypes.INT64
    s = v[1].new()
    assert s == 1
    assert s.dtype == dtypes.INT64

    assert v.dtype == dtypes.INT64
    s = v[1].new(dtype=float)
    assert s == 1.0
    assert s.dtype == dtypes.FP64

    t = Scalar.new(float)
    with pytest.raises(TypeError, match="is not supported"):
        t(accum=binary.plus) << s
    with pytest.raises(TypeError, match="is not supported"):
        t(accum=binary.plus) << 1
    with pytest.raises(TypeError, match="Mask not allowed for Scalars"):
        t(mask=t) << s

    s << v[1]
    assert s.value == 1
    t = Scalar.new(float)
    t << v[1]
    assert t.value == 1.0
    t = Scalar.new(float)
    t() << v[1]
    assert t.value == 1.0
    with pytest.raises(TypeError, match="Scalar accumulation with extract element"):
        t(accum=binary.plus) << v[0]


def test_assign(v):
    u = Vector.from_values([0, 2], [9, 8])
    result = Vector.from_values([0, 1, 3, 4, 6], [9, 1, 1, 8, 0])
    w = v.dup()
    w[[0, 2, 4]] = u
    assert w.isequal(result)
    w = v.dup()
    w[:5:2] << u
    assert w.isequal(result)
    with pytest.raises(TypeError):
        w[:] << u()


def test_assign_scalar(v):
    result = Vector.from_values([1, 3, 4, 5, 6], [9, 9, 2, 9, 0])
    w = v.dup()
    w[[1, 3, 5]] = 9
    assert w.isequal(result)
    w = v.dup()
    w[1::2] = 9
    assert w.isequal(result)
    w = Vector.from_values([0, 1, 2], [1, 1, 1])
    s = Scalar.from_value(9)
    w[0] = s
    assert w.isequal(Vector.from_values([0, 1, 2], [9, 1, 1]))
    w[:] = s
    assert w.isequal(Vector.from_values([0, 1, 2], [9, 9, 9]))
    with pytest.raises(TypeError, match="Bad type for arg"):
        w[:] = object()
    with pytest.raises(TypeError, match="Bad type for arg"):
        w[1] = object()
    w << 2
    assert w.isequal(Vector.from_values([0, 1, 2], [2, 2, 2]))


def test_assign_scalar_mask(v):
    mask = Vector.from_values([1, 2, 5, 6], [0, 0, 1, 0])
    result = Vector.from_values([1, 3, 4, 5, 6], [1, 1, 2, 5, 0])
    w = v.dup()
    w[:](mask.V) << 5
    assert w.isequal(result)
    w = v.dup()
    w(mask.V) << 5
    assert w.isequal(result)
    w = v.dup()
    w(mask.V)[:] << 5
    assert w.isequal(result)
    result2 = Vector.from_values([0, 1, 2, 3, 4, 6], [5, 5, 5, 5, 5, 5])
    w = v.dup()
    w[:](~mask.V) << 5
    assert w.isequal(result2)
    w = v.dup()
    w(~mask.V) << 5
    assert w.isequal(result2)
    w = v.dup()
    w(~mask.V)[:] << 5
    assert w.isequal(result2)
    result3 = Vector.from_values([1, 2, 3, 4, 5, 6], [5, 5, 1, 2, 5, 5])
    w = v.dup()
    w[:](mask.S) << 5
    assert w.isequal(result3)
    w = v.dup()
    w(mask.S) << 5
    assert w.isequal(result3)
    w = v.dup()
    w(mask.S)[:] << 5
    assert w.isequal(result3)
    result4 = Vector.from_values([0, 1, 3, 4, 6], [5, 1, 5, 5, 0])
    w = v.dup()
    w[:](~mask.S) << 5
    assert w.isequal(result4)
    w = v.dup()
    w(~mask.S) << Scalar.from_value(5)
    assert w.isequal(result4)
    w = v.dup()
    w(~mask.S)[:] << 5
    assert w.isequal(result4)


def test_subassign(A):
    v = Vector.from_values([0, 1, 2], [0, 1, 2])
    w = Vector.from_values([0, 1], [10, 20])
    m = Vector.from_values([1], [True])
    v[[0, 1]](m.S) << w
    result1 = Vector.from_values([0, 1, 2], [0, 20, 2])
    assert v.isequal(result1)
    with pytest.raises(DimensionMismatch):
        v[[0, 1]](v.S) << w
    with pytest.raises(DimensionMismatch):
        v[[0, 1]](m.S) << v

    v[[0, 1]](m.S) << 100
    result2 = Vector.from_values([0, 1, 2], [0, 100, 2])
    assert v.isequal(result2)
    with pytest.raises(DimensionMismatch):
        v[[0, 1]](v.S) << 99
    with pytest.raises(TypeError, match="Mask object must be type Vector"):
        v[[0, 1]](A.S) << 88
    with pytest.raises(TypeError, match="Mask object must be type Vector"):
        v[[0, 1]](A.S) << w

    # It may be nice for these to also raise
    v[[0, 1]](A.S)
    v[0](m.S)
    v[0](replace=True)


def test_assign_scalar_with_mask():
    v = Vector.from_values([0, 1, 2], [1, 2, 3])
    m = Vector.from_values([0, 2], [False, True])
    w1 = Vector.from_values([0], [50])
    w3 = Vector.from_values([0, 1, 2], [10, 20, 30])

    v(m.V)[:] << w3
    result = Vector.from_values([0, 1, 2], [1, 2, 30])
    assert v.isequal(result)

    v(m.V)[:] << 100
    result = Vector.from_values([0, 1, 2], [1, 2, 100])
    assert v.isequal(result)

    v(m.V, accum=binary.plus)[2] << 1000
    result = Vector.from_values([0, 1, 2], [1, 2, 1100])
    assert v.isequal(result)

    with pytest.raises(TypeError, match="Single element assign does not accept a submask"):
        v[2](w1.S) << w1

    with pytest.raises(TypeError, match="Single element assign does not accept a submask"):
        v[2](w1.S) << 7

    v[[2]](w1.S) << 7
    result = Vector.from_values([0, 1, 2], [1, 2, 7])
    assert v.isequal(result)


def test_apply(v):
    result = Vector.from_values([1, 3, 4, 6], [-1, -1, -2, 0])
    w = v.apply(unary.ainv).new()
    assert w.isequal(result)


def test_apply_binary(v):
    result_right = Vector.from_values([1, 3, 4, 6], [False, False, True, False])
    w_right = v.apply(binary.gt, right=1).new()
    w_right2 = v.apply(binary.gt, right=Scalar.from_value(1)).new()
    assert w_right.isequal(result_right)
    assert w_right2.isequal(result_right)
    result_left = Vector.from_values([1, 3, 4, 6], [1, 1, 0, 2])
    w_left = v.apply(binary.minus, left=2).new()
    w_left2 = v.apply(binary.minus, left=Scalar.from_value(2)).new()
    assert w_left.isequal(result_left)
    assert w_left2.isequal(result_left)
    with pytest.raises(TypeError):
        v.apply(binary.plus, left=v)
    with pytest.raises(TypeError):
        v.apply(binary.plus, right=v)
    with pytest.raises(TypeError, match="Cannot provide both"):
        v.apply(binary.plus, left=1, right=1)


def test_reduce(v):
    s = v.reduce(monoid.plus).new()
    assert s == 4
    assert s.dtype == dtypes.INT64
    # Test accum
    s(accum=binary.times) << v.reduce(monoid.plus)
    assert s == 16
    # Test default for non-bool
    assert v.reduce().value == 4
    # Test default for bool
    b1 = Vector.from_values([0, 1], [True, False])
    with pytest.raises(KeyError, match="plus does not work"):
        # KeyError here is kind of weird
        b1.reduce()


def test_reduce_coerce_dtype(v):
    assert v.dtype == dtypes.INT64
    s = v.reduce().new(dtype=float)
    assert s == 4.0
    assert s.dtype == dtypes.FP64
    t = Scalar.new(float)
    t << v.reduce(monoid.plus)
    assert t == 4.0
    t = Scalar.new(float)
    t() << v.reduce(monoid.plus)
    assert t == 4.0
    t(accum=binary.times) << v.reduce(monoid.plus)
    assert t == 16.0
    assert v.reduce(monoid.plus[dtypes.UINT64]).value == 4
    # Make sure we accumulate as a float, not int
    t.value = 1.23
    t(accum=binary.plus) << v.reduce()
    assert t == 5.23


def test_simple_assignment(v):
    # w[:] = v
    w = Vector.new(v.dtype, v.size)
    w << v
    assert w.isequal(v)


def test_isequal(v):
    assert v.isequal(v)
    u = Vector.from_values([1], [1])
    assert not u.isequal(v)
    u2 = Vector.from_values([1], [1], size=7)
    assert not u2.isequal(v)
    u3 = Vector.from_values([1, 3, 4, 6], [1.0, 1.0, 2.0, 0.0])
    assert not u3.isequal(v, check_dtype=True), "different datatypes are not equal"
    u4 = Vector.from_values([1, 3, 4, 6], [1.0, 1 + 1e-9, 1.999999999999, 0.0])
    assert not u4.isequal(v)
    u5 = Vector.from_values([1, 3, 4, 5], [1.0, 1.0, 2.0, 3], size=u4.size)
    assert not u4.isequal(u5)


@pytest.mark.slow
def test_isclose(v):
    assert v.isclose(v)
    u = Vector.from_values([1], [1])  # wrong size
    assert not u.isclose(v)
    u2 = Vector.from_values([1], [1], size=7)  # missing values
    assert not u2.isclose(v)
    u3 = Vector.from_values([1, 2, 3, 4, 6], [1, 1, 1, 2, 0], size=7)  # extra values
    assert not u3.isclose(v)
    u4 = Vector.from_values([1, 3, 4, 6], [1.0, 1.0, 2.0, 0.0])
    assert not u4.isclose(v, check_dtype=True), "different datatypes are not equal"
    u5 = Vector.from_values([1, 3, 4, 6], [1.0, 1 + 1e-9, 1.999999999999, 0.0])
    assert u5.isclose(v)
    u6 = Vector.from_values([1, 3, 4, 6], [1.0, 1 + 1e-4, 1.99999, 0.0])
    assert u6.isclose(v, rel_tol=1e-3)
    # isclose should consider `inf == inf`
    u7 = Vector.from_values([1, 3], [-np.inf, np.inf])
    assert u7.isclose(u7, rel_tol=1e-8)
    u4b = Vector.from_values([1, 3, 4, 5], [1.0, 1.0, 2.0, 0.0], size=u4.size)
    assert not u4.isclose(u4b)


def test_binary_op(v):
    v2 = v.dup()
    v2[1] = 0
    w = v.ewise_mult(v2, binary.gt).new()
    result = Vector.from_values([1, 3, 4, 6], [True, False, False, False])
    assert w.dtype == "BOOL"
    assert w.isequal(result)


def test_accum_must_be_binaryop(v):
    with pytest.raises(TypeError):
        v(accum=monoid.plus) << v.ewise_mult(v)


def test_mask_must_be_value_or_structure(v):
    with pytest.raises(TypeError):
        v(mask=v) << v.ewise_mult(v)


def test_incompatible_shapes(A, v):
    u = v[:-1].new()
    with pytest.raises(DimensionMismatch):
        A.mxv(u)
    with pytest.raises(DimensionMismatch):
        u.vxm(A)
    with pytest.raises(DimensionMismatch):
        u.ewise_add(v)
    with pytest.raises(DimensionMismatch):
        u.ewise_mult(v)


def test_del(capsys):
    # Exceptions in __del__ are printed to stderr
    import gc

    # shell_v does not have `gb_obj` attribute
    shell_v = Vector.__new__(Vector)
    del shell_v
    # v has `gb_obj` of NULL
    v = Vector.from_values([0, 1], [0, 1])
    gb_obj = v.gb_obj
    v.gb_obj = grblas.ffi.NULL
    del v
    # let's clean up so we don't have a memory leak
    v2 = Vector.__new__(Vector)
    v2.gb_obj = gb_obj
    del v2
    gc.collect()
    captured = capsys.readouterr()
    assert not captured.out
    assert not captured.err


def test_import_export(v):
    v1 = v.dup()
    d = v1.ss.export("sparse", give_ownership=True)
    assert d["size"] == 7
    assert (d["indices"] == [1, 3, 4, 6]).all()
    assert (d["values"] == [1, 1, 2, 0]).all()
    w1 = Vector.ss.import_any(**d)
    assert w1.isequal(v)

    v2 = v.dup()
    d = v2.ss.export("bitmap")
    assert d["nvals"] == 4
    assert len(d["bitmap"]) == 7
    assert (d["bitmap"] == [0, 1, 0, 1, 1, 0, 1]).all()
    assert (d["values"][d["bitmap"]] == [1, 1, 2, 0]).all()
    w2 = Vector.ss.import_any(**d)
    assert w2.isequal(v)
    del d["nvals"]
    w2b = Vector.ss.import_any(**d)
    assert w2b.isequal(v)
    d["bitmap"] = np.concatenate([d["bitmap"], d["bitmap"]])
    w2c = Vector.ss.import_any(**d)
    assert w2c.isequal(v)

    v3 = Vector.from_values([0, 1, 2], [1, 3, 5])
    v3_copy = v3.dup()
    d = v3.ss.export("full")
    assert (d["values"] == [1, 3, 5]).all()
    w3 = Vector.ss.import_any(**d)
    assert w3.isequal(v3_copy)

    v4 = v.dup()
    d = v4.ss.export()
    assert d["format"] in {"sparse", "bitmap", "full"}
    w4 = Vector.ss.import_any(**d)
    assert w4.isequal(v)

    # can't own if we can't write
    d = v.ss.export("sparse")
    d["indices"].flags.writeable = False
    # can't own a view
    size = len(d["values"])
    vals = np.zeros(2 * size, dtype=d["values"].dtype)
    vals[:size] = d["values"]
    view = vals[:size]
    w5 = Vector.ss.import_sparse(take_ownership=True, **dict(d, values=view))
    assert w5.isequal(v)
    assert d["values"].flags.owndata
    assert d["values"].flags.writeable
    assert d["indices"].flags.owndata

    # now let's take ownership!
    d = v.ss.export("sparse", sort=True)
    w6 = Vector.ss.import_any(take_ownership=True, **d)
    assert w6.isequal(v)
    assert not d["values"].flags.owndata
    assert not d["values"].flags.writeable
    assert not d["indices"].flags.owndata
    assert not d["indices"].flags.writeable

    with pytest.raises(ValueError, match="Invalid format: bad_name"):
        v.ss.export("bad_name")

    d = v.ss.export("sparse")
    del d["format"]
    with pytest.raises(TypeError, match="Cannot provide both"):
        Vector.ss.import_any(bitmap=d["values"], **d)

    # if we give the same value, make sure it's copied
    for format, key1, key2 in [
        ("sparse", "values", "indices"),
        ("bitmap", "values", "bitmap"),
    ]:
        # No assertions here, but code coverage should be "good enough"
        d = v.ss.export(format, raw=True)
        d[key1] = d[key2]
        Vector.ss.import_any(take_ownership=True, **d)


def test_import_export_auto(v):
    v_orig = v.dup()
    for format in ["sparse", "bitmap"]:
        for (
            sort,
            raw,
            import_format,
            give_ownership,
            take_ownership,
            import_func,
        ) in itertools.product(
            [False, True],
            [False, True],
            [format, None],
            [False, True],
            [False, True],
            [Vector.ss.import_any, getattr(Vector.ss, f"import_{format}")],
        ):
            v2 = v.dup() if give_ownership else v
            d = v2.ss.export(format, sort=sort, raw=raw, give_ownership=give_ownership)
            d["format"] = import_format
            other = import_func(take_ownership=take_ownership, **d)
            assert other.isequal(v_orig)
            d["format"] = "bad_format"
            with pytest.raises(ValueError, match="Invalid format"):
                import_func(**d)
    assert v.isequal(v_orig)

    w = Vector.from_values([0, 1, 2], [10, 20, 30])
    w_orig = w.dup()
    format = "full"
    for (raw, import_format, give_ownership, take_ownership, import_func,) in itertools.product(
        [False, True],
        [format, None],
        [False, True],
        [False, True],
        [Vector.ss.import_any, getattr(Vector.ss, f"import_{format}")],
    ):
        w2 = w.dup() if give_ownership else w
        d = w2.ss.export(format, raw=raw, give_ownership=give_ownership)
        d["format"] = import_format
        other = import_func(take_ownership=take_ownership, **d)
        assert other.isequal(w_orig)
        d["format"] = "bad_format"
        with pytest.raises(ValueError, match="Invalid format"):
            import_func(**d)
    assert w.isequal(w_orig)


def test_contains(v):
    assert 0 not in v
    assert 1 in v
    with pytest.raises(TypeError):
        [0] in v
    with pytest.raises(TypeError):
        (0,) in v


def test_iter(v):
    assert set(v) == {1, 3, 4, 6}


def test_wait(v):
    v2 = v.dup()
    v2.wait()
    assert v2.isequal(v)
