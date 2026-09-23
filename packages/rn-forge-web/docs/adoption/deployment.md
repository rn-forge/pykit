# Deployment

**Normative for operators.** `api-conventions.md` is the wire contract; this page is its
companion for whoever deploys the service. The kit's code stays host-neutral — nothing in
`rn-forge-web`, `rn-forge-fastapi` or `rn-forge-django` knows which platform it runs on. This page
maps that one contract onto each host's own mechanisms.

The facts below were read from each vendor's documentation on 2026-09-22. Platform documentation
changes; recheck them when editing this page.

## Health probes

`/livez` answers liveness and `/readyz` answers readiness (`api-conventions.md` §6). Every host
judges a probe by status code and response time only, never the body.

| Host | Probes it offers | Map to | Notes |
| --- | --- | --- | --- |
| Kubernetes (also AKS, GKE, Cloud Run, Azure Container Apps) | `livenessProbe`, `readinessProbe`, `startupProbe` | `/livez`, `/readyz`, `/livez` | Set `timeoutSeconds` ≥ 3, above the 2 s check timeout the kit defaults to. A `preStop` sleep lets endpoint removal propagate before `SIGTERM`. |
| App Engine flexible | `liveness_check`, `readiness_check` in `app.yaml`, each with a configurable `path` | `/livez`, `/readyz` | Only `200` counts as healthy. The default timeout is 4 s. `/_ah/health` legacy checks are deprecated. An instance is downscaled 25 s after the shutdown signal. |
| Azure App Service | **One** Health check path; any 2xx is healthy; pinged every minute; after N failures (`WEBSITE_HEALTHCHECK_MAXPINGFAILURES`, 2–10) the instance leaves the load balancer, and after an hour it is replaced | `/readyz` | Microsoft's guidance is that the path checks critical dependencies and returns 2xx only once warm, which is readiness. It never removes more than `WEBSITE_HEALTHCHECK_MAXUNHEALTHYWORKERPERCENT` (default 50) of instances, and none when all are unhealthy, so a shared dependency outage does not drain the app. Health check does not follow redirects: enable **HTTPS Only** rather than an app-level HTTPS redirect, and ping the default domain. The path must allow anonymous access. |
| App Engine standard | **No** configurable health checks | none | Point an uptime check at `/readyz` for monitoring. Warmup requests (`/_ah/warmup`, via `inbound_services: warmup`) and manual/basic-scaling `/_ah/start` are platform hooks, so the application registers them if it wants them. `SIGTERM` gives about 2 s before `SIGKILL`. |

App Engine standard's manual/basic-scaling `/_ah/start` hook: whether the platform counts a 404
response as a successful start is unconfirmed against current vendor docs. Register the safe
default — a handler that always answers 200 — rather than leaving the route unhandled:

```python
@app.get("/_ah/start")
async def ah_start() -> dict[str, str]:
    return {"status": "ok"}
```

## Cross-cutting points

- **TLS terminates at the host's front end.** Trust `X-Forwarded-Proto` and `X-Forwarded-For`:
  uvicorn `--proxy-headers --forwarded-allow-ips`, Django `SECURE_PROXY_SSL_HEADER` and
  `USE_X_FORWARDED_HOST`. Otherwise `Location`, `Link` and the api-catalog's links (§14) carry
  `http://`. Leave the security-headers `hsts` flag (§15) off unless the host doesn't set HSTS
  itself.
- **CORS.** Azure App Service has a platform CORS feature. Microsoft's guidance is not to combine
  it with application CORS, so use the kit's CORS module (§16) and leave the platform's off.
- **Body size.** Each host's front end has its own cap. The kit's request-body limit (§11) is the
  application's, and it should sit at or below the host's.
- **Port.** The server binds to the host's port variable (`PORT` on App Engine and Cloud Run,
  `WEBSITES_PORT` for Azure custom containers). That is server configuration, not kit code.
- **Logs and traces.** All four hosts collect JSON logs from stdout. W3C `traceparent` is
  understood by Cloud Trace and Azure Monitor alike, which is one reason OpenTelemetry is the
  host-neutral choice for distributed tracing when the workspace adopts it.

## Not built

Helpers for one host only — validating Azure's `x-ms-auth-internal-token` on the health path, or
an App Engine `/_ah/warmup` handler — are not standards, so the kit does not ship them. Each is a
short snippet the application adds when it needs it, following the pattern above for `/_ah/start`.
