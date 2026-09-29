"""Diagnostico de solo lectura: permisos del modulo COMUNICACIONES.

No modifica nada. Lista cada rol con los permisos de COMUNICACIONES que
tiene otorgados, y todos los usuarios activos con su rol, para poder
cruzar con que cuenta se esta probando el guardado de plantillas.
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
from app.modules.usuarios.models import (  # noqa: E402
    Modulo,
    Permiso,
    Rol,
    RolPermisoModulo,
    Usuario,
)


async def diagnosticar() -> None:
    async with AsyncSessionLocal() as session:
        modulo = await session.scalar(
            select(Modulo).where(Modulo.nombre_modulo == "COMUNICACIONES")
        )
        if modulo is None:
            print("El modulo COMUNICACIONES no existe en la base.")
        else:
            print(f"Modulo COMUNICACIONES: id={modulo.id_modulo} estado={modulo.estado}")

        print("\n=== Roles y permisos de COMUNICACIONES otorgados ===")
        roles = list((await session.scalars(select(Rol))).all())
        for rol in roles:
            stmt = (
                select(Permiso.codigo, Permiso.estado)
                .join(
                    RolPermisoModulo,
                    RolPermisoModulo.id_permiso == Permiso.id_permiso,
                )
                .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
                .where(
                    RolPermisoModulo.id_rol == rol.id_rol,
                    Modulo.nombre_modulo == "COMUNICACIONES",
                )
            )
            permisos = [(codigo, estado) for codigo, estado in (await session.execute(stmt)).all()]
            print(f"  Rol [{rol.id_rol}] {rol.nombre_rol} (estado={rol.estado}): {permisos}")

        print("\n=== Usuarios activos y su rol ===")
        usuarios = list(
            (await session.scalars(select(Usuario).where(Usuario.estado.is_(True)))).all()
        )
        for u in usuarios:
            print(
                f"  [{u.id_usuario}] {u.nombre_usuario} | {u.correo} | id_rol={u.id_rol}"
            )


if __name__ == "__main__":
    asyncio.run(diagnosticar())
