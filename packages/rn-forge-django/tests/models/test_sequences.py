from __future__ import annotations

import threading

import pytest
from django.db import connection

from rn_forge.commons.exceptions import AppException
from rn_forge.django.models import (
    AbstractSequenceCounter,
    SequenceGenerator,
    default_code_formatter,
)


class _Counter(AbstractSequenceCounter):
    class Meta:
        app_label = "rn_forge_django"


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(_Counter)


@pytest.mark.unit
class TestFormatting:
    def test_default_formatter_pads_with_a_prefix(self) -> None:
        assert default_code_formatter("PO-", 42) == "PO-000042"

    def test_default_formatter_without_prefix_is_the_plain_value(self) -> None:
        assert default_code_formatter("", 42) == "42"

    @pytest.mark.parametrize(
        "name", ["Order", "1order", "order-code", "order; DROP TABLE x", "", "a" * 64]
    )
    def test_invalid_sequence_names_are_rejected(self, name) -> None:
        with pytest.raises(AppException):
            SequenceGenerator(name, counter_model=_Counter)


@pytest.mark.integration
@pytest.mark.django_db
class TestCounterPath:
    """sqlite: proves the arithmetic, not the locking. See the module docstring."""

    def test_generate_allocates_consecutive_codes(self) -> None:
        generator = SequenceGenerator("orders", counter_model=_Counter, prefix="PO-")
        assert [generator.generate() for _ in range(3)] == [
            "PO-000001",
            "PO-000002",
            "PO-000003",
        ]

    def test_names_are_independent(self) -> None:
        SequenceGenerator("a_seq", counter_model=_Counter).next_value()
        assert SequenceGenerator("b_seq", counter_model=_Counter).next_value() == 1

    def test_custom_formatter(self) -> None:
        generator = SequenceGenerator(
            "invoices",
            counter_model=_Counter,
            prefix="INV",
            formatter=lambda prefix, value: f"{prefix}-2026-{value:04d}",
        )
        assert generator.generate() == "INV-2026-0001"

    def test_ensure_at_least_raises_the_floor(self) -> None:
        generator = SequenceGenerator("backfill", counter_model=_Counter)
        generator.ensure_at_least(100)
        assert generator.next_value() == 101

    def test_ensure_at_least_is_a_noop_when_already_higher(self) -> None:
        generator = SequenceGenerator("ahead", counter_model=_Counter)
        for _ in range(5):
            generator.next_value()
        generator.ensure_at_least(2)
        assert generator.next_value() == 6


@pytest.mark.integration
@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
class TestSequencePathOnPostgres:
    """The real-sequence path; runs in the django-postgres CI job."""

    @pytest.fixture(autouse=True)
    def _require_postgres(self):
        if connection.vendor != "postgresql":
            pytest.skip(
                "real sequences need PostgreSQL (set RN_FORGE_DJANGO_TEST_DATABASE_URL)"
            )
        yield
        with connection.cursor() as cursor:
            cursor.execute(
                "DROP SEQUENCE IF EXISTS pg_orders, pg_backfill, pg_parallel"
            )

    def test_generate_uses_a_real_sequence(self) -> None:
        generator = SequenceGenerator("pg_orders", counter_model=_Counter, prefix="PO-")
        assert [generator.generate() for _ in range(2)] == ["PO-000001", "PO-000002"]
        assert not _Counter.objects.filter(name="pg_orders").exists()

    def test_ensure_at_least_on_a_fresh_and_a_used_sequence(self) -> None:
        generator = SequenceGenerator("pg_backfill", counter_model=_Counter)
        generator.ensure_at_least(100)
        assert generator.next_value() == 101
        generator.ensure_at_least(50)
        assert generator.next_value() == 102

    def test_concurrent_allocation_never_repeats_a_value(self) -> None:
        generator = SequenceGenerator("pg_parallel", counter_model=_Counter)
        generator.next_value()  # create the sequence before the race
        values: list[int] = []
        lock = threading.Lock()

        def allocate():
            try:
                for _ in range(20):
                    value = generator.next_value()
                    with lock:
                        values.append(value)
            finally:
                connection.close()

        threads = [threading.Thread(target=allocate) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(values) == 100
        assert len(set(values)) == 100
