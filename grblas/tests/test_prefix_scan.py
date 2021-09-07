import numpy as np
import pytest

import grblas as gb
from grblas import Matrix, Vector, binary, monoid


@pytest.mark.parametrize("method", ["scan_rows", "scan_columns"])
@pytest.mark.parametrize("length", list(range(34)))
@pytest.mark.parametrize("do_random", [False, True])
def test_scan_matrix(method, length, do_random):
    if do_random:
        A = np.random.randint(10, size=2 * length).reshape((2, length))
        mask = (A % 2).astype(bool)
        A[~mask] = 0
        M = Matrix.ss.import_bitmapr(values=A, bitmap=mask, name="A")
        expected = A.cumsum(axis=1)
        expected[~mask] = 0
    else:
        A = np.arange(2 * length).reshape((2, length))
        M = Matrix.ss.import_fullr(values=A, name="A")
        expected = A.cumsum(axis=1)

    if method == "scan_rows":
        R = M.ss.scan_rows()
    else:
        M = M.T.new(name="A")
        R = M.ss.scan_columns(binary.plus).T.new()

    result = gb.io.to_numpy(R)
    try:
        np.testing.assert_array_equal(result, expected)
    except Exception:  # pragma: no cover
        print(M)
        raise


@pytest.mark.parametrize("length", list(range(34)))
@pytest.mark.parametrize("do_random", [False, True])
def test_scan_vector(length, do_random):
    if do_random:
        a = np.random.randint(10, size=length)
        mask = (a % 2).astype(bool)
        a[~mask] = 0
        v = Vector.ss.import_bitmap(values=a, bitmap=mask)
        expected = a.cumsum()
        expected[~mask] = 0
    else:
        a = np.arange(length)
        v = Vector.ss.import_full(values=a)
        expected = a.cumsum()
    r = v.ss.scan()
    result = gb.io.to_numpy(r)
    try:
        np.testing.assert_array_equal(result, expected)
    except Exception:  # pragma: no cover
        print(v)
        raise


def test_cumprod():
    v = Vector.from_values([1, 3, 4, 6], [2, 3, 4, 5])
    expected = Vector.from_values([1, 3, 4, 6], [2, 6, 24, 120])
    r = v.ss.scan(monoid.times)
    assert r.isequal(expected)


def test_bad_scan():
    v = Vector.from_values(range(10), range(10))
    with pytest.raises(TypeError, match="Bad type for argument `op`"):
        v.ss.scan(op=binary.first)
