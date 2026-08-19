import pytest

from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorCategorias")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="CATEGORIAS"
        )
    actor = await create_user(session, rol, username="actor.categorias")
    await session.commit()
    return actor


async def test_crear_categoria_ok(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_CATEGORIA"])
        headers = auth_header(actor)

    response = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json={"nombre_categoria": "A", "descripcion": "Categoría A"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["nombre_categoria"] == "A"
    assert body["descripcion"] == "Categoría A"
    assert body["estado"] is True


async def test_nombre_duplicado_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_CATEGORIA"])
        headers = auth_header(actor)

    payload = {"nombre_categoria": "B", "descripcion": None}
    primera = await client.post("/api/v1/categorias", headers=headers, json=payload)
    assert primera.status_code == 201

    segunda = await client.post("/api/v1/categorias", headers=headers, json=payload)
    assert segunda.status_code == 409


async def test_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "SinPermisoCategorias")
        actor = await create_user(session, rol, username="sin.permiso.cat")
        await session.commit()
        headers = auth_header(actor)

    response = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json={"nombre_categoria": "C", "descripcion": None},
    )

    assert response.status_code == 403
