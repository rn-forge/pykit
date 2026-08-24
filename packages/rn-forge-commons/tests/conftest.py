from __future__ import annotations

from typing import NoReturn

from rn_forge.commons.testing import output_path  # noqa: F401


def raise_(exc: BaseException) -> NoReturn:
    """Raise ``exc``; usable from a ``lambda`` where a statement is not allowed."""
    raise exc
