"""Elimina la restriccion de "un solo contacto principal por empresa".

Regla de negocio nueva: una empresa puede tener varios contactos marcados
como principal (por ejemplo, para que el codigo de acceso llegue a 2 o 3
personas). Este script quita el indice unico parcial que lo impedia en
bases creadas antes del cambio. Es idempotente: si el indice ya no existe,
no hace nada.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402


async def drop_index() -> bool:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            existe = await conn.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_indexes "
                    "WHERE indexname = 'uq_contacto_principal_por_empresa')"
                )
            )
            if existe:
                await conn.execute(
                    text("DROP INDEX uq_contacto_principal_por_empresa")
                )
            return bool(existe)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    eliminado = asyncio.run(drop_index())
    if eliminado:
        print("Indice uq_contacto_principal_por_empresa eliminado.")
    else:
        print("El indice ya no existia; nada que hacer.")
