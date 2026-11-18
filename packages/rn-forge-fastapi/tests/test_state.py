from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, cast

import pytest
import rn_forge.fastapi
import rn_forge.fastapi.state
from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from rn_forge.fastapi import FastApiApp, app_state, state_lifespan

pytestmark = pytest.mark.unit


@dataclass(frozen=True, slots=True, kw_only=True)
class AppState:
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OtherState:
    size: int


def opening(value: object, events: list[str] | None = None):
    def opener(_app: FastAPI) -> AbstractAsyncContextManager[AppState]:
        @asynccontextmanager
        async def manage() -> AsyncGenerator[AppState]:
            if events is not None:
                events.append("state up")
            try:
                yield cast("AppState", value)
            finally:
                if events is not None:
                    events.append("state down")

        return manage()

    return opener


def route_app(app: FastAPI) -> FastAPI:
    @app.get("/name")
    def name(state: Annotated[AppState, Depends(app_state(AppState))]) -> str:
        return state.name

    return app


def test_a_route_reads_the_state_set_at_startup():
    app = route_app(
        FastAPI(lifespan=state_lifespan(AppState, opening(AppState(name="a"))))
    )

    with TestClient(app) as client:
        assert_that(client.get("/name").json()).is_equal_to("a")


def test_a_route_reads_the_state_on_a_fast_api_app():
    app = route_app(
        FastApiApp(lifespan=state_lifespan(AppState, opening(AppState(name="a"))))
    )

    with TestClient(app) as client:
        assert_that(client.get("/name").json()).is_equal_to("a")


def test_an_opener_yielding_the_wrong_type_fails_at_startup():
    events: list[str] = []
    app = route_app(FastAPI(lifespan=state_lifespan(AppState, opening("nope", events))))

    with pytest.raises(TypeError, match="AppState expected, got str"), TestClient(app):
        pass

    assert_that(events).is_equal_to(["state up", "state down"])


def test_an_unregistered_state_fails_at_request_time():
    app = route_app(FastAPI())

    with (
        TestClient(app, raise_server_exceptions=True) as client,
        pytest.raises(RuntimeError, match="no AppState registered on this application"),
    ):
        client.get("/name")


def test_teardown_is_the_reverse_of_setup():
    events: list[str] = []

    @asynccontextmanager
    async def inner(_app: FastAPI) -> AsyncGenerator[None]:
        events.append("inner up")
        yield
        events.append("inner down")

    app = FastAPI(
        lifespan=state_lifespan(AppState, opening(AppState(name="a"), events), inner)
    )

    with TestClient(app):
        pass

    assert_that(events).is_equal_to(
        ["state up", "inner up", "inner down", "state down"]
    )


def test_teardown_removes_the_registration():
    app = FastAPI(lifespan=state_lifespan(AppState, opening(AppState(name="a"))))

    with TestClient(app):
        assert_that(app.state._rn_forge_states).contains_key(AppState)

    assert_that(app.state._rn_forge_states).does_not_contain_key(AppState)


def test_dependency_overrides_replace_the_state():
    app = route_app(
        FastAPI(lifespan=state_lifespan(AppState, opening(AppState(name="a"))))
    )
    app.dependency_overrides[app_state(AppState)] = lambda: AppState(name="override")

    with TestClient(app) as client:
        assert_that(client.get("/name").json()).is_equal_to("override")


def test_two_state_classes_are_kept_apart():
    @asynccontextmanager
    async def other(_app: FastAPI) -> AsyncGenerator[OtherState]:
        yield OtherState(size=3)

    lifespan = state_lifespan(
        AppState,
        opening(AppState(name="a")),
        state_lifespan(OtherState, other),
    )
    app = FastAPI(lifespan=lifespan)

    @app.get("/both")
    def both(
        state: Annotated[AppState, Depends(app_state(AppState))],
        extra: Annotated[OtherState, Depends(app_state(OtherState))],
    ) -> str:
        return f"{state.name}{extra.size}"

    with TestClient(app) as client:
        assert_that(client.get("/both").json()).is_equal_to("a3")


def test_the_facade_exports_both():
    assert_that(rn_forge.fastapi.app_state).is_same_as(rn_forge.fastapi.state.app_state)
    assert_that(rn_forge.fastapi.state_lifespan).is_same_as(
        rn_forge.fastapi.state.state_lifespan
    )
