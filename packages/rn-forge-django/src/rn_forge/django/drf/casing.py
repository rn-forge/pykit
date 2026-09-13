"""camelCase on the wire, ``snake_case`` in Python.

The rule, normative for every ``rn-forge-*`` framework package: **camelCase
out, both spellings accepted in.** A client posting ``pageSize`` and an internal
caller posting ``page_size`` both work, which matches the FastAPI side's
``populate_by_name``.

Name these in ``REST_FRAMEWORK`` so the rule holds by default rather than per
serializer::

    REST_FRAMEWORK = {
        "DEFAULT_RENDERER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONRenderer"],
        "DEFAULT_PARSER_CLASSES": ["rn_forge.django.drf.casing.CamelCaseJSONParser"],
    }

``RN_FORGE_DJANGO["DRF"]["CASING"]["ENABLED"] = False`` makes both behave as
DRF's plain JSON renderer and parser, for a consumer with a reason.

Opaque values
-------------

Global casing recurses into every nested mapping, which mangles a JSON value
whose keys must stay verbatim — a vendor payload, a mapping keyed by SKU.
Declare such a field as
:class:`~rn_forge.django.drf.serializers.fields.RawPassthroughField`: the
renderer leaves its value alone, and the parser skips it, by field name, for
the view's serializer.

Why this is hand-written
------------------------

``djangorestframework-camel-case`` was evaluated as the dependency and not
taken: its last release is 1.4.2 (2023-02), its classifiers stop at Python
3.10, and it is marked pre-alpha. The two key transforms and the two recursive
walks below are the whole of what an API needs from it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final, cast, override

from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rn_forge.django import settings as rnf_settings

__all__ = [
    "CamelCaseJSONParser",
    "CamelCaseJSONRenderer",
    "RawDict",
    "RawList",
    "camelize",
    "camelize_key",
    "underscore_key",
    "underscoreize",
]

_UNDERSCORE_LETTER: Final = re.compile(r"(?<=[a-zA-Z0-9])_([a-zA-Z0-9])")
_LOWER_UPPER: Final = re.compile(r"(?<=[a-z0-9])([A-Z])")


class RawDict(dict[str, Any]):
    """A mapping the camelCase renderer must not re-key. See the module docstring."""


class RawList(list[Any]):
    """A list the camelCase renderer must not descend into."""


def camelize_key(key: str) -> str:
    """``page_size`` → ``pageSize``. Leading underscores are kept."""
    return _UNDERSCORE_LETTER.sub(lambda match: match.group(1).upper(), key)


def underscore_key(key: str) -> str:
    """``pageSize`` → ``page_size``. A key already in ``snake_case`` is unchanged."""
    return _LOWER_UPPER.sub(lambda match: f"_{match.group(1).lower()}", key)


def camelize(data: Any) -> Any:
    """Recursively camelCase every string key, skipping :class:`RawDict`/:class:`RawList`."""
    if isinstance(data, (RawDict, RawList)):
        return data
    if isinstance(data, Mapping):
        return {
            camelize_key(key) if isinstance(key, str) else key: camelize(value)
            for key, value in cast(Mapping[Any, Any], data).items()
        }
    if isinstance(data, (list, tuple)):
        return [camelize(item) for item in cast(list[Any], data)]
    return data


def underscoreize(data: Any, *, opaque: frozenset[str] = frozenset()) -> Any:
    """Recursively snake_case every string key.

    Args:
        data: Parsed JSON.
        opaque: Field names (in ``snake_case``) whose values are passed through
            untouched, at any depth.
    """
    if isinstance(data, Mapping):
        result: dict[Any, Any] = {}
        for key, value in cast(Mapping[Any, Any], data).items():
            name = underscore_key(key) if isinstance(key, str) else key
            result[name] = (
                value if name in opaque else underscoreize(value, opaque=opaque)
            )
        return result
    if isinstance(data, list):
        return [underscoreize(item, opaque=opaque) for item in cast(list[Any], data)]
    return data


def _casing_enabled() -> bool:
    return rnf_settings.rn_forge_django_settings.drf.casing.enabled


class CamelCaseJSONRenderer(JSONRenderer):
    """DRF's JSON renderer, camelCasing keys on the way out."""

    @override
    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, Any] | None = None,
    ) -> bytes:
        payload = camelize(data) if _casing_enabled() else data
        return super().render(payload, accepted_media_type, renderer_context)  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave render's parameters untyped


class CamelCaseJSONParser(JSONParser):
    """DRF's JSON parser, accepting camelCase or ``snake_case`` keys."""

    @override
    def parse(
        self,
        stream: Any,
        media_type: str | None = None,
        parser_context: Mapping[str, Any] | None = None,
    ) -> Any:
        data = super().parse(stream, media_type, parser_context)  # pyright: ignore[reportUnknownMemberType]  # DRF stubs leave parse's parameters untyped
        if not _casing_enabled():
            return data
        return underscoreize(data, opaque=_opaque_field_names(parser_context))


def _opaque_field_names(parser_context: Mapping[str, Any] | None) -> frozenset[str]:
    """Names of every ``RawPassthroughField`` declared on the view's serializer tree."""
    view = (parser_context or {}).get("view")
    get_serializer_class = getattr(view, "get_serializer_class", None)
    if get_serializer_class is None:
        return frozenset()
    try:
        serializer_class = cast(type[object], get_serializer_class())
    except AssertionError:  # DRF asserts when a view declares no serializer_class
        return frozenset()
    names: set[str] = set()
    _collect_opaque(serializer_class, names)
    return frozenset(names)


def _collect_opaque(serializer_class: type[object], names: set[str]) -> None:
    declared = cast(
        Mapping[str, Any], getattr(serializer_class, "_declared_fields", {})
    )
    for name, field in declared.items():
        if getattr(field, "raw_passthrough", False):
            names.add(name)
        nested = getattr(field, "child", field)
        if nested is not field or hasattr(nested, "_declared_fields"):
            _collect_opaque(cast(type[object], type(nested)), names)
