import grblas as gb
import numpy as np
from numba import njit
from numbers import Integral, Number
from suitesparse_graphblas.utils import claim_buffer, claim_buffer_2d, unclaim_buffer
from .. import ffi, lib
from ..base import call, record_raw
from ..dtypes import lookup_dtype, INT64
from ..exceptions import check_status, check_status_carg
from ..scalar import _CScalar
from ..utils import get_shape, ints_to_numpy_buffer, values_to_numpy_buffer, wrapdoc, _CArray

ffi_new = ffi.new


@njit
def _head_matrix_full(values, nrows, ncols, dtype, n):  # pragma: no cover
    rows = np.empty(n, dtype=np.uint64)
    cols = np.empty(n, dtype=np.uint64)
    vals = np.empty(n, dtype=dtype)
    k = 0
    for i in range(nrows):
        for j in range(ncols):
            rows[k] = i
            cols[k] = j
            vals[k] = values[i * ncols + j]
            k += 1
            if k == n:
                return rows, cols, vals
    return rows, cols, vals


@njit
def _head_matrix_bitmap(bitmap, values, nrows, ncols, dtype, n):  # pragma: no cover
    rows = np.empty(n, dtype=np.uint64)
    cols = np.empty(n, dtype=np.uint64)
    vals = np.empty(n, dtype=dtype)
    k = 0
    for i in range(nrows):
        for j in range(ncols):
            if bitmap[i * ncols + j]:
                rows[k] = i
                cols[k] = j
                vals[k] = values[i * ncols + j]
                k += 1
                if k == n:
                    return rows, cols, vals
    return rows, cols, vals


@njit
def _head_csr_rows(indptr, n):  # pragma: no cover
    rows = np.empty(n, dtype=np.uint64)
    idx = 0
    index = 0
    for row in range(indptr.size - 1):
        next_idx = indptr[row + 1]
        while next_idx != idx:
            rows[index] = row
            index += 1
            if index == n:
                return rows
            idx += 1
    return rows


@njit
def _head_hypercsr_rows(indptr, rows, n):  # pragma: no cover
    rv = np.empty(n, dtype=np.uint64)
    idx = 0
    index = 0
    for ptr in range(indptr.size - 1):
        next_idx = indptr[ptr + 1]
        row = rows[ptr]
        while next_idx != idx:
            rv[index] = row
            index += 1
            if index == n:
                return rv
            idx += 1
    return rv


def head(matrix, n=10, *, sort=False, dtype=None):
    """Like ``matrix.to_values()``, but only returns the first n elements.

    If sort is True, then the results will be sorted as appropriate for the internal format,
    otherwise the order of the result is not guaranteed.  Specifically, row-oriented formats
    (fullr, bitmapr, csr, hypercsr) will sort by row index first, then by column index.
    Column-oriented formats, naturally, will sort by column index first, then by row index.
    Formats fullr, fullc, bitmapr, and bitmapc should always return in sorted order.

    This changes ``matrix.gb_obj``, so care should be taken when using multiple threads.
    """
    if dtype is None:
        dtype = matrix.dtype
    else:
        dtype = lookup_dtype(dtype)
    n = min(n, matrix._nvals)
    if n == 0:
        return (
            np.empty(0, dtype=np.uint64),
            np.empty(0, dtype=np.uint64),
            np.empty(0, dtype=dtype.np_type),
        )
    d = matrix.ss.export(raw=True, give_ownership=True, sort=sort)
    try:
        fmt = d["format"]
        if fmt == "fullr":
            rows, cols, vals = _head_matrix_full(
                d["values"], d["nrows"], d["ncols"], dtype.np_type, n
            )
        elif fmt == "fullc":
            cols, rows, vals = _head_matrix_full(
                d["values"], d["ncols"], d["nrows"], dtype.np_type, n
            )
        elif fmt == "bitmapr":
            rows, cols, vals = _head_matrix_bitmap(
                d["bitmap"], d["values"], d["nrows"], d["ncols"], dtype.np_type, n
            )
        elif fmt == "bitmapc":
            cols, rows, vals = _head_matrix_bitmap(
                d["bitmap"], d["values"], d["ncols"], d["nrows"], dtype.np_type, n
            )
        elif fmt == "csr":
            vals = d["values"][:n].astype(dtype.np_type)
            cols = d["col_indices"][:n].copy()
            rows = _head_csr_rows(d["indptr"], n)
        elif fmt == "csc":
            vals = d["values"][:n].astype(dtype.np_type)
            rows = d["row_indices"][:n].copy()
            cols = _head_csr_rows(d["indptr"], n)
        elif fmt == "hypercsr":
            vals = d["values"][:n].astype(dtype.np_type)
            cols = d["col_indices"][:n].copy()
            rows = _head_hypercsr_rows(d["indptr"], d["rows"], n)
        elif fmt == "hypercsc":
            vals = d["values"][:n].astype(dtype.np_type)
            rows = d["row_indices"][:n].copy()
            cols = _head_hypercsr_rows(d["indptr"], d["cols"], n)
        else:  # pragma: no cover
            raise RuntimeError(f"Invalid format: {fmt}")
    finally:
        rebuilt = ss.import_any(take_ownership=True, name="", **d)
        # We need to set rebuilt.gb_obj to NULL so it doesn't get deleted early, so might
        # as well do a swap, b/c matrix.gb_obj is already "destroyed" from the export.
        matrix.gb_obj, rebuilt.gb_obj = rebuilt.gb_obj, matrix.gb_obj  # pragma: no branch
    return rows, cols, vals


def normalize_chunks(chunks, shape):
    """Normalize chunks argument for use by `Matrix.ss.split`.

    Examples
    --------
    >>> shape = (10, 20)
    >>> normalize_chunks(10, shape)
    [(10,), (10, 10)]
    >>> normalize_chunks((10, 10), shape)
    [(10,), (10, 10)]
    >>> normalize_chunks([None, (5, 15)], shape)
    [(10,), (5, 15)]
    >>> normalize_chunks((5, (5, None)), shape)
    [(5, 5), (5, 15)]
    """
    if isinstance(chunks, (list, tuple)):
        pass
    elif isinstance(chunks, Number):
        chunks = (chunks, chunks)
    elif isinstance(chunks, np.ndarray):
        chunks = chunks.tolist()
    else:
        raise TypeError(
            f"chunks argument must be a list, tuple, or numpy array; got: {type(chunks)}"
        )
    if len(chunks) != 2:
        raise ValueError("chunks argument must be of length 2 (one for each dimension of a Matrix)")
    chunksizes = []
    for size, chunk in zip(shape, chunks):
        if chunk is None:
            cur_chunks = [size]
        elif isinstance(chunk, Integral) or isinstance(chunk, float) and chunk.is_integer():
            chunk = int(chunk)
            if chunk < 0:
                raise ValueError(f"Chunksize must be greater than 0; got: {chunk}")
            div, mod = divmod(size, chunk)
            cur_chunks = [chunk] * div
            if mod:
                cur_chunks.append(mod)
        elif isinstance(chunk, (list, tuple)):
            cur_chunks = []
            none_index = None
            for c in chunk:
                if isinstance(c, Integral) or isinstance(c, float) and c.is_integer():
                    c = int(c)
                    if c < 0:
                        raise ValueError(f"Chunksize must be greater than 0; got: {c}")
                elif c is None:
                    if none_index is not None:
                        raise TypeError(
                            'None value in chunks for "the rest" can only appear once per dimension'
                        )
                    none_index = len(cur_chunks)
                    c = 0
                else:
                    raise TypeError(
                        "Bad type for element in chunks; expected int or None, but got: "
                        f"{type(chunks)}"
                    )
                cur_chunks.append(c)
            if none_index is not None:
                fill = size - sum(cur_chunks)
                if fill < 0:
                    raise ValueError(
                        "Chunks are too large; None value in chunks would need to be negative "
                        "to match size of input"
                    )
                cur_chunks[none_index] = fill
        elif isinstance(chunk, np.ndarray):
            if not np.issubdtype(chunk.dtype, np.integer):
                raise TypeError(f"numpy array for chunks must be integer dtype; got {chunk.dtype}")
            if chunk.ndim != 1:
                raise TypeError(
                    f"numpy array for chunks must be 1-dimension; got ndim={chunk.ndim}"
                )
            if (chunk < 0).any():
                raise ValueError(f"Chunksize must be greater than 0; got: {chunk[chunk < 0]}")
            cur_chunks = chunk.tolist()
        else:
            raise TypeError(
                "Chunks for a dimension must be an integer, a list or tuple of integers, or None."
                f"  Got: {type(chunk)}"
            )
        chunksizes.append(cur_chunks)
    return chunksizes


def _concat_mn(tiles):
    """Argument checking for `Matrix.ss.concat` and returns number of tiles in each dimension"""
    from ..matrix import Matrix

    if not isinstance(tiles, (list, tuple)):
        raise TypeError(f"tiles argument must be list or tuple; got: {type(tiles)}")
    if not tiles:
        raise ValueError("tiles argument must not be empty")
    m = len(tiles)
    n = None
    for row_tiles in tiles:
        if not isinstance(row_tiles, (list, tuple)):
            raise TypeError(f"tiles must be lists or tuples; got: {type(row_tiles)}")
        if n is None:
            n = len(row_tiles)
            if n == 0:
                raise ValueError("tiles must not be empty")
        elif len(row_tiles) != n:
            raise ValueError(
                f"tiles must all be the same length; got tiles of length {n} and "
                f"{len(row_tiles)}"
            )
        for tile in row_tiles:
            if type(tile) is not Matrix:
                raise TypeError(
                    f"Bad tile type in concat.  Each tile must be a Matrix; got {type(tile)}"
                )
    return m, n


class MatrixArray:
    __slots__ = "_carg", "_exc_arg", "name"

    def __init__(self, matrices, exc_arg=None, *, name):
        self._carg = matrices
        self._exc_arg = exc_arg
        self.name = name
        record_raw(f"GrB_Matrix {name}[{len(matrices)}];")


class ss:
    __slots__ = "_parent"

    def __init__(self, parent):
        self._parent = parent

    @property
    def format(self):
        # Determine current format
        parent = self._parent
        format_ptr = ffi_new("GxB_Option_Field*")
        sparsity_ptr = ffi_new("GxB_Option_Field*")
        check_status(
            lib.GxB_Matrix_Option_get(parent._carg, lib.GxB_FORMAT, format_ptr),
            parent,
        )
        check_status(
            lib.GxB_Matrix_Option_get(parent._carg, lib.GxB_SPARSITY_STATUS, sparsity_ptr),
            parent,
        )
        sparsity_status = sparsity_ptr[0]
        if sparsity_status == lib.GxB_HYPERSPARSE:
            format = "hypercs"
        elif sparsity_status == lib.GxB_SPARSE:
            format = "cs"
        elif sparsity_status == lib.GxB_BITMAP:
            format = "bitmap"
        elif sparsity_status == lib.GxB_FULL:
            format = "full"
        else:  # pragma: no cover
            raise NotImplementedError(f"Unknown sparsity status: {sparsity_status}")
        if format_ptr[0] == lib.GxB_BY_COL:
            format = f"{format}c"
        else:
            format = f"{format}r"
        return format

    def diag(self, vector, k=0):
        """
        GxB_Matrix_diag

        Construct a diagonal Matrix from the given vector.
        Existing entries in the Matrix are discarded.

        Parameters
        ----------
        vector : Vector
            Create a diagonal from this Vector.
        k : int, default 0
            Diagonal in question.  Use `k>0` for diagonals above the main diagonal,
            and `k<0` for diagonals below the main diagonal.

        See Also
        --------
        grblas.ss.diag
        Vector.ss.diag

        """
        self._parent._expect_type(vector, gb.Vector, within="ss.diag", argname="vector")
        call("GxB_Matrix_diag", [self._parent, vector, _CScalar(k, dtype=INT64), None])

    def split(self, chunks, *, name=None):
        """
        GxB_Matrix_split

        Split a Matrix into a 2D array of sub-matrices according to `chunks`.

        This performs the opposite operation as ``concat``.

        `chunks` is short for "chunksizes" and indicates the chunk sizes for each dimension.
        `chunks` may be a single integer, or a length 2 tuple or list.  Example chunks:

        - ``chunks=10``
            - Split each dimension into chunks of size 10 (the last chunk may be smaller).
        - ``chunks=(10, 20)``
            - Split rows into chunks of size 10 and columns into chunks of size 20.
        - ``chunks=(None, [5, 10])``
            - Don't split rows into chunks, and split columns into two chunks of size 5 and 10.
        ` ``chunks=(10, [20, None])``
            - Split columns into two chunks of size 20 and ``ncols - 20``

        See Also
        --------
        Matrix.ss.concat
        grblas.ss.concat

        """
        from ..matrix import Matrix

        tile_nrows, tile_ncols = normalize_chunks(chunks, self._parent.shape)
        m = len(tile_nrows)
        n = len(tile_ncols)
        tiles = ffi.new("GrB_Matrix[]", m * n)
        call(
            "GxB_Matrix_split",
            [
                MatrixArray(tiles, self._parent, name="tiles"),
                _CScalar(m),
                _CScalar(n),
                _CArray(tile_nrows),
                _CArray(tile_ncols),
                self._parent,
                None,
            ],
        )
        rv = []
        dtype = self._parent.dtype
        if name is None:
            name = self._parent.name
        index = 0
        for i, nrows in enumerate(tile_nrows):
            cur = []
            for j, ncols in enumerate(tile_ncols):
                # Copy to a new handle so we can free `tiles`
                new_matrix = ffi.new("GrB_Matrix*")
                new_matrix[0] = tiles[index]
                tile = Matrix(new_matrix, dtype, name=f"{name}_{i}x{j}")
                tile._nrows = nrows
                tile._ncols = ncols
                cur.append(tile)
                index += 1
            rv.append(cur)
        return rv

    def _concat(self, tiles, m, n):
        ctiles = ffi.new("GrB_Matrix[]", m * n)
        index = 0
        for row_tiles in tiles:
            for tile in row_tiles:
                ctiles[index] = tile.gb_obj[0]
                index += 1
        call(
            "GxB_Matrix_concat",
            [
                self._parent,
                MatrixArray(ctiles, name="tiles"),
                _CScalar(m),
                _CScalar(n),
                None,
            ],
        )

    def concat(self, tiles):
        """
        GxB_Matrix_concat

        Concatenate a 2D list of Matrix objects into the current Matrix.
        Any existing values in the current Matrix will be discarded.
        To concatenate into a new Matrix, use `grblas.ss.concat`.

        This performs the opposite operation as ``split``.

        See Also
        --------
        Matrix.ss.split
        grblas.ss.concat

        """
        m, n = _concat_mn(tiles)
        self._concat(tiles, m, n)

    def export(self, format=None, *, sort=False, give_ownership=False, raw=False):
        """
        GxB_Matrix_export_xxx

        Parameters
        ----------
        format : str, optional
            If `format` is not specified, this method exports in the currently stored format.
            To control the export format, set `format` to one of:
                - "csr"
                - "csc"
                - "hypercsr"
                - "hypercsc"
                - "bitmapr"
                - "bitmapc"
                - "fullr"
                - "fullc"
        sort : bool, default False
            Whether to sort indices if the format is "csr", "csc", "hypercsr", or "hypercsc".
        give_ownership : bool, default False
            Perform a zero-copy data transfer to Python if possible.  This gives ownership of
            the underlying memory buffers to Numpy.
            ** If True, this nullifies the current object, which should no longer be used! **
        raw : bool, default False
            If True, always return 1d arrays the same size as returned by SuiteSparse.
            If False, arrays may be trimmed to be the expected size, and 2d arrays are
            returned when format is "bitmapr", "bitmapc", "fullr", or "fullc".
            It may make sense to choose ``raw=True`` if one wants to use the data to perform
            a zero-copy import back to SuiteSparse.

        Returns
        -------
        dict; keys depend on `format` and `raw` arguments (see below).

        See Also
        --------
        Matrix.to_values
        Matrix.ss.import_any

        Return values
            - Note: for ``raw=True``, arrays may be larger than specified.
            - "csr" format
                - indptr : ndarray(dtype=uint64, ndim=1, size=nrows + 1)
                - col_indices : ndarray(dtype=uint64, ndim=1, size=nvals)
                - values : ndarray(ndim=1, size=nvals)
                - sorted_index : bool
                    - True if the values in "col_indices" are sorted
                - nrows : int
                - ncols : int
            - "csc" format
                - indptr : ndarray(dtype=uint64, ndim=1, size=ncols + 1)
                - row_indices : ndarray(dtype=uint64, ndim=1, size=nvals)
                - values : ndarray(ndim=1, size=nvals)
                - sorted_index : bool
                    - True if the values in "row_indices" are sorted
                - nrows : int
                - ncols : int
            - "hypercsr" format
                - indptr : ndarray(dtype=uint64, ndim=1, size=nvec + 1)
                - rows : ndarray(dtype=uint64, ndim=1, size=nvec)
                - col_indices : ndarray(dtype=uint64, ndim=1, size=nvals)
                - values : ndarray(ndim=1, size=nvals)
                - sorted_index : bool
                    - True if the values in "col_indices" are sorted
                - nrows : int
                - ncols : int
                - nvec : int, only present if raw == True
                    - The number of rows present in the data structure
            - "hypercsc" format
                - indptr : ndarray(dtype=uint64, ndim=1, size=nvec + 1)
                - cols : ndarray(dtype=uint64, ndim=1, size=nvec)
                - row_indices : ndarray(dtype=uint64, ndim=1, size=nvals)
                - values : ndarray(ndim=1, size=nvals)
                - sorted_index : bool
                    - True if the values in "row_indices" are sorted
                - nrows : int
                - ncols : int
                - nvec : int, only present if raw == True
                    - The number of cols present in the data structure
            - "bitmapr" format
                - ``raw=False``
                    - bitmap : ndarray(dtype=bool8, ndim=2, shape=(nrows, ncols), order="C")
                    - values : ndarray(ndim=2, shape=(nrows, ncols), order="C")
                        - Elements where bitmap is False are undefined
                    - nvals : int
                        - The number of True elements in the bitmap
                - ``raw=True``
                    - bitmap : ndarray(dtype=bool8, ndim=1, size=nrows * ncols)
                        - Stored row-oriented
                    - values : ndarray(ndim=1, size=nrows * ncols)
                        - Elements where bitmap is False are undefined
                        - Stored row-oriented
                    - nvals : int
                        - The number of True elements in the bitmap
                    - nrows : int
                    - ncols : int
            - "bitmapc" format
                - ``raw=False``
                    - bitmap : ndarray(dtype=bool8, ndim=2, shape=(nrows, ncols), order="F")
                    - values : ndarray(ndim=2, shape=(nrows, ncols), order="F")
                        - Elements where bitmap is False are undefined
                    - nvals : int
                        - The number of True elements in the bitmap
                - ``raw=True``
                    - bitmap : ndarray(dtype=bool8, ndim=1, size=nrows * ncols)
                        - Stored column-oriented
                    - values : ndarray(ndim=1, size=nrows * ncols)
                        - Elements where bitmap is False are undefined
                        - Stored column-oriented
                    - nvals : int
                        - The number of True elements in the bitmap
                    - nrows : int
                    - ncols : int
            - "fullr" format
                - ``raw=False``
                    - values : ndarray(ndim=2, shape=(nrows, ncols), order="C")
                - ``raw=True``
                    - values : ndarray(ndim=1, size=nrows * ncols)
                        - Stored row-oriented
                    - nrows : int
                    - ncols : int
            - "fullc" format
                - ``raw=False``
                    - values : ndarray(ndim=2, shape=(nrows, ncols), order="F")
                - ``raw=True``
                    - values : ndarray(ndim=1, size=nrows * ncols)
                        - Stored row-oriented
                    - nrows : int
                    - ncols : int

        Examples
        --------
        Simple usage:

        >>> pieces = A.ss.export()
        >>> A2 = Matrix.ss.import_any(**pieces)

        """
        if give_ownership:
            parent = self._parent
        else:
            parent = self._parent.dup(name="M_export")
        dtype = np.dtype(parent.dtype.np_type)
        index_dtype = np.dtype(np.uint64)

        if format is None:
            format = self.format
        else:
            format = format.lower()

        mhandle = ffi_new("GrB_Matrix*", parent._carg)
        type_ = ffi_new("GrB_Type*")
        nrows = ffi_new("GrB_Index*")
        ncols = ffi_new("GrB_Index*")
        Ap = ffi_new("GrB_Index**")
        Ax = ffi_new("void**")
        Ap_size = ffi_new("GrB_Index*")
        Ax_size = ffi_new("GrB_Index*")
        if sort:
            jumbled = ffi.NULL
        else:
            jumbled = ffi_new("bool*")
        is_uniform = ffi_new("bool*")
        nvals = parent._nvals
        if format == "csr":
            Aj = ffi_new("GrB_Index**")
            Aj_size = ffi_new("GrB_Index*")
            check_status(
                lib.GxB_Matrix_export_CSR(
                    mhandle,
                    type_,
                    nrows,
                    ncols,
                    Ap,
                    Aj,
                    Ax,
                    Ap_size,
                    Aj_size,
                    Ax_size,
                    is_uniform,
                    jumbled,
                    ffi.NULL,
                ),
                parent,
            )
            indptr = claim_buffer(ffi, Ap[0], Ap_size[0] // index_dtype.itemsize, index_dtype)
            col_indices = claim_buffer(ffi, Aj[0], Aj_size[0] // index_dtype.itemsize, index_dtype)
            values = claim_buffer(ffi, Ax[0], Ax_size[0] // dtype.itemsize, dtype)
            if not raw:
                if indptr.size > nrows[0] + 1:  # pragma: no cover
                    indptr = indptr[: nrows[0] + 1]
                if col_indices.size > nvals:  # pragma: no cover
                    col_indices = col_indices[:nvals]
                if values.size > nvals:  # pragma: no cover
                    values = values[:nvals]
            # Note: nvals is also at `indptr[nrows]`
            rv = {
                "indptr": indptr,
                "col_indices": col_indices,
                "sorted_index": True if sort else not jumbled[0],
                "nrows": nrows[0],
                "ncols": ncols[0],
            }
        elif format == "csc":
            Ai = ffi_new("GrB_Index**")
            Ai_size = ffi_new("GrB_Index*")
            check_status(
                lib.GxB_Matrix_export_CSC(
                    mhandle,
                    type_,
                    nrows,
                    ncols,
                    Ap,
                    Ai,
                    Ax,
                    Ap_size,
                    Ai_size,
                    Ax_size,
                    is_uniform,
                    jumbled,
                    ffi.NULL,
                ),
                parent,
            )
            indptr = claim_buffer(ffi, Ap[0], Ap_size[0] // index_dtype.itemsize, index_dtype)
            row_indices = claim_buffer(ffi, Ai[0], Ai_size[0] // index_dtype.itemsize, index_dtype)
            values = claim_buffer(ffi, Ax[0], Ax_size[0] // dtype.itemsize, dtype)
            if not raw:
                if indptr.size > ncols[0] + 1:  # pragma: no cover
                    indptr = indptr[: ncols[0] + 1]
                if row_indices.size > nvals:  # pragma: no cover
                    row_indices = row_indices[:nvals]
                if values.size > nvals:  # pragma: no cover
                    values = values[:nvals]
            # Note: nvals is also at `indptr[ncols]`
            rv = {
                "indptr": indptr,
                "row_indices": row_indices,
                "sorted_index": True if sort else not jumbled[0],
                "nrows": nrows[0],
                "ncols": ncols[0],
            }
        elif format == "hypercsr":
            nvec = ffi_new("GrB_Index*")
            Ah = ffi_new("GrB_Index**")
            Aj = ffi_new("GrB_Index**")
            Ah_size = ffi_new("GrB_Index*")
            Aj_size = ffi_new("GrB_Index*")
            check_status(
                lib.GxB_Matrix_export_HyperCSR(
                    mhandle,
                    type_,
                    nrows,
                    ncols,
                    Ap,
                    Ah,
                    Aj,
                    Ax,
                    Ap_size,
                    Ah_size,
                    Aj_size,
                    Ax_size,
                    is_uniform,
                    nvec,
                    jumbled,
                    ffi.NULL,
                ),
                parent,
            )
            indptr = claim_buffer(ffi, Ap[0], Ap_size[0] // index_dtype.itemsize, index_dtype)
            rows = claim_buffer(ffi, Ah[0], Ah_size[0] // index_dtype.itemsize, index_dtype)
            col_indices = claim_buffer(ffi, Aj[0], Aj_size[0] // index_dtype.itemsize, index_dtype)
            values = claim_buffer(ffi, Ax[0], Ax_size[0] // dtype.itemsize, dtype)
            nvec = nvec[0]
            if not raw:
                if indptr.size > nvec + 1:  # pragma: no cover
                    indptr = indptr[: nvec + 1]
                if rows.size > nvec:  # pragma: no cover
                    rows = rows[:nvec]
                if col_indices.size > nvals:  # pragma: no cover
                    col_indices = col_indices[:nvals]
                if values.size > nvals:  # pragma: no cover
                    values = values[:nvals]
            # Note: nvals is also at `indptr[nvec]`
            rv = {
                "indptr": indptr,
                "rows": rows,
                "col_indices": col_indices,
                "sorted_index": True if sort else not jumbled[0],
                "nrows": nrows[0],
                "ncols": ncols[0],
            }
            if raw:
                rv["nvec"] = nvec
        elif format == "hypercsc":
            nvec = ffi_new("GrB_Index*")
            Ah = ffi_new("GrB_Index**")
            Ai = ffi_new("GrB_Index**")
            Ah_size = ffi_new("GrB_Index*")
            Ai_size = ffi_new("GrB_Index*")
            check_status(
                lib.GxB_Matrix_export_HyperCSC(
                    mhandle,
                    type_,
                    nrows,
                    ncols,
                    Ap,
                    Ah,
                    Ai,
                    Ax,
                    Ap_size,
                    Ah_size,
                    Ai_size,
                    Ax_size,
                    is_uniform,
                    nvec,
                    jumbled,
                    ffi.NULL,
                ),
                parent,
            )
            indptr = claim_buffer(ffi, Ap[0], Ap_size[0] // index_dtype.itemsize, index_dtype)
            cols = claim_buffer(ffi, Ah[0], Ah_size[0] // index_dtype.itemsize, index_dtype)
            row_indices = claim_buffer(ffi, Ai[0], Ai_size[0] // index_dtype.itemsize, index_dtype)
            values = claim_buffer(ffi, Ax[0], Ax_size[0] // dtype.itemsize, dtype)
            nvec = nvec[0]
            if not raw:
                if indptr.size > nvec + 1:  # pragma: no cover
                    indptr = indptr[: nvec + 1]
                if cols.size > nvec:  # pragma: no cover
                    cols = cols[:nvec]
                if row_indices.size > nvals:  # pragma: no cover
                    row_indices = row_indices[:nvals]
                if values.size > nvals:  # pragma: no cover
                    values = values[:nvals]
            # Note: nvals is also at `indptr[nvec]`
            rv = {
                "indptr": indptr,
                "cols": cols,
                "row_indices": row_indices,
                "sorted_index": True if sort else not jumbled[0],
                "nrows": nrows[0],
                "ncols": ncols[0],
            }
            if raw:
                rv["nvec"] = nvec
        elif format == "bitmapr" or format == "bitmapc":
            if format == "bitmapr":
                cfunc = lib.GxB_Matrix_export_BitmapR
            else:
                cfunc = lib.GxB_Matrix_export_BitmapC
            Ab = ffi_new("int8_t**")
            Ab_size = ffi_new("GrB_Index*")
            nvals_ = ffi_new("GrB_Index*")
            check_status(
                cfunc(
                    mhandle,
                    type_,
                    nrows,
                    ncols,
                    Ab,
                    Ax,
                    Ab_size,
                    Ax_size,
                    is_uniform,
                    nvals_,
                    ffi.NULL,
                ),
                parent,
            )
            bool_dtype = np.dtype(np.bool8)
            if raw:
                bitmap = claim_buffer(ffi, Ab[0], Ab_size[0] // bool_dtype.itemsize, bool_dtype)
                values = claim_buffer(ffi, Ax[0], Ax_size[0] // dtype.itemsize, dtype)
            else:
                is_c_order = format == "bitmapr"
                bitmap = claim_buffer_2d(
                    ffi,
                    Ab[0],
                    Ab_size[0] // bool_dtype.itemsize,
                    nrows[0],
                    ncols[0],
                    bool_dtype,
                    is_c_order,
                )
                values = claim_buffer_2d(
                    ffi, Ax[0], Ax_size[0] // dtype.itemsize, nrows[0], ncols[0], dtype, is_c_order
                )
            rv = {"bitmap": bitmap, "nvals": nvals_[0]}
            if raw:
                rv["nrows"] = nrows[0]
                rv["ncols"] = ncols[0]
        elif format == "fullr" or format == "fullc":
            if format == "fullr":
                cfunc = lib.GxB_Matrix_export_FullR
            else:
                cfunc = lib.GxB_Matrix_export_FullC
            check_status(
                cfunc(
                    mhandle,
                    type_,
                    nrows,
                    ncols,
                    Ax,
                    Ax_size,
                    is_uniform,
                    ffi.NULL,
                ),
                parent,
            )
            if raw:
                values = claim_buffer(ffi, Ax[0], Ax_size[0] // dtype.itemsize, dtype)
                rv = {"nrows": nrows[0], "ncols": ncols[0]}
            else:
                is_c_order = format == "fullr"
                values = claim_buffer_2d(
                    ffi, Ax[0], Ax_size[0] // dtype.itemsize, nrows[0], ncols[0], dtype, is_c_order
                )
                rv = {}
        else:
            raise ValueError(f"Invalid format: {format}")

        if is_uniform[0]:
            rv["is_uniform"] = True
        rv["format"] = format
        rv["values"] = values
        parent.gb_obj = ffi.NULL
        return rv

    @classmethod
    def import_csr(
        cls,
        *,
        nrows,
        ncols,
        indptr,
        values,
        col_indices,
        is_uniform=False,
        sorted_index=False,
        take_ownership=False,
        dtype=None,
        format=None,
        name=None,
    ):
        """
        GxB_Matrix_import_CSR

        Create a new Matrix from standard CSR format.

        Parameters
        ----------
        nrows : int
        ncols : int
        indptr : array-like
        values : array-like
        col_indices : array-like
        is_uniform : bool, default False
            Not yet supported.
        sorted_index : bool, default False
            Indicate whether the values in "col_indices" are sorted.
        take_ownership : bool, default False
            If True, perform a zero-copy data transfer from input numpy arrays
            to GraphBLAS if possible.  To give ownership of the underlying
            memory buffers to GraphBLAS, the arrays must:
                - be C contiguous
                - have the correct dtype (uint64 for indptr and col_indices)
                - own its own data
                - be writeable
            If all of these conditions are not met, then the data will be
            copied and the original array will be unmodified.  If zero copy
            to GraphBLAS is successful, then the array will be mofied to be
            read-only and will no longer own the data.
        dtype : dtype, optional
            dtype of the new Matrix.
            If not specified, this will be inferred from `values`.
        format : str, optional
            Must be "csr" or None.  This is included to be compatible with
            the dict returned from exporting.
        name : str, optional
            Name of the new Matrix.

        Returns
        -------
        Matrix
        """
        if format is not None and format.lower() != "csr":
            raise ValueError(f"Invalid format: {format!r}.  Must be None or 'csr'.")
        copy = not take_ownership
        indptr = ints_to_numpy_buffer(
            indptr, np.uint64, copy=copy, ownable=True, name="index pointers"
        )
        col_indices = ints_to_numpy_buffer(
            col_indices, np.uint64, copy=copy, ownable=True, name="column indices"
        )
        values, dtype = values_to_numpy_buffer(values, dtype, copy=copy, ownable=True)
        if col_indices is values:
            values = np.copy(values)
        mhandle = ffi_new("GrB_Matrix*")
        Ap = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(indptr)))
        Aj = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(col_indices)))
        Ax = ffi_new("void**", ffi.cast("void**", ffi.from_buffer(values)))
        check_status_carg(
            lib.GxB_Matrix_import_CSR(
                mhandle,
                dtype._carg,
                nrows,
                ncols,
                Ap,
                Aj,
                Ax,
                indptr.nbytes,
                col_indices.nbytes,
                values.nbytes,
                is_uniform,
                not sorted_index,
                ffi.NULL,
            ),
            "Matrix",
            mhandle[0],
        )
        rv = gb.Matrix(mhandle, dtype, name=name)
        rv._nrows = nrows
        rv._ncols = ncols
        unclaim_buffer(indptr)
        unclaim_buffer(col_indices)
        unclaim_buffer(values)
        return rv

    @classmethod
    def import_csc(
        cls,
        *,
        nrows,
        ncols,
        indptr,
        values,
        row_indices,
        is_uniform=False,
        sorted_index=False,
        take_ownership=False,
        dtype=None,
        format=None,
        name=None,
    ):
        """
        GxB_Matrix_import_CSC

        Create a new Matrix from standard CSC format.

        Parameters
        ----------
        nrows : int
        ncols : int
        indptr : array-like
        values : array-like
        row_indices : array-like
        is_uniform : bool, default False
            Not yet supported.
        sorted_index : bool, default False
            Indicate whether the values in "row_indices" are sorted.
        take_ownership : bool, default False
            If True, perform a zero-copy data transfer from input numpy arrays
            to GraphBLAS if possible.  To give ownership of the underlying
            memory buffers to GraphBLAS, the arrays must:
                - be C contiguous
                - have the correct dtype (uint64 for indptr and row_indices)
                - own its own data
                - be writeable
            If all of these conditions are not met, then the data will be
            copied and the original array will be unmodified.  If zero copy
            to GraphBLAS is successful, then the array will be mofied to be
            read-only and will no longer own the data.
        dtype : dtype, optional
            dtype of the new Matrix.
            If not specified, this will be inferred from `values`.
        format : str, optional
            Must be "csc" or None.  This is included to be compatible with
            the dict returned from exporting.
        name : str, optional
            Name of the new Matrix.

        Returns
        -------
        Matrix
        """
        if format is not None and format.lower() != "csc":
            raise ValueError(f"Invalid format: {format!r}  Must be None or 'csc'.")
        copy = not take_ownership
        indptr = ints_to_numpy_buffer(
            indptr, np.uint64, copy=copy, ownable=True, name="index pointers"
        )
        row_indices = ints_to_numpy_buffer(
            row_indices, np.uint64, copy=copy, ownable=True, name="row indices"
        )
        values, dtype = values_to_numpy_buffer(values, dtype, copy=copy, ownable=True)
        if row_indices is values:
            values = np.copy(values)
        mhandle = ffi_new("GrB_Matrix*")
        Ap = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(indptr)))
        Ai = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(row_indices)))
        Ax = ffi_new("void**", ffi.cast("void**", ffi.from_buffer(values)))
        check_status_carg(
            lib.GxB_Matrix_import_CSC(
                mhandle,
                dtype._carg,
                nrows,
                ncols,
                Ap,
                Ai,
                Ax,
                indptr.nbytes,
                row_indices.nbytes,
                values.nbytes,
                is_uniform,
                not sorted_index,
                ffi.NULL,
            ),
            "Matrix",
            mhandle[0],
        )
        rv = gb.Matrix(mhandle, dtype, name=name)
        rv._nrows = nrows
        rv._ncols = ncols
        unclaim_buffer(indptr)
        unclaim_buffer(row_indices)
        unclaim_buffer(values)
        return rv

    @classmethod
    def import_hypercsr(
        cls,
        *,
        nrows,
        ncols,
        rows,
        indptr,
        values,
        col_indices,
        nvec=None,
        is_uniform=False,
        sorted_index=False,
        take_ownership=False,
        dtype=None,
        format=None,
        name=None,
    ):
        """
        GxB_Matrix_import_HyperCSR

        Create a new Matrix from standard HyperCSR format.

        Parameters
        ----------
        nrows : int
        ncols : int
        rows : array-like
        indptr : array-like
        values : array-like
        col_indices : array-like
        nvec : int, optional
            The number of elements in "rows" to use.
            If not specified, will be set to ``len(rows)``.
        is_uniform : bool, default False
            Not yet supported.
        sorted_index : bool, default False
            Indicate whether the values in "col_indices" are sorted.
        take_ownership : bool, default False
            If True, perform a zero-copy data transfer from input numpy arrays
            to GraphBLAS if possible.  To give ownership of the underlying
            memory buffers to GraphBLAS, the arrays must:
                - be C contiguous
                - have the correct dtype (uint64 for rows, indptr, col_indices)
                - own its own data
                - be writeable
            If all of these conditions are not met, then the data will be
            copied and the original array will be unmodified.  If zero copy
            to GraphBLAS is successful, then the array will be mofied to be
            read-only and will no longer own the data.
        dtype : dtype, optional
            dtype of the new Matrix.
            If not specified, this will be inferred from `values`.
        format : str, optional
            Must be "hypercsr" or None.  This is included to be compatible with
            the dict returned from exporting.
        name : str, optional
            Name of the new Matrix.

        Returns
        -------
        Matrix
        """
        if format is not None and format.lower() != "hypercsr":
            raise ValueError(f"Invalid format: {format!r}  Must be None or 'hypercsr'.")
        copy = not take_ownership
        indptr = ints_to_numpy_buffer(
            indptr, np.uint64, copy=copy, ownable=True, name="index pointers"
        )
        rows = ints_to_numpy_buffer(rows, np.uint64, copy=copy, ownable=True, name="rows")
        col_indices = ints_to_numpy_buffer(
            col_indices, np.uint64, copy=copy, ownable=True, name="column indices"
        )
        values, dtype = values_to_numpy_buffer(values, dtype, copy=copy, ownable=True)
        if col_indices is values:
            values = np.copy(values)
        mhandle = ffi_new("GrB_Matrix*")
        Ap = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(indptr)))
        Ah = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(rows)))
        Aj = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(col_indices)))
        Ax = ffi_new("void**", ffi.cast("void**", ffi.from_buffer(values)))
        if nvec is None:
            nvec = rows.size
        check_status_carg(
            lib.GxB_Matrix_import_HyperCSR(
                mhandle,
                dtype._carg,
                nrows,
                ncols,
                Ap,
                Ah,
                Aj,
                Ax,
                indptr.nbytes,
                rows.nbytes,
                col_indices.nbytes,
                values.nbytes,
                is_uniform,
                nvec,
                not sorted_index,
                ffi.NULL,
            ),
            "Matrix",
            mhandle[0],
        )
        rv = gb.Matrix(mhandle, dtype, name=name)
        rv._nrows = nrows
        rv._ncols = ncols
        unclaim_buffer(indptr)
        unclaim_buffer(rows)
        unclaim_buffer(col_indices)
        unclaim_buffer(values)
        return rv

    @classmethod
    def import_hypercsc(
        cls,
        *,
        nrows,
        ncols,
        cols,
        indptr,
        values,
        row_indices,
        nvec=None,
        is_uniform=False,
        sorted_index=False,
        take_ownership=False,
        dtype=None,
        format=None,
        name=None,
    ):
        """
        GxB_Matrix_import_HyperCSC

        Create a new Matrix from standard HyperCSC format.

        Parameters
        ----------
        nrows : int
        ncols : int
        indptr : array-like
        values : array-like
        row_indices : array-like
        nvec : int, optional
            The number of elements in "cols" to use.
            If not specified, will be set to ``len(cols)``.
        is_uniform : bool, default False
            Not yet supported.
        sorted_index : bool, default False
            Indicate whether the values in "row_indices" are sorted.
        take_ownership : bool, default False
            If True, perform a zero-copy data transfer from input numpy arrays
            to GraphBLAS if possible.  To give ownership of the underlying
            memory buffers to GraphBLAS, the arrays must:
                - be C contiguous
                - have the correct dtype (uint64 for indptr and row_indices)
                - own its own data
                - be writeable
            If all of these conditions are not met, then the data will be
            copied and the original array will be unmodified.  If zero copy
            to GraphBLAS is successful, then the array will be mofied to be
            read-only and will no longer own the data.
        dtype : dtype, optional
            dtype of the new Matrix.
            If not specified, this will be inferred from `values`.
        format : str, optional
            Must be "hypercsc" or None.  This is included to be compatible with
            the dict returned from exporting.
        name : str, optional
            Name of the new Matrix.

        Returns
        -------
        Matrix
        """
        if format is not None and format.lower() != "hypercsc":
            raise ValueError(f"Invalid format: {format!r}  Must be None or 'hypercsc'.")
        copy = not take_ownership
        indptr = ints_to_numpy_buffer(
            indptr, np.uint64, copy=copy, ownable=True, name="index pointers"
        )
        cols = ints_to_numpy_buffer(cols, np.uint64, copy=copy, ownable=True, name="columns")
        row_indices = ints_to_numpy_buffer(
            row_indices, np.uint64, copy=copy, ownable=True, name="row indices"
        )
        values, dtype = values_to_numpy_buffer(values, dtype, copy=copy, ownable=True)
        if row_indices is values:
            values = np.copy(values)
        mhandle = ffi_new("GrB_Matrix*")
        Ap = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(indptr)))
        Ah = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(cols)))
        Ai = ffi_new("GrB_Index**", ffi.cast("GrB_Index*", ffi.from_buffer(row_indices)))
        Ax = ffi_new("void**", ffi.cast("void**", ffi.from_buffer(values)))
        if nvec is None:
            nvec = cols.size
        check_status_carg(
            lib.GxB_Matrix_import_HyperCSC(
                mhandle,
                dtype._carg,
                nrows,
                ncols,
                Ap,
                Ah,
                Ai,
                Ax,
                indptr.nbytes,
                cols.nbytes,
                row_indices.nbytes,
                values.nbytes,
                is_uniform,
                nvec,
                not sorted_index,
                ffi.NULL,
            ),
            "Matrix",
            mhandle[0],
        )
        rv = gb.Matrix(mhandle, dtype, name=name)
        rv._nrows = nrows
        rv._ncols = ncols
        unclaim_buffer(indptr)
        unclaim_buffer(cols)
        unclaim_buffer(row_indices)
        unclaim_buffer(values)
        return rv

    @classmethod
    def import_bitmapr(
        cls,
        *,
        bitmap,
        values,
        nvals=None,
        nrows=None,
        ncols=None,
        is_uniform=False,
        take_ownership=False,
        dtype=None,
        format=None,
        name=None,
    ):
        """
        GxB_Matrix_import_BitmapR

        Create a new Matrix from values and bitmap (as mask) arrays.

        Parameters
        ----------
        bitmap : array-like
            True elements indicate where there are values in "values".
            May be 1d or 2d, but there need to have at least ``nrows*ncols`` elements.
        values : array-like
            May be 1d or 2d, but there need to have at least ``nrows*ncols`` elements.
        nvals : int, optional
            The number of True elements in the bitmap for this Matrix.
        nrows : int, optional
            The number of rows for the Matrix.
            If not provided, will be inferred from values or bitmap if either is 2d.
        ncols : int
            The number of columns for the Matrix.
            If not provided, will be inferred from values or bitmap if either is 2d.
        is_uniform : bool, default False
            Not yet supported.
        take_ownership : bool, default False
            If True, perform a zero-copy data transfer from input numpy arrays
            to GraphBLAS if possible.  To give ownership of the underlying
            memory buffers to GraphBLAS, the arrays must:
                - be C contiguous
                - have the correct dtype (bool8 for bitmap)
                - own its own data
                - be writeable
            If all of these conditions are not met, then the data will be
            copied and the original array will be unmodified.  If zero copy
            to GraphBLAS is successful, then the array will be mofied to be
            read-only and will no longer own the data.
        dtype : dtype, optional
            dtype of the new Matrix.
            If not specified, this will be inferred from `values`.
        format : str, optional
            Must be "bitmapr" or None.  This is included to be compatible with
            the dict returned from exporting.
        name : str, optional
            Name of the new Matrix.

        Returns
        -------
        Matrix
        """
        if format is not None and format.lower() != "bitmapr":
            raise ValueError(f"Invalid format: {format!r}  Must be None or 'bitmapr'.")
        copy = not take_ownership
        bitmap = ints_to_numpy_buffer(
            bitmap, np.bool8, copy=copy, ownable=True, order="C", name="bitmap"
        )
        values, dtype = values_to_numpy_buffer(values, dtype, copy=copy, ownable=True, order="C")
        if bitmap is values:
            values = np.copy(values)
        nrows, ncols = get_shape(nrows, ncols, values=values, bitmap=bitmap)
        mhandle = ffi_new("GrB_Matrix*")
        Ab = ffi_new("int8_t**", ffi.cast("int8_t*", ffi.from_buffer(bitmap)))
        Ax = ffi_new("void**", ffi.cast("void**", ffi.from_buffer(values)))
        if nvals is None:
            if bitmap.size == nrows * ncols:
                nvals = np.count_nonzero(bitmap)
            else:
                nvals = np.count_nonzero(bitmap.ravel()[: nrows * ncols])
        check_status_carg(
            lib.GxB_Matrix_import_BitmapR(
                mhandle,
                dtype._carg,
                nrows,
                ncols,
                Ab,
                Ax,
                bitmap.nbytes,
                values.nbytes,
                is_uniform,
                nvals,
                ffi.NULL,
            ),
            "Matrix",
            mhandle[0],
        )
        rv = gb.Matrix(mhandle, dtype, name=name)
        rv._nrows = nrows
        rv._ncols = ncols
        unclaim_buffer(bitmap)
        unclaim_buffer(values)
        return rv

    @classmethod
    def import_bitmapc(
        cls,
        *,
        bitmap,
        values,
        nvals=None,
        nrows=None,
        ncols=None,
        is_uniform=False,
        take_ownership=False,
        format=None,
        dtype=None,
        name=None,
    ):
        """
        GxB_Matrix_import_BitmapC

        Create a new Matrix from values and bitmap (as mask) arrays.

        Parameters
        ----------
        bitmap : array-like
            True elements indicate where there are values in "values".
            May be 1d or 2d, but there need to have at least ``nrows*ncols`` elements.
        values : array-like
            May be 1d or 2d, but there need to have at least ``nrows*ncols`` elements.
        nvals : int, optional
            The number of True elements in the bitmap for this Matrix.
        nrows : int, optional
            The number of rows for the Matrix.
            If not provided, will be inferred from values or bitmap if either is 2d.
        ncols : int
            The number of columns for the Matrix.
            If not provided, will be inferred from values or bitmap if either is 2d.
        is_uniform : bool, default False
            Not yet supported.
        take_ownership : bool, default False
            If True, perform a zero-copy data transfer from input numpy arrays
            to GraphBLAS if possible.  To give ownership of the underlying
            memory buffers to GraphBLAS, the arrays must:
                - be FORTRAN contiguous
                - have the correct dtype (bool8 for bitmap)
                - own its own data
                - be writeable
            If all of these conditions are not met, then the data will be
            copied and the original array will be unmodified.  If zero copy
            to GraphBLAS is successful, then the array will be mofied to be
            read-only and will no longer own the data.
        dtype : dtype, optional
            dtype of the new Matrix.
            If not specified, this will be inferred from `values`.
        format : str, optional
            Must be "bitmapc" or None.  This is included to be compatible with
            the dict returned from exporting.
        name : str, optional
            Name of the new Matrix.

        Returns
        -------
        Matrix
        """
        if format is not None and format.lower() != "bitmapc":
            raise ValueError(f"Invalid format: {format!r}  Must be None or 'bitmapc'.")
        copy = not take_ownership
        bitmap = ints_to_numpy_buffer(
            bitmap, np.bool8, copy=copy, ownable=True, order="F", name="bitmap"
        )
        values, dtype = values_to_numpy_buffer(values, dtype, copy=copy, ownable=True, order="F")
        if bitmap is values:
            values = np.copy(values)
        nrows, ncols = get_shape(nrows, ncols, values=values, bitmap=bitmap)
        mhandle = ffi_new("GrB_Matrix*")
        Ab = ffi_new("int8_t**", ffi.cast("int8_t*", ffi.from_buffer(bitmap.T)))
        Ax = ffi_new("void**", ffi.cast("void**", ffi.from_buffer(values.T)))
        if nvals is None:
            if bitmap.size == nrows * ncols:
                nvals = np.count_nonzero(bitmap)
            else:
                nvals = np.count_nonzero(bitmap.ravel("F")[: nrows * ncols])
        check_status_carg(
            lib.GxB_Matrix_import_BitmapC(
                mhandle,
                dtype._carg,
                nrows,
                ncols,
                Ab,
                Ax,
                bitmap.nbytes,
                values.nbytes,
                is_uniform,
                nvals,
                ffi.NULL,
            ),
            "Matrix",
            mhandle[0],
        )
        rv = gb.Matrix(mhandle, dtype, name=name)
        rv._nrows = nrows
        rv._ncols = ncols
        unclaim_buffer(bitmap)
        unclaim_buffer(values)
        return rv

    @classmethod
    def import_fullr(
        cls,
        *,
        values,
        nrows=None,
        ncols=None,
        is_uniform=False,
        take_ownership=False,
        dtype=None,
        format=None,
        name=None,
    ):
        """
        GxB_Matrix_import_FullR

        Create a new Matrix from values.

        Parameters
        ----------
        values : array-like
            May be 1d or 2d, but there need to have at least ``nrows*ncols`` elements.
        nrows : int, optional
            The number of rows for the Matrix.
            If not provided, will be inferred from values if it is 2d.
        ncols : int
            The number of columns for the Matrix.
            If not provided, will be inferred from values if it is 2d.
        is_uniform : bool, default False
            Not yet supported.
        take_ownership : bool, default False
            If True, perform a zero-copy data transfer from input numpy arrays
            to GraphBLAS if possible.  To give ownership of the underlying
            memory buffers to GraphBLAS, the arrays must:
                - be C contiguous
                - have the correct dtype
                - own its own data
                - be writeable
            If all of these conditions are not met, then the data will be
            copied and the original array will be unmodified.  If zero copy
            to GraphBLAS is successful, then the array will be mofied to be
            read-only and will no longer own the data.
        dtype : dtype, optional
            dtype of the new Matrix.
            If not specified, this will be inferred from `values`.
        format : str, optional
            Must be "fullr" or None.  This is included to be compatible with
            the dict returned from exporting.
        name : str, optional
            Name of the new Matrix.

        Returns
        -------
        Matrix
        """
        if format is not None and format.lower() != "fullr":
            raise ValueError(f"Invalid format: {format!r}  Must be None or 'fullr'.")
        copy = not take_ownership
        values, dtype = values_to_numpy_buffer(values, dtype, copy=copy, order="C", ownable=True)
        nrows, ncols = get_shape(nrows, ncols, values=values)
        mhandle = ffi_new("GrB_Matrix*")
        Ax = ffi_new("void**", ffi.cast("void**", ffi.from_buffer(values)))
        check_status_carg(
            lib.GxB_Matrix_import_FullR(
                mhandle,
                dtype._carg,
                nrows,
                ncols,
                Ax,
                values.nbytes,
                is_uniform,
                ffi.NULL,
            ),
            "Matrix",
            mhandle[0],
        )
        rv = gb.Matrix(mhandle, dtype, name=name)
        rv._nrows = nrows
        rv._ncols = ncols
        unclaim_buffer(values)
        return rv

    @classmethod
    def import_fullc(
        cls,
        *,
        values,
        nrows=None,
        ncols=None,
        is_uniform=False,
        take_ownership=False,
        dtype=None,
        format=None,
        name=None,
    ):
        """
        GxB_Matrix_import_FullC

        Create a new Matrix from values.

        Parameters
        ----------
        values : array-like
            May be 1d or 2d, but there need to have at least ``nrows*ncols`` elements.
        nrows : int, optional
            The number of rows for the Matrix.
            If not provided, will be inferred from values if it is 2d.
        ncols : int
            The number of columns for the Matrix.
            If not provided, will be inferred from values if it is 2d.
        is_uniform : bool, default False
            Not yet supported.
        take_ownership : bool, default False
            If True, perform a zero-copy data transfer from input numpy arrays
            to GraphBLAS if possible.  To give ownership of the underlying
            memory buffers to GraphBLAS, the arrays must:
                - be FORTRAN contiguous
                - have the correct dtype
                - own its own data
                - be writeable
            If all of these conditions are not met, then the data will be
            copied and the original array will be unmodified.  If zero copy
            to GraphBLAS is successful, then the array will be mofied to be
            read-only and will no longer own the data.
        dtype : dtype, optional
            dtype of the new Matrix.
            If not specified, this will be inferred from `values`.
        format : str, optional
            Must be "fullc" or None.  This is included to be compatible with
            the dict returned from exporting.
        name : str, optional
            Name of the new Matrix.

        Returns
        -------
        Matrix
        """
        if format is not None and format.lower() != "fullc":
            raise ValueError(f"Invalid format: {format!r}.  Must be None or 'fullc'.")
        copy = not take_ownership
        values, dtype = values_to_numpy_buffer(values, dtype, copy=copy, order="F", ownable=True)
        nrows, ncols = get_shape(nrows, ncols, values=values)
        mhandle = ffi_new("GrB_Matrix*")
        Ax = ffi_new("void**", ffi.cast("void**", ffi.from_buffer(values.T)))
        check_status_carg(
            lib.GxB_Matrix_import_FullC(
                mhandle,
                dtype._carg,
                nrows,
                ncols,
                Ax,
                values.nbytes,
                is_uniform,
                ffi.NULL,
            ),
            "Matrix",
            mhandle[0],
        )
        rv = gb.Matrix(mhandle, dtype, name=name)
        rv._nrows = nrows
        rv._ncols = ncols
        unclaim_buffer(values)
        return rv

    @classmethod
    def import_any(
        cls,
        *,
        # All
        values,
        nrows=None,
        ncols=None,
        is_uniform=False,
        take_ownership=False,
        format=None,
        dtype=None,
        name=None,
        # CSR/CSC/HyperCSR/HyperCSC
        indptr=None,
        sorted_index=False,
        # CSR/HyperCSR
        col_indices=None,
        # HyperCSR
        rows=None,
        # CSC/HyperCSC
        row_indices=None,
        # HyperCSC
        cols=None,
        # HyperCSR/HyperCSC
        nvec=None,  # optional
        # BitmapR/BitmapC
        bitmap=None,
        nvals=None,  # optional
    ):
        """
        GxB_Matrix_import_xxx

        Dispatch to appropriate import method inferred from inputs.
        See the other import functions and `Matrix.ss.export`` for details.

        Returns
        -------
        Matrix

        See Also
        --------
        Matrix.from_values
        Matrix.ss.export
        Matrix.ss.import_csr
        Matrix.ss.import_csc
        Matrix.ss.import_hypercsr
        Matrix.ss.import_hypercsc
        Matrix.ss.import_bitmapr
        Matrix.ss.import_bitmapc
        Matrix.ss.import_fullr
        Matrix.ss.import_fullc

        Examples
        --------
        Simple usage:

        >>> pieces = A.ss.export()
        >>> A2 = Matrix.ss.import_any(**pieces)

        """
        if format is None:
            # Determine format based on provided inputs
            if indptr is not None:
                if bitmap is not None:
                    raise TypeError("Cannot provide both `indptr` and `bitmap`")
                if row_indices is None and col_indices is None:
                    raise TypeError("Must provide either `row_indices` or `col_indices`")
                if row_indices is not None and col_indices is not None:
                    raise TypeError("Cannot provide both `row_indices` and `col_indices`")
                if rows is not None and cols is not None:
                    raise TypeError("Cannot provide both `rows` and `cols`")
                elif rows is None and cols is None:
                    if row_indices is None:
                        format = "csr"
                    else:
                        format = "csc"
                elif rows is not None:
                    if col_indices is None:
                        raise TypeError("HyperCSR requires col_indices, not row_indices")
                    format = "hypercsr"
                else:
                    if row_indices is None:
                        raise TypeError("HyperCSC requires row_indices, not col_indices")
                    format = "hypercsc"
            elif bitmap is not None:
                if col_indices is not None:
                    raise TypeError("Cannot provide both `bitmap` and `col_indices`")
                if row_indices is not None:
                    raise TypeError("Cannot provide both `bitmap` and `row_indices`")
                if cols is not None:
                    raise TypeError("Cannot provide both `bitmap` and `cols`")
                if rows is not None:
                    raise TypeError("Cannot provide both `bitmap` and `rows`")

                # Choose format based on contiguousness of values fist
                if isinstance(values, np.ndarray) and values.ndim == 2:
                    if values.flags.f_contiguous:
                        format = "bitmapc"
                    elif values.flags.c_contiguous:
                        format = "bitmapr"
                # Then consider bitmap contiguousness if necessary
                if format is None and isinstance(bitmap, np.ndarray) and bitmap.ndim == 2:
                    if bitmap.flags.f_contiguous:
                        format = "bitmapc"
                    elif bitmap.flags.c_contiguous:
                        format = "bitmapr"
                # Then default to row-oriented
                if format is None:
                    format = "bitmapr"
            else:
                if (
                    isinstance(values, np.ndarray)
                    and values.ndim == 2
                    and values.flags.f_contiguous
                ):
                    format = "fullc"
                else:
                    format = "fullr"
        else:
            format = format.lower()

        if format == "csr":
            return cls.import_csr(
                nrows=nrows,
                ncols=ncols,
                indptr=indptr,
                values=values,
                col_indices=col_indices,
                is_uniform=is_uniform,
                sorted_index=sorted_index,
                take_ownership=take_ownership,
                dtype=dtype,
                name=name,
            )
        elif format == "csc":
            return cls.import_csc(
                nrows=nrows,
                ncols=ncols,
                indptr=indptr,
                values=values,
                row_indices=row_indices,
                is_uniform=is_uniform,
                sorted_index=sorted_index,
                take_ownership=take_ownership,
                dtype=dtype,
                name=name,
            )
        elif format == "hypercsr":
            return cls.import_hypercsr(
                nrows=nrows,
                ncols=ncols,
                nvec=nvec,
                rows=rows,
                indptr=indptr,
                values=values,
                col_indices=col_indices,
                is_uniform=is_uniform,
                sorted_index=sorted_index,
                take_ownership=take_ownership,
                dtype=dtype,
                name=name,
            )
        elif format == "hypercsc":
            return cls.import_hypercsc(
                nrows=nrows,
                ncols=ncols,
                nvec=nvec,
                cols=cols,
                indptr=indptr,
                values=values,
                row_indices=row_indices,
                is_uniform=is_uniform,
                sorted_index=sorted_index,
                take_ownership=take_ownership,
                dtype=dtype,
                name=name,
            )
        elif format == "bitmapr":
            return cls.import_bitmapr(
                nrows=nrows,
                ncols=ncols,
                values=values,
                nvals=nvals,
                bitmap=bitmap,
                is_uniform=is_uniform,
                take_ownership=take_ownership,
                dtype=dtype,
                name=name,
            )
        elif format == "bitmapc":
            return cls.import_bitmapc(
                nrows=nrows,
                ncols=ncols,
                values=values,
                nvals=nvals,
                bitmap=bitmap,
                is_uniform=is_uniform,
                take_ownership=take_ownership,
                dtype=dtype,
                name=name,
            )
        elif format == "fullr":
            return cls.import_fullr(
                nrows=nrows,
                ncols=ncols,
                values=values,
                is_uniform=is_uniform,
                take_ownership=take_ownership,
                dtype=dtype,
                name=name,
            )
        elif format == "fullc":
            return cls.import_fullc(
                nrows=nrows,
                ncols=ncols,
                values=values,
                is_uniform=is_uniform,
                take_ownership=take_ownership,
                dtype=dtype,
                name=name,
            )
        else:
            raise ValueError(f"Invalid format: {format}")

    @wrapdoc(head)
    def head(self, n=10, *, sort=False, dtype=None):
        return head(self._parent, n, sort=sort, dtype=dtype)
