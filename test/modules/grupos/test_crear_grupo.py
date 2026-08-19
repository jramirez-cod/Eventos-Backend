import pytest

from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorGrupos")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="GRUPOS"
        )
    actor = await create_user(session, rol, username="actor.grupos")
    await session.commit()
    return actor


async def test_crear_grupo_ok_con_id_manual(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_GRUPO"])
        headers = auth_header(actor)

    response = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={"id_grupo": 100, "nombre_grupo": "Asociados", "descripcion": None},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_grupo"] == 100
    assert body["nombre_grupo"] == "Asociados"
    assert body["estado"] is True


async def test_id_grupo_duplicado_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_GRUPO"])
        headers = auth_header(actor)

    payload = {"id_grupo": 200, "nombre_grupo": "Aliados", "descripcion": None}
    primera = await client.post("/api/v1/grupos", headers=headers, json=payload)
    assert primera.status_code == 201

    segunda = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={**payload, "nombre_grupo": "Otro Nombre"},
    )
    assert segunda.status_code == 409


async def test_nombre_grupo_duplicado_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_GRUPO"])
        headers = auth_header(actor)

    primera = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={"id_grupo": 300, "nombre_grupo": "Fundadores", "descripcion": None},
    )
    assert primera.status_code == 201

    segunda = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={"id_grupo": 301, "nombre_grupo": "Fundadores", "descripcion": None},
    )
    assert segunda.status_code == 409


async def test_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "SinPermisoGrupos")
        actor = await create_user(session, rol, username="sin.permiso.grupo")
        await session.commit()
        headers = auth_header(actor)

    response = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={"id_grupo": 400, "nombre_grupo": "Externos", "descripcion": None},
    )
    assert response.status_code == 403
