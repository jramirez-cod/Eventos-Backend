"""
Script para crear tablas del esquema en la BD configurada en .env.
Usar solo en desarrollo/test local.
"""
from pathlib import Path
import sys
import asyncio

# On Windows, the default ProactorEventLoop is incompatible with psycopg async.
# Switch to the SelectorEventLoop policy when running locally on Windows.
if sys.platform == "win32":
    try:
        from asyncio import WindowsSelectorEventLoopPolicy

        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    except Exception:
        # If policy class is not available, continue and let asyncio choose.
        pass

# Ensure project root is on sys.path so `app` package imports work when
# running this script directly from scripts/ (matching bootstrap_security.py).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.ext.asyncio import create_async_engine
from app.db.base import Base
from app.core.config import settings


async def create_tables() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_tables())
