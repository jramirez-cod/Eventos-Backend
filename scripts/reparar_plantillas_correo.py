"""Diagnostica y repara correo_plantilla.variables_permitidas si esta en NULL.

seed_default_templates() solo se corre en el setup inicial (bootstrap_security.py
o create_db.py), nunca en cada arranque del backend. Si una plantilla quedo con
variables_permitidas en NULL (por una version anterior del esquema, o por un
insert manual), cualquier accion sobre ella -- editar, previsualizar, enviar
prueba -- explota con un error sin capturar, porque el validador de plantillas
no protegia contra ese caso (ya corregido en el codigo aparte).

Este script primero reporta el estado actual de cada plantilla, y despues
corre la misma logica de sincronizacion que el seed original: rellena
variables_permitidas faltantes sin nunca sobrescribir asunto/cuerpo de una
plantilla que ya fue editada desde el panel (version_actual != 1).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.comunicaciones.models import CorreoPlantilla  # noqa: E402
from app.modules.comunicaciones.seed import seed_default_templates  # noqa: E402


async def diagnosticar_y_reparar() -> None:
    async with AsyncSessionLocal() as session:
        plantillas = list(
            (await session.scalars(select(CorreoPlantilla))).all()
        )
        print("=== Estado actual ===")
        for p in plantillas:
            print(
                f"  {p.codigo}: version_actual={p.version_actual} "
                f"variables_permitidas={p.variables_permitidas!r}"
            )

        await seed_default_templates(session)
        await session.commit()

        print("\n=== Estado despues de sincronizar ===")
        plantillas = list(
            (await session.scalars(select(CorreoPlantilla))).all()
        )
        for p in plantillas:
            print(
                f"  {p.codigo}: version_actual={p.version_actual} "
                f"variables_permitidas={p.variables_permitidas!r}"
            )


if __name__ == "__main__":
    asyncio.run(diagnosticar_y_reparar())
