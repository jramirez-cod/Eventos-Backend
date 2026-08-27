import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.eventos.models import DetalleProgramacionEvento, Lugar
from test.modules.eventos.conftest import (
    crear_evento_http,
    crear_programacion_http,
    future_date,
    programacion_payload,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_crear_consultar_y_actualizar_programacion(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    url = (
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}"
    )

    response = await client.put(
        url,
        headers=headers,
        json={
            "modalidad": "HIBRIDO",
            "enlace_general": "https://meet.example/evento",
            "lugar": {
                "pais": "Perú",
                "provincia": "Callao",
                "distrito": "La Perla",
                "direccion": "Av. La Marina 500",
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["modalidad"] == "HIBRIDO"
    assert response.json()["lugar"]["provincia"] == "Callao"
    get_response = await client.get(url, headers=headers)
    assert get_response.json() == response.json()
    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "ACTUALIZAR_PROGRAMACION_EVENTO"
            )
        )
        assert audit is not None


async def test_programacion_permite_quitar_lugar_y_enlace(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}",
        headers=headers,
        json={"modalidad": "VIRTUAL", "lugar": None, "enlace_general": None},
    )
    assert response.status_code == 200
    assert response.json()["lugar"] is None
    assert response.json()["enlace_general"] is None
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Lugar)) == 0


async def test_actualizar_no_permite_quitar_lugar_si_sigue_presencial(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"], modalidad="PRESENCIAL"
    )
    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}",
        headers=headers,
        json={"lugar": None},
    )
    assert response.status_code == 400, response.text


async def test_dia_con_fecha_pasada_es_rechazado(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    response = await client.post(
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}/dias",
        headers=headers,
        json={
            "fecha": future_date(-1),
            "hora_inicio": "09:00:00",
            "hora_fin": "18:00:00",
        },
    )
    assert response.status_code == 422, response.text


async def test_listar_programaciones_filtra_por_fecha_modalidad_estado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    id_evento = evento["id_evento"]
    presencial = await crear_programacion_http(
        client,
        headers,
        id_evento=id_evento,
        modalidad="PRESENCIAL",
        inicio_dias=10,
        fin_dias=10,
    )
    virtual = await crear_programacion_http(
        client,
        headers,
        id_evento=id_evento,
        modalidad="VIRTUAL",
        inicio_dias=30,
        fin_dias=30,
        incluir_lugar=False,
    )

    por_modalidad = await client.get(
        f"/api/v1/eventos/{id_evento}/programaciones",
        headers=headers,
        params={"modalidad": "VIRTUAL"},
    )
    assert por_modalidad.status_code == 200
    assert por_modalidad.json()["total"] == 1
    assert (
        por_modalidad.json()["items"][0]["id_programacion_evento"]
        == virtual["id_programacion_evento"]
    )

    por_fecha = await client.get(
        f"/api/v1/eventos/{id_evento}/programaciones",
        headers=headers,
        params={"fecha_desde": future_date(9), "fecha_hasta": future_date(11)},
    )
    assert por_fecha.status_code == 200
    assert por_fecha.json()["total"] == 1
    assert (
        por_fecha.json()["items"][0]["id_programacion_evento"]
        == presencial["id_programacion_evento"]
    )


async def test_dias_se_devuelven_ordenados_y_se_edita_horario(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client,
        headers,
        id_evento=evento["id_evento"],
        inicio_dias=10,
        fin_dias=12,
    )
    dias_url = (
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}/dias"
    )
    dias = (await client.get(dias_url, headers=headers)).json()
    assert [item["fecha"] for item in dias] == [
        future_date(10),
        future_date(11),
        future_date(12),
    ]

    response = await client.patch(
        f"{dias_url}/{dias[1]['id_detalle_programacion']}",
        headers=headers,
        json={
            "hora_inicio": "10:30:00",
            "hora_fin": "12:00:00",
            "enlace": "https://meet.example/dia-2",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["hora_inicio"] == "10:30:00"


async def test_hora_fin_no_puede_ser_menor_o_igual(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )
    dias_url = (
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}/dias"
    )
    dias = (await client.get(dias_url, headers=headers)).json()
    response = await client.patch(
        f"{dias_url}/{dias[0]['id_detalle_programacion']}",
        headers=headers,
        json={"hora_inicio": "10:00:00", "hora_fin": "10:00:00"},
    )
    assert response.status_code == 400


async def test_dia_de_otra_programacion_no_puede_modificarse(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    id_evento = evento["id_evento"]
    first = await crear_programacion_http(
        client, headers, id_evento=id_evento, inicio_dias=10, fin_dias=10
    )
    second = await crear_programacion_http(
        client, headers, id_evento=id_evento, inicio_dias=30, fin_dias=30
    )
    second_days = (
        await client.get(
            f"/api/v1/eventos/{id_evento}"
            f"/programaciones/{second['id_programacion_evento']}/dias",
            headers=headers,
        )
    ).json()
    response = await client.patch(
        f"/api/v1/eventos/{id_evento}"
        f"/programaciones/{first['id_programacion_evento']}/dias/"
        f"{second_days[0]['id_detalle_programacion']}",
        headers=headers,
        json={"hora_inicio": "11:00:00"},
    )
    assert response.status_code == 404


async def test_agregar_y_eliminar_dia(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"], inicio_dias=10, fin_dias=10
    )
    dias_url = (
        f"/api/v1/eventos/{evento['id_evento']}"
        f"/programaciones/{programacion['id_programacion_evento']}/dias"
    )

    created = await client.post(
        dias_url,
        headers=headers,
        json={
            "fecha": future_date(11),
            "hora_inicio": "09:00:00",
            "hora_fin": "17:00:00",
        },
    )
    assert created.status_code == 201, created.text

    first_id = (await client.get(dias_url, headers=headers)).json()[0][
        "id_detalle_programacion"
    ]
    deleted = await client.delete(f"{dias_url}/{first_id}", headers=headers)
    assert deleted.status_code == 204

    remaining = (await client.get(dias_url, headers=headers)).json()
    assert len(remaining) == 1

    last = await client.delete(
        f"{dias_url}/{remaining[0]['id_detalle_programacion']}", headers=headers
    )
    assert last.status_code == 409


async def test_constraint_impide_segunda_sesion_en_la_misma_fecha(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    programacion = await crear_programacion_http(
        client, headers, id_evento=evento["id_evento"]
    )

    async with session_factory() as session:
        original = await session.scalar(
            select(DetalleProgramacionEvento).where(
                DetalleProgramacionEvento.id_programacion_evento
                == programacion["id_programacion_evento"]
            )
        )
        assert original is not None
        session.add(
            DetalleProgramacionEvento(
                id_programacion_evento=original.id_programacion_evento,
                fecha=original.fecha,
                hora_inicio=original.hora_inicio,
                hora_fin=original.hora_fin,
                enlace=None,
                estado=True,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
