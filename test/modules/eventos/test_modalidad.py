import pytest

from test.modules.eventos.conftest import evento_payload, seed_event_actor


pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("modalidad", ["PRESENCIAL", "VIRTUAL", "HIBRIDO"])
async def test_modalidades_validas_y_lugar_opcional(
    client, session_factory, modalidad: str
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    payload = evento_payload(modalidad=modalidad)
    payload["lugar"] = None
    payload["enlace_general"] = None
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["programacion"]["modalidad"] == modalidad
    assert response.json()["programacion"]["lugar"] is None


async def test_modalidad_invalida_recibe_422(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    response = await client.post(
        "/api/v1/eventos",
        headers=headers,
        json=evento_payload(modalidad="TELETRANSPORTE"),
    )
    assert response.status_code == 422


async def test_modalidad_es_obligatoria(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    payload = evento_payload()
    payload.pop("modalidad")
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 422
