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

The console handler is selected automatically from `use_json`, `enable_color`, and TTY detection
(`isatty`), in this precedence order:

1. `use_json=True` → a JSON formatter (`json` extra) on a plain `StreamHandler`. Machine output is
   never decorated — JSON always wins over Rich.
2. `enable_color=True` (default when stdout is a TTY) → [`rich.logging.RichHandler`][rich], with
   Rich's own time/level/path columns and `rich.traceback` exception rendering
   (`rich_tracebacks=True` by default, `show_locals=False` since tracebacks routinely carry
   credentials in locals).
3. Otherwise → a plain `StreamHandler` with the full format string.

The **file handler is always a plain `logging.FileHandler`** with the full format string — never
Rich — regardless of what the console handler is doing, so log files stay free of ANSI codes and
column wrapping.

verboselogs' custom levels (`TRACE`, `SPAM`, `VERBOSE`, `NOTICE`, `SUCCESS`) are styled via a
built-in Rich theme. Override per-level styles with `level_styles`:

```python
AppLogger.initialize(
    root_logger_name="billing",
    level_styles={"critical": "bold white on red"},
)
```

Log messages are interpolated with untrusted values, so Rich markup is disabled in the logging
path (`markup=False`) — a value containing `[red]` is emitted literally, never styled or crashing
the markup parser.

[rich]: https://rich.readthedocs.io/en/stable/logging.html

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

## StructLogger vs. AppLogger.get_logger

`AppLogger.get_logger(__name__)` is for one-off, unstructured log calls. Reach for
[`StructLogger`](../api/structlogger.md) (`structlog` extra) instead when you want context —
a request id, a tenant — bound once and carried across a chain of log calls:

```python
from rn_forge.commons.structlogger import StructLogger

log = StructLogger(__name__).bind(request_id=request_id)
log.info("processing order", order_id=order_id)
log.success("order processed")
```

Every `StructLogger` call still flows through whatever `AppLogger.initialize()` configured — the
same Rich console, file, or JSON output a plain `AppLogger.get_logger(__name__)` call would use.
`StructLogger` adds only context binding (`bind`/`unbind`/`new`) and structured keyword fields on
top; it does not call `dictConfig` or install its own formatter. Call `AppLogger.initialize()`
before the first `StructLogger` log call — the underlying logger is resolved lazily, on first use,
so construction order doesn't matter, only which one logs first.
