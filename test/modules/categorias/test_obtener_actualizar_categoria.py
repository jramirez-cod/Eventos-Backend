import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.categorias.models import Categoria
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


pytestmark = pytest.mark.asyncio


async def _actor(session, *, con_permiso: bool = True):
    rol = await create_role(session, "ActorDetalleCategoria")
    if con_permiso:
        await grant_permission(
            session,
            rol,
            permiso_nombre="CREAR_CATEGORIA",
            modulo_nombre="CATEGORIAS",
        )
    actor = await create_user(session, rol, username="actor.detalle.categoria")
    await session.commit()
    return actor


async def test_obtener_y_actualizar_categoria_genera_auditoria(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        categoria = Categoria(
            nombre_categoria="Categoría inicial",
            descripcion="Descripción inicial",
            estado=False,
        )
        session.add(categoria)
        await session.commit()
        id_categoria = categoria.id_categoria
        headers = auth_header(actor)

    detalle = await client.get(
        f"/api/v1/categorias/{id_categoria}", headers=headers
    )
    assert detalle.status_code == 200
    assert detalle.json()["nombre_categoria"] == "Categoría inicial"

    response = await client.put(
        f"/api/v1/categorias/{id_categoria}",
        headers=headers,
        json={
            "nombre_categoria": "  Categoría   corregida  ",
            "descripcion": "  Descripción corregida  ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id_categoria"] == id_categoria
    assert body["nombre_categoria"] == "Categoría corregida"
    assert body["descripcion"] == "Descripción corregida"
    assert body["estado"] is False

    async with session_factory() as session:
        auditoria = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "ACTUALIZAR_CATEGORIA")
        )
        assert auditoria is not None
        assert auditoria.id_usuario == actor.id_usuario
        assert auditoria.valor_anterior["nombre_categoria"] == "Categoría inicial"
        assert auditoria.valor_nuevo["nombre_categoria"] == "Categoría corregida"


async def test_obtener_categoria_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        headers = auth_header(actor)

    response = await client.get("/api/v1/categorias/999999", headers=headers)
    assert response.status_code == 404


async def test_actualizar_categoria_duplicada_recibe_409(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        categoria_a = Categoria(nombre_categoria="Categoría A", estado=True)
        categoria_b = Categoria(nombre_categoria="Categoría B", estado=True)
        session.add_all([categoria_a, categoria_b])
        await session.commit()
        id_categoria_b = categoria_b.id_categoria
        headers = auth_header(actor)

    response = await client.put(
        f"/api/v1/categorias/{id_categoria_b}",
        headers=headers,
        json={"nombre_categoria": "categoría a", "descripcion": None},
    )
    assert response.status_code == 409


async def test_actualizar_categoria_rechaza_id_y_estado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        categoria = Categoria(nombre_categoria="Original", estado=True)
        session.add(categoria)
        await session.commit()
        id_categoria = categoria.id_categoria
        headers = auth_header(actor)

    response = await client.put(
        f"/api/v1/categorias/{id_categoria}",
        headers=headers,
        json={
            "id_categoria": 999,
            "nombre_categoria": "Intento",
            "descripcion": None,
            "estado": False,
        },
    )
    assert response.status_code == 422


async def test_detalle_categoria_requiere_autenticacion(client) -> None:
    response = await client.get("/api/v1/categorias/1")
    assert response.status_code == 401


async def test_actualizar_categoria_sin_permiso_recibe_403(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session, con_permiso=False)
        categoria = Categoria(nombre_categoria="Restringida", estado=True)
        session.add(categoria)
        await session.commit()
        id_categoria = categoria.id_categoria
        headers = auth_header(actor)

    response = await client.put(
        f"/api/v1/categorias/{id_categoria}",
        headers=headers,
        json={"nombre_categoria": "No autorizada", "descripcion": None},
    )
    assert response.status_code == 403
