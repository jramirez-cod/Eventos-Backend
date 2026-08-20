from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.contactos.models import Contacto, ContactoHistorialEmpresa
from app.modules.contactos.router import router as contactos_router
from app.modules.empresas.models import Empresa
from app.modules.grupos.models import Grupo
from app.modules.maestros.models import Cargo
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


CONTACT_PERMISSIONS = (
    "CREAR_CONTACTO",
    "CONSULTAR_CONTACTO",
    "ACTUALIZAR_CONTACTO",
    "CAMBIAR_EMPRESA_CONTACTO",
    "CAMBIAR_ESTADO_CONTACTO",
    "FUSIONAR_CONTACTO",
    "EXPORTAR_CONTACTO",
)

if not any(
    getattr(route, "path", None) == "/api/v1/contactos" for route in app.routes
):
    app.include_router(contactos_router, prefix="/api/v1")


async def seed_contact_actor(
    session: AsyncSession,
    *,
    username: str = "actor.contactos",
    permissions: tuple[str, ...] = CONTACT_PERMISSIONS,
) -> tuple[Usuario, dict[str, str]]:
    role = await create_role(session, f"Rol {username}")
    for permission in permissions:
        await grant_permission(
            session,
            role,
            permiso_nombre=permission,
            modulo_nombre="CONTACTOS",
        )
    actor = await create_user(session, role, username=username)
    await session.commit()
    return actor, auth_header(actor)


async def create_cargo(
    session: AsyncSession,
    *,
    name: str = "Gerente General",
    estado: bool = True,
) -> Cargo:
    cargo = Cargo(nombre_cargo=name, estado=estado)
    session.add(cargo)
    await session.flush()
    return cargo


async def create_empresa(
    session: AsyncSession,
    *,
    sequence: int,
    estado: bool = True,
) -> Empresa:
    grupo = Grupo(
        id_grupo=9_000 + sequence,
        nombre_grupo=f"Grupo Contactos {sequence}",
        descripcion="Grupo de prueba",
        estado=True,
    )
    categoria = Categoria(
        nombre_categoria=f"Categoría Contactos {sequence}",
        estado=True,
    )
    session.add_all([grupo, categoria])
    await session.flush()
    detalle = DetalleCategoria(
        id_grupo=grupo.id_grupo,
        id_categoria=categoria.id_categoria,
        estado=True,
    )
    session.add(detalle)
    await session.flush()
    empresa = Empresa(
        id_detalle_categoria=detalle.id_detalle_categoria,
        nombre_empresa=f"Empresa Contactos {sequence}",
        razon_social=f"Empresa Contactos {sequence} S.A.C.",
        nombre_comercial=f"EC {sequence}",
        ruc=f"20{sequence:09d}",
        estado=estado,
    )
    session.add(empresa)
    await session.flush()
    return empresa


async def create_contacto(
    session: AsyncSession,
    *,
    empresa: Empresa,
    actor: Usuario,
    sequence: int,
    estado: bool = True,
    cargo: Cargo | None = None,
) -> Contacto:
    contacto = Contacto(
        id_empresa=empresa.id_empresa,
        id_cargo=cargo.id_cargo if cargo else None,
        id_tipo_documento=actor.id_tipo_documento,
        numero_documento=f"7{sequence:07d}",
        nombres=f"Nombre {sequence}",
        apellidos=f"Apellido {sequence}",
        genero="M",
        celular=f"9{sequence:08d}",
        correo=f"contacto{sequence}@example.com",
        estado=estado,
    )
    session.add(contacto)
    await session.flush()
    session.add(
        ContactoHistorialEmpresa(
            id_contacto=contacto.id_contacto,
            id_empresa=empresa.id_empresa,
            id_usuario_cambio=actor.id_usuario,
            motivo="Registro inicial de prueba",
        )
    )
    await session.flush()
    return contacto


def contacto_payload(
    *, empresa: Empresa, actor: Usuario, cargo: Cargo | None = None
) -> dict[str, object]:
    return {
        "id_empresa": empresa.id_empresa,
        "id_cargo": cargo.id_cargo if cargo else None,
        "id_tipo_documento": actor.id_tipo_documento,
        "numero_documento": "76543210",
        "nombres": "Juan Carlos",
        "apellidos": "Perez Ramos",
        "genero": "M",
        "celular": "987 654 321",
        "correo": "juan.perez@example.com",
    }


__all__ = [
    "CONTACT_PERMISSIONS",
    "contacto_payload",
    "create_cargo",
    "create_contacto",
    "create_empresa",
    "seed_contact_actor",
]
