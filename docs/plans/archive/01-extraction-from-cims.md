# Plan 1: Extracting reusable libraries from cims-backend into pykit

> **Historical plan.** For current status, use the [spec board](../../specs/index.md). For this plan's section map and unresolved conflicts, use the [migration ledger](../context.md).

> # ⚠️ SUPERSEDED — background reading only
>
> **Do not implement from this document.** It is the original survey that the four current plans grew
> out of; its recommendations have since been split across them, re-decided, and in several places
> reversed. Implement from these instead — see [`README.md`](./plan-board.md) for the execution order:
>
> - [`commons-upgrade-plan.md`](./commons-upgrade-plan.md) — resilience, env guards, and the
>   messaging/secrets/objects protocols
> - [`web-library-plan.md`](./web-library-plan.md) — RFC 9457 problem details, concurrency,
>   pagination, idempotency, health, correlation IDs
> - [`django-upgrade-plan.md`](./django-upgrade-plan.md) — the DRF/Django adapters over those
> - [`azure-library-plan.md`](./azure-library-plan.md) — the Azure adapters
>
> **Known-stale claims in what follows**, so they are not acted on by mistake:
>
> - The "Blocking prerequisite" Python-floor argument (already annotated below) — the floor stays
>   `>=3.14`.
> - The **Tier 1/2/3 priority table** — superseded by the cross-plan order in `README.md`.
> - The "New deps? None" column — it records what cims used, and predates the workspace principle
>   that a proven library beats a hand-rolled equivalent.
> - Every **destination package** it names for RFC 7807 / pagination / idempotency / concurrency /
>   readiness / request-ID work: those moved to `rn-forge-web`.
> - **Plan 2 (`02-cims-adoption-of-pykit.md`) was never written and will not be** — cims is being
>   respecified and reimplemented, and its adoption path is now the web plan's Phase 9 context pack.


Source app: `/Users/rohitnarayanan/Devel/workspaces/walgreens/cims/backend` (Django 5.2 + DRF,
inventory domain, Azure-hosted). Survey performed 2026-07-22 by reading `apps/common`, `apps/core`,
`apps/bff`, `apps/audit`, `apps/ariba`, `apps/hana`, `apps/nexia`, `apps/messaging`, `config/`,
`contracts/events`, and `tests/`.

This document is the extraction plan. Plan 2 ("adopting the result back into cims") was never
written and will not be — see the banner above.

## Summary (read this first)

cims-backend has one clean shared-kernel app, `apps/common`, plus a well-designed
transactional-outbox/inbox messaging subsystem in `apps/messaging`. Everything in `apps/core`,
`apps/audit`, `apps/bff`, `apps/ariba`, `apps/hana`, `apps/nexia` is inventory/SAP/Nexia business
logic and is **not** a candidate for extraction. Roughly 500-600 lines across `apps/common` and
`apps/messaging` are generic enough to become pykit modules.

**Superseded prerequisite (2026-08-31):** this plan originally recorded cims's Python 3.12 pin
([ADR-001](file:///Users/rohitnarayanan/Devel/workspaces/walgreens/cims/backend/docs/adr/001-backend-platform-and-delivery.md))
as a blocker against pykit's `>=3.14` floor. It is not one. cims is work-in-progress and is being
respecified and reimplemented against these libraries, so its current pin constrains nothing. pykit's
floor stays `>=3.14`; see [`web-library-plan.md`](./web-library-plan.md) Phase 0.1.

**How to read this document now:** everything below is a survey of cims's *current* code, which is
being replaced. Treat it as **prior art that shows which concerns are real**, not as a set of call
sites to stay compatible with. Where the survey found a weaker design, the extraction fixes it. The
dependency columns below also predate the workspace design principle (README / CLAUDE.md) — "New
deps? None" is a finding about what cims used, not a constraint on the extraction: if a proven library
covers a row, depend on it and wrap it rather than porting cims's implementation.

**Recommended priority order** (highest value / lowest risk first):

| Tier | What | New deps? | Effort |
|---|---|---|---|
| 1 | RFC 7807 exception handler, pagination, idempotency-key helper, version/optimistic-concurrency mixin + `ImmutableModel` mixin, `OmitEmptyMixin`, `PermissionByMethodMixin`, production-settings guard helper, readiness-check view | None | Small, ~1-2 days total |
| 2 | Resilience module (circuit breaker + retry HTTP client), sequence-backed code generator, CloudEvents envelope builder, request-id middleware | `pybreaker`, `tenacity` (resilience only) | Medium, ~3-5 days |
| 3 | OIDC/JWKS bearer auth (generalized Entra auth), outbox/inbox abstract models + relay/dispatch, `MessageBus` protocol, Celery integration, claim-check pattern | `pyjwt` (have via jwt extra), `celery` (new optional) | Large, design-heavy, ~1-2 weeks |
| — | drf-spectacular + camelCase settings recipes, structlog compatibility | doc-only / deferred | Low priority, document rather than ship code |

Things deliberately **not** extracted: anything under `apps/core`, `apps/audit`, `apps/bff`, and the
domain-specific parts of `apps/ariba`/`apps/hana`/`apps/nexia` (Protocol/Stub/Http client triplets stay
in cims — only the `ResilientHttpClient` base they wrap is generic); the Azure Service Bus and Azure
Blob Storage adapter implementations (cims becomes the Azure adapter for pykit's generic protocols,
not the other way around); `AuditContextMiddleware`'s header-trust mechanism (`X-CIMS-Actor` /
`X-CIMS-Role` — a dev-convenience auth bypass, not something to normalize into a library).

---

## Design decisions to make before/while extracting

1. **Logging backend coupling.** cims uses `structlog`; pykit's `AppLogger` is
   `verboselogs`/`coloredlogs`/stdlib `dictConfig`-based. These are architecturally incompatible —
   do not try to unify them. Any extracted module that currently logs (middleware, resilience
   listener, outbox relay) must accept logging as an **injected callable**, not call `AppLogger`
   directly, so consumers on structlog (or anything else) can wire their own. Default the callable to
   `AppLogger` for pykit's own consumers. See the middleware spec (§7) for the concrete shape.
2. **OTel metrics coupling.** cims increments OTel counters (`circuitbreaker_state`, `outbox_lag`,
   etc.) inline. pykit has an `otel` extra in `rn-forge-commons` but no metrics module. Extracted
   modules should accept optional metric-emission hooks (plain callables) rather than requiring
   `opentelemetry-api` as a hard dependency.
3. **RFC 7807 vs. existing exception contract.** pykit's `drf_exception_handler` already produces a
   response shape (see `rn_forge/django/exceptions.py`, `rn_forge/django/drf/exceptions.py`). cims's
   `problem_details_handler` produces a different, standards-based (`application/problem+json`)
   shape. Ship the RFC 7807 handler as an **additional, opt-in** handler
   (`problem_details_exception_handler`), not a replacement — don't break existing consumers of
   `drf_exception_handler`.
4. **`BaseModel` is not being replaced.** cims's own `apps/common/models.py::BaseModel` (UUID PK,
   `version` int, audit columns with no `db_column` override) and pykit's
   `rn_forge.django.models.base.BaseModel` (`status` EnumField, camelCase `db_column`s, natural-key
   manager) are different, both reasonable designs. Extract cims's **version/immutability behavior**
   as standalone mixins that can compose with *either* base model, not as a fork of pykit's
   `BaseModel`. Do not add a `status` field or camelCase `db_column`s to anything extracted here.

---

## Tier 1 — small, self-contained, no new dependencies

### 1.1 RFC 7807 problem-details exception handler

- **Source:** `apps/common/exceptions.py` (`problem_details_handler`, `DomainConflict`, `VersionConflict`)
- **Destination:**
  - `packages/rn-forge-commons/src/rn_forge/commons/exceptions.py` — add `DomainConflict(AppException)`
    and `VersionConflict(DomainConflict)` (or a new small `conflicts.py` module if `exceptions.py`
    would get crowded — check current line count first).
  - `packages/rn-forge-django/src/rn_forge/django/drf/exceptions.py` — add
    `problem_details_exception_handler(exc, context) -> JsonResponse`, alongside the existing
    `drf_exception_handler`.
- **Behavior to preserve:** delegate to DRF's default `exception_handler` first; map
  `DomainConflict`/`VersionConflict` → HTTP 409; normalize both DRF's `{"detail": ...}` and
  field-error-dict shapes into `{type, title, status, detail, instance, errors?}`; set
  `Content-Type: application/problem+json`; stamp `instance` from a request-id (accept the request-id
  as a parameter or read it from a header — don't hardcode cims's specific context-var mechanism, see
  §1.6 below for the generic version of that piece).
- **Tests:** new `tests/drf/test_problem_details_exception_handler.py` in `rn-forge-django` — cover
  the 409 mapping, both DRF error shapes, and the header/content-type.
- **Non-goals:** don't wire this as the default `EXCEPTION_HANDLER` anywhere in pykit; it's an
  additional option consumers opt into via their own DRF settings.

### 1.2 Pagination

- **Source:** `apps/common/pagination.py::StandardPagination`
- **Destination:** new `packages/rn-forge-django/src/rn_forge/django/drf/pagination.py`
- **Signature:** `class StandardPagination(PageNumberPagination)` with `page_size=50`,
  `page_size_query_param="pageSize"`, `max_page_size=200` as class defaults, but make all three
  overridable via the `RnforgeDjangoSettings` facade (`rn_forge/django/settings.py`) — add a
  `PaginationSettings` dataclass (`page_size`, `page_size_query_param`, `max_page_size`) nested under
  `DRFSettings`, following the exact pattern already used for `DRFViewsSettings`
  (`_get_mapping`/`DictUtils.get` in `_build_settings()`).
- **Tests:** `tests/drf/test_pagination.py` — default values, settings override, `setting_changed`
  signal reload (mirror the existing settings reload tests for `DRFViewsSettings`).

### 1.3 Idempotency-Key helper

- **Source:** `apps/common/idempotency.py` (`replay`, `remember`)
- **Destination:** new `packages/rn-forge-django/src/rn_forge/django/drf/idempotency.py`
- **Signature:**
  - `def replay(request: HttpRequest, scope: str) -> HttpResponse | None` — reads `Idempotency-Key`
    header, looks up `f"idempotency:{scope}:{key}"` in Django cache, returns the cached response or
    `None`.
  - `def remember(request: HttpRequest, scope: str, response: HttpResponse, *, timeout: int = 86400) -> None`
    — stores the response under the same key. Make `timeout` a parameter (cims hardcodes 24h; don't
    hardcode it in the library).
- **Tests:** `tests/drf/test_idempotency.py` — cache hit/miss, missing header, timeout override, using
  Django's `locmem` cache backend in test settings (see `rn-forge-django/tests/conftest.py`).

### 1.4 Optimistic-concurrency mixin + `enforce_version` helper

- **Source:** `apps/common/models.py::BaseModel.version` field + save-increment behavior,
  `apps/common/models.py::ImmutableModel`, `apps/common/concurrency.py::enforce_version`
- **Destination:** new `packages/rn-forge-django/src/rn_forge/django/models/concurrency.py`
  - `class VersionedModelMixin(models.Model)` — abstract, adds `version = models.PositiveIntegerField(default=1)`,
    overrides `save()` to increment `version` on every update (not on insert). Compose via multiple
    inheritance with either `BaseModel`, e.g. `class Item(VersionedModelMixin, BaseModel): ...` —
    don't bake it into `BaseModel` itself (see Design Decision 4).
  - `class ImmutableModelMixin(models.Model)` — abstract, overrides `save()` to diff against the DB
    row and raise on any non-audit-field mutation, overrides `delete()` to raise. Needs a hook for
    which fields count as "audit fields" (default: `created_by`, `created_at`, `updated_by`,
    `updated_at`, or accept an `IMMUTABLE_EXCLUDE_FIELDS` class attribute).
  - `def enforce_version(request: HttpRequest, instance: VersionedModelMixin) -> None` in the same
    module or `rn_forge/django/drf/concurrency.py` — reads `If-Match` header (strip weak-etag
    `W/"..."` quoting) or `version` from body, compares to `instance.version`, raises
    `VersionConflict` (from §1.1) on mismatch.
- **Tests:** `tests/models/test_concurrency.py` (version incrementing, immutability enforcement) and
  `tests/drf/test_concurrency.py` (`enforce_version` header parsing + conflict cases). Use a test-only
  model defined in `conftest.py` per existing rn-forge-django test conventions.

### 1.5 `OmitEmptyMixin` serializer mixin

- **Source:** `apps/core/serializers.py::OmitEmptyMixin` (9 lines — strips empty-string/`None`
  optional fields from `to_representation` output)
- **Destination:** `packages/rn-forge-django/src/rn_forge/django/drf/serializers/base.py` (or
  `fields.py` if that's the established home for serializer mixins — check existing file contents to
  match convention) as `OmitEmptyMixin`.
- **Tests:** add a case to the existing serializer test file for this behavior.

### 1.6 `PermissionByMethodMixin`

- **Source:** `apps/core/views.py::PermissionByMethodMixin` (8 lines — maps HTTP method to a required
  permission class)
- **Destination:** `packages/rn-forge-django/src/rn_forge/django/drf/views/mixins.py`, alongside
  `RequestAccessViewMixin`/`AuditFieldsViewMixin`/etc.
- **Tests:** add to `tests/drf/views/test_mixins.py` (or wherever the existing mixin tests live).

### 1.7 Production-settings guard helper

- **Source:** `config/settings/production.py` (`required_environment` set + `ImproperlyConfigured`
  fail-fast checks, and the explicit "forbid this default value" checks)
- **Destination:** new `packages/rn-forge-commons/src/rn_forge/commons/config.py` additions (check
  existing `config.py` contents first — this may fit alongside what's already there):
  - `def require_env(*names: str) -> None` — raises (an `AppException`, not Django's
    `ImproperlyConfigured` — keep `rn-forge-commons` Django-free) if any of `names` is unset in
    `os.environ`.
  - `def forbid_value(name: str, forbidden: object, *, message: str | None = None) -> None` — raises
    if `os.environ.get(name)` (or a passed-in value) equals `forbidden`.
  - Django-specific fail-fast (`ImproperlyConfigured`) wrapping, if wanted, belongs in
    `rn-forge-django` as a thin wrapper, not in commons.
- **Tests:** `tests/test_config.py` in `rn-forge-commons`.

### 1.8 Readiness-check view

- **Source:** `apps/common/views.py::readyz` (per-dependency check dict, aggregate status + HTTP code)
- **Destination:** `packages/rn-forge-django/src/rn_forge/django/views.py` — add
  `def readiness_view(checks: Mapping[str, Callable[[], bool]], *, required: Collection[str] = ()) -> Callable[[HttpRequest], JsonResponse]`
  — a view **factory**: consumers call `readiness_view({"database": ping_db, "cache": ping_cache})`
  in their URLconf and get back a view function. Checks not listed in `required` soft-fail (result
  recorded but doesn't flip overall status to 503) — mirrors cims's `SERVICE_BUS_REQUIRED` flag
  concept but generalized. Each check callable should return `bool` or raise; catch exceptions and
  record `{ok: False, error: str(exc)}` per-check, matching cims's shape.
- **Tests:** `tests/test_views.py` additions — all-pass, one soft-fail, one hard-fail → 503.

---

## Tier 2 — moderate, need new optional dependencies

### 2.1 Resilience module (circuit breaker + retry HTTP client)

This is the single highest-value extraction in the survey — clean, ~50 lines, zero domain coupling,
and used consistently by every integration client in cims.

- **Source:** `apps/common/resiliency.py` (`retryable`, `breaker`, `BreakerListener`, `ResilientHttpClient`)
- **Destination:** new `packages/rn-forge-commons/src/rn_forge/commons/resilience.py`
- **New dependency:** add `pybreaker` and `tenacity` as a new `resilience` optional extra in
  `rn-forge-commons/pyproject.toml` (needs `httpx` too, since `ResilientHttpClient` wraps it — add
  `httpx` to the same extra). Mirror the existing `[project.optional-dependencies]` pattern (see
  `excel`, `otel`).
- **Design:**
  - `def retryable(exc: BaseException) -> bool` — same classification logic (connect errors, timeouts,
    5xx), but make the exception-type set overridable via a parameter or module-level constant
    consumers can monkeypatch/extend, rather than hardcoding only `httpx` exceptions if pykit wants
    this usable with other HTTP clients later. For v1, keep it `httpx`-specific (matches the source) —
    don't over-generalize on day one.
  - `def breaker(name: str, *, fail_max: int = 5, reset_timeout: int = 60, on_state_change: Callable[[str, str, str], None] | None = None) -> pybreaker.CircuitBreaker`
    — the `on_state_change` callable replaces cims's hardcoded `BreakerListener` OTel-counter call;
    default to logging via `AppLogger` only (no metrics), let callers pass their own OTel hook.
  - `class ResilientHttpClient` — same shape as cims's version (per-instance breaker + tenacity retry
    wrapping `.request()`), constructor takes `base_url`, `name` (breaker name), retry params
    (`stop_after_attempt`, wait params), and the optional `on_state_change` hook.
- **Tests:** `tests/test_resilience.py` — use `respx` or `httpx.MockTransport` to simulate
  timeouts/5xx/success, assert retry counts and breaker state transitions. Gate behind the
  `resilience` extra like `excel`-dependent tests are gated (check `pytest.importorskip` pattern used
  elsewhere in the repo, e.g. for pandas/openpyxl).

### 2.2 Sequence-backed human-readable code generator

- **Source:** `apps/common/identifiers.py` (`generate`, `ensure_at_least`, Postgres `SEQUENCE` +
  sqlite-fallback counter table)
- **Destination:** new `packages/rn-forge-django/src/rn_forge/django/models/sequences.py`
- **Design:**
  - Ship an abstract `SequenceCounter` model (name/value columns) for the non-Postgres fallback path —
    consuming apps run a migration to create the concrete table, same as they would for any other
    pykit abstract model.
  - `class SequenceGenerator` — constructed with a `prefix: str` and a `formatter: Callable[[str, int], str]`
    defaulting to `f"{prefix}-{value:06d}"` (cims's `PO-2026-0001` format is a caller-supplied
    formatter, not baked into the library).
  - `def generate(self) -> str` — uses a real Postgres `SEQUENCE` (`CREATE SEQUENCE IF NOT EXISTS` /
    `nextval`) when `connection.vendor == "postgresql"`, else `select_for_update()`-locks a row in the
    shipped `SequenceCounter` model.
  - `def ensure_at_least(self, value: int) -> None` — same as cims's version, for backfill/import
    scenarios.
- **Tests:** `tests/models/test_sequences.py` — sqlite fallback path (CI default), and a
  `pytest.mark.integration`-gated Postgres-sequence test if the test infra supports it (check whether
  `rn-forge-django`'s test suite has any Postgres integration tests today — if not, sqlite-only
  coverage is acceptable and note the Postgres path as manually-verified-in-cims).

### 2.3 CloudEvents envelope builder

- **Source:** `apps/messaging/cloudevents.py::envelope()`
- **Destination:** new `packages/rn-forge-commons/src/rn_forge/commons/cloudevents.py`
- **Design:** `def build_cloudevent(*, id: str, type: str, source: str, subject: str | None = None, time: datetime | None = None, data: Any = None, extra: Mapping[str, Any] | None = None) -> dict[str, Any]`
  — builds the CloudEvents 1.0 envelope dict (`specversion`, `id`, `source`, `type`, `subject`,
  `time`, `datacontenttype`, `data`). `source` and the W3C `traceparent` injection are caller
  concerns in cims today — keep `source` as a required parameter (no hardcoded `"/cims/backend"`) and
  make `traceparent` injection an optional `extra` dict entry the caller populates, rather than pulling
  OTel spans directly into this module (keeps `rn-forge-commons` free of an OTel hard dependency).
- **Tests:** `tests/test_cloudevents.py` — envelope shape, default `time`, `extra` merge behavior.

### 2.4 Request-ID middleware

- **Source:** `apps/common/middleware.py::RequestIdMiddleware`
- **Destination:** new `packages/rn-forge-django/src/rn_forge/django/middleware.py`
- **Design (per Design Decision 1):** `class RequestIdMiddleware` constructor accepts
  `log: Callable[[str, Mapping[str, Any]], None] | None = None` (defaults to a thin wrapper around
  `AppLogger.get_logger(__name__).info`). Behavior: read/generate `X-Request-ID`, bind it to a
  `ContextVar` (export the `ContextVar` itself, e.g. `request_id_var`, so other pykit code — and
  cims's structlog processors — can read it), log a `request.complete` event with
  method/path/status/duration_ms via the injected `log` callable, echo the header back on the
  response.
- **Tests:** `tests/test_middleware.py` — header passthrough, header generation, `log` callable
  invocation with expected fields, `ContextVar` accessible during request handling.

---

## Tier 3 — substantial subsystems, design-heavy

Do these last, and expect the API to shift as real second/third consumers (beyond cims) show up.
Each of these should probably be its own pykit sub-package or clearly delimited module with its own
optional extra, not bolted onto existing files.

### 3.1 OIDC/JWKS bearer authentication (generalized `EntraAuthentication`)

- **Source:** `apps/common/auth.py::EntraAuthentication`, `Principal`, `EntraAuthenticationScheme`
- **Destination:** new `packages/rn-forge-django/src/rn_forge/django/auth/jwt/oidc.py` (sibling to the
  existing `authentication.py` which wraps simplejwt-issued tokens — this is a distinct mechanism:
  externally-issued tokens verified against a remote JWKS endpoint, no local `User` model involved).
- **Design:**
  - `class JWKSBearerAuthentication(BaseAuthentication)` — constructor/class attributes parameterized
    by `jwks_url: str`, `audience: str`, `issuer: str`, `cache_timeout: int = 86400`, and a
    `claims_to_principal: Callable[[dict], object]` hook (cims's `role_map` extraction becomes
    caller-supplied, not hardcoded to Walgreens' Entra app-role claim shape). Keep the JWKS-fetch +
    `kid`-match + RS256-verify + cache machinery in the library; the Entra-specific discovery URL
    template (`https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys`) becomes a
    documented recipe for constructing `jwks_url`, not hardcoded in pykit (this class should work for
    Auth0/Okta/any OIDC IdP, not just Entra).
  - A minimal default `Principal`-like dataclass can ship as a fallback, but the `claims_to_principal`
    hook is what makes this reusable — cims keeps its own `Principal` and role-mapping logic, wired in
    via that hook.
  - `class JWKSBearerAuthenticationScheme(OpenApiAuthenticationExtension)` — port the drf-spectacular
    registration pattern (only meaningful if pykit also adopts a drf-spectacular optional extra, see
    Tier 3.5).
- **New dependency:** `pyjwt[crypto]` is already available via the `jwt` extra
  (`djangorestframework-simplejwt` implies it) — confirm whether `pyjwt` needs to be a direct
  dependency of this new module or whether it can be resolved transitively; if pykit wants
  `JWKSBearerAuthentication` usable without pulling in `djangorestframework-simplejwt`, add `pyjwt[crypto]`
  as a direct dependency of a new `oidc` extra instead of reusing `jwt`.
- **Tests:** `tests/auth/jwt/test_oidc.py` — mock the JWKS endpoint (cache hit/miss), valid/expired/
  wrong-audience/wrong-issuer tokens, `claims_to_principal` hook invocation.

### 3.2 Outbox/inbox messaging subsystem

This is the best-designed subsystem in cims and the biggest single lift. Treat it as one cohesive
piece of work, not four independent extractions.

- **Sources:**
  - `apps/messaging/models.py` (`OutboxMessage`, `InboxMessage`)
  - `apps/messaging/tasks.py::relay_outbox` (the outbox relay worker)
  - `apps/messaging/consumer.py` (`HANDLERS` registry, `@register`, `process_event` — the inbox
    dedup/dispatch pattern)
  - `apps/messaging/bus.py` (`MessageBus` Protocol, `InMemoryMessageBus`)
- **Destination:** new `packages/rn-forge-django/src/rn_forge/django/messaging/` package:
  - `models.py` — `AbstractOutboxMessage`, `AbstractInboxMessage` (abstract Django models; concrete
    apps subclass them, same pattern as `rn_forge.django.models.base.BaseModel` subclassing).
    Preserve the `(published_at, occurred_at)` index on the outbox table — that's what makes the
    relay's polling query efficient.
  - `bus.py` — `MessageBus` `Protocol` (`publish(destination: str, event: Mapping) -> None`) +
    `InMemoryMessageBus` (dict-based test double). No Azure/AWS/GCP-specific implementation ships
    here — those are adapters that live in the consuming app (cims keeps `AzureServiceBus`, see Plan
    2 §3.9).
  - `relay.py` — a **task factory**, not a hardcoded Celery task:
    `def make_outbox_relay(outbox_model: type[AbstractOutboxMessage], bus: MessageBus, *, envelope_builder: Callable, batch_size: int = 100, on_lag_observed: Callable[[float], None] | None = None) -> Callable[[], None]`
    — returns a plain callable that does the `select_for_update(skip_locked=True)` batch-claim +
    publish + mark-published work. Consumers wrap the returned callable in their own `@shared_task`
    (keeps Celery out of `rn-forge-django`'s hard dependencies; see Tier 3.3 for where Celery-specific
    sugar goes instead).
  - `consumer.py` — `HandlerRegistry` class (replaces the module-level `HANDLERS` dict + `@register`
    decorator with an instantiable registry so multiple registries can coexist in one process) and
    `def process_event(event: Mapping, registry: HandlerRegistry, inbox_model: type[AbstractInboxMessage]) -> None`
    implementing the dedup-by-`message_id` + dispatch + status-recording logic.
- **New optional extra:** `messaging` in `rn-forge-django/pyproject.toml` — likely no new third-party
  deps (this is all Django ORM + stdlib), but keep it as its own extra so consumers who don't need
  messaging don't pull in anything extra by accident.
- **Tests:** `tests/messaging/` — `test_relay.py` (batch claiming, `skip_locked` behavior needs a
  transactional test setup — check how `rn-forge-django`'s existing `integration`-marked tests handle
  this), `test_consumer.py` (dedup on replay, failure recording, re-raise-for-dead-lettering),
  `test_bus.py` (`InMemoryMessageBus` basic contract).
- **Explicit non-goal:** do not port `AzureServiceBus`, the Azure Blob claim-check storage, or the
  `run_consumer`/`resubmit_dlq` management commands. Those stay Azure-specific and stay in cims. If a
  second cloud-messaging consumer shows up later, *that's* the trigger to design a pluggable adapter
  interface — don't speculatively build one now.

### 3.3 Celery integration

pykit currently has zero Celery code or dependencies — this is net-new, not extracted from existing
cims code (cims's Celery usage is entirely stock `@shared_task`).

- **Destination:** new `packages/rn-forge-django/src/rn_forge/django/celery.py`, new `celery` optional
  extra (`celery[redis]` or just `celery`, matching what cims needs minus the redis-specific pin —
  confirm with actual usage).
- **Design:**
  - `def make_app(name: str, *, config_source: str = "django.conf:settings", namespace: str = "CELERY", autodiscover: bool = True) -> Celery`
    — the 6-line bootstrap from `config/celery.py`, factored into a one-call helper.
  - `RETRYABLE_TASK_KWARGS: dict[str, Any] = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_kwargs": {"max_retries": 5}}`
    — a preset dict consumers spread into `@shared_task(**RETRYABLE_TASK_KWARGS)`. Keep it a plain
    dict, not a decorator wrapper — simplest possible thing that works, matches how cims already uses
    it as a literal.
  - Optionally, a thin Celery-specific wrapper around the outbox relay factory from §3.2:
    `def make_outbox_relay_task(app: Celery, ...) -> Task` — only build this if wiring it manually in
    cims (Plan 2) proves annoying; don't build it speculatively.
- **Tests:** `tests/test_celery.py` — `make_app` returns a configured `Celery` instance; snapshot the
  `RETRYABLE_TASK_KWARGS` dict shape (regression-guard against accidental changes, since consumers
  spread it directly).

### 3.4 Claim-check pattern (defer)

- **Source:** `apps/messaging/claim_check.py::ClaimCheck`
- **Recommendation:** **defer this one.** The pattern (threshold-based payload externalization +
  SHA-256 integrity check) is genuinely generic, but the only concrete implementation is Azure Blob
  Storage-specific, and designing a good storage-backend `Protocol` from a single example tends to
  produce the wrong abstraction. Revisit once there's a second storage backend in view (S3, GCS, or
  even a second Azure consumer with different requirements). If picked up later: destination would be
  `rn_forge.commons.claim_check` (protocol + threshold/hash logic, storage-agnostic), with the Azure
  Blob adapter staying in cims.

### 3.5 drf-spectacular + camelCase settings recipes (documentation, not code)

- **What:** cims's `SPECTACULAR_SETTINGS` (`CAMELIZE_NAMES: True` + the
  `djangorestframework_camel_case.contrib` postprocessing hook) and the global
  `CamelCaseJSONRenderer`/`CamelCaseJSONParser` wiring are well-known but easy-to-miss configuration
  combinations. pykit has no drf-spectacular or camelCase dependency today.
- **Recommendation:** don't add these as code/dependencies speculatively. Instead, add a short page
  to `packages/rn-forge-django/docs/` (mkdocs site) documenting the recommended `SPECTACULAR_SETTINGS`
  and `REST_FRAMEWORK` renderer/parser snippet, plus the nested-`DictField` gotcha
  (`apps/core/serializers.py::normalize_line` in cims — global camelCase parsing recurses into opaque
  dict/list fields and mangles keys that should stay as-is). If/when a second consumer needs the
  nested-dict escape hatch, promote it to a real `RawPassthroughField` in
  `rn_forge.django.drf.serializers.fields` at that point.

### 3.6 structlog compatibility (decision, not extraction)

- **Recommendation:** leave `rn_forge.commons.logging.AppLogger` (verboselogs/coloredlogs-based) as
  pykit's only logging story for now. Do not attempt to add structlog support to pykit to accommodate
  cims. cims's `add_context` processor (OTel trace/span-id + actor/role enrichment via
  `structlog.configure`) is specific enough to structlog's processor-chain model that porting it would
  mean building and maintaining a second logging subsystem in pykit for a single consumer. Revisit
  only if a second pykit consumer independently wants structlog.

---

## Implementation notes for whoever picks this up

- Work through Tier 1 first as a single PR-per-item (or a few small PRs) — no new dependencies means
  fast review and no `uv.lock` churn to reason about.
- For every new module, follow the repo's existing conventions: `__all__` exports, module docstring
  at the top of the file, dataclasses via `rn_forge.commons.dataclasses.DataclassMixin` where
  applicable, `AppException`/`AppException.check()` for validation rather than raw `raise`, and
  `AppLogger.get_logger(__name__)` for logging (except where Design Decision 1 says to inject a
  logging callable instead).
- New public symbols must be re-exported from the package's curated `__init__.py`
  (`rn_forge/commons/__init__.py`, and check whether `rn_forge/django/__init__.py` plays the same role
  — confirm before assuming).
- Run `uv run pyright` after each addition — `src/` is strict-mode; test code under `tests/` is
  excluded.
- Run `uv run ruff check . && uv run ruff format .` before opening each PR.
- When adding a new optional extra (`resilience`, `oidc`, `messaging`, `celery`), update the
  package's `all` extra in `pyproject.toml` to include it, following the existing pattern where `all`
  aggregates every other extra.
- Every new module needs tests before merge — this repo's own `CLAUDE.md` doesn't waive that, and
  strict Pyright + the existing test conventions (`pytest-randomly`, `unit`/`integration` markers in
  `rn-forge-django`) should be followed for new test files.
