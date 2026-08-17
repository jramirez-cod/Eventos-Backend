from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.empresas.models import Empresa
from app.modules.grupos.models import Grupo
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


GROUP_PERMISSIONS = (
    "CREAR_GRUPO",
    "INACTIVAR_GRUPO",
    "REACTIVAR_GRUPO",
    "CONFIGURAR_GRUPO",
)
CATEGORY_PERMISSIONS = (
    "CREAR_CATEGORIA",
    "INACTIVAR_CATEGORIA",
    "REACTIVAR_CATEGORIA",
)


async def seed_catalog_actor(
    session: AsyncSession,
    *,
    username: str = "catalog-admin",
    group_permissions: bool = True,
    category_permissions: bool = True,
) -> tuple[Usuario, dict[str, str]]:
    role = await create_role(session, f"Rol {username}")
    if group_permissions:
        for permission in GROUP_PERMISSIONS:
            await grant_permission(
                session,
                role,
                permiso_nombre=permission,
                modulo_nombre="GRUPOS",
            )
    if category_permissions:
        for permission in CATEGORY_PERMISSIONS:
            await grant_permission(
                session,
                role,
                permiso_nombre=permission,
                modulo_nombre="CATEGORIAS",
            )
    actor = await create_user(
        session,
        role,
        username=username,
        email=f"{username}@codip.pe",
    )
    await session.commit()
    return actor, auth_header(actor)


async def create_group(
    session: AsyncSession,
    *,
    name: str,
    requiere_categoria: bool = False,
    estado: bool = True,
) -> Grupo:
    grupo = Grupo(
        nombre_grupo=name,
        descripcion=f"Grupo {name}",
        requiere_categoria=requiere_categoria,
        estado=estado,
    )
    session.add(grupo)
    await session.flush()
    return grupo


async def create_category_detail(
    session: AsyncSession,
    grupo: Grupo,
    *,
    name: str = "A",
    category_estado: bool = True,
) -> tuple[Categoria, DetalleCategoria]:
    categoria = Categoria(
        nombre_categoria=name,
        descripcion=f"Categoría {name}",
        estado=category_estado,
    )
    session.add(categoria)
    await session.flush()
    detail = DetalleCategoria(
        id_grupo=grupo.id_grupo,
        id_categoria=categoria.id_categoria,
        estado=True,
    )
    session.add(detail)
    await session.flush()
    return categoria, detail


async def create_company(
    session: AsyncSession,
    grupo: Grupo,
    *,
    sequence: int,
    detail: DetalleCategoria | None = None,
    estado: bool = True,
) -> Empresa:
    empresa = Empresa(
        id_grupo=grupo.id_grupo,
        id_detalle_categoria=(
            detail.id_detalle_categoria if detail is not None else None
        ),
        nombre_empresa=f"Empresa {sequence}",
        nombre_comercial=f"Comercial {sequence}",
        razon_social=f"Empresa {sequence} S.A.C.",
        ruc=f"20{sequence:09d}",
        estado=estado,
    )
    session.add(empresa)
    await session.flush()
    return empresa


__all__ = [
    "CATEGORY_PERMISSIONS",
    "GROUP_PERMISSIONS",
    "create_category_detail",
    "create_company",
    "create_group",
    "seed_catalog_actor",
]
