# Standards re-baseline plan

**Status:** planned, 2026-09-21, from an owner-requested review of `rn-forge-web`,
`rn-forge-fastapi` and `rn-forge-django`. It changes a premise the web, fastapi and
django plans were written under, so it takes precedence over them where they
disagree: [web-library-plan §9.1](web-library-plan.md), and
[web-api-reuse-plan](web-api-reuse-plan.md) Phases 1 and 5.

**R1 and R2 implemented, 2026-09-21. R2.5 (Parts A and B) implemented,
reviewed and committed, 2026-09-22 (`373d6bc`).** **R3 (W3C Trace Context
through OpenTelemetry, replacing `X-Correlation-ID`) implemented 2026-09-23,
ahead of R4 — see the R3 section for why.** **R4 (the shared wire types become
pydantic models in `rn-forge-web`) decided 2026-09-22, implemented
2026-09-23.** R5 follows them; R6 is
on the backlog (owner, 2026-09-23). **R7 (tabular transfer and bulk operations, adopting
`tablib` and `django-import-export`) is implemented and committed**; its
three open questions are settled. **R8 (AIP adoption where no RFC applies) done
2026-09-23** (see "R8 status"). **R9 (SQLAlchemy and `tablib` across both stacks) implemented
2026-09-23, uncommitted**: `rn-forge-sqlalchemy` is unparked and built for it. **R10 (a simplification pass after R3: delete what the adopted
OpenTelemetry instrumentation and Starlette already provide) implemented
2026-09-23, except R10.3, which stopped at its probe; R5's evaluations run
next, then R4.** Full validation block below is green, including the strict
docs builds; see "What is open" on the [status board](README.md) for detail.

## The premise

pykit exists because building a second and third API on FastAPI or Django turned
up copy-pasted plumbing: error handling, schema, pagination, preconditions,
idempotency, health, correlation. The kit removes that plumbing, so an
application's code is its functional logic. It does **not** add a layer a
developer has to learn in place of the framework, and it does not define the API
its consumers see.

For a consumer, an API is its wire behaviour, described by its OpenAPI document
and the published standards that document relies on. Whether the service behind
it was built with pykit, with the native libraries alone, or with Spring Boot
must not be observable **on the wire**. The document text, and any client
generated from it, may still show which generator produced it (see below).

Two consequences, which the standing rules in the [status board](README.md) now
carry:

1. **The order of authority is:** published standard → the framework's native
   mechanism → pykit's wrapper. pykit never owns a wire shape a standard already
   defines. `api-conventions.md` records choices *among* standards and fills the
   gaps no standard covers, and it names which one each rule comes from.
2. **A library that implements the standard is adopted.** The reason given for
   not adopting `fastapi-problem` and `fastapi-pagination`, "each decides a wire
   shape, and the wire shape is `rn-forge-web`'s", is withdrawn. A standard
   decides the wire shape, and a library that follows it is doing pykit's job
   for it. R5 re-runs those evaluations.
3. **Where no standard applies, the [AIPs](https://google.aip.dev) break the
   tie.** They are a naming and convention guide adopted for the gaps, not a
   design commitment: nothing from Google's gRPC or protobuf stack is used, and
   an AIP that an RFC already governs, or that only makes sense over gRPC
   (122, 134, 154, 155, 160, 193), is rejected. Adopting or rejecting a new AIP
   is judged by that test.

## What "identical across stacks" means

The earlier plans held Django and FastAPI to "the same wire", and in places
read that as "the same OpenAPI document". Those are different claims, and only
the first is a goal.

| Layer | Identical across stacks? | How |
| --- | --- | --- |
| **Wire behaviour**: status codes, headers, body shapes | **Yes, required** | Both follow the same RFCs. Each framework package configures its framework's defaults to them. The conformance cases prove it |
| **Schema semantics**: which JSON a request or response schema accepts | **Yes**, when the application declares the same model | The application's job; nothing is post-processed |
| **OpenAPI document text**: component names, `operationId`s, how nullability or enums are spelled, `title` keywords | **No, not a goal** | Each generator's native output, plus only the repairs needed for *accuracy* |

**Why the wire is not identical by default, even though both frameworks are
OpenAPI-compliant.** OpenAPI *describes* an API; it does not *prescribe* one. A
framework is compliant when the document it emits is valid and accurately
describes what the framework does, and the two frameworks' defaults differ:

- a failed body validation is FastAPI `422 {"detail": [{loc, msg, type}]}` and
  DRF `400 {"field": ["message"]}`;
- FastAPI's `Query(le=100)` rejects an oversized page with 422, where AIP-158
  clamps;
- Django's `APPEND_SLASH` answers a missing trailing slash with a 301; DRF
  answers `OPTIONS` with a metadata body; FastAPI answers both differently.

Each of those is accurately documented by its own generator, so both documents
are compliant and the two APIs still differ on the wire. Making them identical
means configuring each framework to one standard. That is legitimate plumbing,
and it is most of what the framework packages already do.

**Why the document text is not a goal.** Two compliant generators describing
the same JSON produce different text:

| Same schema | pydantic / FastAPI | drf-spectacular |
| --- | --- | --- |
| A nullable string | `anyOf: [{type: string}, {type: "null"}]` | `type: [string, "null"]` |
| A page of orders | `Page_OrderOut_` | `PaginatedOrderOutList` |
| An enum field | inlined, or a component named after the Python class | hoisted to a component `<Field>Enum` |
| One model used in and out | split into `-Input`/`-Output` components when they differ | one component with `readOnly`/`writeOnly` |
| Titles | a `title` on every property | none |

All of these accept exactly the same JSON. They do not produce the same
generated client. Most client generators, on any stack, derive type names and
type shapes from the document text, so a client generated from either
document works against either service, but its code differs:

| Generated client | Same on both stacks? | Why |
| --- | --- | --- |
| Method names | **Yes** | The shared `operationId` rule, kept by R1 |
| Declared error responses | **Yes**, after R1 | Both documents declare the problem+json responses (R1.3) |
| Model, page and enum type names | No | Component names differ (`Page_OrderOut_` / `PaginatedOrderOutList`, inlined / hoisted enums) |
| Model structure | No | `-Input`/`-Output` split vs one component with `readOnly`/`writeOnly`; some generators ignore `readOnly` |
| Nullable field types | Generator-dependent | `anyOf` with `null` becomes a wrapper or union type in some generators; `type: [T, "null"]` becomes a plain optional |
| Path-parameter names | Only when the application spells them the same | `{order_id}` on FastAPI vs DRF's default `{id}` |

Forcing textual identity means
post-processing each generator's output, which is where the OpenAPI patching
questioned on 2026-09-20 came from. It pays off only when one API is
re-implemented on another stack behind a client that must not change, and even
then the normalization would have to track every generator's output. The
standard way to get that is **spec-first**: one owned OpenAPI document, with
each implementation contract-tested against it. If that need arises, adopt that
approach rather than normalizing generator output.

**Accuracy repairs remain in scope.** The document must describe what the
service returns. The problem handlers send `application/problem+json`, so every
operation declares those responses and the `ProblemDetail` component. FastAPI's
own `responses=` cannot do that: a `model` always lands under the route's media
type, and a bare `$ref` does not register the component. That was probed on
FastAPI 0.141.1 on 2026-09-20.

The Django document has the same gap and no repair for it. `SPECTACULAR_SETTINGS`
appends the `ProblemDetail` component, but no operation declares a problem
response, and drf-spectacular does not declare 4xx responses by default. So the
Django document leaves out responses the service sends, and a client generated
from it has no typed errors. R1.3 closes this gap.

## Review findings

### The wire: standard, with five deviations

RFC 9457, RFC 9110/6585 preconditions, RFC 6750/7617 challenges, AIP-158
pagination and camelCase JSON are all as published. These are not:

| # | Today | The standard | Source |
| --- | --- | --- | --- |
| 1 | Idempotency key reused with a different body → **409** | **422** | `draft-ietf-httpapi-idempotency-key-header-07` §2.7, read 2026-09-21 |
| 2 | A retry while the original is in flight **executes again** (`record_or_replay` returns `None`) | **409** | same section |
| 3 | Validation errors are `errors[].{pointer, message}` | `errors[].{pointer, detail}` | RFC 9457 §3, the validation example |
| 4 | `type: about:blank` with kit titles ("Validation Error") | With `about:blank`, the title should be the HTTP status phrase ("Unprocessable Content") | RFC 9457 §4.2.1 |
| 5 | `X-Correlation-ID` and a `correlation_id` problem member | W3C Trace Context (`traceparent`); no standard names a correlation header | W3C Trace Context; OpenTelemetry, which `rn-forge-commons` already integrates |

### The code: where the kit became a layer

- **Each shared wire type is modelled three times.** `ProblemDetail`, `Page`,
  `CheckResult` and `HealthReport` exist as `rn-forge-web` dataclasses, as
  pydantic copies in `rn_forge.fastapi.schemas` with `from_wire`/`to_wire`
  converters, and again on the DRF side. R4 (2026-09-23) collapsed them to
  one pydantic model per type in `rn-forge-web`.
- **Libraries were rejected because pykit owned the format.** This covers
  `fastapi-problem` and `fastapi-pagination` (see the premise).
  `asgi-correlation-id` was rightly kept out of `rn-forge-web`, which is
  Starlette-free, but nothing kept it out of `rn-forge-fastapi`, which imports
  Starlette anyway.
- **Cross-stack naming machinery.** `page_component_name`, the generic-name
  rename in `rn_forge.fastapi.openapi` and the Page rename in `WireAutoSchema`
  exist to make the two documents' text match. That is the non-goal above.
- **`rn-forge-django` scope.** `drf/views/transfer.py` (about 1,300 lines of
  Excel/CSV import and export) is loaded by the `drf` facade, so every
  DRF-bringing extra requires `rn-forge-commons[excel]`. SAML, Celery, fixtures
  and messaging are Django tooling, not web-API plumbing.

### Reviewed and kept

- `FastApiApp` as a plain `FastAPI` subclass; `page_params`, `require_if_match`
  and `require_idempotency_key` as ordinary FastAPI dependencies; the health
  router; the RFC 9457 exception handlers on both stacks; drf-spectacular
  configured through its own hooks.
- camelCase through pydantic's own `alias_generator` (`WireModel`).
- `rn_forge.django.drf.casing`. The review's first draft counted it as a
  reimplementation of `djangorestframework-camel-case`. That library's last
  release is 1.4.2 (2023-02), which is a valid principle-1 exemption, recorded
  in the django README.
- `operation_id`. Both frameworks take it through a native hook
  (`generate_unique_id_function`, `AutoSchema.get_operation_id`), and FastAPI's
  default (`read_item_items__item_id__get`) makes a poor generated client even
  for a single API. It stays as a default for client ergonomics, not for parity.
- `Principal`, `Authenticator` and `OidcAuthenticator`. One JWT verification
  path is shared by both stacks, and the FastAPI surface remains a native
  `Security` dependency.
- The conformance cases, **reframed** as tests of wire behaviour against the
  standards (the table's first row), not as a parity harness.

## Phases

### R1: OpenAPI, accuracy only (`fastapi`, `django`, `web`) — done, 2026-09-21

1. **Withdraw web-api-reuse Phase 1.** Remove `install_component_schemas`,
   `openapi_json` and `AppConfig.components`, with their tests and docs. Its only
   evidence came from the Account Portal and IntelliBuild, which are parked
   (owner, 2026-09-21). An application that needs an unreferenced component
   overrides `openapi()` on its own subclass.
2. **Replace the attribute patching with a method override.**
   `FastApiApp.openapi()` calls `super().openapi()` and repairs the cached
   document once. `install_problem_schema` becomes private. A consumer subclass
   extends it through `super()`; that composition was probed on 2026-09-21.
3. **The repair declares the problem responses and nothing else.** It keeps the
   `ProblemDetail` component, the problem+json response per registry status,
   and the replacement of FastAPI's 422.
   - Drop the `OPENAPI_VERSION` pin: 3.1.0 is FastAPI's default. Keep a test
     that asserts it.
   - Drop the generic-name rename on FastAPI, the Page rename in
     `WireAutoSchema`, and `page_component_name` from `rn_forge.web`.
   - **Django gets the same repair.** Every operation declares an
     `application/problem+json` response referencing `ProblemDetail` for each
     registry status plus 500, without overwriting one the author declared.
     Do this through drf-spectacular's own mechanism: a postprocessing hook in
     `SPECTACULAR_SETTINGS`, or an override on `WireAutoSchema`. Choose the one
     that can read the registry the problem handler renders with.
   - A test on each stack asserts that every operation declares those
     responses.
4. Rewrite `api-conventions.md` §9 around the layer table above. Include what
   a generated client shares across stacks and what it does not.

**Implementation notes.** `install_problem_schema` is now
`rn_forge.fastapi.openapi.repair_problem_schema` — not underscore-private
(pyright's `reportPrivateUsage` forbids that across a module boundary, and
`FastApiApp.openapi()` is in a different module), but dropped from the
package's `__all__`/facade, which is what "private" means for every other
cross-module helper in this workspace. Its `default_responses=` toggle was
dropped along with it: nothing wired it to `AppConfig`, and the repair is
accuracy-only per item 3. Django's `OPENAPI_VERSION` constant (in
`rn_forge.django.drf.openapi`) is **kept** — unlike FastAPI's redundant pin,
it is load-bearing: drf-spectacular's own default `OAS_VERSION` is `3.0.3`,
so the acceptance grep for `OPENAPI_VERSION` below is read as scoped to the
FastAPI-side pin the bullet above describes, not this unrelated one.

### R2: the standards deviations (`web`, both drivers) — done, 2026-09-21

1. `IdempotencyKeyReuse` → **422**. A duplicate in flight → **409**. This needs
   an in-flight signal from `IdempotencyStore.record_or_replay` (a distinct
   exception or return), implemented in the in-memory stores and in django's
   `CacheIdempotencyStore`.
2. `errors[].message` → `errors[].detail`, in `errors_from_pointer_list`,
   `errors_from_field_map` and both validation handlers.
3. With `about:blank`, `title` is the status phrase (`HTTPStatus(...).phrase`).
   Kit-specific titles are used only when a `type_base` is configured, because
   then `type` is a real URI that the title describes.
4. Update `api-conventions.md` §2 and §5 and the affected conformance cases.
   Both drivers must pass with no skips.

**Implementation notes.** The in-flight signal is a new exception,
`IdempotencyKeyInFlight` (409), registered on `default_registry()` alongside
`IdempotencyKeyReuse` (now 422) — both stores raise it instead of returning
`None` for a claimed-but-incomplete key, which is a behaviour change from the
prior "returns `None`, caller re-executes" contract (see the updated
docstrings and tests on `InMemoryIdempotencyStore` and
`CacheIdempotencyStore`). No conformance-table case exercises the in-flight
path: the table drives one request at a time through a synchronous test
client, which cannot represent a request genuinely still in flight when a
second one arrives — that scenario is covered at the store unit-test level on
both `rn_forge.web` and `rn_forge.django`.

### R2.5: shared logic in `web`, and the standard service surface — done, 2026-09-22

**Parts A and B implemented, reviewed and committed (`373d6bc`), 2026-09-22.**
Where the implementation departs from the spec below, "Part B implementation
notes" records it; the spec text is kept as written.

The owner's rule, from the review of R1 and R2, applies to all of it:

1. **Standard first.** pykit provides the industry-standard pattern for each
   thing an API microservice needs today. A requirement is implemented when a
   published standard or a de facto one (Kubernetes, OWASP, OpenTelemetry)
   defines it.
2. **Common logic lives in `rn-forge-web`,** as framework-free code: path
   constants, body and header builders, exceptions and registry rows, and pure
   ASGI middleware where no framework hook is needed.
3. **The framework packages only wire it,** each through its framework's own
   pattern. For FastAPI that is an `APIRouter`, a dependency, ASGI middleware,
   or `FastApiApp`/`AppConfig`. For Django it is a `urlpatterns` factory, a
   view decorator, a middleware, a settings fragment, or a registry row.
4. **Library first** (README principle 1). Before hand-rolling any B item,
   check for a maintained library that implements the standard and can be
   configured to `api-conventions.md`. Wrap it if one exists. Otherwise record
   the exemption in the module docstring. The candidates checked on
   2026-09-22 are named in each item.
5. **Host-neutral.** No code assumes a platform (Kubernetes, Azure App
   Service, App Engine, Cloud Run). Paths and timeouts are defaults that can
   be overridden, and host-specific mapping lives in documentation (B12).
6. **Adopted first** (owner, 2026-09-23, from R10). When a library or the
   framework is adopted for a concern, everything it already emits or
   enforces is deleted from the kit, including code that predates the
   adoption.

#### Part A: shared logic moved into `web` (done)

| Was duplicated or misplaced | Now |
| --- | --- |
| Problem-response assembly (correlation extension, masked 401 detail, challenge) in both handlers | `render_problem` → `ProblemResponse` |
| `errors_from_pointer_list` (pydantic shape) and `errors_from_field_map` (DRF shape) in `web` | Private adapters in `rn_forge.fastapi.problem` and `rn_forge.django.drf.exceptions`, on `web.field_error` and `REQUIRED_FIELD_DETAIL` |
| Correlation ID validation in the ASGI middleware only; Django's echoed any inbound value | `resolve_correlation_id`, used by both middlewares |
| Liveness: FastAPI `{"status": "pass"}`, Django `healthy` as text | `liveness_body`, used by both |
| `Authorization` header parsing by hand on Django and FastAPI Basic | `parse_authorization` |
| `Idempotency-Key` name and presence check on both | `IDEMPOTENCY_KEY_HEADER`, `check_idempotency_key` |
| Problem-response declarations in both OpenAPI repairs; `PROBLEM_DETAIL_SCHEMA` in django | `rn_forge.web.openapi`: `problem_statuses`, `problem_response`, `add_problem_responses`, `PROBLEM_DETAIL_SCHEMA` |

Wire changes in Part A:

- Django's liveness body is now JSON.
- Django replaces a malformed inbound correlation ID.
- A FastAPI 401 keeps a challenge the exception already carries instead of
  overwriting it, which was already Django's rule.

#### Part B: the standard service surface (done)

Each item lists the standard, then the `web` piece, then the FastAPI and
Django wiring. **Every wire-visible item adds conformance cases** in
`rn_forge.web.conformance.cases`, with a new `ConformanceArea` where needed.
Each case is served by all three drivers:

- `rn-forge-web/docs/adoption/examples/asgi_app.py`, which the web tests
  execute;
- `rn-forge-fastapi/tests/test_conformance.py`;
- `rn-forge-django/tests/test_conformance.py`.

Update `api-conventions.md` with each rule and the standard it comes from.
Unless an item says otherwise, a default below is the decision; do not stop to
ask.

**B1. Health probes: liveness and readiness, platform-neutral.**

- *The contract is two semantics, not a platform.* **Liveness** answers
  whether the process can serve at all, and touches no dependency.
  **Readiness** answers whether this instance should receive traffic, and runs
  the dependency checks. Every host probes a configurable HTTP path; see B12
  for how each host maps onto the two.
- *What a probe reads.* Every host judges the probe by its **status code
  and response time only**. None reads the body. Kubernetes accepts 200–399,
  Azure App Service 200–299, and App Engine flexible exactly 200. So the
  contract is: liveness answers **200**; readiness answers **200** or **503**;
  neither ever redirects. The JSON body is for people and monitoring tools,
  and is the same on every host.
- *Default paths.* `/livez` and `/readyz`, with `/healthz` as an alias of
  liveness. Kubernetes deprecated `/healthz` in v1.16 in favour of `/livez`
  and `/readyz` (kubernetes.io "Kubernetes API health endpoints", read
  2026-09-22), and no other host defines a default path: Azure App Service and
  App Engine flexible both take whatever path is configured.
- *web.* Add `LIVENESS_PATH = "/livez"`, `READINESS_PATH = "/readyz"` and
  `LEGACY_LIVENESS_PATH = "/healthz"`, as defaults only.
  - `run_checks_sync` gains `timeout=`, with the same semantics as
    `run_checks`. Run the checks in a `concurrent.futures.ThreadPoolExecutor`
    and report a check still running at the timeout as `fail` (`timed out
    after Ns`). This closes Django's missing timeout.
  - The per-check timeout defaults to **2 seconds** on both stacks, not
    `None`. It must sit below the host's probe timeout: App Engine flexible
    defaults to 4 s, and Kubernetes to 1 s, which the B12 guide tells the
    deployer to raise.
- *FastAPI.* `health_router` serves all three paths. `/healthz` is the same
  handler as `/livez`, marked `deprecated=True` in OpenAPI. The paths are
  keyword arguments (`liveness_path=`, `readiness_path=`,
  `legacy_liveness_path=`, where `None` drops the alias), exposed on
  `AppConfig`.
- *Django.* Add `rn_forge.django.views.health_urlpatterns(*, checks, required=(),
  timeout=2.0, liveness_path=..., readiness_path=..., legacy_liveness_path=...)
  -> list[URLPattern]`, serving the paths with no trailing slash. Probes on
  every host fail on a redirect, so an `APPEND_SLASH` 301 would mark the
  instance unhealthy.
  - Rename `healthcheck_view` to `liveness_view`.
  - Drop `healthcheck/` from `rn_forge.django.urls`; that URLconf keeps only
    the index and debug-request views.
  - Update `docs/guides/quickstart.md`. There are no compatibility aliases
    (README).
- *Body.* Keep `application/json` and today's shape. `api-conventions.md` §6
  must say that the `pass`/`warn`/`fail` vocabulary comes from
  `draft-inadarei-api-health-check` (expired at -06, 2022), and that pykit
  keeps `checks` as an object keyed by name rather than the draft's
  `application/health+json` arrays.
- *Not built.* There is no startup endpoint, because no host defines one; a
  Kubernetes `startupProbe` reuses `/livez`. There is no in-app drain flag:
  shutdown is the host's signal plus the server's graceful shutdown, and the
  B12 guide covers it per host.

**B2. Service discovery: the OpenAPI document, the docs UI, and
`/.well-known/api-catalog`.**

- *Standard.* RFC 9727 (June 2025, Proposed Standard) defines the
  `/.well-known/api-catalog` URI. It returns an RFC 9264
  `application/linkset+json` document whose links use the RFC 8631 relations
  `service-desc` (machine-readable description: the OpenAPI document),
  `service-doc` (human docs) and `status` (`/readyz`).
- *web.*
  - Add `OPENAPI_PATH = "/openapi.json"`, `DOCS_PATH = "/docs"`,
    `API_CATALOG_PATH = "/.well-known/api-catalog"` and
    `LINKSET_MEDIA_TYPE = "application/linkset+json"`.
  - Add `api_catalog_body(*, anchor, service_desc, service_doc=None,
    status=None) -> dict[str, Any]`, following RFC 9727 §4's example.
- *FastAPI.* The OpenAPI document and docs UI stay FastAPI's own
  (`openapi_url`, `docs_url`); only assert that the defaults equal the web
  constants.
  - `FastApiApp` serves the api-catalog, with `AppConfig.api_catalog: bool =
    True`. The catalog answers `GET` and `HEAD` and is excluded from the
    OpenAPI document (`include_in_schema=False`).
- *Django.* Add `rn_forge.django.drf.openapi.openapi_urlpatterns() ->
  list[URLPattern]` (behind the `openapi` extra). It serves drf-spectacular's
  own `SpectacularAPIView` at `OPENAPI_PATH` (JSON), `SpectacularSwaggerView`
  at `DOCS_PATH`, and an api-catalog view.

**B3. Deprecation and Sunset headers.**

- *Standard.* RFC 9745 (March 2025) defines the `Deprecation` field (a
  structured-field date, `@<epoch-seconds>`) and the `deprecation` link
  relation. RFC 8594 defines the `Sunset` field (an HTTP-date) and the `sunset`
  link relation.
- *web.* Add `deprecation_headers(*, deprecated_at: datetime, sunset:
  datetime | None = None, link: str | None = None) -> dict[str, str]`, which
  emits `Deprecation`, `Sunset`, and `Link` with `rel="deprecation"`.
- *FastAPI.* Add a dependency factory, `deprecated(...)`, that sets the headers
  on the response. The route also passes FastAPI's own `deprecated=True`, and
  the guide shows both together.
- *Django.* Add a view decorator, `@deprecated(...)`, that sets the headers.
  The guide shows it with drf-spectacular's `@extend_schema(deprecated=True)`.

**B4. Conditional GET: `If-None-Match` → 304.**

- *Standard.* RFC 9110 §13.1.2 and §15.4.5. `GET`/`HEAD` with a matching
  `If-None-Match` (weak comparison, `*`, comma lists) → 304, with no body and
  the `ETag` repeated.
- *web.* Add `is_not_modified(if_none_match: str | None, etag: str) -> bool` in
  `concurrency.py`.
- *FastAPI.* Add `conditional_get(request, etag) -> Response | None`, which
  returns the 304 to send, or `None`.
- *Django.* Adopt Django's own `ConditionalGetMiddleware`, which does weak
  `If-None-Match` comparison for any response carrying an `ETag`. Document it
  in the settings guide and cover it with the conformance case; no new code.

**B5. 429 and 503 with `Retry-After`.**

- *Standard.* RFC 6585 §4 (429) and RFC 9110 §10.2.3 (`Retry-After`) and
  §15.6.4 (503).
- *web.*
  - Add `TooManyRequests` and `ServiceUnavailable` exceptions, each taking
    `retry_after: int | None` in seconds, with the rows `TOO_MANY_REQUESTS`
    (429) and `SERVICE_UNAVAILABLE` (503) in `default_registry()`.
  - Add a `HasResponseHeaders` protocol, alongside `HasProblemExtensions`.
    `render_problem` merges its headers beneath the caller's `headers=`.
- *Both stacks.* No wiring beyond `render_problem`. Add conformance cases.
- *Not built.* Enforcing a rate limit is a gateway's job, or a library's
  (`slowapi` 0.1.10 and `limits` 5.8.0 are maintained; `django-ratelimit`
  4.1.0 is from 2023). The `RateLimit`/`RateLimit-Policy` headers are still
  `draft-ietf-httpapi-ratelimit-headers-11`. Both go to R5.

**B6. API security response headers.**

- *Standard.* The OWASP REST Security Cheat Sheet's response headers:
  `Cache-Control: no-store`, `Content-Security-Policy: frame-ancestors
  'none'`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Strict-Transport-Security` (HTTPS deployments only), and
  `Referrer-Policy: no-referrer`.
- *Library check first.* `secure` (2.0.1, 2026-04) is framework-agnostic with
  ASGI support. If it can emit exactly this preset without a framework import,
  `web` wraps it behind a new `security` extra. Otherwise, hand-roll it and
  record the exemption.
- *web.* Add `API_SECURITY_HEADERS: Mapping[str, str]` (the preset without
  HSTS) and a pure-ASGI `SecurityHeadersMiddleware` that uses setdefault
  semantics, so a route's own `Cache-Control` wins.
- *FastAPI.* `FastApiApp` installs it by default, with
  `AppConfig.security_headers: bool = True` and an `hsts: bool = False` flag.
- *Django.*
  - Add a `SECURITY_SETTINGS` fragment for Django's own `SecurityMiddleware`
    and `XFrameOptionsMiddleware` (`SECURE_CONTENT_TYPE_NOSNIFF`,
    `SECURE_REFERRER_POLICY`, `X_FRAME_OPTIONS`, HSTS settings).
  - Add a small middleware for the two headers Django has no setting for
    (`Cache-Control`, CSP `frame-ancestors`), reading `API_SECURITY_HEADERS`.

**B7. Request body size limit: 413.**

- *Standard.* RFC 9110 §15.5.14 ("413 Content Too Large").
- *web.* Add a `ContentTooLarge` exception and a `CONTENT_TOO_LARGE` row. Add
  a pure-ASGI `BodySizeLimitMiddleware(max_bytes)` that rejects on
  `Content-Length` and on streamed bytes.
- *FastAPI.* Install it from `AppConfig.max_body_bytes: int | None =
  1_048_576`; `None` disables it. Uvicorn itself sets no limit.
- *Django.* Keep Django's own `DATA_UPLOAD_MAX_MEMORY_SIZE`, and map its
  `RequestDataTooBig` to `CONTENT_TOO_LARGE` in `problem_registry()`. Django
  answers 400 by default, which is wrong.

**B8. CORS on both stacks** (supersedes web-api-reuse Phase 6, which was
FastAPI-only and is not yet implemented).

- *web.* Add `EXPOSED_HEADERS`: the response headers the kit emits that a
  browser can read only when they are exposed. These are `ETag`, `Link`,
  `Location`, the correlation header, `Retry-After`, `Deprecation` and
  `Sunset`.
- *FastAPI.* Keep Phase 6 as written, over Starlette's `CORSMiddleware`, with
  `expose_headers` from `EXPOSED_HEADERS`.
- *Django.* Add a `cors_settings(allowed_origins)` fragment for
  `django-cors-headers` (4.9.0, 2025-09), behind a new `cors` extra, with
  `CORS_EXPOSE_HEADERS` from `EXPOSED_HEADERS`. The application owns the
  origins on both stacks.

**B9. One access-log event on both stacks, in OpenTelemetry semantic-convention
names.**

- *Standard.* OpenTelemetry HTTP semantic conventions: `http.request.method`,
  `url.path`, `http.response.status_code`, and the request duration.
- *web.* Add `request_log_fields(*, method, path, status, duration_ms,
  correlation_id) -> dict[str, Any]`. The ASGI `CorrelationIdMiddleware`
  gains an optional `log=` sink and emits `request.complete` with those
  fields, as Django's middleware already does.
- *FastAPI.* `AppConfig.log` feeds it.
- *Django.* The middleware's event switches to the same field names.

**B10. A framework-free idempotency runner.**

- *Standard.* `draft-ietf-httpapi-idempotency-key-header-07` (see R2).
- *web.* Add `run_idempotent(store, *, scope, key, method, body, execute) ->
  StoredResponse` and its async twin. It holds the whole flow: safe methods
  bypass, claim, replay, complete, and 409/422 from the store.
- *FastAPI.* A dependency or route decorator over the async twin.
- *Django.* Rewrite `@idempotent` over the sync runner; keep its public
  signature.

**B11. `VersionConflict` subclasses `WebError`, not `DomainConflict`,** so
catching the 409 class no longer catches 412s.

**B12. A deployment guide: one contract, mapped per host.**

The kit's code stays host-neutral. Nothing in `web`, `fastapi` or `django`
knows which platform it runs on. Add `rn-forge-web/docs/adoption/deployment.md`,
which is `api-conventions.md`'s companion for operators, with the mapping below
and a link from both framework packages' guides (by name, not a cross-package
link). The facts were read on 2026-09-22 from each vendor's docs; recheck them
when editing.

| Host | Probes it offers | Map to | Notes |
| --- | --- | --- | --- |
| Kubernetes (also AKS, GKE, Cloud Run, Azure Container Apps) | `livenessProbe`, `readinessProbe`, `startupProbe` | `/livez`, `/readyz`, `/livez` | Set `timeoutSeconds` ≥ 3, above the 2 s check timeout. A `preStop` sleep lets endpoint removal propagate before `SIGTERM` |
| App Engine flexible | `liveness_check`, `readiness_check` in `app.yaml`, each with a configurable `path` | `/livez`, `/readyz` | Only `200` counts as healthy. The default timeout is 4 s. `/_ah/health` legacy checks are deprecated. An instance is downscaled 25 s after the shutdown signal |
| Azure App Service | **One** Health check path; any 2xx is healthy; pinged every minute; after N failures (`WEBSITE_HEALTHCHECK_MAXPINGFAILURES`, 2–10) the instance leaves the load balancer, and after an hour it is replaced | `/readyz` | Microsoft's guidance is that the path checks critical dependencies and returns 2xx only once warm, which is readiness. It never removes more than `WEBSITE_HEALTHCHECK_MAXUNHEALTHYWORKERPERCENT` (default 50) of instances, and none when all are unhealthy, so a shared dependency outage does not drain the app. Health check does not follow redirects: enable **HTTPS Only** rather than an app-level HTTPS redirect, and ping the default domain. The path must allow anonymous access |
| App Engine standard | **No** configurable health checks | none | Point an uptime check at `/readyz` for monitoring. Warmup requests (`/_ah/warmup`, via `inbound_services: warmup`) and manual/basic-scaling `/_ah/start` are platform hooks, so the application registers them if it wants them. `SIGTERM` gives about 2 s before `SIGKILL` |

The guide also covers the cross-cutting points that differ by host:

- **TLS terminates at the host's front end.** Trust `X-Forwarded-Proto` and
  `X-Forwarded-For`: uvicorn `--proxy-headers --forwarded-allow-ips`, Django
  `SECURE_PROXY_SSL_HEADER` and `USE_X_FORWARDED_HOST`. Otherwise `Location`,
  `Link` and the B2 catalog links carry `http://`. Leave B6's `hsts` off unless
  the host doesn't set HSTS itself.
- **CORS.** Azure App Service has a platform CORS feature. Microsoft's guidance
  is not to combine it with application CORS, so use B8's and leave the
  platform's off.
- **Body size.** Each host's front end has its own cap. B7's limit is the
  application's, and it should sit at or below the host's.
- **Port.** The server binds to the host's port variable (`PORT` on App
  Engine and Cloud Run, `WEBSITES_PORT` for Azure custom containers). That is
  server configuration, not kit code.
- **Logs and traces.** All four hosts collect JSON logs from stdout. W3C
  `traceparent` is understood by Cloud Trace and Azure Monitor alike, which is
  one more reason R3 option a (OpenTelemetry) is the host-neutral choice.

To verify while writing the guide: whether App Engine standard counts a 404
on `/_ah/start` (sent under manual or basic scaling) as a successful start.
The vendor pages read on 2026-09-22 don't say. If it doesn't, the guide shows
the one-line handler.

Not built: helpers for one host only, such as validating Azure's
`x-ms-auth-internal-token` on the health path or an App Engine `/_ah/warmup`
handler. They are not standards. The guide shows each as a short snippet the
application adds when it needs it.

#### Part B implementation notes

All twelve items shipped in `373d6bc`, in the handoff order, with conformance
cases on all three drivers (new areas `deprecation`, `discovery`, `security`
and `cors`). Where the code differs from the spec above:

| Item | As built |
| --- | --- |
| B1 | `AppConfig.check_timeout = 2.0` is the FastAPI default. `health_router(timeout=None)` keeps `None` as its own default, because `FastApiApp` always passes the config's value. `health_urlpatterns(timeout=2.0)` on Django |
| B2 | `openapi_urlpatterns(*, readiness_path=READINESS_PATH)`: the catalog's `status` link follows a readiness path the application moved |
| B3 | `rn_forge.fastapi.deprecation.deprecated` and `rn_forge.django.deprecation.deprecated` (a decorator on both). `deprecation_headers` in `rn_forge.web.deprecation` |
| B6 | The library check passed: **`secure` is wrapped**, not hand-rolled, in `rn_forge.web.security` behind web's `security` extra (approved). It also exports `HSTS_HEADER`. `rn-forge-fastapi` takes `rn-forge-web[security]` as a hard dependency, because `FastApiApp` installs the middleware by default. Django adds a `security` extra and `rn_forge.django.security` (`SECURITY_SETTINGS`, `SecurityHeadersMiddleware`) |
| B8 | FastAPI: `rn_forge.fastapi.cors` (`CorsPolicy`, `apply_cors`), wired from `AppConfig.cors: CorsPolicy \| None = None`. Django: `rn_forge.django.cors.cors_settings` behind the `cors` extra (`django-cors-headers>=4.9.0`, approved) |
| B9 | `EXPOSED_HEADERS` and `request_log_fields` live in `rn_forge.web.context`. The Django middleware keeps the name `CorrelationIdMiddleware`; R3 renames it |
| B10 | The async twin is `run_idempotent_async`. FastAPI's binding is a route decorator, `rn_forge.fastapi.idempotency.idempotent` |
| B12 | `rn-forge-web/docs/adoption/deployment.md`. The `/_ah/start` question stays unconfirmed against vendor docs, so the guide registers an always-200 handler as the safe default |

Still open after R2.5: the combined root `mkdocs build --strict` fails on the
two pre-existing links named in the handoff notes.

#### Not in R2.5

- **The exception classes stay.** `rfc9457` (0.4.1, 2026-02; the core of
  `fastapi-problem`) is the only maintained framework-free library. It puts
  status and type on the class and derives `type` from the class name, which
  conflicts with the registry and with R2.3's `about:blank`. Evaluate it in
  R5.
- **`/metrics`** goes with R3. Once OpenTelemetry is adopted, metrics come
  from its SDK (OTLP push, or `opentelemetry-exporter-prometheus` for pull).
  pykit does not hand-roll a `/metrics` endpoint.
- **`traceparent` and the correlation header** stay in R3, now decided (W3C
  Trace Context). B9's field names already follow OpenTelemetry.
- **RFC 9116 `security.txt`** is not in scope. It belongs to a public web
  property, not to each microservice.
- **`RemoteProblem` stays** as the documented gateway seam, although nothing
  in the kit raises it.
- **FastAPI's `ProblemDetail` component** still comes from the pydantic
  mirror, and Django's from `PROBLEM_DETAIL_SCHEMA`; R4 makes the web model
  the single source.

#### Handoff notes (as used for Part B; kept for the record)

- **Order.** B11 → B1 → B5 → B7 → B4 → B3 → B2 → B6 → B8 → B9 → B10 → B12. Each item
  lands with its tests, conformance cases, docs and a green validation run
  before the next one starts.
- **Rules that bite:**
  - root `CLAUDE.md` (docstrings describe the contract only; comments explain
    a non-obvious *why*);
  - no compatibility re-exports;
  - new public `web` symbols go into `rn_forge/web/__init__.py`, except
    extra-gated modules;
  - tests mirror the source layout, with no `tests/__init__.py`;
  - `pyright` strict on `src/`;
  - `.importlinter`: `web` imports no framework.
- **New dependencies** (the `security` and `cors` extras) need the owner's
  approval before they are added. Do the library check, then ask.
- **Validation** is this plan's validation block, plus the per-package strict
  docs build for each package touched. The combined root `mkdocs build
  --strict` fails today on links in `docs/plans/01-extraction-from-cims.md`
  and `fastapi-app-layer-plan.md`; that is not caused by this work.
- **When done,** mark each B item done here with the date and any deviation,
  and update the status board.

### R3: correlation through W3C Trace Context — implemented 2026-09-23

**Implemented 2026-09-23, all of web → fastapi → django → docs, ahead of R4.**
The plan's own order note below (§"R3 order and validation") says to land R3
after R4 because both edit `problem.py` and landing R4 first keeps a failing
conformance run pointing at one change at a time; R4 has not landed yet, so
this run could not benefit from that ordering. R3 does not depend on R4's
pydantic models for correctness — `ProblemDetail` is still the
`DataclassMixin` dataclass — so the risk that ordering guards against did not
apply, and every validation in "R3 order and validation" below passed
(`uv run pytest`, `ruff check`, `ruff format --check`, `pyright`,
`lint-imports`, all green at the repo root; all three drivers pass the four
`tracing.*` cases with no skips). That list did not include
`mkdocs build --strict`, which the block also requires and which failed in
`rn-forge-web` (a stale `api/context.md`) until R10.1 fixed it on 2026-09-23.
Two deviations from the acceptance checks as literally written:

- `rg -i "correlation" packages --type py` is not fully empty:
  `rn_forge.web.conformance.cases` and its regression test
  (`tracing.house-header-is-not-echoed`) still spell `X-Correlation-ID`
  literally, because proving the header is no longer read or echoed requires
  naming it somewhere. `rg "X-Correlation-ID|correlation_id"` also still
  matches `rn-forge-commons`' unrelated `enable_otel_correlation` logging
  option (`rn_forge.commons.logging.logger`), which R3 elsewhere explicitly
  says needs no change.
- `uv sync --extra drf` was verified with `uv pip install ".[drf]"` into a
  scratch venv rather than `uv sync`, to avoid touching the workspace lock for
  a one-off check; it confirms `opentelemetry-instrumentation-django` is not
  pulled in.

**Decision (owner, 2026-09-22): option a.** The options as they were weighed:

| Option | Wire | Cost |
| --- | --- | --- |
| **a. W3C Trace Context through OpenTelemetry instrumentation** (chosen) | `traceparent` in, `traceresponse` out; the problem body carries the trace id | OTel instrumentation on both stacks; the log processor reads the trace id |
| b. Keep `X-Correlation-ID`, adopting `asgi-correlation-id` in `rn-forge-fastapi` | unchanged | Rejected: keeps a house header that no standard names |
| c. Status quo | unchanged | Rejected, for the same reason |

Choosing a also approves the dependencies listed under "R3 dependencies" below.
`X-Correlation-ID` is removed outright, with no alias and no transition
period: nothing is released (README).

The earlier note that web-api-reuse Phase 5's validator "stays whichever
option is chosen" is withdrawn for option a. The W3C propagator already
validates the inbound value: a malformed `traceparent` is ignored and a new
trace starts (probed below). The hand-written validator goes, and Phase 5 is
marked withdrawn in the same change.

#### R3 standards

- **W3C Trace Context** (Recommendation). The request headers are
  `traceparent` and `tracestate`. A malformed `traceparent` is discarded, and
  the server starts a new trace.
- **W3C Trace Context Level 2** (Candidate Recommendation Draft). The response
  header is `traceresponse: 00-<trace-id>-<span-id>-<flags>`. OpenTelemetry
  Python implements it as `TraceResponsePropagator`, which its own source marks
  "experimental".
- **OpenTelemetry library guidance.** A library depends on
  `opentelemetry-api` only, which is a no-op until the application configures
  the SDK. The application, or the `opentelemetry-instrument` launcher, owns
  the `TracerProvider` and the exporter. The kit never configures an exporter,
  because exporters are host-specific (B12).
- **OpenTelemetry log data model.** A log record's trace fields are `trace_id`
  (32 lowercase hex characters) and `span_id` (16).

#### R3 probe, 2026-09-22

The probe used `opentelemetry-api`/`-sdk` 1.44.0,
`opentelemetry-instrumentation-fastapi` and `-django` 0.65b0, and FastAPI's
`TestClient`.

| Check | Result |
| --- | --- |
| No SDK configured (API only) | The handler sees no valid span, so the trace id is `None` and no `traceresponse` is sent |
| SDK plus `TraceResponsePropagator`, inbound `traceparent` | The handler's trace id equals the inbound one, and `traceresponse` carries it with a new span id |
| Malformed `traceparent` (`garbage`) | 200, with a new trace id in the handler and in `traceresponse` |
| No `traceparent` | A new trace id |
| Inside a FastAPI exception handler, for a domain exception (409) and for an unhandled exception (500 handler) | The trace id is still the request's. The span wraps `ServerErrorMiddleware` |
| `FastAPIInstrumentor.instrument_app` called twice, for example by `FastApiApp` and by `opentelemetry-instrument` | The second call logs a warning and does nothing |
| CORS | `CORSMiddleware`'s `Access-Control-Expose-Headers` line is kept. The propagator **adds** a second line, `traceresponse`, so a client that joins the two lines reads `<CORS list>, traceresponse`. Django's setter (`DictHeaderSetter`) appends to the existing value the same way |

#### R3 wire contract

This replaces `api-conventions.md` §1, "Correlation", which becomes "Tracing".

| Rule | Detail | Source |
| --- | --- | --- |
| Inbound | `traceparent` and `tracestate` continue the caller's trace. A malformed value starts a new trace; it is never an error | W3C Trace Context |
| Outbound | Every response carries `traceresponse` when a `TracerProvider` is configured | Trace Context Level 2 |
| Problem body (member renamed `traceId` by R10.5) | `trace_id` extension member: the current trace id, 32 lowercase hex characters, or `null` when no span is recording. It replaces `correlation_id`. It stays snake_case, the documented exception in §2, because it matches the log field | RFC 9457 §3.2; OTel log data model |
| Access log (deleted by R10.2) | The `request.complete` event carries `trace_id` and `span_id` instead of `correlation_id` | OTel log data model |
| `X-Correlation-ID` | Not read and not sent | none; removed |
| CORS | `EXPOSED_HEADERS` drops the correlation header and does **not** list `traceresponse`, because the propagator exposes it itself (probe) | Fetch standard |

#### R3 dependencies (approved with the decision)

| Package | Change |
| --- | --- |
| `rn-forge-web` | **Base** dependency `opentelemetry-api>=1.44`, following OTel's library guidance. Rewrite the `pyproject.toml` comment that says there is no third-party dependency beyond commons, and the README's "Dependencies and why" section. Dev group: `opentelemetry-sdk>=1.44` and `opentelemetry-instrumentation-asgi>=0.65b0`, for the ASGI example driver |
| `rn-forge-fastapi` | **Base** dependency `opentelemetry-instrumentation-fastapi>=0.65b0`, because `FastApiApp` instruments itself by default. It brings `opentelemetry-instrumentation`, which holds `TraceResponsePropagator`. Dev group: `opentelemetry-sdk>=1.44` |
| `rn-forge-django` | New `otel` extra: `opentelemetry-instrumentation-django>=0.65b0`. Dev group: `opentelemetry-sdk>=1.44`, and add `otel` to the extras the dev group self-references |

`opentelemetry-sdk` is never a runtime dependency of any package.

#### R3 in `rn-forge-web`

1. **Rename `rn_forge/web/context.py` to `rn_forge/web/tracing.py`** and
   `tests/test_context.py` to `tests/test_tracing.py`.
2. **Delete from it:** `DEFAULT_CORRELATION_HEADER`, `CORRELATION_ID_KEY`,
   `MAX_CORRELATION_ID_LENGTH`, `_CORRELATION_ID_PATTERN`,
   `is_valid_correlation_id`, `correlation_id_var`, `new_correlation_id`,
   `resolve_correlation_id`, `set_correlation_id`, `get_correlation_id`,
   `require_correlation_id`, `bind_correlation_id` and
   `correlation_log_processor`.
3. **Add:**
   - `TRACE_ID_KEY: Final = "trace_id"` and `SPAN_ID_KEY: Final = "span_id"`;
   - `current_trace_id() -> str | None`: `ctx =
     trace.get_current_span().get_span_context()`, then `format(ctx.trace_id,
     "032x") if ctx.is_valid else None`;
   - `current_span_id() -> str | None`: the same, with `"016x"` over
     `ctx.span_id`;
   - `trace_log_processor(logger, method_name, event_dict)`: a structlog
     processor with the same signature and contract as the deleted
     `correlation_log_processor`. It sets `trace_id` and `span_id` when a span
     is valid, and leaves the event untouched otherwise.
4. **Keep, and change:**
   - `EXPOSED_HEADERS` loses `DEFAULT_CORRELATION_HEADER`. Its docstring says
     that `traceresponse` is exposed by the OTel propagator, not by this list;
   - `request_log_fields(*, method, path, status, duration_ms)` drops its
     `correlation_id` argument, and adds `trace_id` and `span_id` from
     `current_trace_id()` and `current_span_id()`.
5. **`asgi.py`.**
   - Replace `CorrelationIdMiddleware` with
     `AccessLogMiddleware(app, *, log: Log)`. It only times the request and
     emits `request.complete` with `request_log_fields`. There is no header
     handling, and `log` is required: a caller with no sink does not install
     it;
   - `_send_413` writes `TRACE_ID_KEY: current_trace_id()` in place of the
     correlation member. Update the module docstring.
6. **`problem.py`.**
   - `render_problem` drops `correlation_header=`. The extension becomes
     `{TRACE_ID_KEY: current_trace_id(), **(extensions or {})}`;
   - update its docstring bullets.
7. **Facade.** In `rn_forge/web/__init__.py`, remove the deleted names and
   add `TRACE_ID_KEY`, `SPAN_ID_KEY`, `current_trace_id`, `current_span_id`,
   `trace_log_processor` and `AccessLogMiddleware`. Import them from
   `rn_forge.web.tracing`.
8. **Conformance** (`rn_forge.web.conformance`).
   - `types.py`:
     - in `ConformanceArea`, rename `"correlation"` to `"tracing"`;
     - in `VARIABLE_MEMBERS`, replace `"correlation_id"` with `"trace_id"`,
       and update its docstring;
     - add `expect_header_patterns: Mapping[str, str]` to `ConformanceCase`.
       Each value is a regular expression matched with `re.fullmatch` against
       the header value; header names are case-insensitive, as for
       `expect_headers`. Update every driver's comparison helper, including
       the one the web tests use for `asgi_app.py`, to apply it.
   - `cases.py`: replace the two `correlation.*` cases with these, all
     against the existing `/conformance/echo` or problem-raising fixture
     routes. `TP` is
     `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`.

     | id | Request | Expect |
     | --- | --- | --- |
     | `tracing.inbound-traceparent-continues-the-trace` | `GET /conformance/echo`, `traceparent: TP` | 200. `traceresponse` matches `00-4bf92f3577b34da6a3ce929d0e0e4736-[0-9a-f]{16}-[0-9a-f]{2}` |
     | `tracing.malformed-traceparent-starts-a-new-trace` | the same, with `traceparent: garbage` | 200. `traceresponse` matches `00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}` |
     | `tracing.problem-body-carries-the-trace-id` | a problem-raising route, `traceparent: TP` | The problem status. The body is compared after redaction as usual, and `traceresponse` matches the first pattern |
     | `tracing.correlation-header-is-not-echoed` | `GET /conformance/echo`, `X-Correlation-ID: abc123` | 200. `X-Correlation-ID` in `expect_absent_headers` |

   - The CORS case's expected `Access-Control-Expose-Headers` becomes
     `", ".join((*EXPOSED_HEADERS, "traceresponse"))`.
   - The `expect_body` of `tracing.problem-body-carries-the-trace-id` lists
     `"trace_id": REDACTED`. That proves the member is present, but not that
     it equals the inbound id, because `redact` hides the value. The unit
     tests in item 10 cover equality.
9. **`docs/adoption/examples/asgi_app.py`.** Wrap the app in
   `opentelemetry.instrumentation.asgi.OpenTelemetryMiddleware`, outermost,
   and replace `CorrelationIdMiddleware` with `AccessLogMiddleware` only where
   the example logs. The module docstring's "no framework" claim still holds,
   because OTel is not a framework. It says so in one line.
10. **Tests.**
    - `test_tracing.py`: `current_trace_id` and `current_span_id` return
      `None` with no span. Inside `tracer.start_as_current_span` under an SDK
      `TracerProvider` they return the span's ids. `trace_log_processor` sets
      both fields or leaves the event untouched. `request_log_fields` includes
      the ids.
    - `test_problem.py`: `render_problem` inside a span puts that span's
      trace id in `trace_id`, and outside one puts `null`.
    - `test_asgi.py`: `AccessLogMiddleware` emits one `request.complete` with
      the new fields.
    - The SDK is configured once per test session in a `conftest.py` fixture
      (`autouse=True`, `scope="session"`) that calls
      `trace.set_tracer_provider(TracerProvider())` and
      `set_global_response_propagator(TraceResponsePropagator())`.
      `set_tracer_provider` can only be called once per process; a second
      call logs a warning and is ignored. Under a root-level `uv run pytest`,
      three packages' conftests call it, and the first call wins, which is
      harmless because they are identical. Do not rely on replacing the
      provider between tests.

#### R3 in `rn-forge-fastapi`

1. `AppConfig`: remove `correlation_header` and add `tracing: bool = True`.
   Update the class docstring's field list.
2. `FastApiApp.__init__`, when `config.tracing` is true:
   - call `FastAPIInstrumentor.instrument_app(self)` after the kit's own
     middleware is added. The instrumentor wraps the whole middleware stack
     and is therefore outermost regardless of order (probed);
   - then, if `get_global_response_propagator()` is `None`, call
     `set_global_response_propagator(TraceResponsePropagator())`. The
     application's own choice wins. Add a one-line `#` comment: it is
     process-global state, set only when nobody else set it.
3. Replace the `CorrelationIdMiddleware` installation with
   `AccessLogMiddleware`, installed only when `AppConfig.log` is set.
4. `problem.py`: stop passing `correlation_header=` to `render_problem`.
5. Tests: `test_app.py` covers `tracing=False` (no `traceresponse`, even with
   an SDK configured) and the default (`traceresponse` present). A test also
   covers an application that installed its own response propagator
   beforehand, which `FastApiApp` must leave alone. Add the session fixture
   from web item 10 to this package's `conftest.py`.
6. Docs: in `docs/guides/wiring.md`, replace the correlation section with
   "Tracing". It shows the application configuring the SDK
   (`TracerProvider`, a `BatchSpanProcessor` and an exporter of its choice),
   or running under `opentelemetry-instrument`, and says that `FastApiApp`
   does not double-instrument. Update the README's feature list.

#### R3 in `rn-forge-django`

1. `middleware.py`: replace `CorrelationIdMiddleware` with
   `AccessLogMiddleware`. Keep the `log` hook and the `AppLogger` default.
   Drop the header, the `header` class attribute and the
   `request.correlation_id` attribute. `grep -rn "correlation_id" packages/rn-forge-django`
   finds every reader of the attribute, and each one moves to
   `current_trace_id()`.
2. New module `rn_forge/django/tracing.py` (the `otel` extra, not in any
   facade) with `instrument() -> None`. It calls
   `DjangoInstrumentor().instrument()`, then installs `TraceResponsePropagator`
   under the same "only when unset" rule as FastAPI. The application calls it
   once, from `wsgi.py`/`asgi.py` and `manage.py`, before Django loads. That
   is the native pattern: the instrumentor inserts its middleware into
   `settings.MIDDLEWARE` itself, at position 0, so it wraps the kit's
   middleware and the DRF exception handler.
3. `drf/exceptions.py`: stop passing `correlation_header=`.
4. Tests: `tests/test_tracing.py` checks that `instrument()` is idempotent
   and leaves an existing response propagator alone. Add the session fixture.
   `test_conformance.py` calls `instrument()` once, at module import or in a
   session fixture, before the test client is built.
5. Docs: `docs/guides/quickstart.md` drops `CorrelationIdMiddleware` from
   `MIDDLEWARE`, adds `AccessLogMiddleware`, and shows the `instrument()`
   call. The django README lists the `otel` extra.

#### R3 elsewhere

- `api-conventions.md`:
  - §1 is rewritten from the wire-contract table above;
  - the extension-naming paragraph (currently "`correlation_id` as a problem
    extension…") names `trace_id`;
  - the CORS section and the access-log section (B9) follow the changes
    above.
- `deployment.md`, "Logs and traces": configure the OTel SDK with the host's
  exporter, or OTLP to a collector. Name `azure-monitor-opentelemetry` and
  `opentelemetry-exporter-gcp-trace` as examples, not dependencies.
- `rn-forge-commons` needs no change. Its logger already injects
  `otelTraceID`/`otelSpanID` through its `otel` extra
  (`enable_otel_correlation`); the structlog path uses
  `trace_log_processor`.
- `web-api-reuse-plan.md` Phase 5: mark it withdrawn by R3, with the reason
  above.

#### R3 order and validation

Implement R3 **after R4**. Both edit `problem.py`; R4 is wire-neutral and R3
is not, so a failing conformance run then points at one change. Land it in
this order: web (with the ASGI driver) → fastapi → django → docs. Each step
runs the plan's validation block.

Acceptance, in addition to the block:

- `rg -i "correlation" packages --type py` finds nothing;
- `rg "X-Correlation-ID|correlation_id" packages` finds nothing;
- all three drivers pass the four `tracing.*` cases with no skips;
- `uv sync --extra drf` in `rn-forge-django` does not install
  `opentelemetry-instrumentation-django`.

### R4: one model per stack — decided 2026-09-22, implemented 2026-09-23

**Sequencing (owner, 2026-09-23, R10):** R5's four evaluations run first; R4
then covers only the types no library takes, in the shape below.

**Decision (owner, 2026-09-22): option b.** `rn-forge-web` defines
`ProblemDetail`, `Page[T]`, `CheckResult` and `HealthReport` as pydantic
models. FastAPI uses them directly. Django uses them for its OpenAPI
component and its health bodies. Option a, framework-free builders plus
schema-only pydantic models on FastAPI, was the fallback if the verification
failed, and is not needed.

This change is **wire-neutral**. No conformance case changes, and any
conformance diff is a bug.

#### R4 verification, 2026-09-22 (drf-spectacular 0.30.0, pydantic 2.13.5)

| Check | Result |
| --- | --- |
| drf-spectacular's `contrib.pydantic.PydanticExtension` with a concrete model in `@extend_schema(responses=…)` | Works. The component is pydantic's own serialization-mode JSON schema, camelCase aliases included, named after the class |
| A generic `Page[OrderOut]` in `@extend_schema` | Emits the component name `Page[OrderOut]`, which drf-spectacular warns is illegal. **Not needed:** DRF describes a page through the paginator's native `get_paginated_response_schema`, which the kit's paginator already implements. On Django, `Page` is used to build bodies only, never passed to `@extend_schema` |
| `ProblemDetail` flattening extensions through a wrap `@model_serializer` | **Rejected.** The serialization schema collapses to `{"additionalProperties": true}` |
| `ProblemDetail` with `extra="allow"` and a `mode="before"` validator that merges an `extensions=` argument | Works. The schema lists the five core members as required, with `additionalProperties: true`. Core members win a collision. Extras keep their spelling (`trace_id` is not camelized). The body round-trips through `model_validate` |
| `HealthReport.http_status` as `Field(exclude=True)` | Absent from the body and the schema |

#### R4 target shape (`rn-forge-web`)

1. **Dependency.** The base dependencies gain
   `rn-forge-commons[pydantic]` (commons Part G's extra), in place of the
   bare commons requirement, so the pydantic floor stays in one place.
   `rn-forge-django` then installs pydantic transitively; that is the
   accepted cost of b. `.importlinter` needs no change, because pydantic is
   not a framework.
2. **`WireModel` moves** from `rn_forge.fastapi.schemas` to a new
   `rn_forge/web/models.py`, with its `model_config` unchanged (it is **not**
   frozen, because applications subclass it for their own models). Export it
   from the web facade.
3. **The four types become `WireModel` subclasses in their current modules**,
   replacing the dataclasses and their `DataclassMixin`/`LenientDataclassMixin`
   bases. Each keeps `as_body()` with its current contract, implemented as
   `self.model_dump()`: python mode, with `serialize_by_alias` from the
   config. Every existing caller keeps working unchanged. Each also sets
   `model_config = ConfigDict(frozen=True)`, which pydantic merges with
   `WireModel`'s config.
   - **`ProblemDetail`** (`problem.py`): `extra="allow"`, with fields `type`,
     `title`, `status`, `detail` and `instance`.
     - A `@model_validator(mode="before")` pops an `extensions` mapping from
       dict input and merges it underneath the core members, so core members
       win a collision. This keeps the `ProblemDetail(..., extensions={...})`
       call sites working.
     - `extensions` becomes a read-only `@property` returning
       `dict(self.model_extra or {})`.
     - Delete the hand-written `as_body` flattening and `_CORE_MEMBERS` if
       nothing else uses it.
   - **`Page[T]`** (`pagination.py`): `items: list[T]`, `next_page_token: str
     | None`, `total_size: int | None = Field(default=None,
     exclude_if=<is None>)`. This is exactly the mirror in today's
     `rn_forge.fastapi.schemas`; move it rather than rewrite it. `as_body()`
     must still omit an absent `totalSize` and always include
     `nextPageToken`.
   - **`CheckResult`** (`health.py`): `status: CheckStatus`, `reason`,
     `remediation`, and `details: dict[str, Any]`.
   - **`HealthReport`** (`health.py`): `status`, `checks: dict[str,
     CheckResult]` and `http_status: int = Field(exclude=True)`. `as_body()`
     keeps returning `status` and `checks` only.
4. **`PROBLEM_DETAIL_SCHEMA` is deleted** from `rn_forge.web.openapi` and the
   facade. Its one consumer, Django's `SPECTACULAR_SETTINGS`, uses
   `ProblemDetail.model_json_schema(mode="serialization")`, the same call
   FastAPI's repair makes. The two documents now share one component source.
   Their text still differs elsewhere, which is not a goal ("What identical
   across stacks means").
5. **Callers of the dataclass API.** `from_dict`, `to_dict` and
   `dataclasses.replace` on these four types become `model_validate`,
   `model_dump` and `model_copy(update=…)`. On 2026-09-22 no source module
   used them; `rg "from_dict|to_dict|replace\(" packages/*/tests` finds the
   tests that do.

#### R4 in `rn-forge-fastapi`

- Delete `rn_forge/fastapi/schemas.py` and `tests/test_schemas.py`. Move any
  assertion in it that is still meaningful, such as `Page` omitting
  `totalSize` or the `ProblemDetail` extension flattening, into web's
  `test_pagination.py`, `test_problem.py` or `test_health.py`.
- `openapi.py` and `health.py` import `ProblemDetail` and `HealthReport` from
  `rn_forge.web`.
- Facade: remove `CheckResult`, `HealthReport`, `Page`, `ProblemDetail` and
  `WireModel` from `rn_forge.fastapi`, with no re-exports. Update the tests,
  the docs and the web package's `examples/fastapi_app.py`, which import them
  from `rn_forge.fastapi`, to import from `rn_forge.web`.
- README and `docs/guides/wiring.md`: `WireModel` is now `rn_forge.web`'s.

#### R4 in `rn-forge-django`

- Delete `drf/serializers/wire.py` (`ProblemDetailSerializer`,
  `PageSerializer`, `CheckResultSerializer` and `HealthReportSerializer`), its
  exports in `drf/serializers/__init__.py`, and
  `tests/drf/serializers/test_wire.py`.
- `drf/openapi.py`: `APPEND_COMPONENTS` takes the `ProblemDetail` schema from
  the model (target-shape item 4).
- `tests/drf/test_openapi.py` uses `HealthReportSerializer` today. Switch it
  to `@extend_schema(responses=HealthReport)`, with the web pydantic model,
  and assert that the component exists with camelCase properties. This is the
  standing regression test for the verification above.
- `drf/pagination.py` keeps building `Page[Any](...)` and calling
  `as_body()`, and keeps its hand-written `get_paginated_response_schema`.

#### R4 docs

- `rn-forge-web` README: "Dependencies and why" gains pydantic, and R3 adds
  `opentelemetry-api` there too. The module table names `models.py`.
- In `api-conventions.md`, no rule changes. If a paragraph says the wire
  types are modelled per stack, correct it.
- This plan's "Review findings" bullet "Each shared wire type is modelled
  three times" gets a closing line naming R4.

#### R4 validation

The plan's block, plus:

- `rg "from_wire|to_wire|PROBLEM_DETAIL_SCHEMA|rn_forge.fastapi.schemas|ProblemDetailSerializer|PageSerializer|CheckResultSerializer|HealthReportSerializer" packages`
  finds nothing;
- all three conformance drivers pass with **no case edited**;
- both stacks' "every operation declares the problem+json responses" tests
  pass unchanged;
- `pyright` strict passes over the four models, including `Page[T]`'s
  PEP 695 generic.

### R5: re-run the withdrawn library evaluations — done 2026-09-23, all four exempt (a fifth, `fastapi-import-export`, added by R9)

Re-run every evaluation rejected on wire-ownership grounds. A library is
adopted when it implements the standard, can be configured to
`api-conventions.md`, and is maintained. Otherwise the exemption is written into
the module docstring, as principle 1 requires.

- FastAPI: `fastapi-problem` and other RFC 9457 handlers on PyPI;
  `fastapi-pagination` (cursor mode, with AIP-158 names). `asgi-correlation-id`
  is dropped from the list: R3 chose W3C Trace Context, and that header is
  gone.
- Django: `drf-standardized-errors` (only if configurable to RFC 9457);
  `django-health-check`.

**Reordered by R10 (owner, 2026-09-23):** the four evaluations run after R10
and **before** R4, each as a probe with a written verdict here, judged by the
criteria above plus rule 6. A candidate must fit two things: `ProblemDetail` and `Page` as `rn-forge-web`
pydantic models (R4), and the `traceId` problem extension (R3, renamed by R10.5).

#### R5 verdicts (probed 2026-09-23, throwaway venvs, repo untouched)

Every candidate is **exempt**: none can be configured to `api-conventions.md`
without replacing most of its own machinery, so adopting one would add a
dependency and delete no kit code (rule 6).

| Candidate | Verdict | Evidence |
| --- | --- | --- |
| `fastapi-problem` 0.12.1 (released 2026-02-10; sits on `starlette-problem` and `rfc9457`) | **Exempt** | Emits no `instance`. The default 500 `detail` was `str(exc)` (avoidable only through `unhandled_wrappers`). `type` and `title` are the library's own, not `about:blank` and the status phrase. 422 `errors` are raw pydantic dicts that echo the input, not `{pointer, detail}`. No exception-to-status registry, no `Retry-After` protocol. `traceId` works only through a post hook that rebuilds the response. Its `Problem` is an `Exception` subclass, not a pydantic model, so it cannot be R4's `ProblemDetail`. Other candidates (`fastapi-problem-details` 0.1.5, `fastapi-rfc9457` 0.2.1, `fastapi-faults` 0.1.0) were judged on release metadata only, not probed |
| `fastapi-pagination` 0.16.0 (released 2026-09-16) | **Exempt** | In-memory `paginate()` raises `ValueError` for cursor params; cursor works only through a DB extension or a hand-built `CursorPage`. Stock `CursorPage`, camelCased, returns `{items, total, currentPage, currentPageBackwards, previousPage, nextPage}`: no `nextPageToken`, `total` required (the kit's `totalSize` is off by default). A custom `AbstractPage` and params class reach `{items, nextPageToken}`, but that discards the library's model, and clamping stays the kit's. Stock `CursorParams` uses `le=100` (a 422, which the conventions forbid). `pageToken=%%%` returned 200 with the first page, not 400; its 400 for hard base64 errors is not problem+json. Its SQLAlchemy keyset extension is not evaluated here; revisit under R8 item 5 |
| `drf-standardized-errors` 0.16.0 (released 2026-04-29; runs on the locked Django 6.0.7 and DRF 3.17.1) | **Exempt** | No RFC 9457: `application/json`, `{type, errors[{code, detail, attr}]}`, `type` one of three fixed words, no `title`, `status` or `instance`. No `traceId`, members not camelCase, `errors` not RFC 6901 pointers, `RequestDataTooBig` gives 500 not 413. Meeting the conventions needs a custom `ExceptionHandler`, `ErrorResponseSerializer` and renderer, which replaces the library's output. Its 5xx detail is generic, and status codes follow DRF |
| `django-health-check` 4.6.1 (released 2026-09-18; Django 5.2 to 6.1) | **Exempt** | Follows no published contract (`OK` or an error string, not `pass`/`warn`/`fail`). A failing check returns **500**, hard-coded, not 503; a warning also returns 500, so "warn never changes status" fails. No required versus optional, so `health.optional-failure-is-200-degraded` cannot be met. Flat body keyed by `repr(check)`, no `status`. No timeout (a 5 s check took 5 s; the kit's default is 2 s). No liveness endpoint. Default checks include database, cache, DNS, mail and storage. HTML by default. The shared web health model must stay for FastAPI regardless |
| `fastapi-import-export` 0.3.0 (released 2026-02-26; probed in R9 step 0, 2026-09-23) | **Exempt** | A two-phase service: validate returns an `import_id`, commit reads the validated rows back from parquet on disk under an optional Redis lock, which is a different wire from `validateOnly` on one request. Persistence is a caller-supplied `persist_fn(db, dataframe, allow_overwrite=...)`, so it offers no upsert and deletes none of R9's. Row errors are `{row_number, field, type}` with the library's own type codes, `ImportExportError` carries `400`/`409`/`413`/`415`, and none of it is RFC 9457 or the kit's `RowError`. Data is polars DataFrames, so tablib's `Dataset` would stop being the in-memory contract. The base install adds polars, fastexcel, xlsxwriter and uuid6. Single maintainer, four 0.x releases |

**Consequences.**

- R4 proceeds as decided: `ProblemDetail`, `Page`, `CheckResult` and
  `HealthReport` become pydantic models in `rn-forge-web`. Nothing in R5 changes
  its scope.
- No dependency was added and no kit code changed.
- The exemption text is written into the module docstrings (2026-09-23), as
  principle 1 requires: `rn_forge.web.problem` (fastapi-problem),
  `rn_forge.web.pagination` (fastapi-pagination), the Django DRF problem
  handler (drf-standardized-errors) and `rn_forge.django.views`
  (django-health-check). Root `CLAUDE.md` keeps design justification out of
  docstrings, so each is one sentence naming the library, the date and the
  blocking fact, with the detail left here.
- **Revisit triggers.** `fastapi-problem`: when it emits `instance`, defaults to
  a generic 5xx `detail` and offers a status registry. `fastapi-pagination`:
  when its page model is configurable to `{items, nextPageToken}` without
  `total`. `drf-standardized-errors`: when it ships an RFC 9457 mode.
  `django-health-check`: when failure status and JSON body are configurable.
  `fastapi-import-export`: when it offers a single-request validate-only mode
  and row errors that map to RFC 9457.

### R6: `rn-forge-django` scope, **backlog (owner, 2026-09-23)**

The package split, and the whole auth feature, are revisited later; nothing
here is scheduled.

At minimum, stop the `drf` facade from importing the transfer views, so the
`drf`, `jwt`, `saml`, `openapi` and `oidc` extras stop requiring `excel`.
Whether transfer, SAML, Celery, fixtures and messaging move to their own
package is the owner's call.

**Transfer is settled by R7 (2026-09-22):** the views are replaced, not
moved. What remains of R6 is SAML, Celery, fixtures and messaging.

### R7: tabular transfer and bulk operations, adopt the libraries

**Status:** ready to implement, 2026-09-22. `tablib` and
`django-import-export` **approved by the owner** on 2026-09-22. The DRF router
question is answered by a probe (see "AIP-136 routing on DRF" below). Independent of R3–R6.
Ordered after R2.5 Part B, because B's 413 and conditional-GET handling apply to
the export path.

#### Why

Full CRUD plus spreadsheet upload and download is a baseline requirement for a
line-of-business API, not a pykit specialty. `drf/views/` (about 2,200 lines, of
which `transfer.py` is 1,300) re-implements what two maintained libraries do.
It also sends four house wire shapes: `POST …/export` with a `format` body
field, `400 {created, updated, errors:[{row, message}]}` for a failed import,
`{"message"}` bodies, and bulk-create row errors joined with `"\n"` into a 403.

The code was carved out of `accelerate-django`, which powers `ew-loop-api`.
That application is the reference consumer, and its use sets the requirements.

#### Requirements, from `ew-loop-api`

| Requirement | `ew-loop-api` today | Viewsets |
| --- | --- | --- |
| **Export** the filtered collection as xlsx or CSV | Headers differ from field names; foreign-key traversal (`store.sap`); computed columns (employee full name); enum code to display name; per-column date and currency number formats | 15 |
| **Upsert import** from xlsx | Headers come from another system's export (`FNAME`, `JOB`) and differ from the export headers; natural key (`employeeId`); foreign key resolved by code (`Role` by `code`); value normalization (`.title()`, `.lower()`); only changed fields updated; audit fields; dry run ("simulation mode"); per-row errors; counts of inserts, updates and errors | 4 (Employee, Store, Plan, Accessory) |
| **Import template**, empty or prefilled from a filtered queryset | Separate column set from the export | 4 |
| **Bulk create and delete** as JSON | Per-object authorization (region, market and store scope) checked for every item | all CRUD viewsets |
| **Bespoke report** workbooks | Built by a service, returned as a download | 1 (PerfTracker) |

Not required by the consumer, but in pykit's current code: snapshot import with
delete-missing, and the DB-shaped bulk load. They are dropped unless a consumer
asks (see "Retired" below).

#### The libraries, evaluated 2026-09-22

| Library | Latest | Verdict |
| --- | --- | --- |
| `tablib` (Jazzband) | 3.10.0, 2026-07-31 | **Adopt** as the one format codec on both stacks: csv, tsv, json, xlsx, ods, yaml. Framework-free. `tablib[xlsx]` needs only openpyxl, not pandas |
| `django-import-export` | 4.4.1, 2026-05-05 | **Adopt** for Django. Its `Resource` covers every import and export row in the table above: `Field(attribute="store__sap", column_name="Store")`, `ForeignKeyWidget(Role, field="code")`, `import_id_fields`, `skip_unchanged` with explicit `fields`, `dehydrate_<field>`, `before_import_row`, `use_bulk` with `batch_size`, `import_data(dry_run=…)` and a `Result` with per-row errors and totals. `Resource` is usable outside the admin |
| `drf-excel` | 2.6.0, 2026-08-06 | Not adopted. It renders serializer output, so it covers export only, and the import column set still needs a second definition. One `Resource` per direction covers export, import and template |
| `djangorestframework-csv` | 3.0.2, 2023-12 | Not adopted. CSV only, unmaintained, and tablib covers it |
| `djangorestframework-bulk` | 0.2.1, 2015 | Not adopted. Unmaintained. DRF's own `many=True` `ListSerializer` is the native mechanism for bulk create |
| `fastapi-import-export` | 0.3.0, 2026-02 | Not adopted, re-evaluate in R5. Single maintainer, four 0.x releases, and the base install pulls in polars, fastexcel, xlsxwriter and uuid6 |

There is no FastAPI equivalent of `django-import-export` that passes the check.
On FastAPI the native mechanisms cover most of it: pydantic for row validation
and column aliases, `UploadFile`, `StreamingResponse`, and the ORM's own upsert
(`INSERT … ON CONFLICT DO UPDATE` in SQLAlchemy's PostgreSQL and SQLite
dialects). pykit adds only the glue shared by both stacks.

#### Wire contract, both stacks

Added to `api-conventions.md` as a new section, each rule naming its source.

| Operation | Wire | Source |
| --- | --- | --- |
| Export | `GET /orders` with `Accept: text/csv` or `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`. Same filters as the JSON list. Not paginated; a result above the configured cap is a problem response naming the cap. `?format=csv\|xlsx` is the fallback for plain links (DRF's native `URL_FORMAT_OVERRIDE`). `Content-Disposition: attachment` with `filename*` | RFC 9110 §12 (proactive negotiation), RFC 6266, RFC 8187 |
| Import | `POST /orders:import`, `multipart/form-data` with a `file` part, `?validateOnly=true`. `200` with `{created, updated, skipped, validateOnly}`. Any row error: `422` problem+json with `errors[].pointer = "/rows/12/Quantity"`, and nothing persisted | AIP-136 custom method (§9 already requires the colon form); AIP-163 for `validateOnly`; RFC 9457 §3 and R2.3 for `errors[]` |
| Import template | `GET /orders:importTemplate`, negotiated like export; `?prefill=true` adds the current filtered rows | AIP-136 |
| Bulk create | `POST /orders:batchCreate`, body `{"requests": [...]}`, all or nothing. `200 {"orders": [...]}`. A per-item authorization or validation failure is one 403 or 422 problem, with `errors[].pointer = "/requests/3/…"` | AIP-233, RFC 9457 |
| Bulk delete | `POST /orders:batchDelete`, body `{"ids": [...]}`, all or nothing, `204` | AIP-235 |
| Large files | Not built. `api-conventions.md` names the pattern for when a consumer needs it: `POST /imports` → `202` + `Location`, then poll the operation (AIP-151), with an `Idempotency-Key` | AIP-151, `draft-ietf-httpapi-idempotency-key-header` |

All or nothing is the default because it is what AIP-233 and
`django-import-export` (`use_transactions`, `rollback_on_validation_errors`)
default to. `ew-loop-api` currently commits the valid rows and reports the
rest. On Django a viewset can keep that behaviour with one attribute
(`import_rollback_on_validation_errors = False`), and the response is then
`200` with the errors listed. That is the only sanctioned variant.

#### What pykit ships

**`rn-forge-commons`**, `excel` extra becomes `openpyxl` + `tablib[xlsx]`,
without pandas:

- `write_xlsx(dataset, column_formats=…)` in `rn_forge.commons.data.excel`.
  tablib's xlsx writer has no per-column number formats, and `ew-loop-api`
  needs dates and currency. This is the one recorded exemption: about 40 lines
  over openpyxl's write-only mode, taking a `tablib.Dataset`.

**`rn-forge-web`**, `rn_forge.web.transfer`, framework-free and without tablib:

- `TABULAR_FORMATS`: media type ↔ extension ↔ tablib format name.
- `negotiate_tabular_format(accept, format_param, allowed)`.
- `content_disposition(filename)`, per RFC 6266 and RFC 8187.
- `import_report_body(...)` and `row_errors_problem(errors)`, the two wire
  shapes above.
- Conformance cases: export negotiation, the `Content-Disposition` header, the
  import report, row-error 422s, and all-or-nothing bulk create and delete.

**`rn-forge-django`**, new extra `transfer = ["django-import-export[xlsx]"]`,
new module `rn_forge.django.drf.transfer`, not imported by the `drf` facade:

- `ResourceExportMixin`: the viewset names an `export_resource_class`. It
  overrides `list()` so that a negotiated tabular format runs
  `filter_queryset()` → `Resource.export()` → tablib, or `write_xlsx`.
  Passthrough renderers make DRF's own content negotiation select the format.
- `ResourceImportMixin`: the viewset names an `import_resource_class`. It
  provides the `:import` and `:importTemplate` actions. It passes the request
  user to the resource so audit fields and per-row authorization run in
  `before_import_row`, and maps `Result` to the wire shapes above.
- `BatchCreateMixin` and `BatchDeleteMixin` replace `bulk.py`, keeping the
  per-item authorization hooks `ew-loop-api` depends on. Recorded exemption:
  no maintained library exists.
- `CustomMethodRouter`, a `DefaultRouter` subclass, in `rn_forge.django.drf.routers`.
  It goes in the base `drf` extra, not `transfer`, because every `:action`
  needs it. See "AIP-136 routing on DRF" below.

**`rn-forge-fastapi`**, `rn_forge.fastapi.transfer`, behind a `transfer` extra
that brings `tablib[xlsx]` through `rn-forge-commons[excel]`:

- `tabular_format` dependency: web's negotiation over the request headers.
- `tabular_response(rows, model, fmt, filename)`: pydantic field aliases become
  the headers; returns a `StreamingResponse` for CSV and a `Response` for xlsx.
- `read_rows(upload, model) -> RowsResult`: tablib load, then a pydantic
  `TypeAdapter` per row, collecting `(row, field, message)` errors for
  `row_errors_problem`.
- No persistence and no upsert planner. The application calls its ORM's upsert.
  A shared planner is added only when a second FastAPI consumer writes the same
  one.

**`django-import-export` is not ported.** Most of its code is Django ORM
integration: instance loaders, `ForeignKeyWidget` querysets, transactions, the
admin. FastAPI already has a native mechanism for each concept:

| `django-import-export` | FastAPI equivalent | Owned by |
| --- | --- | --- |
| `Resource` with export fields | A pydantic export model with `from_attributes=True`. Field aliases are the headers; a `computed_field` or `field_serializer` covers FK traversal, full names and enum display names | Application |
| `Resource` with import fields | A separate pydantic import model: aliases are the external headers (`FNAME`), `field_validator`s normalize values | Application |
| tablib load and export | Called directly by `read_rows` and `tabular_response` | pykit (thin) |
| Row validation and `Result.invalid_rows` | `read_rows` → `RowsResult(valid, errors)` → `row_errors_problem` | pykit (thin) |
| `ForeignKeyWidget(Role, field="code")` | One `SELECT … WHERE code IN (…)` in the application's service, mapped before persisting | Application |
| `import_id_fields`, `skip_unchanged`, `use_bulk` | SQLAlchemy `insert().on_conflict_do_update(index_elements=…, set_=…, where=<columns IS DISTINCT FROM excluded>)`. On PostgreSQL, `RETURNING (xmax = 0)` separates inserts from updates for the report counts | Application (native ORM) |
| `dry_run` | `validateOnly`: run the same unit of work, then roll the transaction back | Application; the wire shape is pykit's |
| `before_import_row` authorization | A plain loop over the validated rows with the request's `Principal` | Application |

What pykit ships for FastAPI is therefore about 200 lines of wire glue. The
persistence half stays with the application, because `rn-forge-sqlalchemy` is
parked. If that package is revived, a generic upsert over an ORM model is its
first candidate. Until then, `fastapi-import-export` is re-evaluated in R5.

#### AIP-136 routing on DRF, probed 2026-09-22

The probe ran DRF 3.17.1, Django 6.0.7 and drf-spectacular, with `WireAutoSchema`
generating the schema.

**Stock routers cannot express the colon form.** A dynamic route is
`^{prefix}/{url_path}{trailing_slash}$`, so `url_path=":batchCreate"` gives
`/orders/:batchCreate`. The detail route's default lookup regex, `[^/.]+`, also
accepts a colon, so `GET /orders/12:cancel` reaches `retrieve` with
`pk="12:cancel"`. Today every `@action` is spelled `/orders/import`, and
`operation_id` names it `importCreate`, which violates §9.

**A route-table override is enough.** The routes table becomes:

| Order | Route | Mapping |
| --- | --- | --- |
| 1 | `^{prefix}{trailing_slash}$` | `list`, `create` |
| 2 | `^{prefix}:{url_path}$` | `detail=False` actions |
| 3 | `^{prefix}/{lookup}:{url_path}$` | `detail=True` actions, **before the detail route** |
| 4 | `^{prefix}/{lookup}{trailing_slash}$` | `retrieve`, `update`, `partial_update`, `destroy` |

What the probe showed for that table:

| Check | Result |
| --- | --- |
| Resolve | `POST /orders:batchCreate`, `POST /orders:import` and `POST /orders/12:cancel` reach the right action, with `pk="12"` |
| Unknown verb and wrong method | `GET /orders/12:cancel` is 405, not `retrieve`. Putting row 3 after row 4 brings the `pk="12:cancel"` bug back |
| `reverse()` | `orders-batch-create` gives `/api/orders:batchCreate` and `orders-cancel` gives `/api/orders/12:cancel` |
| `DefaultRouter` base | Works with `trailing_slash=True` too: the API root view and format suffixes are kept, and custom methods never take a slash |
| Lookup regex | Excluding `:` (`[^/.:]+`) also fixes the collision under the stock order, and turns `GET /orders/12:nope` into 404 |
| drf-spectacular | Paths come out as `/api/orders:batchCreate` and `/api/orders/{id}:cancel`, with operationIds `ordersBatchCreate`, `ordersImport` and `ordersCancel`, straight from `rn_forge.web.openapi.operation_id` with no override |

**Ship both fixes.** Use the route order, and have `get_lookup_regex` default to
`[^/.:]+` when a viewset sets no `lookup_value_regex`. That is about 30 lines
over DRF's own extension point, so no exemption is needed.

`rn_forge.django.auth.urls` moves to the new router. The existing
`/…/bulk-create/` and `/…/import/` URLs change as part of R7.
`api-conventions.md` §9 gains one line naming `CustomMethodRouter` as the DRF
spelling, in the same change that ships it.

#### Retired

Deleted outright, with no re-exports:

- `drf/views/transfer.py`, `parsers.py`, `renderers.py`, `bulk.py`;
- `TransferColumn`, `ExportDataset`, `ImportDataset` and `ImportResult`;
- snapshot delete-missing and the DB-shaped bulk load;
- the `default_transfer_format`, `export_max_rows` and `import_max_rows`
  settings, which are replaced by a single `transfer.max_rows`;
- the transfer-view variants in `rn_forge.django.auth.drf.views`.

`BaseModelViewSet` drops the bulk mixins. The `excel` requirement leaves every
DRF extra, which completes R6's minimum. `mixins.py`, `enums.py` and `base.py`
stay; they are DRF-native.

#### R7 order

1. ~~Owner approves `tablib` and `django-import-export`.~~ Approved
   2026-09-22.
2. Web: `rn_forge.web.transfer`, conformance cases, `api-conventions.md`
   section.
3. Commons: `write_xlsx`, and the `excel` extra swap. Check that `fixtures.py`
   still passes without pandas; if it reads Excel through pandas, it keeps the
   `pandas` extra.
4. Django: `CustomMethodRouter` (probed, above), then the mixins; delete the old modules, tests and
   guide sections in the same change.
5. FastAPI: `rn_forge.fastapi.transfer` and its conformance driver.
6. `ew-loop-api` migration notes in the django guide:
   - `_get_download_template` / `_build_download_template_row` become an export
     `Resource`;
   - `_get_upload_template` / `_build_instance` / `_build_foreignkey_lookups`
     become an import `Resource`;
   - the frontend moves from `POST …/download` (and its base64-in-JSON CSV
     response) to `GET` with `Accept`.

   The application migrates when it adopts pykit; it is not a gate.

#### R7 validation

The block below, plus:

- `rg "TransferColumn|ExportRenderer|ImportParser|bulk-create" packages`
  finds nothing;
- `uv sync --extra drf` in `rn-forge-django` installs neither openpyxl nor
  pandas;
- the transfer conformance cases run on both drivers with no skips.

#### R7 open questions

Settled by the owner, 2026-09-23:

1. **Import failure default:** all or nothing, with partial saves opt-in
   (`import_rollback_on_validation_errors = False`).
2. **Export over the row cap:** `422`, `about:blank`, the cap in `detail`.
3. **How much the transfer layer is shared across stacks:** moved to R9.

### R9: SQLAlchemy and tablib across both stacks — implemented 2026-09-23

**Status:** implemented 2026-09-23, uncommitted; see "R9 status" below. Every
question was settled by the owner on 2026-09-23. R7 and R8 are done, and nothing in R9 changes their wire: R9 adds
the SQLAlchemy half that R7 left to the application and R8 left to R9.

**Owner decisions, 2026-09-23 (before the questions):**

- **All SQLAlchemy work is ideated and implemented together in R9.** That
  covers R7's FastAPI persistence half (the upsert row of its FastAPI mapping
  table), R8's SQLAlchemy keyset `orderBy`, R5's deferred
  `fastapi-pagination` SQLAlchemy keyset evaluation, and the web plan's
  "Deferred" `rn-forge-sqlalchemy` contents. No SQLAlchemy code lands under R7
  or R8.
- **SQLite is supported alongside PostgreSQL**, as the default local and test
  database. Every contract below works on both dialects.
- **R7's settled answers carry over:** an import is all or nothing by default,
  and an export over the row cap is `422`. The upsert contract inherits the
  first.

#### R9 facts checked, 2026-09-23

| Fact | Consequence |
| --- | --- |
| R7 is implemented: `rn_forge.fastapi.transfer` (`read_rows`, `tabular_response`) and `rn_forge.django.drf.transfer` exist | R9 adds to working code; no wire changes |
| `read_rows` is `async` but runs `tablib` load and pydantic validation on the event loop | Q4 |
| `fastapi-pagination[sqlalchemy]` depends on `sqlakeyset` (2.0, released 2026-08-29) | Q5 has one library candidate, not two |
| `rn_forge.web.pagination.Cursor` holds one `sort_key: str`, an `entity_id` and the bound `order_by` | The SQLAlchemy keyset must read and write that token |
| `fastapi-import-export` 0.3.0 (2026-02-26) was routed to R5 by R7, but R5 evaluated only its four candidates | Still unevaluated; Q7 |
| SQLAlchemy's `on_conflict_do_update` does not apply a column's Python-side `onupdate` | The upsert stamps `update_time` itself (Q6) |
| SQLite stores `DateTime(timezone=True)` without a zone | Timestamps need a UTC type decorator to keep AIP-142's `Z` (Q6) |
| Django's optimistic concurrency raises `rn_forge.web.VersionConflict` with `412` | The SQLAlchemy helper raises the same, not a package-local `StaleVersionError` |

#### R9 decisions (owner, 2026-09-23)

| # | Question | Decision |
| --- | --- | --- |
| Q1 | Unpark `rn-forge-sqlalchemy`? | **Unparked**, as the sibling package the web plan places (depends on `rn-forge-web`, imports neither `rn_forge.fastapi` nor `rn_forge.django`), **scoped to what R7, R8 and R9 need**. The rest of the web plan's list waits for a consumer |
| Q2 | One upsert contract, two ORMs | **Shared at the wire, native per ORM.** Django keeps `django-import-export` as its engine. SQLAlchemy gets a native `upsert` with a portable pre-`SELECT`. No shared Python interface across the two ORMs |
| Q3 | One column spec, or two native idioms? | **Two native idioms**: `Resource` on Django, pydantic models on FastAPI. The conformance cases prove the wire is identical. A shared spec would be a layer in place of the framework |
| Q4 | Async | **pykit offloads its own CPU-bound work**: `read_rows` and `tabular_response`'s xlsx build run in a worker thread. `rn-forge-sqlalchemy` is **async only** (`AsyncSession`). No streaming export: the row cap bounds it, and large files are AIP-151's path |
| Q5 | Keyset `orderBy` on SQLAlchemy | **Own predicate over web's `Cursor`**, about 30–40 lines. `sqlakeyset` is exempt (below). The first sort field need not be unique on either stack (id tiebreak) |
| Q6 | Audit fields | **Explicit.** An `AuditMixin` with Python-side UTC defaults and a `UTCDateTime` type decorator. `created_by`/`updated_by` are set by the caller; `upsert(actor=…)` stamps all four. No session events, no contextvar, no `server_default` |
| Q7 | Library re-checks | `fastapi-import-export` is **probed in step 0** against R5's criteria, verdict written into R5's table. tablib's `Dataset` **stays the in-memory contract**; no streaming reader while `transfer.max_rows` exists (revisit with the first AIP-151 consumer). `sqlakeyset` is settled by Q5 |
| Q8 | Dependencies and test matrix | **Approved.** Base: `sqlalchemy[asyncio]>=2.0` and `rn-forge-web`, no database driver. `dev`: `aiosqlite` (the default suite runs on SQLite) and `asyncpg` (PostgreSQL tests, marked `postgres`, run only when a DSN is set) |

**Recorded exemption (principle 1), `sqlakeyset`:** its bookmark is its own
serialized marker tuple, not web's `Cursor`. Adopting it means translating the
token in both directions to replace a predicate of about ten lines, so it
deletes no kit code (rule 6). One sentence goes in the keyset module's
docstring, as R5's exemptions do. Revisit when it accepts a caller-supplied
marker codec.

#### R9 in `rn-forge-sqlalchemy` (new package)

`packages/rn-forge-sqlalchemy`, `src/rn_forge/sqlalchemy/`, laid out like the
other packages (README, `docs/guides/`, `mkdocs.yml`, curated facade).

- **`models`**:
  - `Base`, a `DeclarativeBase` whose `MetaData` carries the Alembic
    constraint `NAMING_CONVENTION`;
  - `UTCDateTime`, a `TypeDecorator` over `DateTime(timezone=True)`. It rejects
    a naive value on write, stores UTC, and returns an aware UTC value on read
    on both dialects;
  - `AuditMixin`: `create_time` and `update_time` (`UTCDateTime`, Python-side
    UTC `default`, and `onupdate` on `update_time`), `created_by` and
    `updated_by` (`String(255)`, matching Django's `BaseModel`). Names follow
    `model-conventions.md` and AIP-148;
  - `VersionMixin`: a `version` integer, starting at 1.
- **`concurrency`**: `update_versioned(session, obj, **values)`, which issues
  `UPDATE … WHERE pk = :pk AND version = :expected`, sets `version + 1`, and
  raises `rn_forge.web.VersionConflict` with `error_code=412` when no row
  matched but the row exists. Same contract as Django's `VersionedModel`.
- **`upsert`**:

  ```python
  async def upsert(
      session: AsyncSession,
      model: type[Base],
      rows: Sequence[Mapping[str, Any]],
      *,
      key: Sequence[str],
      fields: Sequence[str],
      actor: str,
  ) -> UpsertCounts  # created, updated, skipped
  ```

  1. Read the existing rows with `SELECT … WHERE (key) IN (…)`, chunked so
     SQLite's bound-parameter limit is never reached.
  2. Classify each input row in Python: absent is *created*, any of `fields`
     different is *updated*, otherwise *skipped*.
  3. Write created and updated rows with one dialect
     `insert().on_conflict_do_update(index_elements=key, set_=fields + audit)`
     statement (PostgreSQL or SQLite, picked from the session's dialect).
     `create_time`/`created_by` are set on insert only; `update_time` and
     `updated_by` are set explicitly, because `onupdate` does not apply.
  4. Two input rows with the same natural key raise `ValueError`; the caller
     validates before calling, as it does for every row error.

  `upsert` never commits. All or nothing is the caller's transaction. For
  `validateOnly` the caller rolls back after the call, matching
  `django-import-export`'s `dry_run`, which writes and rolls back. No
  SAVEPOINTs. No `RETURNING`/`xmax` optimisation until a measurement asks
  for it.
- **`pagination`**:
  - `keyset(stmt, *, columns, terms, cursor, id_column)` applies web's
    ordering to a `Select`: `ORDER BY` the first term, then `id_column`, both
    in the first term's direction. With a cursor, it adds
    `(col > k) OR (col = k AND id > i)`, with `<` for `desc`. `columns` maps
    each allowed wire field name to its column. `cursor.sort_key` is
    converted back by the column type's `python_type`, `datetime` through
    `fromisoformat`. It calls `check_cursor_order` first, so a changed
    `orderBy` stays a 400.
  - `next_page_token(sort_value, entity_id, terms)` is the other direction:
    it writes `sort_value` in the form `keyset` reads (`isoformat()` for
    `datetime`, `str` otherwise) and calls `rn_forge.web.encode_cursor` with
    the canonical order. The caller fetches `page_size + 1` rows; there is no
    page-fetching helper.
- **Not in the first cut** (the web plan's list, waiting for a consumer):
  the SQL `AsyncIdempotencyStore`, session and unit-of-work helpers,
  readiness checks, and multi-tenant scoping.

**Workspace wiring**, in the same change that creates the package:

- a root `pyproject.toml` workspace member and `[tool.uv.sources]` entry;
  `postgres` is registered as a root pytest marker;
- `.importlinter`: `rn_forge.sqlalchemy` in `root_packages`, and a forbidden
  contract: `rn_forge.sqlalchemy` imports neither `rn_forge.fastapi`,
  `rn_forge.django`, `fastapi` nor `django`;
- the root `mkdocs.yml` nav and `docs/index.md` include the new site;
- the status board's repo-shape rule applies: the kiln
  `[archetype.python-lib] packages` entry and `state.json` re-seed happen only
  once kiln Phase F.1 has created those files. They do not exist today, so
  they are not created here;
- the web plan's "Deferred" entry and the status board's "Parked" list mark
  the package unparked by R9, naming this section.

#### R9 in `rn-forge-fastapi`

- `read_rows` runs the tablib load and the per-row validation in
  `run_in_threadpool`; only `await upload.read()` stays on the loop.
- `tabular_response` builds the xlsx body in `run_in_threadpool`. CSV already
  streams.
- No import of `rn_forge.sqlalchemy`, in either direction. The FastAPI guide
  gains the wiring example: `read_rows` → the application's foreign-key
  lookups → `upsert(actor=principal…)` → rollback when `validateOnly` →
  `import_report_body`, and `keyset` behind `order_by_param`.

#### R9 in `rn-forge-django`

Nothing. `django-import-export` stays the engine, and audit fields stay with
`AuditFieldsViewMixin`.

#### R9 order

0. Probe `fastapi-import-export` 0.3.0 in a throwaway venv against R5's
   criteria and rule 6; add its row to R5's verdict table. The expected
   verdict is exempt. If it is adoptable, stop and bring it to the owner
   before step 3.
1. FastAPI: the thread offload in `read_rows` and `tabular_response`.
2. Scaffold `rn-forge-sqlalchemy` with the workspace wiring above.
3. `models` and `concurrency`.
4. `upsert`.
5. `pagination` (`keyset`), with the `sqlakeyset` exemption sentence.
6. Docs: the package README and guide, the FastAPI guide's wiring example,
   `model-conventions.md` naming the SQLAlchemy mixins, the status board.

#### R9 validation

The block below, plus:

- `uv run pytest packages/rn-forge-sqlalchemy` passes on SQLite (aiosqlite),
  and again with the PostgreSQL DSN set, where the `postgres`-marked tests run;
- the package's tests include a FastAPI app over SQLite (test-only; `fastapi`
  is in the package's `dev` group, never in `src`) that passes the
  `pagination.order-by-*` and import cases from `rn_forge.web.conformance.CASES`
  (through `case_by_id`, as the FastAPI driver does) with no skips;
- `upsert` tests cover created, updated and skipped counts, the audit stamps
  on insert and on update, rollback for `validateOnly`, a duplicate key in the
  input, and a chunked key set larger than SQLite's parameter limit, on both
  dialects;
- a timestamp written and read back through SQLite is aware UTC and
  serializes with `Z`;
- `uv run lint-imports` passes with the new contract;
- `uv run --group docs mkdocs build --strict` passes for the new package and
  for the combined site.


#### R9 status, 2026-09-23

Steps 0 to 6 are done and uncommitted.

- **Step 0:** `fastapi-import-export` 0.3.0 is exempt; its row is in R5's table.
  Nothing was brought to the owner.
- **Step 1:** `read_rows` and `tabular_response` offload to
  `run_in_threadpool`. `tabular_response` is now `async`, so callers `await` it.
- **Steps 2 to 5:** `packages/rn-forge-sqlalchemy` (`models`, `concurrency`,
  `upsert`, `pagination`) with the workspace wiring. `web-layers` lists
  `sqlalchemy` as a third sibling beside `django` and `fastapi`, and a separate
  contract forbids the frameworks.
- **Step 6:** the package README and guide, the FastAPI transfer guide's
  wiring and paging examples, `model-conventions.md`, the root README and
  `docs/index.md`, and the status board.
- **Choices the plan left open:** `keyset` with no terms orders by `id_column`
  ascending and the token's sort key is the id (which is what the shared
  conformance tokens hold); `update_versioned` raises `LookupError` when the row
  is gone; `upsert` raises `TypeError` for a model without `AuditMixin`;
  `UTCDateTime` defines `python_type` so `keyset` can convert a token value;
  the `postgres` tests read `RN_FORGE_TEST_POSTGRES_DSN`.
- **Verified:** the sqlalchemy suite passes on SQLite, and passes again on
  PostgreSQL through an embedded server (67 passed, both dialects). The
  conformance test serves the `pagination.*` and `transfer.import-*` cases with
  no skips.

### R8: AIP adoption where no RFC applies

**Status:** planned, 2026-09-22. No new dependencies. The owner decides the
two "consider" rows; everything else is ready once R7 lands.

AIPs are a published design guide, not IETF standards. They fill gaps. Where
an RFC or IETF draft covers the same ground, the RFC wins, following the order
of authority in the premise. `api-conventions.md` already uses AIP-158
(pagination) and AIP-136 (custom methods); R7 adds AIP-163, AIP-233, AIP-235
and names AIP-151.

| AIP | What it gives | Verdict | Work |
| --- | --- | --- | --- |
| [132](https://google.aip.dev/132) List `orderBy` | `orderBy=displayName desc,createTime` on List | **Adopt.** Today pagination is pinned to `pk` (`rn_forge.django.drf.pagination`, `ordering = "pk"`), so a client cannot sort. Every CRUD UI needs sorting | web: parse and validate `orderBy` against an allow-list. The cursor token binds the order, and a changed `orderBy` with an old `pageToken` is 400. DRF: an `OrderingFilter` subclass (`ordering_param="orderBy"`, AIP syntax) that `CursorPagination` already consults. FastAPI: a dependency. Conformance cases |
| [163](https://google.aip.dev/163) `validateOnly` | Validate without side effects | **Adopt** (R7 import). It applies to any mutating method a UI previews | Convention, plus the R7 flag |
| [231](https://google.aip.dev/231) / [234](https://google.aip.dev/234) `:batchGet`, `:batchUpdate` | Completes the batch set R7 starts | **Adopt the spelling.** Implement on demand | Convention only |
| [142](https://google.aip.dev/142) Time and duration | RFC 3339 UTC timestamps (`Z`), `…Time`/`…Date` suffixes | **Adopt.** It points to RFC 3339, which is the actual standard, and the conventions do not state a timestamp format today | Convention, plus one conformance case per stack (DRF `DATETIME_FORMAT`, pydantic's serializer) |
| [185](https://google.aip.dev/185) Versioning | Major version in the path (`/v1`); no minor versions on the wire | **Adopt.** Pairs with R2.5 B3 (RFC 9745 `Deprecation`, RFC 8594 `Sunset`) for retiring a version | Convention |
| [180](https://google.aip.dev/180) Backwards compatibility | What counts as a breaking change | **Adopt as the review rule.** Enforce it with an OpenAPI diff in CI (`oasdiff`), in kiln's golden repos rather than in pykit | Convention; kiln handoff note |
| [151](https://google.aip.dev/151) Long-running operations | `202` + `Location` to an `Operation {name, done, metadata, error \| response}` | **Adopt the shape now, build on demand.** R7's large-file path points to it. `error` is an RFC 9457 problem, not `google.rpc.Status` | Convention; a web dataclass when the first consumer needs it |
| [148](https://google.aip.dev/148) Standard fields | `createTime`, `updateTime`, `etag`, `uid` | **Consider (owner).** `BaseModel` emits `createdAt`/`updatedAt`, and `createdBy`/`updatedBy` have no AIP equivalent. Renaming is cheap only before the release tags. Database columns stay; only the serializer names change | django serializers and FastAPI models; conformance |
| [164](https://google.aip.dev/164) Soft delete | `deleteTime`, `:undelete`, `showDeleted` | **Consider (owner)**, only if a consumer needs it. The kit has no soft delete today | — |
| [157](https://google.aip.dev/157) Partial responses | `readMask` | Defer until a payload-size problem appears | — |
| [193](https://google.aip.dev/193) Errors | `google.rpc.Status` | **Reject.** RFC 9457 governs | — |
| [154](https://google.aip.dev/154) ETags | `etag` field | **Reject.** RFC 9110 headers govern (§3) | — |
| [155](https://google.aip.dev/155) Request identification | `requestId` field | **Reject.** The IETF `Idempotency-Key` draft governs (§5) | — |
| [134](https://google.aip.dev/134) Update with `updateMask` | Field masks on `PATCH` | **Reject.** `PATCH` is RFC 7396 JSON Merge Patch; the convention should name it (§10) | One line in §10 |
| [160](https://google.aip.dev/160) Filtering | A `filter` expression language | **Reject.** pykit would have to maintain a parser. Per-field query parameters (django-filter, FastAPI `Query`) are the native mechanism | — |
| [122](https://google.aip.dev/122) Resource names | `name: "orders/123"` in place of ids | **Reject.** It changes every payload and path parameter, and REST ids are the common practice | — |

**Order.** 142, 185, 134 (§10 wording) and 180 are convention text and land
together. 132 is the one code item. 151's dataclass waits for its first
consumer. 148 and 164 wait on the owner.

#### R8 status (2026-09-23)

Owner decisions: **AIP-148 adopted** (rename), **AIP-164 skipped** and put on
the backlog (revisit when a consumer needs soft delete; `deleteTime`,
`:undelete`, `showDeleted`).

- **Convention text** (`api-conventions.md`): §4 sorting, §10 `PATCH` is RFC 7396,
  new §18 (timestamps, standard fields) and §19 (versioning, compatibility,
  `validateOnly`, batch spelling, long-running operations, rejected AIPs).
- **AIP-132 `orderBy`:** `rn_forge.web` (`parse_order_by`, `OrderField`,
  `format_order_by`, `check_cursor_order`, `InvalidOrderBy` → 400; the cursor
  carries its order), DRF `OrderByFilter` with `CursorPagination`, FastAPI
  `order_by_param`. Three conformance cases, run by all five drivers.
  The token holds a sort value and the primary key, so the first sortable field
  need not be unique (closed 2026-09-23, below). FastAPI's SQLAlchemy keyset half
  stays with R9.
- **AIP-148:** the Django `BaseModel` fields are now `create_time` and
  `update_time` (all four `db_column` camelCase overrides were
  then dropped, since no application is migrating), so the
  wire names are `createTime`/`updateTime`; `createdBy`/`updatedBy` stay. The
  FastAPI package has no base model, so there was nothing to rename there.
  `model-conventions.md` follows.
- **AIP-142:** stated in §18, with a unit test per stack (pydantic; DRF with
  `USE_TZ`/`TIME_ZONE=UTC`) rather than a conformance case.
- **Closed 2026-09-23.** Two points were checked against majority practice
  and both stand, with a recorded reason:
  - `createTime`/`updateTime` is the one adopted name that differs from the
    common `createdAt`/`updatedAt`. It stays (owner decision above) because
    nothing is released; changing it after the release tags is a breaking
    change under AIP-180.
  - The `:verb` spelling (AIP-136) is valid in a URI but some gateways and
    routers read `:` as a parameter marker. DRF's `CustomMethodRouter` handles
    it. A gateway check in kiln's golden repos is the handoff, and if a target
    fails it, the deviation (`POST /orders/{id}/cancel`) is recorded here, not
    patched in the kit.
- **AIP-142 and AIP-151 built (2026-09-23).** `timestamps.rfc-3339-utc-with-z`
  runs on the web, FastAPI and Django drivers (Django with `USE_TZ`/`TIME_ZONE=UTC`
  in its wiring). `rn_forge.web.Operation` is the AIP-151 body, with three
  `operations.*` cases on the same drivers. The Django driver sets the camelCase
  renderer on its timestamp view, because its views bind DRF's default renderer at
  import, before the driver's settings apply.
- **Non-unique first sort field closed (2026-09-23).** A page orders by the first
  `orderBy` field, then the primary key, and the token holds both. SQLAlchemy
  already did this. DRF's `CursorPagination` now overrides `paginate_queryset` to
  filter on that pair, because DRF's own cursor resolves ties with an offset the
  shared token does not carry, and a second token format would break the exact
  token parity the conformance table asserts. No conformance case: the fixtures
  have no sortable field with duplicates, so the tie walk is a DRF integration
  test and the SQLAlchemy one that already existed.
- **One `orderBy` term (2026-09-23).** `parse_order_by` rejects more than one
  comma-separated term with a 400 (`pagination.order-by-two-fields-is-400`, all
  drivers), because later terms would otherwise be accepted and silently not
  order the list. AIP-132 allows several; the industry standard is a composite
  keyset (a value per term plus the key, an OR-of-ANDs predicate, an explicit
  NULL rule, a matching composite index). That is on the status board's backlog
  to be ideated. The function still returns a tuple, so allowing several later
  does not change its signature.
- **Done, verified 2026-09-23.** The `orderBy` code exists in web, DRF and
  FastAPI, and the three `pagination.order-by-*` conformance cases pass on all
  five drivers with no skips (21 tests). The leftovers are on the status board's backlog: AIP-151's
  dataclass, `:batchGet`/`:batchUpdate` handlers, the `oasdiff` kiln note for
  AIP-180, and multi-term `orderBy` on a paged list. SQLAlchemy keyset `orderBy` is an R9 item, implemented there with the
  rest of the SQLAlchemy work (owner, 2026-09-23).

### R10: simplification pass after R3 — implemented 2026-09-23 (R10.3 stopped at its probe)

**Why this section exists.** Reviewing R3's `asgi.py`, `problem.py` and
`tracing.py`, the owner asked why request timing and W3C trace handling, which
every service needs and which published standards define, are implemented in
the kit rather than taken from a library. The question is the premise's own
test, applied to R2.5 and R3 together: the kit is plumbing that wires the
standard way of doing things, and a developer should only write functional
logic. This section is the answer, the owner's decisions, and the handoff
spec. R10.1, R10.2, R10.4 and R10.5 are implemented; R10.3 stopped at its
probe, see "R10 status" below.

**Short answer.** R3 did adopt the library: `traceparent`/`tracestate`
parsing, validation, the new-trace fallback, `traceresponse`, and the span
that times every request all come from OpenTelemetry's instrumentation. What
R3 left in the kit is the glue beneath that (reading the active span into the
problem body, 30 lines). The surprise is justified elsewhere: three pieces
that **predate** R3 or the current Starlette now duplicate something the
adopted stack already provides, and R3 landed on top of them instead of
removing them.

**Rule 6, adopted first (owner, 2026-09-23).** Added to R2.5's rules and to
the status board's standing rules. When a library or the framework is adopted
for a concern, everything that library already emits or enforces is deleted
from the kit, including code that predates the adoption. A conformance case
that only the deleted code satisfied is re-pointed at the library's
behaviour, or dropped with the reason recorded in the plan.

#### R10 findings

| # | Kit code | Verdict | Evidence, read 2026-09-23 |
| --- | --- | --- | --- |
| 1 | `AccessLogMiddleware` (web ASGI and `rn_forge.django.middleware`), `request_log_fields`, `api-conventions.md` §17, `AppConfig.log`'s access-log role (R2.5 B9) | **Delete** (R10.2) | The OTel server span that R3 installs already carries `http.request.method`, `url.path`, `http.response.status_code` and the request duration, in exactly B9's names, and `opentelemetry-instrumentation-asgi` 0.65b0 (locked) records the `http.server.request.duration` histogram beside it. uvicorn and gunicorn write an access log by default for the no-SDK case. B9 was written before R3 chose option a; with option a its requirement is met by the instrumentation itself |
| 2 | `BodySizeLimitMiddleware`, `_send_413` and `_get_header` in `rn_forge.web.asgi` (R2.5 B7) | **Keep** (R10.3 rejected) | Starlette 1.6.0 (locked) ships `starlette.middleware.body_limit.RequestBodyLimitMiddleware` with B7's semantics: a `Content-Length` pre-check plus counted streaming, 413 on breach. It raises an `HTTPException(413)` out of `receive()`, but for a declared oversized `Content-Length` its `send` wrapper discards the app's response and sends a plain-text 413, so the kit's problem body is lost (**the probe failed, 2026-09-23; the kit's middleware stays**, see "R10 status"). Rule 6 does not apply: the library enforces the limit but not the kit's wire format. Django keeps `DATA_UPLOAD_MAX_MEMORY_SIZE` → `RequestDataTooBig` → `CONTENT_TOO_LARGE`, as today |
| 3 | `trace_log_processor` in `rn_forge.web.tracing` (R3 web item 3) | **Move to commons** (R10.4) | It is not an HTTP concern: any process under a span wants its log lines to carry the ids. `rn-forge-commons` already owns OTel log correlation for the stdlib path (`enable_otel_correlation`, the `otel` extra) and the structlog integration (`rn_forge.commons.logging.structlog`). No maintained library packages this processor (structlog's docs give it as a snippet), so hand-rolling is right, but in the package whose subject is logging |
| 4 | `trace_id` problem extension, the documented snake_case exception to §7 | **Rename to `traceId`** (R10.5; decision 2 below) | ASP.NET Core's problem-details factory emits `traceId`; §7 then has no exception |
| 5 | `rn_forge.web.security` (`secure` wrapper, `SecurityHeadersMiddleware`) | **Keep** | The library is adopted; the middleware is the setdefault merge that `secure`'s own ASGI helper does not do. After R10.2 it is one of two ASGI middlewares left in web, beside `BodySizeLimitMiddleware` |
| 6 | `FastApiApp` and `rn_forge.django.tracing.instrument()` setting `TraceResponsePropagator` as process-global state | **Keep, flagged** | `traceresponse` is Trace Context Level 2 (Candidate Recommendation) and OTel marks the propagator experimental. Revisit when OTel graduates or removes it; if removed, `AppConfig.tracing` keeps instrumenting and the `traceresponse` expectations move to `expect_absent_headers` |
| 7 | `current_trace_id`, `current_span_id`, `TRACE_ID_KEY`, `render_problem`'s use of them | **Keep** | The glue between the adopted instrumentation and the problem body; no library offers it, because the problem body is the kit's rendering |
| 8 | R3's documentation | **Defects** (R10.1) | See "R3 docs defects". R3's "all validation green" is not true of the plan's validation block: `mkdocs build --strict` fails in `rn-forge-web` |

#### R3 docs defects (found 2026-09-23)

- `packages/rn-forge-web/docs/api/context.md` still documents
  `rn_forge.web.context`, which R3 deleted, and `mkdocs.yml` still lists it.
  `uv run --group docs mkdocs build --strict` aborts on it.
- `packages/rn-forge-web/README.md`: the opening paragraph names "the
  correlation ID" and "the ASGI correlation middleware"; "What stays in a
  framework package" lists "resolving an inbound correlation ID"; "Eleven flat
  modules" is no longer the count; the last "Dependencies and why" paragraph
  names "the access-log middleware" as hand-rolled.
- Root `README.md` package table says "correlation IDs" for `rn-forge-web`.
- `packages/rn-forge-web/docs/guides/quickstart.md` §2 passes
  `extensions={"trace_id": current_trace_id()}` to `registry.build`. That
  teaches the caller to add a member `render_problem` already adds; the
  example should call `render_problem`, or drop the extension.

#### R10 status (2026-09-23)

- **R10.1: done, 2026-09-23.** `api/context.md` replaced by `api/tracing.md`
  and the nav entry fixed; the README, root README, quickstart, adoption index
  and checklist wording corrected. `mkdocs build --strict` passes in
  `rn-forge-web`, `rn-forge-fastapi` and `rn-forge-django`. The R3 section's
  validation claim is corrected above. Deviation: the plan's defect list did not
  name `docs/adoption/index.md`, `docs/guides/quickstart.md`'s "house
  correlation header" line or the checklist's `X-Correlation-ID` grep item; all
  three matched the R10 validation's `rg -i "correlation"` and were reworded.
  The web README's module count is now thirteen, not eleven.
- **R10.2: done, 2026-09-23.** Removed `AccessLogMiddleware` and `Log` from
  `rn_forge.web.asgi`, `request_log_fields` from `rn_forge.web.tracing`, and
  their facade entries and tests; dropped the FastAPI install and test and
  narrowed `AppConfig.log`'s docstring to the server-error event; deleted
  `rn_forge/django/middleware.py`, its test, `docs/api/middleware.md` and the
  nav entry; removed api-conventions §17. Deviations, none affecting the spec's
  intent: `.github/scripts/check_django_extra.py` listed
  `rn_forge.django.middleware` in its base import check, so it was dropped
  there; `docs/index.md` and `docs/adoption/model-conventions.md` in web and the
  Django README also named the access log and were corrected; the web
  checklist had no access-log item to remove. Because R10.3 did not land,
  `tests/test_asgi.py` was rewritten to cover the retained
  `BodySizeLimitMiddleware` (four tests) instead of being deleted.
- **R10.3: stopped at the probe, 2026-09-23. Nothing landed.** Probe: Starlette
  1.6.0's `RequestBodyLimitMiddleware` under `FastApiApp`'s handlers, against a
  route with a pydantic body, limit 200 bytes.
  - (a) A declared oversized `Content-Length` (a real 261-byte body, header
    matching): **fails.** The response is Starlette's plain-text `413 Content
    Too Large` (`text/plain`), not the kit's RFC 9457 problem.
    Corrected mechanism: `receive_with_limit` does raise
    `_RequestBodyTooLarge` (an `HTTPException` subclass) and the kit's handler
    renders a problem, but `send_with_limit` then sees `http.response.start`
    with the declared length over the limit, discards the app's response and
    sends a `PlainTextResponse`. The kit cannot intercept that.
  - (b) A streamed body with no `Content-Length` (10-byte limit): produced the
    RFC 9457 413 through `on_http_exception`. The "known risk" of FastAPI
    wrapping the exception in a 400 did not occur.
  - (c) Any route, including ones that never read a body, hits the plain-text
    413 when the declared `Content-Length` is over the limit, because that
    check runs before the application. A `GET` with `Content-Length: 0`
    passed.
  Per the stop condition, the kit's `BodySizeLimitMiddleware`, `_send_413`,
  `_get_header` and `rn_forge.web.asgi` stay, as do the ASGI type aliases in
  the web facade, the 413 `detail` and Django's `RequestDataTooBig` detail. No
  workaround was written. R10 decision 3 (remove `asgi.py`) depends on this
  phase and is deferred with it; **Decision 3 is withdrawn**: `asgi.py` still holds the middleware. Revisit
  only if Starlette lets the declared-length rejection go through the app's
  exception handlers, or offers a hook for the response.
- **R10.4: done, 2026-09-23.** `rn_forge.commons.logging.structlog` gains
  `otel_processor` (in `__all__`, installed in `_configure_once` before
  `_render_event`); web's `trace_log_processor`, its facade entry and tests are
  deleted; web's quickstart and checklist name the commons processor. Tests
  cover a valid span, no span, an unimportable `opentelemetry`, and the
  configured chain. Deviation: `SPAN_ID_KEY` (unused after this step) was
  deleted in R10.5 as specified, so its docstring was reworded in between.
- **R10.5: done, 2026-09-23.** `TRACE_ID_KEY = "traceId"`; `SPAN_ID_KEY` and
  its facade entry deleted; the `problem.server_error` log context keeps the
  literal `"trace_id"`; `VARIABLE_MEMBERS` and the conformance table use
  `traceId`; api-conventions §1 names `traceId` and the casing section drops
  its exception (it is section 8 in the file, not 7, and now lists three
  exemptions); the drivers' `CASING_EXEMPT` no longer names `trace_id`. All
  three drivers pass every case with no skips.

#### R10 decisions (owner, 2026-09-23)

1. **Rule 6: adopted.** See above.
2. **`trace_id` → `traceId`: adopted (R10.5).** *The issue.* The problem body
   is JSON a client reads, and §7 says every wire member is camelCase. R3 made
   `trace_id` the one exception, reasoning that it should match the log
   field. But the log field's name comes from the OpenTelemetry log data
   model, which governs log records, not HTTP payloads. The result is that a
   generated TypeScript or Java client sees `errors`, `detail` and
   `traceId`-style names everywhere except this one member, and every reader
   of §7 has to learn an exception whose only justification is on the other
   side of the service. Renaming aligns the member with §7 and with the one
   widely deployed precedent (ASP.NET Core). The log field stays `trace_id`:
   logs and the wire are different surfaces, each following its own standard.
   It is a wire change, and cheap only before the release tags.
3. **`rn_forge.web.asgi`: withdrawn (R10.3 rejected); it stays.** *Original reasoning, now moot:* *Checked for a fluent-surface role,
   2026-09-23:* neither framework package imports its type aliases.
   `rn-forge-fastapi` uses Starlette's own ASGI types and never touches web's,
   and `rn-forge-django` has no ASGI code. The only importers are
   `rn_forge.web.security`, the framework-free example `asgi_app.py`, and two
   web tests. Each framework package's facade is already the single surface
   its users import from, so the aliases add nothing there. They move into
   `security.py` as module-level aliases, not in its `__all__`; the example
   declares its own.
4. **Sequencing: R5's model-bearing evaluations run before R4.** See "R10
   sequencing" below.
5. **`AppConfig.log`: keep, for `problem.server_error` only.** *The issue.*
   The kit deliberately sends a generic `detail` on every 5xx, so the real
   cause never reaches the client. Something must record it server-side.
   Starlette re-raises an **unhandled** exception after the kit's 500 handler
   runs (`ServerErrorMiddleware`, `raise exc`), so the server's own log
   captures that case without the kit. It does **not** re-raise an exception
   the registry maps to a 5xx row, such as `RemoteProblem` (502) or
   `ServiceUnavailable` (503), nor a framework `HTTPException` with a 5xx
   status. For those, `AppConfig.log` is the only place the cause is recorded.
   The OpenTelemetry span could carry it instead, but only when an exporter
   is configured, and the kit cannot assume one (R3). So the sink stays, with
   its access-log role removed and its docstring narrowed.

#### R10 phases

Ordered, each with its tests, docs and a green validation run before the
next. R10.1 to R10.4 are wire-neutral; R10.5
is a wire change. All five land before R5's evaluations and R4.

**R10.1 Fix the R3 docs defects.**

- Replace `docs/api/context.md` with `docs/api/tracing.md` (`::: rn_forge.web.tracing`)
  and fix the nav entry in `packages/rn-forge-web/mkdocs.yml`.
- Fix every bullet in "R3 docs defects" above.
- Rerun the strict docs build in `rn-forge-web`, `rn-forge-fastapi` and
  `rn-forge-django`, and correct the R3 section's validation claim.

**R10.2 Delete the access log.**

- *web.*
  - Remove `AccessLogMiddleware` and `Log` from `asgi.py`, and
    `request_log_fields` from `tracing.py`.
  - Remove all three from `rn_forge/web/__init__.py`.
  - Remove their tests from `tests/test_asgi.py` and `tests/test_tracing.py`.
- *FastAPI.*
  - `app.py`: drop the `AccessLogMiddleware` install. Narrow the
    `AppConfig.log` docstring to the server-error event (decision 5).
  - `tests/test_app.py`: drop the access-log tests.
- *Django.*
  - Delete `rn_forge/django/middleware.py`, `tests/test_middleware.py` and
    `docs/api/middleware.md`, and the `Middleware` nav entry in
    `packages/rn-forge-django/mkdocs.yml`.
  - `tests/test_conformance.py`: remove it from the `MIDDLEWARE` list and from
    the module docstring.
  - `rn_forge/django/tracing.py`: remove it from the docstring.
  - `docs/guides/quickstart.md`: remove it from `MIDDLEWARE`, and remove the
    paragraph on overriding its `log`. Add one line: with the `otel` extra
    and `instrument()`, the request span is the access record.
  - The django README, if it lists the middleware.
- *Docs.*
  - Delete `api-conventions.md` §17; it is the last section, so nothing
    renumbers.
  - `rn-forge-web/docs/adoption/checklist.md`: remove any access-log item.
  - Status board: the R2.5 summary line "one access-log event in OTel names"
    gets "(deleted by R10.2)".
- No conformance case changes: §17 never had one.

**R10.3 Adopt Starlette's body limit.**

**Result, 2026-09-23: stopped at the probe; nothing in this phase landed.** See "R10 status".

- *Probe first, before editing.* Under `FastApiApp` with Starlette's
  `RequestBodyLimitMiddleware` in place of the kit's, against a route with a
  pydantic body:
  - (a) a declared oversized `Content-Length`, and (b) a streamed body with no
    `Content-Length`, must each produce the RFC 9457 413 through the kit's
    `on_http_exception` handler;
  - (c) record whether any kit route can hit Starlette's plain-text 413. That
    path fires when the application starts a response without reading the
    body. The health and catalog routes never read one, and a `GET` has no
    body to breach.
  - **Known risk for (a) and (b).** FastAPI's request-body parsing wraps
    unexpected exceptions in a 400 ("There was an error parsing the body").
    If Starlette's 413 exception is caught there, the probe fails.
  - **If (a) or (b) fails, stop R10.3.** Record the result under this item,
    leave the kit's middleware in place, and continue with R10.4. Do not
    hand-roll a workaround.
- *FastAPI.* In `app.py`, install `RequestBodyLimitMiddleware(max_body_size=
  config.max_body_bytes)` where `BodySizeLimitMiddleware` is installed today.
  `AppConfig.max_body_bytes` keeps its name and default.
- *web.*
  - Delete `BodySizeLimitMiddleware`, `_send_413` and `_get_header`, and
    their facade entries and tests. `tests/test_asgi.py` is then empty;
    delete it.
  - Keep `ContentTooLarge` and `CONTENT_TOO_LARGE`, which Django's mapping
    and the example use.
- *Remove `asgi.py`* (decision 3).
  - Move `ASGIApp`, `Message`, `Receive`, `Scope` and `Send` into
    `security.py` as module-level aliases, not in `__all__`.
  - Remove them from the web facade.
  - Delete `docs/api/asgi.md` and its nav entry.
  - `tests/test_security.py` stops importing them. Tests are not
    type-checked, so plain dicts and callables will do.
- *Conformance.* `problem.content-too-large-is-413` keeps its status and
  media type. Its `detail` becomes `"Content Too Large"`, the status phrase,
  which is what Starlette's exception carries.
  - Django: `drf/exceptions.py` sets the same string for `RequestDataTooBig`.
  - The example: `asgi_app.py` declares its own ASGI aliases. It implements
    the limit in its plumbing section, about 15 lines: a `Content-Length`
    check plus a counted `receive`, raising `ContentTooLarge` and rendering
    it through `render_problem`. The example already hand-rolls routing and
    body parsing for the same reason; its docstring says so in one line.
- *Docs.* In `api-conventions.md`'s 413 line and the B7 note, name Starlette's
  middleware on FastAPI and `DATA_UPLOAD_MAX_MEMORY_SIZE` on Django.

**R10.4 Move the structlog processor to commons.**

- `rn_forge.commons.logging.structlog` gains a public `otel_processor`, in
  that module's `__all__`, with the contract of today's `trace_log_processor`.
  - It imports `opentelemetry.trace` inside the function. On `ImportError`,
    it returns the event untouched, so the `structlog` extra does not require
    `opentelemetry-api`.
  - With no valid span it also leaves the event untouched. Otherwise it sets
    `trace_id` (032x) and `span_id` (016x).
- `_configure_once` puts it in the chain before `_render_event`,
  unconditionally, because it is a no-op without a span.
- Tests, in the commons test module that mirrors `logging/structlog.py`:
  - A valid span needs only the API: wrap a
    `NonRecordingSpan(SpanContext(...))` in `trace.use_span`. No SDK is
    needed.
  - Cover no span, and an unimportable `opentelemetry` via
    `monkeypatch.setitem(sys.modules, "opentelemetry", None)`.
- web deletes `trace_log_processor`, its facade entry and its tests.
  `current_trace_id` and `current_span_id` stay.
- Web's `docs/guides/quickstart.md` "For structured logs" paragraph and
  `docs/adoption/checklist.md` point at
  `rn_forge.commons.logging.structlog.otel_processor`, by name, with no
  cross-package link.

**R10.5 Rename the problem member to `traceId`.**

- `rn_forge.web.tracing`:
  - `TRACE_ID_KEY = "traceId"`. Its docstring names it the problem-body
    extension member only.
  - Delete `SPAN_ID_KEY`, which nothing uses after R10.2 and R10.4.
- `rn_forge.fastapi.problem`: the `problem.server_error` log context uses the
  literal `"trace_id"`. It is a log field, not a wire member (decision 2).
- Conformance:
  - `types.py`: `VARIABLE_MEMBERS` and its docstring.
  - `cases.py`: the redacted member in `_problem_body`, the casing case's
    description (which names `trace_id` as the exception), and
    `tracing.problem-body-carries-the-trace-id`'s description.
- `api-conventions.md`: §1's problem-body bullet, and §7's exception
  paragraph, which is deleted. §1's log-line bullet keeps `trace_id`.
- This plan: the R3 wire contract table's "Problem body" row gets "(member
  renamed `traceId` by R10.5)".
- All three drivers, including `asgi_app.py`: no code change is expected
  beyond the constant, because every driver renders through `render_problem`.

#### R10 sequencing (decided 2026-09-23): R5's evaluations before R4

R4 (decided 2026-09-22) makes `ProblemDetail`, `Page`, `CheckResult` and
`HealthReport` pydantic models in web. R5 evaluates `fastapi-problem`/`rfc9457`,
`fastapi-pagination`, `django-health-check` and `drf-standardized-errors`,
each of which brings its own model for one of those types. Doing R4 first
would build models R5 may replace, or bias R5 against adoption because the
models already exist.

**Order after R10:** R5's four evaluations, each as a probe with a written
verdict in R5, judged by R5's criteria plus rule 6. Then R4, for whichever
types no library takes, in R4's specified shape. Expected from the "Not in
R2.5" note: `rfc9457` conflicts with `about:blank` titles and the registry, so
`ProblemDetail` probably stays the kit's; `Page` and `HealthReport` are the
open ones. R5 and R4 are **not** part of the R10 handoff.

#### R10 handoff notes

- **Starting state.** R3 is in the working tree, staged and uncommitted, on
  top of `373d6bc`. Work on top of it. Do not unstage, reset or commit;
  committing is the owner's.
- **Order.** R10.1 → R10.2 → R10.3 → R10.4 → R10.5. Each lands with its
  tests and docs and a green run of the validation below before the next
  starts. R10.3 has a stop condition (its probe).
- **Rules that bite.**
  - Root `CLAUDE.md`: docstrings describe the contract only; comments
    explain a non-obvious *why*; fix or delete a comment when its code
    changes.
  - No compatibility re-exports or aliases for anything removed.
  - Public web symbols go in `rn_forge/web/__init__.py`, except
    extra-gated modules. `security.py` is extra-gated.
  - Tests mirror the source layout, and there is no `tests/__init__.py`.
  - Pyright strict on `src/`. `.importlinter`: web imports no framework.
- **No new dependencies.** Starlette arrives with FastAPI, and commons'
  `otel` extra already brings `opentelemetry-api`.
- **When done.** Mark each R10.x here as done with the date and any
  deviation. Update the status board's R10 entry and its "What is open" list.

#### R10 validation

The plan's validation block, plus:

- `uv run --group docs mkdocs build --strict` passes in `rn-forge-web`,
  `rn-forge-fastapi` and `rn-forge-django`;
- `rg "AccessLogMiddleware|request_log_fields|request\.complete|BodySizeLimitMiddleware|_send_413|trace_log_processor|rn_forge\.web\.asgi|rn_forge\.django\.middleware|SPAN_ID_KEY" packages README.md`
  finds nothing;
- `rg -i "correlation" README.md packages/*/README.md packages/*/docs`
  finds only `api-conventions.md` §1's "`X-Correlation-ID` is not read" line
  and commons' `enable_otel_correlation`;
- all three drivers pass every conformance case with no skips, including the
  `traceId`;
- `uv run pytest packages/rn-forge-commons` passes, including R10.4's
  unimportable-`opentelemetry` test.

## Effect on other plans

- **web-api-reuse-plan.** Phase 0 is kept. Phase 1 is withdrawn (R1). Phases 2,
  3 and 6 are unchanged: each wraps a library (`sse-starlette`, Starlette's
  `CORSMiddleware`) or has a recorded exemption. Phase 4 is kept: extension
  members are RFC 9457 §3.2, and `unmapped_exceptions` is a test helper. Phase 5
  (the correlation-ID validator) is **withdrawn by R3**, because the W3C
  propagator validates `traceparent`. R3's implementation marks it in that
  plan. Phase 6 was delivered as R2.5 B8. The Account Portal and
  IntelliBuild acceptances are parked; both applications are work in progress
  and adopt what ships.
- **web-library-plan §9.1.** The `Page<Item>` rule is withdrawn (R1). The
  `operationId` rule is kept as a default.
- **Status board.** A new document row, a new "What is open" entry, and two
  revised standing rules.
- **django-upgrade-plan.** The "`transfer.py` vs `django-import-export`"
  out-of-scope entries are resolved by R7.

## Order

R1, R2 and R2.5 are done. R3 is implemented (2026-09-23) and uncommitted. R7
followed R2.5 Part B, which is now done, so R7 is unblocked. R8's
convention items follow R7; its `orderBy` item is independent. R7 and R8 are
done. R9 is implemented (2026-09-23); it adds the
SQLAlchemy half without changing R7's or R8's wire. **Next, decided 2026-09-23:**
R10 (R10.1 to R10.5), then R5's evaluations, then R4 for the types no library
takes. R6 is on the backlog. All of it lands before the release tags:
nothing is released, so there are no compatibility shims (README).

## Validation

```bash
uv run pytest packages/rn-forge-web packages/rn-forge-fastapi packages/rn-forge-django
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run lint-imports
uv run --group docs mkdocs build --strict
```

Acceptance requires the following:

- both conformance drivers run every case with no skips;
- on both stacks, every operation in the generated document declares the
  problem+json responses;
- `rg "install_component_schemas|openapi_json|page_component_name|OPENAPI_VERSION" packages`
  finds nothing after R1;
- every rule in `api-conventions.md` names the standard it comes from, or says
  that none exists.
