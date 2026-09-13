# API conventions

**Normative.** Every HTTP API built on this kit does all of the following
identically, on every framework. Where a rule has a conformance case, the case
id is given: a decision stated here and absent from
`rn_forge.web.conformance.CASES` is a decision that will drift, and the case is
what a framework package's driver actually asserts.

This page names no application and assumes no domain. It can be pasted into a
specification as a normative section as it stands.

---

## 1. Correlation

Every request carries a correlation ID, and every response returns one.

- The header is **`X-Correlation-ID`**, in both directions.
- A caller-supplied ID is **never replaced**. — `correlation.inbound-id-is-echoed-never-replaced`
- When the caller supplies none, the server generates one (a UUID4 hex string),
  binds it for the request and stamps it on the response.
  — `correlation.generated-id-reaches-the-problem-body`
- Every error body carries it as the `correlation_id` **extension member**. It
  is what makes a user-reported error id findable in the logs, and it is the
  one documented exception to the casing rule in §7.
- Every structured log line emitted while handling the request carries it.

A deployment fronted by infrastructure that stamps a different header
configures the header name; it does not add a second one.

## 2. Errors

**Every** error response — including ones the framework raises before
application code runs — is an RFC 9457 problem.

- `Content-Type: application/problem+json`.
- Core members `type`, `title`, `status`, `detail`, `instance` are always
  present. Extension members are **flattened at the top level**, not nested.
- `type` is `about:blank` unless the application configures a type-URI base, in
  which case it is that base plus the slug.
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
| `conflict` | 409 | a conflict with the resource's state; idempotency-key reuse |
| `precondition-failed` | 412 | an `If-Match` that evaluated to false |
| `validation-error` | 422 | a request body that failed validation |
| `precondition-required` | 428 | a required `If-Match` that was absent |
| `internal-error` | 500 | anything unregistered |
| `bad-gateway` | 502 | an upstream returned a problem |

### Validation errors

A `validation-error` body carries an `errors` extension: a list of
`{"pointer": ..., "message": ...}`, where `pointer` is an **RFC 6901 JSON
pointer**. Both frameworks produce the identical list for the identical
failure — DRF's `{field: [messages]}` and pydantic's `loc`/`msg` list are both
normalized, and nested serializers recurse rather than being dropped.
— `problem.validation-errors-are-rfc6901-pointers`

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

## 5. Idempotency

Unsafe endpoints that a client may retry accept an `Idempotency-Key` header.

- The specification says, per endpoint, whether the key is required or
  optional. Where required and absent → **400**.
- **The request body is hashed.** The same key with a different body is
  **409**, not a silently-wrong replay.
  — `idempotency.same-key-different-body-is-409`
- A replay returns the **stored status and body**, unchanged.
  — `idempotency.replay-returns-the-stored-response`
- The claim is atomic — a uniqueness constraint or an atomic set-if-absent, not
  a check-then-insert — so two concurrent first-sight requests do not both
  execute.
- Keys are namespaced by an opaque `scope`, so the same key on two endpoints,
  or in two tenants, does not collide.

## 6. Health

Two endpoints, and they are not the same thing.

- **`/healthz` — liveness.** Returns 200 unconditionally as long as the process
  is running. It touches no dependency. A liveness probe that checks the
  database restarts a healthy process when the database blips.
- **`/readyz` — readiness.** Runs a named check per dependency and returns
  `{"status": ..., "checks": {...}}`.
  - A check reports `pass`, `warn`, `fail` or **`skipped`**. `skipped` is for a
    check group that is not configured or not yet implemented, so its absence
    is visible rather than silent.
  - A failing **required** check → **503**. — `health.required-failure-is-503`
  - A failing non-required check degrades the reported `status` but the
    endpoint stays **200**. — `health.optional-failure-is-200-degraded`
  - A `warn` never changes the HTTP status.
  - A check that raises is reported as a failure. `/readyz` never 500s: a
    readiness endpoint that 500s tells a load balancer nothing.
  - The response is `application/json`, **not** problem+json, even at 503 — a
    readiness report is the endpoint's normal representation and the 503 is its
    verdict, not an error.
  - The HTTP status is not repeated in the body.

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
- **`correlation_id`** as a problem extension, which matches the log field name
  it exists to be joined against.
- **Headers.** HTTP field names are case-insensitive and hyphenated.

**Both framework packages enforce this in code, not in a recipe** — a renderer
and a parser wired through the framework's own settings. A convention that only
a guide enforces is a convention that holds until the first hurried endpoint.

## 9. OpenAPI

The generated client is the real interface, so the schema is part of the
contract and not a by-product.

- Both stacks emit **OpenAPI 3.1.0** (JSON Schema 2020-12).
- The shared shapes are named identically in `components/schemas`:
  **`ProblemDetail`**, **`Page`**, **`CheckResult`**, **`HealthReport`**. A
  handler that builds an error body by hand is invisible to schema collection,
  so each framework package injects `ProblemDetail` explicitly — without it a
  generated TypeScript client has no error type at all.
- **One `operationId` convention across both stacks.** `operationId` is what a
  generator turns into a client method name, so two stacks that differ there
  produce two different client call sites for the same endpoint even when every
  byte of JSON matches. The convention is `<resource><Verb>` in lowerCamelCase
  (`ordersList`, `ordersCreate`, `ordersGet`, `ordersUpdate` for `PUT`,
  `ordersPartialUpdate` for `PATCH`, `ordersDelete`), and each package
  implements it. `PUT` and `PATCH` get distinct verbs so a resource serving
  both never produces a duplicate `operationId`.
- Every operation that can return an error declares the problem responses it
  can produce, by status.

## 10. HTTP methods and status codes

Unremarkable, and worth stating so it does not vary:

| Situation | Status |
| --- | --- |
| A successful read | 200 |
| A successful create | 201, with `Location` |
| A successful update | 200 with the representation, or 204 with no body |
| A successful delete | 204 |
| An accepted asynchronous operation | 202 |

`PUT` replaces, `PATCH` merges. A `DELETE` on an already-absent resource is
404, not 204 — an idempotent *outcome* is not the same as a silent one, and a
client that deleted something twice usually wants to know.

---

## Conformance

`rn_forge.web.conformance.CASES` is the executable form of this page. Each
framework package ships a ~15-line driver that builds a small application over
these primitives, runs every case through its own stack, and asserts against
the table — never against the other stack's output, because two stacks
agreeing on the wrong thing is not conformance.

A rule stated here with no case in that table is treated as unfinished.
