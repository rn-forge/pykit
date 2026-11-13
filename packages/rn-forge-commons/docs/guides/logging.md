# Logging

Initialize logging once near process startup:

```python
from rn_forge.commons import AppLogger

logger = AppLogger.initialize(
    root_logger_name="billing",
    level=AppLogger.INFO,
    enable_color=True,
)
```

## Console rendering

The console handler is selected automatically from `use_json`, `enable_color`,
and TTY detection (`isatty`), in this precedence order:

1. `use_json=True` → a JSON formatter (`json` extra) on a plain `StreamHandler`.
   Machine output is never decorated — JSON always wins over Rich.
1. `enable_color=True` (default when stdout is a TTY) →
   [`rich.logging.RichHandler`][rich], with Rich's own time/level/path columns
   and `rich.traceback` exception rendering (`rich_tracebacks=True` by
   default, `show_locals=False` since tracebacks routinely carry credentials
   in locals).
1. Otherwise → a plain `StreamHandler` with the full format string.

The **file handler is always a plain `logging.FileHandler`** with the full
format string — never Rich — regardless of what the console handler is doing, so
log files stay free of ANSI codes and column wrapping.

verboselogs' custom levels (`TRACE`, `SPAM`, `VERBOSE`, `NOTICE`, `SUCCESS`) are
styled via a built-in Rich theme. Override per-level styles with `level_styles`:

```python
AppLogger.initialize(
    root_logger_name="billing",
    level_styles={"critical": "bold white on red"},
)
```

Log messages are interpolated with untrusted values, so Rich markup is disabled
in the logging path (`markup=False`) — a value containing `[red]` is emitted
literally, never styled or crashing the markup parser.

Get module loggers later:

```python
logger = AppLogger.get_logger(__name__)
logger.info("request_id={}", request_id)
```

Audit a single method:

```python
logger = AppLogger.get_logger(__name__)

@logger.audit_method(exclude=["password"])
def authenticate(user: str, password: str) -> bool:
    return True
```

Audit a class:

```python
@logger.audit_class(exclude=["token"])
class Client:
    def fetch(self, token: str, resource_id: str) -> dict:
        return {}
```

## Secret redaction

Redaction is **on by default**: `AppLogger.initialize()` registers a
`RedactFilter` on the console and file handlers, so JSON, Rich and plain output
all apply it. Pass `redact=False` (or `LoggingConfig.build(redact=False)`) to
turn it off. Enabling it changes log output, so a deployment that parses logs
for a value now sees `[redacted]` in its place.

The filter redacts three things on each record, assigning new objects and never
mutating what the caller passed:

- the message, when it is a string;
- `args`, keeping its tuple or mapping shape and any non-string values, so
  `%d`-style formatting still works;
- every `extra` field.

It decides what to redact in two ways:

- **By key.** A value stored under a key whose *final segment* is
  `authorization`, `cookie`, `password`, `secret` or `token` (plural allowed,
  any case) is replaced wholesale with `[redacted]`, whatever its type.
  Segments split on `_`, `-`, `.` and camelCase boundaries, so `access_token`,
  `accessToken`, `client_secret`, `set-cookie` and `x-csrf-token` are redacted
  while `token_count`, `password_hint` and `cookie_jar` are not. `None` and
  `""` are kept.
- **By value.** In any string, under any key, the credential in `Bearer <token>`
  or `Basic <credential>` and the password in `scheme://user:password@host`
  are replaced, and so is the password in `scheme://:password@host`. The
  scheme word and the rest of the text stay. A credential must contain a
  digit, a symbol or an inner capital, so prose such as "bearer token expired"
  is kept, and so is a short all-lowercase token: log it under a matching key
  instead.

Nested dicts, lists and tuples are redacted at any depth. Use `redact()` to
apply the same rules to your own data, and a `RedactionPolicy` to change them:

```python
import re
from rn_forge.commons import RedactFilter, RedactionPolicy, redact

policy = RedactionPolicy(re.compile(r"^ssn$"), scrub_credentials=True, scrub_url_passwords=True)
redact({"ssn": "123-45-6789", "user": "ann"}, policy=policy)
# {'ssn': '[redacted]', 'user': 'ann'}
```

`AppLogger.initialize()` always uses the default policy. To use another, build
your own handlers and attach `RedactFilter(policy)` to them.

**Exception tracebacks are not redacted.** Formatted tracebacks and exception
messages can carry secrets and pass through unchanged; keep credentials out of
exception text.

With the `structlog` extra,
`rn_forge.commons.logging.structlog.redact_processor` redacts each event
dictionary before it is rendered. `StructLogger` installs it automatically, and
`redact=False` does not remove it; add it yourself to any other structlog chain,
ahead of the renderer.

## StructLogger vs. AppLogger.get_logger

`AppLogger.get_logger(__name__)` is for one-off, unstructured log calls. Reach
for [`StructLogger`](../reference/logging/structlog.md) (`structlog` extra)
instead when you want context — a request id, a tenant — bound once and carried
across a chain of log calls:

```python
from rn_forge.commons.logging.structlog import StructLogger

log = StructLogger(__name__).bind(request_id=request_id)
log.info("processing order", order_id=order_id)
log.success("order processed")
```

Every `StructLogger` call still flows through whatever `AppLogger.initialize()`
configured — the same Rich console, file, or JSON output a plain
`AppLogger.get_logger(__name__)` call would use. `StructLogger` adds only
context binding (`bind`/`unbind`/`new`) and structured keyword fields on top; it
does not call `dictConfig` or install its own formatter. Call
`AppLogger.initialize()` before the first `StructLogger` log call — the
underlying logger is resolved lazily, on first use, so construction order
doesn't matter, only which one logs first.

[rich]: https://rich.readthedocs.io/en/stable/logging.html
