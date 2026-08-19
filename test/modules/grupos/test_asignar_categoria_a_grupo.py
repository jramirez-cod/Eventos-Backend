import pytest

from app.modules.categorias.models import Categoria
from app.modules.grupos.models import Grupo
from test.modules.usuarios.conftest import auth_header, create_role, create_user, grant_permission


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorAsignacion")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="GRUPOS"
        )
    actor = await create_user(session, rol, username="actor.asignacion")
    await session.commit()
    return actor


async def _grupo_y_categoria(session):
    grupo = Grupo(id_grupo=600, nombre_grupo="Asociados", estado=True)
    categoria_a = Categoria(nombre_categoria="A", estado=True)
    categoria_c = Categoria(nombre_categoria="C", estado=True)
    session.add_all([grupo, categoria_a, categoria_c])
    await session.commit()
    return grupo, categoria_a, categoria_c


async def test_asignar_categoria_ok(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_GRUPO"])
        grupo, categoria_a, _ = await _grupo_y_categoria(session)
        headers = auth_header(actor)

    response = await client.post(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias",
        headers=headers,
        json={"id_categoria": categoria_a.id_categoria},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_grupo"] == grupo.id_grupo
    assert body["id_categoria"] == categoria_a.id_categoria
    assert body["nombre_categoria"] == "A"
    assert body["estado"] is True


async def test_grupo_puede_tener_varias_categorias(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_GRUPO"])
        grupo, categoria_a, categoria_c = await _grupo_y_categoria(session)
        headers = auth_header(actor)

    for categoria in (categoria_a, categoria_c):
        response = await client.post(
            f"/api/v1/grupos/{grupo.id_grupo}/categorias",
            headers=headers,
            json={"id_categoria": categoria.id_categoria},
        )
        assert response.status_code == 201

    listado = await client.get(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias", headers=headers
    )
    assert listado.status_code == 200
    nombres = {item["nombre_categoria"] for item in listado.json()}
    assert nombres == {"A", "C"}


async def test_categoria_ya_asignada_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_GRUPO"])
        grupo, categoria_a, _ = await _grupo_y_categoria(session)
        headers = auth_header(actor)

    payload = {"id_categoria": categoria_a.id_categoria}
    primera = await client.post(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias", headers=headers, json=payload
    )
    assert primera.status_code == 201

    segunda = await client.post(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias", headers=headers, json=payload
    )
    assert segunda.status_code == 409


async def test_grupo_o_categoria_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_GRUPO"])
        grupo, categoria_a, _ = await _grupo_y_categoria(session)
        headers = auth_header(actor)

    grupo_inexistente = await client.post(
        "/api/v1/grupos/999999/categorias",
        headers=headers,
        json={"id_categoria": categoria_a.id_categoria},
    )
    assert grupo_inexistente.status_code == 404

    categoria_inexistente = await client.post(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias",
        headers=headers,
        json={"id_categoria": 999999},
    )
    assert categoria_inexistente.status_code == 404


async def test_quitar_asignacion_es_soft_y_desaparece_del_listado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(
            session, permisos=["CREAR_GRUPO", "INACTIVAR_GRUPO"]
        )
        grupo, categoria_a, _ = await _grupo_y_categoria(session)
        headers = auth_header(actor)

    asignar = await client.post(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias",
        headers=headers,
        json={"id_categoria": categoria_a.id_categoria},
    )
    assert asignar.status_code == 201

    quitar = await client.patch(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias/{categoria_a.id_categoria}/quitar",
        headers=headers,
    )
    assert quitar.status_code == 200
    assert quitar.json()["estado"] is False

    listado = await client.get(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias", headers=headers
    )
    assert listado.json() == []

    async with session_factory() as session:
        from sqlalchemy import select

        from app.modules.categorias.models import DetalleCategoria

        fila = await session.scalar(
            select(DetalleCategoria).where(
                DetalleCategoria.id_grupo == grupo.id_grupo,
                DetalleCategoria.id_categoria == categoria_a.id_categoria,
            )
        )
        assert fila is not None
        assert fila.estado is False


async def test_quitar_asignacion_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["INACTIVAR_GRUPO"])
        grupo, categoria_a, _ = await _grupo_y_categoria(session)
        headers = auth_header(actor)

    response = await client.patch(
        f"/api/v1/grupos/{grupo.id_grupo}/categorias/{categoria_a.id_categoria}/quitar",
        headers=headers,
    )
    assert response.status_code == 404
