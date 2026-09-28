"""Limpia afiliaciones de empresa duplicadas y asegura la restriccion unica.

Regla de negocio: solo puede existir una fila de evento_empresa por par
(programacion, empresa) -- afiliar/desafiliar reutiliza la misma fila
(activandola o desactivandola), nunca crea una nueva. Si en la practica
aparecen duplicados (por ejemplo porque la restriccion unica nunca se
llego a crear en esta base), este script:

1. Por cada grupo duplicado, elige una fila "ganadora" (activa, con
   contacto principal asignado, la mas antigua como desempate) y le
   reasigna los codigos de acceso (codigo_acceso_principal) de las
   demas filas del grupo antes de eliminarlas.
2. Al final, crea la restriccion unica uq_evento_empresa_programacion_empresa
   si todavia no existe, para que esto no pueda volver a pasar.

Es seguro correrlo varias veces: si no hay duplicados y la restriccion ya
existe, no hace nada. Todo corre en una sola transaccion.
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


async def limpiar() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            grupos = (
                await conn.execute(
                    text(
                        """
                        SELECT id_programacion_evento, id_empresa
                        FROM evento_empresa
                        GROUP BY id_programacion_evento, id_empresa
                        HAVING COUNT(*) > 1
                        """
                    )
                )
            ).all()

            if not grupos:
                print("No hay filas duplicadas en evento_empresa.")
            else:
                print(f"Se encontraron {len(grupos)} combinacion(es) duplicada(s). Limpiando...")
                for grupo in grupos:
                    filas = (
                        await conn.execute(
                            text(
                                """
                                SELECT id_evento_empresa
                                FROM evento_empresa
                                WHERE id_programacion_evento = :prog AND id_empresa = :emp
                                ORDER BY estado DESC,
                                         (id_contacto_principal IS NOT NULL) DESC,
                                         id_evento_empresa ASC
                                """
                            ),
                            {"prog": grupo.id_programacion_evento, "emp": grupo.id_empresa},
                        )
                    ).all()

                    ganador = filas[0].id_evento_empresa
                    perdedores = [f.id_evento_empresa for f in filas[1:]]

                    await conn.execute(
                        text(
                            "UPDATE codigo_acceso_principal SET id_evento_empresa = :ganador "
                            "WHERE id_evento_empresa = ANY(:perdedores)"
                        ),
                        {"ganador": ganador, "perdedores": perdedores},
                    )
                    await conn.execute(
                        text(
                            "DELETE FROM evento_empresa WHERE id_evento_empresa = ANY(:perdedores)"
                        ),
                        {"perdedores": perdedores},
                    )
                    print(
                        f"  programacion={grupo.id_programacion_evento} empresa={grupo.id_empresa}: "
                        f"se conservo id_evento_empresa={ganador}, se eliminaron {perdedores}"
                    )

            existe_restriccion = await conn.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_constraint "
                    "WHERE conname = 'uq_evento_empresa_programacion_empresa')"
                )
            )
            if existe_restriccion:
                print("La restriccion uq_evento_empresa_programacion_empresa ya existia.")
            else:
                await conn.execute(
                    text(
                        "ALTER TABLE evento_empresa ADD CONSTRAINT "
                        "uq_evento_empresa_programacion_empresa "
                        "UNIQUE (id_programacion_evento, id_empresa)"
                    )
                )
                print("Restriccion uq_evento_empresa_programacion_empresa creada.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(limpiar())
