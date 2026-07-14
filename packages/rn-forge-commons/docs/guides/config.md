# Config

`Config` loads one file or a directory of JSON or YAML files, deep-merges them, and optionally resolves references.

Example YAML:

```yaml
service:
  host: localhost
  port: 8080

service_url: "https://${service.host}:${service.port}"

profiles:
  base:
    debug: true
    timeout: 30

production:
  __extends__: "@{profiles.base}"
  debug: false
```

Usage:

```python
from rn_forge.commons import Config

cfg = Config("config")
url = cfg.get("service_url")
production = cfg.get("production")
```

Reference forms:

- `${path}` scalar interpolation
- `@{path}` dict splice
- `#{path}` list splice
- `__extends__` dict inheritance
