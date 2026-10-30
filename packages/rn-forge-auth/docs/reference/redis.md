# Redis

Requires the `redis` extra:

```bash
uv add "rn-forge-auth[redis]"
```

`rn_forge.auth.redis` is not re-exported from `rn_forge.auth` — import it
directly:

```python
from rn_forge.auth.redis import RedisSessionStore
```

::: rn_forge.auth.redis
