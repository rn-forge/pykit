# API conventions

**Normative.** Every HTTP API built on this kit does all of the following
identically, on every framework. Where a rule has a conformance case, the case
id is given: a decision stated here and absent from
`rn_forge.web.conformance.CASES` is a decision that will drift, and the case is
what a framework package's driver actually asserts.

This page names no application and assumes no domain. It can be pasted into a
specification as a normative section as it stands.

---

## 1. Tracing

Every request is part of a trace, per **W3C Trace Context**.

- The request headers are **`traceparent`** and **`tracestate`**, read by the
  OpenTelemetry instrumentation. A malformed `traceparent` is never an error:
  it is discarded and the server starts a new trace.
  — `tracing.inbound-traceparent-continues-the-trace`,
  `tracing.malformed-traceparent-starts-a-new-trace`
- Every response carries **`traceresponse`**
  (`00-<trace-id>-<span-id>-<flags>`, W3C Trace Context Level 2) when a
  `TracerProvider` is configured.
- Every error body carries the current trace id as the `traceId`
  **extension member** (`null` when no span is recording). It is what makes a
  user-reported error findable in the trace backend and the logs.
  — `tracing.problem-body-carries-the-trace-id`
- Every structured log line emitted while handling the request carries
  `trace_id` and `span_id`.
- **`X-Correlation-ID` is not read and not sent.** There is no house
  correlation header; a caller that still sends one is ignored, and it is
  never echoed. — `tracing.house-header-is-not-echoed`

`rn_forge.web` never configures a `TracerProvider` or an exporter. The
application does, or runs under `opentelemetry-instrument`; see
`deployment.md`, "Logs and traces".

## 2. Errors

**Every** error response — including ones the framework raises before
application code runs — is an RFC 9457 problem.

- `Content-Type: application/problem+json`.
- Core members `type`, `title`, `status`, `detail`, `instance` are always
  present. Extension members are **flattened at the top level**, not nested.
- `type` is `about:blank` unless the application configures a type-URI base, in
  which case it is that base plus the slug.
- **`title` is the HTTP status phrase** (`"Unprocessable Content"`, not
  `"Validation Error"`) when `type` is `about:blank` — RFC 9457 §4.2.1's rule
  for that case. A configured `type_base` makes `type` a real URI, and only
  then is `title` the kit's own row title, since it is describing that URI.
- `instance` is the request path.
- **A 5xx `detail` never contains `str(exc)`.** It is a fixed generic string.
  The real reason goes to the log. — `problem.unregistered-is-500-without-detail`
- An exception with no registered row resolves to `internal-error`/500 by way
  of an MRO walk, so a subclass inherits its base's row.
  — `problem.registered-domain-conflict-is-409`
- A framework-raised 404 is a problem body too, not the framework's default
  page. — `problem.framework-404-is-a-problem-body`

### The standard slugs and status codes

| Slug | Status | Raised by |
| --- | --- | --- |
| `bad-request` | 400 | a malformed precondition, cursor or idempotency key |
| `unauthorized` | 401 | no credentials, or credentials that failed verification |
| `forbidden` | 403 | valid credentials lacking the required scope or role |
| `not-found` | 404 | a missing resource |
| `conflict` | 409 | a conflict with the resource's state; a duplicate idempotency key still in flight |
| `precondition-failed` | 412 | an `If-Match` that evaluated to false |
| `content-too-large` | 413 | a request body over the configured limit |
| `validation-error` | 422 | a request body that failed validation; an idempotency key reused with a different body |
| `precondition-required` | 428 | a required `If-Match` that was absent |
| `internal-error` | 500 | anything unregistered |
| `bad-gateway` | 502 | an upstream returned a problem |
| `too-many-requests` | 429 | `TooManyRequests`, raised by the application |
| `service-unavailable` | 503 | `ServiceUnavailable`, raised by the application |

`TooManyRequests` and `ServiceUnavailable` (RFC 6585 §4, RFC 9110 §15.6.4) each
take a `retry_after` in seconds, sent as the `Retry-After` header
(RFC 9110 §10.2.3) — `problem.too-many-requests-carries-retry-after`,
`problem.service-unavailable-carries-retry-after`. Enforcing a rate limit is
not pykit's job: it is a gateway's, or a maintained library's (`slowapi`,
`limits`); pykit only renders the response once the application decides to
send one.

### Validation errors

A `validation-error` body carries an `errors` extension: a list of
`{"pointer": ..., "detail": ...}` — RFC 9457 §3's own validation example,
`pointer` an **RFC 6901 JSON pointer**. Both frameworks produce the identical
list for the identical failure — DRF's `{field: [messages]}` and pydantic's
`loc`/`msg` list are both normalized, and nested serializers recurse rather
than being dropped. — `problem.validation-errors-are-rfc6901-pointers`

### Exception-carried extension members

A domain exception that wants extra members on its problem body implements
`HasProblemExtensions.problem_extensions()`. `ProblemRegistry.build` merges the
result beneath an explicit `extensions=` argument, and only for a row below
500 — a 5xx body says nothing about the cause, so nothing an exception carries
reaches the wire for one. An application does **not** get this by putting
arbitrary context on `AppException.error_data`: that dict routinely carries
credentials and internal identifiers and is never published automatically:
the application chooses what to expose by implementing the protocol.

### Proving the exception table is total

An unregistered domain exception silently resolves to `internal-error`/500,
which is easy to miss. `unmapped_exceptions(registry, *bases)` walks every
subclass of *bases* and returns the ones that resolve to the registry's
fallback, so a test or a readiness check can assert the list is empty.

## 3. Optimistic concurrency

An endpoint that mutates a versioned resource uses ETag preconditions.

- A read response carries `ETag: W/"<entity_id>:<version>"` — a **weak**
  validator. A strong one is refused: a version counter does not assert
  byte-for-byte equality.
- A write reads `If-Match`.
- Absent on a route that requires it → **428**. — `concurrency.absent-if-match-on-required-route-is-428`
- Present and stale → **412**, not 409. — `concurrency.stale-if-match-is-412-not-409`
- `If-Match: *` matches any current representation and passes. — `concurrency.star-if-match-passes`
- Present and unparseable → **400**, never a crash. — `concurrency.malformed-if-match-is-400`

Whether a given route *requires* a precondition is the application's choice,
made per route and stated in its specification.

`VersionConflict` (412) subclasses `WebError` directly, not `DomainConflict`
(409) — the two are different failures on the wire, and catching the 409 class
must not also catch a 412.

## 4. Pagination

Collection endpoints use **cursor pagination in Google AIP-158's spelling**.
Page-number pagination is legacy and is used only where an endpoint genuinely
needs a total and a jumpable page index; where it is used, the specification
says so and says why.

| Direction | Name | Meaning |
| --- | --- | --- |
| request | `pageSize` | requested page size |
| request | `pageToken` | opaque continuation token; absent means the first page |
| response | `items` | the page's elements |
| response | `nextPageToken` | opaque; `null` on the last page |
| response | `totalSize` | optional, **off by default** |

- **`pageSize` above the cap is clamped, never rejected.** A 422 here is a
  specification violation, and it is the single easiest divergence to
  introduce on FastAPI (`Query(le=...)` does exactly the wrong thing).
  — `pagination.oversized-page-size-is-clamped-not-rejected`
- **`pageToken` is opaque.** A client must not parse, construct or persist it
  beyond the next request. It is not signed — a cursor is opaque, not secret.
- **A malformed token is 400**, never 500. — `pagination.tampered-page-token-is-400`
- **`nextPageToken` is present and `null` on the last page**, not omitted, so a
  generated client's type does not change shape between pages.
  — `pagination.last-page-has-a-null-next-token`
- `totalSize` is opt-in per endpoint, because a keyset query cannot cheaply
  count. Do not enable it by default to ease a migration from page numbers.
- An `RFC 8288` `Link: <...>; rel="next"` header **may** be emitted alongside.
  It is additive; the body field is the contract.

**Sorting** follows Google AIP-132's spelling: `orderBy=displayName desc` — a
field name on the wire, optionally followed by `asc` (the default) or `desc`.

- **A list sorts by one field.** More than one comma-separated term is 400,
  never ignored, because the page token holds one sort value. AIP-132 allows
  several; this convention does not yet.
  — `pagination.order-by-two-fields-is-400`
- **An endpoint lists the fields it can sort by.** An unlisted or malformed
  term is 400, never ignored.
  — `pagination.order-by-unlisted-field-is-400`
- **The page token binds the order.** A token issued under one `orderBy` and
  presented under another is 400.
  — `pagination.order-by-descending-binds-the-token`,
  `pagination.token-under-a-different-order-by-is-400`
- **Ties are broken by the key.** A page is ordered by the `orderBy`
  field and then the primary key, and the token holds both, so the field need
  not be unique. It must not be null.

## 5. Idempotency

Unsafe endpoints that a client may retry accept an `Idempotency-Key` header.

- The specification says, per endpoint, whether the key is required or
  optional. Where required and absent → **400**.
- **The request body is hashed.** The same key with a different body is
  **422** — `draft-ietf-httpapi-idempotency-key-header-07` §2.7, not a
  silently-wrong replay. — `idempotency.same-key-different-body-is-422`
- **A duplicate while the original request is still in flight is 409.** The
  store signals this distinctly from first sight (`IdempotencyKeyInFlight`,
  not a silent re-execution) — same section of the draft.
- A replay returns the **stored status and body**, unchanged.
  — `idempotency.replay-returns-the-stored-response`
- The claim is atomic — a uniqueness constraint or an atomic set-if-absent, not
  a check-then-insert — so two concurrent first-sight requests do not both
  execute.
- Keys are namespaced by an opaque `scope`, so the same key on two endpoints,
  or in two tenants, does not collide.

**The flow is framework-free.** `run_idempotent`/`run_idempotent_async` hold
all of the above — safe-method bypass, claim, replay, complete, and the
409/422 from the store — over `IdempotencyStore`/`AsyncIdempotencyStore`. Both
stacks build on it: FastAPI's `idempotent` route decorator wraps the async
twin; Django's `@idempotent` wraps the sync one, its public signature
unchanged.

## 6. Health

Two endpoints, and they are not the same thing. The paths are platform-neutral
defaults, not a standard: no published spec names `/livez` or `/readyz`, but
Kubernetes deprecated `/healthz` in v1.16 in favour of them (kubernetes.io
"Kubernetes API health endpoints"), and no other host defines a default. See
`deployment.md` for how each host maps its own probes onto liveness and
readiness.

- **`/livez` — liveness.** Returns 200 unconditionally as long as the process
  is running. It touches no dependency. A liveness probe that checks the
  database restarts a healthy process when the database blips.
  `/healthz` is a deprecated alias of `/livez`, kept for hosts still probing
  it. — `health.liveness-is-200`
- **`/readyz` — readiness.** Runs a named check per dependency and returns
  `{"status": ..., "checks": {...}}`.
  - A check reports `pass`, `warn`, `fail` or **`skipped`**. `skipped` is for a
    check group that is not configured or not yet implemented, so its absence
    is visible rather than silent. This vocabulary comes from
    `draft-inadarei-api-health-check` (expired at -06, 2022); pykit keeps
    `checks` as an object keyed by name rather than the draft's
    `application/health+json` arrays.
  - A failing **required** check → **503**. — `health.required-failure-is-503`
  - A failing non-required check degrades the reported `status` but the
    endpoint stays **200**. — `health.optional-failure-is-200-degraded`
  - A `warn` never changes the HTTP status.
  - A check that raises is reported as a failure. `/readyz` never 500s: a
    readiness endpoint that 500s tells a load balancer nothing.
  - Each check runs with a 2-second timeout by default — below every host's
    probe timeout — and a check still running at the timeout is reported
    `fail` with `"timed out after Ns"`.
  - The response is `application/json`, **not** problem+json, even at 503 — a
    readiness report is the endpoint's normal representation and the 503 is its
    verdict, not an error.
  - The HTTP status is not repeated in the body.
- Every host judges a probe by its **status code and response time only**, never
  the body, so neither endpoint ever redirects (a trailing-slash 301 would mark
  the instance unhealthy).

## 7. Authentication and authorization

- **No credentials, or credentials that fail verification → 401**, with a
  `WWW-Authenticate` challenge. — `auth.no-credentials-is-401-with-a-challenge`
- **Valid credentials lacking the required scope or role → 403**, with **no**
  challenge. A challenge here tells a browser to re-prompt for credentials that
  were already correct. — `auth.insufficient-scope-is-403-without-a-challenge`
- The challenge follows RFC 6750 §3 for Bearer and RFC 7617 for Basic, and is
  constructed rather than hand-written.
- **The 401 body never says why verification failed.** Expired, bad signature
  and unknown `kid` are indistinguishable on the wire; the reason goes to the
  log.
- The verified caller is a `Principal`: `subject` (required), plus optional
  `issuer`, `scopes`, `roles`, `tenant`, raw `claims` and `mechanism`. Scopes
  and roles are separate sets and neither is encoded as the other.
- Basic auth, where offered, is documented as local-development and
  simple-internal-deployment only, and emits the identical challenge.

## 8. Field casing

**camelCase on the wire, `snake_case` in Python.** — `casing.response-bodies-are-camel-case`

This is the Google JSON Style Guide's rule, Microsoft's REST API Guidelines'
rule, and what proto3's JSON mapping produces — which is also why AIP-158's
`page_size` appears on the wire as `pageSize`. It is what every TypeScript
client and every popular UI framework's HTTP layer expects, and picking either
casing is far better than letting it vary per application.

Three exemptions, and only three:

- **RFC 9457's core members** (`type`, `title`, `status`, `detail`, `instance`)
  are single lowercase words and are unaffected. Problem *extensions* follow
  the rule.
- **Headers.** HTTP field names are case-insensitive and hyphenated.
- **RFC 9264 linkset member names** (`anchor`, `service-desc`, `service-doc`,
  `status`, `href`) in the §14 api-catalog body — they are the RFC's own
  vocabulary, verbatim.

**Both framework packages enforce this in code, not in a recipe** — a renderer
and a parser wired through the framework's own settings. A convention that only
a guide enforces is a convention that holds until the first hurried endpoint.

## 9. OpenAPI

The generated client is the real interface, so the schema is part of the
contract and not a by-product. But **two compliant OpenAPI documents
describing the same JSON are not required to be the same document** — OpenAPI
*describes* an API; it does not *prescribe* one. What this kit holds identical
across stacks is narrower than "the document": wire behaviour, always; a
generated client's method names and declared error types; nothing about a
generated client's model, page or enum type names.

| Layer | Identical across stacks? |
| --- | --- |
| Wire behaviour: status codes, headers, body shapes | **Yes, required** |
| Schema semantics: which JSON a schema accepts | **Yes**, when the application declares the same model |
| Document text: component names, `operationId`s, nullability spelling, enum hoisting | **No, not a goal**, except `operationId` (below) |

- Both stacks emit **OpenAPI 3.1.0** (JSON Schema 2020-12) — each framework's
  own default; nothing pins it.
- The shared **non-generic** shapes are named identically in
  `components/schemas`: **`ProblemDetail`**, **`CheckResult`**,
  **`HealthReport`**. A handler that builds an error body by hand is invisible to
  schema collection, so each framework package injects `ProblemDetail`
  explicitly — without it a generated TypeScript client has no error type at all.
- **The paginated envelope's component name is not held identical.**
  Left to themselves the two stacks disagree — pydantic mangles the type
  parameters into `Page_OrderOut_`, drf-spectacular emits
  `PaginatedOrderOutList` — and neither is renamed. A resource's wire *model*
  (`OrderOut`) still carries the same name on both stacks; only its page
  wrapper's name differs, and a generated client's page type was never going
  to be identical across two different generators regardless.
- **One `operationId` convention across both stacks**, `<resource><Verb>` in
  lowerCamelCase: `ordersList`, `ordersCreate`, `ordersGet`, `ordersUpdate` for
  `PUT`, `ordersPartialUpdate` for `PATCH`, `ordersDelete`. `PUT` and `PATCH` get
  distinct verbs so a resource serving both never produces a duplicate
  `operationId`. This is the one piece of document text held identical, because
  it is what a generated client's method names are made from — read from
  `rn_forge.web.openapi.operation_id`, which both framework packages call
  rather than deriving names themselves.
- **An operation outside those six is a custom method, spelled
  [AIP-136](https://google.aip.dev/136)-style as `:action` on the resource it
  acts on**, and named `<resource><Action>`: `POST /orders/{orderId}:cancel` →
  `ordersCancel`, `POST /orders:batchCreate` → `ordersBatchCreate`. The colon is
  what makes the name derivable. Spelled as a plain path segment, nothing
  distinguishes an action from a sub-collection — `POST /orders/{orderId}/cancel`
  and `POST /orders/{orderId}/items` have the same shape — so that spelling
  yields a mechanical `cancelCreate` and needs an explicit override
  (`operation_id=` on FastAPI, `@extend_schema(operation_id=...)` on DRF).
  On DRF the colon spelling is served by `rn_forge.django.drf.routers.CustomMethodRouter`;
  stock routers cannot express it.
- `operationId` **must be unique across the document**; OpenAPI requires it, and
  a generator that meets a duplicate produces a broken client. drf-spectacular
  warns and appends a numeral; FastAPI does neither, so on that stack a
  collision is silent. Two routes ending in the same literal segment
  (`/orders/{id}/items` and `/invoices/{id}/items`) are the case to watch.
- **Every operation that can return an error declares the problem responses it
  can produce, by status** — an `application/problem+json` response
  referencing `ProblemDetail`, for each status the application's registry can
  render plus 500. This is an *accuracy* repair, not a naming convention: the
  document must describe what the service actually returns, and neither
  framework's own schema collection sees a hand-built error body.
  `FastApiApp.openapi()` does it on FastAPI by overriding `openapi()` and
  repairing the cached document; `rn_forge.django.drf.openapi`'s
  `problem_responses_hook` does the identical thing through drf-spectacular's
  postprocessing hooks.

### What a generated client shares across stacks, and what it does not

| Generated client | Same on both stacks? |
| --- | --- |
| Method names (`operationId`) | **Yes** |
| Declared error responses | **Yes** |
| Model, page and enum type names | No |
| Model structure (`-Input`/`-Output` split vs. `readOnly`/`writeOnly`) | No |
| Nullable field types | Generator-dependent |
| Path-parameter names | Only when the application spells them the same |

Forcing textual identity beyond this means post-processing each generator's
output to normalize away its own idioms, which buys nothing until an API must
be re-implemented on another stack behind a client that cannot change. If that
need arises, the standard way to get it is spec-first — one owned OpenAPI
document, each implementation contract-tested against it — not generator
post-processing.

## 10. HTTP methods and status codes

Unremarkable, and worth stating so it does not vary:

| Situation | Status |
| --- | --- |
| A successful read | 200 |
| A successful create | 201, with `Location` |
| A successful update | 200 with the representation, or 204 with no body |
| A successful delete | 204 |
| An accepted asynchronous operation | 202 |

`PUT` replaces; `PATCH` is RFC 7396 JSON Merge Patch (`Content-Type:
application/merge-patch+json`), and there is no field-mask parameter (AIP-134 is
not adopted). A `DELETE` on an already-absent resource is
404, not 204 — an idempotent *outcome* is not the same as a silent one, and a
client that deleted something twice usually wants to know.

## 11. Request body size

RFC 9110 §15.5.14: a body over the configured limit is **413** —
`problem.content-too-large-is-413`.

- **FastAPI.** `AppConfig.max_body_bytes` (default 1 MiB; `None` disables it)
  installs a pure-ASGI `BodySizeLimitMiddleware`, ahead of the router: a
  declared `Content-Length` over the limit is rejected before the application
  runs, and a streamed body without one is cut off as it arrives. Uvicorn
  itself sets no limit.
- **Django.** Django's own `DATA_UPLOAD_MAX_MEMORY_SIZE` maps to 413 through
  `problem_registry()`, instead of Django's default 400. It guards
  `request.body` and form/multipart parsing (`request.POST`), but **not** a
  raw stream read — DRF's `JSONParser` reads via `HttpRequest.read()`, which
  the check does not cover. A view that must enforce the limit on a JSON body
  touches `request.body` itself before the parser runs.
- Each host's own front end has its own cap too (see `deployment.md`); this
  limit is the application's and should sit at or below it.

## 12. Deprecation and Sunset

An endpoint scheduled for removal announces it on every response.

- `Deprecation` (RFC 9745) carries the date it became deprecated, as a
  structured-field date: `@<epoch-seconds>`.
- `Sunset` (RFC 8594) carries the date it stops being served, as an HTTP-date,
  when one is scheduled.
- `Link: <...>; rel="deprecation"` names the deprecation notice, when there is
  one. — `deprecation.endpoint-carries-rfc9745-headers`
- **FastAPI** pairs the `deprecated(...)` dependency with the route's own
  `deprecated=True`, so the OpenAPI document marks the operation deprecated
  too.
- **Django** pairs the `@deprecated(...)` view decorator with
  drf-spectacular's `@extend_schema(deprecated=True)` for the same reason.

## 13. Conditional GET

A `GET`/`HEAD` on a resource that carries an `ETag` honors an inbound
`If-None-Match` (RFC 9110 §13.1.2, §15.4.5).

- A weak match — `*`, or any validator in a comma-separated list, compared
  ignoring a leading `W/` on either side — answers **304**, with no body and
  the `ETag` repeated. —
  `concurrency.if-none-match-matches-is-304`
- A miss is an ordinary 200 carrying the current representation and `ETag`. —
  `concurrency.if-none-match-mismatch-is-200`
- **Django** gets this from its own `ConditionalGetMiddleware`, which does
  weak `If-None-Match` comparison against any response carrying an `ETag` — no
  kit code is involved.

## 14. Service discovery

- The OpenAPI document and the docs UI stay each framework's own defaults:
  `/openapi.json` and `/docs`. Document text is not held identical across
  stacks (§9); only the *paths* are, so a client always knows where to look.
- **`/.well-known/api-catalog`** (RFC 9727) is an RFC 9264 linkset,
  `application/linkset+json`, naming the OpenAPI document (`service-desc`,
  RFC 8631), the docs UI (`service-doc`) and readiness (`status`).
  — `discovery.api-catalog-is-an-rfc9264-linkset`
- **FastAPI** serves it by default (`AppConfig.api_catalog: bool = True`),
  answering `GET` and `HEAD`, excluded from the OpenAPI document itself.
- **Django** serves it, plus the OpenAPI document and docs UI, from
  `rn_forge.django.drf.openapi.openapi_urlpatterns()` (the `openapi` extra).

## 15. Security headers

The OWASP REST Security Cheat Sheet's response headers, on every response:
`Cache-Control: no-store`, `Content-Security-Policy: frame-ancestors 'none'`,
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`. — `security.owasp-headers-are-present`

- **`Strict-Transport-Security` is excluded from the default preset** and is
  opt-in (`hsts`) on both stacks: sending it over plain HTTP tells a browser
  to refuse a future connection that isn't HTTPS, which is wrong unless this
  service terminates TLS itself rather than behind a front end that already
  sets it (see `deployment.md`).
- **A route's own header wins.** Both stacks apply the preset with `setdefault`
  semantics.
- **web** (the `security` extra, wrapping the `secure` library): `rn_forge.web.security.API_SECURITY_HEADERS`
  and a pure-ASGI `SecurityHeadersMiddleware`.
- **FastAPI** installs it by default (`AppConfig.security_headers: bool = True`, `AppConfig.hsts: bool = False`).
- **Django**: `rn_forge.django.security.SECURITY_SETTINGS` configures Django's own
  `SecurityMiddleware` and `XFrameOptionsMiddleware` for three of the five headers plus HSTS;
  `rn_forge.django.security.SecurityHeadersMiddleware` adds the two Django has no setting for
  (`Cache-Control`, the CSP directive).

## 16. CORS

**The application owns its CORS policy** — which origins, whether there is
one at all, and whether credentials are allowed. Neither stack picks a
default.

- **`EXPOSED_HEADERS`** is the one thing only this kit can supply: a browser
  cannot read `ETag`, `Link`, `Location`, `Retry-After`, `Deprecation` or
  `Sunset` unless they are named in `Access-Control-Expose-Headers`,
  comma-joined in that order. `traceresponse` is not in this list — the
  OpenTelemetry response propagator exposes it itself.
  — `cors.exposed-headers-are-comma-joined`
- **FastAPI**: `AppConfig.cors: CorsPolicy | None = None`, over Starlette's
  own `CORSMiddleware`. `None` installs nothing.
- **Django**: `rn_forge.django.cors.cors_settings(allowed_origins)` (the
  `cors` extra, `django-cors-headers`) sets `CORS_ALLOWED_ORIGINS` and
  `CORS_EXPOSE_HEADERS`; the application adds `corsheaders` to
  `INSTALLED_APPS` and `CorsMiddleware` to `MIDDLEWARE` itself.
- `CorsPolicy(allow_credentials=True, allow_origins=("*",))` raises: browsers
  reject that combination outright.

---

## 17. Tabular transfer and bulk operations

`rn_forge.web.transfer` holds the wire shapes; the framework packages hold the
handlers. Every rule names its source and its conformance case.

**Export.** `GET /orders` with `Accept: text/csv` or
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` returns the
same filtered collection as the JSON list, as a file. This is proactive
negotiation (RFC 9110 §12); a wildcard never selects a tabular format.
`?format=csv|xlsx` is the fallback for a plain link and wins over `Accept`. The
export is not paginated. A result above the configured cap is a `422` problem
whose `detail` names the cap. The response carries
`Content-Disposition: attachment` with a quoted ASCII `filename` and a UTF-8
`filename*` (RFC 6266, RFC 8187). —
`transfer.export-is-negotiated-from-accept`,
`transfer.export-format-param-is-the-fallback`,
`transfer.export-filename-carries-rfc8187-encoding`,
`transfer.export-over-the-cap-is-422`

**Import.** `POST /orders:import` is a custom method (AIP-136, §9), a
`multipart/form-data` upload with a `file` part. `?validateOnly=true` runs the
whole import and persists nothing (AIP-163). Success is `200` with
`{created, updated, skipped, validateOnly}`. Any row error fails the whole
import: `422` `application/problem+json` with
`errors[].pointer = "/rows/12/Quantity"` (RFC 9457 §3, §2's `errors`), and
nothing persisted. — `transfer.import-report-counts-and-validate-only`,
`transfer.import-row-errors-are-422-pointers`

**Import template.** `GET /orders:importTemplate`, negotiated like an export;
`?prefill=true` adds the current filtered rows (AIP-136).

**Bulk create.** `POST /orders:batchCreate` with `{"requests": [...]}` is all or
nothing (AIP-233) and answers `200 {"orders": [...]}`. A per-item validation or
authorization failure is one `422` or `403` problem with
`errors[].pointer = "/requests/3/..."` (RFC 9457). —
`transfer.batch-create-item-failure-is-422-pointer`,
`transfer.failed-batch-create-persists-nothing`,
`transfer.batch-create-returns-the-created-resources`

**Bulk delete.** `POST /orders:batchDelete` with `{"ids": [...]}` is all or
nothing and answers `204` (AIP-235); an id that does not exist fails the whole
batch with `404`. — `transfer.batch-delete-with-unknown-id-is-404`,
`transfer.failed-batch-delete-deletes-nothing`, `transfer.batch-delete-is-204`

**Large files (not built).** When a consumer needs it, the pattern is
`POST /imports` returning `202` with `Location`, then polling the operation
(AIP-151, §19), with an `Idempotency-Key` (§5,
`draft-ietf-httpapi-idempotency-key-header`).

---

## 18. Timestamps and standard fields

- **Timestamps are RFC 3339 in UTC with a `Z` suffix**, per AIP-142 (which
  points to RFC 3339): `2026-09-23T14:05:00Z`. Property names end in `Time`
  for an instant and `Date` for a calendar date. On Django this needs
  `USE_TZ = True` and `TIME_ZONE = "UTC"`, which DRF's `DateTimeField` renders
  with the `Z`. — `timestamps.rfc-3339-utc-with-z`
- **The audit fields are `createTime`, `updateTime`, `createdBy` and
  `updatedBy`** (AIP-148 for the first two; `createdBy`/`updatedBy` have no
  AIP equivalent). `etag` and `requestId` are not fields: RFC 9110 headers
  (§3) and the `Idempotency-Key` header (§5) govern.
- Errors are RFC 9457 problems, never `google.rpc.Status`.

## 19. Versioning, compatibility and operations

Where no RFC or IETF draft applies, these conventions follow Google's AIPs for
naming and shape. Nothing else from Google's stack is used, and an AIP an RFC
already governs, or one that assumes gRPC, is not adopted (last bullet).

- **Versioning** (AIP-185): a major version in the path, `/v1`, and no minor
  versions on the wire. A version is retired with the `Deprecation` and
  `Sunset` headers of §12.
- **Breaking changes** (AIP-180) are the review rule: removing or renaming a
  field, path or parameter, narrowing a type, or adding a required request
  field. Enforce it with an OpenAPI diff (`oasdiff`) in CI of the consuming
  repository; the kit does not run it.
- **`validateOnly`** (AIP-163): a mutating method a UI previews accepts a
  `validateOnly=true` query parameter, runs validation and every check the real
  call would, and has no side effects. §17's import uses it.
- **Batch methods** are spelled `:batchCreate`, `:batchGet` and `:batchUpdate`
  (AIP-233, 231, 234). `:batchGet` and `:batchUpdate` are specified here and
  built when a consumer needs them.
- **Long-running operations** (AIP-151): the call returns `202` with a
  `Location` naming an operation resource
  `{name, done, metadata, error | response}`; `error` is an RFC 9457 problem.
  `rn_forge.web.Operation` is that body: unfinished has neither outcome,
  finished has exactly one. Storing operations and running the work are the
  application's. — `operations.start-is-202-with-location`,
  `operations.finished-carries-its-response`, `operations.failed-carries-a-problem`
- **Custom-method paths** (`:cancel`, `:import`, the batch spellings) put a
  colon in the last path segment. It is valid in a URI, but a gateway or router
  that treats `:` as a parameter marker must be configured to pass it through.
- **Not adopted:** AIP-160 `filter` expressions (per-field query parameters
  are the mechanism), AIP-122 resource names (ids stay ids), AIP-157 `readMask`
  and AIP-164 soft delete (deferred).

## Conformance

`rn_forge.web.conformance.CASES` is the executable form of this page. Each
framework package ships a ~15-line driver that builds a small application over
these primitives, runs every case through its own stack, and asserts against
the table — never against the other stack's output, because two stacks
agreeing on the wrong thing is not conformance.

A rule stated here with no case in that table is treated as unfinished.
