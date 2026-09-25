# Web API consumer reuse plan

> **Historical plan.** For current status, use the [spec board](../../specs/index.md). For this plan's section map and unresolved conflicts, use the [migration ledger](../context.md).

**Status:** planned, 2026-09-19. Supersedes and absorbs the *FastAPI consumer
reuse follow-up* drafted the same day (same file, renamed: the findings now
span `rn-forge-commons`, `rn-forge-web` and `rn-forge-fastapi`, not
`rn-forge-fastapi` alone).

**Re-baselined 2026-09-21** by the
[standards re-baseline plan](standards-rebaseline-plan.md), which takes
precedence here:

- Phase 0 is kept.
- **Phase 1 is withdrawn** (R1).
- Phases 4 and 5 are in the working tree; Phase 5's choice of header moves to
  R3.
- Phases 2, 3 and 6 are unchanged.
- The Account Portal and IntelliBuild are **parked** as acceptance consumers,
  so the evidence drawn from them no longer justifies a phase on its own.

Follow-up to the implemented
[standard FastAPI application layer](fastapi-app-layer-plan.md). Phases 1 and 2
came from its first adoption; Phases 3–6 come from a review of three further
in-progress FastAPI applications.

## What was reviewed

| Application | Path | Uses pykit |
| --- | --- | --- |
| Account Portal API | `rn-forge/web-app/apps/api/src/web_app_api/` | commons, cli, web, fastapi |
| IntelliBuild API | `walgreens/intellibench/apps/api/src/intellibuild_api/` | none |
| Apollo API | `rn-tools/apollo/apps/api/src/apollo/` | commons only |
| PhotoTidy controller | `rn-tools/phototidy/apps/controller/src/photos_cleanup/` | none |

All four are FastAPI + a separately built Angular frontend. Three of the four
predate `rn-forge-web`/`rn-forge-fastapi` and re-derive parts of them; that
re-derivation is **prior art, not a compatibility constraint** (README, design
principle 4), so this plan takes what recurs and is genuinely missing, and
records what it rejects.

## How a candidate was judged

A pattern was only accepted when it passed all four design principles:

1. **Don't reimplement a proven library.** Every phase's candidates were
   checked against PyPI, not memory — see *Library evaluations* below. One
   phase changed shape as a result and one shrank to nothing.
2. **Wrap for one design language.** Accepted API is frozen-dataclass config,
   `AppException`/`WebError` subclasses, injected logging, curated re-exports.
   The underlying FastAPI/Starlette object stays reachable.
3. **Package boundaries.** Anything framework-free goes in the lowest package
   that can hold it. `rn_forge.web` must not import `starlette`, so a
   Starlette-based dependency can only be taken by `rn_forge.fastapi`.
4. **pykit is upstream.** Where an application got something wrong, this plan
   fixes it here rather than encoding it.

A pattern seen in only one application was accepted only where it is a
**safe-by-default** concern the kit is already responsible for (Phases 5, 6).

## Library evaluations (run 2026-09-19)

Design principle 1 requires checking PyPI before hand-rolling, and saying which
exemption applies when hand-rolling anyway. These are the results; do not redo
them, and do not hand-roll past them.

### `sse-starlette` — **adopted** (Phase 3)

Version 3.4.11, released 2026-09-05; `starlette>=0.49.1`, `anyio>=4.7.0`;
`requires_python >=3.10`. Installed into a throwaway 3.14 venv alongside
`fastapi==0.141.1` and driven through `TestClient`. It resolves against the
workspace's `starlette 1.6.0` and works:

- `ServerSentEvent(data, *, event, id, retry, comment, sep)` — the same field
  set the three applications each hand-rolled;
- multi-line `data` splits into one `data:` line per line;
- a comment-only frame renders `: heartbeat\r\n\r\n` with no `data:` line;
- the response carries `text/event-stream; charset=utf-8`,
  `cache-control: no-store` and `x-accel-buffering: no` by default;
- `EventSourceResponse(..., ping=<seconds>)` emits the heartbeat, and
  `_listen_for_disconnect` consumes `http.disconnect` internally — so the
  0.5-second poll loop IntelliBuild wrote is not needed at all;
- it also offers `ping_message_factory`, `send_timeout`, `shutdown_event` and
  `client_close_handler_callable`.

Two behaviours the phase must account for rather than inherit silently:

1. **It strips newlines from `id` and `event` instead of rejecting them.**
   `ServerSentEvent(id="1\nevent: forged").encode()` produces
   `b'id: 1event: forged\r\n\r\n'` — no frame is forged, but the value is
   silently mangled.
2. **It monkey-patches `uvicorn.Server.handle_exit`** (`sse_starlette.sse.AppStatus`)
   to drain streams on shutdown. That is a process-wide side effect of
   importing it, which is why it goes behind an extra rather than into the
   package's base dependencies.

### Log redaction — **no candidate; hand-roll** (Phase 2)

- `logredactor` 0.0.2, last released **2023-02-10**, no declared
  `requires_python`, regex-over-the-formatted-string only — it cannot walk
  structured fields, which is the whole requirement.
- `scrubadub` 2.0.1, last released **2023-09-01**, drags `scikit-learn`,
  `textblob`, `dateparser` and `faker`. It is a PII-in-prose cleaner, a
  different concern and far heavier.
- `pii-redact` 0.1.0 requires `torch` and `transformers`.

Both principle-1 exemptions apply — the maintained candidates are far heavier
and target a different concern, and the needed slice is a few dozen lines.
**Name the exemption in the module docstring**, as the principle requires.

### `asgi-correlation-id` — **not adopted; design confirmed** (Phase 5)

Version 5.0.1, released 2026-06-09, maintained, `starlette>=0.18`. Not taken:
`rn_forge.web.CorrelationIdMiddleware` already exists and is framework-free,
and this package imports Starlette, which `.importlinter`'s
`web-is-framework-free` forbids `rn_forge.web` from doing.

It is still the useful result, because its parameter set is exactly what
Phase 5 adds: `generator=lambda: uuid4().hex` plus
`validator=is_valid_uuid4`, where a value the validator rejects is replaced by
a generated one. Phase 5 adopts that shape — a `bool`-returning validator —
rather than inventing another.

### Phases 1, 4 and 6 — nothing to evaluate

Phase 1 is composition over `pydantic.json_schema.models_json_schema` and
`json.dumps`, both already dependencies. Phase 4 is a change to
`ProblemRegistry`. Phase 6 is configuration over Starlette's own
`CORSMiddleware`, which arrives with FastAPI.

## Findings

| # | Finding | Apps | Verdict |
| --- | --- | --- | --- |
| 1 | OpenAPI: register unreferenced models, render deterministically | Account Portal, IntelliBuild | ~~**Build** — Phase 1 (`fastapi`)~~ **Withdrawn 2026-09-21** (re-baseline R1) |
| 2 | Structured-log secret redaction | Account Portal | **Build** — Phase 2 (`commons`) |
| 3 | Server-sent events | IntelliBuild, Apollo, PhotoTidy | **Build** — Phase 3 (`fastapi`, over `sse-starlette`) |
| 4 | Problem extensions carried by the exception; proving an exception table total | IntelliBuild (+ Apollo's `error_data`) | **Build** — Phase 4 (`web`) |
| 5 | Caller-supplied correlation ID accepted unvalidated | Apollo validates; pykit does not | **Build** — Phase 5 (`web`) |
| 6 | CORS, and exposing the kit's own response headers to a browser | IntelliBuild | **Build** — Phase 6 (`fastapi`), as an opt-in module |
| 7 | Offset/limit pagination envelope | Apollo | **Reject** |
| 8 | `offload()` over `run_in_threadpool` | Apollo | **Reject** |
| 9 | SPA static-file mount with index fallback | PhotoTidy | **Reject** |
| 10 | `serve` command wrapping `uvicorn.run` | all four | **Reject** |
| 11 | Settings facade (`BaseSettings` + cached accessor) | IntelliBuild, Apollo | **Reject** |
| 12 | Per-request dependency/port container | IntelliBuild | **Reject** |
| 13 | A `FastApiApp` wrapper class | — (owner's question) | **Build** — Phase 0 (`fastapi`); the *fluent builder* variant is rejected |

**Phase 0 runs first** — it is the surface Phases 1 and 6 attach to. The rest
are independent; suggested order is 0, 4, 5, 1, 6, 3, 2 — smallest and
lowest-risk first, the dependency-taking one late.

---

## Phase 0 — `FastApiApp` (`rn-forge-fastapi`)

**Why.** `rn-forge-cli` ships `CliApp`, a `typer.Typer` subclass that wires the
standard surface in `__init__`; `rn-forge-fastapi` ships a `create_app`
factory. One kit, two shapes for the same job. Closing that is the owner's
decision (2026-09-19), conditional on the subclass introducing no other
problems.

**It does not.** Probed against the real package on 2026-09-19 — a `FastAPI`
subclass doing exactly the wiring `create_app` does:

- `isinstance(app, FastAPI)` holds, so `TestClient`, `uvicorn` and every
  FastAPI/Starlette API take it unchanged;
- correlation middleware, problem handlers (a registered domain exception
  rendered 418 `application/problem+json` with its `correlation_id`), the
  routing 404 problem, `/healthz`, `operationId` generation and the
  `openapi_version: 3.1.0` document with `ProblemDetail` in `components` all
  behave identically;
- `install_problem_schema`'s instance-attribute assignment to `self.openapi`
  works on a subclass, and the document stays cached across calls
  (`app.openapi() is app.openapi()`);
- `/docs` and the rest of FastAPI's own routes are present;
- the class definition type-checks at **0 errors under strict Pyright**;
- it subclasses further without special handling.

**Build.** In `src/rn_forge/fastapi/app.py`:

```python
class FastApiApp(FastAPI):
    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        routers: Sequence[APIRouter] = (),
        lifespan: Lifespan[FastAPI] | None = None,
        title: str = "FastAPI",
        description: str = "",
        version: str = "0.1.0",
        **fastapi_kwargs: Any,
    ) -> None: ...
```

Body: default `generate_unique_id_function` to `operation_id` via
`fastapi_kwargs.setdefault` (so a caller can override it), call
`super().__init__`, keep the resolved config on `self.config`, then add the
correlation middleware, register the problem handlers, install the problem
schema, include `health_router`, and include *routers* in order. That is
`create_app`'s current body, moved. Follow `CliApp`'s docstring style: state
that FastAPI is inherited rather than wrapped, so `@app.get()`,
`add_middleware` and the full constructor keyword set remain available.

**`create_app` is removed, not kept beside it.** Keeping both would be two
supported ways to do one thing — the same objection that rejects the builder
below. Nothing is released yet (no tags are cut), the Account Portal is the
only consumer and pins the branch, and the README states the workspace ships
**no compatibility shims in any direction**. The migration is one line per
consumer: `create_app(config, routers=..., title=...)` →
`FastApiApp(config, routers=..., title=...)`.

Note pykit does **not** need to ship a factory function for
`uvicorn.run(..., factory=True)`: an application defines its own `create_app()`
returning a `FastApiApp`, which is what all four reviewed applications already
do.

**Call sites to update in the same change** — a grep for `create_app` across
`packages/` will find them, and they are the phase's real work:

- the curated facade `src/rn_forge/fastapi/__init__.py`;
- `tests/test_app.py` and the conformance driver's fixture in
  `tests/test_conformance.py`;
- the package `README.md`, `docs/api/app.md`, `docs/guides/quickstart.md` and
  `docs/guides/wiring.md`;
- [`fastapi-app-layer-plan.md`](fastapi-app-layer-plan.md) — add a short
  "superseded" note to its implementation-surface section pointing here, rather
  than rewriting it; it is a historical record.

**Tests.** Keep every existing `test_app.py` case, retargeted at the
constructor, and add: `isinstance(app, FastAPI)`; `app.config` is the config
passed; `FastApiApp()` with no argument uses a default `AppConfig`;
`generate_unique_id_function` is overridable through `**fastapi_kwargs`; a
subclass of `FastApiApp` constructs and serves.

### Rejected within this phase: the fluent builder

The owner's alternative — `FastApiApp(...).problem(...).routers(...).build()` —
stays rejected, for reasons the subclass does not share:

1. The app-layer plan's decision stands: "Preserve access to normal FastAPI
   APIs for extension; **avoid a parallel router or dependency framework**."
   A subclass *is* the normal FastAPI API; a builder is a second vocabulary in
   front of it.
2. Principle 2 says configuration is "a frozen dataclass (or a settings-facade
   field), **never a kwargs soup**". Chained setters are mutable-builder
   configuration. Where chaining earns its place the kit already has it:
   `ProblemRegistry.register` returns `Self`.
3. It deletes no code. After Phase 1, the Account Portal's composition root is
   three `registry.register` calls, a router loop and one constructor — every
   line an application-specific declaration. A builder renames them.
4. `CliApp` is the precedent being matched, and it is a subclass with an
   `__init__` and a `from_config` classmethod, not a builder. Matching it means
   matching that shape.

If a consumer later wants chained configuration, the supported extension point
is a classmethod in `CliApp.from_config`'s mould, not a mutable builder.

## Phase 1 — composable OpenAPI components (`rn-forge-fastapi`)

> **Withdrawn 2026-09-21.** It was implemented on 2026-09-20 and is removed by
> [re-baseline R1](standards-rebaseline-plan.md#r1-openapi-accuracy-only-fastapi-django-web).
> Neither helper fills a gap in FastAPI or in OpenAPI:
>
> - OpenAPI does not require unreferenced components, and adding one is a
>   single `openapi()` override on the application's own subclass.
> - `openapi_json` is one `json.dumps` call.
> - The composition hazard it guarded against was created by pykit's own
>   attribute patching, which R1 replaces with a method override.
>
> A generic `Page[Item]` supplied to it also duplicated the route-derived
> component (`Page_OrderOut_` beside `PageOrderOut`). The section below is kept
> as the record.

**Evidence.** Account Portal's `app.py::_install_shared_shapes` adds every
shared Pydantic model to `components.schemas` whether or not a route references
it, and `openapi_document()` renders `json.dumps(..., sort_keys=True, indent=2,
ensure_ascii=False) + "\n"` for a committed drift check. IntelliBuild's
`app.py::_custom_openapi` does the same for `ProblemDetail` alone — and does it
by calling `get_openapi(...)` from scratch, which is exactly the hazard this
phase removes: on a pykit-based app that would discard everything
`install_problem_schema` repairs.

**Build.** In `src/rn_forge/fastapi/openapi.py`:

```python
def install_component_schemas(app: FastAPI, *, models: Sequence[type[BaseModel]]) -> None: ...
def openapi_json(document: Mapping[str, Any]) -> str: ...
```

- `install_component_schemas` composes with `app.openapi` the way
  `install_problem_schema` already does — take the current callable, return a
  new one — and **never** rebuilds via `get_openapi`. Resolve inter-model
  `$ref`s with
  `models_json_schema([(m, "serialization") for m in models],
  ref_template="#/components/schemas/{model}")` and merge its `$defs` with
  `setdefault`, so a route-derived component always wins a name collision.
- **Caching detail Sonnet must get right:** `install_problem_schema`'s wrapper
  assigns `app.openapi_schema` and returns that same dict. So
  `install_component_schemas` must merge **in place** into the mapping it gets
  back; a merge into a copy would be discarded on the second call. Its own
  early-return on `app.openapi_schema` is therefore unnecessary and must not be
  added — it would run before the inner call has ever populated the cache.
- `openapi_json` takes a mapping, not an app: choosing the output path is the
  consumer's. `sort_keys=True`, `indent=2`, `ensure_ascii=False`, exactly one
  trailing newline.

**Wire it into the constructor, don't leave it as a post-construction call.**
`AppConfig` gains `components: Sequence[type[BaseModel]] = ()`, and
`FastApiApp.__init__` (Phase 0) calls `install_component_schemas` immediately
after `install_problem_schema` when it is non-empty. That is the ordering that
works, and leaving it to the caller is the wart behind finding 13.
`install_component_schemas` stays public for an application that builds its own
FastAPI instance.

**Tests** (`tests/test_openapi.py`, `tests/test_app.py`): an unreferenced model
appears; a `$ref` between two supplied models resolves inside
`components/schemas`; the problem repair still applies after both installs; a
second `app.openapi()` returns the cached document, still carrying the
components, without re-merging; a route-derived component of the same name is
preserved; `openapi_json` is byte-identical across two calls and ends with
exactly one `\n`; `AppConfig(components=...)` produces the same document as the
manual call.

**Facade and docs.** Export both from `rn_forge/fastapi/__init__.py`; extend
`docs/api/openapi.md`, `docs/api/app.md` and `docs/guides/wiring.md`.

Out of scope: filesystem writes, CLI parsing, and which models an application
considers public.

## Phase 2 — structured-log redaction (`rn-forge-commons`)

**Evidence.** Account Portal's `logging.py::redact` walks nested values,
redacts by case-insensitive field-name match
(`authorization|token|password|secret|cookie`), and scrubs `Bearer`/`Basic`
credentials and URL user-info passwords inside strings. No other reviewed app
redacts anything; two of them log request context straight to stdout. The kit
owns logging, so the default belongs here. No usable library exists — see
*Library evaluations*.

**Build.** In `src/rn_forge/commons/logging/`:

- `redaction.py` — module docstring names the principle-1 exemption. Contents:
  `REDACTED: Final = "[redacted]"`; a frozen `RedactionPolicy` dataclass
  (`field_pattern: re.Pattern[str]`, `scrub_credentials: bool`,
  `scrub_url_passwords: bool`) with `RedactionPolicy.default()` covering
  authorization, token, password, secret and cookie; and
  `redact(value, *, policy=None, key="") -> Any`.
- A `RedactFilter(logging.Filter)` beside `EnrichFilter` that redacts
  `record.args` and any `extra` fields the record carries, registered in
  `AppLogger._configure_logging`'s `filters` dict so it applies to the JSON,
  Rich and plain handlers alike. Gate it on a new `LoggingConfig.redact: bool`
  (default `True`) plumbed through `AppLogger.initialize(redact=...)` and
  `LoggingConfig.defaults()`.
- A structlog processor `redact_processor` in `logging/structlog.py`, behind
  the existing `structlog` extra, inserted before the renderer in
  `_configure_once`.

Rules: never mutate the caller's mapping or sequence; preserve `None` and `""`
rather than replacing them; leave unmatched fields untouched. Do **not** carry
over the Account Portal's `*env` key exemption or its fixed logger name — both
are application policy. Preserve structured context; never flatten to a string.

**Tests** (`tests/logging/test_redaction.py`): nested dict/list/tuple mixes;
input unchanged after a call; case-insensitive key match; a `Bearer <token>`
inside a message; a URL user-info password; a field named `token_count` not
redacted by a key match on its value; a custom policy; `redact=False` disabling
the filter; and one integration test asserting a `use_json=True` record emits
redacted output.

**Docs.** Extend the commons logging guide and its API reference page.

## Phase 3 — server-sent events (`rn-forge-fastapi`, over `sse-starlette`)

**Evidence.** Three independent hand-rolled SSE implementations, each with its
own frame formatting:

- `intellibuild_api/routers/runs.py` — `_sse_frame()` with comment/id/event and
  per-line `data:`; a 0.5 s disconnect poll under a 15 s heartbeat; a terminal
  `event: error` frame carrying a problem body.
- `apollo/api/v1/routers/operations/jobs.py` — `_frame()`, a counted heartbeat,
  `request.is_disconnected()` in the loop condition.
- `photos_cleanup/services/events.py` — a queue-fanout broker emitting
  `: connected`, `: keepalive` and `id:`/`data:` frames, plus
  `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

`sse-starlette` already does all of the framing, the heartbeat and the
disconnect handling, correctly and better (see *Library evaluations*). **So
this phase ships no frame encoder and no `rn_forge.web.sse` module** — an
earlier draft of this plan proposed both, and the PyPI check retired them.

**Build.** One new module, `src/rn_forge/fastapi/sse.py`, behind a new `sse`
extra. It contributes only the three things `sse-starlette` does not:

```python
DEFAULT_PING_SECONDS: Final = 15.0

def sse_response(
    events: AsyncIterable[ServerSentEvent],
    *,
    ping: float | None = DEFAULT_PING_SECONDS,
    registry: ProblemRegistry | None = None,
    instance: str = "",
    correlation_header: str = DEFAULT_CORRELATION_HEADER,
    headers: Mapping[str, str] | None = None,
) -> EventSourceResponse: ...
```

1. **Validation instead of silent mangling.** `sse_response` wraps *events* in
   an internal async generator that checks each frame's `id` and `event` for
   `\r`, `\n` and `\x00` and raises `WebError` on any of them. Doing it in the
   wrapper rather than in a factory function is deliberate: every frame passes
   through it, so the check cannot be bypassed.
2. **The correlation header on the response**, read from
   `rn_forge.web.get_correlation_id()` when one is bound.
3. **A terminal problem frame.** An exception escaping *events* is caught and
   converted to one final `ServerSentEvent(event="error", data=<problem JSON>)`
   built from `registry.build(exc, instance=instance)` (defaulting to
   `default_registry()`), after which the stream closes cleanly. This is
   IntelliBuild's behaviour, and `ProblemRegistry.build`'s 5xx detail rule
   already keeps internals off the wire.

Everything else — media type, `cache-control`, `x-accel-buffering`, the ping,
disconnect, graceful shutdown — is `EventSourceResponse`'s and is not
re-implemented. Caller `headers` merge last so an application can override.

**Packaging.** Add to `rn-forge-fastapi/pyproject.toml`:

```toml
[project.optional-dependencies]
sse = ["sse-starlette>=3.4.11"]
```

and add `rn-forge-fastapi[sse]` to the `dev` and `docs` dependency groups so a
`--group dev` sync exercises the module instead of skipping its tests.
**Document the `AppStatus` uvicorn monkey-patch** in the module docstring as
the reason it is an extra and not a base dependency.

Per CLAUDE.md, a module behind an extra is **not** re-exported from the curated
`__init__.py` — import `rn_forge.fastapi.sse` directly, exactly as
`rn_forge.web.oidc` is.

**Tests** (`packages/rn-forge-fastapi/tests/test_sse.py`, opening with
`pytest.importorskip("sse_starlette")`): `TestClient` streaming a few frames and
asserting the wire bytes; an `id` or `event` containing a newline raising
`WebError`; the heartbeat under an idle generator with a small `ping`; the error
frame body validating as a `ProblemDetail` with the expected status; the
correlation header present on the response; caller headers overriding a default.

**Do not add SSE cases to `rn_forge.web.conformance.CASES`.** Both framework
drivers run every case with no skips and `rn-forge-django` has no SSE adapter;
a case there breaks the Django suite. Say so in the module docstring.

**Docs.** `packages/rn-forge-fastapi/docs/api/sse.md` plus a section in that
package's wiring guide. Nothing in `rn-forge-web`'s docs: this phase adds
nothing there.

## Phase 4 — exception-carried problem extensions and table audit (`rn-forge-web`)

**Evidence.** `intellibuild_api/handlers.py` special-cases one exception class
inside the shared handler to put `current_version` on the wire — the only way to
add a member without forking the handler. Apollo puts `AppException.error_data`
into its envelope. IntelliBuild also maintains `test_error_mapping_is_total`, a
bespoke test proving its table covers every domain error; the other three have
no such test, so an unregistered domain error becomes a 500 with nothing to
catch it.

**Build.** In `src/rn_forge/web/problem.py`:

- A `runtime_checkable` protocol:

  ```python
  @runtime_checkable
  class HasProblemExtensions(Protocol):
      def problem_extensions(self) -> Mapping[str, Any]: ...
  ```

  `ProblemRegistry.build` calls it when the exception implements it, merging the
  result **beneath** its own `extensions=` argument (an explicit caller value
  wins) and **only when the resolved row's status is below 500** — a 5xx body
  says nothing about the cause, and that rule must not be reachable around.
  `ProblemDetail.as_body` already drops core-member collisions.
- A read-only `ProblemRegistry.fallback` property.
- `unmapped_exceptions(registry, *bases) -> list[type[BaseException]]` —
  recursively walks `__subclasses__()` from each base and returns, sorted by
  qualified name, every class whose `problem_for` resolves to the registry's
  fallback. An application calls it from a test or a readiness check.

**Explicit decision to record in the docstring:** `AppException.error_data` is
**not** published automatically. It is an arbitrary context dict that routinely
carries credentials and internal identifiers; an application that wants some of
it on the wire implements `problem_extensions()` and chooses the members.

**Tests** (`tests/test_problem.py`): extensions merged from the exception; the
caller's `extensions=` overriding a same-named one; nothing merged on a 5xx row;
an exception without the method unchanged; `unmapped_exceptions` finding a
subclass that resolves to the fallback and not finding one that resolves through
its base's row.

**Docs.** `docs/api/problem.md` and the error section of
`docs/adoption/api-conventions.md`.

## Phase 5 — correlation ID validation (`rn-forge-web`)

> **Withdrawn by R3, 2026-09-22.** R3 replaced `X-Correlation-ID` with W3C
> Trace Context through OpenTelemetry. The hand-written validator below is
> gone: the W3C propagator already validates the inbound `traceparent` — a
> malformed value is discarded and a new trace starts — so there is nothing
> left for this phase to build. See
> [R3](standards-rebaseline-plan.md#r3-correlation-through-w3c-trace-context--decided-2026-09-22-ready-to-implement).

**Evidence.** Apollo parses the inbound `X-Request-ID` as a UUID and generates a
fresh one when it does not parse. IntelliBuild and
`rn_forge.web.CorrelationIdMiddleware` accept whatever arrives. pykit then
echoes that value on the response, writes it into every log record
(`correlation_log_processor`) and into every problem body — so an arbitrary
caller string of arbitrary length reaches three sinks unexamined. Practically
this is log forging and log bloat rather than response splitting (the ASGI
server rejects a CRLF in a header value), but the kit should not be the thing
that passes it along. `asgi-correlation-id` validates by default; pykit should
too.

**Build.** In `src/rn_forge/web/context.py`:

- `MAX_CORRELATION_ID_LENGTH: Final = 128`
- `is_valid_correlation_id(value: str) -> bool` — true for 1–128 characters of
  `[A-Za-z0-9._:-]`.

In `src/rn_forge/web/asgi.py`, `CorrelationIdMiddleware` gains
`validator: Callable[[str], bool] = is_valid_correlation_id`, mirroring
`asgi-correlation-id`'s `generator`/`validator` pair. A value the validator
rejects is replaced by `generator()`. Passing `lambda _: True` restores today's
behavior. Deliberately **not** a sanitizer: trimming or rewriting a caller's ID
produces an ID that matches neither end's logs.

This **changes the documented contract** — "a caller-supplied ID is never
replaced" becomes "never replaced when it is well-formed". Amend that docstring
and the class example in the same edit, and check
`rn_forge.web.conformance.CASES` for a correlation case sending an ID the new
default would reject; if one exists, update the case and both framework drivers
together.

**Tests** (`tests/test_context.py`, `tests/test_asgi.py`): a conforming ID is
passed through; an over-long one, an empty one and ones containing a newline,
a space or `%` are each replaced by a generated ID; a custom validator is
honored; the response header always carries the ID that was bound.

## Phase 6 — an opt-in CORS module (`rn-forge-fastapi`)

**Superseded by [standards-rebaseline-plan](standards-rebaseline-plan.md) R2.5 B8**,
which extends it to Django and moves the exposed-header list into `rn-forge-web`.

**The application owns its CORS policy** — which origins, and whether there is
one at all. The [app-layer plan](fastapi-app-layer-plan.md) scoped CORS out on
exactly that ground and that holds. What pykit adds here is not a policy but an
**opt-in module carrying the industry defaults and the one default only pykit
can know**: nothing is installed unless the application asks for it.

**Evidence.** IntelliBuild is the only reviewed app that configures CORS, and it
makes `cors_allow_origin` a required setting so a missing value refuses to
start. All four ship a separately built frontend, so the rest reach this the
moment they stop proxying in development. The default only pykit can supply:
**a browser cannot read `ETag`, `Link` or the correlation header unless they are
named in `Access-Control-Expose-Headers`** — and the kit's own concurrency,
pagination and tracing contracts are delivered in exactly those headers. An
application-owned CORS block does not know what headers the kit emits; this
module does.

**Build.** A new module, `src/rn_forge/fastapi/cors.py` — its own module rather
than a field buried in `app.py`, so it is usable by an application that builds
its FastAPI instance itself:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class CorsPolicy:
    allow_origins: tuple[str, ...]
    allow_credentials: bool = False
    allow_methods: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    allow_headers: tuple[str, ...] = ("Authorization", "Content-Type", "If-Match", "Idempotency-Key")
    expose_headers: tuple[str, ...] = ("ETag", "Link")
    max_age: int = 600

def apply_cors(app: FastAPI, policy: CorsPolicy, *, correlation_header: str = DEFAULT_CORRELATION_HEADER) -> None: ...
```

- `CorsPolicy.__post_init__` raises a `WebError` when `allow_credentials` is set
  and `allow_origins` contains `"*"` — the combination browsers reject outright
  and the one that quietly makes a policy meaningless. `allow_origins` has **no
  default**: naming the origins is the application's decision, and a default
  would be a policy pykit does not get to make.
- `apply_cors` adds Starlette's own `CORSMiddleware` with the policy's values,
  appending *correlation_header* to both `allow_headers` and `expose_headers`
  so a renamed header stays consistent. It wraps `CORSMiddleware`; it does not
  reimplement any part of it.

**Opt-in wiring.** `AppConfig` gains `cors: CorsPolicy | None = None`. `None` —
the default — adds no middleware at all, which is today's behaviour exactly.
When set, `FastApiApp.__init__` calls `apply_cors` **after** the correlation
middleware: Starlette's `add_middleware` prepends to `user_middleware`, so the
last one added is outermost, and CORS must be outermost for an error response
to carry its headers.

**Tests** (`tests/test_cors.py`, `tests/test_app.py`): a preflight returns the
configured methods and headers; a simple response carries
`Access-Control-Allow-Origin` and exposes `ETag`, `Link` and the correlation
header; a 404 problem response still carries CORS headers (proves the
ordering); `CorsPolicy(allow_origins=("*",), allow_credentials=True)` raises;
`cors=None` adds no middleware; `apply_cors` works on a plain `FastAPI`.

**Docs.** A CORS section in `docs/guides/wiring.md` and a new
`docs/api/cors.md`, both stating that the policy is the application's and the
module only carries defaults. Export `CorsPolicy` and `apply_cors` from the
curated facade.

## Decision record: the wrapper class (finding 13)

Asked by the owner on 2026-09-19: the Account Portal still writes its own
`create_app()`, so should the package ship a `FastApiApp` class with
daisy-chained configuration for cleaner consumer composition roots?

**Resolved, same day, in two parts:**

- **A `FastApiApp` subclass — yes.** Built as Phase 0, on the owner's decision
  that consistency with `CliApp` is worth having if the subclass introduces no
  other problems. It does not: a probe against the real package showed
  identical runtime behaviour across middleware, problem handlers, health
  routes, OpenAPI caching and `operationId`s, and 0 errors under strict
  Pyright. `create_app` is removed rather than kept beside it.
- **A fluent builder — no.** Reasons in Phase 0's own rejection note: it is the
  "parallel framework" the app-layer plan excluded, it is mutable-builder
  configuration where principle 2 requires a frozen dataclass, it deletes no
  code, and `CliApp` — the precedent being matched — is a subclass, not a
  builder.

Two smaller results of the same question, folded into other phases: Phase 1
moves `install_component_schemas` into `AppConfig.components` so there is no
post-construction call to sequence, and Phase 6 gives CORS an opt-in module
rather than a repeated `add_middleware` line in every application.

## Rejected, with reasons

- **Offset/limit pagination envelope (finding 7).** Apollo returns
  `{items, page, page_size, total}` from roughly five routers. AIP-158 cursor
  pagination is settled and normative for both framework packages (plans README,
  "Standing rules"), and IntelliBuild asserts over its own document that no
  offset parameter exists anywhere. One application's grid UI is not a reason to
  ship a second pagination contract; Apollo migrates to `page_params` or keeps
  its envelope local. `apollo/index/paging.py` — the beets `LIMIT` pushdown — is
  library-specific and not a candidate at all.
- **`offload()` (finding 8).** One line over
  `starlette.concurrency.run_in_threadpool`. Its value in Apollo is the
  greppable name and the test that scans routers for unwrapped blocking calls —
  an application-local lint, not a library API.
- **SPA static mount (finding 9).** PhotoTidy's `SpaStaticFiles` falls back to
  `index.html` for extensionless 404s. One of four mounts its frontend from the
  API process; the rest serve the bundle separately. Revisit if a second one
  does it, and note the behaviour belongs with the deployment archetype (kiln)
  more than with the adapter package.
- **`serve` command (finding 10).** All four wrap `uvicorn.run`, and all four
  wrap it differently (host, port, reload, factory vs import string). It is one
  call, and `.importlinter`'s `fastapi-runtime-has-no-tooling` forbids
  `rn_forge.fastapi` importing `rn_forge.cli`, so the shared thing would have to
  be a bare function that saves nobody anything. Put the recipe in
  `rn-forge-fastapi/docs/guides/wiring.md`.
- **Settings facade (finding 11).** IntelliBuild and Apollo both use
  `pydantic-settings` with `env_prefix`, Apollo caching through `lru_cache`;
  Account Portal validates a YAML file with pydantic; PhotoTidy reads
  `os.environ` directly. `pydantic-settings` already does required-at-startup
  validation (principle 1), and `rn_forge.commons.lang.models.parse_model` /
  `ModelValidationError` already aggregate field paths. The gap is **guidance**:
  add a short section to the commons config guide saying when to reach for
  `rn_forge.commons.config.Config` (multi-file, merged, reference-resolving app
  config) versus `pydantic-settings` (process environment). That is this
  finding's only output.
- **Per-request dependency container (finding 12).** IntelliBuild's
  `PortContainer` plus fifteen `Depends` factories is hexagonal wiring for that
  application's ports. Nothing generic survives extraction, and a unified
  repository or service abstraction is permanently out of scope (web plan, "The
  unification boundary").

## Adoption findings — consumer work, no pykit change

Recorded because they are the largest source of the duplication above, and
because each is a place the reviewed code is weaker than what already ships:

- **IntelliBuild re-derives six pykit modules**: `correlation.py`, `problem.py`,
  `error_mapping.py`, `handlers.py`, `idempotency.py`, `concurrency.py` and the
  cursor half of `pagination.py` are `rn_forge.web` +
  `rn_forge.fastapi.register_problem_handlers` with different names. Its
  `_status_mapping` table is `ProblemRegistry.problem_for_status`; its MRO walk
  is `ProblemRegistry.problem_for`. Its `_custom_openapi` would discard the
  problem-schema repair if grafted onto a pykit app — Phase 1 is the supported
  way to do what it wants.
- **Apollo and PhotoTidy emit non-RFC-9457 errors.** Apollo returns
  `{"error": {code, message, detail}}`; PhotoTidy's `invoke()` maps domain
  errors onto `HTTPException(detail=...)`, so its bodies are FastAPI's
  `{"detail": ...}`. Both predate `rn-forge-web`. Apollo's `ApolloError`
  hierarchy (a `code` and a `status_code` per class) maps onto `ProblemRegistry`
  rows one-for-one.
- **`WireModel` is unused outside pykit.** Three of the four hand-roll wire
  models in `snake_case` or re-declare `alias_generator=to_camel`, which the
  camelCase convention already settles.
- **Only IntelliBuild proves its error table is total.** Phase 4's
  `unmapped_exceptions` is the supported replacement for that bespoke test.

## Consumer acceptance

> **Parked 2026-09-21:** the Account Portal and IntelliBuild are work in
> progress and adopt what ships; they no longer gate a phase. Phase 3's
> acceptance by PhotoTidy and Apollo stands.

A phase is not done until one application deletes the corresponding local code:

| Phase | Acceptance consumer |
| --- | --- |
| 0 | Account Portal — its `create_app()` returns a `FastApiApp`; it is the only consumer of the removed factory |
| 1, 2 | Account Portal — drops `_install_shared_shapes`, `openapi_document`'s dumping policy and `logging.py::redact`, keeping `ALL_SHAPES`, its output path and its logger configuration local |
| 3 | PhotoTidy (smallest: `services/events.py` keeps the broker, drops the frame strings) and Apollo `jobs.py` |
| 4, 5, 6 | IntelliBuild, as part of its move onto `create_app` |

Adoption needs a resolvable pykit revision, which means these phases land before
the release tags or the consumers pin the branch, as Account Portal does today.

## Validation

Narrow first, then the repository gates:

```bash
uv run pytest packages/rn-forge-web packages/rn-forge-fastapi packages/rn-forge-commons
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run lint-imports
uv run --group docs mkdocs build --strict
```

Acceptance requires: the focused tests and the strict docs build passing; the
import contracts intact; **no `create_app` left anywhere under `packages/`**
after Phase 0 (grep, including the docs and the conformance driver);
`uv sync --all-extras` resolving the new `sse` extra;
every new public symbol re-exported from its package's curated `__init__.py`
**except** `rn_forge.fastapi.sse`, which is behind an extra and imported
directly; and the consumer deletions above made without losing coverage.
