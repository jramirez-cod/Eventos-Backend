from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comunicaciones.models import CorreoConfiguracionGlobal
from app.modules.comunicaciones.seed import seed_default_templates
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


COMUNICACION_PERMISSIONS = (
    "CONSULTAR_PLANTILLA_CORREO",
    "GESTIONAR_PLANTILLA_CORREO",
    "RESTAURAR_PLANTILLA_CORREO",
    "ENVIAR_CORREO_PRUEBA",
    "CONFIGURAR_CORREO_GLOBAL",
)


async def seed_comunicacion_actor(
    session: AsyncSession,
    *,
    permissions: tuple[str, ...] = COMUNICACION_PERMISSIONS,
    username: str = "actor.comunicaciones",
) -> tuple[Usuario, dict[str, str]]:
    role = await create_role(session, f"Rol {username}")
    for permission in permissions:
        await grant_permission(
            session,
            role,
            permiso_nombre=permission,
            modulo_nombre="COMUNICACIONES",
        )
    actor = await create_user(session, role, username=username)
    await seed_default_templates(session)
    session.add(
        CorreoConfiguracionGlobal(
            codigo="GLOBAL",
            id_usuario_emisor=actor.id_usuario,
            nombre_remitente="Sistema Eventos CODIP",
            estado=True,
            actualizado_por=actor.id_usuario,
        )
    )
    await session.commit()
    return actor, auth_header(actor)


__all__ = ["COMUNICACION_PERMISSIONS", "seed_comunicacion_actor"]

