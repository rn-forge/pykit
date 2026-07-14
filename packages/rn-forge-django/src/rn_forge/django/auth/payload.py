"""Normalized login payload objects for rn-forge auth flows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

__all__ = [
    "LoginPayload",
]


@dataclass(frozen=True, slots=True)
class LoginPayload:
    """Normalized login result passed from identity flow into JWT minting."""

    user: object
    claims: Mapping[str, object] = field(
        default_factory=lambda: cast(Mapping[str, object], {})
    )
