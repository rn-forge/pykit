"""Structured exception base classes for ``rn-forge-*`` packages.

Typical usage::

    from rn_forge.commons import AppException

    AppException.check(user_id, "User id is required", error_code=400)

    raise AppException(
        "Unable to process order {}",
        order_id,
        error_code=409,
        customer_id=customer_id,
    )
"""

from typing import Any

__all__ = ["AppException"]


class AppException(Exception):
    """Base exception with structured error code and contextual data.

    Args:
        message: Human-readable description; supports ``str.format`` positional args.
        *message_args: Positional arguments forwarded to ``message.format()``.
        error_code: Application-specific integer error code (default ``-1``).
        **error_data: Arbitrary key/value context attached to the exception.

    Example::

        raise AppException(
            "Invalid state transition: {} -> {}",
            old_state,
            new_state,
            error_code=1001,
            order_id=order_id,
        )
    """

    message: str
    error_code: int
    error_data: dict[str, Any]

    def __init__(
        self,
        message: str,
        *message_args: Any,
        error_code: int = -1,
        **error_data: Any,
    ) -> None:
        self.message = message.format(*message_args)
        self.error_code = error_code
        self.error_data = error_data
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.error_code} | {self.message} | {self.error_data}"

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code!r}, "
            f"error_data={self.error_data!r})"
        )

    @classmethod
    def check(cls, value: Any, message: str, *message_args: Any, **kwargs: Any) -> None:
        """Raise this exception if *value* is falsy.

        Args:
            value: The value to test.
            message: Exception message (supports positional format args).
            *message_args: Forwarded to ``message.format()``.
            **kwargs: Forwarded as ``error_code`` / ``error_data`` to the constructor.

        Example::

            AppException.check(path.exists(), "Missing file: {}", path, error_code=404)
        """
        if not value:
            raise cls(message, *message_args, **kwargs)
