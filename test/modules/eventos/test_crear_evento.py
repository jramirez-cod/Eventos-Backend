from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.categorias.models import Categoria
from app.modules.eventos.models import (
    DetallePoliticaEvento,
    Evento,
    EventoEstado,
    PoliticaEvento,
)
from app.modules.eventos.repository import EventoRepository
from app.modules.maestros.models import Area, Beneficio
from scripts.create_db import Base
from test.modules.eventos.conftest import (
    create_evento_dependencies,
    evento_payload,
    future_date,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_crear_evento_genera_politica_y_auditoria(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        area, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
        )

    response = await client.post("/api/v1/eventos", headers=headers, json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["estado"] == "ABIERTO"
    assert body["nombre_area"] == area.nombre_area
    assert body["politica"]["fecha_inicio"] == payload["politica"]["fecha_inicio"]
    assert len(body["politica"]["detalles"]) == 1
    assert body["politica"]["detalles"][0]["nombre_beneficio"] == beneficio.nombre

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Evento)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(PoliticaEvento))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(DetallePoliticaEvento)
            )
            == 1
        )
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "CREAR_EVENTO")
        )
        assert audit is not None


async def test_crear_evento_sin_autenticacion_recibe_401(
    client, session_factory
) -> None:
    async with session_factory() as session:
        area, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
        )
    response = await client.post("/api/v1/eventos", json=payload)
    assert response.status_code == 401


async def test_crear_evento_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session, permissions=())
        area, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
        )
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 403


async def test_fecha_inicio_pasada_es_rechazada(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        area, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
        )
    yesterday = (
        datetime.now(ZoneInfo("America/Lima")).date() - timedelta(days=1)
    ).isoformat()
    payload["politica"]["fecha_inicio"] = yesterday
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 400


async def test_fecha_final_anterior_es_rechazada(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        area, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
        )
    payload["politica"]["fecha_inicio"] = future_date(20)
    payload["politica"]["fecha_fin"] = future_date(10)
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 400


async def test_area_inexistente_o_inactiva_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        _, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=999999,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
        )
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 404


async def test_beneficio_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        area, _, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=999999,
            id_categoria=categoria.id_categoria,
        )
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 404


async def test_categoria_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        area, beneficio, _ = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=999999,
        )
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 404


async def test_nombre_repetido_no_bloquea_creacion(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        area, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
        )
    first = await client.post("/api/v1/eventos", headers=headers, json=payload)
    second = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id_evento"] != second.json()["id_evento"]


async def test_create_db_registra_metadata_de_eventos() -> None:
    assert {
        "evento",
        "politica_evento",
        "detalle_politica_evento",
        "programacion_evento",
        "detalle_programacion_evento",
        "lugar",
        "responsable_evento",
    } <= set(Base.metadata.tables)


async def test_create_all_crea_tablas_de_eventos(session_factory) -> None:
    async with session_factory() as session:
        for table_name in (
            "evento",
            "politica_evento",
            "detalle_politica_evento",
            "programacion_evento",
            "detalle_programacion_evento",
            "lugar",
            "responsable_evento",
        ):
            table = await session.scalar(select(func.to_regclass(table_name)))
            assert str(table) == table_name


async def test_estado_modelado_como_enum(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        area, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
        )
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    async with session_factory() as session:
        evento = await session.get(Evento, response.json()["id_evento"])
        assert evento is not None
        assert evento.estado == EventoEstado.ABIERTO


async def test_creacion_hace_rollback_si_falla_creacion_de_detalle_politica(
    client, session_factory, monkeypatch
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        area = Area(nombre_area="Area Rollback", estado=True)
        beneficio_1 = Beneficio(nombre="Beneficio Rollback 1", estado=True)
        beneficio_2 = Beneficio(nombre="Beneficio Rollback 2", estado=True)
        categoria = Categoria(nombre_categoria="Categoria Rollback", estado=True)
        categoria_2 = Categoria(nombre_categoria="Categoria Rollback 2", estado=True)
        session.add_all([area, beneficio_1, beneficio_2, categoria, categoria_2])
        await session.flush()
        await session.commit()
        payload = evento_payload(
            id_area=area.id_area,
            id_beneficio=beneficio_1.id_beneficio,
            id_categoria=categoria.id_categoria,
        )
        payload["politica"]["detalles"].append(
            {
                "id_beneficio": beneficio_2.id_beneficio,
                "id_categoria": categoria_2.id_categoria,
                "entradas_gratuitas": 1,
            }
        )

    original = EventoRepository.create_detalle_politica
    calls = 0

    async def fail_on_second_detalle(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fallo controlado")
        return await original(self, **kwargs)

    monkeypatch.setattr(
        EventoRepository, "create_detalle_politica", fail_on_second_detalle
    )
    with pytest.raises(RuntimeError, match="fallo controlado"):
        await client.post("/api/v1/eventos", headers=headers, json=payload)

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Evento)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(PoliticaEvento))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(DetallePoliticaEvento)
            )
            == 0
        )
