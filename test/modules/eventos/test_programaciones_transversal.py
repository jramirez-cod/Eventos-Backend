import pytest

from app.modules.eventos.models import EventoEstado
from app.modules.participantes.models import EventoEmpresa
from test.modules.contactos.conftest import create_empresa
from test.modules.eventos.conftest import (
    crear_evento_http,
    crear_programacion_http,
    future_date,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_listado_transversal_combina_programaciones_de_varios_eventos_ordenadas(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)

    evento_a = await crear_evento_http(
        client, headers, session_factory, nombre_evento="Evento A"
    )
    evento_b = await crear_evento_http(
        client, headers, session_factory, nombre_evento="Evento B"
    )

    lejana = await crear_programacion_http(
        client, headers, id_evento=evento_a["id_evento"], inicio_dias=40, fin_dias=41
    )
    cercana = await crear_programacion_http(
        client, headers, id_evento=evento_b["id_evento"], inicio_dias=5, fin_dias=6
    )

    response = await client.get(
        "/api/v1/eventos/programaciones", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    ids = [item["id_programacion_evento"] for item in body["items"]]
    assert ids == [
        cercana["id_programacion_evento"],
        lejana["id_programacion_evento"],
    ]
    nombres = {item["id_programacion_evento"]: item["nombre_evento"] for item in body["items"]}
    assert nombres[cercana["id_programacion_evento"]] == "Evento B"
    assert nombres[lejana["id_programacion_evento"]] == "Evento A"


async def test_listado_transversal_filtra_por_estado_fecha_y_empresa(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)

    evento = await crear_evento_http(client, headers, session_factory)
    id_evento = evento["id_evento"]

    abierta = await crear_programacion_http(
        client, headers, id_evento=id_evento, inicio_dias=5, fin_dias=6
    )
    finalizada = await crear_programacion_http(
        client, headers, id_evento=id_evento, inicio_dias=50, fin_dias=51
    )
    await client.patch(
        f"/api/v1/eventos/{id_evento}"
        f"/programaciones/{finalizada['id_programacion_evento']}/finalizar",
        headers=headers,
        json={},
    )

    async with session_factory() as session:
        empresa = await create_empresa(session, sequence=90_001)
        session.add(
            EventoEmpresa(
                id_programacion_evento=abierta["id_programacion_evento"],
                id_empresa=empresa.id_empresa,
                estado=True,
            )
        )
        await session.commit()
        id_empresa = empresa.id_empresa

    por_estado = await client.get(
        "/api/v1/eventos/programaciones",
        headers=headers,
        params={"estado": "FINALIZADO"},
    )
    assert por_estado.status_code == 200
    assert por_estado.json()["total"] == 1
    assert (
        por_estado.json()["items"][0]["id_programacion_evento"]
        == finalizada["id_programacion_evento"]
    )

    por_empresa = await client.get(
        "/api/v1/eventos/programaciones",
        headers=headers,
        params={"id_empresa": id_empresa},
    )
    assert por_empresa.status_code == 200
    assert por_empresa.json()["total"] == 1
    assert (
        por_empresa.json()["items"][0]["id_programacion_evento"]
        == abierta["id_programacion_evento"]
    )

    por_fecha = await client.get(
        "/api/v1/eventos/programaciones",
        headers=headers,
        params={"fecha_desde": future_date(1), "fecha_hasta": future_date(10)},
    )
    assert por_fecha.status_code == 200
    assert por_fecha.json()["total"] == 1
    assert (
        por_fecha.json()["items"][0]["id_programacion_evento"]
        == abierta["id_programacion_evento"]
    )


async def test_listado_transversal_paginado(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)

    evento = await crear_evento_http(client, headers, session_factory)
    id_evento = evento["id_evento"]
    for offset in (5, 15, 25):
        await crear_programacion_http(
            client,
            headers,
            id_evento=id_evento,
            inicio_dias=offset,
            fin_dias=offset + 1,
        )

    response = await client.get(
        "/api/v1/eventos/programaciones",
        headers=headers,
        params={"page": 2, "page_size": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["pages"] == 2
    assert body["page"] == 2
    assert len(body["items"]) == 1
