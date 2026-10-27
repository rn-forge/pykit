# OIDC

Requires the `oidc` extra:

```bash
uv add "rn-forge-auth[oidc]"
```

`rn_forge.auth.oidc` is not re-exported from `rn_forge.auth` — import it
directly:

```python
from rn_forge.auth.oidc import OidcAuthenticator
```

::: rn_forge.auth.oidc
