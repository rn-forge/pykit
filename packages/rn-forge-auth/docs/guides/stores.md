# Stores

Four protocols hold server-side state. Each has an in-memory implementation in
the core and a Redis implementation in `rn_forge.auth.redis`.

| Protocol | Holds | Redis operation it relies on |
| -- | -- | -- |
| `TransactionStore` | Login transactions between the redirect and the callback. `consume` returns the transaction to exactly one caller. | `SET ... EX` to save, `GETDEL` to consume |
| `SessionStore` | Login sessions under random IDs. `create`, `get`, `touch`, `delete` and `rotate`. | `SET ... EX`, `GET`, `EXPIRE`, `GETDEL` |
| `ReplayStore` | Single-use values, such as logout-token `jti`, and revoked `(issuer, sid)` pairs. | `SET key 1 NX EX` for `record_once`, `SET ... EX` and `EXISTS` for revoked `sid` values |
| `AuthorizationVersions` | The counters behind `AuthorizationContextCache`. | `INCR` per account and for the global counter, `MGET` to read |

A session ends at its idle expiry or at `SessionInfo.expires_at`, whichever
comes first. `get` does not extend the idle expiry, so a poll cannot keep an
idle session alive; `touch` extends it, never past `expires_at`. `rotate`
returns a new ID and leaves the old one unreadable. The stores do not check
session versions or revoked `sid` values; the framework binding does that after
`get`.

```python
from redis import Redis
from rn_forge.auth.redis import RedisSessionStore, RedisTransactionStore

client = Redis.from_url("redis://localhost:6379/0")
sessions = RedisSessionStore(client)
transactions = RedisTransactionStore(client, prefix="myapp-auth:")

session_id = sessions.create(session_info, idle_ttl=timedelta(minutes=30))
```

## Supported storage

Transactions, replay records and revoked `sid` values must be shared by every
worker, so a store used by more than one process must be backed by shared
storage whose operations above are atomic. The in-memory stores
(`InMemoryTransactionStore`, `InMemorySessionStore`, `InMemoryReplayStore` and
`InMemoryAuthorizationVersions`) are thread-safe but are not safe across
processes; use them in tests and single-process development only. The Redis
stores need Redis 6.2 or later (for `GETDEL`).

Every Redis store takes a client and a key `prefix` (`"rn-forge-auth:"` by
default). Expiries are whole seconds, rounded up, and at least one. A session
is stored as JSON, and a missing, expired or rotated-away key reads as absent.

## Authorization versions

`AuthorizationVersions` holds the counters behind `AuthorizationContextCache`
(see [Contracts](contracts.md#authorization-context-and-cache)): a version per
account and a global version, read together by `current(account_id)` and raised
by `bump(account_id)` and `bump_all()`. `InMemoryAuthorizationVersions` is local
to the process, so with several workers a bump reaches only the worker that made
it and the others rely on the cache TTL. `RedisAuthorizationVersions` shares the
counters through `INCR` and `MGET`.
