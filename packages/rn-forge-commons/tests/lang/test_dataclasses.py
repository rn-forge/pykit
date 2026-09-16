"""Tests for rn_forge.commons.lang.dataclasses."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Literal, Optional

import pytest

import rn_forge.commons.lang.dataclasses as dataclasses_module
from rn_forge.commons.exceptions import AppException
from rn_forge.commons.lang.dataclasses import DataclassMixin, LenientDataclassMixin
from rn_forge.commons.findings import Finding, Severity


# ---------------------------------------------------------------------------
# Test dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Simple(DataclassMixin):
    name: str = "test"
    value: int = 42


@dataclass
class WithExcluded(DataclassMixin):
    host: str = "localhost"
    port: int = 8080
    secret: str = field(default="s3cret", metadata={"exclude": True})


@dataclass
class Nested(DataclassMixin):
    label: str = "outer"
    inner: Simple = field(default_factory=Simple)


@dataclass
class DeepNested(DataclassMixin):
    primary: Nested
    aliases: list[Simple] = field(default_factory=list)
    maybe_inner: Optional[Simple] = None


@dataclass(frozen=True)
class Frozen(DataclassMixin):
    x: int = 1
    y: int = 2


@dataclass
class WithDefaults(DataclassMixin):
    required: str = ""
    optional: int = 0
    flag: bool = False


@dataclass
class InnerWithExclude(DataclassMixin):
    value: int = 1
    secret: str = field(default="inner-secret", metadata={"exclude": True})


@dataclass
class PlainInner:
    value: int


@dataclass
class WithCollections(DataclassMixin):
    values: tuple[int, ...]
    tags: set[int]
    mapping: dict[str, int]


@dataclass
class WithUnionSequence(DataclassMixin):
    payload: list[int] | tuple[int, ...]


@dataclass
class UsesPlainInner(DataclassMixin):
    inner: PlainInner


@dataclass
class RaisesOnInit(DataclassMixin):
    value: int

    def __post_init__(self) -> None:
        raise RuntimeError("boom")


@dataclass
class WithDictOfNested(DataclassMixin):
    items: dict[str, Simple]


@dataclass
class Lenient(LenientDataclassMixin):
    name: str = "test"
    value: int = 0


type Status = Literal["pass", "fail"]


@dataclass
class WithAliasField(DataclassMixin):
    status: Status


@dataclass
class WithLenientAliasField(LenientDataclassMixin):
    status: Status


@dataclass
class GenericRecord[T](DataclassMixin):
    items: Sequence[T]


@dataclass
class LenientGenericRecord[T](LenientDataclassMixin):
    items: Sequence[T]


# ---------------------------------------------------------------------------
# as_dict tests
# ---------------------------------------------------------------------------


class TestAsDict:
    def test_basic(self) -> None:
        obj = Simple(name="hello", value=99)
        assert obj.as_dict() == {"name": "hello", "value": 99}

    def test_excludes_hidden_fields(self) -> None:
        obj = WithExcluded()
        d = obj.as_dict()
        assert "host" in d
        assert "port" in d
        assert "secret" not in d

    def test_include_hidden_fields(self) -> None:
        obj = WithExcluded()
        d = obj.as_dict(exclude_hidden=False)
        assert "secret" in d
        assert d["secret"] == "s3cret"

    def test_nested_dataclass(self) -> None:
        obj = Nested()
        d = obj.as_dict()
        assert d == {"label": "outer", "inner": {"name": "test", "value": 42}}

    def test_frozen_dataclass(self) -> None:
        obj = Frozen()
        assert obj.as_dict() == {"x": 1, "y": 2}

    def test_excludes_hidden_fields_recursively(self) -> None:
        @dataclass
        class Outer(DataclassMixin):
            inner: InnerWithExclude = field(default_factory=InnerWithExclude)

        d = Outer().as_dict()
        assert d == {"inner": {"value": 1}}
        assert "secret" not in d["inner"]

    def test_include_hidden_fields_recursively(self) -> None:
        @dataclass
        class Outer(DataclassMixin):
            inner: InnerWithExclude = field(default_factory=InnerWithExclude)

        d = Outer().as_dict(exclude_hidden=False)
        assert d["inner"]["secret"] == "inner-secret"

    def test_not_a_dataclass_raises(self) -> None:
        class NotDC(DataclassMixin):
            pass

        instance = NotDC()
        with pytest.raises(TypeError, match="not a dataclass"):
            instance.as_dict()


# ---------------------------------------------------------------------------
# to_json / to_yaml tests
# ---------------------------------------------------------------------------


class TestJson:
    def test_to_json(self) -> None:
        obj = Simple(name="hello", value=1)
        parsed = json.loads(obj.to_json())
        assert parsed == {"name": "hello", "value": 1}

    def test_to_json_excludes(self) -> None:
        obj = WithExcluded()
        parsed = json.loads(obj.to_json())
        assert "secret" not in parsed

    def test_to_json_with_indent(self) -> None:
        obj = Simple()
        text = obj.to_json(indent=2)
        assert "\n" in text  # indented output has newlines

    def test_from_json(self) -> None:
        text = '{"name": "restored", "value": 7}'
        obj = Simple.from_json(text)
        assert obj.name == "restored"
        assert obj.value == 7

    def test_from_json_ignores_extra_keys(self) -> None:
        text = '{"name": "ok", "value": 1, "unknown": "ignored"}'
        obj = Simple.from_json(text)
        assert obj.name == "ok"
        assert not hasattr(obj, "unknown")


class TestYaml:
    def test_to_yaml(self) -> None:
        obj = Simple(name="hello", value=1)
        text = obj.to_yaml()
        assert "name: hello" in text
        assert "value: 1" in text

    def test_to_yaml_excludes(self) -> None:
        obj = WithExcluded()
        text = obj.to_yaml()
        assert "secret" not in text

    def test_from_yaml(self) -> None:
        text = "name: restored\nvalue: 7\n"
        obj = Simple.from_yaml(text)
        assert obj.name == "restored"
        assert obj.value == 7

    def test_from_yaml_ignores_extra_keys(self) -> None:
        text = "name: ok\nvalue: 1\nextra: ignored\n"
        obj = Simple.from_yaml(text)
        assert obj.name == "ok"


# ---------------------------------------------------------------------------
# from_dict tests
# ---------------------------------------------------------------------------


class TestFromDict:
    def test_basic(self) -> None:
        obj = Simple.from_dict({"name": "abc", "value": 10})
        assert obj.name == "abc"
        assert obj.value == 10

    def test_ignores_unknown_keys(self) -> None:
        obj = Simple.from_dict({"name": "abc", "value": 10, "extra": "nope"})
        assert obj.name == "abc"
        assert not hasattr(obj, "extra")

    def test_uses_defaults_for_missing_keys(self) -> None:
        obj = WithDefaults.from_dict({"required": "yes"})
        assert obj.required == "yes"
        assert obj.optional == 0
        assert obj.flag is False

    def test_recursively_restores_nested_dataclasses(self) -> None:
        obj = DeepNested.from_dict(
            {
                "primary": {
                    "label": "outer-1",
                    "inner": {"name": "nested", "value": 7},
                },
                "aliases": [{"name": "a", "value": 1}, {"name": "b", "value": 2}],
                "maybe_inner": {"name": "optional", "value": 3},
            }
        )
        assert isinstance(obj.primary, Nested)
        assert isinstance(obj.primary.inner, Simple)
        assert obj.primary.inner.name == "nested"
        assert [alias.name for alias in obj.aliases] == ["a", "b"]
        assert all(isinstance(alias, Simple) for alias in obj.aliases)
        assert isinstance(obj.maybe_inner, Simple)
        assert obj.maybe_inner.value == 3

    def test_frozen_from_dict(self) -> None:
        obj = Frozen.from_dict({"x": 10, "y": 20})
        assert obj.x == 10
        assert obj.y == 20

    def test_not_a_dataclass_raises(self) -> None:
        class NotDC(DataclassMixin):
            pass

        with pytest.raises(TypeError, match="not a dataclass"):
            NotDC.from_dict({"a": 1})

    def test_from_dict_constructor_error_propagates(self) -> None:
        with pytest.raises(RuntimeError, match="boom"):
            RaisesOnInit.from_dict({"value": 1})

    def test_from_dict_coerces_collections(self) -> None:
        obj = WithCollections.from_dict(
            {
                "values": [1, 2],
                "tags": [3, 4],
                "mapping": {"a": 7},
            }
        )
        assert obj.values == (1, 2)
        assert obj.tags == {3, 4}
        assert obj.mapping == {"a": 7}

    def test_from_dict_union_sequence_prefers_matching_arm(self) -> None:
        obj = WithUnionSequence.from_dict({"payload": [1, 2, 3]})
        assert obj.payload == [1, 2, 3]

    def test_from_dict_constructs_plain_nested_dataclass(self) -> None:
        obj = UsesPlainInner.from_dict({"inner": {"value": 9}})
        assert isinstance(obj.inner, PlainInner)
        assert obj.inner.value == 9

    def test_from_dict_int_field_receiving_str_is_rejected(self) -> None:
        with pytest.raises(AppException, match="Invalid Simple"):
            Simple.from_dict({"name": "n", "value": "5"})

    def test_from_dict_missing_required_field_is_rejected(self) -> None:
        with pytest.raises(AppException, match="Invalid WithDictOfNested"):
            WithDictOfNested.from_dict({})

    def test_lenient_subclass_passes_a_mismatched_value_through(self) -> None:
        obj = Lenient.from_dict({"name": "n", "value": "5"})
        assert obj.value == "5"

    def test_optional_nested_dataclass_from_none(self) -> None:
        obj = DeepNested.from_dict(
            {"primary": {"label": "outer", "inner": {}}, "maybe_inner": None}
        )
        assert obj.maybe_inner is None

    def test_optional_nested_dataclass_from_dict(self) -> None:
        obj = DeepNested.from_dict(
            {
                "primary": {"label": "outer", "inner": {}},
                "maybe_inner": {"name": "x", "value": 1},
            }
        )
        assert isinstance(obj.maybe_inner, Simple)
        assert obj.maybe_inner.name == "x"

    def test_dict_of_nested_dataclass_round_trips(self) -> None:
        obj = WithDictOfNested.from_dict(
            {"items": {"a": {"name": "a", "value": 1}, "b": {"name": "b", "value": 2}}}
        )
        assert set(obj.items) == {"a", "b"}
        assert all(isinstance(v, Simple) for v in obj.items.values())
        assert obj.items["a"].value == 1
        round_tripped = WithDictOfNested.from_dict(obj.as_dict())
        assert round_tripped == obj

    def test_list_of_nested_dataclass_round_trips(self) -> None:
        obj = DeepNested.from_dict(
            {
                "primary": {"label": "outer", "inner": {}},
                "aliases": [{"name": "a", "value": 1}, {"name": "b", "value": 2}],
            }
        )
        round_tripped = DeepNested.from_dict(obj.as_dict())
        assert round_tripped == obj


# ---------------------------------------------------------------------------
# __str__ / __repr__ tests
# ---------------------------------------------------------------------------


class TestStringRepresentation:
    def test_str_is_json(self) -> None:
        obj = Simple(name="hello", value=1)
        parsed = json.loads(str(obj))
        assert parsed == {"name": "hello", "value": 1}

    def test_str_excludes_hidden(self) -> None:
        obj = WithExcluded()
        assert "secret" not in str(obj)

    def test_repr_format(self) -> None:
        obj = Simple(name="hello", value=1)
        r = repr(obj)
        assert r == "Simple(name='hello', value=1)"

    def test_repr_excludes_hidden(self) -> None:
        obj = WithExcluded()
        r = repr(obj)
        assert "secret" not in r
        assert "host" in r

    def test_user_defined_repr_is_preserved(self) -> None:
        @dataclass
        class CustomRepr(DataclassMixin):
            x: int = 1

            def __repr__(self) -> str:
                return "custom"

        assert repr(CustomRepr()) == "custom"

    def test_repr_non_dataclass_falls_back(self) -> None:
        class NotDC(DataclassMixin):
            pass

        assert "NotDC object" in repr(NotDC())


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_json_round_trip(self) -> None:
        original = Simple(name="round", value=99)
        restored = Simple.from_json(original.to_json())
        assert restored.name == original.name
        assert restored.value == original.value

    def test_yaml_round_trip(self) -> None:
        original = Simple(name="round", value=99)
        restored = Simple.from_yaml(original.to_yaml())
        assert restored.name == original.name
        assert restored.value == original.value

    def test_dict_round_trip(self) -> None:
        original = WithExcluded(host="example.com", port=443, secret="pw")
        d = original.as_dict()  # excludes secret
        restored = WithExcluded.from_dict(d)
        assert restored.host == "example.com"
        assert restored.port == 443
        assert restored.secret == "s3cret"  # default, since excluded from dict


class TestInternalHelpers:
    def test_convert_value_handles_tuple(self) -> None:
        result = dataclasses_module._convert_value((1, 2), exclude_hidden=True)
        assert result == (1, 2)

    def test_convert_value_preserves_frozenset(self) -> None:
        result = dataclasses_module._convert_value(
            frozenset({1, 2}),
            exclude_hidden=True,
        )
        assert result == frozenset({1, 2})

    def test_convert_value_handles_set(self) -> None:
        result = dataclasses_module._convert_value({1, 2}, exclude_hidden=True)
        assert result == {1, 2}

    def test_convert_value_handles_dict(self) -> None:
        result = dataclasses_module._convert_value({"a": 1}, exclude_hidden=True)
        assert result == {"a": 1}

    def test_convert_value_preserves_type_objects(self) -> None:
        assert dataclasses_module._convert_value(5, exclude_hidden=True) == 5


# Coverage ROI notes:
# - Trace-level logging branches are exercised incidentally; tests stay focused
#   on coercion behavior rather than log record formatting.


class Colour(StrEnum):
    RED = "red"
    BLUE = "blue"


class Shape(Enum):
    ROUND = "round"


@dataclass
class Paint(DataclassMixin):
    colour: Colour


@dataclass
class Thing(DataclassMixin):
    shape: Shape


class TestEnumFields:
    """Enum-typed fields must survive a round trip as members, not strings."""

    def test_str_enum_round_trips_as_a_member(self):
        restored = Paint.from_json(Paint(colour=Colour.RED).to_json())
        assert restored.colour is Colour.RED

    def test_plain_enum_round_trips_as_a_member(self):
        assert Thing.from_dict({"shape": "round"}).shape is Shape.ROUND

    def test_unknown_enum_value_is_rejected(self):
        with pytest.raises(AppException, match="Invalid Paint"):
            Paint.from_dict({"colour": "puce"})

    def test_finding_severity_survives_a_json_round_trip(self):
        finding = Finding(code="a.b", severity=Severity.ERROR, message="boom")
        restored = Finding.from_json(finding.to_json())
        assert restored.severity is Severity.ERROR
        assert restored.is_error


class TestDaciteCannotCheck:
    """Pin the two annotations dacite's type check cannot see through.

    Both are documented in the module docstring as the reason a record uses
    `LenientDataclassMixin`. A dacite release that fixes either fails here,
    which is the signal to move those records back onto the strict base.
    """

    def test_a_pep695_alias_is_rejected_even_when_the_value_matches(self) -> None:
        with pytest.raises(AppException, match="Invalid WithAliasField"):
            WithAliasField.from_dict({"status": "pass"})

    def test_a_pep695_alias_parses_under_the_lenient_mixin(self) -> None:
        assert WithLenientAliasField.from_dict({"status": "pass"}).status == "pass"

    def test_an_unbound_type_var_is_rejected(self) -> None:
        with pytest.raises(AppException, match="Invalid GenericRecord"):
            GenericRecord.from_dict({"items": [1, 2]})

    def test_an_unbound_type_var_parses_under_the_lenient_mixin(self) -> None:
        assert LenientGenericRecord.from_dict({"items": [1, 2]}).items == [1, 2]
