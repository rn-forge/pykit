from importlib.metadata import metadata

import pytest
from assertpy import assert_that

pytestmark = pytest.mark.unit


def test_package_metadata_lists_postgres_and_sqlite_extras() -> None:
    meta = metadata("rn-forge-sqlalchemy")
    requires = [r.replace("'", '"') for r in meta.get_all("Requires-Dist") or []]

    assert_that(meta.get_all("Provides-Extra")).contains("postgres", "sqlite")
    assert_that(
        [r for r in requires if r.startswith("asyncpg") and 'extra == "postgres"' in r]
    ).is_not_empty()
    assert_that(
        [r for r in requires if r.startswith("aiosqlite") and 'extra == "sqlite"' in r]
    ).is_not_empty()
