"""Lossless native string transport without JSON encoding ordinary identifiers."""

import json


def wire(value: str) -> str:
    # Native guards compare escaped strings, preserving unpaired surrogates too.
    # Printable ASCII identifiers need no encoder or temporary encoder options.
    # Subclasses retain JSON encoding without invoking overridden string methods.
    if (
        type(value) is str
        and value.isascii()
        and value.isprintable()
        and '"' not in value
        and "\\" not in value
    ):
        return '"' + value + '"'
    return json.dumps(value, ensure_ascii=True)
