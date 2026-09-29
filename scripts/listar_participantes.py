"""Lista de solo lectura los participantes de una programacion.

No modifica nada. Util para corroborar que un import de contactos/
participantes quedo completo.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.contactos.models import Contacto  # noqa: E402
from app.modules.empresas.models import Empresa  # noqa: E402
from app.modules.participantes.models import EventoContacto, ParticipanteQr  # noqa: E402


async def listar(id_programacion_evento: int) -> None:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(EventoContacto, Contacto, Empresa, ParticipanteQr.fecha_envio)
            .join(Contacto, Contacto.id_contacto == EventoContacto.id_contacto)
            .join(Empresa, Empresa.id_empresa == EventoContacto.id_empresa)
            .outerjoin(
                ParticipanteQr,
                ParticipanteQr.id_evento_contacto == EventoContacto.id_evento_contacto,
            )
            .where(EventoContacto.id_programacion_evento == id_programacion_evento)
            .order_by(Empresa.nombre_empresa, Contacto.apellidos)
        )
        rows = (await session.execute(stmt)).all()

        print(f"Total participantes en programacion {id_programacion_evento}: {len(rows)}\n")
        for ec, contacto, empresa, fecha_envio_qr in rows:
            print(
                f"  [{ec.id_evento_contacto}] {contacto.nombres} {contacto.apellidos} "
                f"| {empresa.nombre_empresa} | correo={contacto.correo} "
                f"| estado={ec.estado} | asistencia={ec.asistencia_evento} "
                f"| credencial_impresa={ec.credencial_impresa} "
                f"| qr_enviado={fecha_envio_qr is not None}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--programacion", type=int, default=6)
    args = parser.parse_args()
    asyncio.run(listar(args.programacion))
