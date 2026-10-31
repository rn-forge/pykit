# Processes and Tasks

## Subprocesses

```python
from rn_forge.commons import Process

result = Process.execute("python-version", "python", "--version", fail_on_error=False)
if not result.succeeded:
    raise RuntimeError(result.stderr or result.stdout)
```

Shortcuts:

- `Process.python(...)`
- `Process.mvn(...)`
- `Process.npm(...)`
- `Process.az(...)`
- `Process.pwsh(...)`

## Tasks

```python
from rn_forge.commons import Task, TaskPool

class EchoTask(Task):
    def run(self) -> None:
        print(self.get_prop("message"))

failed = (
    TaskPool(max_workers=2)
    .submit(EchoTask("echo-1", message="hello"))
    .shutdown(fail_on_error=False)
)
```

Use `fail_on_error=True` when task failures should raise `AppException`.

## Thread actor

`ThreadActor` owns one resource on a dedicated thread. Some libraries, such as
a SQLite connection or a single-session SDK, must be created, used and closed
on one thread. The actor guarantees this: `factory` builds the resource on the
owner thread, every call runs there one at a time in queue order, and `on_close`
releases it there after the last queued call.

```python
import sqlite3

from rn_forge.commons import ThreadActor

actor = ThreadActor(
    lambda: sqlite3.connect("app.db"),
    name="db",
    on_close=lambda conn: conn.close(),
)
future = actor.submit(lambda conn: conn.execute("SELECT 1").fetchone())
row = future.result()

# In async code, await the same call without blocking the event loop.
row = await actor.run(lambda conn: conn.execute("SELECT 1").fetchone())

actor.close()
```

- An exception from `factory` is raised by the constructor as `AppException`
  with the original as `__cause__`. Exceeding `startup_timeout` also raises
  `AppException`.
- An exception from a call is set on that call's future and does not stop the
  actor.
- `close()` runs the calls already queued, then `on_close`, and is idempotent.
  A `submit` after it raises `AppException`.
- The owner thread is a daemon, so a forgotten `close()` does not block
  interpreter exit; the resource is then not closed.

### Keep the actor short

A caller must never hold the actor during a network call or other long external
work. Every other caller waits behind it, and the kit cannot detect a violation.
Do that work outside the actor and pass the results in.

When one job touches many files, split it into three phases:

1. Work on the actor.
1. A cheap projection to plain data, also on the actor.
1. Fan out off the actor, for example with `TaskPool`.
