from .. import backend, binary
from ..dtypes import BOOL
from ..monoid import land, lor
from ..semiring import any_pair
from . import automethods, utils
from .base import _expect_op, _expect_type
from .expr import InfixExprBase
from .mask import Mask
from .matrix import Matrix, MatrixExpression, TransposedMatrix
from .scalar import Scalar, ScalarExpression
from .utils import output_type, wrapdoc
from .vector import Vector, VectorExpression

InfixExprBase._expect_op = _expect_op
InfixExprBase._expect_type = _expect_type


def _ewise_add_to_expr(self):
    if self._value is not None:
        return self._value
    if self.left.dtype == BOOL and self.right.dtype == BOOL:
        self._value = self.left.ewise_add(self.right, lor)
        return self._value
    raise TypeError(
        "Bad dtypes for `x | y`!  Automatic computation of `x | y` infix expressions is only valid "
        f"for BOOL dtypes.  The argument dtypes are {self.left.dtype} and {self.right.dtype}.\n\n"
        "When auto-computed for boolean dtypes, `x | y` performs ewise_add (union) using LOR.\n\n"
        "Typical usage is to create an ewise_add expression such as `monoid.plus(x | y)`."
    )


def _ewise_mult_to_expr(self):
    if self._value is not None:
        return self._value
    if self.left.dtype == BOOL and self.right.dtype == BOOL:
        self._value = self.left.ewise_mult(self.right, land)
        return self._value
    raise TypeError(
        "Bad dtypes for `x & y`!  Automatic computation of `x & y` infix expressions is only valid "
        f"for BOOL dtypes.  The argument dtypes are {self.left.dtype} and {self.right.dtype}.\n\n"
        "When auto-computed for boolean dtypes, `x & y` performs ewise_mult (intersection) using "
        "LAND.\n\n"
        "Typical usage is to create an ewise_mult expression such as `monoid.times(x & y)`."
    )


class VectorInfixExpr(InfixExprBase):
    __slots__ = "_size"
    ndim = 1
    output_type = VectorExpression

    def __init__(self, left, right):
        super().__init__(left, right)
        self._size = left._size

    @property
    def size(self):
        return self._size

    @property
    def shape(self):
        return (self._size,)

    # Begin auto-generated code: Vector
    S = wrapdoc(Vector.S)(property(automethods.S))
    V = wrapdoc(Vector.V)(property(automethods.V))
    __and__ = wrapdoc(Vector.__and__)(property(automethods.__and__))
    __contains__ = wrapdoc(Vector.__contains__)(property(automethods.__contains__))
    __getitem__ = wrapdoc(Vector.__getitem__)(property(automethods.__getitem__))
    __iter__ = wrapdoc(Vector.__iter__)(property(automethods.__iter__))
    __matmul__ = wrapdoc(Vector.__matmul__)(property(automethods.__matmul__))
    __or__ = wrapdoc(Vector.__or__)(property(automethods.__or__))
    __rand__ = wrapdoc(Vector.__rand__)(property(automethods.__rand__))
    __rmatmul__ = wrapdoc(Vector.__rmatmul__)(property(automethods.__rmatmul__))
    __ror__ = wrapdoc(Vector.__ror__)(property(automethods.__ror__))
    _as_matrix = wrapdoc(Vector._as_matrix)(property(automethods._as_matrix))
    _carg = wrapdoc(Vector._carg)(property(automethods._carg))
    _name_html = wrapdoc(Vector._name_html)(property(automethods._name_html))
    _nvals = wrapdoc(Vector._nvals)(property(automethods._nvals))
    apply = wrapdoc(Vector.apply)(property(automethods.apply))
    diag = wrapdoc(Vector.diag)(property(automethods.diag))
    ewise_add = wrapdoc(Vector.ewise_add)(property(automethods.ewise_add))
    ewise_mult = wrapdoc(Vector.ewise_mult)(property(automethods.ewise_mult))
    ewise_union = wrapdoc(Vector.ewise_union)(property(automethods.ewise_union))
    gb_obj = wrapdoc(Vector.gb_obj)(property(automethods.gb_obj))
    get = wrapdoc(Vector.get)(property(automethods.get))
    inner = wrapdoc(Vector.inner)(property(automethods.inner))
    isclose = wrapdoc(Vector.isclose)(property(automethods.isclose))
    isequal = wrapdoc(Vector.isequal)(property(automethods.isequal))
    name = wrapdoc(Vector.name)(property(automethods.name))
    name = name.setter(automethods._set_name)
    nvals = wrapdoc(Vector.nvals)(property(automethods.nvals))
    outer = wrapdoc(Vector.outer)(property(automethods.outer))
    reduce = wrapdoc(Vector.reduce)(property(automethods.reduce))
    reposition = wrapdoc(Vector.reposition)(property(automethods.reposition))
    select = wrapdoc(Vector.select)(property(automethods.select))
    if backend == "suitesparse":
        ss = wrapdoc(Vector.ss)(property(automethods.ss))
    to_coo = wrapdoc(Vector.to_coo)(property(automethods.to_coo))
    to_dict = wrapdoc(Vector.to_dict)(property(automethods.to_dict))
    to_pygraphblas = wrapdoc(Vector.to_pygraphblas)(property(automethods.to_pygraphblas))
    to_values = wrapdoc(Vector.to_values)(property(automethods.to_values))
    vxm = wrapdoc(Vector.vxm)(property(automethods.vxm))
    wait = wrapdoc(Vector.wait)(property(automethods.wait))
    # These raise exceptions
    __array__ = Vector.__array__
    __bool__ = Vector.__bool__
    __iadd__ = automethods.__iadd__
    __iand__ = automethods.__iand__
    __ifloordiv__ = automethods.__ifloordiv__
    __imatmul__ = automethods.__imatmul__
    __imod__ = automethods.__imod__
    __imul__ = automethods.__imul__
    __ior__ = automethods.__ior__
    __ipow__ = automethods.__ipow__
    __isub__ = automethods.__isub__
    __itruediv__ = automethods.__itruediv__
    __ixor__ = automethods.__ixor__
    # End auto-generated code: Vector


class VectorEwiseAddExpr(VectorInfixExpr):
    __slots__ = ()
    method_name = "ewise_add"
    _example_op = "plus"
    _infix = "|"

    _to_expr = _ewise_add_to_expr


class VectorEwiseMultExpr(VectorInfixExpr):
    __slots__ = ()
    method_name = "ewise_mult"
    _example_op = "times"
    _infix = "&"

    _to_expr = _ewise_mult_to_expr


class VectorMatMulExpr(VectorInfixExpr):
    __slots__ = "method_name"
    _example_op = "plus_times"
    _infix = "@"

    def __init__(self, left, right, *, method_name, size):
        InfixExprBase.__init__(self, left, right)
        self.method_name = method_name
        self._size = size


utils._output_types[VectorEwiseAddExpr] = Vector
utils._output_types[VectorEwiseMultExpr] = Vector
utils._output_types[VectorMatMulExpr] = Vector


class MatrixInfixExpr(InfixExprBase):
    __slots__ = "_nrows", "_ncols"
    ndim = 2
    output_type = MatrixExpression
    _is_transposed = False
    __networkx_plugin__ = "graphblas"

    def __init__(self, left, right):
        super().__init__(left, right)
        if left.ndim == 1:
            self._nrows = right._nrows
            self._ncols = right._ncols
        else:
            self._nrows = left._nrows
            self._ncols = left._ncols

    @property
    def nrows(self):
        return self._nrows

    @property
    def ncols(self):
        return self._ncols

    @property
    def shape(self):
        return (self._nrows, self._ncols)

    # Begin auto-generated code: Matrix
    S = wrapdoc(Matrix.S)(property(automethods.S))
    T = wrapdoc(Matrix.T)(property(automethods.T))
    V = wrapdoc(Matrix.V)(property(automethods.V))
    __and__ = wrapdoc(Matrix.__and__)(property(automethods.__and__))
    __contains__ = wrapdoc(Matrix.__contains__)(property(automethods.__contains__))
    __getitem__ = wrapdoc(Matrix.__getitem__)(property(automethods.__getitem__))
    __iter__ = wrapdoc(Matrix.__iter__)(property(automethods.__iter__))
    __matmul__ = wrapdoc(Matrix.__matmul__)(property(automethods.__matmul__))
    __or__ = wrapdoc(Matrix.__or__)(property(automethods.__or__))
    __rand__ = wrapdoc(Matrix.__rand__)(property(automethods.__rand__))
    __rmatmul__ = wrapdoc(Matrix.__rmatmul__)(property(automethods.__rmatmul__))
    __ror__ = wrapdoc(Matrix.__ror__)(property(automethods.__ror__))
    _as_vector = wrapdoc(Matrix._as_vector)(property(automethods._as_vector))
    _carg = wrapdoc(Matrix._carg)(property(automethods._carg))
    _name_html = wrapdoc(Matrix._name_html)(property(automethods._name_html))
    _nvals = wrapdoc(Matrix._nvals)(property(automethods._nvals))
    apply = wrapdoc(Matrix.apply)(property(automethods.apply))
    diag = wrapdoc(Matrix.diag)(property(automethods.diag))
    ewise_add = wrapdoc(Matrix.ewise_add)(property(automethods.ewise_add))
    ewise_mult = wrapdoc(Matrix.ewise_mult)(property(automethods.ewise_mult))
    ewise_union = wrapdoc(Matrix.ewise_union)(property(automethods.ewise_union))
    gb_obj = wrapdoc(Matrix.gb_obj)(property(automethods.gb_obj))
    get = wrapdoc(Matrix.get)(property(automethods.get))
    isclose = wrapdoc(Matrix.isclose)(property(automethods.isclose))
    isequal = wrapdoc(Matrix.isequal)(property(automethods.isequal))
    kronecker = wrapdoc(Matrix.kronecker)(property(automethods.kronecker))
    mxm = wrapdoc(Matrix.mxm)(property(automethods.mxm))
    mxv = wrapdoc(Matrix.mxv)(property(automethods.mxv))
    name = wrapdoc(Matrix.name)(property(automethods.name))
    name = name.setter(automethods._set_name)
    nvals = wrapdoc(Matrix.nvals)(property(automethods.nvals))
    reduce_columnwise = wrapdoc(Matrix.reduce_columnwise)(property(automethods.reduce_columnwise))
    reduce_rowwise = wrapdoc(Matrix.reduce_rowwise)(property(automethods.reduce_rowwise))
    reduce_scalar = wrapdoc(Matrix.reduce_scalar)(property(automethods.reduce_scalar))
    reposition = wrapdoc(Matrix.reposition)(property(automethods.reposition))
    select = wrapdoc(Matrix.select)(property(automethods.select))
    if backend == "suitesparse":
        ss = wrapdoc(Matrix.ss)(property(automethods.ss))
    to_coo = wrapdoc(Matrix.to_coo)(property(automethods.to_coo))
    to_csc = wrapdoc(Matrix.to_csc)(property(automethods.to_csc))
    to_csr = wrapdoc(Matrix.to_csr)(property(automethods.to_csr))
    to_dcsc = wrapdoc(Matrix.to_dcsc)(property(automethods.to_dcsc))
    to_dcsr = wrapdoc(Matrix.to_dcsr)(property(automethods.to_dcsr))
    to_dicts = wrapdoc(Matrix.to_dicts)(property(automethods.to_dicts))
    to_pygraphblas = wrapdoc(Matrix.to_pygraphblas)(property(automethods.to_pygraphblas))
    to_values = wrapdoc(Matrix.to_values)(property(automethods.to_values))
    wait = wrapdoc(Matrix.wait)(property(automethods.wait))
    # These raise exceptions
    __array__ = Matrix.__array__
    __bool__ = Matrix.__bool__
    __iadd__ = automethods.__iadd__
    __iand__ = automethods.__iand__
    __ifloordiv__ = automethods.__ifloordiv__
    __imatmul__ = automethods.__imatmul__
    __imod__ = automethods.__imod__
    __imul__ = automethods.__imul__
    __ior__ = automethods.__ior__
    __ipow__ = automethods.__ipow__
    __isub__ = automethods.__isub__
    __itruediv__ = automethods.__itruediv__
    __ixor__ = automethods.__ixor__
    # End auto-generated code: Matrix


class MatrixEwiseAddExpr(MatrixInfixExpr):
    __slots__ = ()
    method_name = "ewise_add"
    _example_op = "plus"
    _infix = "|"

    _to_expr = _ewise_add_to_expr


class MatrixEwiseMultExpr(MatrixInfixExpr):
    __slots__ = ()
    method_name = "ewise_mult"
    _example_op = "times"
    _infix = "&"

    _to_expr = _ewise_mult_to_expr


class MatrixMatMulExpr(MatrixInfixExpr):
    __slots__ = ()
    method_name = "mxm"
    _example_op = "plus_times"
    _infix = "@"

    def __init__(self, left, right, *, nrows, ncols):
        super().__init__(left, right)
        self._nrows = nrows
        self._ncols = ncols


utils._output_types[MatrixEwiseAddExpr] = Matrix
utils._output_types[MatrixEwiseMultExpr] = Matrix
utils._output_types[MatrixMatMulExpr] = Matrix


class ScalarMatMulExpr(InfixExprBase):
    __slots__ = ()
    method_name = "inner"
    ndim = 0
    output_type = ScalarExpression
    shape = ()
    _example_op = "plus_times"
    _infix = "@"
    _is_scalar = True

    def new(self, dtype=None, *, is_cscalar=None, name=None):
        # Rely on the default operator for the method
        expr = getattr(self.left, self.method_name)(self.right)
        return expr.new(dtype, is_cscalar=is_cscalar, name=name)

    dup = new

    @property
    def is_cscalar(self):
        if self._value is not None:
            return self._value._is_cscalar
        return self._to_expr()._is_cscalar

    _is_cscalar = is_cscalar

    @property
    def is_grbscalar(self):
        if self._value is not None:
            return not self._value._is_cscalar
        return not self._to_expr()._is_cscalar

    # Begin auto-generated code: Scalar
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


utils._output_types[ScalarMatMulExpr] = Scalar


def _ewise_infix_expr(left, right, *, method, within):
    left_type = output_type(left)
    right_type = output_type(right)

    types = {Vector, Matrix, TransposedMatrix}
    if left_type in types and right_type in types:
        # Create dummy expression to check compatibility of dimensions, etc.
        expr = getattr(left, method)(right, binary.any)
        if expr.output_type is Vector:
            if method == "ewise_mult":
                return VectorEwiseMultExpr(left, right)
            return VectorEwiseAddExpr(left, right)
        if method == "ewise_mult":
            return MatrixEwiseMultExpr(left, right)
        return MatrixEwiseAddExpr(left, right)
    if within == "__or__" and isinstance(right, Mask):
        return right.__ror__(left)
    if within == "__and__" and isinstance(right, Mask):
        return right.__rand__(left)
    if left_type in types:
        left._expect_type(right, tuple(types), within=within, argname="right")
    elif right_type in types:
        right._expect_type(left, tuple(types), within=within, argname="left")
    else:  # pragma: no cover (sanity)
        raise TypeError(f"Bad types for ewise infix: {type(left).__name__}, {type(right).__name__}")


def _matmul_infix_expr(left, right, *, within):
    left_type = output_type(left)
    right_type = output_type(right)

    if left_type is Vector:
        if right_type is Matrix or right_type is TransposedMatrix:
            method = "vxm"
        elif right_type is Vector:
            method = "inner"
        else:
            right = left._expect_type(
                right,
                (Matrix, TransposedMatrix),
                within=within,
                argname="right",
            )
    elif left_type is Matrix or left_type is TransposedMatrix:
        if right_type is Vector:
            method = "mxv"
        elif right_type is Matrix or right_type is TransposedMatrix:
            method = "mxm"
        else:
            right = left._expect_type(
                right,
                (Vector, Matrix, TransposedMatrix),
                within=within,
                argname="right",
            )
    elif right_type is Vector:
        left = right._expect_type(
            left,
            (Matrix, TransposedMatrix),
            within=within,
            argname="left",
        )
    elif right_type is Matrix or right_type is TransposedMatrix:
        left = right._expect_type(
            left,
            (Vector, Matrix, TransposedMatrix),
            within=within,
            argname="left",
        )
    else:  # pragma: no cover (sanity)
        raise TypeError(
            f"Bad types for matmul infix: {type(left).__name__}, {type(right).__name__}"
        )

    # Create dummy expression to check compatibility of dimensions, etc.
    expr = getattr(left, method)(right, any_pair[bool])
    if expr.output_type is Vector:
        return VectorMatMulExpr(left, right, method_name=method, size=expr._size)
    if expr.output_type is Matrix:
        return MatrixMatMulExpr(left, right, nrows=expr._nrows, ncols=expr._ncols)
    return ScalarMatMulExpr(left, right)


# Import infixmethods, which has side effects
from . import infixmethods  # noqa isort:skip
