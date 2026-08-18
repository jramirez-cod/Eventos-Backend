from argparse import Namespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.modules.usuarios.models import (
    Modulo,
    Permiso,
    Rol,
    RolPermisoModulo,
    Usuario,
)
from scripts import bootstrap_security


pytestmark = pytest.mark.asyncio


async def test_bootstrap_rbac_es_idempotente_para_grupos_y_categorias(
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
        ) == 3
        assert await session.scalar(
            select(func.count()).select_from(Permiso)
        ) == 9
        assert await session.scalar(
            select(func.count()).select_from(RolPermisoModulo)
        ) == 16
        assert await session.scalar(
            select(func.count()).select_from(Usuario)
        ) == 1

        personal_permissions = await session.scalar(
            select(func.count())
            .select_from(RolPermisoModulo)
            .join(Rol, Rol.id_rol == RolPermisoModulo.id_rol)
            .where(Rol.nombre_rol == "PERSONAL_EVENTOS")
        )
        assert personal_permissions == 7
