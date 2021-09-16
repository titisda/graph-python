""" Define functions to use as property methods on expressions.

These will automatically compute the value and avoid the need for `.new()`.

To automatically create the functions, run:

```python

common = {
    "_name_html",
    "_nvals",
    "gb_obj",
    "isclose",
    "isequal",
    "name",
    "nvals",
    "to_pygraphblas",
    "wait",
}
scalar = {
    "__array__",
    "__bool__",
    "__complex__",
    "__eq__",
    "__float__",
    "__index__",
    "__int__",
    "__neg__",
    "is_empty",
    "value",
}
vector_matrix = {
    "S",
    "V",
    "__and__",
    "__contains__",
    "__getitem__",
    "__iter__",
    "__matmul__",
    "__or__",
    "__rand__",
    "__rmatmul__",
    "__ror__",
    "_carg",
    "apply",
    "ewise_add",
    "ewise_mult",
    "ss",
    "to_values",
}
vector = {
    "inner",
    "outer",
    "reduce",
    "vxm",
}
matrix = {
    "T",
    "kronecker",
    "mxm",
    "mxv",
    "reduce_columns",
    "reduce_rows",
    "reduce_scalar",
}
common_raises = {
    "__ior__",
    "__iand__",
    "__imatmul__",
}
scalar_raises = {
    "__and__",
    "__matmul__",
    "__or__",
    "__rand__",
    "__rmatmul__",
    "__ror__",
}
vector_matrix_raises = {
    "__array__",
    "__bool__",
}
has_defaults = {
    "__eq__",
}
# no inplace math for expressions
bad_sugar = {
    "__iadd__",
    "__ifloordiv__",
    "__imod__",
    "__imul__",
    "__ipow__",
    "__isub__",
    "__itruediv__",
}
# Copy the result of this below
for name in sorted(common | scalar | vector_matrix | vector | matrix):
    print(f"def {name}(self):")
    if name in has_defaults:
        print(f"    return self._get_value({name!r}, default{name})\n\n")
    else:
        print(f"    return self._get_value({name!r})\n\n")
for name in sorted(bad_sugar):
    print(f"def {name}(self, other):")
    print(f'    raise TypeError(f"{name!r} not supported for {{type(self).__name__}}")\n\n')


# Copy to scalar.py and infix.py
print("    _get_value = _automethods._get_value")
for name in sorted(common | scalar):
    print(f"    {name} = wrapdoc(Scalar.{name})(property(_automethods.{name}))")
    if name == "name":
        print("    name = name.setter(_automethods._set_name)")
print("    # These raise exceptions")
for name in sorted(common_raises | scalar_raises):
    print(f"    {name} = wrapdoc(Scalar.{name})(Scalar.{name})")
print()

# Copy to vector.py and infix.py
print("    _get_value = _automethods._get_value")
for name in sorted(common | vector_matrix | vector):
    print(f"    {name} = wrapdoc(Vector.{name})(property(_automethods.{name}))")
    if name == "name":
        print("    name = name.setter(_automethods._set_name)")
print("    # These raise exceptions")
for name in sorted(common_raises | vector_matrix_raises):
    print(f"    {name} = wrapdoc(Vector.{name})(Vector.{name})")
for name in sorted(bad_sugar):
    print(f"    {name} = _automethods.{name}")
print()

# Copy to matrix.py and infix.py
print("    _get_value = _automethods._get_value")
for name in sorted(common | vector_matrix | matrix):
    print(f"    {name} = wrapdoc(Matrix.{name})(property(_automethods.{name}))")
    if name == "name":
        print("    name = name.setter(_automethods._set_name)")
print("    # These raise exceptions")
for name in sorted(common_raises | vector_matrix_raises):
    print(f"    {name} = wrapdoc(Matrix.{name})(Matrix.{name})")
for name in sorted(bad_sugar):
    print(f"    {name} = _automethods.{name}")

```
"""
from . import config


def _get_value(self, attr=None, default=None):
    if config.get("autocompute"):
        if self._value is None:
            self._value = self.new()
        if attr is None:
            return self._value
        else:
            return getattr(self._value, attr)
    if default is not None:
        return default.__get__(self)
    raise TypeError(
        f"{attr} not enabled for objects of type {type(self)}.  "
        f"Use `.new()` to create a new {self.output_type.__name__}.\n\n"
        "Hint: use `grblas.config.set(autocompute=True)` to enable "
        "automatic computation of expressions."
    )


def _set_name(self, name):
    self._get_value().name = name


def default__eq__(self, other):
    raise TypeError(
        f"__eq__ not enabled for objects of type {type(self)}.  "
        f"Use `.new()` to create a new {self.output_type.__name__}, then use `.isequal` method.\n\n"
        "Hint: use `grblas.config.set(autocompute=True)` to enable "
        "automatic computation of expressions."
    )


# Paste here
def S(self):
    return self._get_value("S")


def T(self):
    return self._get_value("T")


def V(self):
    return self._get_value("V")


def __and__(self):
    return self._get_value("__and__")


def __array__(self):
    return self._get_value("__array__")


def __bool__(self):
    return self._get_value("__bool__")


def __complex__(self):
    return self._get_value("__complex__")


def __contains__(self):
    return self._get_value("__contains__")


def __eq__(self):
    return self._get_value("__eq__", default__eq__)


def __float__(self):
    return self._get_value("__float__")


def __getitem__(self):
    return self._get_value("__getitem__")


def __index__(self):
    return self._get_value("__index__")


def __int__(self):
    return self._get_value("__int__")


def __iter__(self):
    return self._get_value("__iter__")


def __matmul__(self):
    return self._get_value("__matmul__")


def __neg__(self):
    return self._get_value("__neg__")


def __or__(self):
    return self._get_value("__or__")


def __rand__(self):
    return self._get_value("__rand__")


def __rmatmul__(self):
    return self._get_value("__rmatmul__")


def __ror__(self):
    return self._get_value("__ror__")


def _carg(self):
    return self._get_value("_carg")


def _name_html(self):
    return self._get_value("_name_html")


def _nvals(self):
    return self._get_value("_nvals")


def apply(self):
    return self._get_value("apply")


def ewise_add(self):
    return self._get_value("ewise_add")


def ewise_mult(self):
    return self._get_value("ewise_mult")


def gb_obj(self):
    return self._get_value("gb_obj")


def inner(self):
    return self._get_value("inner")


def is_empty(self):
    return self._get_value("is_empty")


def isclose(self):
    return self._get_value("isclose")


def isequal(self):
    return self._get_value("isequal")


def kronecker(self):
    return self._get_value("kronecker")


def mxm(self):
    return self._get_value("mxm")


def mxv(self):
    return self._get_value("mxv")


def name(self):
    return self._get_value("name")


def nvals(self):
    return self._get_value("nvals")


def outer(self):
    return self._get_value("outer")


def reduce(self):
    return self._get_value("reduce")


def reduce_columns(self):
    return self._get_value("reduce_columns")


def reduce_rows(self):
    return self._get_value("reduce_rows")


def reduce_scalar(self):
    return self._get_value("reduce_scalar")


def ss(self):
    return self._get_value("ss")


def to_pygraphblas(self):
    return self._get_value("to_pygraphblas")


def to_values(self):
    return self._get_value("to_values")


def value(self):
    return self._get_value("value")


def vxm(self):
    return self._get_value("vxm")


def wait(self):
    return self._get_value("wait")


def __iadd__(self, other):
    raise TypeError(f"'__iadd__' not supported for {type(self).__name__}")


def __ifloordiv__(self, other):
    raise TypeError(f"'__ifloordiv__' not supported for {type(self).__name__}")


def __imod__(self, other):
    raise TypeError(f"'__imod__' not supported for {type(self).__name__}")


def __imul__(self, other):
    raise TypeError(f"'__imul__' not supported for {type(self).__name__}")


def __ipow__(self, other):
    raise TypeError(f"'__ipow__' not supported for {type(self).__name__}")


def __isub__(self, other):
    raise TypeError(f"'__isub__' not supported for {type(self).__name__}")


def __itruediv__(self, other):
    raise TypeError(f"'__itruediv__' not supported for {type(self).__name__}")
