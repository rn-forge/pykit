# Standards re-baseline plan

**Status:** planned, 2026-09-21, from an owner-requested review of `rn-forge-web`,
`rn-forge-fastapi` and `rn-forge-django`. It changes a premise the web, fastapi and
django plans were written under, so it takes precedence over them where they
disagree: [web-library-plan §9.1](web-library-plan.md), and
[web-api-reuse-plan](web-api-reuse-plan.md) Phases 1 and 5.

**R1 and R2 implemented, 2026-09-21. R2.5 Part A implemented, 2026-09-22;
Part B (the standard service surface) is specified and ready.** R3, R4, R5
and R6 remain open — gated on the owner (R3, R4, R6) or waiting on their
outcomes (R5). **R7 (tabular transfer and bulk operations, adopting
`tablib` and `django-import-export`) is ready to implement**: dependencies
approved and the DRF router probed, 2026-09-22; three open questions are
listed at its end. **R8 (AIP adoption where no RFC applies) planned
2026-09-22.** **R9 (SQLAlchemy and `tablib` across both stacks) is open for
ideation.** Full validation
block below is green; see "What is open" on the [status board](README.md) for
detail.

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
  converters, and again on the DRF side.
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

### R2.5: shared logic in `web`, and the standard service surface

**Part A done, 2026-09-22. Part B is specified below and ready to implement.**

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

#### Part B: the standard service surface (to implement)

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

#### Not in R2.5

- **The exception classes stay.** `rfc9457` (0.4.1, 2026-02; the core of
  `fastapi-problem`) is the only maintained framework-free library. It puts
  status and type on the class and derives `type` from the class name, which
  conflicts with the registry and with R2.3's `about:blank`. Evaluate it in
  R5.
- **`/metrics`** goes with R3. Once OpenTelemetry is adopted, metrics come
  from its SDK (OTLP push, or `opentelemetry-exporter-prometheus` for pull).
  pykit does not hand-roll a `/metrics` endpoint.
- **`traceparent` and the correlation header** stay in R3. B9's field names
  already follow OpenTelemetry.
- **RFC 9116 `security.txt`** is not in scope. It belongs to a public web
  property, not to each microservice.
- **`RemoteProblem` stays** as the documented gateway seam, although nothing
  in the kit raises it.
- **FastAPI's `ProblemDetail` component** still comes from the pydantic
  mirror; R4 picks the single source.

#### Handoff notes

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

### R3: correlation, **gated** (owner decision)

| Option | Wire | Cost |
| --- | --- | --- |
| **a. W3C Trace Context through OpenTelemetry instrumentation** (recommended) | `traceparent` in and out; the problem body carries the trace id | OTel instrumentation on both stacks; the log processor reads the trace id |
| b. Keep `X-Correlation-ID`, adopting `asgi-correlation-id` in `rn-forge-fastapi` | unchanged | The problem handlers read its ContextVar instead of `rn_forge.web.context`; Django keeps web's middleware |
| c. Status quo | unchanged | none; it stays a house header |

Option b is a reasonable interim step toward a. Web-api-reuse Phase 5's
validator stays whichever option is chosen, since a caller-supplied value must
still be validated.

### R4: one model per stack, **gated**

Choose one:

- **a.** `rn-forge-web` keeps framework-free builders that return plain dict
  bodies. The FastAPI pydantic models describe the schema only, with no
  `from_wire`/`to_wire`.
- **b.** `rn-forge-web` defines the shared types as pydantic models (pydantic
  is not a web framework; commons already has a `pydantic` extra). FastAPI uses
  them directly, and drf-spectacular reads them through its pydantic support.
  **Verify that support before choosing b.**

Recommended: b if the verification holds, otherwise a.

### R5: re-run the withdrawn library evaluations

Re-run every evaluation rejected on wire-ownership grounds. A library is
adopted when it implements the standard, can be configured to
`api-conventions.md`, and is maintained. Otherwise the exemption is written into
the module docstring, as principle 1 requires.

- FastAPI: `fastapi-problem` and other RFC 9457 handlers on PyPI;
  `fastapi-pagination` (cursor mode, with AIP-158 names); `asgi-correlation-id`
  (with R3).
- Django: `drf-standardized-errors` (only if configurable to RFC 9457);
  `django-health-check`.

This runs after R3 and R4, because their outcomes change what a candidate must
fit.

### R6: `rn-forge-django` scope, **gated**

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

The spec above stands as written unless the owner changes one of these before
implementation.

1. **Import failure default.** The spec is all or nothing, with an opt-in for
   partial saves (`import_rollback_on_validation_errors = False`).
   `ew-loop-api` does partial saves today. The owner has not confirmed which
   should be the default.
2. **Status for an export over the row cap.** The spec says "a problem response
   naming the cap" and leaves the status open. Recommended: `422`, with
   `about:blank` and the cap in `detail`. `413` is for request content, not
   response size (RFC 9110 §15.5.14). Settle it in step 2, when the web
   conformance case is written.
3. **How much the transfer layer is shared across stacks** (R7 ships two native
   idioms): see R9.

### R9: SQLAlchemy and tablib across both stacks, **to ideate**

**Status:** open, 2026-09-22. The owner will work through this in a separate
session. It is not a spec yet. R7 is deliberately shaped so that R9 can replace
its FastAPI "application-owned" rows without changing the wire.

**Questions to settle:**

1. **Unpark `rn-forge-sqlalchemy`?** Its trigger is currently "planned with
   intellibuild's spec" (status board, "Parked"). R7 gives it a second reason:
   the FastAPI persistence half of transfer. The contents already recorded in
   the web plan's "Deferred" section are: declarative base, naming convention,
   `TimestampMixin`, the optimistic `update`/`StaleVersionError` helper, and a
   SQLAlchemy `IdempotencyStore`.
2. **One upsert contract, two ORMs.** The semantics are: natural keys, update
   only listed fields, skip unchanged rows, created/updated/skipped counts, and
   roll back under `validateOnly`. The native mechanisms are:
   - Django: `bulk_create(update_conflicts=True, unique_fields=…, update_fields=…)`
     (Django ≥ 4.1). `django-import-export` uses per-row instance loading
     instead;
   - SQLAlchemy: `insert().on_conflict_do_update(…)` in the PostgreSQL and
     SQLite dialects, with `RETURNING (xmax = 0)` for the counts.

   Decide whether both stacks expose the same small contract, and whether
   `django-import-export` stays the Django engine or becomes a thin layer over
   the native upsert.
3. **One column spec, or two native idioms?** R7 has the Django `Resource`
   fields and FastAPI's pydantic aliases plus `computed_field`s. A single
   framework-free declarative spec over `tablib` could feed both. It interacts
   with R4: if web's shared types become pydantic, a pydantic-based spec is the
   natural candidate. Weigh this against the premise's "no layer in place of the
   framework".
4. **Async.** FastAPI consumers are async; intellibuild is fully async.
   `tablib` and openpyxl are synchronous and CPU-bound, so decide where
   `run_in_threadpool` sits (in `read_rows`, or in the caller) and whether large
   exports stream from an async session.
5. **Keyset pagination and `orderBy` on SQLAlchemy** (R8, AIP-132). Candidates
   are `fastapi-pagination`'s cursor mode (already in R5) and `sqlakeyset`.
   The page token must encode the order on both stacks.
6. **Audit fields**, tied to R8's AIP-148 decision: the `createdBy`/`updatedBy`
   and `createTime`/`updateTime` names and how each ORM populates them.
   Today `AuditFieldsViewMixin` is DRF-only.
7. **Library re-checks** that feed the answers: `fastapi-import-export`, now
   in R5; whether `tablib`'s `Dataset` is enough as the in-memory contract, or
   whether large files need a streaming reader (openpyxl `read_only`);
   `sqlakeyset`.

**Inputs:**

- R7's requirements table, from `ew-loop-api`;
- R7's FastAPI mapping table;
- the web plan's "Deferred" section;
- `fastapi-library-plan.md` §"Things deliberately NOT in this package";
- intellibuild as the SQLAlchemy consumer, which is parked as an acceptance
  consumer while it is in progress.

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

## Effect on other plans

- **web-api-reuse-plan.** Phase 0 is kept. Phase 1 is withdrawn (R1). Phases 2,
  3 and 6 are unchanged: each wraps a library (`sse-starlette`, Starlette's
  `CORSMiddleware`) or has a recorded exemption. Phase 4 is kept: extension
  members are RFC 9457 §3.2, and `unmapped_exceptions` is a test helper. Phase 5
  is kept, and its header question moves to R3. The Account Portal and
  IntelliBuild acceptances are parked; both applications are work in progress
  and adopt what ships.
- **web-library-plan §9.1.** The `Page<Item>` rule is withdrawn (R1). The
  `operationId` rule is kept as a default.
- **Status board.** A new document row, a new "What is open" entry, and two
  revised standing rules.
- **django-upgrade-plan.** The "`transfer.py` vs `django-import-export`"
  out-of-scope entries are resolved by R7.

## Order

R1 and R2 need no decision and are independent; do them first. R3, R4 and R6
wait on the owner. R5 follows R3 and R4. R7 follows R2.5 Part B. R8's
convention items follow R7; its `orderBy` item is independent. R9 is ideation;
its outcome may reshape R7's FastAPI half and R8's `orderBy` on SQLAlchemy, so
settle it before implementing those two parts. All of it lands before the release tags:
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
