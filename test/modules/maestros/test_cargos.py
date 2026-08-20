import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.maestros.models import Cargo
from test.modules.maestros import create_cargo, seed_maestro_actor
from test.modules.usuarios.conftest import auth_header, create_role, create_user


pytestmark = pytest.mark.asyncio


async def test_crear_cargo_correcto_normaliza_y_audita(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_maestro_actor(session)

    response = await client.post(
        "/api/v1/maestros/cargos",
        headers=headers,
        json={"nombre_cargo": "  Gerente   Comercial  "},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_cargo"] > 0
    assert body["nombre_cargo"] == "Gerente Comercial"
    assert body["estado"] is True

    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "CREAR_CARGO")
        )
    assert audit is not None
    assert audit.id_usuario == actor.id_usuario
    assert audit.entidad == "cargo"


async def test_nombre_cargo_obligatorio(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)

    missing = await client.post(
        "/api/v1/maestros/cargos", headers=headers, json={}
    )
    blank = await client.post(
        "/api/v1/maestros/cargos",
        headers=headers,
        json={"nombre_cargo": "   "},
    )

    assert missing.status_code == 422
    assert blank.status_code == 400


async def test_cargo_duplicado_ignora_mayusculas_y_espacios(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)

    first = await client.post(
        "/api/v1/maestros/cargos",
        headers=headers,
        json={"nombre_cargo": "Gerente Comercial"},
    )
    duplicate = await client.post(
        "/api/v1/maestros/cargos",
        headers=headers,
        json={"nombre_cargo": "  gerente   comercial "},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409


async def test_obtener_cargo_y_cargo_inexistente(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        cargo = await create_cargo(session, nombre="Director Ejecutivo")
        await session.commit()
        id_cargo = cargo.id_cargo

    found = await client.get(
        f"/api/v1/maestros/cargos/{id_cargo}", headers=headers
    )
    missing = await client.get(
        "/api/v1/maestros/cargos/999999", headers=headers
    )

    assert found.status_code == 200
    assert found.json()["nombre_cargo"] == "Director Ejecutivo"
    assert missing.status_code == 404


async def test_listar_cargos_con_paginacion(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        await create_cargo(session, nombre="Analista")
        await create_cargo(session, nombre="Coordinador")
        await create_cargo(session, nombre="Gerente")
        await session.commit()

    response = await client.get(
        "/api/v1/maestros/cargos",
        headers=headers,
        params={"page": 2, "page_size": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["pages"] == 2
    assert body["page"] == 2
    assert len(body["items"]) == 1


async def test_filtrar_cargos_activos_y_buscar_por_nombre(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        await create_cargo(session, nombre="Gerente Comercial", estado=True)
        await create_cargo(session, nombre="Gerente Histórico", estado=False)
        await create_cargo(session, nombre="Analista", estado=True)
        await session.commit()

    active = await client.get(
        "/api/v1/maestros/cargos",
        headers=headers,
        params={"estado": "true"},
    )
    search = await client.get(
        "/api/v1/maestros/cargos",
        headers=headers,
        params={"search": "comercial"},
    )

    assert active.status_code == 200
    assert active.json()["total"] == 2
    assert all(item["estado"] for item in active.json()["items"])
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["nombre_cargo"] == "Gerente Comercial"


async def test_actualizar_cargo_y_auditar(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        cargo = await create_cargo(session, nombre="Jefe Comercial")
        await session.commit()
        id_cargo = cargo.id_cargo

    response = await client.put(
        f"/api/v1/maestros/cargos/{id_cargo}",
        headers=headers,
        json={"nombre_cargo": "  Director   Comercial "},
    )

    assert response.status_code == 200
    assert response.json()["nombre_cargo"] == "Director Comercial"
    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "ACTUALIZAR_CARGO")
        )
    assert audit is not None
    assert audit.valor_anterior["nombre_cargo"] == "Jefe Comercial"
    assert audit.valor_nuevo["nombre_cargo"] == "Director Comercial"


async def test_actualizar_cargo_no_permite_nombre_duplicado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        target = await create_cargo(session, nombre="Coordinador")
        await create_cargo(session, nombre="Director")
        await session.commit()
        id_cargo = target.id_cargo

    response = await client.put(
        f"/api/v1/maestros/cargos/{id_cargo}",
        headers=headers,
        json={"nombre_cargo": "director"},
    )
    assert response.status_code == 409


async def test_inactivar_oculta_de_activos_y_reactivar(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        cargo = await create_cargo(session, nombre="Supervisor")
        await session.commit()
        id_cargo = cargo.id_cargo

    inactive = await client.patch(
        f"/api/v1/maestros/cargos/{id_cargo}/estado",
        headers=headers,
        json={"estado": False},
    )
    active_list = await client.get(
        "/api/v1/maestros/cargos",
        headers=headers,
        params={"estado": "true", "search": "Supervisor"},
    )
    active = await client.patch(
        f"/api/v1/maestros/cargos/{id_cargo}/estado",
        headers=headers,
        json={"estado": True},
    )

    assert inactive.status_code == 200
    assert inactive.json()["estado"] is False
    assert active_list.status_code == 200
    assert active_list.json()["total"] == 0
    assert active.status_code == 200
    assert active.json()["id_cargo"] == id_cargo
    assert active.json()["estado"] is True

    async with session_factory() as session:
        actions = set(
            (
                await session.scalars(
                    select(Auditoria.accion).where(
                        Auditoria.entidad == "cargo"
                    )
                )
            ).all()
        )
        stored = await session.get(Cargo, id_cargo)
    assert stored is not None
    assert {"INACTIVAR_CARGO", "REACTIVAR_CARGO"} <= actions


async def test_crear_cargo_sin_permiso_recibe_403(
    client, session_factory
) -> None:
    async with session_factory() as session:
        role = await create_role(session, "Sin gestión maestros")
        actor = await create_user(session, role, username="sin.maestros")
        await session.commit()
        headers = auth_header(actor)

    response = await client.post(
        "/api/v1/maestros/cargos",
        headers=headers,
        json={"nombre_cargo": "Gerente"},
    )
    assert response.status_code == 403
