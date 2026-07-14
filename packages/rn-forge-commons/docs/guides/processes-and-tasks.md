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
