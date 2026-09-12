# Quickstart

```python
from fastapi import Depends, FastAPI

from rn_forge.fastapi import (
    Page,
    WireModel,
    health_router,
    install_problem_schema,
    operation_id,
    page_params,
    register_problem_handlers,
)
from rn_forge.web import CorrelationIdMiddleware, default_registry

registry = default_registry()

app = FastAPI(generate_unique_id_function=operation_id)
app.add_middleware(CorrelationIdMiddleware)
register_problem_handlers(app, registry=registry)
install_problem_schema(app, registry=registry)
app.include_router(health_router(checks={"db": db_reachable}, required=["db"]))


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
