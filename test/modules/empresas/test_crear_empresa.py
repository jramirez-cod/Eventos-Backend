import pytest

from test.modules.empresas.conftest import create_grupo_categoria_detalle
from test.modules.usuarios.conftest import auth_header, create_role, create_user, grant_permission


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorEmpresas")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="EMPRESAS"
        )
    actor = await create_user(session, rol, username="actor.empresas")
    await session.commit()
    return actor


async def test_crear_empresa_ok(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        _, _, detalle = await create_grupo_categoria_detalle(session)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    response = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={
            "nombre_empresa": "Agrolight Peru",
            "ruc": "20552103816",
            "id_detalle_categoria": id_detalle_categoria,
            "razon_social": "AGROLIGHT PERU S.A.C.",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["nombre_empresa"] == "Agrolight Peru"
    assert body["ruc"] == "20552103816"
    assert body["estado"] is True
    assert body["nombre_grupo"] == "GrupoEmpresaTest"


async def test_ruc_duplicado_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        _, _, detalle = await create_grupo_categoria_detalle(session)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    payload = {
        "nombre_empresa": "Empresa Uno",
        "ruc": "20100047218",
        "id_detalle_categoria": id_detalle_categoria,
    }
    primera = await client.post("/api/v1/empresas", headers=headers, json=payload)
    assert primera.status_code == 201

    segunda = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={**payload, "nombre_empresa": "Empresa Dos"},
    )
    assert segunda.status_code == 409


async def test_ruc_formato_invalido_recibe_422(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        _, _, detalle = await create_grupo_categoria_detalle(session)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    response = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={
            "nombre_empresa": "Empresa RUC malo",
            "ruc": "123",
            "id_detalle_categoria": id_detalle_categoria,
        },
    )
    assert response.status_code == 422


async def test_detalle_categoria_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        headers = auth_header(actor)

    response = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={
            "nombre_empresa": "Empresa sin detalle",
            "ruc": "20999999999",
            "id_detalle_categoria": 999999,
        },
    )
    assert response.status_code == 404


async def test_detalle_categoria_inactivo_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        grupo, categoria, detalle = await create_grupo_categoria_detalle(
            session, id_grupo=701
        )
        grupo.estado = False
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    response = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={
            "nombre_empresa": "Empresa grupo inactivo",
            "ruc": "20888888888",
            "id_detalle_categoria": id_detalle_categoria,
        },
    )
    assert response.status_code == 404


async def test_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "SinPermisoEmpresas")
        actor = await create_user(session, rol, username="sin.permiso.empresa")
        _, _, detalle = await create_grupo_categoria_detalle(session, id_grupo=702)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    response = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={
            "nombre_empresa": "Empresa sin permiso",
            "ruc": "20777777777",
            "id_detalle_categoria": id_detalle_categoria,
        },
    )
    assert response.status_code == 403
