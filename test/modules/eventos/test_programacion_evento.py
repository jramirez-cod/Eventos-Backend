import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.eventos.models import DetalleProgramacionEvento, Lugar
from test.modules.eventos.conftest import (
    crear_evento_http,
    future_date,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_consultar_y_actualizar_programacion(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    url = f"/api/v1/eventos/{evento['id_evento']}/programacion"

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
    evento = await crear_evento_http(client, headers)
    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/programacion",
        headers=headers,
        json={"modalidad": "VIRTUAL", "lugar": None, "enlace_general": None},
    )
    assert response.status_code == 200
    assert response.json()["lugar"] is None
    assert response.json()["enlace_general"] is None
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Lugar)) == 0


async def test_dias_se_devuelven_ordenados_y_se_edita_horario(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    dias_url = f"/api/v1/eventos/{evento['id_evento']}/dias"
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


async def test_hora_fin_no_puede_ser_menor_o_igual(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    dias = (
        await client.get(
            f"/api/v1/eventos/{evento['id_evento']}/dias", headers=headers
        )
    ).json()
    response = await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/dias/"
        f"{dias[0]['id_detalle_programacion']}",
        headers=headers,
        json={"hora_inicio": "10:00:00", "hora_fin": "10:00:00"},
    )
    assert response.status_code == 400


async def test_dia_de_otro_evento_no_puede_modificarse(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    first = await crear_evento_http(client, headers, nombre_evento="Evento Uno")
    second = await crear_evento_http(client, headers, nombre_evento="Evento Dos")
    second_days = (
        await client.get(
            f"/api/v1/eventos/{second['id_evento']}/dias", headers=headers
        )
    ).json()
    response = await client.patch(
        f"/api/v1/eventos/{first['id_evento']}/dias/"
        f"{second_days[0]['id_detalle_programacion']}",
        headers=headers,
        json={"hora_inicio": "11:00:00"},
    )
    assert response.status_code == 404


async def test_cambiar_rango_preserva_dias_comunes_y_regenera_extremos(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)
    id_evento = evento["id_evento"]
    dias = (
        await client.get(f"/api/v1/eventos/{id_evento}/dias", headers=headers)
    ).json()
    middle = dias[1]
    await client.patch(
        f"/api/v1/eventos/{id_evento}/dias/{middle['id_detalle_programacion']}",
        headers=headers,
        json={"hora_inicio": "11:00:00", "hora_fin": "14:00:00"},
    )

    response = await client.put(
        f"/api/v1/eventos/{id_evento}",
        headers=headers,
        json={"fecha_inicio": future_date(11), "fecha_fin": future_date(13)},
    )
    assert response.status_code == 200, response.text
    updated = (
        await client.get(f"/api/v1/eventos/{id_evento}/dias", headers=headers)
    ).json()
    assert [item["fecha"] for item in updated] == [
        future_date(11),
        future_date(12),
        future_date(13),
    ]
    assert updated[0]["id_detalle_programacion"] == middle[
        "id_detalle_programacion"
    ]
    assert updated[0]["hora_inicio"] == "11:00:00"
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(DetalleProgramacionEvento)
        )
        assert count == 3


async def test_constraint_impide_segunda_sesion_en_la_misma_fecha(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers)

    async with session_factory() as session:
        original = await session.scalar(
            select(DetalleProgramacionEvento).order_by(
                DetalleProgramacionEvento.fecha
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
