"""Fast transport remains lossless and does not bypass malformed JSON checks."""

import json

import pytest

from aiogram_idle._native_queue import _unwire
from aiogram_idle._wire import wire


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc_-012",
        "Հայերեն",
        "😀",
        "\ud800",
        'a"b',
        "a\\b",
        "\n",
        "\x00",
        "\x7f",
        " " * 100,
        "A" * 1024,
    ],
)
def test_unwire_round_trip_matches_json(value):
    encoded = wire(value)
    assert _unwire(encoded) == json.loads(encoded) == value


@pytest.mark.parametrize("raw", ['"a"b"', '"a\n"', '"a\\q"', '"unterminated', '"a" trailing'])
def test_malformed_tokens_do_not_bypass_decoder(raw):
    with pytest.raises(json.JSONDecodeError):
        _unwire(raw)


def test_subclasses_do_not_invoke_overridden_accessors():
    class Text(str):
        def __getitem__(self, index):
            raise AssertionError("subclass fast path")

        def isascii(self):
            raise AssertionError("subclass fast path")

    assert _unwire(Text('"valid"')) == "valid"
