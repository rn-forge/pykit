"""Database-backed generation of human-readable sequence codes."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Final

from django.db import connections, models, router, transaction
from rn_forge.commons.exceptions import AppException

__all__ = ["AbstractSequenceCounter", "SequenceGenerator", "default_code_formatter"]

_NAME: Final = re.compile(r"[a-z][a-z0-9_]{0,62}")


class AbstractSequenceCounter(models.Model):
    """Abstract counter table backing the non-PostgreSQL sequence path."""

    name: models.CharField[str, str] = models.CharField(max_length=63, unique=True)
    value: models.PositiveBigIntegerField[int, int] = models.PositiveBigIntegerField(
        default=0
    )

    class Meta:
        abstract = True


def default_code_formatter(prefix: str, value: int) -> str:
    """Return a six-digit value with a prefix, or the raw value without one."""
    return f"{prefix}{value:06d}" if prefix else str(value)


class SequenceGenerator:
    """Allocate gap-free, human-readable codes from a named database sequence.

    Args:
        name: The sequence name. Must match ``[a-z][a-z0-9_]*`` (at most 63
            characters). The attribute may be reassigned; the current value is
            validated again, and quoted with the connection's identifier
            quoting, before each PostgreSQL statement.
        counter_model: The consumer's concrete :class:`AbstractSequenceCounter`.
        prefix: Passed to *formatter*.
        formatter: ``(prefix, value) -> code``. Defaults to
            :func:`default_code_formatter`.
        using: A database alias. Defaults to the router's write database for
            *counter_model*.

    Raises:
        AppException: *name* is not a valid sequence name, at construction or
            when :meth:`next_value` or :meth:`ensure_at_least` runs.
    """

    def __init__(
        self,
        name: str,
        *,
        counter_model: type[AbstractSequenceCounter],
        prefix: str = "",
        formatter: Callable[[str, int], str] | None = None,
        using: str | None = None,
    ) -> None:
        self._check_name(name)
        self.name = name
        self._model = counter_model
        self._prefix = prefix
        self._formatter = formatter if formatter is not None else default_code_formatter
        self._using = using

    def generate(self) -> str:
        """Allocate the next value and return it formatted."""
        return self._formatter(self._prefix, self.next_value())

    def next_value(self) -> int:
        """Allocate and return the next raw value."""
        alias = self._alias()
        if connections[alias].vendor == "postgresql":
            identifier = self._identifier(alias)
            with connections[alias].cursor() as cursor:
                cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {identifier}")
                cursor.execute("SELECT nextval(%s)", [self.name])
                row: tuple[Any, ...] = cursor.fetchone()
                return int(row[0])
        with transaction.atomic(using=alias):
            counter = self._locked_counter(alias)
            counter.value += 1
            counter.save(update_fields=["value"])
            return counter.value

    def ensure_at_least(self, value: int) -> None:
        """Raise the floor so the next value is greater than *value*.

        For backfills and imports. A no-op when the current value is already
        at or above *value*.
        """
        alias = self._alias()
        if connections[alias].vendor == "postgresql":
            identifier = self._identifier(alias)
            with connections[alias].cursor() as cursor:
                cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {identifier}")
                cursor.execute(f"SELECT last_value, is_called FROM {identifier}")
                last_value, is_called = cursor.fetchone()
                current = int(last_value) if is_called else int(last_value) - 1
                if value > current:
                    cursor.execute("SELECT setval(%s, %s, true)", [self.name, value])
            return
        with transaction.atomic(using=alias):
            counter = self._locked_counter(alias)
            if counter.value < value:
                counter.value = value
                counter.save(update_fields=["value"])

    @staticmethod
    def _check_name(name: str) -> None:
        AppException.check(
            _NAME.fullmatch(name), "Invalid sequence name: {!r}", name, error_code=400
        )

    def _identifier(self, alias: str) -> str:
        self._check_name(self.name)
        return connections[alias].ops.quote_name(self.name)

    def _alias(self) -> str:
        return self._using or router.db_for_write(self._model)

    def _locked_counter(self, alias: str) -> AbstractSequenceCounter:
        manager = self._model._default_manager.db_manager(alias)
        manager.get_or_create(name=self.name)
        return manager.select_for_update().get(name=self.name)
