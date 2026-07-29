"""Create/upgrade LangGraph checkpoint tables in the agent_runtime schema."""

from __future__ import annotations

import asyncio

from app.core.settings import settings
from app.runtime.postgres_store import PostgresRuntimeStore


async def main() -> None:
    if not settings.AGENT_RUNTIME_DATABASE_URL:
        raise SystemExit("AGENT_RUNTIME_DATABASE_URL is required")
    store = await PostgresRuntimeStore.open(
        settings.AGENT_RUNTIME_DATABASE_URL
    )
    try:
        await store.build_checkpointer(setup=True)
        readiness = await store.validate_ready()
        if not readiness["checkpoint_ready"]:
            raise SystemExit("checkpoint schema setup failed")
        print("agent_runtime checkpoint schema is ready")
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
