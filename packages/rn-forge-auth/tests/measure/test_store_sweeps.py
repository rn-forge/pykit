from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta

import pytest
from rn_forge.auth import (
    InMemoryReplayStore,
    InMemorySessionStore,
    InMemoryTransactionStore,
    LoginTransaction,
    SessionInfo,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("PYKIT_MEASURE_OUT"), reason="measurement run only"
)

Measure = Callable[
    [str, dict[str, object], str], AbstractContextManager[dict[str, int | float]]
]


@pytest.mark.parametrize("store", ["replay", "transaction", "session"])
@pytest.mark.parametrize("records", [1000, 4000, 16000])
def test_store_sweeps(measure: Measure, store: str, records: int) -> None:
    ttl = timedelta(hours=1)
    now = datetime.now(UTC)
    with measure(
        "auth_store_sweep", {"store": store, "records": records}, "cpu"
    ) as counts:
        if store == "replay":
            replay = InMemoryReplayStore()
            for number in range(records):
                replay.record_once(str(number), ttl=ttl)
        elif store == "transaction":
            transactions = InMemoryTransactionStore()
            for number in range(records):
                transactions.save(
                    LoginTransaction(
                        id=str(number),
                        provider="idp",
                        return_to="/",
                        created_at=now,
                        state="s",
                        nonce="n",
                        code_verifier="v",
                    ),
                    ttl=ttl,
                )
        else:
            sessions = InMemorySessionStore()
            for _ in range(records):
                sessions.create(
                    SessionInfo(
                        account_id="acct",
                        session_version=1,
                        provider="idp",
                        issuer="https://issuer",
                        external_subject="sub",
                        created_at=now,
                        expires_at=now + ttl,
                    ),
                    idle_ttl=ttl,
                )
        counts["operations"] = records
