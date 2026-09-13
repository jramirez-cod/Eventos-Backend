from argparse import Namespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.modules.categorias.models import Categoria
from app.modules.comunicaciones.models import (
    CorreoConfiguracionGlobal,
    CorreoPlantilla,
    CorreoPlantillaHistorial,
)
from app.modules.maestros.models import Beneficio, TipoCalculoBeneficio
from app.modules.usuarios.models import (
    Modulo,
    Permiso,
    Rol,
    RolPermisoModulo,
    Usuario,
)
from scripts import bootstrap_security


pytestmark = pytest.mark.asyncio


async def test_bootstrap_rbac_es_idempotente(
    session_factory,
    monkeypatch,
) -> None:
    admin_args = {
        "username": "admin-bootstrap",
        "password": "AdminSeguro1!",
        "email": "admin-bootstrap@codip.pe",
        "nombres": "Administrador",
        "apellidos": "Eventos",
        "numero_documento": "12345678",
    }
    monkeypatch.setattr(
        bootstrap_security,
        "AsyncSessionLocal",
        session_factory,
    )
    monkeypatch.setattr(
        bootstrap_security,
        "_ensure_schema_exists",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        bootstrap_security,
        "_resolve_admin_args",
        lambda _: admin_args,
    )
    args = Namespace(
        username=None,
        email=None,
        nombres=None,
        apellidos=None,
        documento=None,
    )

    await bootstrap_security.bootstrap(args)
    await bootstrap_security.bootstrap(args)

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Rol)) == 2
        assert await session.scalar(
            select(func.count()).select_from(Modulo)
        ) == 10
        assert await session.scalar(
            select(func.count()).select_from(Permiso)
        ) == 38
        assert await session.scalar(
            select(func.count()).select_from(RolPermisoModulo)
        ) == 62
        assert await session.scalar(
            select(func.count()).select_from(Usuario)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(Categoria)
        ) == 4
        assert await session.scalar(
            select(func.count()).select_from(Beneficio)
        ) == 3

        categorias = set(
            (
                await session.scalars(
                    select(Categoria.nombre_categoria)
                )
            ).all()
        )
        assert categorias == {"Sin categoría", "A", "B", "C"}

        beneficios = {
            beneficio.nombre: beneficio
            for beneficio in (
                await session.scalars(select(Beneficio))
            ).all()
        }
        assert beneficios["Sin beneficio"].tipo_calculo == (
            TipoCalculoBeneficio.SIN_BENEFICIO
        )
        assert beneficios["Entrada gratuita"].tipo_calculo == (
            TipoCalculoBeneficio.POR_EVENTO
        )
        assert beneficios["Entrada gratuita"].personas_por_asignacion == 1
        assert beneficios["Entrada doble"].tipo_calculo == (
            TipoCalculoBeneficio.POR_ANIO
        )
        assert beneficios["Entrada doble"].personas_por_asignacion == 2

        personal_permissions = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .where(Rol.nombre_rol == "PERSONAL_EVENTOS")
        )
        assert personal_permissions == 24

        personal_fusion_permission = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .join(Permiso, Permiso.id_permiso == RolPermisoModulo.id_permiso)
            .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
            .where(
                Rol.nombre_rol == "PERSONAL_EVENTOS",
                Modulo.nombre_modulo == "CONTACTOS",
                Permiso.codigo == "FUSIONAR_CONTACTO",
            )
        )
        assert personal_fusion_permission == 0

        personal_gestionar_maestros = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .join(Permiso, Permiso.id_permiso == RolPermisoModulo.id_permiso)
            .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
            .where(
                Rol.nombre_rol == "PERSONAL_EVENTOS",
                Modulo.nombre_modulo == "MAESTROS",
                Permiso.codigo == "GESTIONAR_MAESTROS",
            )
        )
        assert personal_gestionar_maestros == 1

        personal_admin_event_permissions = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .join(Permiso, Permiso.id_permiso == RolPermisoModulo.id_permiso)
            .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
            .where(
                Rol.nombre_rol == "PERSONAL_EVENTOS",
                Modulo.nombre_modulo == "EVENTOS",
                Permiso.codigo.in_(
                    {"REABRIR_EVENTO", "ELIMINAR_EVENTO", "REABRIR_PROGRAMACION"}
                ),
            )
        )
        assert personal_admin_event_permissions == 0

        personal_participante_permissions = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
            .where(
                Rol.nombre_rol == "PERSONAL_EVENTOS",
                Modulo.nombre_modulo == "PARTICIPANTES",
            )
        )
        assert personal_participante_permissions == 3

        admin_report_permissions = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
            .where(
                Rol.nombre_rol == "ADMINISTRADOR_EVENTOS",
                Modulo.nombre_modulo == "REPORTES",
            )
        )
        assert admin_report_permissions == 3

        personal_report_permissions = await session.scalar(
            select(Permiso.codigo)
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .join(Permiso, Permiso.id_permiso == RolPermisoModulo.id_permiso)
            .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
            .where(
                Rol.nombre_rol == "PERSONAL_EVENTOS",
                Modulo.nombre_modulo == "REPORTES",
            )
        )
        assert personal_report_permissions == "CONSULTAR_REPORTE_EVENTO"

        admin_comunicacion_permissions = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
            .where(
                Rol.nombre_rol == "ADMINISTRADOR_EVENTOS",
                Modulo.nombre_modulo == "COMUNICACIONES",
            )
        )
        assert admin_comunicacion_permissions == 5

        personal_comunicacion_permissions = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .join(Modulo, Modulo.id_modulo == RolPermisoModulo.id_modulo)
            .where(
                Rol.nombre_rol == "PERSONAL_EVENTOS",
                Modulo.nombre_modulo == "COMUNICACIONES",
            )
        )
        assert personal_comunicacion_permissions == 0
        assert await session.scalar(
            select(func.count()).select_from(CorreoConfiguracionGlobal)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(CorreoPlantilla)
        ) == 4
        assert await session.scalar(
            select(func.count()).select_from(CorreoPlantillaHistorial)
        ) == 4
