# Quickstart

```python
from fastapi import Depends

from rn_forge.fastapi import (
    Page,
    WireModel,
    AppConfig,
    page_params,
    create_app,
)
from rn_forge.web import default_registry

app = create_app(
    AppConfig(
        registry=default_registry(),
        checks={"db": db_reachable},
        required_checks=("db",),
    ),
    title="Orders",
)


class OrderOut(WireModel):
    order_id: str          # "orderId" on the wire


@app.get("/orders")
async def orders_list(page=Depends(page_params(cap=100, default=20))) -> Page[OrderOut]:
    size, cursor = page
    ...
```

That is an application with problem-details errors, a correlation ID, a
generated client that has an error type, readiness checks and AIP-158
pagination. The [wiring guide](wiring.md) explains each line and the rules they
depend on.
