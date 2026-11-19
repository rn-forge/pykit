# Typed application state

Reading a resource as `request.app.state.<name>` is untyped: a misspelt name or
a wrong type surfaces as a 500 at request time. `app_state` and `state_lifespan`
declare the resources once, as a class, and a route receives them through
`Depends`, so the same mistakes fail type checking.

## Declare the state

Declare the resources as a frozen dataclass.

```python
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True, slots=True, kw_only=True)
class AppState:
    engine: AsyncEngine
    greeting: str
```

## Open it

An opener is an async context manager that builds the state and releases it on
shutdown.

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine


@asynccontextmanager
async def open_state(app: FastAPI) -> AsyncGenerator[AppState]:
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        yield AppState(engine=engine, greeting="hello")
    finally:
        await engine.dispose()
```

Pass `state_lifespan(...)` as `lifespan=`. An opener that yields something that
is not an `AppState` raises `TypeError` at startup, and the application never
serves.

```python
from rn_forge.fastapi import FastApiApp, state_lifespan

app = FastApiApp(lifespan=state_lifespan(AppState, open_state))
```

Startup runs the opener, then the optional `inner` lifespan; shutdown runs in
reverse, removing the registration before the opener exits.

## Use it in a route

Alias the dependency once and annotate routes with it.

```python
from typing import Annotated

from fastapi import Depends
from rn_forge.fastapi import app_state

State = Annotated[AppState, Depends(app_state(AppState))]


@app.get("/greeting")
def greeting(state: State) -> str:
    return state.greeting
```

`state.greting` or `state.greeting + 1` is a type error. A route on an
application whose lifespan never registered `AppState` raises
`RuntimeError("no AppState registered on this application")`.

## Replace it in tests

`app_state(AppState)` returns the same dependency object every time, so it is
the key for an override.

```python
app.dependency_overrides[app_state(AppState)] = lambda: AppState(
    engine=fake_engine, greeting="test"
)
```

## Several state classes

Nest `state_lifespan` calls through `inner`; each registers its own class.

```python
lifespan = state_lifespan(
    AppState,
    open_state,
    inner=state_lifespan(CacheState, open_cache),
)
```
