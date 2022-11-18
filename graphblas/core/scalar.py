import itertools
import warnings

import numpy as np

from .. import backend, config
from ..binary import isclose
from ..dtypes import _INDEX, BOOL, FP64, lookup_dtype
from ..exceptions import EmptyObject, check_status
from . import automethods, ffi, lib, utils
from .base import BaseExpression, BaseType, call
from .expr import AmbiguousAssignOrExtract
from .operator import get_typed_op
from .utils import _Pointer, output_type, wrapdoc

ffi_new = ffi.new


def _scalar_index(name):
    """Fast way to create scalars with GrB_Index type; used internally."""
    self = object.__new__(Scalar)
    self.name = name
    self.dtype = _INDEX
    self.gb_obj = ffi_new("GrB_Index*")
    self._is_cscalar = True
    self._empty = True
    return self


class Scalar(BaseType):
    """Create a new GraphBLAS Sparse Scalar.

    Parameters
    ----------
    dtype :
        Data type of the Scalar.
    is_cscalar : bool, default=False
        If True, the empty state is managed on the Python side rather than
        with a proper GrB_Scalar object.
    name : str, optional
        Name to give the Scalar. This will be displayed in the ``__repr__``.
    """

    __slots__ = "_empty", "_is_cscalar"
    ndim = 0
    shape = ()
    _is_scalar = True
    _name_counter = itertools.count()

    def __new__(cls, dtype=FP64, *, is_cscalar=False, name=None):
        self = object.__new__(cls)
        dtype = self.dtype = lookup_dtype(dtype)
        self.name = f"s_{next(Scalar._name_counter)}" if name is None else name
        if is_cscalar is None:
            # Internally, we sometimes use `is_cscalar=None` to either defer to `expr.is_cscalar`
            # or to create a C scalar from a Python scalar.  For example, see Matrix.apply.
            is_cscalar = True  # pragma: to_grb
        self._is_cscalar = is_cscalar
        if is_cscalar:
            self._empty = True
            if dtype._is_udt:
                self.gb_obj = ffi_new(dtype.c_type)
            else:
                self.gb_obj = ffi_new(f"{dtype.c_type}*")
        else:
            self.gb_obj = ffi_new("GrB_Scalar*")
            call("GrB_Scalar_new", [_Pointer(self), dtype])
        return self

    @classmethod
    def _from_obj(cls, gb_obj, dtype, *, is_cscalar=False, name=None):
        self = object.__new__(cls)
        self.name = f"s_{next(Scalar._name_counter)}" if name is None else name
        self.gb_obj = gb_obj
        self.dtype = dtype
        self._is_cscalar = is_cscalar
        return self

    def __del__(self):
        gb_obj = getattr(self, "gb_obj", None)
        if gb_obj is not None and lib is not None and "GB_Scalar_opaque" in str(gb_obj):
            # it's difficult/dangerous to record the call, b/c `self.name` may not exist
            check_status(lib.GrB_Scalar_free(gb_obj), self)

    @property
    def is_cscalar(self):
        """Returns True if the empty state is managed on the Python side."""
        return self._is_cscalar

    @property
    def is_grbscalar(self):
        """Returns True if the empty state is managed by the GraphBLAS backend."""
        return not self._is_cscalar

    @property
    def _expr_name(self):
        """The name used in the text for expressions"""
        # Always using `repr(self.value)` may also be reasonable
        return self.name or repr(self.value)

    @property
    def _expr_name_html(self):
        """The name used in the text for expressions in HTML formatting"""
        return self._name_html or repr(self.value)

    def __repr__(self, expr=None):
        from .formatting import format_scalar

        return format_scalar(self, expr=expr)

    def _repr_html_(self, collapse=False, expr=None):
        from .formatting import format_scalar_html

        return format_scalar_html(self, expr=expr)

    def __eq__(self, other):
        """Check equality.

        Equality comparison uses :meth:`isequal`. Use that directly for finer control of
        what is considered equal.
        """
        return self.isequal(other)

    def __bool__(self):
        """Truthiness check.

        The scalar is considered truthy if it is non-empty and the value inside is truthy.

        To only check if a value is present, use :attr:`is_empty`.
        """
        if self._is_empty:
            return False
        return bool(self.value)

    def __float__(self):
        return float(self.value)

    def __int__(self):
        return int(self.value)

    def __complex__(self):
        return complex(self.value)

    def __neg__(self):
        dtype = self.dtype
        if dtype.name[0] == "U" or dtype == BOOL or dtype._is_udt:
            raise TypeError(f"The negative operator, `-`, is not supported for {dtype.name} dtype")
        rv = Scalar(dtype, is_cscalar=self._is_cscalar, name=f"-{self.name or 's_temp'}")
        if self._is_empty:
            return rv
        rv.value = -self.value
        return rv

    def __invert__(self):
        if self.dtype != BOOL:
            raise TypeError(
                f"The invert operator, `~`, is not supported for {self.dtype.name} dtype.  "
                "It is only supported for BOOL dtype."
            )
        rv = Scalar(BOOL, is_cscalar=self._is_cscalar, name=f"~{self.name or 's_temp'}")
        if self._is_empty:
            return rv
        rv.value = not self.value
        return rv

    __index__ = __int__

    def __array__(self, dtype=None):
        if dtype is None:
            dtype = self.dtype.np_type
        return np.array(self.value, dtype=dtype)

    def __sizeof__(self):
        base = object.__sizeof__(self)
        if self._is_cscalar:
            return base + self.gb_obj.__sizeof__() + ffi.sizeof(self.dtype.c_type)
        if backend == "suitesparse":
            size = ffi_new("size_t*")
            check_status(lib.GxB_Scalar_memoryUsage(size, self.gb_obj[0]), self)
            return base + size[0]
        raise TypeError("Unable to get size of GrB_Scalar with backend: {backend}")

    def isequal(self, other, *, check_dtype=False):
        """Check for exact equality (including whether the value is missing).

        Parameters
        ----------
        other : Scalar
            Scalar to compare against
        check_dtypes : bool, default=False
            If True, also checks that dtypes match

        Returns
        -------
        Bool

        See Also
        --------
        :meth:`isclose` : For equality check of floating point dtypes
        """
        if type(other) is not Scalar:
            if other is None:
                return self._is_empty
            try:
                dtype = self.dtype if self.dtype._is_udt else None
                other = Scalar.from_value(other, dtype, is_cscalar=None, name="s_isequal")
            except TypeError:
                other = self._expect_type(
                    other,
                    Scalar,
                    within="isequal",
                    argname="other",
                    extra_message="Literal scalars also accepted.",
                )
            # Don't check dtype if we had to infer dtype of `other`
            check_dtype = False
        if check_dtype and self.dtype != other.dtype:
            return False
        if self._is_empty:
            return other._is_empty
        if other._is_empty:
            return False
        # For now, compare values in Python
        rv = self.value == other.value
        try:
            return bool(rv)
        except ValueError:
            return bool(rv.all())

    def isclose(self, other, *, rel_tol=1e-7, abs_tol=0.0, check_dtype=False):
        """Check for approximate equality (including whether the value is missing).

        Equivalent to: ``abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)``.

        Parameters
        ----------
        other : Scalar
            Scalar to compare against
        rel_tol : float
            Relative tolerance
        abs_tol : float
            Absolute tolerance
        check_dtype : bool
            If True, also checks that dtypes match

        Returns
        -------
        bool
        """
        if type(other) is not Scalar:
            if other is None:
                return self._is_empty
            try:
                other = Scalar.from_value(other, is_cscalar=None, name="s_isclose")
            except TypeError:
                other = self._expect_type(
                    other,
                    Scalar,
                    within="isclose",
                    argname="other",
                    extra_message="Literal scalars also accepted.",
                )
            # Don't check dtype if we had to infer dtype of `other`
            check_dtype = False
        if check_dtype and self.dtype != other.dtype:
            return False
        if self._is_empty:
            return other._is_empty
        if other._is_empty:
            return False
        # We can't yet call a UDF on a scalar as part of the spec, so let's do it ourselves
        isclose_func = isclose(rel_tol, abs_tol)
        isclose_func = get_typed_op(
            isclose_func,
            self.dtype,
            other.dtype,
            is_left_scalar=True,
            is_right_scalar=True,
            kind="binary",
        )
        return isclose_func._numba_func(self.value, other.value)

    def clear(self):
        """In-place operation which clears the value in the Scalar.

        After the call, :attr:`nvals` will return 0.
        """
        if self._is_empty:
            return
        if self._is_cscalar:
            self._empty = True
        else:
            call("GrB_Scalar_clear", [self])

    @property
    def is_empty(self):
        """Indicates whether the Scalar is empty or not."""
        if self._is_cscalar:
            return self._empty
        return self.nvals == 0

    @property
    def _is_empty(self):
        """Like is_empty, but doesn't record calls"""
        if self._is_cscalar:
            return self._empty
        return self._nvals == 0

    @property
    def value(self):
        """Returns the value held by the Scalar as a Python object,
        or None if the Scalar is empty.

        Assigning to ``value`` will update the Scalar.

        Example Usage:

            >>> s.value
            15
            >>> s.value = 16
            >>> s.value
            16
        """
        if self._is_empty:
            return None
        is_udt = self.dtype._is_udt
        if self._is_cscalar:
            scalar = self
        else:
            scalar = Scalar(self.dtype, is_cscalar=True, name="s_temp")
            dtype_name = "UDT" if is_udt else self.dtype.name
            call(f"GrB_Scalar_extractElement_{dtype_name}", [_Pointer(scalar), self])
        if is_udt:
            np_type = self.dtype.np_type
            rv = np.array(ffi.buffer(scalar.gb_obj[0 : np_type.itemsize]))
            if np_type.subdtype is None:
                return rv.view(np_type)[0]
            return rv.view(np_type.subdtype[0]).reshape(np_type.subdtype[1])
        return scalar.gb_obj[0]

    @value.setter
    def value(self, val):
        if val is None or output_type(val) is Scalar and val._is_empty:
            self.clear()
        elif self._is_cscalar:
            if output_type(val) is Scalar:
                val = val.value  # raise below if wrong type (as determined by cffi)
            if self.dtype._is_udt:
                np_type = self.dtype.np_type
                if np_type.subdtype is None:
                    arr = np.empty(1, dtype=np_type)
                    if isinstance(val, dict) and np_type.names is not None:
                        val = _dict_to_record(np_type, val)
                else:
                    arr = np.empty(np_type.subdtype[1], dtype=np_type.subdtype[0])
                arr[:] = val
                self.gb_obj[0 : self.dtype.np_type.itemsize] = arr.view(np.uint8)
                # self.gb_obj[0:self.dtype.np_type.itemsize] = bytes(val)
            else:
                self.gb_obj[0] = val
            self._empty = False
        else:
            if self.dtype._is_udt:
                val = _Pointer(_as_scalar(val, self.dtype, is_cscalar=True))
                dtype_name = "UDT"
            else:
                val = _as_scalar(val, is_cscalar=True)
                dtype_name = val.dtype.name
            call(f"GrB_Scalar_setElement_{dtype_name}", [self, val])

    @property
    def nvals(self):
        """Number of non-empty values.

        Can only be 0 or 1.
        """
        if self._is_cscalar:
            return 0 if self._empty else 1
        scalar = _scalar_index("s_nvals")
        call("GrB_Scalar_nvals", [_Pointer(scalar), self])
        return scalar.gb_obj[0]

    @property
    def _nvals(self):
        """Like nvals, but doesn't record calls"""
        if self._is_cscalar:
            return 0 if self._empty else 1
        n = ffi_new("GrB_Index*")
        check_status(lib.GrB_Scalar_nvals(n, self.gb_obj[0]), self)
        return n[0]

    @property
    def _carg(self):
        if not self._is_cscalar or not self._is_empty:
            return self.gb_obj[0]
        raise EmptyObject(
            "Empty C scalar is invalid when when passed as value (not pointer) to C functions.  "
            "Perhaps use GrB_Scalar instead (e.g., `my_scalar.dup(is_cscalar=False)`)"
        )

    def dup(self, dtype=None, *, clear=False, is_cscalar=None, name=None):
        """Create a duplicate of the Scalar.

        This is a full copy, not a view on the original.

        Parameters
        ----------
        dtype :
            Data type of the new Scalar. Normal typecasting rules apply.
        clear : bool, default=False
            If True, the returned Scalar will be empty.
        is_cscalar : bool
            If True, the empty state is managed on the Python side rather
            than with a proper GrB_Scalar object.
        name : str, optional
            Name to give the Scalar.

        Returns
        -------
        Scalar
        """
        if is_cscalar is None:
            is_cscalar = self._is_cscalar
        if (
            not is_cscalar
            and not self._is_cscalar
            and not clear
            and (dtype is None or dtype == self.dtype)
        ):
            new_scalar = Scalar._from_obj(
                ffi_new("GrB_Scalar*"),
                self.dtype,
                is_cscalar=False,  # pragma: is_grbscalar
                name=name,
            )
            call("GrB_Scalar_dup", [_Pointer(new_scalar), self])
        elif dtype is None:
            new_scalar = Scalar(self.dtype, is_cscalar=is_cscalar, name=name)
            if not clear:
                new_scalar.value = self
        else:
            new_scalar = Scalar(dtype, is_cscalar=is_cscalar, name=name)
            if not clear and not self._is_empty:
                if new_scalar.is_cscalar and not new_scalar.dtype._is_udt:
                    # Cast value so we don't raise given explicit dup with dtype
                    new_scalar.value = new_scalar.dtype.np_type.type(self.value)
                else:
                    new_scalar.value = self.value
        return new_scalar

    def wait(self, how="materialize"):
        """Wait for a computation to complete or establish a "happens-before" relation

        Parameters
        ----------
        how : {"materialize", "complete"}
            "materialize" fully computes an object.
            "complete" establishes a "happens-before" relation useful with multi-threading.
            See GraphBLAS documentation for more details.

        In `non-blocking mode <../user_guide/init.html#graphblas-modes>`__,
        the computations may be delayed and not yet safe to use by multiple threads.
        Use wait to force completion of the Scalar.

        Has no effect in `blocking mode <../user_guide/init.html#graphblas-modes>`__.
        """
        how = how.lower()
        if how == "materialize":
            mode = _MATERIALIZE
        elif how == "complete":
            mode = _COMPLETE
        else:
            raise ValueError(f'`how` argument must be "materialize" or "complete"; got {how!r}')
        if not self._is_cscalar:
            call("GrB_Scalar_wait", [self, mode])

    def get(self, default=None):
        """Get the internal value of the Scalar as a Python scalar.

        Parameters
        ----------
        default :
            Value returned if internal value is missing.

        Returns
        -------
        Python scalar
        """
        return default if self._is_empty else self.value

    @classmethod
    def new(cls, dtype, *, is_cscalar=False, name=None):
        warnings.warn(
            "`Scalar.new(...)` is deprecated; please use `Scalar(...)` instead.",
            DeprecationWarning,
        )
        return Scalar(dtype, is_cscalar=is_cscalar, name=name)

    @classmethod
    def from_value(cls, value, dtype=None, *, is_cscalar=False, name=None):
        """Create a new Scalar from a value.

        Parameters
        ----------
        value : Python scalar
            Internal value of the Scalar.
        dtype :
            Data type of the Scalar. If not provided, the value will be
            inspected to choose an appropriate dtype.
        is_cscalar : bool, default=False
            If True, the empty state is managed on the Python side
            rather than with a proper GrB_Scalar object.
        name : str, optional
            Name to give the Scalar.

        Returns
        -------
        Scalar
        """
        typ = output_type(value)
        if dtype is None:
            if typ is Scalar:
                dtype = value.dtype
            else:
                try:
                    dtype = lookup_dtype(type(value), value)
                except ValueError:
                    raise TypeError(
                        f"Argument of from_value must be a known scalar type, not {type(value)}"
                    ) from None
        if typ is Scalar and type(value) is not Scalar:
            if config.get("autocompute"):
                return value.new(dtype=dtype, is_cscalar=is_cscalar, name=name)
            cls._expect_type(
                value,
                Scalar,
                within="from_value",
                argname="value",
                extra_message="Literal scalars expected.",
            )
        new_scalar = cls(dtype, is_cscalar=is_cscalar, name=name)
        new_scalar.value = value
        return new_scalar

    def __reduce__(self):
        return Scalar._deserialize, (self.value, self.dtype, self._is_cscalar, self.name)

    @staticmethod
    def _deserialize(value, dtype, is_cscalar, name):
        return Scalar.from_value(value, dtype, is_cscalar=is_cscalar, name=name)

    def to_pygraphblas(self):  # pragma: no cover (outdated)
        """Convert to a ``pygraphblas.Scalar`` by making a copy of the internal value.

        This method requires the
        `pygraphblas <https://graphegon.github.io/pygraphblas/pygraphblas/index.html>`_
        library to be installed.
        """
        if backend != "suitesparse":
            raise RuntimeError(
                f"to_pygraphblas only works with 'suitesparse' backend, not {backend}"
            )
        import pygraphblas as pg

        return pg.Scalar.from_value(self.value)

    @classmethod
    def from_pygraphblas(cls, scalar):  # pragma: no cover (outdated)
        """Convert a ``pygraphblas.Scalar`` to a new :class:`Scalar` by making
        a copy of the internal value.

        This method requires the
        `pygraphblas <https://graphegon.github.io/pygraphblas/pygraphblas/index.html>`_
        library to be installed.
        """
        if backend != "suitesparse":
            raise RuntimeError(
                f"from_pygraphblas only works with 'suitesparse' backend, not {backend!r}"
            )
        import pygraphblas as pg

        if not isinstance(scalar, pg.Scalar):
            raise TypeError(f"Expected pygraphblas.Scalar object.  Got type: {type(scalar)}")
        dtype = lookup_dtype(scalar.gb_type)
        return cls.from_value(scalar[0], dtype)

    def _as_vector(self, *, name=None):
        """Copy or cast this Scalar to a Vector

        This casts to a Vector when using GrB_Scalar from SuiteSparse.
        """
        from .vector import Vector

        if backend == "suitesparse" and not self._is_cscalar:
            return Vector._from_obj(
                ffi.cast("GrB_Vector*", self.gb_obj),
                self.dtype,
                1,
                parent=self,
                name=f"(GrB_Vector){self.name or 's_temp'}" if name is None else name,
            )
        rv = Vector(self.dtype, size=1, name=name)
        if not self._is_empty:
            rv[0] = self
        return rv

    def _as_matrix(self, *, name=None):
        """Copy or cast this Scalar to a Matrix

        This casts to a Matrix when using GrB_Scalar from SuiteSparse.
        """
        from .matrix import Matrix

        if backend == "suitesparse" and not self._is_cscalar:
            return Matrix._from_obj(
                ffi.cast("GrB_Matrix*", self.gb_obj),
                self.dtype,
                1,
                1,
                parent=self,
                name=f"(GrB_Matrix){self.name or 's_temp'}" if name is None else name,
            )
        rv = Matrix(self.dtype, ncols=1, nrows=1, name=name)
        if not self._is_empty:
            rv[0, 0] = self
        return rv


class ScalarExpression(BaseExpression):
    __slots__ = "_is_cscalar"
    output_type = Scalar
    ndim = 0
    shape = ()
    _is_scalar = True

    def __init__(self, *args, is_cscalar, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_cscalar = is_cscalar

    def construct_output(self, dtype=None, *, is_cscalar=None, name=None):
        if dtype is None:
            dtype = self.dtype
        if is_cscalar is None:
            is_cscalar = self._is_cscalar
        return Scalar(dtype, is_cscalar=is_cscalar, name=name)

    def new(self, dtype=None, *, is_cscalar=None, name=None):
        if is_cscalar is None:
            is_cscalar = self._is_cscalar
        return super()._new(dtype, None, name, is_cscalar=is_cscalar)

    dup = new

    def __repr__(self):
        from .formatting import format_scalar_expression

        return format_scalar_expression(self)

    def _repr_html_(self):
        from .formatting import format_scalar_expression_html

        return format_scalar_expression_html(self)

    is_cscalar = Scalar.is_cscalar
    is_grbscalar = Scalar.is_grbscalar

    # Begin auto-generated code: Scalar
    _get_value = automethods._get_value
    __array__ = wrapdoc(Scalar.__array__)(property(automethods.__array__))
    __bool__ = wrapdoc(Scalar.__bool__)(property(automethods.__bool__))
    __complex__ = wrapdoc(Scalar.__complex__)(property(automethods.__complex__))
    __eq__ = wrapdoc(Scalar.__eq__)(property(automethods.__eq__))
    __float__ = wrapdoc(Scalar.__float__)(property(automethods.__float__))
    __index__ = wrapdoc(Scalar.__index__)(property(automethods.__index__))
    __int__ = wrapdoc(Scalar.__int__)(property(automethods.__int__))
    __invert__ = wrapdoc(Scalar.__invert__)(property(automethods.__invert__))
    __neg__ = wrapdoc(Scalar.__neg__)(property(automethods.__neg__))
    _as_matrix = wrapdoc(Scalar._as_matrix)(property(automethods._as_matrix))
    _as_vector = wrapdoc(Scalar._as_vector)(property(automethods._as_vector))
    _is_empty = wrapdoc(Scalar._is_empty)(property(automethods._is_empty))
    _name_html = wrapdoc(Scalar._name_html)(property(automethods._name_html))
    _nvals = wrapdoc(Scalar._nvals)(property(automethods._nvals))
    gb_obj = wrapdoc(Scalar.gb_obj)(property(automethods.gb_obj))
    get = wrapdoc(Scalar.get)(property(automethods.get))
    is_empty = wrapdoc(Scalar.is_empty)(property(automethods.is_empty))
    isclose = wrapdoc(Scalar.isclose)(property(automethods.isclose))
    isequal = wrapdoc(Scalar.isequal)(property(automethods.isequal))
    name = wrapdoc(Scalar.name)(property(automethods.name))
    name = name.setter(automethods._set_name)
    nvals = wrapdoc(Scalar.nvals)(property(automethods.nvals))
    to_pygraphblas = wrapdoc(Scalar.to_pygraphblas)(property(automethods.to_pygraphblas))
    value = wrapdoc(Scalar.value)(property(automethods.value))
    wait = wrapdoc(Scalar.wait)(property(automethods.wait))
    # These raise exceptions
    __and__ = Scalar.__and__
    __matmul__ = Scalar.__matmul__
    __or__ = Scalar.__or__
    __rand__ = Scalar.__rand__
    __rmatmul__ = Scalar.__rmatmul__
    __ror__ = Scalar.__ror__
    # End auto-generated code: Scalar


class ScalarIndexExpr(AmbiguousAssignOrExtract):
    output_type = Scalar
    ndim = 0
    shape = ()
    _is_scalar = True
    _is_cscalar = False

    def new(self, dtype=None, *, is_cscalar=None, name=None):
        if is_cscalar is None:
            is_cscalar = False
        return self.parent._extract_element(
            self.resolved_indexes, dtype, is_cscalar=is_cscalar, name=name
        )

    dup = new

    @property
    def is_cscalar(self):
        return self._is_cscalar

    @property
    def is_grbscalar(self):
        return not self._is_cscalar

    # Begin auto-generated code: Scalar
    _get_value = automethods._get_value
    __array__ = wrapdoc(Scalar.__array__)(property(automethods.__array__))
    __bool__ = wrapdoc(Scalar.__bool__)(property(automethods.__bool__))
    __complex__ = wrapdoc(Scalar.__complex__)(property(automethods.__complex__))
    __eq__ = wrapdoc(Scalar.__eq__)(property(automethods.__eq__))
    __float__ = wrapdoc(Scalar.__float__)(property(automethods.__float__))
    __index__ = wrapdoc(Scalar.__index__)(property(automethods.__index__))
    __int__ = wrapdoc(Scalar.__int__)(property(automethods.__int__))
    __invert__ = wrapdoc(Scalar.__invert__)(property(automethods.__invert__))
    __neg__ = wrapdoc(Scalar.__neg__)(property(automethods.__neg__))
    _as_matrix = wrapdoc(Scalar._as_matrix)(property(automethods._as_matrix))
    _as_vector = wrapdoc(Scalar._as_vector)(property(automethods._as_vector))
    _is_empty = wrapdoc(Scalar._is_empty)(property(automethods._is_empty))
    _name_html = wrapdoc(Scalar._name_html)(property(automethods._name_html))
    _nvals = wrapdoc(Scalar._nvals)(property(automethods._nvals))
    gb_obj = wrapdoc(Scalar.gb_obj)(property(automethods.gb_obj))
    get = wrapdoc(Scalar.get)(property(automethods.get))
    is_empty = wrapdoc(Scalar.is_empty)(property(automethods.is_empty))
    isclose = wrapdoc(Scalar.isclose)(property(automethods.isclose))
    isequal = wrapdoc(Scalar.isequal)(property(automethods.isequal))
    name = wrapdoc(Scalar.name)(property(automethods.name))
    name = name.setter(automethods._set_name)
    nvals = wrapdoc(Scalar.nvals)(property(automethods.nvals))
    to_pygraphblas = wrapdoc(Scalar.to_pygraphblas)(property(automethods.to_pygraphblas))
    value = wrapdoc(Scalar.value)(property(automethods.value))
    wait = wrapdoc(Scalar.wait)(property(automethods.wait))
    # These raise exceptions
    __and__ = Scalar.__and__
    __matmul__ = Scalar.__matmul__
    __or__ = Scalar.__or__
    __rand__ = Scalar.__rand__
    __rmatmul__ = Scalar.__rmatmul__
    __ror__ = Scalar.__ror__
    # End auto-generated code: Scalar


def _as_scalar(scalar, dtype=None, *, is_cscalar):
    if type(scalar) is not Scalar:
        return Scalar.from_value(scalar, dtype, is_cscalar=is_cscalar, name="")
    if scalar._is_cscalar != is_cscalar or dtype is not None and scalar.dtype != dtype:
        return scalar.dup(dtype, is_cscalar=is_cscalar, name=scalar.name)
    return scalar


def _dict_to_record(np_type, d):
    """Converts e.g. `{"x": 1, "y": 2.3}` to `(1, 2.3)`"""
    rv = []
    for name, (dtype, _) in np_type.fields.items():
        val = d[name]
        if dtype.names is not None and isinstance(val, dict):
            rv.append(_dict_to_record(dtype, val))
        else:
            rv.append(val)
    return tuple(rv)


_MATERIALIZE = Scalar.from_value(lib.GrB_MATERIALIZE, is_cscalar=True, name="GrB_MATERIALIZE")
_COMPLETE = Scalar.from_value(lib.GrB_COMPLETE, is_cscalar=True, name="GrB_COMPLETE")

utils._output_types[Scalar] = Scalar
utils._output_types[ScalarIndexExpr] = Scalar
utils._output_types[ScalarExpression] = Scalar
