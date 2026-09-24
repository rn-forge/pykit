import pytest
from assertpy import assert_that
from sqlalchemy import update
from sqlalchemy.orm import Mapped, mapped_column

from rn_forge.sqlalchemy import Base, VersionMixin, update_versioned
from rn_forge.web import VersionConflict

pytestmark = pytest.mark.unit


class Doc(VersionMixin, Base):
    __tablename__ = "concurrency_doc"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]


async def _doc(session) -> Doc:
    doc = Doc(title="a")
    session.add(doc)
    await session.commit()
    return doc


@pytest.mark.asyncio
async def test_the_version_starts_at_one_and_advances_on_each_update(session):
    doc = await _doc(session)
    assert_that(doc.version).is_equal_to(1)

    await update_versioned(session, doc, title="b")
    await update_versioned(session, doc, title="c")

    assert_that((doc.title, doc.version)).is_equal_to(("c", 3))


@pytest.mark.asyncio
async def test_a_stale_version_raises_version_conflict_412(session):
    doc = await _doc(session)
    await session.execute(
        update(Doc).values(version=5).execution_options(synchronize_session=False)
    )

    with pytest.raises(VersionConflict) as caught:
        await update_versioned(session, doc, title="b")

    assert_that(caught.value.error_code).is_equal_to(412)


@pytest.mark.asyncio
async def test_a_deleted_row_is_not_a_version_conflict(session):
    doc = await _doc(session)
    await session.delete(doc)
    await session.flush()

    with pytest.raises(LookupError):
        await update_versioned(session, doc, title="b")
