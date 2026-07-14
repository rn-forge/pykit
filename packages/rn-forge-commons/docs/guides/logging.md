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
