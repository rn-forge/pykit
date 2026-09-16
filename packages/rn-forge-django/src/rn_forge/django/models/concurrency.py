"""Opt-in optimistic-concurrency and immutability model mixins."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar, override

from django.db import models
from django.db.models.base import ModelBase
from rn_forge.django.models._meta import get_model_meta
from rn_forge.web import DomainConflict, VersionConflict

__all__ = ["ImmutableModelMixin", "VersionedModelMixin"]


class VersionedModelMixin(models.Model):
    """Abstract mixin adding an optimistic-concurrency ``version`` counter.

    Existing rows increment from the loaded version, including partial saves.
    A concurrent update raises :class:`rn_forge.web.VersionConflict`.
    """

    version: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(
        default=1
    )

    class Meta:
        abstract = True

    @override
    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """Bump ``version`` on update, then delegate to ``super().save()``."""
        if not self._state.adding:
            self.version += 1
            if update_fields is not None:
                update_fields = {*update_fields, "version"}
        try:
            super().save(
                force_insert=force_insert,
                force_update=force_update,
                using=using,
                update_fields=update_fields,
            )
        except VersionConflict:
            self.version -= 1
            raise

    @override
    def _do_update(  # pyright: ignore[reportIncompatibleMethodOverride]  # private Django hook, untyped in the stubs
        self,
        base_qs: models.QuerySet[Any],
        using: str | None,
        pk_val: Any,
        values: list[tuple[models.Field[Any, Any], Any, Any]],
        update_fields: Iterable[str] | None,
        forced_update: bool,
        returning_fields: list[models.Field[Any, Any]],
    ) -> Any:
        """Match the row only at the loaded version; raise if it moved on."""
        if self._state.adding or not any(
            field.attname == "version" for field, _, _ in values
        ):
            return super()._do_update(
                base_qs,
                using,
                pk_val,
                values,
                update_fields,
                forced_update,
                returning_fields,
            )
        expected = self.version - 1
        results = super()._do_update(
            base_qs.filter(version=expected),
            using,
            pk_val,
            values,
            update_fields,
            forced_update,
            returning_fields,
        )
        if not results and base_qs.filter(pk=pk_val).exists():
            raise VersionConflict(
                "{} {} was modified concurrently: expected version {}",
                type(self).__name__,
                pk_val,
                expected,
                error_code=412,
            )
        return results


class ImmutableModelMixin(models.Model):
    """Abstract mixin that rejects post-creation mutation and deletion.

    Saving a changed row raises :class:`rn_forge.web.DomainConflict`; deleting
    always raises. Queryset-level ``update()`` and ``delete()`` bypass the guard.
    """

    IMMUTABLE_EXCLUDE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"created_by", "created_at", "updated_by", "updated_at"}
    )

    class Meta:
        abstract = True

    @override
    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """Reject a change to any guarded field, then delegate to ``super().save()``."""
        if not self._state.adding:
            self._reject_changes(using)
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    @override
    def delete(
        self, using: Any = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]:
        """Always raise: an immutable row is never deleted."""
        raise DomainConflict(
            "{} is immutable and cannot be deleted", type(self).__name__
        )

    def _reject_changes(self, using: str | None) -> None:
        guarded = [
            field.attname
            for field in get_model_meta(type(self)).concrete_fields
            if not field.primary_key and field.name not in self.IMMUTABLE_EXCLUDE_FIELDS
        ]
        stored = (
            type(self)
            ._default_manager.db_manager(using)
            .filter(pk=self.pk)
            .values(*guarded)
            .first()
        )
        if stored is None:
            return
        changed = sorted(
            name for name in guarded if stored[name] != getattr(self, name)
        )
        DomainConflict.check(
            not changed,
            "{} is immutable; cannot change {}",
            type(self).__name__,
            ", ".join(changed),
        )
