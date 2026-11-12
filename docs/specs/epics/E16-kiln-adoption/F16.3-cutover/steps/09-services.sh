#!/usr/bin/env bash
# S16.3.1 step 9: services.
set -euo pipefail
python3 - <<'PY'
import pathlib

PG = '''[tool.workspace-ci.integration.postgres]
image = "postgres:17"
ports = ["5432:5432"]
health-cmd = "pg_isready -U ci"

[tool.workspace-ci.integration.postgres.env]
POSTGRES_USER = "ci"
POSTGRES_PASSWORD = "ci"
POSTGRES_DB = "ci"

[tool.workspace-ci.integration.postgres.expose]
# The `postgres`-marked tests read this DSN and skip without it.
{key} = "postgresql://ci:ci@localhost:5432/ci"
'''
REDIS = '''[tool.workspace-ci.integration.redis]
image = "redis:7"
ports = ["6379:6379"]
health-cmd = "redis-cli ping"

[tool.workspace-ci.integration.redis.expose]
# The Redis tests read this URL and skip without it.
RN_FORGE_AUTH_REDIS_URL = "redis://localhost:6379/0"
'''
KEYCLOAK = '''
[tool.workspace-ci.integration.keycloak]
image = "quay.io/keycloak/keycloak:26.4.7"
command = ["start-dev", "--import-realm"]
ports = ["127.0.0.1:8080:8080"]
volumes = ["tests/broker/realms:/opt/keycloak/data/import:ro"]
health-cmd = "exec 3<>/dev/tcp/127.0.0.1/9000 && printf 'GET /health/ready HTTP/1.1\\\\r\\\\nHost: localhost\\\\r\\\\nConnection: close\\\\r\\\\n\\\\r\\\\n' >&3 && grep -q '\\"status\\": \\"UP\\"' <&3"
# The broker tests skip unless RN_FORGE_AUTH_KEYCLOAK_URL is set.
pytest-args = ["-p", "no:randomly"]
health-wait = 300

[tool.workspace-ci.integration.keycloak.env]
KC_HEALTH_ENABLED = "true"

[tool.workspace-ci.integration.keycloak.expose]
RN_FORGE_AUTH_KEYCLOAK_URL = "http://127.0.0.1:8080"
'''


def edit(path, old, new):
    file = pathlib.Path(path)
    text = file.read_text()
    assert text.count(old) == 1, (path, old)
    file.write_text(text.replace(old, new))


edit(
    "packages/rn-forge-sqlalchemy/pyproject.toml",
    '[tool.workspace-ci.postgres]\n# The `postgres`-marked tests read this DSN and skip without it.\nenv = "RN_FORGE_TEST_POSTGRES_DSN"\n',
    PG.format(key="RN_FORGE_TEST_POSTGRES_DSN"),
)
edit(
    "packages/rn-forge-django/pyproject.toml",
    '[tool.workspace-ci.postgres]\n# The `postgres`-marked tests read this DSN and skip without it.\nenv = "RN_FORGE_DJANGO_TEST_DATABASE_URL"\n',
    PG.format(key="RN_FORGE_DJANGO_TEST_DATABASE_URL"),
)
edit(
    "packages/rn-forge-auth/pyproject.toml",
    '[tool.workspace-ci.redis]\n# The Redis tests read this URL and skip without it.\nenv = "RN_FORGE_AUTH_REDIS_URL"\n',
    REDIS,
)
auth = pathlib.Path("packages/rn-forge-auth/pyproject.toml")
auth.write_text(auth.read_text() + KEYCLOAK)
PY
