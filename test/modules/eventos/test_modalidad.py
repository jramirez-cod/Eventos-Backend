import pytest

from test.modules.eventos.conftest import (
    crear_evento_http,
    programacion_payload,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("modalidad", ["PRESENCIAL", "HIBRIDO"])
async def test_modalidades_validas_con_lugar(
    client, session_factory, modalidad: str
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    payload = programacion_payload(modalidad=modalidad, incluir_lugar=True)
    response = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    assert response.json()["modalidad"] == modalidad
    assert response.json()["lugar"] is not None


async def test_virtual_permite_omitir_lugar(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    payload = programacion_payload(modalidad="VIRTUAL", incluir_lugar=False)
    response = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    assert response.json()["modalidad"] == "VIRTUAL"
    assert response.json()["lugar"] is None


async def test_virtual_no_admite_lugar(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    payload = programacion_payload(modalidad="VIRTUAL", incluir_lugar=True)
    response = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("modalidad", ["PRESENCIAL", "HIBRIDO"])
async def test_presencial_e_hibrido_requieren_lugar(
    client, session_factory, modalidad: str
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    payload = programacion_payload(modalidad=modalidad, incluir_lugar=False)
    response = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 422, response.text


async def test_modalidad_invalida_recibe_422(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    payload = programacion_payload(incluir_lugar=False)
    payload["modalidad"] = "TELETRANSPORTE"
    response = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 422


async def test_modalidad_es_obligatoria(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    payload = programacion_payload(incluir_lugar=False)
    payload.pop("modalidad")
    response = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}/programaciones",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 422
