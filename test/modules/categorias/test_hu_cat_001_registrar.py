from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.categorias.dto import CategoriaCreateDTO
from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.categorias.service import CategoriaService
from test.modules.catalogos_helpers import (
    create_group,
    seed_catalog_actor,
)
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
)


pytestmark = pytest.mark.asyncio


def categoria_payload(id_grupo: int) -> dict[str, object]:
    return {
        "id_grupo": id_grupo,
        "nombre_categoria": "A",
        "descripcion": "Categoría A",
    }


async def test_crear_categoria_para_grupo_activo_crea_detalle_y_audita(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_catalog_actor(session)
        grupo = await create_group(
            session,
            name="Asociado",
            requiere_categoria=True,
        )
        await session.commit()
        group_id = grupo.id_grupo
        actor_id = actor.id_usuario

    response = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json=categoria_payload(group_id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_categoria"] > 0
    assert body["id_grupo"] == group_id
    assert body["id_detalle_categoria"] > 0
    assert body["nombre_categoria"] == "A"
    assert body["estado"] is True
    assert body["estado_relacion"] is True

    async with session_factory() as session:
        detail = await session.get(
            DetalleCategoria,
            body["id_detalle_categoria"],
        )
        assert detail is not None
        assert detail.id_categoria == body["id_categoria"]
        audits = (
            await session.scalars(
                select(Auditoria)
                .where(
                    Auditoria.accion.in_(
                        ("CREAR_CATEGORIA", "ASOCIAR_CATEGORIA_GRUPO")
                    )
                )
                .order_by(Auditoria.id_auditoria)
            )
        ).all()
        assert [audit.accion for audit in audits] == [
            "CREAR_CATEGORIA",
            "ASOCIAR_CATEGORIA_GRUPO",
        ]
        assert all(audit.id_usuario == actor_id for audit in audits)


async def test_grupo_inexistente_o_inactivo_rechaza_categoria(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        inactive_group = await create_group(
            session,
            name="Inactivo",
            estado=False,
        )
        await session.commit()
        inactive_id = inactive_group.id_grupo

    missing = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json=categoria_payload(9999),
    )
    inactive = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json=categoria_payload(inactive_id),
    )

    assert missing.status_code == 404
    assert inactive.status_code == 400


async def test_categoria_requiere_nombre_y_permiso(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Asociado")
        role = await create_role(session, "Sin categorías")
        user = await create_user(session, role, username="sin-categorias")
        await session.commit()
        group_id = grupo.id_grupo
        forbidden_headers = auth_header(user)

    missing_name = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json={"id_grupo": group_id},
    )
    forbidden = await client.post(
        "/api/v1/categorias",
        headers=forbidden_headers,
        json=categoria_payload(group_id),
    )
    unauthenticated = await client.post(
        "/api/v1/categorias",
        json=categoria_payload(group_id),
    )

    assert missing_name.status_code == 422
    assert forbidden.status_code == 403
    assert unauthenticated.status_code == 401


async def test_misma_categoria_y_mismo_grupo_devuelve_409(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Asociado")
        await session.commit()
        group_id = grupo.id_grupo

    first = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json=categoria_payload(group_id),
    )
    duplicate = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json=categoria_payload(group_id),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409


async def test_categoria_global_se_reutiliza_en_otro_grupo(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        asociado = await create_group(session, name="Asociado")
        expositor = await create_group(session, name="Expositor")
        await session.commit()
        asociado_id = asociado.id_grupo
        expositor_id = expositor.id_grupo

    first = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json=categoria_payload(asociado_id),
    )
    second = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json=categoria_payload(expositor_id),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id_categoria"] == second.json()["id_categoria"]
    assert first.json()["id_detalle_categoria"] != second.json()[
        "id_detalle_categoria"
    ]

    async with session_factory() as session:
        category_count = await session.scalar(
            select(func.count()).select_from(Categoria)
        )
        detail_count = await session.scalar(
            select(func.count()).select_from(DetalleCategoria)
        )
        assert category_count == 1
        assert detail_count == 2


async def test_fallo_de_auditoria_revierte_categoria_y_detalle(
    session_factory,
) -> None:
    async with session_factory() as session:
        actor, _ = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Transaccional")
        await session.commit()
        actor_id = actor.id_usuario
        group_id = grupo.id_grupo

    async with session_factory() as session:
        actor = await session.get(type(actor), actor_id)
        service = CategoriaService(session)
        service.auditoria.create = AsyncMock(
            side_effect=RuntimeError("Fallo de auditoría")
        )

        with pytest.raises(RuntimeError, match="Fallo de auditoría"):
            await service.crear_categoria(
                data=CategoriaCreateDTO(**categoria_payload(group_id)),
                actor=actor,
            )

    async with session_factory() as session:
        assert await session.scalar(
            select(func.count()).select_from(Categoria)
        ) == 0
        assert await session.scalar(
            select(func.count()).select_from(DetalleCategoria)
        ) == 0
