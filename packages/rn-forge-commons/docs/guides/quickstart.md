# Quickstart

```python
from dataclasses import dataclass

from rn_forge.commons import (
    AppLogger,
    Config,
    DataclassMixin,
    DictUtils,
    JsonUtils,
)

logger = AppLogger.initialize(root_logger_name="example")
cfg = Config("config")

payload = {"service": {"host": "localhost", "port": 8080}}
host = DictUtils.get(payload, "service.host")

@dataclass
class ServiceConfig(DataclassMixin):
    host: str
    port: int

service = ServiceConfig.from_dict(cfg.get("service", default={}))
logger.info("service={} host={}", JsonUtils.serialize(service.as_dict()), host)
```

Common imports:

```python
from rn_forge.commons import (
    AppException,
    AppLogger,
    AppUtils,
    Config,
    DataclassMixin,
    DictUtils,
    DocumentUtils,
    JsonUtils,
    ListUtils,
    PathUtils,
    Process,
    Task,
    TaskPool,
    YamlUtils,
)
```
