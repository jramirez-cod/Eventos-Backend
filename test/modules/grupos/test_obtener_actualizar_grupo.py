import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.grupos.models import Grupo
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


pytestmark = pytest.mark.asyncio


async def _actor(session, *, con_permiso: bool = True):
    rol = await create_role(session, "ActorDetalleGrupo")
    if con_permiso:
        await grant_permission(
            session,
            rol,
            permiso_nombre="CREAR_GRUPO",
            modulo_nombre="GRUPOS",
        )
    actor = await create_user(session, rol, username="actor.detalle.grupo")
    await session.commit()
    return actor


async def test_obtener_y_actualizar_grupo_genera_auditoria(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        grupo = Grupo(
            id_grupo=810,
            nombre_grupo="Grupo inicial",
            descripcion="Descripción inicial",
            estado=False,
        )
        session.add(grupo)
        await session.commit()
        headers = auth_header(actor)

    detalle = await client.get("/api/v1/grupos/810", headers=headers)
    assert detalle.status_code == 200
    assert detalle.json()["nombre_grupo"] == "Grupo inicial"

    response = await client.put(
        "/api/v1/grupos/810",
        headers=headers,
        json={
            "nombre_grupo": "  Grupo   corregido  ",
            "descripcion": "  Descripción corregida  ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id_grupo": 810,
        "nombre_grupo": "Grupo corregido",
        "descripcion": "Descripción corregida",
        "estado": False,
    }

    async with session_factory() as session:
        auditoria = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "ACTUALIZAR_GRUPO")
        )
        assert auditoria is not None
        assert auditoria.id_usuario == actor.id_usuario
        assert auditoria.valor_anterior["nombre_grupo"] == "Grupo inicial"
        assert auditoria.valor_nuevo["nombre_grupo"] == "Grupo corregido"


async def test_obtener_grupo_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        headers = auth_header(actor)

    response = await client.get("/api/v1/grupos/999999", headers=headers)
    assert response.status_code == 404


async def test_actualizar_grupo_duplicado_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        session.add_all(
            [
                Grupo(id_grupo=811, nombre_grupo="Asociados", estado=True),
                Grupo(id_grupo=812, nombre_grupo="Expositores", estado=True),
            ]
        )
        await session.commit()
        headers = auth_header(actor)

    response = await client.put(
        "/api/v1/grupos/812",
        headers=headers,
        json={"nombre_grupo": "asociados", "descripcion": None},
    )
    assert response.status_code == 409


async def test_actualizar_grupo_rechaza_id_y_estado(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        session.add(Grupo(id_grupo=813, nombre_grupo="Original", estado=True))
        await session.commit()
        headers = auth_header(actor)

    response = await client.put(
        "/api/v1/grupos/813",
        headers=headers,
        json={
            "id_grupo": 999,
            "nombre_grupo": "Intento",
            "descripcion": None,
            "estado": False,
        },
    )
    assert response.status_code == 422


async def test_detalle_grupo_requiere_autenticacion(client) -> None:
    response = await client.get("/api/v1/grupos/810")
    assert response.status_code == 401


async def test_actualizar_grupo_sin_permiso_recibe_403(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session, con_permiso=False)
        session.add(Grupo(id_grupo=814, nombre_grupo="Restringido", estado=True))
        await session.commit()
        headers = auth_header(actor)

    response = await client.put(
        "/api/v1/grupos/814",
        headers=headers,
        json={"nombre_grupo": "No autorizado", "descripcion": None},
    )
    assert response.status_code == 403
