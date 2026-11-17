"""Full fingerprint parity across native serialization and Python reference."""

import math
import random
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from types import MappingProxyType

import pytest

from aiogram_nav.storage.state import fingerprint


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
    pytest.importorskip("aiogram_nav_native")


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
