# `rn-forge-azure` — new package plan

Scope: a **new** workspace package, `packages/rn-forge-azure` (import path `rn_forge.azure`), holding
Azure adapters for protocols defined elsewhere in the workspace. It depends on `rn-forge-commons` and
on nothing else in the workspace — deliberately **not** on `rn-forge-web` or `rn-forge-django`, so an
Azure-backed worker or CLI pulls in no HTTP machinery.

**Start from [`README.md`](./README.md)** — it carries the execution order across all five plans.
This package is blocked on `rn-forge-commons` Phases 8b/8c/8d (the protocol modules); see Phase 0.1.

This package implements protocols; it does not define them. That single rule is what keeps it honest
and it is the reason Phase 0 is a prerequisite check rather than a scaffold.

Three sources feed this plan, and it is self-contained:

- The `cims-backend` survey (`/Users/rohitnarayanan/Devel/workspaces/walgreens/cims/backend`,
  2026-07-22) — Azure Service Bus (outbox publishing, DLQ resubmission), Azure Blob Storage
  (claim-check payload externalization), Entra ID authentication. Sync, Django/Celery.
- A survey of `intellibench` (`/Users/rohitnarayanan/Devel/workspaces/walgreens/intellibench`,
  2026-08-31) — a `SecretPort` whose only adapter is env-var-based and whose docstring names its
  replacement, a specified-but-unimplemented `BlobPort`, reserved Entra ID configuration, a REST-only
  Azure OpenAI adapter and a REST-only Azure DevOps adapter. Async throughout.
- The pykit workspace as it stands on 2026-08-31, for scaffold conventions.

Companion documents: [`web-library-plan.md`](./web-library-plan.md) (which defines the amendments this
plan depends on) and [`django-upgrade-plan.md`](./django-upgrade-plan.md).

## Alignment with the standardization plan (kiln revision 9)

**Written 2026-09-10.** This plan predates `rn-forge/kiln`. Its five phases, the translation-layer
principle and the error-translation table are unchanged. What changed is the workspace around it.
Authority: the kiln standardization plan (revision 9, since retired; D-numbers resolve through
`../../../kiln/docs/plans/context.md` §2.2), ADR-0002 (dependency
graphs), ADR-0005 (archetypes and golden repos), D46 (releases are pinned git tags).

### 1. "Depends on commons and nothing else" now excludes two more packages

The development layer split into `rn-forge-cli` and `rn-forge-tooling` (kiln **D52**), so the rule
this plan opens with has two new names in it. `rn-forge-azure` may import **`rn_forge.commons` only**
— never `rn_forge.web`, `rn_forge.django`, `rn_forge.cli` or `rn_forge.tooling`. The reasoning is the
one already in this document, extended: an Azure-backed worker must not acquire ASGI middleware, and
it must not acquire a Typer application factory or a generation engine either.

This is exactly why the protocols it implements live in **commons**, not in web. Under the current
commons layout (kiln **D55**) they are:

| Protocol | Module | Facade import |
| --- | --- | --- |
| `SecretStore` / `AsyncSecretStore` | `rn_forge/commons/integration/secrets.py` | `from rn_forge.commons import SecretStore` |
| `ObjectStore` / `AsyncObjectStore` | `rn_forge/commons/integration/objects.py` | `from rn_forge.commons import ObjectStore` |
| `MessageBus` / `HandlerRegistry` | `rn_forge/commons/integration/messaging.py` | `from rn_forge.commons import MessageBus` |
| resilience (`RateLimiter`, `retryable`, `parse_retry_after`) | `rn_forge/commons/integration/resilience.py` | **direct import** — it sits behind the `resilience` extra and is deliberately excluded from the facade |

**Import the three protocols through the curated facade**, not the submodule path — D55 moved
modules but froze public class names precisely so that `from rn_forge.commons import SecretStore` is
stable across a regrouping. Phase 0.1's prerequisite check should look for the symbol, not the file.
Resilience is the exception and follows the workspace rule for extras: a module gated behind an
optional extra is excluded from the facade and imported directly, so that `import rn_forge.commons`
keeps working with no extras installed.

### 2. The boundary is an import-linter contract

Add to `.importlinter`, with `rn_forge.azure` in `root_packages`:

```ini
[importlinter:contract:azure-depends-on-commons-only]
name = rn_forge.azure imports commons and nothing else in the workspace
type = forbidden
source_modules =
    rn_forge.azure
forbidden_modules =
    rn_forge.web
    rn_forge.django
    rn_forge.cli
    rn_forge.tooling
```

`uv run lint-imports` gates every other CI job, so this is a real gate rather than a documented
intention. It also gives the namespace-collision warning below a second line of defence: a contract
naming `rn_forge.azure` as a source module fails loudly if the package ever resolves to the SDK's
`azure` instead.

### 3. Releases are pinned git tags (D46)

The scaffold below declares `# kiln D46 — a pinned direct URL, not a bare name; see the alignment section, §3
dependencies = [
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
]` with a workspace source override.
A source override does not survive into a built wheel, so a consumer outside the workspace could not
resolve commons at all. Corrected:

```toml
dependencies = [
  # kiln D46 — not on PyPI; a release is a tag. The uv source override is local development only.
  "rn-forge-commons @ git+https://github.com/rn-forge/pykit@rn-forge-commons-v0.5.0#subdirectory=packages/rn-forge-commons",
]

[tool.uv.sources]
rn-forge-commons = { workspace = true }
rn-forge-azure = { workspace = true }
```

The package's own releases are `rn-forge-azure-v0.1.0` and so on, and its installation guide documents
the `git+…@tag` form. **This interacts with the extras design**: a consumer installs
`rn-forge-azure[keyvault] @ git+…@rn-forge-azure-v0.1.0#subdirectory=packages/rn-forge-azure`. Write
that full line into the installation guide for each extra — the shape is unfamiliar enough that a
consumer will otherwise reach for `uv add`, which is the finding that was raised against tooling's
guide (commons plan D.7).

### 4. Layout (D55)

Five flat modules, all one kind of mechanism (Azure service adapters), so flat stays — and, as with
`rn-forge-web`, that is now a recorded decision rather than a default. If the package grows past its
five phases, group by service family and keep the public class names where they are.

### 5. Consumers, and the golden-repo rule

The two applications this plan names are being rebuilt as kiln archetypes (**D53**): intellibuild is
`python-web-api` with `framework = fastapi`, and the cims successor is `python-web-app` with
`framework = django`. Neither is an adoption of the surveyed code (**D39** — rebuild, not migrate),
which reinforces this plan's existing stance that both are prior art.

One consequence worth stating: **no golden repo depends on `rn-forge-azure`.** kiln's archetypes
describe repo shape, not cloud provider, and an Azure adapter is an application dependency. So this
package's acceptance stays what it already is — the three-tier testing strategy below, with tier 1
(protocol conformance against commons' in-memory implementation) as the tier that earns the package.
Do not go looking for a golden repo to prove it.

### 6. Adding the package to pykit is a repo-shape change

pykit is the `python-lib` archetype. Beyond `[tool.uv.workspace] members`, `[tool.uv.sources]` and
the `workspace` dependency group, once kiln Phase F.1 has regenerated pykit's skeleton you also
update `[archetype.python-lib] packages` in `.rn-forge/kiln/config.toml` (it drives the generated CI
matrix, build and release jobs), re-seed `.rn-forge/kiln/state.json` via `kiln apply`, and add the
site to the root `mkdocs.yml` nav and `docs/index.md`. Before that regeneration none of those files
exists; do not create them early.

### 7. Validation

Every phase's validation block gains `uv run lint-imports`. After kiln Phase F.1 the repo's public
verbs are the ten kiln wrappers (ADR-0008) and `task validate` is what CI runs; the `uv run …` forms
below remain valid as the inner primitives.

## Summary (read this first)

| Phase | Module | Implements | Consumer waiting today | New deps | Risk |
| --- | --- | --- | --- | --- | --- |
| 0 | Scaffold + **protocol prerequisites** | — | — | — | **blocking** |
| 1 | `credentials.py` | — (foundation for 2-5) | both | `azure-identity` | low |
| 2 | `keyvault.py` | `SecretStore` | intellibench, explicitly | `azure-keyvault-secrets` | low |
| 3 | `blob.py` | `ObjectStore` | intellibench (`BlobPort`), cims (claim-check) | `azure-storage-blob` | medium |
| 4 | **Gated:** `servicebus.py` | `MessageBus` | cims | `azure-servicebus` | **high** |
| 5 | **Gated:** `monitor.py` | — (OTel export wiring) | cims | `azure-monitor-opentelemetry` | medium |
| — | Deferred: Azure OpenAI, Azure DevOps, managed-identity Postgres, Entra OIDC | — | — | — | — |

Every service is its own optional extra. Installing `rn-forge-azure` with no extras installs nothing
but `rn-forge-commons` — Azure SDK packages are large and a consumer using Key Vault must not be made
to install the Service Bus stack.

### Guiding principle for this plan

**This package is a translation layer, not a wrapper.** The Azure SDKs are competent; re-exposing
their surface with different names would be pure cost. There are exactly four things worth doing here,
and a module that does something else is out of scope:

1. **Protocol conformance.** Make `KeyVaultSecretStore` satisfy `SecretStore` so calling code depends
   on the protocol, not on `azure.keyvault`.
2. **Error translation.** Map `azure.core.exceptions` onto the workspace's exception taxonomy so
   `ResourceNotFoundError` never reaches a caller's `except` clause. This is the highest-value thing
   in the package — it is what stops a cloud vendor's exception hierarchy from colonizing domain code.
3. **Credential and client lifecycle.** `DefaultAzureCredential` is expensive to construct, holds
   sockets, and must be closed. Consumers get this wrong; one place should get it right.
4. **Configuration shape.** A frozen settings dataclass per service, so endpoints and names are typed
   and validated at construction rather than discovered at first call.

Corollary: **no business logic and no policy**. Retry, backoff and circuit breaking are the SDK's own
(they ship real retry policies) or commons' (`resilience.py`); this package does not re-implement
either. If a phase below starts growing a state machine, it is in the wrong package.

### Conventions for this package

1. **Async and sync are both first-class, and are separate classes.** Every Azure SDK ships an `.aio`
   variant. intellibench is async end to end; cims is sync Django/Celery. Ship `KeyVaultSecretStore`
   and `AsyncKeyVaultSecretStore` as siblings, not one class with a mode flag. Do not build a sync
   facade that drives the async client through `asyncio.run` — that breaks under an already-running
   loop, which is exactly where it would be called.
2. **Every client is closable and says so.** Expose `close()` / `aclose()` and support the context
   manager protocol. A module-level singleton client that is never closed is the default failure mode
   of Azure SDK usage; do not ship one.
3. **No `azure.*` type in any public signature.** Parameters and returns are stdlib types, workspace
   protocol types, or this package's own dataclasses. The one deliberate exception is the credential
   object itself (Phase 1), which is unavoidably an Azure type and is therefore isolated in a module
   whose whole purpose is to produce it.
4. **Logging is injected** — same rule as the other plans, and it matters more here: both surveyed
   codebases use `structlog`. No `AppLogger` at module scope.
4b. **Wrap the Azure SDKs; do not reimplement them.** This package exists precisely to apply the
   workspace principle (README / CLAUDE.md §Design principles) to Azure: depend on the official
   `azure-*` clients, and contribute pykit's syntax — frozen-dataclass settings, `AppException`-derived
   errors, injected logging, curated re-exports — around them. Never hand-roll REST calls the SDK
   already makes, and never extend an SDK client with features it does not have.
5. **Never read `os.environ` at the call site.** Settings dataclasses are constructed by the consumer
   from wherever their configuration lives. `DefaultAzureCredential` reads the environment itself,
   which is the SDK's business, not ours.
6. **Strict typing, `py.typed`, module docstrings, explicit `__all__`.** Azure SDK stubs are uneven;
   follow the workspace precedent of a narrow `# pyright: ignore[...]` with a trailing reason rather
   than a file-level suppression, and check whether the `azure-*` packages ship `py.typed` before
   assuming their types resolve.
7. **`requires-python = ">=3.14"`** — the workspace floor. An earlier draft matched a 3.12 floor
   proposed for `rn-forge-web` on the basis of cims's and intellibench's pins; both applications are
   being rewritten against these libraries, so those pins constrain nothing. See that plan's
   Phase 0.1.

### Things deliberately NOT in this package

- **Any protocol definition.** If a phase here needs a protocol that does not exist, the protocol goes
  into `rn-forge-commons` first (Phase 0). A protocol defined next to its only implementation is a
  protocol shaped by that implementation.
- **The Azure DevOps adapter.** intellibench's is ~1,400 lines and almost all of it is Azure DevOps
  *domain* — an operation registry with pinned `api-version` per route, work-item schema mapping, WIQL
  queries, an annotation profile. The genuinely generic parts (async circuit breaker, token-bucket
  rate limiter, `Retry-After`-aware retry, HTTP-status→error-taxonomy mapping) are **resilience**, and
  they belong in commons — see the web plan's amendment §A.3. Extract those; leave the adapter.
- **The Azure OpenAI adapter.** It is an `LLMPort` implementation, and pykit has no LLM abstraction.
  Building one from a single provider adapter is exactly the mistake this workspace's plans keep
  warning about. Deferred with a trigger, below.
- **Entra-specific authentication.** The `rn-forge-django` plan's Phase 9 ships generic JWKS/OIDC
  bearer auth that works against Entra, Auth0, Okta or anything else. Entra needs no code here — only
  a documented `jwks_url` recipe, which belongs in that package's docs. Shipping an `EntraAuth` class
  would re-hardcode the vendor the OIDC design deliberately parameterized.
- **Infrastructure provisioning.** No ARM/Bicep/Terraform, no resource creation. This package talks to
  resources that exist.
- **A `CachePort` implementation over Azure Cache for Redis.** Redis is not Azure; `redis-py` against a
  connection string is the whole adapter. If a Redis cache protocol is wanted, it is a commons or
  standalone concern.

### Package scaffold and dependencies

`packages/rn-forge-azure/pyproject.toml`:

```toml
[project]
name = "rn-forge-azure"
version = "0.1.0"
description = "Azure adapters for rn-forge protocols"
requires-python = ">=3.14"
dependencies = ["rn-forge-commons"]

[project.optional-dependencies]
identity    = ["azure-identity>=1.19"]                      # phase 1
keyvault    = ["azure-identity>=1.19", "azure-keyvault-secrets>=4.9"]   # phase 2
blob        = ["azure-identity>=1.19", "azure-storage-blob>=12.24"]     # phase 3
# servicebus = ["azure-identity>=1.19", "azure-servicebus>=7.13"]       # phase 4 ONLY IF the gate passes
# monitor    = ["azure-monitor-opentelemetry>=1.6"]                     # phase 5 ONLY IF the gate passes
all = ["azure-identity>=1.19", "azure-keyvault-secrets>=4.9", "azure-storage-blob>=12.24"]

[build-system]
requires = ["uv_build>=0.11.28,<0.12.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "rn_forge.azure"

[tool.uv.sources]                   # local development only — see the alignment section, §3
rn-forge-commons = { workspace = true }
rn-forge-azure = { workspace = true }
```

**Pin floors against what is actually installed, not against the numbers above** — those are
plausible-looking versions, not verified ones. Run `uv add --dry-run` or check PyPI before committing
each floor, and record the resolved version in the PR.

Every extra includes `azure-identity` because every service client needs a credential. Add each
extra's packages to `all` as the phase lands, per the workspace convention.

Root `pyproject.toml`: add to `[tool.uv.workspace] members`, `[tool.uv.sources]`, and the `workspace`
dependency group. Pyright picks it up via `include = ["packages"]`.

### Namespace collision warning — read before writing a single import

The import path is `rn_forge.azure`, and the SDK's is `azure.*`. Inside
`packages/rn-forge-azure/src/rn_forge/azure/keyvault.py`, a bare `import azure.identity` resolves
correctly under absolute imports (which is every Python 3 module), but the two names sitting one
level apart will confuse readers and tooling — and `from azure import identity` inside a module whose
own package is named `azure` is the kind of thing that produces a baffling bug report. Two mitigations,
both cheap: always import the SDK as `from azure.identity import DefaultAzureCredential` (fully
qualified, never `import azure`), and add a test that asserts `rn_forge.azure.__path__` and
`azure.__path__` are disjoint. If this proves noisy in practice, the fallback is to rename the import
path to `rn_forge.azure_adapters` — decide in Phase 0, not after five modules are written.

### Validation command for every phase

```bash
uv sync --all-extras
uv run pytest packages/rn-forge-azure
uv run ruff check packages/rn-forge-azure
uv run ruff format --check packages/rn-forge-azure
uv run pyright
uv run lint-imports                  # the commons-only boundary — alignment §2
uv run --directory packages/rn-forge-azure --group docs mkdocs build --strict
```

Plus, for every phase: `import rn_forge.azure` must succeed in an environment with **no** extras
installed. Every SDK import is inside a function or guarded at module level with a clear error.

### Testing strategy (decide once, in Phase 0)

**No test in this package may make a network call.** Three tiers:

1. **Protocol conformance tests** — run the same test body against this package's adapter and against
   commons' in-memory implementation, asserting identical behaviour. This is the tier that earns the
   package: it proves the protocol is implementable twice, which is the whole justification for the
   protocol existing.
2. **Transport-level tests** — `azure-core` clients accept a `transport=` argument, which is the seam
   for a fake that returns canned responses. Use it to cover error translation (Phase 1's table)
   without a network.
3. **Emulator-backed integration tests, marked and opt-in** — Azurite covers Blob and is a cheap
   container. Whether a usable Service Bus emulator exists is a Phase 4 gate question, not an
   assumption; check current state at that time rather than trusting this sentence.

Tiers 1 and 2 run in the default suite. Tier 3 is marked `integration` and skipped unless the emulator
is reachable.

---

## Phase 0 — Scaffold and protocol prerequisites

**This phase is blocking, and its substance is the prerequisites, not the scaffold.**

### 0.1 — The protocols must exist first

Every phase in this package implements a protocol defined in `rn-forge-commons`, specified by the web
plan's amendment §A.2 and built as the commons plan's Phases **8b**, **8c** and **8d**.

> **Status 2026-09-10: all three have landed.** What was a prerequisite is now a verification step —
> confirm the symbol imports from the facade, then proceed. The module paths moved in the D55
> re-layout and the class names did not, which is exactly what the facade is for.

| Protocol | Commons module (after D55) | Needed by | Modelled on |
| --- | --- | --- | --- |
| `SecretStore` / `AsyncSecretStore` + `EnvSecretStore` | `commons/integration/secrets.py` | Phase 2 | intellibench `intellibuild_ports/secrets.py` |
| `ObjectStore` / `AsyncObjectStore` + `InMemoryObjectStore` | `commons/integration/objects.py` | Phase 3 | intellibench's specified `BlobPort` (`put`/`get`/`delete`/`url_for`) |
| `MessageBus` / `AsyncMessageBus` + `InMemoryMessageBus` | `commons/integration/messaging.py` | Phase 4 | cims `apps/messaging/bus.py` |

Verify with `python -c "from rn_forge.commons import SecretStore, ObjectStore, MessageBus"` rather
than by looking for a file. Do not define a protocol here "temporarily" — there is no such thing.

The shaping notes below are the record of how each was designed; check the shipped surface against
them and raise any gap against the **commons** plan, never by widening a protocol from this side.

Notes on shaping each, from the surveys:

- **`SecretStore`** is 15 lines: `get_secret(key) -> str`, raising `SecretNotFound`. intellibench's
  version is an ABC; a `Protocol` is better for a library (no inheritance requirement on adapters).
  Ship `EnvSecretStore` in commons as the default — it is 8 lines and it is what every consumer starts
  with.
- **`ObjectStore`** should follow intellibench's specified `BlobPort` surface: `put`, `get`, `delete`,
  plus **`url_for`**. That last one is the interesting member — it is a time-limited, pre-signed URL,
  which lets a client download directly rather than streaming bytes through the app. Azure calls it a
  SAS URL, S3 calls it a presigned URL; the concept is portable and the protocol should carry it.
  Include `exists` too — the claim-check pattern needs it and it costs nothing.
- **`MessageBus`** is `publish(destination: str, event: Mapping[str, Any]) -> None`, per the django
  plan's Phase 10. It needs an async sibling for the same reason everything else here does.

### 0.2 — Scaffold

Standard workspace-member layout copied from `rn-forge-commons` (`pyproject.toml`, `README.md`,
`mkdocs.yml`, `docs/`, `src/rn_forge/azure/{__init__.py,py.typed}`, `tests/`). Resolve the namespace
question from the warning above. Add the no-extras import test.

**Phase 0 exit criteria:** the three commons protocol modules exist with tests; `uv sync` resolves;
`import rn_forge.azure` works with zero extras; namespace decision recorded; Pyright clean.

---

## Phase 1 — `credentials.py`: the credential chain

Nothing else in the package works without this, and it is the piece consumers most reliably get
wrong — usually by constructing a `DefaultAzureCredential` per request.

```python
@dataclass(frozen=True)
class AzureCredentialSettings:
    tenant_id: str | None = None
    client_id: str | None = None
    managed_identity_client_id: str | None = None
    authority: str | None = None
    exclude_interactive: bool = True
    exclude_shared_token_cache: bool = True


def get_credential(settings: AzureCredentialSettings | None = None) -> TokenCredential: ...
def get_async_credential(settings: AzureCredentialSettings | None = None) -> AsyncTokenCredential: ...
def close_credentials() -> None: ...
async def aclose_credentials() -> None: ...
```

Design calls:

- **Cache per settings value, not globally.** A process may legitimately need two credentials (two
  tenants). Key a module-level cache on the frozen settings dataclass — which is hashable precisely
  because it is frozen. `functools.lru_cache` over the dataclass is the whole implementation.
- **`exclude_interactive=True` by default.** `DefaultAzureCredential`'s interactive-browser and
  device-code legs are useful on a developer laptop and catastrophic in a container, where they
  manifest as a request that hangs rather than an error. Default to the non-interactive chain and let
  a developer opt in.
- **`exclude_shared_token_cache=True` by default.** The shared-token-cache credential is a frequent
  source of "works on my machine, 401s in CI" because it silently picks up a stale identity.
- **`close_credentials()` must exist and must be documented as required at shutdown.** Both a Django
  `AppConfig.ready`-shutdown hook and a FastAPI `lifespan` need somewhere to call it.
- **Return the SDK's `TokenCredential` type**, not a wrapper. This is the deliberate exception to
  Convention 3: every Azure client constructor takes a credential, and wrapping it would mean
  unwrapping it at every call site.

### 1.1 — The error-translation table

This belongs in Phase 1 because every later phase uses it. Put it in `rn_forge/azure/errors.py`:

```python
def translate(exc: BaseException) -> Exception:
    """Map an azure.core exception onto the workspace taxonomy. Never raises."""
```

Modelled on intellibench's `devops/azure/_errors.py::map_response_to_error`, which is the same idea
one layer down, and on its explicit table-in-a-docstring convention — reproduce that table:

| Azure exception | Becomes | Why |
| --- | --- | --- |
| `ResourceNotFoundError` | `SecretNotFound` / `ObjectNotFound` (per module) | The caller's key does not exist |
| `ResourceExistsError` | `DomainConflict`-shaped | A create raced |
| `ClientAuthenticationError` | An auth-failure `AppException` | Credentials are wrong or expired |
| `ServiceRequestError` | A transient `AppException` | Transport failure — retryable |
| `ServiceResponseError` | A transient `AppException` | Response failure — retryable |
| `HttpResponseError` 429 / 5xx | A transient `AppException` | Throttled or upstream down |
| `HttpResponseError` other | A non-transient `AppException` | Everything else |

Carry a `transient: bool` attribute on the raised exception so commons' resilience layer can classify
without re-inspecting the cause, and always chain with `raise ... from exc` so the original is
recoverable. **`translate` must never raise on an unrecognized input** — an error mapper that fails is
worse than no mapper, and intellibench's equivalent is explicit about this ("Never raises `KeyError`").

**Tests.** `tests/test_credentials.py` and `tests/test_errors.py` (`unit`, gated with
`pytest.importorskip("azure.identity")`): the cache returns the same object for equal settings and
different objects for different settings; exclusion flags reach the constructor (patch
`DefaultAzureCredential` and assert kwargs — do not construct a real chain); `close_credentials`
clears the cache and closes what it held; every row of the translation table, including an unmapped
exception type falling through to the generic case and a non-Azure exception passing through unchanged.

---

## Phase 2 — `keyvault.py`: `SecretStore` over Key Vault

The first phase with a consumer literally waiting for it: intellibench's `EnvSecretPort` docstring
says "Development only; a managed-identity or key-vault-backed adapter replaces this one, not the
port." This phase is that adapter.

```python
@dataclass(frozen=True)
class KeyVaultSettings:
    vault_url: str
    cache_ttl_seconds: float = 300.0


class KeyVaultSecretStore:      # satisfies commons SecretStore
    def __init__(self, settings: KeyVaultSettings, *, credential: TokenCredential | None = None) -> None: ...
    def get_secret(self, key: str) -> str: ...
    def close(self) -> None: ...


class AsyncKeyVaultSecretStore:  # satisfies commons AsyncSecretStore
    ...
```

Design calls:

- **Cache secrets with a TTL, default 5 minutes.** A Key Vault call is a network round trip with a
  throttling limit, and secrets are read on nearly every outbound request in intellibench's design
  (`AdoHttpClient._auth_headers` resolves the PAT through `SecretPort`). Without caching this adapter
  is a latency and throttling problem. **But make the TTL finite** — a rotated secret must eventually
  be picked up, so an unbounded cache is wrong even though it is what the naive implementation does.
- **Cache only successes.** A cached `SecretNotFound` turns a fixable misconfiguration into a
  five-minute outage after the fix lands.
- **Key-name translation.** Key Vault secret names allow only `[a-zA-Z0-9-]`, while consumers use
  names like `IB_ADO_PAT`. Ship a `name_mapper: Callable[[str], str]` parameter defaulting to a
  lowercase-and-hyphenate transform, and **document the default's exact behaviour with an example**,
  because a silent name transform is a debugging nightmare when it is wrong. Do not make it magic —
  a consumer passing `lambda k: k` must get literal names.
- **`credential=None` means "use `get_credential()`"**, so the common case is one line and the
  testable case is injection.

**Tests.** `tests/test_keyvault.py` (`unit`, `importorskip`): protocol conformance — the same test
body that exercises commons' `EnvSecretStore` passes against this one with a fake client; missing
secret raises `SecretNotFound`, not `ResourceNotFoundError`; cache hit avoids a second client call;
cache expiry triggers a refetch (inject a clock — do not sleep); a failure is not cached; the default
name mapper's exact transform; a custom mapper is used verbatim; `close()` closes the underlying
client; async variant covers the same list.

---

## Phase 3 — `blob.py`: `ObjectStore` over Blob Storage

Two consumers: intellibench's specified-but-unbuilt `BlobPort` (its docs call the migration to Azure
Blob "a mount configuration change", which is only true if the port exists first), and cims's
claim-check payload externalization — the pattern both the commons and django plans deferred for want
of exactly this second storage backend.

```python
@dataclass(frozen=True)
class BlobSettings:
    account_url: str
    container: str


class BlobObjectStore:          # satisfies commons ObjectStore
    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def url_for(self, key: str, *, expires_in: timedelta) -> str: ...
    def close(self) -> None: ...


class AsyncBlobObjectStore: ...
```

Design calls, in rough order of how easy they are to get wrong:

- **`url_for` needs a user-delegation SAS, not an account key.** Generating a SAS from an account key
  requires having the account key, which defeats managed identity. The correct path with a
  `TokenCredential` is `get_user_delegation_key()` then `generate_blob_sas(...)` with that key. This
  is fiddly, it is the reason `url_for` is the highest-risk member here, and it also means the
  delegation key itself should be cached (it has its own expiry, typically up to 7 days). Budget real
  time for this one method; the other four are thin.
- **Do not stream through memory by default and pretend otherwise.** `get` returning `bytes` is right
  for the claim-check use case (bounded payloads) and wrong for large objects. Either add
  `open(key) -> IO[bytes]` to the protocol or document the ceiling explicitly. intellibench's design
  already implies a ceiling — it inlines text to 100KB and uses a blob reference above it — so a
  bytes-oriented API is defensible; say so rather than leaving it implied.
- **Container creation is not this class's job.** Do not call `create_container` on first write.
  A library that provisions infrastructure as a side effect of a write is a library that fails in a
  read-only-permissions environment for an unrelated reason. Raise, with a message naming the
  container.
- **Key sanitation.** Blob names permit almost anything, including characters that break the URL in
  `url_for`. Validate and reject rather than silently mangle.
- **Error translation** through Phase 1's table: `ResourceNotFoundError` → `ObjectNotFound`.

**Tests.** `tests/test_blob.py`: conformance against the protocol with a fake client (`unit`);
round-trip put/get/exists/delete against **Azurite** (`integration`, skipped when unreachable);
`url_for` returns a URL containing the expected SAS query parameters and honours `expires_in`
(assertable against Azurite); missing blob raises `ObjectNotFound`; delegation-key caching avoids a
second call; oversized-key and invalid-key rejection; async variant covers the same list.

---

## Phase 4 — GATED: `servicebus.py`, `MessageBus` over Service Bus

### 4.1 — The gate

**Do not start until all three hold.** Record the answers in the PR before writing code:

1. **The django plan's Phase 10 has landed, or is landing in the same change.** This class implements
   `MessageBus`. If that protocol does not exist and is not committed, this phase is designing a
   protocol from its only implementation — the exact failure mode every plan in this workspace warns
   about. (intellibench's own ADR-0040, "a port requires a second supplier", says the same thing from
   the other direction.)
2. **cims is actually going to adopt it.** cims has a working `AzureServiceBus` today. Replacing
   working code with a library version buys nothing unless a second consumer is real. If cims is the
   only consumer forever, the honest answer is that its adapter should stay where it is.
3. **There is a way to test it without a network.** Check whether a usable first-party Service Bus
   emulator exists and works in this workspace's CI *at the time you start* — the answer has changed
   recently and this document should not be trusted on it. If there is none, the fallback is
   conformance tests against a fake plus a manually-verified note, which is weaker than Phase 3 gets
   and should be an explicit, recorded acceptance.

### 4.2 — If the gate passes

```python
@dataclass(frozen=True)
class ServiceBusSettings:
    namespace_url: str            # <namespace>.servicebus.windows.net
    default_destination: str | None = None


class ServiceBusMessageBus:       # satisfies commons MessageBus
    def publish(self, destination: str, event: Mapping[str, Any]) -> None: ...
    def close(self) -> None: ...


class AsyncServiceBusMessageBus: ...
```

- **Cache one sender per destination**, created lazily, closed on `close()`. Creating a sender per
  publish is a per-message AMQP link setup and it is the standard way this integration is made slow.
- **Serialize the event to JSON and set `content_type: application/json`.** Both consumers publish
  CloudEvents envelopes as dicts.
- **Map CloudEvents fields onto Service Bus message properties** where they correspond —
  `message_id` from the envelope's `id`, `correlation_id` from the correlation ContextVar, `subject`.
  This is what makes DLQ inspection and correlation work at all, and it is the thing a naive
  `publish(json.dumps(event))` loses.
- **Do not implement a consumer/receiver in this phase.** cims's `run_consumer` and `resubmit_dlq`
  management commands stay in cims. Publishing is the half the outbox relay needs; receiving is a
  process-lifecycle concern with far more surface, and it should have its own gate.

**Tests.** Conformance against `InMemoryMessageBus`'s test body with a fake sender; sender caching
(publish twice to one destination → one sender created); message properties populated from the
envelope; `close()` closes every cached sender; error translation for a throttled publish.

---

## Phase 5 — GATED: `monitor.py`, OpenTelemetry export to Azure Monitor

### 5.1 — The gate

**Build only if a consumer asks for it, and only after checking what it actually replaces.**
`azure-monitor-opentelemetry` is itself a distribution that configures OTel from environment
variables; a wrapper around a configurator is a thin thing on top of a thin thing. The plausible value
is a single call that wires the exporter *and* the workspace's own conventions (correlation ID as a
span attribute, service name from settings). If that is not what is wanted, there is no phase here.

### 5.2 — If the gate passes

```python
@dataclass(frozen=True)
class MonitorSettings:
    connection_string: str
    service_name: str
    service_version: str | None = None
    environment: str | None = None


def configure_monitor(settings: MonitorSettings, *, enable_logging: bool = False) -> None: ...
```

- **`enable_logging=False` by default.** Both consumers already have a logging stack (structlog); an
  OTel logging handler installing itself alongside is duplicate output at best.
- **Bind the correlation ID as a span attribute** using `rn_forge.web.context` — except that would
  make this package depend on `rn-forge-web`, which the scope rule forbids. Resolve by having
  `configure_monitor` accept a `correlation_provider: Callable[[], str | None] | None = None` that a
  web consumer wires to `get_correlation_id`. That keeps the dependency direction and is one
  parameter.
- **Idempotent.** Calling it twice must not install two exporters; guard with a module-level flag and
  say so.

**Tests.** `unit`, `importorskip`: `configure_monitor` is idempotent; settings reach the configurator
(patch it); `correlation_provider` is invoked and its value lands on the span; `enable_logging=False`
installs no logging handler.

---

## Deferred — do not build these yet

- **Azure OpenAI adapter.** intellibench has a complete, REST-only, SDK-free one
  (`llm/azure_openai/adapter.py` + `settings.py` + `_errors.py`) behind an `LLMPort` with
  `ChatMessage`/`CompletionResult`/`EmbeddingResult`/`TokenUsage`. The adapter is good; the *port* is
  the hard part and it has one supplier. **Trigger:** a second LLM provider adapter in view (Anthropic,
  Bedrock, or OpenAI direct), at which point the port design has evidence and this becomes an
  `rn-forge-llm` package with `rn-forge-azure` supplying one adapter. Note that intellibench's
  deliberate no-SDK stance means the adapter would be portable to that package almost unchanged.
- **Azure DevOps adapter.** See "Things deliberately NOT in this package". The extraction that *should*
  happen is its generic machinery into commons' resilience module — see the web plan's §A.3.
- **Managed-identity authentication for PostgreSQL.** Both consumers use password auth today
  (intellibench's `IB_DATABASE_URL`/`IB_APP_DATABASE_URL`). Entra-token-based Postgres auth means
  fetching a token and refreshing it inside the connection pool's lifecycle, which is genuinely
  fiddly and genuinely valuable — but nobody is asking for it. **Trigger:** a deployment that
  forbids database passwords.
- **Entra ID authentication classes.** Covered by generic OIDC plus a documented `jwks_url` recipe.
  Not code. See the exclusions above.
- **A `LockPort` implementation over blob leases.** intellibench declares `LockPort` and implements it
  over Postgres rows. Blob leases are the classic distributed-lock primitive on Azure and would be a
  legitimate second supplier — but its `LockPort` is Postgres-shaped (heartbeats, holder pid,
  `os.kill(pid, 0)` liveness) and would need redesign first. **Trigger:** a multi-host deployment,
  which is what breaks the current pid-based staleness check anyway.

---

## Final checklist before calling this done

- [ ] The three commons protocol modules (`secrets`, `objects`, `messaging`) exist, with tests, before
      any adapter here implements them
- [ ] `uv sync --all-extras && uv run pytest packages/rn-forge-azure` green
- [ ] `uv run pyright` clean across every package
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `import rn_forge.azure` succeeds with **no** extras installed; each module raises a clear,
      actionable error naming the missing extra when its SDK is absent
- [ ] No `azure.*` type appears in any public signature except the credential objects in
      `credentials.py` — grep the module `__all__`s and check each symbol's annotations
- [ ] Every adapter passes the same conformance test body as its commons in-memory counterpart
- [ ] No test makes a network call; emulator-backed tests are marked `integration` and skip cleanly
      when the emulator is absent
- [ ] Every client class closes cleanly and is context-manager-usable; no module-level client
      singletons
- [ ] Dependency floors verified against actually-resolved versions, not guessed
- [ ] `.importlinter` carries `azure-depends-on-commons-only` and `uv run lint-imports` is green —
      no import of `rn_forge.web`, `rn_forge.django`, `rn_forge.cli` or `rn_forge.tooling`
- [ ] Protocols are imported from the commons facade (`from rn_forge.commons import SecretStore`),
      not from `rn_forge.commons.integration.*` — D55 froze the class names, not the module paths
- [ ] The commons dependency is a pinned direct URL at a release tag (kiln D46), and the installation
      guide gives the full `git+…@tag` line for each extra rather than `uv add rn-forge-azure`
- [ ] The package is wired into pykit's repo shape per alignment §6
- [ ] The namespace decision (`rn_forge.azure` vs `rn_forge.azure_adapters`) recorded with its reason
- [ ] Phase 4 and Phase 5 gate outcomes recorded (built, or abandoned with the reason written down)
- [ ] `CLAUDE.md`'s repository overview describes the package and its extras
- [ ] Nothing committed or pushed — leave the working tree for review

## Not in this plan (deliberately deferred)

- **Changes to cims or intellibench.** Their adoption is separate work in their own repositories.
  Design against their call sites; do not modify them.
- **The commons protocol modules themselves.** Specified in the web plan's §A.2, built there, checked
  as a prerequisite here.
- **The commons resilience redesign** (web plan §A.3), which is where the generic half of the Azure
  DevOps adapter should land.
