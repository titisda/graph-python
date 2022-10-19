import atexit
import functools
import itertools

import numpy as np
import pytest

import graphblas as gb

orig_binaryops = set()
orig_semirings = set()


def pytest_configure(config):
    randomly = config.getoption("--randomly", False)
    backend = config.getoption("--backend", "suitesparse")
    blocking = config.getoption("--blocking", True)
    if blocking is None:  # pragma: no branch
        blocking = np.random.rand() < 0.5 if randomly else True
    record = config.getoption("--record", False)
    if record is None:  # pragma: no branch
        record = np.random.rand() < 0.5 if randomly else False
    mapnumpy = config.getoption("--mapnumpy", False)
    if mapnumpy is None:  # pragma: no branch
        mapnumpy = np.random.rand() < 0.5 if randomly else False
    runslow = config.getoption("--runslow", False)
    if runslow is None:  # pragma: no branch
        runslow = np.random.rand() < 0.25 if randomly else False
    config.runslow = runslow

    gb.config.set(autocompute=False, mapnumpy=mapnumpy)

    gb.init(backend, blocking=blocking)
    print(
        f'Running tests with "{backend}" backend, blocking={blocking}, '
        f"record={record}, mapnumpy={mapnumpy}, runslow={runslow}"
    )
    if record:
        rec = gb.Recorder()
        rec.start()

        def save_records():
            with open("record.txt", "w") as f:  # pragma: no cover
                f.write("\n".join(rec.data))

        # I'm sure there's a `pytest` way to do this...
        atexit.register(save_records)
    orig_semirings.update(
        key
        for key in dir(gb.semiring)
        if isinstance(
            getattr(gb.semiring, key),
            (gb.core.operator.Semiring, gb.core.operator.ParameterizedSemiring),
        )
    )
    orig_binaryops.update(
        key
        for key in dir(gb.binary)
        if isinstance(
            getattr(gb.binary, key),
            (gb.core.operator.BinaryOp, gb.core.operator.ParameterizedBinaryOp),
        )
    )
    for mod in [gb.unary, gb.binary, gb.monoid, gb.semiring, gb.op]:
        for name in list(mod._delayed):
            getattr(mod, name)


def pytest_runtest_setup(item):
    if "slow" in item.keywords and not item.config.runslow:
        pytest.skip("need --runslow option to run")


@pytest.fixture(autouse=True, scope="function")
def reset_name_counters():
    """Reset automatic names for each test for easier comparison of record.txt"""
    gb.Matrix._name_counter = itertools.count()
    gb.Vector._name_counter = itertools.count()
    gb.Scalar._name_counter = itertools.count()


def autocompute(func):
    @functools.wraps(func)
    def inner(*args, **kwargs):
        with gb.config.set(autocompute=True):
            return func(*args, **kwargs)

    return inner


def compute(x):
    return x
