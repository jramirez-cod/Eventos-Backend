import pytest

from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def _crear_evento_contacto(client, session_factory):
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )
    created = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    return headers, created.json()["evento_contactos"][0]


async def test_nuevo_evento_contacto_requiere_coordinacion_por_defecto(
    client, session_factory
) -> None:
    _, evento_contacto = await _crear_evento_contacto(client, session_factory)
    assert evento_contacto["requiere_coordinacion"] is True


async def test_marcar_asistencia_registra_hora_ingreso(client, session_factory) -> None:
    headers, evento_contacto = await _crear_evento_contacto(client, session_factory)
    assert evento_contacto["asistencia_evento"] is False
    assert evento_contacto["hora_ingreso"] is None

    response = await client.patch(
        f"/api/v1/participantes/evento-contactos/"
        f"{evento_contacto['id_evento_contacto']}/asistencia",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["asistencia_evento"] is True
    assert response.json()["hora_ingreso"] is not None


async def test_evento_contacto_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, *_ = await evento_contacto_context(session, client)
    response = await client.patch(
        "/api/v1/participantes/evento-contactos/999999/asistencia",
        headers=headers,
    )
    assert response.status_code == 404
