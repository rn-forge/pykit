# Adoption checklist

For an application's own review. Each item is phrased so the answer is
checkable in the codebase rather than in someone's memory — the failure mode
this catches is an application that uses the primitives *almost* everywhere.

## Tracing

- [ ] `traceparent`/`tracestate` are the only trace headers read or written.
      `grep -rn "X-Correlation-ID"` returns nothing.
- [ ] The application configures a `TracerProvider` (or runs under
      `opentelemetry-instrument`); `rn_forge.web` never does.
- [ ] The log configuration includes `trace_log_processor`.
- [ ] No module defines its own request-id ContextVar or header constant.

## Errors

- [ ] **Every** error response goes through the registry. `grep -rn
      '"error"\|"detail":' ` finds no hand-built error body.
- [ ] Domain exceptions are registered on the application's registry instance
      at startup, in one place.
- [ ] The registry is an *instance*, not a mutated module-level default.
- [ ] No handler branches on `status_code` where a registration would do.
- [ ] A 5xx response body has been eyeballed in a real failure: it contains no
      exception message, no stack frame and no connection string.
- [ ] Validation errors come out as RFC 6901 pointers, including for a
      **nested** object — tested, not assumed.

## Concurrency

- [ ] Every mutating endpoint on a versioned resource either requires
      `If-Match` or has a written reason not to.
- [ ] Read responses for those resources carry an `ETag`.
- [ ] No endpoint returns 409 for a stale precondition.
- [ ] No endpoint accepts a version from the request *body* in place of the
      header.

## Pagination

- [ ] Every collection endpoint is cursor-paginated, or its specification says
      why it is page-number.
- [ ] **No `pageSize` validator rejects an over-large value.** On FastAPI:
      `grep -rn "le=" ` finds no `pageSize` constraint. This is the single
      easiest divergence to introduce.
- [ ] `nextPageToken` is `null`, not absent, on the last page.
- [ ] `totalSize` appears only where an endpoint opted in and pays for a count.
- [ ] No client code, and no test, parses or constructs a `pageToken`.

## Idempotency

- [ ] Every unsafe endpoint a client may retry accepts `Idempotency-Key`.
- [ ] The store's claim is atomic — `cache.add()`, or `ON CONFLICT DO
      NOTHING` — and **not** a `get` followed by a `set`.
- [ ] The cache backend is shared across worker processes. It is not
      `LocMemCache`.
- [ ] Replaying a key with a different body has been tested and returns 409.
- [ ] `scope` distinguishes endpoints (and tenants, where relevant).

## Health

- [ ] `/healthz` touches no dependency.
- [ ] `/readyz` names every external dependency the process needs, including
      the ones that are not configured yet — as `skipped`, not omitted.
- [ ] `required` contains exactly the dependencies whose loss should take the
      instance out of the load-balancer pool, and no more.
- [ ] `/readyz` has been exercised with a dependency actually down, and
      returned 503 rather than 500.

## Auth

- [ ] Missing or invalid credentials → 401 **with** a challenge.
- [ ] Insufficient scope → 403 **without** one.
- [ ] The 401 body is byte-identical whether the token was expired, badly
      signed or issued by an unknown key.
- [ ] Basic auth, if enabled, is documented as non-production and is off in the
      production configuration.

## Casing and schema

- [ ] The camelCase renderer/parser is wired globally, not per serializer.
- [ ] The emitted schema is OpenAPI 3.1.0.
- [ ] `ProblemDetail`, `Page`, `CheckResult` and `HealthReport` appear in
      `components/schemas` under exactly those names.
- [ ] `ProblemDetail` is present even though no route declares it as a response
      model — the explicit injection is in place.
- [ ] `operationId`s follow the shared convention.

## Conformance

- [ ] The conformance driver is present and every case in
      `rn_forge.web.conformance.CASES` passes.
- [ ] The driver asserts against the table, not against another stack's
      recorded output.
- [ ] The driver needs no redaction of its own beyond `redact`. If it does,
      that is the finding — report it upstream rather than working around it.
