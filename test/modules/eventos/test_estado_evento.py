import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.eventos.models import Evento
from test.modules.eventos.conftest import (
    EVENT_PERMISSIONS,
    crear_evento_http,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_finalizar_evento_y_auditoria(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/finalizar",
        headers=headers,
        json={"motivo": "Cierre de inscripciones"},
    )
    assert response.status_code == 200
    assert response.json()["estado"] == "FINALIZADO"
    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "FINALIZAR_EVENTO")
        )
        assert audit is not None
        assert audit.motivo == "Cierre de inscripciones"


async def test_finalizar_dos_veces_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    url = f"/api/v1/eventos/{evento['id_evento']}/finalizar"
    await client.patch(url, headers=headers, json={})
    response = await client.patch(url, headers=headers, json={})
    assert response.status_code == 409


async def test_reabrir_evento_con_permiso_y_motivo(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/finalizar",
        headers=headers,
        json={},
    )
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/reabrir",
        headers=headers,
        json={"motivo": "Corrección autorizada"},
    )
    assert response.status_code == 200
    assert response.json()["estado"] == "ABIERTO"


async def test_personal_sin_permiso_no_reabre(client, session_factory) -> None:
    personal_permissions = tuple(
        permission
        for permission in EVENT_PERMISSIONS
        if permission not in {"REABRIR_EVENTO", "ELIMINAR_EVENTO"}
    )
    async with session_factory() as session:
        _, headers = await seed_event_actor(
            session, permissions=personal_permissions
        )
    evento = await crear_evento_http(client, headers)
    await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/finalizar",
        headers=headers,
        json={},
    )
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/reabrir",
        headers=headers,
        json={"motivo": "Intento sin permiso"},
    )
    assert response.status_code == 403


async def test_reabrir_requiere_motivo(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/finalizar",
        headers=headers,
        json={},
    )
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/reabrir",
        headers=headers,
        json={"motivo": "   "},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("finalizar_primero", [False, True])
async def test_inactivar_evento_desde_abierto_o_finalizado(
    client, session_factory, finalizar_primero: bool
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    if finalizar_primero:
        await client.patch(
            f"/api/v1/eventos/{evento['id_evento']}/finalizar",
            headers=headers,
            json={},
        )
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/inactivar",
        headers=headers,
        json={"motivo": "Baja administrativa"},
    )
    assert response.status_code == 200
    assert response.json()["estado"] == "INACTIVO"


async def test_evento_inactivo_solo_permite_consulta(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    id_evento = evento["id_evento"]
    await client.patch(
        f"/api/v1/eventos/{id_evento}/inactivar", headers=headers, json={}
    )
    query = await client.get(f"/api/v1/eventos/{id_evento}", headers=headers)
    update = await client.put(
        f"/api/v1/eventos/{id_evento}",
        headers=headers,
        json={"nombre_evento": "No debe cambiar"},
    )
    assert query.status_code == 200
    assert update.status_code == 409


async def test_eliminar_evento_sin_participantes_es_fisico_y_audita(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    id_evento = evento["id_evento"]
    response = await client.delete(f"/api/v1/eventos/{id_evento}", headers=headers)
    assert response.status_code == 204
    async with session_factory() as session:
        assert await session.get(Evento, id_evento) is None
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "ELIMINAR_EVENTO")
        )
        assert audit is not None
