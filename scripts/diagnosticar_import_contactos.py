"""Diagnostico de solo lectura antes de importar contactos desde Excel.

No modifica nada. Imprime:
1. Todas las empresas activas (nombre_empresa / nombre_comercial), para
   comparar contra los nombres de la hoja de calculo y detectar typos.
2. Las programaciones cuyo dia incluye el 29 de septiembre (de
   cualquier anio) o cuyo lugar menciona "San Isidro", para confirmar
   cual es la del evento a importar.
3. Si contacto.correo tiene una restriccion NOT NULL en esta base (el
   modelo ya lo declara nullable, pero la base real puede no haberse
   migrado -- ya paso antes con otras restricciones en este proyecto).
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
            print("=== Empresas activas (nombre_empresa | nombre_comercial) ===")
            empresas = (
                await conn.execute(
                    text(
                        "SELECT id_empresa, nombre_empresa, nombre_comercial "
                        "FROM empresa WHERE estado = true ORDER BY nombre_empresa"
                    )
                )
            ).all()
            for e in empresas:
                print(f"  [{e.id_empresa}] {e.nombre_empresa} | {e.nombre_comercial}")
            print(f"Total empresas activas: {len(empresas)}")

            print("\n=== Programaciones con dia = 29 de septiembre (cualquier anio) ===")
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT p.id_programacion_evento, p.id_evento, e.nombre_evento,
                               d.fecha, d.hora_inicio, d.hora_fin,
                               l.distrito, l.provincia, l.direccion, p.estado
                        FROM detalle_programacion_evento d
                        JOIN programacion_evento p
                          ON p.id_programacion_evento = d.id_programacion_evento
                        JOIN evento e ON e.id_evento = p.id_evento
                        LEFT JOIN lugar l ON l.id_lugar = p.id_lugar
                        WHERE EXTRACT(MONTH FROM d.fecha) = 9
                          AND EXTRACT(DAY FROM d.fecha) = 29
                        ORDER BY d.fecha DESC
                        """
                    )
                )
            ).all()
            for r in rows:
                print(
                    f"  programacion={r.id_programacion_evento} evento='{r.nombre_evento}' "
                    f"fecha={r.fecha} hora={r.hora_inicio}-{r.hora_fin} "
                    f"lugar=({r.distrito}, {r.provincia}) direccion={r.direccion} "
                    f"estado_programacion={r.estado}"
                )
            if not rows:
                print("  (ninguna encontrada con dia=29 de septiembre)")

            print("\n=== Programaciones cuyo lugar menciona 'San Isidro' ===")
            rows2 = (
                await conn.execute(
                    text(
                        """
                        SELECT p.id_programacion_evento, p.id_evento, e.nombre_evento,
                               l.distrito, l.provincia, l.direccion, p.estado
                        FROM programacion_evento p
                        JOIN evento e ON e.id_evento = p.id_evento
                        LEFT JOIN lugar l ON l.id_lugar = p.id_lugar
                        WHERE l.distrito ILIKE '%san isidro%'
                           OR l.direccion ILIKE '%san isidro%'
                        """
                    )
                )
            ).all()
            for r in rows2:
                print(
                    f"  programacion={r.id_programacion_evento} evento='{r.nombre_evento}' "
                    f"lugar=({r.distrito}, {r.provincia}) direccion={r.direccion} "
                    f"estado_programacion={r.estado}"
                )
            if not rows2:
                print("  (ninguna encontrada)")

            print("\n=== Restriccion NOT NULL en contacto.correo ===")
            es_not_null = await conn.scalar(
                text(
                    "SELECT attnotnull FROM pg_attribute "
                    "WHERE attrelid = 'contacto'::regclass AND attname = 'correo'"
                )
            )
            print(f"  contacto.correo NOT NULL = {es_not_null}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(diagnosticar())
