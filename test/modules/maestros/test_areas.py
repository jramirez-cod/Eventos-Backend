import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.maestros.models import Area
from test.modules.maestros import create_area, seed_maestro_actor


pytestmark = pytest.mark.asyncio


async def test_crear_area_correcta_normaliza_y_audita(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_maestro_actor(session)

    response = await client.post(
        "/api/v1/maestros/areas",
        headers=headers,
        json={
            "nombre_area": "  Relaciones   Institucionales ",
            "descripcion": "  Atención a instituciones  ",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_area"] > 0
    assert body["nombre_area"] == "Relaciones Institucionales"
    assert body["descripcion"] == "Atención a instituciones"
    assert body["estado"] is True

    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "CREAR_AREA")
        )
    assert audit is not None
    assert audit.id_usuario == actor.id_usuario
    assert audit.entidad == "area"


async def test_nombre_area_obligatorio(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)

    missing = await client.post(
        "/api/v1/maestros/areas", headers=headers, json={}
    )
    blank = await client.post(
        "/api/v1/maestros/areas",
        headers=headers,
        json={"nombre_area": "   ", "descripcion": None},
    )

    assert missing.status_code == 422
    assert blank.status_code == 400


async def test_area_duplicada_ignora_mayusculas_y_espacios(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)

    first = await client.post(
        "/api/v1/maestros/areas",
        headers=headers,
        json={"nombre_area": "Comunidad"},
    )
    duplicate = await client.post(
        "/api/v1/maestros/areas",
        headers=headers,
        json={"nombre_area": "  comunidad  "},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409


async def test_obtener_area_y_area_inexistente(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        area = await create_area(
            session,
            nombre="Marketing",
            descripcion="Difusión institucional",
        )
        await session.commit()
        id_area = area.id_area

    found = await client.get(
        f"/api/v1/maestros/areas/{id_area}", headers=headers
    )
    missing = await client.get(
        "/api/v1/maestros/areas/999999", headers=headers
    )

    assert found.status_code == 200
    assert found.json()["nombre_area"] == "Marketing"
    assert missing.status_code == 404


async def test_listar_areas_con_paginacion(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        await create_area(session, nombre="Comercial")
        await create_area(session, nombre="Comunidad")
        await create_area(session, nombre="Marketing")
        await session.commit()

    response = await client.get(
        "/api/v1/maestros/areas",
        headers=headers,
        params={"page": 2, "page_size": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["pages"] == 2
    assert body["page"] == 2
    assert len(body["items"]) == 1


async def test_filtrar_areas_activas_y_buscar_por_nombre(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        await create_area(session, nombre="Relaciones Comerciales", estado=True)
        await create_area(session, nombre="Comercial Histórica", estado=False)
        await create_area(session, nombre="Marketing", estado=True)
        await session.commit()

    active = await client.get(
        "/api/v1/maestros/areas",
        headers=headers,
        params={"estado": "true"},
    )
    search = await client.get(
        "/api/v1/maestros/areas",
        headers=headers,
        params={"search": "relaciones"},
    )

    assert active.status_code == 200
    assert active.json()["total"] == 2
    assert all(item["estado"] for item in active.json()["items"])
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["nombre_area"] == "Relaciones Comerciales"


async def test_actualizar_area_y_auditar(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        area = await create_area(
            session,
            nombre="Relaciones",
            descripcion="Descripción anterior",
        )
        await session.commit()
        id_area = area.id_area

    response = await client.put(
        f"/api/v1/maestros/areas/{id_area}",
        headers=headers,
        json={
            "nombre_area": "  Relaciones   Institucionales ",
            "descripcion": "  Nueva descripción  ",
        },
    )

    assert response.status_code == 200
    assert response.json()["nombre_area"] == "Relaciones Institucionales"
    assert response.json()["descripcion"] == "Nueva descripción"
    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "ACTUALIZAR_AREA")
        )
    assert audit is not None
    assert audit.valor_anterior["nombre_area"] == "Relaciones"
    assert audit.valor_nuevo["descripcion"] == "Nueva descripción"


async def test_actualizar_area_no_permite_nombre_duplicado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        target = await create_area(session, nombre="Comunidad")
        await create_area(session, nombre="Marketing")
        await session.commit()
        id_area = target.id_area

    response = await client.put(
        f"/api/v1/maestros/areas/{id_area}",
        headers=headers,
        json={"nombre_area": "marketing", "descripcion": None},
    )
    assert response.status_code == 409


async def test_inactivar_area_es_idempotente_y_permite_reactivar(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        area = await create_area(session, nombre="Comunidad")
        await session.commit()
        id_area = area.id_area

    inactive = await client.patch(
        f"/api/v1/maestros/areas/{id_area}/estado",
        headers=headers,
        json={"estado": False},
    )
    inactive_again = await client.patch(
        f"/api/v1/maestros/areas/{id_area}/estado",
        headers=headers,
        json={"estado": False},
    )
    active_list = await client.get(
        "/api/v1/maestros/areas",
        headers=headers,
        params={"estado": "true", "search": "Comunidad"},
    )
    active = await client.patch(
        f"/api/v1/maestros/areas/{id_area}/estado",
        headers=headers,
        json={"estado": True},
    )

    assert inactive.status_code == 200
    assert inactive.json()["estado"] is False
    assert inactive_again.status_code == 200
    assert inactive_again.json()["estado"] is False
    assert active_list.status_code == 200
    assert active_list.json()["total"] == 0
    assert active.status_code == 200
    assert active.json()["id_area"] == id_area
    assert active.json()["estado"] is True

    async with session_factory() as session:
        stored = await session.get(Area, id_area)
        actions = set(
            (
                await session.scalars(
                    select(Auditoria.accion).where(Auditoria.entidad == "area")
                )
            ).all()
        )
    assert stored is not None
    assert {"INACTIVAR_AREA", "REACTIVAR_AREA"} <= actions


async def test_cambiar_estado_area_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)

    response = await client.patch(
        "/api/v1/maestros/areas/999999/estado",
        headers=headers,
        json={"estado": False},
    )
    assert response.status_code == 404
