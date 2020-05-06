import importlib
from . import backends  # noqa

_init_params = None
_SPECIAL_ATTRS = {"lib", "ffi", "Matrix", "Vector", "Scalar",
                  "exceptions", "matrix", "ops", "scalar", "vector",
                  "unary", "binary", "monoid", "semiring"}


def __getattr__(name):
    """Auto-initialize if special attrs used without explicit init call by user"""
    if name in _SPECIAL_ATTRS:
        if _init_params is None:
            _init("suitesparse", True, automatic=True)
        if name not in globals():
            _load(name)
        return globals()[name]
    else:
        raise AttributeError(f"module {__name__!r} has not attribute {name!r}")


def __dir__():
    return list(globals().keys() | _SPECIAL_ATTRS)


def init(backend="suitesparse", blocking=True):
    _init(backend, blocking)


def _init(backend, blocking, automatic=False):
    global _init_params, lib, ffi

    passed_params = dict(backend=backend, blocking=blocking, automatic=automatic)
    if _init_params is None:
        _init_params = passed_params
    else:
        if _init_params != passed_params:
            from .exceptions import GrblasException
            if _init_params.get("automatic"):
                raise GrblasException("grblas objects accessed prior to manual initialization")
            else:
                raise GrblasException("grblas initialized multiple times with different init parameters")
        # Already initialized with these parameters; nothing more to do
        return

    ffi_backend = importlib.import_module(f'.backends.{backend}', __name__)
    lib = ffi_backend.lib
    ffi = ffi_backend.ffi
    # This must be called before anything else happens
    if blocking:
        ffi_backend.lib.GrB_init(ffi_backend.lib.GrB_BLOCKING)
    else:
        ffi_backend.lib.GrB_init(ffi_backend.lib.GrB_NONBLOCKING)


def _load(name):
    if name in {'Matrix', 'Vector', 'Scalar'}:
        module_name = name.lower()
        if module_name not in globals():
            _load(module_name)
        module = globals()[module_name]
        val = getattr(module, name)
        globals()[name] = val
    elif name in _SPECIAL_ATTRS:
        # Everything else is a module
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
    else:
        raise ValueError(name)
