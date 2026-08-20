from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.modules.maestros.models import Area, Cargo
from app.modules.maestros.router import router as maestros_router
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


MAESTRO_PERMISSIONS = ("CONSULTAR_MAESTROS", "GESTIONAR_MAESTROS")

if not any(
    getattr(route, "path", None) == "/api/v1/maestros/cargos"
    for route in app.routes
):
    app.include_router(maestros_router, prefix="/api/v1")


async def seed_maestro_actor(
    session: AsyncSession,
    *,
    username: str = "actor.maestros",
    permissions: tuple[str, ...] = MAESTRO_PERMISSIONS,
) -> tuple[Usuario, dict[str, str]]:
    role = await create_role(session, f"Rol {username}")
    for permission in permissions:
        await grant_permission(
            session,
            role,
            permiso_nombre=permission,
            modulo_nombre="MAESTROS",
        )
    actor = await create_user(session, role, username=username)
    await session.commit()
    return actor, auth_header(actor)


async def create_cargo(
    session: AsyncSession,
    *,
    nombre: str,
    estado: bool = True,
) -> Cargo:
    cargo = Cargo(nombre_cargo=nombre, estado=estado)
    session.add(cargo)
    await session.flush()
    return cargo


async def create_area(
    session: AsyncSession,
    *,
    nombre: str,
    descripcion: str | None = None,
    estado: bool = True,
) -> Area:
    area = Area(
        nombre_area=nombre,
        descripcion=descripcion,
        estado=estado,
    )
    session.add(area)
    await session.flush()
    return area


__all__ = [
    "MAESTRO_PERMISSIONS",
    "create_area",
    "create_cargo",
    "seed_maestro_actor",
]
