import pytest

from test.modules.eventos.conftest import (
    crear_evento_http,
    crear_programacion_http,
    seed_event_actor,
)
from test.modules.usuarios.conftest import create_role, create_user


pytestmark = pytest.mark.asyncio


async def _crear_evento_y_programacion(client, headers, session_factory):
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    return evento, programacion


async def test_asignar_responsable_y_listar(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        role = await create_role(session, "Rol Responsable")
        responsable = await create_user(session, role, username="responsable.uno")
        await session.commit()
        id_usuario = responsable.id_usuario

    evento, programacion = await _crear_evento_y_programacion(
        client, headers, session_factory
    )
    url = (
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}/responsables"
    )

    response = await client.post(url, headers=headers, json={"id_usuario": id_usuario})
    assert response.status_code == 201, response.text
    assert response.json()["id_usuario"] == id_usuario
    assert response.json()["estado"] is True

    listado = await client.get(url, headers=headers)
    assert listado.status_code == 200
    assert len(listado.json()) == 1


async def test_asignar_responsable_duplicado_recibe_409(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        role = await create_role(session, "Rol Responsable Dup")
        responsable = await create_user(session, role, username="responsable.dup")
        await session.commit()
        id_usuario = responsable.id_usuario

    evento, programacion = await _crear_evento_y_programacion(
        client, headers, session_factory
    )
    url = (
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}/responsables"
    )
    first = await client.post(url, headers=headers, json={"id_usuario": id_usuario})
    second = await client.post(url, headers=headers, json={"id_usuario": id_usuario})
    assert first.status_code == 201
    assert second.status_code == 409


async def test_desactivar_responsable(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        role = await create_role(session, "Rol Responsable Estado")
        responsable = await create_user(session, role, username="responsable.estado")
        await session.commit()
        id_usuario = responsable.id_usuario

    evento, programacion = await _crear_evento_y_programacion(
        client, headers, session_factory
    )
    base_url = (
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}/responsables"
    )
    created = await client.post(
        base_url, headers=headers, json={"id_usuario": id_usuario}
    )
    id_responsable = created.json()["id_responsable_evento"]

    response = await client.patch(
        f"{base_url}/{id_responsable}/estado",
        headers=headers,
        params={"estado": "false"},
    )
    assert response.status_code == 200
    assert response.json()["estado"] is False


async def test_asignar_responsable_a_programacion_no_abierta_recibe_409(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        role = await create_role(session, "Rol Responsable No Abierta")
        responsable = await create_user(
            session, role, username="responsable.no.abierta"
        )
        await session.commit()
        id_usuario = responsable.id_usuario

    evento, programacion = await _crear_evento_y_programacion(
        client, headers, session_factory
    )
    id_evento = evento["id_evento"]
    id_prog = programacion["id_programacion_evento"]
    await client.patch(
        f"/api/v1/eventos/{id_evento}/programaciones/{id_prog}/finalizar",
        headers=headers,
        json={},
    )

    response = await client.post(
        f"/api/v1/eventos/{id_evento}/programaciones/{id_prog}/responsables",
        headers=headers,
        json={"id_usuario": id_usuario},
    )
    assert response.status_code == 409, response.text


async def test_cambiar_estado_responsable_en_programacion_no_abierta_recibe_409(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        role = await create_role(session, "Rol Responsable Estado Cerrada")
        responsable = await create_user(
            session, role, username="responsable.estado.cerrada"
        )
        await session.commit()
        id_usuario = responsable.id_usuario

    evento, programacion = await _crear_evento_y_programacion(
        client, headers, session_factory
    )
    id_evento = evento["id_evento"]
    id_prog = programacion["id_programacion_evento"]
    base_url = f"/api/v1/eventos/{id_evento}/programaciones/{id_prog}/responsables"
    created = await client.post(
        base_url, headers=headers, json={"id_usuario": id_usuario}
    )
    id_responsable = created.json()["id_responsable_evento"]

    await client.patch(
        f"/api/v1/eventos/{id_evento}/programaciones/{id_prog}/finalizar",
        headers=headers,
        json={},
    )

    response = await client.patch(
        f"{base_url}/{id_responsable}/estado",
        headers=headers,
        params={"estado": "false"},
    )
    assert response.status_code == 409, response.text


async def test_asignar_responsable_a_programacion_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        role = await create_role(session, "Rol Responsable Inexistente")
        responsable = await create_user(
            session, role, username="responsable.inexistente"
        )
        await session.commit()
        id_usuario = responsable.id_usuario

    evento = await crear_evento_http(client, headers, session_factory)
    response = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones/999999/responsables",
        headers=headers,
        json={"id_usuario": id_usuario},
    )
    assert response.status_code == 404
