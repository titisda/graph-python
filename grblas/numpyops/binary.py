import numpy as np
from .. import ops

_binary_names = {
    # Math operations
    'add',
    'subtract',
    'multiply',
    'divide',
    'logaddexp',
    'logaddexp2',
    'true_divide',
    'floor_divide',
    'power',
    'remainder',
    'mod',
    'fmod',
    'gcd',
    'lcm',

    # Trigonometric functions
    'arctan2',
    'hypot',

    # Bit-twiddling functions
    'bitwise_and',
    'bitwise_or',
    'bitwise_xor',
    'left_shift',
    'right_shift',

    # Comparison functions
    'greater',
    'greater_equal',
    'less',
    'less_equal',
    'not_equal',
    'equal',
    'logical_and',
    'logical_or',
    'logical_xor',
    'maximum',
    'minimum',
    'fmax',
    'fmin',

    # Floating functions
    'copysign',
    'nextafter',
    'ldexp',
}


def __dir__():
    return list(_binary_names)


def __getattr__(name):
    if name not in _binary_names:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    numpy_func = getattr(np, name)
    func = ops.BinaryOp.register_anonymous(lambda x, y: numpy_func(x, y), name)
    globals()[name] = func
    return func
