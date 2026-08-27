import pytest

from test.modules.eventos.conftest import (
    crear_evento_http,
    crear_programacion_http,
    future_date,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_evento_admite_multiples_programaciones_independientes(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    id_evento = evento["id_evento"]

    enero = await crear_programacion_http(
        client, headers, id_evento=id_evento, inicio_dias=10, fin_dias=10
    )
    febrero = await crear_programacion_http(
        client, headers, id_evento=id_evento, inicio_dias=40, fin_dias=41
    )

    assert enero["id_programacion_evento"] != febrero["id_programacion_evento"]

    listado = await client.get(
        f"/api/v1/eventos/{id_evento}/programaciones", headers=headers
    )
    assert listado.status_code == 200
    assert listado.json()["total"] == 2

    dias_enero = (
        await client.get(
            f"/api/v1/eventos/{id_evento}"
            f"/programaciones/{enero['id_programacion_evento']}/dias",
            headers=headers,
        )
    ).json()
    dias_febrero = (
        await client.get(
            f"/api/v1/eventos/{id_evento}"
            f"/programaciones/{febrero['id_programacion_evento']}/dias",
            headers=headers,
        )
    ).json()
    assert [d["fecha"] for d in dias_enero] == [future_date(10)]
    assert [d["fecha"] for d in dias_febrero] == [future_date(40), future_date(41)]


async def test_eliminar_dia_de_una_programacion_no_afecta_otra(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    id_evento = evento["id_evento"]

    primera = await crear_programacion_http(
        client, headers, id_evento=id_evento, inicio_dias=10, fin_dias=11
    )
    segunda = await crear_programacion_http(
        client, headers, id_evento=id_evento, inicio_dias=40, fin_dias=41
    )

    dias_primera = (
        await client.get(
            f"/api/v1/eventos/{id_evento}"
            f"/programaciones/{primera['id_programacion_evento']}/dias",
            headers=headers,
        )
    ).json()
    await client.delete(
        f"/api/v1/eventos/{id_evento}"
        f"/programaciones/{primera['id_programacion_evento']}/dias/"
        f"{dias_primera[0]['id_detalle_programacion']}",
        headers=headers,
    )

    dias_segunda = (
        await client.get(
            f"/api/v1/eventos/{id_evento}"
            f"/programaciones/{segunda['id_programacion_evento']}/dias",
            headers=headers,
        )
    ).json()
    assert len(dias_segunda) == 2
