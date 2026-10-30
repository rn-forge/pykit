# Testing

Requires the `oidc` extra:

```bash
uv add "rn-forge-auth[oidc]"
```

`rn_forge.auth.testing` is not re-exported from `rn_forge.auth` — import it
directly:

```python
from rn_forge.auth.testing import FakeOidcProvider
```

::: rn_forge.auth.testing
