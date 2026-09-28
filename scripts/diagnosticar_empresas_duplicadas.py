"""Diagnostico de solo lectura: busca afiliaciones de empresa duplicadas.

No modifica nada. Reporta:
1. Si el indice/restriccion unica de evento_empresa (programacion, empresa)
   existe realmente en la base.
2. Filas de evento_empresa duplicadas para el mismo (programacion, empresa),
   si las hay, con su estado.
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


async def diagnosticar() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            existe_restriccion = await conn.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_constraint "
                    "WHERE conname = 'uq_evento_empresa_programacion_empresa')"
                )
            )
            print(
                "Restriccion uq_evento_empresa_programacion_empresa "
                f"{'EXISTE' if existe_restriccion else 'NO EXISTE'} en la base."
            )

            duplicados = (
                await conn.execute(
                    text(
                        """
                        SELECT id_programacion_evento, id_empresa, COUNT(*) AS filas,
                               array_agg(id_evento_empresa ORDER BY id_evento_empresa) AS ids,
                               array_agg(estado ORDER BY id_evento_empresa) AS estados
                        FROM evento_empresa
                        GROUP BY id_programacion_evento, id_empresa
                        HAVING COUNT(*) > 1
                        ORDER BY id_programacion_evento, id_empresa
                        """
                    )
                )
            ).all()

            if not duplicados:
                print("No se encontraron filas duplicadas en evento_empresa.")
                return

            print(f"Se encontraron {len(duplicados)} combinacion(es) duplicada(s):")
            for row in duplicados:
                print(
                    f"  programacion={row.id_programacion_evento} "
                    f"empresa={row.id_empresa} filas={row.filas} "
                    f"ids={row.ids} estados={row.estados}"
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(diagnosticar())
