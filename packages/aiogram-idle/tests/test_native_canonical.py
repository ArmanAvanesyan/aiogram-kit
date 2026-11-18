"""Full fingerprint parity across native serialization and Python reference."""

import math
import random
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from types import MappingProxyType

import pytest

from aiogram_idle.storage.receipts import fingerprint


class Number(IntEnum):
    ONE = 1


class Word(str, Enum):
    TEXT = "Հայերեն"


class Complex(Enum):
    VALUE = {True: [1.0, "x"]}


@dataclass
class Record:
    data: object
    other: object = field(default_factory=lambda: (Number.ONE, Word.TEXT))


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        2**200,
        -(2**200),
        -0.0,
        1e-200,
        1e200,
        1.2345678901234567,
        "\x00\b\f\n\r\t\x1f\x7f\uffff😀Հայերեն",
        "\ud800\udfff",
        {1: 1, "1": 2, None: 3, False: 4},
        MappingProxyType({"b": (1, {"a": False})}),
        Record({"a": [1, None]}),
        Word.TEXT,
        Number.ONE,
        Complex.VALUE,
    ],
)
def test_full_fingerprint_parity(value):
    native()
    assert fingerprint(value, engine="rust") == fingerprint(value)


def native():
    pytest.importorskip("aiogram_idle_native")


def test_generated_finite_numbers():
    native()
    rng = random.Random(7315)
    values = [math.ldexp(rng.uniform(-1, 1), rng.randrange(-1020, 1020)) for _ in range(1000)]
    assert fingerprint(values, engine="rust") == fingerprint(values)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object(), Record(object())])
def test_rejected_values_match_exception_type(value):
    native()
    errors = []
    for engine in ("python", "rust"):
        with pytest.raises(Exception) as error:
            fingerprint(value, engine=engine)
        errors.append(type(error.value))
    assert errors[0] is errors[1]


def test_recursive_input_does_not_crash():
    native()
    value = []
    value.append(value)
    with pytest.raises(RecursionError):
        fingerprint(value, engine="rust")


def test_datetime_fingerprints_use_python_isoformat():
    native()
    from datetime import datetime, timezone

    for value in (datetime(2026, 11, 18), datetime(2026, 11, 18, tzinfo=timezone.utc)):
        assert fingerprint(value, engine="rust") == fingerprint(value)


def test_big_integer_runtime_digit_limit_is_not_hidden_by_memo():
    native()
    import sys

    from aiogram_idle.models import ActivityGuard
    from aiogram_idle.storage.receipts import new_canonicalizer

    if not hasattr(sys, "set_int_max_str_digits"):
        pytest.skip("Interpreter has no digit-limit control")
    original = sys.get_int_max_str_digits()
    core = new_canonicalizer()
    value = ActivityGuard("session", "activity", 10**1000)
    try:
        sys.set_int_max_str_digits(0)
        assert core.fingerprint(value) == fingerprint(value)
        sys.set_int_max_str_digits(640)
        for function in (core.fingerprint, fingerprint):
            with pytest.raises(ValueError):
                function(value)
    finally:
        sys.set_int_max_str_digits(original)


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_mapping_items_pairs_use_bounded_iterable_unpacking(count):
    native()
    from collections.abc import Mapping

    class Pairs(Mapping):
        def __iter__(self):
            return iter(())

        def __len__(self):
            return 1

        def __getitem__(self, key):
            raise KeyError(key)

        def items(self):
            yield (item for item in ("key", 7, "extra")[:count])

    if count == 2:
        assert fingerprint(Pairs(), engine="rust") == fingerprint(Pairs())
    else:
        for engine in ("python", "rust"):
            with pytest.raises(ValueError):
                fingerprint(Pairs(), engine=engine)
