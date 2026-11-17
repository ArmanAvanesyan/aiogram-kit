"""Native transport must preserve the complete Python identifier domain."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aiogram_idle._wire import wire


@given(st.text())
def test_wire_matches_json(value: str) -> None:
    assert wire(value) == json.dumps(value, ensure_ascii=True)


@pytest.mark.parametrize(
    "value", ["", "\ud800", "\udfff", "\x00", "\n", 'a"b', "a\\b", "Հայերեն", "printable-token_123"]
)
def test_wire_identifiers(value: str) -> None:
    assert wire(value) == json.dumps(value, ensure_ascii=True)
