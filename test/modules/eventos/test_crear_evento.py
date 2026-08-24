from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.eventos.models import (
    DetalleProgramacionEvento,
    Evento,
    EventoEstado,
    ProgramacionEvento,
)
from app.modules.eventos.repository import EventoRepository
from scripts.create_db import Base
from test.modules.eventos.conftest import (
    evento_payload,
    future_date,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_crear_evento_genera_programacion_dias_y_auditoria(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)

    response = await client.post(
        "/api/v1/eventos", headers=headers, json=evento_payload()
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["estado"] == "ABIERTO"
    assert body["programacion"]["modalidad"] == "PRESENCIAL"
    assert body["programacion"]["lugar"]["distrito"] == "Miraflores"

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Evento)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ProgramacionEvento))
            == 1
        )
        dias = list(
            (
                await session.scalars(
                    select(DetalleProgramacionEvento).order_by(
                        DetalleProgramacionEvento.fecha
                    )
                )
            ).all()
        )
        assert [dia.fecha.isoformat() for dia in dias] == [
            future_date(10),
            future_date(11),
            future_date(12),
        ]
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "CREAR_EVENTO")
        )
        assert audit is not None


async def test_crear_evento_sin_autenticacion_recibe_401(client) -> None:
    response = await client.post("/api/v1/eventos", json=evento_payload())
    assert response.status_code == 401


async def test_crear_evento_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session, permissions=())
    response = await client.post(
        "/api/v1/eventos", headers=headers, json=evento_payload()
    )
    assert response.status_code == 403


async def test_fecha_inicio_pasada_es_rechazada(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    yesterday = (
        datetime.now(ZoneInfo("America/Lima")).date() - timedelta(days=1)
    ).isoformat()
    payload = evento_payload()
    payload["fecha_inicio"] = yesterday
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 400


async def test_fecha_final_anterior_es_rechazada(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    payload = evento_payload(inicio_dias=12, fin_dias=10)
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 400


async def test_evento_de_un_dia_es_valido(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    payload = evento_payload(inicio_dias=10, fin_dias=10)
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 201
    id_evento = response.json()["id_evento"]
    dias = await client.get(
        f"/api/v1/eventos/{id_evento}/dias", headers=headers
    )
    assert len(dias.json()) == 1


async def test_nombre_repetido_no_bloquea_creacion(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    first = await client.post(
        "/api/v1/eventos", headers=headers, json=evento_payload()
    )
    second = await client.post(
        "/api/v1/eventos", headers=headers, json=evento_payload()
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id_evento"] != second.json()["id_evento"]


async def test_create_db_registra_metadata_de_eventos() -> None:
    assert {
        "evento",
        "programacion_evento",
        "detalle_programacion_evento",
        "lugar",
    } <= set(Base.metadata.tables)


async def test_create_all_crea_tablas_de_eventos(session_factory) -> None:
    async with session_factory() as session:
        for table_name in (
            "evento",
            "programacion_evento",
            "detalle_programacion_evento",
            "lugar",
        ):
            table = await session.scalar(
                select(func.to_regclass(table_name))
            )
            assert str(table) == table_name


async def test_estado_modelado_como_enum(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    response = await client.post(
        "/api/v1/eventos", headers=headers, json=evento_payload()
    )
    async with session_factory() as session:
        evento = await session.get(Evento, response.json()["id_evento"])
        assert evento is not None
        assert evento.estado == EventoEstado.ABIERTO


async def test_creacion_hace_rollback_si_falla_generacion_de_dias(
    client, session_factory, monkeypatch
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)

    original = EventoRepository.create_dia
    calls = 0

    async def fail_on_second_day(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fallo controlado")
        return await original(self, **kwargs)

    monkeypatch.setattr(EventoRepository, "create_dia", fail_on_second_day)
    with pytest.raises(RuntimeError, match="fallo controlado"):
        await client.post("/api/v1/eventos", headers=headers, json=evento_payload())

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Evento)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(ProgramacionEvento))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(DetalleProgramacionEvento)
            )
            == 0
        )
