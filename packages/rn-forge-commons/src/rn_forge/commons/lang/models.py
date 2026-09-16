"""Strict pydantic models for externally authored documents.

Provides:

- :class:`StrictModel` — a ``BaseModel`` that is strict, frozen and forbids
  unknown keys, with :meth:`StrictModel.parse` as its one entry point.
- :func:`parse_model` — the same parse for any ``BaseModel`` subclass.
- :class:`ModelValidationError` — every failure at once, each named by its
  dotted path.
- :class:`FieldError` — one of those failures.

Requires the ``pydantic`` extra. Not imported by ``rn_forge.commons``'s curated
``__init__.py``; import this module directly.

Example::

    from rn_forge.commons.lang.models import StrictModel

    class Repository(StrictModel):
        name: str
        archetype: str = "python-tool"

    class ProjectConfig(StrictModel):
        repository: Repository

    ProjectConfig.parse(
        {"repository": {"archtype": 1}}, source="config.toml"
    )
    # ModelValidationError: config.toml: 2 invalid key(s)
    #   repository.name: Field required
    #   repository.archtype: Extra inputs are not permitted
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, ValidationError

from rn_forge.commons.exceptions import AppException

__all__ = ["FieldError", "ModelValidationError", "StrictModel", "parse_model"]


@dataclass(frozen=True, slots=True)
class FieldError:
    """One validation failure.

    Args:
        path: The dotted path of the offending key (``repository.name``, or
            ``packages.0`` for a list element). Empty for the document itself.
        message: pydantic's description of the failure.
        kind: pydantic's stable error type (``missing``, ``extra_forbidden``,
            ``string_type``, …).
    """

    path: str
    message: str
    kind: str

    def __str__(self) -> str:
        return f"{self.path or '<root>'}: {self.message}"


class ModelValidationError(AppException):
    """A document failed validation; :attr:`errors` lists every failure.

    Args:
        model: The model the document was validated against.
        errors: Every failure, in pydantic's reporting order.
        source: Where the document came from (a path, say), for the message.
    """

    errors: tuple[FieldError, ...]

    def __init__(
        self,
        model: type[BaseModel],
        errors: tuple[FieldError, ...],
        source: str | None = None,
    ) -> None:
        super().__init__(
            "{}: {} invalid key(s)\n{}",
            source or model.__name__,
            len(errors),
            "\n".join(f"  {error}" for error in errors),
            model=model.__name__,
            paths=[error.path for error in errors],
        )
        self.errors = errors


def parse_model[M: BaseModel](
    model: type[M], data: Mapping[str, Any], *, source: str | None = None
) -> M:
    """Validate *data* against *model*, reporting every failure at once.

    Args:
        model: Any pydantic model class.
        data: The parsed document.
        source: Where *data* came from, named in the error message.

    Returns:
        The validated model instance.

    Raises:
        ModelValidationError: *data* does not satisfy *model*.
    """
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise ModelValidationError(model, _field_errors(error), source) from error


class StrictModel(BaseModel):
    """A pydantic model for configuration documents.

    Strict (no ``"1"`` → ``1`` coercion), frozen, and every key the model does
    not declare is an error. Subclasses may widen :attr:`model_config`.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        strict=True, frozen=True, extra="forbid"
    )

    @classmethod
    def parse(cls, data: Mapping[str, Any], *, source: str | None = None) -> Self:
        """Validate *data* against this model; see :func:`parse_model`.

        Raises:
            ModelValidationError: *data* does not satisfy this model.
        """
        return parse_model(cls, data, source=source)


def _field_errors(error: ValidationError) -> tuple[FieldError, ...]:
    return tuple(
        FieldError(
            path=".".join(str(part) for part in detail["loc"]),
            message=detail["msg"],
            kind=detail["type"],
        )
        for detail in error.errors(include_url=False)
    )
