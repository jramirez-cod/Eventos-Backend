from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.grupos.dto import GrupoCreateDTO
from app.modules.grupos.models import Grupo
from app.modules.grupos.service import DuplicateGroupNameError, GrupoService
from test.modules.catalogos_helpers import seed_catalog_actor
from test.modules.usuarios.conftest import create_role, create_user


pytestmark = pytest.mark.asyncio


def grupo_payload(*, requiere_categoria: bool = True) -> dict[str, object]:
    return {
        "nombre_grupo": "Asociado",
        "descripcion": "Empresas asociadas a CODIP",
        "requiere_categoria": requiere_categoria,
    }


async def test_usuario_con_permiso_registra_grupo_activo_y_audita(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_catalog_actor(session)
        actor_id = actor.id_usuario

    response = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json=grupo_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_grupo"] > 0
    assert body["nombre_grupo"] == "Asociado"
    assert body["estado"] is True
    assert body["requiere_categoria"] is True

    async with session_factory() as session:
        stored = await session.get(Grupo, body["id_grupo"])
        assert stored is not None
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "CREAR_GRUPO")
        )
        assert audit is not None
        assert audit.id_usuario == actor_id
        assert audit.valor_nuevo["id_grupo"] == body["id_grupo"]


async def test_grupo_puede_crearse_sin_requerir_categoria(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)

    response = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json=grupo_payload(requiere_categoria=False),
    )

    assert response.status_code == 201
    assert response.json()["requiere_categoria"] is False


async def test_registrar_grupo_requiere_autenticacion_y_permiso(
    client,
    session_factory,
) -> None:
    unauthenticated = await client.post(
        "/api/v1/grupos",
        json=grupo_payload(),
    )

    async with session_factory() as session:
        role = await create_role(session, "Sin permisos")
        user = await create_user(session, role, username="sin-grupos")
        await session.commit()
        from test.modules.usuarios.conftest import auth_header

        headers = auth_header(user)

    forbidden = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json=grupo_payload(),
    )

    assert unauthenticated.status_code == 401
    assert forbidden.status_code == 403


async def test_nombre_obligatorio_e_id_no_editable(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)

    missing_name = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={"descripcion": "Sin nombre"},
    )
    manual_id = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={"id_grupo": 99, **grupo_payload()},
    )

    assert missing_name.status_code == 422
    assert manual_id.status_code == 422


async def test_nombre_de_grupo_duplicado_devuelve_409(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)

    first = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json=grupo_payload(),
    )
    duplicate = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json=grupo_payload(),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409


async def test_restriccion_unique_se_traduce_a_error_de_dominio(
    session_factory,
) -> None:
    async with session_factory() as session:
        actor, _ = await seed_catalog_actor(session)
        session.add(Grupo(nombre_grupo="Asociado", estado=True))
        await session.commit()

    async with session_factory() as session:
        actor = await session.merge(actor)
        service = GrupoService(session)
        service.grupos.get_by_name = AsyncMock(return_value=None)

        with pytest.raises(DuplicateGroupNameError):
            await service.crear_grupo(
                data=GrupoCreateDTO(**grupo_payload()),
                actor=actor,
            )
