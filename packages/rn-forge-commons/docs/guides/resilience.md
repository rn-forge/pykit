# Resilience

`ResilientAsyncHttpClient` wraps `httpx.AsyncClient` with a per-key circuit breaker (`purgatory`),
retry with `Retry-After` awareness (`stamina`), and a rate limiter clamped from response headers —
the `resilience` extra.

```python
from rn_forge.commons.resilience import ResilientAsyncHttpClient

async with ResilientAsyncHttpClient("https://api.example.com", name="example-api") as client:
    response = await client.get("/widgets")
```

## Per-key breakers

Pass `key=` to `request`/`get`/`post`/... to protect several independent upstreams (e.g. one
breaker per tenant or per upstream organisation) from one client instance — each key gets its own
circuit, tripped independently:

```python
await client.get("/widgets", key=f"tenant-{tenant_id}")
```

## The metrics seam

`on_state_change(key, old_state, new_state)` is called on every circuit transition. It defaults to
an `AppLogger` warning — wire it to your own metrics backend rather than expecting this module to
import OpenTelemetry:

```python
ResilientAsyncHttpClient(
    "https://api.example.com",
    name="example-api",
    on_state_change=lambda key, old, new: my_metrics.increment("circuitbreaker_state", tags=[key, new]),
)
```

## Testable timing

The rate limiter's `clock`/`sleep` are constructor-injectable, so a test can run on a fake clock
instead of real wall time:

```python
client = ResilientAsyncHttpClient(
    "https://api.example.com",
    name="example-api",
    clock=fake_clock,
    sleep=fake_sleep,
)
```

## Escape hatch

`client.client` is the underlying `httpx.AsyncClient`, for anything this facade doesn't cover.
