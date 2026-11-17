"""Native transport must preserve the complete Python identifier domain."""

import json
import random

import pytest

from aiogram_idle._wire import wire


def test_wire_matches_json() -> None:
    rng = random.Random(137)
    values = [chr(codepoint) for codepoint in range(256)]
    values.extend(
        "".join(chr(rng.randrange(0x110000)) for _ in range(rng.randrange(65))) for _ in range(1000)
    )
    for value in values:
        assert wire(value) == json.dumps(value, ensure_ascii=True)


@pytest.mark.parametrize(
    "value",
    ["", "\ud800", "\udfff", "\x00", "\n", 'a"b', "a\\b", "Հայերեն", "printable-token_123"],
)
def test_wire_identifiers(value: str) -> None:
    assert wire(value) == json.dumps(value, ensure_ascii=True)


def test_string_subclasses_use_the_original_json_encoder() -> None:
    class Identifier(str):
        def isascii(self) -> bool:
            raise AssertionError("Fast-path methods must not be dispatched on subclasses")

        def isprintable(self) -> bool:
            raise AssertionError("Fast-path methods must not be dispatched on subclasses")

        def __radd__(self, value: str) -> str:
            raise AssertionError("Subclass concatenation must not replace encoded contents")

    for value in (Identifier("identifier"), Identifier('line\n"Հայերեն')):
        assert wire(value) == json.dumps(value, ensure_ascii=True)
