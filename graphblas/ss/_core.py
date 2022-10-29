from collections.abc import Mapping

from suitesparse_graphblas import vararg

from ..core import ffi, lib
from ..core.base import _expect_type
from ..core.matrix import Matrix, TransposedMatrix
from ..core.scalar import Scalar
from ..core.ss.config import BaseConfig
from ..core.ss.matrix import _concat_mn
from ..core.vector import Vector
from ..dtypes import INT64
from ..exceptions import _error_code_lookup


class _graphblas_ss:
    """Used in `_expect_type`"""


_graphblas_ss.__name__ = "graphblas.ss"
_graphblas_ss = _graphblas_ss()


def diag(x, k=0, dtype=None, *, name=None):
    """
    GxB_Matrix_diag, GxB_Vector_diag

    Extract a diagonal Vector from a Matrix, or construct a diagonal Matrix
    from a Vector.  Unlike ``Matrix.diag`` and ``Vector.diag``, this function
    returns a new object.

    Parameters
    ----------
    x : Vector or Matrix
        The Vector to assign to the diagonal, or the Matrix from which to
        extract the diagonal.
    k : int, default 0
        Diagonal in question.  Use `k>0` for diagonals above the main diagonal,
        and `k<0` for diagonals below the main diagonal.

    See Also
    --------
    Vector.diag
    Matrix.diag
    Vector.ss.build_diag
    Matrix.ss.build_diag

    """
    x = _expect_type(
        _graphblas_ss, x, (Matrix, TransposedMatrix, Vector), within="diag", argname="x"
    )
    if type(k) is not Scalar:
        k = Scalar.from_value(k, INT64, is_cscalar=True, name="")
    if dtype is None:
        dtype = x.dtype
    typ = type(x)
    if typ is Vector:
        size = x._size + abs(k.value)
        rv = Matrix(dtype, nrows=size, ncols=size, name=name)
        rv.ss.build_diag(x, k)
    else:
        if k.value < 0:
            size = min(x._nrows + k.value, x._ncols)
        else:
            size = min(x._ncols - k.value, x._nrows)
        if size < 0:
            size = 0
        rv = Vector(dtype, size=size, name=name)
        rv.ss.build_diag(x, k)
    return rv


def concat(tiles, dtype=None, *, name=None):
    """
    GxB_Matrix_concat

    Concatenate a 2D list of Matrix objects into a new Matrix, or a 1D list of
    Vector objects into a new Vector.  To concatenate into existing objects,
    use ``Matrix.ss.concat`` or `Vector.ss.concat`.

    Vectors may be used as `Nx1` Matrix objects when creating a new Matrix.

    This performs the opposite operation as ``split``.

    See Also
    --------
    Matrix.ss.split
    Matrix.ss.concat
    Vector.ss.split
    Vector.ss.concat

    """
    tiles, m, n, is_matrix = _concat_mn(tiles)
    if is_matrix:
        if dtype is None:
            dtype = tiles[0][0].dtype
        nrows = sum(row_tiles[0]._nrows for row_tiles in tiles)
        ncols = sum(tile._ncols for tile in tiles[0])
        rv = Matrix(dtype, nrows=nrows, ncols=ncols, name=name)
        rv.ss._concat(tiles, m, n)
    else:
        if dtype is None:
            dtype = tiles[0].dtype
        size = sum(tile._nrows for tile in tiles)
        rv = Vector(dtype, size=size, name=name)
        rv.ss._concat(tiles, m)
    return rv


class GlobalConfig(BaseConfig):
    """Get and set global configuration options for SuiteSparse:GraphBLAS

    See SuiteSparse:GraphBLAS documentation for more details.

    Config parameters
    -----------------
    format : str, {"by_row", "by_col"}
        Rowwise or columnwise orientation
    hyper_switch : double
        Threshold that determines when to switch to hypersparse format
    bitmap_switch : List[double]
        Threshold that determines when to switch to bitmap format
    nthreads : int
        Maximum number of OpenMP threads to use
    memory_pool : List[int]
    burble : bool
        Enable diagnostic printing from SuiteSparse:GraphBLAS
    print_1based: bool
    gpu_control : str, {"always", "never"}
    gpu_chunk : double

    Setting values to None restores the default value for most configurations.
    """

    _get_function = lib.GxB_Global_Option_get
    _set_function = lib.GxB_Global_Option_set
    _null_valid = {"bitmap_switch"}
    _options = {
        # Matrix/Vector format
        "hyper_switch": (lib.GxB_HYPER_SWITCH, "double"),
        "bitmap_switch": (lib.GxB_BITMAP_SWITCH, f"double[{lib.GxB_NBITMAP_SWITCH}]"),
        "format": (lib.GxB_FORMAT, "GxB_Format_Value"),
        # OpenMP control
        "nthreads": (lib.GxB_GLOBAL_NTHREADS, "int"),
        "chunk": (lib.GxB_GLOBAL_CHUNK, "double"),
        # Memory pool control
        "memory_pool": (lib.GxB_MEMORY_POOL, "int64_t[64]"),
        # Diagnostics (skipping "printf" and "flush" for now)
        "burble": (lib.GxB_BURBLE, "bool"),
        "print_1based": (lib.GxB_PRINT_1BASED, "bool"),
        # CUDA GPU control
        "gpu_control": (lib.GxB_GLOBAL_GPU_CONTROL, "GrB_Desc_Value"),
        "gpu_chunk": (lib.GxB_GLOBAL_GPU_CHUNK, "double"),
    }
    # Values to restore defaults
    _defaults = {
        "hyper_switch": lib.GxB_HYPER_DEFAULT,
        "bitmap_switch": None,
        "format": lib.GxB_FORMAT_DEFAULT,
        "nthreads": 0,
        "chunk": 0,
        "burble": 0,
        "print_1based": 0,
    }
    _enumerations = {
        "format": {
            lib.GxB_BY_ROW: "by_row",
            lib.GxB_BY_COL: "by_col",
            # lib.GxB_NO_FORMAT: "no_format",  # Used by iterators; not valid here
        },
        "gpu_control": {
            lib.GxB_GPU_ALWAYS: "always",
            lib.GxB_GPU_NEVER: "never",
        },
    }


class About(Mapping):
    _modes = {
        lib.GrB_NONBLOCKING: "nonblocking",
        lib.GrB_BLOCKING: "blocking",
        lib.GxB_NONBLOCKING_GPU: "nonblocking_gpu",
        lib.GxB_BLOCKING_GPU: "blocking_gpu",
    }
    _mode_options = {
        "mode": lib.GxB_MODE,
    }
    _int3_options = {
        "library_version": lib.GxB_LIBRARY_VERSION,
        "api_version": lib.GxB_API_VERSION,
        "compiler_version": lib.GxB_COMPILER_VERSION,
    }
    _str_options = {
        "library_name": lib.GxB_LIBRARY_NAME,
        "library_date": lib.GxB_LIBRARY_DATE,
        "library_about": lib.GxB_LIBRARY_ABOUT,
        "library_url": lib.GxB_LIBRARY_URL,
        "library_license": lib.GxB_LIBRARY_LICENSE,
        "library_compile_date": lib.GxB_LIBRARY_COMPILE_DATE,
        "library_compile_time": lib.GxB_LIBRARY_COMPILE_TIME,
        "api_date": lib.GxB_API_DATE,
        "api_about": lib.GxB_API_ABOUT,
        "api_url": lib.GxB_API_URL,
        "compiler_name": lib.GxB_COMPILER_NAME,
    }

    def __getitem__(self, key):
        key = key.lower()
        if key in self._mode_options:
            val_ptr = ffi.new("GrB_Mode*")
            info = lib.GxB_Global_Option_get(self._mode_options[key], vararg(val_ptr))
            if info == lib.GrB_SUCCESS:  # pragma: no branch
                val = val_ptr[0]
                if val not in self._modes:  # pragma: no cover
                    raise ValueError(f"Unknown mode: {val}")
                return self._modes[val]
        elif key in self._int3_options:
            val_ptr = ffi.new("int[3]")
            info = lib.GxB_Global_Option_get(self._int3_options[key], vararg(val_ptr))
            if info == lib.GrB_SUCCESS:  # pragma: no branch
                return (val_ptr[0], val_ptr[1], val_ptr[2])
        elif key in self._str_options:
            val_ptr = ffi.new("char**")
            info = lib.GxB_Global_Option_get(self._str_options[key], vararg(val_ptr))
            if info == lib.GrB_SUCCESS:  # pragma: no branch
                return ffi.string(val_ptr[0]).decode()
        else:
            raise KeyError(key)
        raise _error_code_lookup[info](f"Failed to get info for {key}")  # pragma: no cover

    def __iter__(self):
        return iter(
            sorted(self._mode_options.keys() | self._int3_options.keys() | self._str_options.keys())
        )

    def __len__(self):
        return len(self._mode_options) + len(self._int3_options) + len(self._str_options)

    __repr__ = GlobalConfig.__repr__
    _ipython_key_completions_ = GlobalConfig._ipython_key_completions_


about = About()
config = GlobalConfig()
