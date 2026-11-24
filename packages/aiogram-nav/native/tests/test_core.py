"""Independent native contract parity; the base library is not required."""

import hashlib
import json
import math

import aiogram_nav_native as native
import pytest


def test_versions():
    assert native.API_VERSION == 1
    assert native.ENGINE_VERSION == "0.3.3"


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        0,
        -1,
        2**200,
        -(2**200),
        1.0,
        -0.0,
        1e-200,
        1e200,
        "Հայերեն 😀",
        {"a": [1, "x", None], "Ω": 2**100},
    ],
)
def test_json_and_fingerprint_preserve_python_scalar_domain(value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
    result = native.strict_loads(raw)
    assert result == json.loads(raw)
    if isinstance(value, float):
        assert type(result) is float
        assert math.copysign(1, result) == math.copysign(1, value)
    for ensure_ascii in (True, False):
        canonical = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=ensure_ascii, allow_nan=False
        )
        assert (
            native.fingerprint_canonical(canonical)
            == hashlib.sha256(canonical.encode()).hexdigest()
        )


@pytest.mark.parametrize(
    "raw",
    [
        '{"a":1,"a":2}',
        '{"a":1,"\\u0061":2}',
        '{"x":{"a":1,"a":2}}',
        "NaN",
        "Infinity",
        "-Infinity",
        "1e400",
        '"\\ud800"',
        '"\\udfff"',
        "[1,]",
        '{"a":1,}',
        "true false",
        "01",
        "[",
        "",
    ],
)
def test_malformed_json_is_rejected(raw):
    with pytest.raises(ValueError):
        native.strict_loads(raw)


def test_limits_and_strict_strings():
    with pytest.raises(ValueError):
        native.strict_loads('"é"', max_bytes=3)
    with pytest.raises(ValueError):
        native.strict_loads("[[[0]]]", max_depth=2)
    assert native.strict_loads('"\\ud83d\\ude00"') == "😀"
    assert native.strict_loads('{"escaped\\"key":"\\\\"}') == {'escaped"key': "\\"}


def registry():
    return {
        "roots": ["main"],
        "nodes": [
            {"id": "main", "parent": None, "renderer": "r", "back_to": None, "cancel_to": None},
            {
                "id": "settings",
                "parent": "main",
                "renderer": "r",
                "back_to": None,
                "cancel_to": "main",
            },
            {
                "id": "settings.language",
                "parent": "settings",
                "renderer": "r",
                "back_to": "settings",
                "cancel_to": None,
            },
        ],
        "migrations": {"old.language": "settings.language"},
        "safe_root": "main",
    }


def test_registry_cached_graph_and_targets():
    graph = native.Registry(json.dumps(registry()))
    assert graph.ancestors("settings.language") == ["settings.language", "settings", "main"]
    assert graph.root_for("settings.language") == "main"
    assert graph.back_target("settings.language") == "settings"
    assert graph.cancel_target("settings.language") == "main"
    assert graph.resolve("old.language") == "settings.language"
    assert graph.resolve("missing") == "main"
    assert graph.node_count() == 3
    with pytest.raises(KeyError):
        graph.ancestors("missing")


@pytest.mark.parametrize("kind", ["cycle", "missing", "duplicate", "target", "root", "migration"])
def test_registry_invalid_graph(kind):
    spec = registry()
    if kind == "cycle":
        spec["nodes"][1]["parent"] = "settings.language"
    elif kind == "missing":
        spec["nodes"][1]["parent"] = "missing"
    elif kind == "duplicate":
        spec["nodes"].append(spec["nodes"][0])
    elif kind == "target":
        spec["nodes"][1]["cancel_to"] = "missing"
    elif kind == "root":
        spec["roots"] = []
    else:
        spec["migrations"] = {"main": "main"}
    with pytest.raises(ValueError):
        native.Registry(json.dumps(spec))


@pytest.mark.parametrize(
    "mode,pop,push,expected",
    [
        ("push", 1, True, [2, 3]),
        ("push", 1, False, [1, 2]),
        ("pop", 1, True, [1]),
        ("pop", 0, True, [1, 2]),
        ("pop", 10, True, []),
        ("clear", 1, True, []),
        ("none", 1, True, [1, 2]),
    ],
)
def test_history_reducer(mode, pop, push, expected):
    assert json.loads(native.transition_history("[1,2]", "3", mode, 2, pop, push)) == expected
    assert json.loads(native.transition_history("[1,2]", "3", mode, 0, pop, push)) == []


def test_state_reducer_preserves_entry_and_activity_time():
    old = {
        "node_id": "main",
        "nav_revision": 5,
        "activity_revision": 2,
        "entered_at": 10,
        "last_activity_at": 20,
    }
    assert json.loads(native.transition_state(json.dumps(old), "main", False, False, "100")) == {
        "nav_revision": 6,
        "activity_revision": 2,
        "entered_at": 10,
        "last_activity_at": 20,
    }
    assert json.loads(native.transition_state(json.dumps(old), "other", False, True, "100")) == {
        "nav_revision": 6,
        "activity_revision": 3,
        "entered_at": 100,
        "last_activity_at": 100,
    }
    assert json.loads(native.transition_state(None, "main", False, False, "100")) == {
        "nav_revision": 1,
        "activity_revision": 1,
        "entered_at": 100,
        "last_activity_at": 100,
    }


def test_token_provenance_and_expiry():
    args = ["key", "key", "42", "42", "session", "session", "view", "view", "101", "100"]
    assert native.token_matches(*args)
    for index in (0, 2, 4, 6, 8):
        bad = args.copy()
        bad[index] = "100" if index == 8 else "43" if index == 2 else "foreign"
        assert not native.token_matches(*bad)


def test_state_and_token_arbitrary_integer_domain():
    huge = 10**100
    old = {
        "node_id": "main",
        "nav_revision": huge,
        "activity_revision": huge,
        "entered_at": huge,
        "last_activity_at": huge,
    }
    result = json.loads(
        native.transition_state(json.dumps(old), "main", False, True, str(huge + 10))
    )
    assert result["nav_revision"] == huge + 1 and result["last_activity_at"] == huge + 10
    assert native.token_matches(
        "k", "k", str(huge), str(huge), "s", "s", "v", "v", str(huge + 1), str(huge)
    )


def test_mapping_order_is_preserved():
    assert list(native.strict_loads('{"z":0,"a":1,"m":2}')) == ["z", "a", "m"]


def test_json_property_parity():
    from hypothesis import given, settings
    from hypothesis import strategies as st

    scalar = (
        st.none()
        | st.booleans()
        | st.integers(min_value=-(2**300), max_value=2**300)
        | st.floats(allow_nan=False, allow_infinity=False)
        | st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=30)
    )
    values = st.recursive(
        scalar,
        lambda child: (
            st.lists(child, max_size=8)
            | st.dictionaries(
                st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=10),
                child,
                max_size=8,
            )
        ),
        max_leaves=30,
    )

    @given(values)
    @settings(max_examples=200, deadline=None)
    def check(value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
        assert native.strict_loads(raw) == json.loads(raw)

    check()


def test_tagged_codec_depth_is_not_serde_default_recursion_limit():
    raw = "[" * 140 + "0" + "]" * 140
    native.strict_loads(raw, max_depth=512)
    with pytest.raises(ValueError):
        native.strict_loads(raw, max_depth=128)


def test_large_chain_keeps_linear_compiled_state_and_resolves_end():
    count = 5000
    nodes = [
        {
            "id": f"n{i}",
            "parent": f"n{i - 1}" if i else None,
            "renderer": "r",
            "back_to": None,
            "cancel_to": None,
        }
        for i in range(count)
    ]
    graph = native.Registry(
        json.dumps({"roots": ["n0"], "nodes": nodes, "migrations": {}, "safe_root": None})
    )
    assert graph.node_count() == count
    assert graph.root_for("n4999") == "n0"
    assert len(graph.ancestors("n4999")) == count


def test_registry_graph_property_against_reference():
    from hypothesis import given, settings
    from hypothesis import strategies as st

    @given(st.lists(st.integers(min_value=0, max_value=100), max_size=80))
    @settings(max_examples=100, deadline=None)
    def check(parents):
        nodes = [{"id": "n0", "parent": None, "renderer": "r", "back_to": None, "cancel_to": None}]
        for i, parent in enumerate(parents, 1):
            nodes.append(
                {
                    "id": f"n{i}",
                    "parent": f"n{parent % i}",
                    "renderer": "r",
                    "back_to": None,
                    "cancel_to": "n0" if i % 4 == 0 else None,
                }
            )
        spec = {"roots": ["n0"], "nodes": nodes, "migrations": {}, "safe_root": None}
        graph = native.Registry(json.dumps(spec))
        index = {n["id"]: n for n in nodes}
        for node in nodes:
            path = [node["id"]]
            current = node
            while current["parent"] is not None:
                current = index[current["parent"]]
                path.append(current["id"])
            assert graph.ancestors(node["id"]) == path
            assert graph.root_for(node["id"]) == "n0"
            assert graph.cancel_target(node["id"]) == "n0"

    check()


@pytest.mark.parametrize(
    "mode,pop,limit",
    [
        (mode, pop, limit)
        for mode in ("push", "pop", "clear", "none")
        for pop in (0, 1, 3)
        for limit in (0, 1, 3)
    ],
)
def test_object_transition_matches_json_boundary(mode, pop, limit):
    entries = ({"node": "a", "params": {"value": [1, 2]}}, {"node": "b"})
    current = {"node": "c", "params": {"large": 2**200}}
    expected = json.loads(
        native.transition_history(json.dumps(entries), json.dumps(current), mode, limit, pop, True)
    )
    actual, state = native.transition_values(
        entries, current, mode, limit, pop, True, (str(2**200), "4", "5", "6"), True, "10"
    )
    assert actual == expected
    assert tuple(map(int, state)) == (2**200 + 1, 5, 10, 10)
    assert entries == ({"node": "a", "params": {"value": [1, 2]}}, {"node": "b"})
    # The native boundary borrows opaque objects, without JSON reconstruction.
    for entry in actual:
        assert any(entry is item for item in (*entries, current))


def test_object_transition_first_entry_and_rejections():
    assert native.transition_values((), None, "none", 0, 0, True, None, False, "10") == (
        [],
        ("1", "1", "10", "10"),
    )
    for kwargs in (
        {"mode": "invalid"},
        {"limit": 1001},
        {"pop": 1001},
        {"now": "-1"},
        {"previous": ("-1", "1", "1", "1")},
    ):
        args = dict(
            history=(),
            current=None,
            mode="none",
            limit=1,
            pop=1,
            changed=False,
            previous=("1", "1", "1", "1"),
            accepted=False,
            now="10",
        )
        args.update(kwargs)
        with pytest.raises(ValueError):
            native.transition_values(**args)


@pytest.mark.parametrize(
    "raw",
    [
        "0",
        "-0",
        "0.0",
        "-0.0",
        "1e-999",
        "-1e-999",
        "1.7976931348623157e308",
        "2.2250738585072014e-308",
        "4.9406564584124654e-324",
        "9007199254740993.0",
        "18446744073709551616",
        "-9223372036854775809",
        "1" + "0" * 1000,
        '{"z":true,"a":[null,false,{},[],"Հայերեն😀"]}',
        ' \r\n {"escaped\\u0020key":"\\ud83d\\ude00"}\t ',
    ],
)
def test_direct_strict_materialization_preserves_scalar_semantics(raw):
    import json
    import math

    expected = json.loads(raw)
    actual = native.strict_loads(raw)
    assert actual == expected
    assert type(actual) is type(expected)
    if isinstance(expected, float) and expected == 0:
        assert math.copysign(1, actual) == math.copysign(1, expected)
    if isinstance(expected, dict):
        assert list(actual) == list(expected)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "+1",
        "00",
        "-00",
        "01",
        ".1",
        "1.",
        "-.1",
        "1e",
        "1e+",
        "1e-",
        "1e999",
        "-1e999",
        "NaN",
        "Infinity",
        "truefalse",
        "null0",
        "[0,]",
        '{"a":0,}',
        '{"a":0,"\\u0061":1}',
        '"\\ud800"',
        '"\\udfff"',
        '"\\x20"',
        '"a\nb"',
        '{"a" 0}',
        "[1 2]",
        '{"a":}',
        "[",
        "{",
        '"unterminated',
    ],
)
def test_direct_strict_materialization_retains_existing_rejection_policy(raw):
    with pytest.raises(ValueError):
        native.validate_json(raw)
    with pytest.raises(ValueError):
        native.strict_loads(raw)


def test_direct_integer_decode_observes_python_digit_limit():
    import sys

    if not hasattr(sys, "set_int_max_str_digits"):
        pytest.skip("Runtime integer digit limit unavailable")
    old = sys.get_int_max_str_digits()
    raw = "9" * 1000
    try:
        sys.set_int_max_str_digits(640)
        with pytest.raises(ValueError):
            native.strict_loads(raw)
        sys.set_int_max_str_digits(0)
        assert native.strict_loads(raw) == int(raw)
    finally:
        sys.set_int_max_str_digits(old)


def test_public_coarse_codec_exports_match_extension_and_typed_api():
    import aiogram_nav_native as public

    assert public.Canonicalizer is native.Canonicalizer
    assert public.InvalidJson is native.InvalidJson
    assert issubclass(public.InvalidJson, ValueError)
    for method in ("fork", "fingerprint", "freeze", "clear_cache", "cache_stats"):
        assert callable(getattr(public.Canonicalizer, method))


def test_replace_history_mode_preserves_stack_and_applies_bound():
    import json

    assert json.loads(native.transition_history("[1,2]", "3", "replace", 1)) == [2]
    entries, state = native.transition_values(
        (1, 2), 3, "replace", 1, 1, True, ("1", "1", "100", "100"), True, "200"
    )
    assert entries == [2]
    assert state == ("2", "2", "200", "200")
