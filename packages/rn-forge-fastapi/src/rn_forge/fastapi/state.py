"""Typed application state: declared once, injected through ``Depends``."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import cache
from typing import cast

from fastapi import FastAPI, Request
from starlette.types import Lifespan

__all__ = ["app_state", "state_lifespan"]

_KEY = "_rn_forge_states"


def _registry(app: FastAPI) -> dict[type, object]:
    if not hasattr(app.state, _KEY):
        setattr(app.state, _KEY, {})
    return cast("dict[type, object]", getattr(app.state, _KEY))


@cache
def app_state[T](cls: type[T]) -> Callable[[Request], T]:
    """Return the dependency that provides the *cls* state to a route.

    The same dependency object is returned for the same class, so
    ``app.dependency_overrides[app_state(cls)]`` replaces it.

    Args:
        cls: The state class registered with :func:`state_lifespan`.

    Returns:
        A dependency that returns the registered instance of *cls*; it raises
        ``RuntimeError`` when the application has none.
    """

    def dependency(request: Request) -> T:
        found = cast("dict[type, object]", getattr(request.app.state, _KEY, {})).get(
            cls
        )
        if found is None:
            raise RuntimeError(f"no {cls.__name__} registered on this application")
        return cast("T", found)

    return dependency


def state_lifespan[T](
    cls: type[T],
    opener: Callable[[FastAPI], AbstractAsyncContextManager[T]],
    inner: Lifespan[FastAPI] | None = None,
) -> Lifespan[FastAPI]:
    """Return a lifespan that registers the state *opener* builds.

    Startup enters *opener*, registers its value under *cls*, then enters
    *inner*. Shutdown exits *inner*, removes the registration, then exits
    *opener*. Nest calls through *inner* to register several state classes.

    Args:
        cls: The state class; routes receive it through :func:`app_state`.
        opener: Builds the state and releases it on shutdown.
        inner: A lifespan to run while the state is registered.

    Returns:
        A lifespan to pass as ``lifespan=`` to the application.

    Raises:
        TypeError: At startup, when the opener yields something that is not an
            instance of *cls*; nothing is registered.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with opener(app) as value:
            if not isinstance(value, cls):
                raise TypeError(f"{cls.__name__} expected, got {type(value).__name__}")
            states = _registry(app)
            states[cls] = value
            try:
                if inner is None:
                    yield
                else:
                    async with cast("AbstractAsyncContextManager[None]", inner(app)):
                        yield
            finally:
                del states[cls]

    return lifespan
