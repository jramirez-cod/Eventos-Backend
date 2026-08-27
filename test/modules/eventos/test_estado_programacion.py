import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from test.modules.eventos.conftest import (
    EVENT_PERMISSIONS,
    crear_evento_http,
    crear_programacion_http,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_finalizar_programacion_y_auditoria(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    id_prog = programacion["id_programacion_evento"]
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/finalizar",
        headers=headers,
        json={"motivo": "Ya se realizó el evento"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "FINALIZADO"
    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "FINALIZAR_PROGRAMACION")
        )
        assert audit is not None
        assert audit.motivo == "Ya se realizó el evento"


async def test_finalizar_programacion_dos_veces_recibe_409(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    id_prog = programacion["id_programacion_evento"]
    url = f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/finalizar"
    await client.patch(url, headers=headers, json={})
    response = await client.patch(url, headers=headers, json={})
    assert response.status_code == 409


async def test_reabrir_programacion_con_permiso_y_motivo(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    id_prog = programacion["id_programacion_evento"]
    await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/finalizar",
        headers=headers,
        json={},
    )
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/reabrir",
        headers=headers,
        json={"motivo": "Corrección autorizada"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "ABIERTO"


async def test_personal_sin_permiso_no_reabre_programacion(
    client, session_factory
) -> None:
    personal_permissions = tuple(
        permission
        for permission in EVENT_PERMISSIONS
        if permission not in {"REABRIR_EVENTO", "ELIMINAR_EVENTO", "REABRIR_PROGRAMACION"}
    )
    async with session_factory() as session:
        _, headers = await seed_event_actor(
            session, permissions=personal_permissions
        )
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    id_prog = programacion["id_programacion_evento"]
    await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/finalizar",
        headers=headers,
        json={},
    )
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/reabrir",
        headers=headers,
        json={"motivo": "Intento sin permiso"},
    )
    assert response.status_code == 403


async def test_reabrir_programacion_requiere_motivo(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    id_prog = programacion["id_programacion_evento"]
    await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/finalizar",
        headers=headers,
        json={},
    )
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/reabrir",
        headers=headers,
        json={"motivo": "   "},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("finalizar_primero", [False, True])
async def test_inactivar_programacion_desde_abierta_o_finalizada(
    client, session_factory, finalizar_primero: bool
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    id_prog = programacion["id_programacion_evento"]
    if finalizar_primero:
        await client.patch(
            f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/finalizar",
            headers=headers,
            json={},
        )
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/inactivar",
        headers=headers,
        json={"motivo": "Baja administrativa"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["estado"] == "INACTIVO"


async def test_programacion_no_abierta_no_permite_editar(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    id_prog = programacion["id_programacion_evento"]
    await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/inactivar",
        headers=headers,
        json={},
    )
    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}",
        headers=headers,
        json={"enlace_general": "https://no-deberia-cambiar.example"},
    )
    assert response.status_code == 409

    dia = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/{id_prog}/dias",
        headers=headers,
        json={"fecha": "2026-12-20", "hora_inicio": "09:00:00", "hora_fin": "18:00:00"},
    )
    assert dia.status_code == 409
