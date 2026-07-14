"""Abstract Django model building blocks.

Provides:

- :class:`NaturalKeyLookupManager` — Manager that resolves natural keys for
  fixture loading.
- :class:`TruncateModelMixin` — ``TRUNCATE TABLE`` helper, useful for test
  teardown.
- :class:`FixtureModelMixin` — Abstract contract that declares the
  ``natural_keys()`` class method.
- :class:`BaseModel` — Abstract model with status, audit timestamps, and
  natural-key support.
- :class:`DateModel` — Abstract model extending :class:`BaseModel` with a
  single date field.
- :class:`DateRangeModel` — Abstract model extending :class:`BaseModel` with
  ``start_date`` / ``end_date`` and an ``is_date_range_active`` property.
"""

from __future__ import annotations

from datetime import date
from operator import attrgetter
from typing import Any, Iterable, cast, override

from rn_forge.commons.logging import AppLogger
from rn_forge.django.models._meta import get_model_meta
from rn_forge.django.models.enums import Status
from rn_forge.django.models.fields import EnumField

from django.db import connection, models

__all__ = [
    "BaseModel",
    "DateModel",
    "DateRangeModel",
    "FixtureModelMixin",
    "NaturalKeyLookupManager",
    "TruncateModelMixin",
]

_LOGGER = AppLogger.get_logger(__name__)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class NaturalKeyLookupManager(models.Manager):
    """Manager that supports natural-key deserialization in Django fixtures.

    The model must implement :meth:`FixtureModelMixin.natural_keys`.
    """

    def get_by_natural_key(self, *values: str) -> "BaseModel":
        natural_keys = self.model.natural_keys()
        if len(values) != len(natural_keys):
            raise RuntimeError(
                f"Incorrect natural keys: expected {len(natural_keys)}, "
                f"got {len(values)} — {values!r}"
            )
        return self.get(**dict(zip(natural_keys, values)))


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class TruncateModelMixin:
    """Mixin that adds a ``truncate()`` class method for DDL-level table clearing.

    Useful for test teardown. Issues a raw ``TRUNCATE TABLE`` statement; use
    with care in production.
    """

    @classmethod
    def truncate(cls) -> None:
        """Truncate the table backing this model.

        Uses ``TRUNCATE TABLE`` on backends that support it (PostgreSQL, MySQL).
        Falls back to ``DELETE FROM`` on SQLite, which does not support TRUNCATE.
        """
        _LOGGER.warning("TruncateModelMixin.truncate: {}", cls.__name__)
        table = connection.ops.quote_name(get_model_meta(cls).db_table)
        if connection.vendor == "sqlite":
            sql = f"DELETE FROM {table}"
        else:
            sql = f"TRUNCATE TABLE {table}"
        with connection.cursor() as cursor:
            cursor.execute(sql)


class FixtureModelMixin:
    """Abstract mixin that declares the ``natural_keys()`` contract."""

    @classmethod
    def natural_keys(cls) -> list[str]:
        """Return the list of field names that form this model's natural key.

        Used by :class:`NaturalKeyLookupManager` to resolve fixture references.
        Consumers should treat the corresponding :meth:`natural_key` values as a
        tuple even when only one field name is returned here.
        """
        raise NotImplementedError(f"natural_keys not implemented: {cls.__name__}")

    def natural_key(self) -> tuple[Any, ...]:
        """Return the current instance values for :meth:`natural_keys`.

        Dotted attribute paths are supported. Legacy Django-style
        ``"relation__field"`` paths are accepted and converted to standard
        attribute traversal. Single natural-key values are normalized to a
        one-element tuple so callers always receive tuple-shaped output.
        """
        getter = attrgetter(*(key.replace("__", ".") for key in self.natural_keys()))
        result = cast(object | tuple[Any, ...], getter(self))
        if isinstance(result, tuple):
            return cast(tuple[Any, ...], result)
        return (result,)


# ---------------------------------------------------------------------------
# Abstract Base Models
# ---------------------------------------------------------------------------


class BaseModel(
    models.Model,
    TruncateModelMixin,
    FixtureModelMixin,
):
    """Abstract base model with status field and audit timestamps.

    All concrete models should inherit from this class. The default manager
    (:attr:`objects`) is :class:`NaturalKeyLookupManager`, which enables
    natural-key fixture loading.

    Field names use snake_case. The underlying database columns preserve the
    original camelCase names for backwards compatibility.
    """

    status = EnumField.build(
        enum_type=Status,
        default=Status.Active,
    )
    created_by = models.CharField(max_length=255, db_column="createdBy")
    created_at = models.DateTimeField(auto_now_add=True, db_column="createdAt")
    updated_by = models.CharField(max_length=255, db_column="updatedBy")
    updated_at = models.DateTimeField(auto_now=True, db_column="updatedAt")

    objects = NaturalKeyLookupManager()
    validate_on_save = False

    class Meta:
        abstract = True

    def get_attrs(self, attr_getter: attrgetter[Any]) -> tuple[Any]:
        """Return a tuple of attribute values extracted by *attr_getter*."""
        result = cast(object | tuple[Any, ...], attr_getter(self))
        if isinstance(result, tuple):
            return cast(tuple[Any, ...], result)
        return (result,)

    @override
    def save(
        self,
        *,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """Optionally run model validation, then delegate to ``super().save()``.

        The explicit ``full_clean`` call is kept here because this library
        allows models to opt into validation-on-save, and Django's current
        stubs require a narrow Pyright suppression on that call boundary.
        """
        if self.should_validate_on_save():
            self.full_clean(  # pyright: ignore[reportUnknownMemberType]
                exclude=self.get_full_clean_exclude(update_fields)
            )

        cast(Any, super()).save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    @classmethod
    def should_validate_on_save(cls) -> bool:
        """Return whether this model opts into `full_clean()` during save."""
        return bool(cls.validate_on_save)

    @classmethod
    def get_full_clean_exclude(
        cls,
        update_fields: Iterable[str] | None = None,
    ) -> set[str] | None:
        """Return the field names to exclude from `full_clean()`."""
        if update_fields is None:
            return None

        included = set(update_fields)
        exclude: set[str] = set()
        for field in get_model_meta(cls).concrete_fields:
            if field.primary_key:
                continue

            field_name = field.name
            field_attname = field.attname
            if field_name not in included and field_attname not in included:
                exclude.add(field_name)

        return exclude


class DateModel(BaseModel):
    """Abstract model that adds a single ``date`` field to :class:`BaseModel`."""

    date = models.DateField()

    class Meta(BaseModel.Meta):
        abstract = True


class DateRangeModel(BaseModel):
    """Abstract model with an inclusive date range and an activity property.

    ``end_date`` is optional; an open-ended range is considered active
    indefinitely once ``start_date`` is reached.
    """

    DATE_RANGE_ACTIVE_FIELD = "is_date_range_active"

    start_date = models.DateField(db_column="startDate")
    end_date = models.DateField(blank=True, null=True, db_column="endDate")

    class Meta(BaseModel.Meta):
        abstract = True

    @property
    def is_date_range_active(self) -> bool:
        """Return ``True`` when today falls within ``[start_date, end_date]``."""
        today = date.today()
        end_date = cast(date | None, self.end_date)
        return (self.start_date <= today) and (end_date is None or end_date >= today)
